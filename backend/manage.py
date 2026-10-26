"""Local-only database management; no network scraping or implicit external AI calls."""

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from backend.app.analytics import ingest_articles
from backend.app.config import ROOT, get_settings
from backend.app.db import Database
from backend.app.models import Article
from backend.news_collector import collect_feeds


def migrate(url, baseline=False):
    with psycopg.connect(url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(726381)")
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations
            (name TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        existing = conn.execute("SELECT to_regclass('organizations')").fetchone()[0]
        migrations = sorted((ROOT / "backend/internal/migrations").glob("[0-9]*.sql"))
        for path in migrations:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            applied = conn.execute(
                "SELECT checksum FROM schema_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if applied:
                if applied[0] != digest:
                    raise RuntimeError("Applied migration was changed: " + path.name)
                continue
            if path.name.startswith("001") and existing:
                if not baseline:
                    raise RuntimeError(
                        "Existing schema without migration history; inspect it before --baseline-001"
                    )
                # A deliberate baseline requires the latest columns from the previous schema.
                for table, column in [
                    ("organizations", "profile_data"),
                    ("materials", "material_type"),
                    ("analysis_runs", "company_context"),
                    ("insight_evidence", "quote"),
                ]:
                    if not conn.execute(
                        """SELECT 1 FROM information_schema.columns
                        WHERE table_schema=current_schema() AND table_name=%s AND column_name=%s""",
                        (table, column),
                    ).fetchone():
                        raise RuntimeError("Existing schema is incompatible with migration 001")
            else:
                sql = re.sub(r"^\s*BEGIN;", "", path.read_text(encoding="utf-8"), count=1, flags=re.I)
                sql = re.sub(r"COMMIT;\s*$", "", sql, count=1, flags=re.I)
                conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations(name,checksum) VALUES(%s,%s)", (path.name, digest))
            print("Applied", path.name)


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        yield from csv.DictReader(stream, dialect=csv.Sniffer().sniff(sample, delimiters=";,\t"))


def import_companies(db, path):
    grouped = defaultdict(list)
    for row in csv_rows(path):
        grouped[row["SYNTHETIC_U"]].append(row)
    conflicts = [
        key for key, rows in grouped.items() if len({json.dumps(r, sort_keys=True) for r in rows}) > 1
    ]
    valid = [(key, rows[0]) for key, rows in grouped.items() if key not in conflicts]
    flags = {
        "has_loans": "CL_PRODUCT_LOA_MARK",
        "has_leasing": "CL_PRODUCT_LEA_MARK",
        "has_deposits": "CL_PRODUCT_DEP_MARK",
        "has_guarantees": "CL_PRODUCT_GAR_MARK",
        "has_factoring": "FACTORING_MARK",
        "has_foreign_trade": "FTS_FLAG",
    }
    with db.transaction() as conn:
        conn.execute("CREATE TEMP TABLE company_import(synthetic_u TEXT,raw JSONB) ON COMMIT DROP")
        with conn.cursor().copy("COPY company_import FROM STDIN") as copy:
            for key, row in valid:
                copy.write_row((key, json.dumps(row, ensure_ascii=False)))
        expressions = []
        for col in flags.values():
            expressions.append(
                f"CASE raw->>'{col}' WHEN '1.0' THEN true WHEN '1' THEN true WHEN '0.0' THEN false WHEN '0' THEN false END"
            )
        conn.execute(
            """INSERT INTO organizations(synthetic_u,industry,okved_code,region,city,group_id,
            annual_revenue,profile_data,foreign_trade_countries,"""
            + ",".join(flags)
            + """)
            SELECT synthetic_u,NULLIF(raw->>'MAINOKVED_NAME',''),NULLIF(raw->>'MAINOKVED_CODE',''),
            NULLIF(raw->>'REGION',''),NULLIF(raw->>'CITY',''),NULLIF(raw->>'GROUP_ID',''),
            NULLIF(raw->>'REVENUE_COMPANY','')::numeric,raw,
            CASE WHEN NULLIF(raw->>'FTS_COUNTRY_NAME','') IS NULL THEN ARRAY[]::text[]
            ELSE regexp_split_to_array(raw->>'FTS_COUNTRY_NAME',',[[:space:]]*') END,"""
            + ",".join(expressions)
            + """
            FROM company_import ON CONFLICT(synthetic_u) DO UPDATE SET
            industry=EXCLUDED.industry,okved_code=EXCLUDED.okved_code,region=EXCLUDED.region,
            city=EXCLUDED.city,group_id=EXCLUDED.group_id,annual_revenue=EXCLUDED.annual_revenue,
            profile_data=EXCLUDED.profile_data,foreign_trade_countries=EXCLUDED.foreign_trade_countries,
            updated_at=NOW(),"""
            + ",".join(f"{k}=EXCLUDED.{k}" for k in flags)
        )
        # Conflicting records remain unprofiled, not silently overwritten with arbitrary data.
        for key in conflicts:
            conn.execute("INSERT INTO organizations(synthetic_u) VALUES(%s) ON CONFLICT DO NOTHING", (key,))
    report = {"profiles_loaded": len(valid), "conflicting_ids": conflicts}
    report_path = ROOT / "runtime/import_report.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return {"profiles_loaded": len(valid), "conflicting_profile_count": len(conflicts)}


def import_links(db, folder):
    path = folder / "df_Fid_Uid_link_hack.csv"
    with db.transaction() as conn:
        conn.execute("CREATE TEMP TABLE link_import(f TEXT,u TEXT,city TEXT,region TEXT) ON COMMIT DROP")
        with conn.cursor().copy("COPY link_import FROM STDIN") as copy:
            for row in csv_rows(path):
                copy.write_row(
                    (row["SYNTHETIC_F"], row["SYNTHETIC_U"], row["CITY_NAME"] or None, row["RC_NAME"] or None)
                )
        conn.execute(
            "INSERT INTO organizations(synthetic_u) SELECT DISTINCT u FROM link_import ON CONFLICT DO NOTHING"
        )
        conn.execute("""INSERT INTO person_organization_links(synthetic_f,organization_id,city,region)
            SELECT l.f,o.id,l.city,l.region FROM link_import l JOIN organizations o ON o.synthetic_u=l.u
            ON CONFLICT(synthetic_f,organization_id) DO UPDATE SET city=EXCLUDED.city,region=EXCLUDED.region""")


def import_payments(db, folder):
    path = folder / "df_Uid_payment_hack.csv"
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    ref = path.name + ":sha256:" + digest
    with db.transaction() as conn:
        conn.execute(
            "CREATE TEMP TABLE flow_import(payer TEXT,beneficiary TEXT,amount NUMERIC,cnt BIGINT,row_no BIGINT) ON COMMIT DROP"
        )
        with conn.cursor().copy("COPY flow_import FROM STDIN") as copy:
            for number, row in enumerate(csv_rows(path), 1):
                copy.write_row((row["PAYER"], row["BENEFICIARY"], row["PAY_AMT"], row["PAY_CNT"], number))
        conn.execute("""INSERT INTO organizations(synthetic_u)
            SELECT payer FROM flow_import UNION SELECT beneficiary FROM flow_import ON CONFLICT DO NOTHING""")
        # Versioned import replaces the previous snapshot atomically, not in addition to it.
        conn.execute("DELETE FROM payment_flows WHERE source_ref LIKE %s", (path.name + ":sha256:%",))
        conn.execute(
            """INSERT INTO payment_flows(payer_id,beneficiary_id,amount,payment_count,source_ref,source_row)
            SELECT p.id,b.id,f.amount,f.cnt,%s,f.row_no FROM flow_import f
            JOIN organizations p ON p.synthetic_u=f.payer JOIN organizations b ON b.synthetic_u=f.beneficiary""",
            (ref,),
        )


BANK_METADATA = {
    "ALFA-7M26.md": ("Макростатистика 7М26", "2026-09-07"),
    "ALFA-Macro_Insights-Policy_Rate_11Sep.md": ("Ключевая ставка ЦБ РФ: ставка без изменения", "2026-09-11"),
    "ALFA-consumption.md": ("Потребление на пике", "2026-08-05"),
    "ALFA-macro_stat1H26.md": ("Макростатистика 1П26", "2026-07-31"),
    "ALFA_Russian_Steels_1Q21_Preview_Update_15Apr2021.md": ("Российская сталь: 1К21", "2021-04-15"),
    "Bond_Brief_14092026.md": ("Бонд Бриф: итоги недели", "2026-09-14"),
    # Conflicting OCR/file date: deliberately do not guess.
    "FI_Strategy_3Q26_22072026.md": ("Тактический взгляд на 3-й квартал 2026 года", None),
    "Gold_digest_August26.md": ("Обзор рынка золота: август 2026", None),
    "Inflation_tracker_02.md": ("Инфляция 25–31 августа: основные выводы", "2026-09-02"),
}


def import_bank(db, folder):
    count = 0
    for path in sorted(folder.glob("*.md")):
        title, date = BANK_METADATA.get(path.name, (path.stem, None))
        body = path.read_text(encoding="utf-8")
        ref = "ml/data/alfa-bank_materials_for_large_business/" + path.name
        published = datetime.fromisoformat(date).replace(tzinfo=timezone.utc) if date else None
        with db.transaction() as conn:
            source = conn.execute("""INSERT INTO sources(name,source_type) VALUES('Альфа-Банк: материалы кейса','bank_analytics')
                ON CONFLICT(name,source_type) DO UPDATE SET name=EXCLUDED.name RETURNING id""").fetchone()
            conn.execute(
                """INSERT INTO materials(source_id,material_type,source_ref,title,body,summary,published_at,processing_status,analysis_data)
                VALUES(%s,'bank_analytics',%s,%s,%s,%s,%s,'ready','{"analysis_eligible": true, "origin": "organizers"}')
                ON CONFLICT(source_id,source_ref) DO UPDATE SET title=EXCLUDED.title,body=EXCLUDED.body,
                summary=EXCLUDED.summary,published_at=EXCLUDED.published_at,analysis_data=EXCLUDED.analysis_data""",
                (source["id"], ref, title, body, re.sub(r"\s+", " ", body[:1000])[:500], published),
            )
        count += 1
    return {"bank_materials": count}


def seed_demo(db):
    result = import_companies(db, ROOT / "data/samples/companies_small.csv")
    news = [
        (
            "Демонстрация: снижение инфляции",
            "Демонстрационный сценарий. Инфляция снизилась, но давление на издержки сохраняется. Проверьте сроки пересмотра цен в договорах.",
            [{"factor": "inflation", "direction": -1, "magnitude": 0.3}],
        ),
        (
            "Демонстрация: рост стоимости перевозок",
            "Демонстрационный сценарий. Стоимость международных перевозок выросла. Компаниям с импортными поставками стоит проверить условия доставки.",
            [{"factor": "logistics", "direction": 1, "magnitude": 0.4}],
        ),
        (
            "Демонстрация: изменение стоимости заимствований",
            "Демонстрационный сценарий. Стоимость заимствований выросла. Изменение условий новых кредитов может повлиять на инвестиционные планы.",
            [{"factor": "key_rate", "direction": 1, "magnitude": 0.4}],
        ),
    ]
    articles = [
        Article.model_validate(
            {
                "title": title,
                "body": body,
                "source_name": "Синтетические сценарии команды",
                "source_url": f"https://demo.invalid/scenarios/{i}",
                "published_at": "2026-09-15T12:00:00+03:00",
                "shocks": shocks,
            }
        )
        for i, (title, body, shocks) in enumerate(news, 1)
    ]
    result.update(ingest_articles(db, articles, demo=True))
    bank_folder = ROOT / "ml/data/alfa-bank_materials_for_large_business"
    if bank_folder.exists():
        result.update(import_bank(db, bank_folder))
    return result


def quality_report(db, since):
    jobs = db.all(
        """SELECT status, count(*) AS count,
                  coalesce(sum(CASE WHEN summary->>'total' ~ '^[0-9]+$' THEN (summary->>'total')::int ELSE 0 END),0) AS materials,
                  coalesce(sum(CASE WHEN summary->>'created' ~ '^[0-9]+$' THEN (summary->>'created')::int ELSE 0 END),0) AS created,
                  coalesce(sum(CASE WHEN summary->>'skipped' ~ '^[0-9]+$' THEN (summary->>'skipped')::int ELSE 0 END),0) AS skipped,
                  coalesce(sum(CASE WHEN summary->>'failed' ~ '^[0-9]+$' THEN (summary->>'failed')::int ELSE 0 END),0) AS failed_materials
           FROM analysis_jobs WHERE created_at >= %s GROUP BY status ORDER BY status""",
        (since,),
    )
    insights = db.one(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE bank_view IS NOT NULL) AS with_bank_view,
                  count(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM insight_evidence e WHERE e.insight_id=insights.id
                  )) AS with_citations
           FROM insights WHERE created_at >= %s""",
        (since,),
    )
    verification = db.one(
        """SELECT count(*) AS attempts,
                  count(*) FILTER (WHERE coalesce(
                    step#>>'{result,status}',step#>>'{result,verification,status}')='passed') AS passed,
                  count(*) FILTER (WHERE coalesce(
                    step#>>'{result,status}',step#>>'{result,verification,status}')='warning') AS warning,
                  count(*) FILTER (WHERE coalesce(
                    step#>>'{result,status}',step#>>'{result,verification,status}')='failed') AS failed
           FROM analysis_runs r
           CROSS JOIN LATERAL jsonb_array_elements(r.steps) AS item(step)
           WHERE r.started_at >= %s AND step->>'tool' IN ('insight.verify','insight.repair')""",
        (since,),
    )
    feedback = db.all(
        """SELECT rating,count(*) AS count FROM insight_feedback
           WHERE updated_at >= %s GROUP BY rating ORDER BY rating""",
        (since,),
    )
    modes = db.all(
        """SELECT coalesce(payload->>'generation_mode','unknown') AS mode,count(*) AS count
           FROM insights WHERE created_at >= %s GROUP BY mode ORDER BY mode""",
        (since,),
    )
    total_insights = insights["total"]
    return {
        "since": since.isoformat(),
        "job_status": {row["status"]: row["count"] for row in jobs},
        "materials": {
            field: sum(row[key] for row in jobs)
            for field, key in (
                ("submitted", "materials"),
                ("created", "created"),
                ("skipped", "skipped"),
                ("failed", "failed_materials"),
            )
        },
        "insights": {
            "total": total_insights,
            "with_bank_view": insights["with_bank_view"],
            "with_citations": insights["with_citations"],
            "bank_view_rate": round(insights["with_bank_view"] / total_insights, 4)
            if total_insights
            else None,
            "citation_coverage": round(insights["with_citations"] / total_insights, 4)
            if total_insights
            else None,
        },
        "verification": {
            "attempts": verification["attempts"],
            "passed": verification["passed"],
            "warning": verification["warning"],
            "failed": verification["failed"],
            "pass_rate": round(verification["passed"] / verification["attempts"], 4)
            if verification["attempts"]
            else None,
        },
        "generation_modes": {row["mode"]: row["count"] for row in modes},
        "feedback": {row["rating"]: row["count"] for row in feedback},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "migrate", "seed-demo", "import-data", "import-bank", "collect-news", "quality-report", "export-openapi"
        ],
    )
    parser.add_argument("--baseline-001", action="store_true")
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--with-payments", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "export-openapi":
        from backend.app.main import app

        (ROOT / "contracts/openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
        return
    if args.command == "migrate":
        migrate(settings.database_url.get_secret_value(), args.baseline_001)
        return
    if args.days < 1 or args.days > 3650:
        parser.error("--days must be between 1 and 3650")
    db = Database(settings.database_url.get_secret_value())
    db.open()
    try:
        if args.command == "quality-report":
            result = quality_report(db, datetime.now(timezone.utc) - timedelta(days=args.days))
        elif args.command == "collect-news":
            articles, failures = collect_feeds(settings.news_feed_urls)
            result = ingest_articles(db, articles) if articles else {"inserted_ids": [], "duplicates": 0}
            result.update({"fetched": len(articles), "feed_failures": failures})
        elif args.command == "seed-demo":
            result = seed_demo(db)
        elif args.command == "import-bank":
            result = import_bank(db, args.folder or ROOT / "ml/data/alfa-bank_materials_for_large_business")
        else:
            folder = args.folder or ROOT / "ml/data/classification_classes"
            result = import_companies(db, folder / "df_Uid_data_hack.csv")
            import_links(db, folder)
            if args.with_payments:
                import_payments(db, folder)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
