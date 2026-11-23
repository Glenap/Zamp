"""Generate synthetic PDFs and restore vendor registry/settings, preserving reviews."""

import argparse
from datetime import date, datetime, timezone
import json
import sys
from pathlib import Path

# Support both the documented direct command and python -m backend.seed.seed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db import SETTINGS_PATH, connect, database_path, init_db
from backend.seed.documents import generate_documents
from backend.seed.fixtures import NORTHWIND_ACCOUNT, existing_vendors, scenarios


def seed(path=None, *, reset=False, output_dir=None, as_of=None):
    destination = Path(output_dir) if output_dir else Path(__file__).resolve().parent
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "scenarios.json"
    defaults = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    reference = as_of or datetime.now(timezone.utc).date()
    # Reuse dated fixtures on normal startup, keeping documents and forms aligned.
    if manifest_path.exists() and not reset and as_of is None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reference = date.fromisoformat(manifest["reference_date"])
    else:
        manifest = scenarios(reference, defaults["sanctions_list"][0])
    document_count = generate_documents(manifest, destination / "docs")
    init_db(path)
    records = existing_vendors()
    with connect(path) as connection:
        if reset:
            connection.execute("DELETE FROM vendors_existing")
            connection.execute("DELETE FROM settings")
            connection.executemany(
                "INSERT INTO settings(key, value_json) VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in defaults.items()],
            )
        connection.executemany(
            """INSERT INTO vendors_existing
               (id, legal_name, trade_name, country, tax_id, bank_account, iban, status, email_domain, created_at)
               VALUES (:id, :legal_name, :trade_name, :country, :tax_id, :bank_account, :iban, :status, :email_domain, :created_at)
               ON CONFLICT(id) DO NOTHING""",
            records,
        )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (destination / "vendors.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return {"database": str(database_path(path).resolve()), "vendors": len(records),
            "scenarios": len(manifest["scenarios"]), "unique_documents": document_count,
            "reference_date": reference.isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace the vendor registry and restore policy defaults.")
    parser.add_argument("--db", help="Path to an alternate SQLite database.")
    parser.add_argument("--output-dir", type=Path, help="Fixture output folder; default backend/seed")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Reference date YYYY-MM-DD; default UTC today")
    args = parser.parse_args()
    print(json.dumps(seed(args.db, reset=args.reset, output_dir=args.output_dir, as_of=args.as_of), indent=2))


if __name__ == "__main__":
    main()
