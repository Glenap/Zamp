"""An existing Task 1 database must survive the parent-run schema upgrade."""
from backend.db import connect, init_db


def test_early_database_gains_parent_run_link_without_losing_rows(tmp_path):
    database = tmp_path / "old.sqlite3"
    with connect(database) as connection:
        connection.executescript("""
            CREATE TABLE runs(id INTEGER PRIMARY KEY, submission_id TEXT,
              status TEXT, risk_score REAL, decision_json TEXT, started_at TEXT, finished_at TEXT);
            INSERT INTO runs(id,submission_id,status) VALUES (42,'existing','completed');
        """)
    init_db(database)
    with connect(database) as connection:
        assert "parent_run_id" in {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        assert connection.execute("SELECT status,parent_run_id FROM runs WHERE id=42").fetchone()[0] == "completed"
