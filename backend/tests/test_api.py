"""Contract tests isolate HTTP behavior from the separately tested pipeline."""

from datetime import date
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend import api
from backend.db import connect
from backend.main import app
from backend.seed.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "api.sqlite3"
    fixtures = tmp_path / "samples"
    monkeypatch.setenv("VENDORGATE_DB_PATH", str(database))
    monkeypatch.setenv("VENDORGATE_SEED_DIR", str(fixtures))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    seed(database, reset=True, output_dir=fixtures, as_of=date(2026, 11, 23))

    def completed_test_pipeline(run_id, path):
        # Test-only substitute verifies the API reads persisted rows rather than
        # returning simulated decisions. Real pipeline behavior has its own suite.
        decision = {"decision": "PENDING", "risk_score": 15, "risk_breakdown": [],
                    "reasons": [{"stage_no": 3, "field": "documents", "message": "Test missing evidence", "evidence": []}],
                    "what_would_change": ["Provide evidence"], "confidence": 0.5}
        with connect(path) as connection:
            connection.execute("UPDATE runs SET status='completed',risk_score=15,decision_json=?,started_at=?,finished_at=? WHERE id=?",
                               (json.dumps(decision), "2026-11-23T10:00:00Z", "2026-11-23T10:00:01Z", run_id))
            for number in range(1, 10):
                output = {"summary": f"Recorded test stage {number}", "findings": [], "data": {}}
                connection.execute("""INSERT INTO stage_results(run_id,stage_no,stage_name,stage_type,status,input_json,output_json,started_at,duration_ms,rule_version)
                                      VALUES (?,?,?,'RULE','passed','{}',?,'2026-11-23T10:00:00Z',1,'test')""",
                                   (run_id, number, f"Test stage {number}", json.dumps(output)))
            connection.execute("INSERT INTO messages_outbox(run_id,audience,subject,body) VALUES (?,'vendor','Evidence request','Please provide the requested evidence.')", (run_id,))

    monkeypatch.setattr(api, "run_pipeline", completed_test_pipeline)
    with TestClient(app) as active:
        yield active, database, fixtures


def start(client, scenario="S1"):
    submitted = client.post(f"/api/scenarios/{scenario}/load")
    assert submitted.status_code == 200
    submission_id = submitted.json()["submission_id"]
    response = client.post(f"/api/submissions/{submission_id}/runs")
    assert response.status_code == 200
    return response.json()["run_id"], submission_id


def test_scenarios_load_parent_and_preserve_evidence(client):
    web, database, fixtures = client
    assert web.get("/health").json() == {"ok": True}
    assert web.get("/api/runtime").json() == {"llm_provider": "mock", "demo_mode": True, "delivery_mode": "manual_outbox"}
    scenarios = web.get("/api/scenarios").json()
    assert len(scenarios) == 6
    assert scenarios[4]["parent_submission_id"] == "S4"
    submitted = web.post("/api/scenarios/S5/load").json()["submission_id"]
    with connect(database) as connection:
        row = connection.execute("SELECT * FROM submissions WHERE id=?", (submitted,)).fetchone()
        assert row["parent_submission_id"].startswith("S4-")
        assert connection.execute("SELECT count(*) FROM submissions").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 6
        assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert web.post("/api/scenarios/missing/load").status_code == 404


def test_run_audit_events_history_and_manual_outbox(client):
    web, database, fixtures = client
    identifier, submission_id = start(web)
    detail = web.get(f"/api/runs/{identifier}").json()
    assert detail["decision"] == "PENDING"
    assert detail["elapsed_ms"] == 1000
    assert len(detail["stages"]) == 9
    assert detail["stages"][0]["input"] == {}
    assert detail["stages"][0]["rule_version"] == "test"
    stream = web.get(f"/api/runs/{identifier}/events")
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.text.count("event: stage_started") == 9
    assert stream.text.count("event: stage_completed") == 9
    assert "event: run_completed" in stream.text
    replay = web.get(f"/api/runs/{identifier}/events", headers={"Last-Event-ID": "19"})
    assert "event: stage_completed" not in replay.text
    assert "event: run_completed" in replay.text
    history = web.get("/api/runs?status=PENDING&q=brightline").json()
    assert history["total"] == 1
    assert history["items"][0]["run_id"] == identifier
    assert web.get("/api/runs?offset=-1").status_code == 422
    message_id = detail["messages"][0]["id"]
    assert web.put(f"/api/messages/{message_id}", json={"subject": "Evidence needed", "body": "Please attach a bank letter."}).status_code == 200
    sent = web.post(f"/api/runs/{identifier}/send").json()
    assert sent["delivery_mode"] == "manual_outbox"
    assert "no email" in sent["notice"].lower()
    assert web.post(f"/api/runs/{identifier}/send").json()["sent_at"] == sent["sent_at"]
    assert web.put(f"/api/messages/{message_id}", json={"subject": "changed", "body": "changed"}).status_code == 409
    statistics = web.get("/api/dashboard/stats").json()
    assert statistics["total"] == 1
    assert statistics["pending_pct"] == 100
    assert statistics["manual_hours_saved"] == 0


def test_override_rerun_resubmit_and_parent_diff(client):
    web, database, fixtures = client
    identifier, submission_id = start(web)
    assert web.post(f"/api/runs/{identifier}/override", json={"new_status": "APPROVED", "reason": " "}).status_code == 422
    overridden = web.post(f"/api/runs/{identifier}/override", json={"new_status": "APPROVED", "reason": "Independent manual evidence verified"}).json()
    assert overridden["decision"] == "APPROVED"
    assert overridden["overrides"][0]["old_status"] == "PENDING"
    assert overridden["overrides"][0]["new_status"] == "APPROVED"
    assert web.get("/api/dashboard/stats").json()["auto_approved_pct"] == 0
    rerun = web.post(f"/api/runs/{identifier}/rerun").json()["run_id"]
    assert web.get(f"/api/runs/{rerun}").json()["parent_run_id"] == identifier
    form = overridden["form"]
    form["trade_name"] = "Updated trading name"
    resubmitted = web.post(f"/api/submissions/{submission_id}/resubmit", data={"form_json": json.dumps(form)})
    new_submission = resubmitted.json()["submission_id"]
    next_run = web.post(f"/api/submissions/{new_submission}/runs").json()["run_id"]
    next_detail = web.get(f"/api/runs/{next_run}").json()
    assert next_detail["parent_run_id"] == rerun
    assert next_detail["form"]["trade_name"] == "Updated trading name"
    assert len(next_detail["documents"]) == 3
    assert next_detail["diff_from_parent"] is not None


def test_upload_validation_and_safe_document_serving(client):
    web, database, fixtures = client
    assert web.post("/api/submissions", data={"form_json": "[1]"}).status_code == 422
    assert web.post("/api/submissions", data={"form_json": "{broken"}).status_code == 422
    assert web.post("/api/submissions", data={"form_json": "{}"}, files={"files": ("fake.pdf", b"not pdf", "application/pdf")}).status_code == 422
    data = (fixtures / "docs/s1_w9.pdf").read_bytes()
    excessive = [("files", (f"{index}.pdf", data, "application/pdf")) for index in range(5)]
    assert web.post("/api/submissions", data={"form_json": "{}"}, files=excessive).status_code == 422
    response = web.post("/api/submissions", data={"form_json": '{"legal_name":"Upload test"}'},
                        files={"files": ("../../outside.pdf", data, "application/pdf")})
    assert response.status_code == 200
    submission_id = response.json()["submission_id"]
    with connect(database) as connection:
        document = connection.execute("SELECT * FROM documents WHERE submission_id=?", (submission_id,)).fetchone()
        assert document["filename"] == "outside.pdf"
        assert Path(document["path"]).is_relative_to(database.parent / "uploads")
    served = web.get(f"/api/documents/{document['id']}/file")
    assert served.status_code == 200
    assert served.content == data
    assert served.headers["content-type"] == "application/pdf"
    assert web.get("/api/documents/999999/file").status_code == 404
    assert web.get("/api/runs/999999").status_code == 404
    assert web.get("/api/not-an-endpoint").status_code == 404


def test_settings_validate_and_persist_without_mutating_defaults(client):
    web, database, fixtures = client
    original = web.get("/api/settings").json()
    assert web.put("/api/settings", json={"name_match_threshold": 2}).status_code == 422
    assert web.put("/api/settings", json={"max_documents": 5}).status_code == 422
    assert web.put("/api/settings", json={"max_upload_bytes": -1}).status_code == 422
    assert web.put("/api/settings", json={"risk_bands": {"low": [0, 31], "medium": [31, 60], "high": [61, 100]}}).status_code == 422
    assert web.put("/api/settings", json={"required_docs": {"OTHER": [123]}}).status_code == 422
    updated = web.put("/api/settings", json={"name_match_threshold": 0.9})
    assert updated.status_code == 200
    assert web.get("/api/settings").json()["name_match_threshold"] == 0.9
    assert original["name_match_threshold"] == 0.85
    assert "markdown" in web.get("/api/assumptions").json()


def test_real_pipeline_scenarios_through_http_and_durable_audit(client, monkeypatch):
    from backend.pipeline import execute_run

    web, database, fixtures = client
    monkeypatch.setattr(api, "run_pipeline", lambda run_id, path: execute_run(run_id, db_path=path))
    scenarios = web.get("/api/scenarios").json()
    results = {}
    for scenario in scenarios:
        identifier, _ = start(web, scenario["id"])
        detail = web.get(f"/api/runs/{identifier}").json()
        assert detail["status"] == "completed"
        assert detail["decision"] == scenario["expected_decision"], (scenario["id"], detail["reasons"])
        assert len(detail["stages"]) == 9
        assert [stage["type"] for stage in detail["stages"]] == ["RULE", "AI", "RULE", "RULE", "RULE", "RULE", "RULE", "AI", "RULE"]
        assert all(stage["input"] and stage["output"] and stage["rule_version"] and stage["duration_ms"] >= 0 for stage in detail["stages"])
        assert all(message["sent_at"] is None for message in detail["messages"])
        results[scenario["id"]] = detail
    assert results["S5"]["parent_run_id"] == results["S4"]["run_id"]
    assert results["S5"]["diff_from_parent"]["resolved"]
    assert "event: run_completed" in web.get(f"/api/runs/{results['S5']['run_id']}/events").text
