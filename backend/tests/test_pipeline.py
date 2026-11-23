"""Run real storage/evidence through all nine stages using explicit offline extraction."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from backend.db import connect
from backend import llm
from backend.pipeline import execute_run
from backend.seed.seed import seed
from backend.stages import s8_communication


@pytest.fixture
def fixtures(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    database = tmp_path / "review.sqlite3"
    seed(database, reset=True, output_dir=tmp_path, as_of=datetime.now(timezone.utc).date())
    manifest = json.loads((tmp_path / "scenarios.json").read_text())
    return database, tmp_path, manifest["scenarios"]


def load_run(fixtures, index=0, form_updates=None):
    database, destination, scenarios = fixtures
    scenario = scenarios[index]
    form = {**scenario["form"], **(form_updates or {})}
    with connect(database) as connection:
        connection.execute("INSERT INTO submissions(id,form_json) VALUES (?,?)", (scenario["id"], json.dumps(form)))
        for filename in scenario["documents"]:
            connection.execute("INSERT INTO documents(submission_id,filename,path) VALUES (?,?,?)",
                               (scenario["id"], filename, str(destination / "docs" / filename)))
        run_id = connection.execute("INSERT INTO runs(submission_id,status) VALUES (?,'queued')", (scenario["id"],)).lastrowid
    return run_id


@pytest.mark.parametrize("index,expected", [(0, "APPROVED"), (1, "PENDING"), (2, "REJECTED"), (3, "PENDING"), (4, "APPROVED"), (5, "REJECTED")])
def test_scenarios_end_to_end(fixtures, index, expected):
    database, _, _ = fixtures
    run_id = load_run(fixtures, index)
    decision = execute_run(run_id, database)
    assert decision["decision"] == expected, decision["reasons"]
    assert decision["provider"] == "mock" and decision["offline_demo"]
    with connect(database) as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        assert run["status"] == "completed" and run["finished_at"]
        stages = connection.execute("SELECT * FROM stage_results WHERE run_id=? ORDER BY stage_no", (run_id,)).fetchall()
        assert len(stages) == 9
        assert [stage["stage_no"] for stage in stages] == list(range(1, 10))
        for stage in stages:
            assert stage["input_json"] and stage["output_json"] and stage["started_at"]
            assert stage["duration_ms"] >= 0 and stage["rule_version"] == "1.0"
        messages = connection.execute("SELECT * FROM messages_outbox WHERE run_id=?", (run_id,)).fetchall()
        assert len(messages) == (1 if expected == "APPROVED" else 2)
        assert all(message["sent_at"] is None for message in messages)
    # Claiming a completed run is idempotent; it never fabricates a second audit.
    assert execute_run(run_id, database) == decision
    with connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM stage_results WHERE run_id=?", (run_id,)).fetchone()[0] == 9


def test_missing_real_provider_does_not_fallback(fixtures, monkeypatch):
    database, _, _ = fixtures
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    decision = execute_run(load_run(fixtures), database)
    assert decision["decision"] == "PENDING"
    assert decision["provider"] == "openai" and not decision["offline_demo"]
    with connect(database) as connection:
        assert connection.execute("SELECT status FROM stage_results WHERE stage_no=2").fetchone()[0] == "needs_manual_review"
        assert connection.execute("SELECT count(*) FROM stage_results").fetchone()[0] == 9
        assert connection.execute("SELECT count(*) FROM messages_outbox").fetchone()[0] == 0


def test_post_decision_stage_failure_cannot_leave_approved(fixtures, monkeypatch):
    database, _, _ = fixtures
    def broken(context):
        raise RuntimeError("unsafe provider detail must not be logged")
    monkeypatch.setattr(s8_communication, "run", broken)
    decision = execute_run(load_run(fixtures), database)
    assert decision["decision"] == "PENDING"
    assert any(reason["stage_no"] == 8 for reason in decision["reasons"])
    assert "unsafe provider detail" not in json.dumps(decision)


def test_schema_validation_retries_once_then_manual():
    calls = []
    def invalid():
        calls.append(True)
        return {"unexpected": "wrong schema"}
    with pytest.raises(llm.ManualReviewRequired):
        llm._validated(invalid, llm.EXTRACTION_SCHEMA)
    assert len(calls) == 2


def test_changed_form_uses_document_evidence_not_expected_outcome(fixtures):
    database, _, _ = fixtures
    decision = execute_run(load_run(fixtures, form_updates={"tax_id": "36-7009999"}), database)
    assert decision["decision"] == "REJECTED"
    assert any(reason["field"] == "tax_id" and reason["stage_no"] == 5 for reason in decision["reasons"])
