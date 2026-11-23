"""Synchronous orchestration; SSE reads the durably committed stage rows."""

from datetime import datetime, timezone
import json
import time

from backend.db import connect
from backend.llm import provider_name
from backend.stages import (s1_intake, s2_extract, s3_required_docs, s4_format,
                            s5_cross_reference, s6_risk, s7_decision, s8_communication, s9_audit)
from backend.stages.common import finding, result

STAGES = [("Intake & completeness", "RULE", s1_intake), ("Document classification & extraction", "AI", s2_extract),
          ("Required-document check", "RULE", s3_required_docs), ("Format validation", "RULE", s4_format),
          ("Cross-reference consistency", "RULE", s5_cross_reference), ("Risk & fraud screening", "RULE", s6_risk),
          ("Decision engine", "RULE", s7_decision), ("Communication drafting", "AI", s8_communication), ("Audit log", "RULE", s9_audit)]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def execute_run(run_id, db_path=None):
    """Claim a queued run once, audit every stage and fail closed on stage errors."""
    started = utc_now()
    with connect(db_path) as connection:
        claim = connection.execute("UPDATE runs SET status='running', started_at=? WHERE id=? AND status='queued'", (started, run_id))
        if claim.rowcount != 1:
            row = connection.execute("SELECT decision_json FROM runs WHERE id=?", (run_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else None
        run = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        submission = connection.execute("SELECT * FROM submissions WHERE id=?", (run["submission_id"],)).fetchone()
        settings = {row["key"]: json.loads(row["value_json"]) for row in connection.execute("SELECT * FROM settings")}
        documents = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE submission_id=? ORDER BY id", (run["submission_id"],))]
        vendors = [dict(row) for row in connection.execute("SELECT * FROM vendors_existing")]
    context = {"form": json.loads(submission["form_json"]), "settings": settings, "documents": documents, "existing_vendors": vendors,
               "reference_date": datetime.now(timezone.utc).date(), "provider": provider_name(), "findings": [], "extracted": [],
               "messages": [], "risk_score": 0, "risk_breakdown": []}
    for number, (name, kind, stage) in enumerate(STAGES, 1):
        timestamp, timer = utc_now(), time.perf_counter()
        inputs = {"form": context["form"], "documents": documents, "extracted": context["extracted"], "settings": settings,
                  "reference_date": context["reference_date"].isoformat(), "provider": context["provider"], "prior_findings": context["findings"]}
        with connect(db_path) as connection:
            stage_id = connection.execute("INSERT INTO stage_results(run_id,stage_no,stage_name,stage_type,status,input_json,started_at,rule_version) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, number, name, kind, "running", json.dumps(inputs), timestamp, settings.get("rule_version", "unconfigured"))).lastrowid
            if number == 9:
                context["audit_count"] = connection.execute("SELECT count(*) FROM stage_results WHERE run_id=? AND stage_no<9 AND output_json IS NOT NULL", (run_id,)).fetchone()[0]
        try:
            output = stage.run(context)
        except Exception as error:
            output = result("Stage could not complete; manual review required.",
                            [finding("stage", f"{name} failed safely ({type(error).__name__}).", action="Resolve this stage failure before approval.")], status="needs_manual_review")
        context["findings"].extend({"stage_no": number, **item} for item in output["findings"])
        elapsed = (time.perf_counter() - timer) * 1000
        output["duration_ms"] = round(elapsed, 3)
        with connect(db_path) as connection:
            connection.execute("UPDATE stage_results SET status=?,output_json=?,duration_ms=? WHERE id=?", (output["status"], json.dumps(output), elapsed, stage_id))
            if number == 2:
                for document in context["extracted"]:
                    connection.execute("UPDATE documents SET doc_type_detected=? WHERE id=?", (document["doc_type"], document["document_id"]))
            if number == 8:
                for message in context["messages"]:
                    connection.execute("INSERT INTO messages_outbox(run_id,audience,subject,body) VALUES (?,?,?,?)", (run_id, message["audience"], message["subject"], message["body"]))
    # Re-evaluate after communication/audit failures to avoid a stale APPROVED.
    try:
        decision = s7_decision.decide(context)
    except Exception:
        decision = {"decision": "PENDING", "risk_score": context["risk_score"], "risk_breakdown": context["risk_breakdown"],
                    "reasons": [{"stage_no": 7, "field": "configuration", "message": "Decision policy incomplete; manual review required.", "evidence": None}],
                    "what_would_change": ["Restore valid policy settings and rerun."], "confidence": 0,
                    "provider": context["provider"], "offline_demo": context["provider"] == "mock"}
    with connect(db_path) as connection:
        connection.execute("UPDATE runs SET status='completed',risk_score=?,decision_json=?,finished_at=? WHERE id=?", (decision["risk_score"], json.dumps(decision), utc_now(), run_id))
    return decision
