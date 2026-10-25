"""Durable PostgreSQL job queue, independent from the HTTP process."""

import logging
import threading
import time
import uuid

from psycopg.types.json import Jsonb

from backend.app.analytics import AnalysisFailure, analyze_material, make_profile
from backend.app.config import get_settings
from backend.app.connections import build_context
from backend.app.data_mode import material_filter
from backend.app.db import Database, WorkerLeaseLost
from backend.app.llm import LLM

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.llm = LLM(settings)
        self.owner = uuid.uuid4()

    def claim(self):
        with self.db.transaction() as conn:
            expired = conn.execute(
                """UPDATE analysis_jobs SET status='failed', error_code='worker_lease_expired',
                finished_at=NOW() WHERE status='running'
                AND heartbeat_at < NOW() - make_interval(secs => %s) RETURNING id""",
                (self.settings.job_lease_seconds,),
            ).fetchall()
            for job in expired:
                conn.execute(
                    """UPDATE analysis_runs SET status='failed',
                    error_message='worker_lease_expired',finished_at=NOW()
                    WHERE job_id=%s AND status='running'""",
                    (job["id"],),
                )
            row = conn.execute("""SELECT * FROM analysis_jobs WHERE status='pending'
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
            if row:
                conn.execute(
                    """UPDATE analysis_jobs SET status='running',lease_owner=%s,heartbeat_at=NOW()
                    WHERE id=%s""",
                    (self.owner, row["id"]),
                )
                row["status"] = "running"
            return row

    def heartbeat(self, job_id, stop):
        while not stop.wait(10):
            try:
                with self.db.transaction() as conn:
                    conn.execute(
                        """UPDATE analysis_jobs SET heartbeat_at=NOW()
                        WHERE id=%s AND status='running' AND lease_owner=%s""",
                        (job_id, self.owner),
                    )
            except Exception:
                logger.warning("job_heartbeat_failed job_id=%s", job_id)

    def ensure_owner(self, conn, job):
        if not conn.execute(
            "SELECT id FROM analysis_jobs WHERE id=%s AND status='running' AND lease_owner=%s FOR UPDATE",
            (job["id"], self.owner),
        ).fetchone():
            raise WorkerLeaseLost("worker_lease_lost")

    def save_progress(self, conn, job, summary):
        self.ensure_owner(conn, job)
        conn.execute("UPDATE analysis_jobs SET summary=%s WHERE id=%s", (Jsonb(summary), job["id"]))

    def run_once(self):
        job = self.claim()
        if not job:
            return False
        stop = threading.Event()
        heartbeat = threading.Thread(target=self.heartbeat, args=(job["id"], stop), daemon=True)
        heartbeat.start()
        run_id = None
        summary = None
        try:
            org = self.db.one("SELECT * FROM organizations WHERE id=%s", (job["organization_id"],))
            profile = make_profile(org)
            params = job["parameters"]
            connection_context = build_context(
                self.db, org["id"], max_depth=params["max_depth"], decay=params["decay"]
            )
            material_ids = params.get("material_ids")
            sql = "SELECT * FROM materials WHERE " + material_filter(self.settings.data_mode)
            args = []
            if material_ids:
                sql += " AND id=ANY(%s)"
                args.append(material_ids)
            sql += " ORDER BY published_at DESC NULLS LAST,id DESC LIMIT %s"
            args.append(params["max_events"])
            materials = self.db.all(sql, args)
            summary = {
                "total": len(materials),
                "processed": 0,
                "created": 0,
                "skipped": 0,
                "failed": 0,
                "retrying": False,
                "materials": [
                    {"material_id": m["id"], "status": "pending", "error_code": None} for m in materials
                ],
            }
            with self.db.transaction() as conn:
                self.save_progress(conn, job, summary)
            for index, material in enumerate(materials):
                steps = []
                outcome = summary["materials"][index]
                outcome["status"] = "running"
                summary["retrying"] = False

                def on_attempt(attempt):
                    summary["retrying"] = attempt == 2
                    if attempt == 2:
                        outcome["retries"] = outcome.get("retries", 0) + 1
                    with self.db.transaction() as conn:
                        self.save_progress(conn, job, summary)

                self.llm.on_attempt = on_attempt
                with self.db.transaction() as conn:
                    self.save_progress(conn, job, summary)
                    run_id = conn.execute(
                        """INSERT INTO analysis_runs
                        (organization_id,target_role,status,model_name,pipeline_version,company_context,job_id)
                        VALUES(%s,%s,'running',%s,'evidence-v2',%s,%s) RETURNING id""",
                        (
                            org["id"],
                            job["target_role"],
                            self.settings.llm_model or "offline-rules",
                            Jsonb(
                                {
                                    "profile": profile,
                                    "material_id": material["id"],
                                    "connections": connection_context,
                                }
                            ),
                            job["id"],
                        ),
                    ).fetchone()["id"]
                try:
                    payload, steps = analyze_material(
                        self.db,
                        org,
                        profile,
                        {
                            "id": job["user_id"],
                            "role": job["target_role"],
                            "connection_context": connection_context,
                        },
                        material,
                        params,
                        self.llm,
                        str(run_id),
                    )
                except AnalysisFailure as exc:
                    outcome.update(status="failed", error_code=exc.code)
                    summary["failed"] += 1
                    summary["processed"] += 1
                    summary["retrying"] = False
                    with self.db.transaction() as conn:
                        self.ensure_owner(conn, job)
                        conn.execute(
                            "UPDATE analysis_runs SET status='failed',error_message=%s,steps=%s,finished_at=NOW() WHERE id=%s",
                            (
                                exc.code,
                                Jsonb(exc.steps + [{"tool": "error", "result": {"code": exc.code}}]),
                                run_id,
                            ),
                        )
                        self.save_progress(conn, job, summary)
                    logger.warning(
                        "material_failed job_id=%s material_id=%s code=%s",
                        job["id"],
                        material["id"],
                        exc.code,
                    )
                    run_id = None
                    continue
                with self.db.transaction() as conn:
                    self.ensure_owner(conn, job)
                    if payload:
                        channels = payload["channels"]
                        interpretation = channels["ai_conclusion"][0]["text"]
                        insight = conn.execute(
                            """INSERT INTO insights
                            (run_id,primary_material_id,title,facts,bank_view,interpretation,relevance_reason,
                             risks,opportunities,suggested_actions,relevance_score,confidence,payload)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (
                                run_id,
                                material["id"],
                                payload["headline"],
                                channels["fact"][0]["text"],
                                "\n\n".join(b["text"] for b in channels["bank_analytics"]) or None,
                                interpretation,
                                payload["relevance_reason"],
                                Jsonb(payload["risks"]),
                                Jsonb(payload["opportunities"]),
                                Jsonb(payload["actions"]),
                                payload["relevance_score"],
                                payload["confidence"],
                                Jsonb(payload),
                            ),
                        ).fetchone()
                        conn.execute(
                            """INSERT INTO insight_evidence
                            (insight_id,material_id,section,claim,quote) VALUES(%s,%s,'facts',%s,%s)""",
                            (insight["id"], material["id"], material["title"], channels["fact"][0]["text"]),
                        )
                        for b in payload["bank_sources"]:
                            conn.execute(
                                """INSERT INTO insight_evidence
                                (insight_id,material_id,section,claim,quote) VALUES(%s,%s,'bank_view',%s,%s)""",
                                (insight["id"], b["material_id"], b["quote"], b["quote"]),
                            )
                        for other in payload.get("evidence", [])[1:]:
                            conn.execute(
                                """INSERT INTO insight_evidence
                                (insight_id,material_id,section,claim,quote)
                                VALUES(%s,%s,'facts',%s,%s)""",
                                (
                                    insight["id"], other["material_id"],
                                    "Дополнительный источник: " + other["kind"], other["quote"],
                                ),
                            )
                        summary["created"] += 1
                        outcome["status"] = "completed"
                    else:
                        summary["skipped"] += 1
                        outcome["status"] = "skipped"
                    conn.execute(
                        """UPDATE analysis_runs SET status='completed',steps=%s,finished_at=NOW()
                        WHERE id=%s""",
                        (Jsonb(steps), run_id),
                    )
                    summary["processed"] += 1
                    summary["retrying"] = False
                    self.save_progress(conn, job, summary)
                run_id = None
            all_failed = bool(materials) and summary["failed"] == len(materials)
            with self.db.transaction() as conn:
                self.ensure_owner(conn, job)
                conn.execute(
                    """UPDATE analysis_jobs SET status=%s,error_code=%s,summary=%s,finished_at=NOW()
                    WHERE id=%s AND status='running' AND lease_owner=%s""",
                    (
                        "failed" if all_failed else "completed",
                        summary["materials"][0]["error_code"] if all_failed else None,
                        Jsonb(summary),
                        job["id"],
                        self.owner,
                    ),
                )
        except WorkerLeaseLost:
            logger.warning("worker_lease_lost job_id=%s", job["id"])
        except Exception as exc:
            error_code = getattr(exc, "code", "analysis_failed")
            logger.error("analysis_failed job_id=%s exception_type=%s", job["id"], type(exc).__name__)
            with self.db.transaction() as conn:
                self.ensure_owner(conn, job)
                if run_id:
                    conn.execute(
                        """UPDATE analysis_runs SET status='failed',error_message=%s,
                        finished_at=NOW(),steps=%s WHERE id=%s AND status='running'""",
                        (
                            error_code,
                            Jsonb(
                                getattr(exc, "steps", [])
                                + [{"tool": "error", "result": {"code": error_code}}]
                            ),
                            run_id,
                        ),
                    )
                conn.execute(
                    """UPDATE analysis_jobs SET status='failed',error_code=%s,
                    finished_at=NOW() WHERE id=%s AND status='running' AND lease_owner=%s""",
                    (error_code, job["id"], self.owner),
                )
        finally:
            self.llm.on_attempt = None
            stop.set()
            heartbeat.join(timeout=2)
        return True


def main():
    settings = get_settings()
    db = Database(settings.database_url.get_secret_value())
    db.open()
    try:
        worker = Worker(db, settings)
        while True:
            if not worker.run_once():
                time.sleep(settings.worker_poll_seconds)
    finally:
        db.close()


if __name__ == "__main__":
    main()
