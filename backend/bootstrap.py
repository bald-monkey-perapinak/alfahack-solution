"""Import organizer files from the configured data directory."""

import hashlib
import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.connections import rebuild_payment_connections
from backend.app.db import Database
from backend.manage import import_bank, import_companies, import_links, import_payments, seed_demo


def bootstrap(db, folder: Path, mode="organizers"):
    if mode == "demo":
        return seed_demo(db)
    companies = folder / "classification_classes"
    bank = folder / "alfa-bank_materials_for_large_business"
    required = [
        companies / name
        for name in ("df_Uid_data_hack.csv", "df_Fid_Uid_link_hack.csv", "df_Uid_payment_hack.csv")
    ]
    required += sorted(bank.glob("*.md"))
    if len(required) < 4 or any(not p.is_file() for p in required):
        raise RuntimeError(
            "Organizer files missing. Put the provided CSV/Markdown files in ml/data; demo fallback is disabled."
        )
    fingerprint = hashlib.sha256()
    for path in required:
        fingerprint.update(path.name.encode())
        with path.open("rb") as stream:
            fingerprint.update(hashlib.file_digest(stream, "sha256").digest())
    digest = fingerprint.hexdigest()
    with db.transaction() as lock:
        lock.execute("SELECT pg_advisory_xact_lock(726382)")
        existing = lock.execute(
            "SELECT content_hash,statistics FROM dataset_imports WHERE dataset_name='organizers'"
        ).fetchone()
        if existing and existing["content_hash"] == digest:
            return dict(existing["statistics"], unchanged=True)
        statistics = import_companies(db, companies / "df_Uid_data_hack.csv")
        import_links(db, companies)
        statistics.update(import_payments(db, companies))
        statistics.update(import_bank(db, bank))
        statistics["payment_connections"] = rebuild_payment_connections(db)
        statistics["payment_records"] = db.one("SELECT count(*) AS n FROM payment_flows")["n"]
        statistics["person_links"] = db.one("SELECT count(*) AS n FROM person_organization_links")["n"]
        from psycopg.types.json import Jsonb

        lock.execute(
            """INSERT INTO dataset_imports(dataset_name,content_hash,statistics)
            VALUES('organizers',%s,%s) ON CONFLICT(dataset_name) DO UPDATE SET
            content_hash=EXCLUDED.content_hash,statistics=EXCLUDED.statistics,imported_at=NOW()""",
            (digest, Jsonb(statistics)),
        )
    return statistics


def main():
    settings = get_settings()
    db = Database(settings.database_url.get_secret_value())
    db.open()
    try:
        result = bootstrap(db, Path(settings.organizer_data_dir), settings.data_mode)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
