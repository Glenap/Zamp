"""SQLite persistence only; no decision or stage logic belongs here."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BACKEND_DIR / "config" / "settings.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors_existing (
    id INTEGER PRIMARY KEY,
    legal_name TEXT NOT NULL,
    trade_name TEXT,
    country TEXT NOT NULL,
    tax_id TEXT,
    bank_account TEXT,
    iban TEXT,
    status TEXT NOT NULL,
    email_domain TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    parent_submission_id TEXT REFERENCES submissions(id),
    form_json TEXT NOT NULL CHECK(json_valid(form_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    doc_type_detected TEXT,
    UNIQUE(submission_id, filename)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    parent_run_id INTEGER REFERENCES runs(id),
    status TEXT NOT NULL,
    risk_score REAL CHECK(risk_score BETWEEN 0 AND 100),
    decision_json TEXT CHECK(decision_json IS NULL OR json_valid(decision_json)),
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS stage_results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    stage_no INTEGER NOT NULL CHECK(stage_no BETWEEN 1 AND 9),
    stage_name TEXT NOT NULL,
    stage_type TEXT NOT NULL CHECK(stage_type IN ('AI','RULE')),
    status TEXT NOT NULL,
    input_json TEXT CHECK(input_json IS NULL OR json_valid(input_json)),
    output_json TEXT CHECK(output_json IS NULL OR json_valid(output_json)),
    started_at TEXT,
    duration_ms REAL CHECK(duration_ms >= 0),
    rule_version TEXT
);
CREATE TABLE IF NOT EXISTS messages_outbox (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    audience TEXT NOT NULL CHECK(audience IN ('vendor','internal')),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS overrides (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK(json_valid(value_json))
);
CREATE INDEX IF NOT EXISTS idx_documents_submission ON documents(submission_id);
CREATE INDEX IF NOT EXISTS idx_runs_submission ON runs(submission_id);
CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_stages_run ON stage_results(run_id);
CREATE INDEX IF NOT EXISTS idx_messages_run ON messages_outbox(run_id);
CREATE INDEX IF NOT EXISTS idx_overrides_run ON overrides(run_id);
CREATE INDEX IF NOT EXISTS idx_vendor_bank ON vendors_existing(bank_account);
CREATE INDEX IF NOT EXISTS idx_vendor_tax ON vendors_existing(tax_id);
"""


def database_path(path=None):
    """Resolve relative database paths against backend, independent of cwd."""
    selected = Path(path or os.getenv("VENDORGATE_DB_PATH", "data/vendorgate.sqlite3"))
    return selected if selected.is_absolute() else BACKEND_DIR / selected


@contextmanager
def connect(path=None):
    target = database_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db(path=None):
    with connect(path) as connection:
        # Upgrade an early Task 1 database before indexes or queries use the link.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        if columns and "parent_run_id" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN parent_run_id INTEGER REFERENCES runs(id)")
        connection.executescript(SCHEMA)
        # Preserve operator settings on normal app startup. Reset explicitly reloads defaults.
        defaults = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        connection.executemany(
            "INSERT OR IGNORE INTO settings(key, value_json) VALUES (?, ?)",
            [(key, json.dumps(value)) for key, value in defaults.items()],
        )
