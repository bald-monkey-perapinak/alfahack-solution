"""Observed links are evidence of connectivity, not proof of supply-chain dependency."""

from collections import deque

from .config import get_settings

NOTE = (
    "Связи из данных организаторов: платежи, группы и общие обезличенные лица. "
    "Они не доказывают поставку или критическую зависимость; доли относятся только к наблюдаемым платежам."
)


def dataset_note():
    limit = get_settings().payment_import_limit_per_direction
    if not limit:
        return NOTE
    return NOTE + (
        f" В этой публикации сохранено до {limit} крупнейших платежных наблюдений "
        "на компанию в каждом направлении; доли рассчитаны по сохраненной выборке."
    )


def rebuild_payment_connections(db):
    with db.transaction() as conn:
        conn.execute("TRUNCATE payment_connections")
        conn.execute("""INSERT INTO payment_connections
            (payer_id,beneficiary_id,amount,payment_count,observation_count,payer_share,beneficiary_share)
            WITH pairs AS (
                SELECT payer_id,beneficiary_id,count(*)::int AS n,
                    CASE WHEN count(*)=1 THEN max(amount) END AS amount,
                    CASE WHEN count(*)=1 THEN max(payment_count) END AS cnt
                FROM payment_flows WHERE payer_id<>beneficiary_id GROUP BY payer_id,beneficiary_id
            ) SELECT payer_id,beneficiary_id,amount,cnt,n,
                (amount/NULLIF(sum(amount) OVER(PARTITION BY payer_id),0))::double precision,
                (amount/NULLIF(sum(amount) OVER(PARTITION BY beneficiary_id),0))::double precision
            FROM pairs""")
        return conn.execute("SELECT count(*) AS count FROM payment_connections").fetchone()["count"]


def neighbors(db, organization_id, limit=20):
    # Each branch is independently bounded and indexed; no group cliques are materialized.
    rows = db.all(
        """WITH links AS (
        (SELECT counterparty_id AS related_id,relation_type AS kind,
                COALESCE(dependency_weight,0.5)::double precision AS weight,
                dependency_weight::double precision AS dependency_weight,evidence,
                'dependency'::text AS direction,NULL::double precision AS share,1 AS observations
         FROM organization_relations WHERE organization_id=%s
         ORDER BY dependency_weight DESC NULLS LAST LIMIT %s)
        UNION ALL
        (SELECT beneficiary_id,'payment',GREATEST(0.02,COALESCE(payer_share,0.02)),NULL::double precision,
                'Компания перечисляла средства этому получателю; назначение платежей неизвестно.',
                'outgoing',payer_share,observation_count
         FROM payment_connections WHERE payer_id=%s ORDER BY payer_share DESC NULLS LAST LIMIT %s)
        UNION ALL
        (SELECT payer_id,'payment',GREATEST(0.02,COALESCE(beneficiary_share,0.02)),NULL::double precision,
                'Компания получала средства от этого плательщика; назначение платежей неизвестно.',
                'incoming',beneficiary_share,observation_count
         FROM payment_connections WHERE beneficiary_id=%s ORDER BY beneficiary_share DESC NULLS LAST LIMIT %s)
        UNION ALL
        (SELECT other.id,'group',0.3,NULL::double precision,'Одна группа компаний по GROUP_ID.',
                'association',NULL::double precision,1
         FROM organizations current JOIN organizations other ON other.group_id=current.group_id
         WHERE current.id=%s AND other.id<>current.id AND current.group_id IS NOT NULL
         ORDER BY (other.profile_data<>'{}') DESC,other.id LIMIT %s)
        UNION ALL
        (SELECT DISTINCT other.organization_id,'shared_person',0.1,NULL::double precision,
                'Есть связь через общее обезличенное физическое лицо; характер связи не указан.',
                'association',NULL::double precision,1
         FROM person_organization_links mine JOIN person_organization_links other
              ON other.synthetic_f=mine.synthetic_f
         WHERE mine.organization_id=%s AND other.organization_id<>mine.organization_id
         ORDER BY other.organization_id LIMIT %s)
    ) SELECT links.*,o.synthetic_u,COALESCE(o.name,o.synthetic_u) AS counterparty_name,
             o.industry,o.region,o.profile_data<>'{}' AS has_profile
      FROM links JOIN organizations o ON o.id=links.related_id
      ORDER BY weight DESC,related_id,kind,direction LIMIT %s""",
        (
            organization_id,
            limit,
            organization_id,
            limit,
            organization_id,
            limit,
            organization_id,
            limit,
            organization_id,
            limit,
            limit * 5,
        ),
    )
    result = []
    seen = set()
    for row in rows:
        identity = (row["related_id"], row["kind"], row["direction"])
        if identity in seen:
            continue
        seen.add(identity)
        row["id"] = f"{row['kind']}:{organization_id}:{row['related_id']}:{row['direction']}"
        row["counterparty_id"] = row.pop("related_id")
        row["relation_type"] = row.pop("kind")
        row["connection_weight"] = min(1, float(row.pop("weight")))
        if row["observations"] > 1:
            row["evidence"] += " Несколько исходных наблюдений: сумма и доля не интерпретируются."
        if row["share"] is not None:
            row["evidence"] += f" Доля наблюдаемых платежей в этом направлении: {row['share']:.1%}."
        result.append(row)
    ranks = {}
    for item in result:
        category = (item["relation_type"], item["direction"])
        item["_rank"] = ranks.get(category, 0)
        ranks[category] = item["_rank"] + 1
    result.sort(key=lambda item: (item["_rank"], -item["connection_weight"], item["counterparty_id"]))
    for item in result:
        item.pop("_rank")
    return result[:limit]


def build_context(db, organization_id, max_depth=3, decay=0.5, max_nodes=32, per_node=5):
    root_links = neighbors(db, organization_id, 20)
    queue = deque([(organization_id, [organization_id], [], 1.0)])
    best = {organization_id: 1.0}
    paths = {}
    truncated = False
    while queue:
        node, visited, edges, weight = queue.popleft()
        if len(edges) >= max_depth:
            continue
        choices = root_links if node == organization_id else neighbors(db, node, per_node + 1)
        if len(choices) > per_node:
            truncated = True
        selected = set()
        for link in choices:
            target = link["counterparty_id"]
            if target in visited or target in selected:
                continue
            selected.add(target)
            if len(selected) > per_node:
                break
            path_weight = weight * link["connection_weight"] * (decay if edges else 1.0)
            if path_weight < 0.005 or path_weight <= best.get(target, 0):
                continue
            if target not in best and len(best) >= max_nodes:
                truncated = True
                continue
            step = {
                "from": node,
                "to": target,
                "kind": link["relation_type"],
                "direction": link["direction"],
                "weight": link["connection_weight"],
                "evidence": link["evidence"],
            }
            best[target] = path_weight
            path = {
                "organization_id": target,
                "label": link["counterparty_name"],
                "industry": link["industry"],
                "has_profile": link["has_profile"],
                "nodes": visited + [target],
                "edges": edges + [step],
                "depth": len(edges) + 1,
                "weight": round(path_weight, 6),
                "dependency_confirmed": all(
                    e["kind"] in ("supplier", "buyer", "partner", "other") for e in edges + [step]
                ),
            }
            paths[target] = path
            queue.append((target, path["nodes"], path["edges"], path_weight))
    return {
        "root_id": organization_id,
        "direct_connections": root_links,
        "paths": sorted(paths.values(), key=lambda p: p["weight"], reverse=True),
        "max_depth": max_depth,
        "decay": decay,
        "max_nodes": max_nodes,
        "truncated": truncated or len(best) >= max_nodes,
        "per_node": per_node,
        "note": dataset_note(),
    }


def assess_context(db, context, shocks, propagator, profile_builder):
    paths = context.get("paths", [])
    ids = [p["organization_id"] for p in paths if p["has_profile"]]
    companies = (
        db.all("SELECT * FROM organizations WHERE id=ANY(%s) AND profile_data<>'{}'", (ids,)) if ids else []
    )
    profiles = {org["id"]: profile_builder(org) for org in companies}
    affected = []
    for path in paths:
        profile = profiles.get(path["organization_id"])
        if not profile:
            continue
        impact = propagator.impact_on_all_companies([profile], shocks)[0]
        signal = abs(impact.total_impact) * path["weight"]
        if signal < 0.005:
            continue
        affected.append(dict(path, signal=round(signal, 6), factor_impacts=impact.factor_impacts))
    affected.sort(key=lambda p: p["signal"], reverse=True)
    return {
        "direct_count": len(context.get("direct_connections", [])),
        "examined_count": len(paths),
        "profiled_count": len(profiles),
        "indirect_signal": affected[0]["signal"] if affected else 0.0,
        "top_paths": affected[:5],
        "max_depth": context.get("max_depth", 3),
        "truncated": context.get("truncated", False),
        "note": dataset_note(),
    }
