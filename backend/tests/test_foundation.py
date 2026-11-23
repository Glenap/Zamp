import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.db import connect, init_db
from backend.main import app
from backend.seed.seed import NORTHWIND_ACCOUNT

BACKEND = Path(__file__).resolve().parents[1]


def test_schema_and_health(tmp_path, monkeypatch):
    path = tmp_path / "health.sqlite3"
    monkeypatch.setenv("VENDORGATE_DB_PATH", str(path))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
    with connect(path) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert tables == {
            "vendors_existing", "submissions", "documents", "runs", "stage_results",
            "messages_outbox", "overrides", "settings",
        }
        assert {row[1] for row in connection.execute("PRAGMA table_info(runs)")} >= {"parent_run_id"}
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_seed_cli_reset_is_repeatable_and_restores_defaults(tmp_path):
    path = tmp_path / "fixtures.sqlite3"
    init_db(path)
    with connect(path) as connection:
        connection.execute("INSERT INTO submissions(id, form_json) VALUES ('keep-me', '{}')")
    args = [sys.executable, str(BACKEND / "seed" / "seed.py"), "--reset", "--output-dir", str(tmp_path / "fixtures")]
    for _ in range(2):
        with connect(path) as connection:
            connection.execute("UPDATE settings SET value_json = '0.10' WHERE key = 'name_match_threshold'")
        subprocess.run(args, check=True, env={**os.environ, "VENDORGATE_DB_PATH": str(path)})
        with connect(path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM vendors_existing").fetchone()[0] == 20
            row = connection.execute(
                "SELECT bank_account, status FROM vendors_existing WHERE legal_name = ?",
                ("Northwind Industrial Supplies LLC",),
            ).fetchone()
            assert tuple(row) == (NORTHWIND_ACCOUNT, "APPROVED")
            row = connection.execute("SELECT value_json FROM settings WHERE key = 'name_match_threshold'").fetchone()
            assert json.loads(row[0]) == 0.85
            assert connection.execute("SELECT id FROM submissions").fetchone()[0] == "keep-me"
