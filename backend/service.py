"""SQLite read models and small API persistence operations.

The pipeline owns decisions. This module exposes stored evidence and preserves
explicit manual overrides; it never invents a completed review.
"""

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from fastapi import HTTPException

from backend.db import BACKEND_DIR, connect, database_path


def now():
    return datetime.now(timezone.utc).isoformat()


def decode(value, fallback=None):
    return json.loads(value) if value else fallback


def elapsed(start, finish):
    if not start or not finish:
        return None
    return max(0, round((datetime.fromisoformat(finish.replace("Z", "+00:00")) -
                         datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds() * 1000))


def require_row(connection, table, identifier):
    # Table names are exclusively module-defined constants, never request input.
    row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{table.rstrip('s').replace('_', ' ').title()} not found")
    return dict(row)


def runtime():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    return {"llm_provider": provider, "demo_mode": provider == "mock", "delivery_mode": "manual_outbox"}


def seed_directory():
    return Path(os.getenv("VENDORGATE_SEED_DIR", str(BACKEND_DIR / "seed"))).resolve()


def manifest():
    path = seed_directory() / "scenarios.json"
    if not path.is_file():
        raise HTTPException(503, "Sample documents are not seeded. Run python backend/seed/seed.py.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["scenarios"] if isinstance(data, dict) else data


def create_submission(form, documents, parent=None, prefix=""):
    identifier = prefix + uuid.uuid4().hex
    with connect() as connection:
        if parent:
            require_row(connection, "submissions", parent)
        connection.execute("INSERT INTO submissions(id,parent_submission_id,form_json) VALUES (?,?,?)",
                           (identifier, parent, json.dumps(form)))
        connection.executemany(
            "INSERT INTO documents(submission_id,filename,path) VALUES (?,?,?)",
            [(identifier, filename, str(Path(path).resolve())) for filename, path in documents],
        )
    return identifier


def load_scenario(scenario_id):
    scenarios = manifest()
    scenario = next((item for item in scenarios if item["id"] == scenario_id), None)
    if scenario is None:
        raise HTTPException(404, "Scenario not found")
    parent = None
    if scenario.get("parent_submission_id"):
        parent_id = scenario["parent_submission_id"]
        with connect() as connection:
            row = connection.execute("SELECT id FROM submissions WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
                                     (parent_id + "-%",)).fetchone()
        parent = row[0] if row else load_scenario(parent_id)
    docs = [(filename, seed_directory() / "docs" / filename) for filename in scenario["documents"]]
    if any(not path.is_file() for _, path in docs):
        raise HTTPException(503, "A sample document is missing; regenerate seed fixtures.")
    return create_submission(scenario["form"], docs, parent=parent, prefix=scenario_id + "-")


def new_run(submission_id, parent_run_id=None):
    with connect() as connection:
        submission = require_row(connection, "submissions", submission_id)
        if parent_run_id is None and submission["parent_submission_id"]:
            parent = connection.execute("SELECT id FROM runs WHERE submission_id=? ORDER BY id DESC LIMIT 1",
                                        (submission["parent_submission_id"],)).fetchone()
            parent_run_id = parent[0] if parent else None
        result = connection.execute("INSERT INTO runs(submission_id,parent_run_id,status) VALUES (?,?,'queued')",
                                    (submission_id, parent_run_id))
        return result.lastrowid


def stages_for(connection, run_id):
    stages = []
    for row in connection.execute("SELECT * FROM stage_results WHERE run_id=? ORDER BY stage_no,id", (run_id,)):
        stage = dict(row)
        output = decode(stage["output_json"], {})
        stages.append({"stage_no": stage["stage_no"], "name": stage["stage_name"],
                       "type": stage["stage_type"], "status": stage["status"],
                       "summary": output.get("summary", ""), "findings": output.get("findings", []),
                       "data": output.get("data", {}), "input": decode(stage["input_json"], {}),
                       "output": output, "started_at": stage["started_at"],
                       "duration_ms": stage["duration_ms"], "rule_version": stage["rule_version"]})
    return stages


def reason_key(reason):
    if isinstance(reason, str):
        return reason
    return str(reason.get("field", "")) + ": " + str(reason.get("message", ""))


def run_detail(run_id):
    with connect() as connection:
        run = require_row(connection, "runs", run_id)
        submission = require_row(connection, "submissions", run["submission_id"])
        decision = decode(run["decision_json"], {})
        documents = [{"id": row["id"], "filename": row["filename"],
                      "doc_type_detected": row["doc_type_detected"],
                      "url": f"/api/documents/{row['id']}/file"}
                     for row in connection.execute("SELECT * FROM documents WHERE submission_id=? ORDER BY id",
                                                   (run["submission_id"],))]
        messages = [dict(row) for row in connection.execute("SELECT * FROM messages_outbox WHERE run_id=? ORDER BY id", (run_id,))]
        overrides = [dict(row) for row in connection.execute("SELECT * FROM overrides WHERE run_id=? ORDER BY id", (run_id,))]
        stages = stages_for(connection, run_id)
        parent_decision = None
        if run["parent_run_id"]:
            parent_decision = decode(require_row(connection, "runs", run["parent_run_id"])["decision_json"], {})
    reasons = decision.get("reasons", [])
    difference = None
    if parent_decision is not None:
        previous = {reason_key(item) for item in parent_decision.get("reasons", [])}
        current = {reason_key(item) for item in reasons}
        difference = {"resolved": sorted(previous - current), "still_open": sorted(previous & current),
                      "new": sorted(current - previous)}
    return {"run_id": run["id"], "submission_id": run["submission_id"],
            "parent_run_id": run["parent_run_id"], "status": run["status"],
            "decision": decision.get("decision"), "risk_score": run["risk_score"],
            "risk_breakdown": decision.get("risk_breakdown", []), "reasons": reasons,
            "what_would_change": decision.get("what_would_change", []),
            "confidence": decision.get("confidence"), "form": decode(submission["form_json"], {}),
            "documents": documents, "stages": stages, "messages": messages, "overrides": overrides,
            "diff_from_parent": difference, "started_at": run["started_at"], "finished_at": run["finished_at"],
            "elapsed_ms": elapsed(run["started_at"], run["finished_at"])}


def run_items():
    with connect() as connection:
        rows = list(connection.execute(
            """SELECT r.*, s.form_json, s.created_at AS submitted_at
               FROM runs r JOIN submissions s ON s.id=r.submission_id ORDER BY r.id DESC"""))
    items = []
    for row in rows:
        form = decode(row["form_json"], {})
        decision = decode(row["decision_json"], {})
        items.append({"run_id": row["id"], "submission_id": row["submission_id"],
                      "vendor_name": form.get("legal_name", "Unnamed vendor"), "country": form.get("country", ""),
                      "status": row["status"], "decision": decision.get("decision"), "risk_score": row["risk_score"],
                      "duration_ms": elapsed(row["started_at"], row["finished_at"]),
                      "created_at": row["started_at"] or row["submitted_at"], "parent_run_id": row["parent_run_id"]})
    return items


def dashboard():
    items = run_items()
    complete = [item for item in items if item["status"] == "completed"]
    counts = Counter(item["decision"] for item in complete)
    durations = [item["duration_ms"] for item in complete if item["duration_ms"] is not None]
    with connect() as connection:
        overridden = {row[0] for row in connection.execute("SELECT DISTINCT run_id FROM overrides")}
        reasons = []
        for row in connection.execute("SELECT decision_json FROM runs WHERE status='completed'"):
            reasons.extend(reason_key(reason) for reason in decode(row[0], {}).get("reasons", []))
    total = len(complete)
    percentage = lambda value: round(100 * value / total, 1) if total else 0
    automatic = sum(item["decision"] == "APPROVED" and item["run_id"] not in overridden for item in complete)
    return {"total": len(items), "auto_approved_pct": percentage(automatic),
            "pending_pct": percentage(counts["PENDING"]), "rejected_pct": percentage(counts["REJECTED"]),
            "avg_review_ms": round(sum(durations) / len(durations)) if durations else 0,
            "flags_caught": len(reasons), "manual_hours_saved": 0,
            "manual_hours_saved_note": "Not estimated; no measured manual-review baseline has been configured.",
            "outcomes": [{"decision": status, "count": counts[status]} for status in ("APPROVED", "PENDING", "REJECTED")],
            "top_reasons": [{"reason": reason, "count": count} for reason, count in Counter(reasons).most_common(6)]}


def settings():
    with connect() as connection:
        return {row["key"]: decode(row["value_json"]) for row in connection.execute("SELECT * FROM settings")}


def validate_settings(values):
    try:
        json.dumps(values, allow_nan=False)
    except (ValueError, TypeError):
        raise HTTPException(422, "Settings must contain finite JSON values")
    for name in ("name_match_threshold", "extraction_confidence_min", "sanctions_name_match_threshold"):
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise HTTPException(422, f"{name} must be a number between 0 and 1")
    band = values.get("name_match_review_band", {})
    if not isinstance(band, dict) or not all(type(band.get(k)) in (int, float) for k in ("min", "max")):
        raise HTTPException(422, "name_match_review_band requires numeric min/max")
    if not 0 <= band["min"] < band["max"] <= values["name_match_threshold"]:
        raise HTTPException(422, "Review band must be ordered and below the match threshold")
    risk = values.get("risk_bands", {})
    if not isinstance(risk, dict) or any(not isinstance(risk.get(key), list) or len(risk[key]) != 2 for key in ("low", "medium", "high")):
        raise HTTPException(422, "risk_bands requires low/medium/high integer ranges")
    ranges = [risk[key] for key in ("low", "medium", "high")]
    if any(type(v) is not int for pair in ranges for v in pair) or ranges[0][0] != 0 or ranges[-1][1] != 100:
        raise HTTPException(422, "Risk bands must cover integer scores 0 to 100")
    if any(lo > hi for lo, hi in ranges) or any(ranges[i][1] + 1 != ranges[i + 1][0] for i in range(2)):
        raise HTTPException(422, "Risk bands must be ordered, contiguous and non-overlapping")
    for name in ("high_risk_jurisdictions", "free_mail_domains", "sanctions_list", "eu_countries"):
        if not isinstance(values.get(name), list) or any(not isinstance(v, str) for v in values[name]):
            raise HTTPException(422, f"{name} must be a list of strings")
    for name in ("max_documents", "min_documents", "max_document_pages", "max_document_pixels", "max_upload_bytes"):
        if type(values.get(name)) is not int or values[name] < 1:
            raise HTTPException(422, f"{name} must be a positive integer")
    if not 1 <= values["min_documents"] <= values["max_documents"] <= 4:
        raise HTTPException(422, "Document limits must be ordered within 1 to 4")
    if values.get("max_risk_score") != 100:
        raise HTTPException(422, "max_risk_score must remain 100 to match risk bands and database limits")
    for name in ("llm_timeout_seconds", "manual_review_minutes"):
        if type(values.get(name)) not in (int, float) or values[name] <= 0:
            raise HTTPException(422, f"{name} must be a positive number")
    required_fields = values.get("required_form_fields")
    if not isinstance(required_fields, list) or not required_fields or any(not isinstance(v, str) or not v.strip() for v in required_fields):
        raise HTTPException(422, "required_form_fields must be a nonempty list of field names")
    if not isinstance(values.get("rule_version"), str) or not values["rule_version"].strip():
        raise HTTPException(422, "rule_version must be a nonempty string")
    docs = values.get("required_docs")
    if not isinstance(docs, dict) or not docs or "OTHER" not in docs:
        raise HTTPException(422, "required_docs must define country policies including OTHER")
    for required in docs.values():
        if not isinstance(required, list) or any(not (isinstance(v, str) or isinstance(v, list) and v and all(isinstance(x, str) for x in v)) for v in required):
            raise HTTPException(422, "Required documents must be names or nonempty lists of alternatives")
    for name in ("new_company_days", "high_spend_threshold"):
        if isinstance(values.get(name), bool) or not isinstance(values.get(name), (int, float)) or values[name] < 0:
            raise HTTPException(422, f"{name} must be a nonnegative number")
    weights = values.get("risk_signal_weights")
    if not isinstance(weights, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100 for v in weights.values()):
        raise HTTPException(422, "Risk signal weights must be numbers between 0 and 100")
    aliases = values.get("country_aliases")
    if not isinstance(aliases, dict) or any(not isinstance(v, str) for v in aliases.values()):
        raise HTTPException(422, "country_aliases must map country codes to string codes")
    validity = values.get("document_validity_rules")
    if not isinstance(validity, dict):
        raise HTTPException(422, "document_validity_rules must be an object")
    for rule in validity.values():
        if not isinstance(rule, dict):
            raise HTTPException(422, "Each document validity rule must be an object")
        age = rule.get("max_age_days")
        if age is not None and (type(age) is not int or age < 0):
            raise HTTPException(422, "Document max_age_days must be a nonnegative integer or null")
        if "expiry_required" in rule and not isinstance(rule["expiry_required"], bool):
            raise HTTPException(422, "Document expiry_required must be true or false")
    return values
