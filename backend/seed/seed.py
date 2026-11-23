"""Load the synthetic existing vendor registry and restore default policy on reset."""

import argparse
import json
import sys
from pathlib import Path

# Support both the documented direct command and python -m backend.seed.seed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db import SETTINGS_PATH, connect, database_path, init_db

NORTHWIND_ACCOUNT = "9000000101"


def seed(path=None, *, reset=False):
    init_db(path)
    records = json.loads(Path(__file__).with_name("vendors.json").read_text(encoding="utf-8"))
    defaults = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
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
               (id, legal_name, trade_name, country, tax_id, bank_account, iban, status, email_domain)
               VALUES (:id, :legal_name, :trade_name, :country, :tax_id, :bank_account, :iban, :status, :email_domain)
               ON CONFLICT(id) DO NOTHING""",
            records,
        )
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace the vendor registry and restore policy defaults.")
    parser.add_argument("--db", help="Path to an alternate SQLite database.")
    args = parser.parse_args()
    count = seed(args.db, reset=args.reset)
    print(f"Loaded {count} vendor fixtures into {database_path(args.db)}")


if __name__ == "__main__":
    main()
