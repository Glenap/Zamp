"""API contract for vendor review, durable audit replay and a manual message outbox."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
import fitz

from backend.db import BACKEND_DIR, connect, database_path
from backend import service

router = APIRouter(prefix="/api")
MAX_FILE_BYTES = 10 * 1024 * 1024


def run_pipeline(run_id, path):
    try:
        from backend.pipeline import execute_run
        execute_run(run_id, db_path=path)
    except Exception:
        # Keep details out of responses: provider exceptions can contain credentials.
        with connect(path) as connection:
            connection.execute("UPDATE runs SET status='failed',finished_at=? WHERE id=? AND status!='completed'",
                               (service.now(), run_id))


def parse_form(value):
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(422, "form_json must contain valid JSON")
    if not isinstance(data, dict):
        raise HTTPException(422, "form_json must be a JSON object")
    return data


def sniff(data):
    if data.startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise HTTPException(422, "Only PDF, PNG, JPEG and WebP documents are supported")


async def store_uploads(files):
    if len(files) > 4:
        raise HTTPException(422, "Upload at most four documents")
    collected = []
    # Validate the entire request before persisting any files.
    for upload in files:
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, "Each document must be 10 MB or smaller")
        extension, _ = sniff(data)
        try:
            with fitz.open(stream=data, filetype=extension.lstrip(".")) as document:
                if document.is_encrypted or document.page_count == 0:
                    raise ValueError("Encrypted or empty document")
        except Exception:
            raise HTTPException(422, "A document is unreadable, encrypted or damaged")
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", (upload.filename or "document").replace("\\", "/").split("/")[-1])
        name = name.strip(" .")[:150] or "document"
        if Path(name).suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
            name += extension
        elif (extension == ".pdf") != (Path(name).suffix.lower() == ".pdf"):
            raise HTTPException(422, "Document filename extension does not match its content")
        collected.append((name, data))
    folder = database_path().parent / "uploads" / uuid.uuid4().hex
    if collected:
        folder.mkdir(parents=True, exist_ok=True)
    result = []
    for index, (name, data) in enumerate(collected):
        path = folder / f"{index + 1}-{name}"
        path.write_bytes(data)
        result.append((name, path))
    return result


@router.get("/runtime")
async def runtime():
    return service.runtime()


@router.get("/scenarios")
async def scenarios():
    return service.manifest()


@router.post("/scenarios/{scenario_id}/load")
async def load_scenario(scenario_id: str):
    return {"submission_id": service.load_scenario(scenario_id)}


@router.post("/submissions")
async def submit(form_json: str = Form(...), files: list[UploadFile] = File(default=[]),
                 parent_submission_id: str | None = Form(default=None)):
    form = parse_form(form_json)
    if parent_submission_id:
        with connect() as connection:
            service.require_row(connection, "submissions", parent_submission_id)
    documents = await store_uploads(files)
    return {"submission_id": service.create_submission(form, documents, parent_submission_id)}


@router.post("/submissions/{submission_id}/resubmit")
async def resubmit(submission_id: str, form_json: str = Form(...), files: list[UploadFile] = File(default=[])):
    form = parse_form(form_json)
    with connect() as connection:
        service.require_row(connection, "submissions", submission_id)
        previous = [(row["filename"], row["path"]) for row in connection.execute(
            "SELECT * FROM documents WHERE submission_id=? ORDER BY id", (submission_id,))]
    documents = await store_uploads(files) if files else previous
    return {"submission_id": service.create_submission(form, documents, parent=submission_id)}


@router.post("/submissions/{submission_id}/runs")
async def start_run(submission_id: str, background: BackgroundTasks):
    identifier = service.new_run(submission_id)
    background.add_task(run_pipeline, identifier, database_path())
    return {"run_id": identifier}


@router.get("/runs")
async def list_runs(status: str | None = None, q: str = "", limit: int = 20, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "limit must be between 1 and 100; offset must be nonnegative")
    items = service.run_items()
    if status:
        items = [item for item in items if item["decision"] == status.upper() or item["status"] == status.lower()]
    if q:
        items = [item for item in items if q.casefold() in (item["vendor_name"] + " " + item["country"]).casefold()]
    return {"total": len(items), "items": items[offset:offset + limit]}


@router.get("/runs/{run_id}")
async def detail(run_id: int):
    return service.run_detail(run_id)


def event(identifier, name, data):
    return f"id: {identifier}\nevent: {name}\ndata: {json.dumps(data)}\n\n"


@router.get("/runs/{run_id}/events")
async def events(run_id: int, request: Request):
    with connect() as connection:
        service.require_row(connection, "runs", run_id)
    try:
        after = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        after = 0

    async def stream():
        sent = set()
        heartbeat = 0
        while not await request.is_disconnected():
            detail = service.run_detail(run_id)
            ready = []
            if detail["started_at"]:
                ready.append((1, "run_started", {"run_id": run_id, "started_at": detail["started_at"]}))
            for stage in detail["stages"]:
                number = stage["stage_no"]
                ready.append((number * 2, "stage_started", {"stage_no": number, "name": stage["name"], "type": stage["type"]}))
                if stage["status"] not in ("queued", "running"):
                    ready.append((number * 2 + 1, "stage_completed", {
                        "stage_no": number, "status": stage["status"], "summary": stage["summary"],
                        "duration_ms": stage["duration_ms"], "findings": stage["findings"], "data": stage["data"]}))
            if detail["status"] == "completed":
                ready.append((20, "run_completed", {"run_id": run_id, "decision": detail["decision"],
                                                    "risk_score": detail["risk_score"], "elapsed_ms": detail["elapsed_ms"]}))
            elif detail["status"] == "failed":
                ready.append((20, "run_error", {"message": "Review could not finish. Check configuration and retry; stored audit is available."}))
            for identifier, name, data in sorted(ready):
                if identifier not in sent and identifier > after:
                    yield event(identifier, name, data)
                    sent.add(identifier)
            if detail["status"] in ("completed", "failed"):
                return
            heartbeat += 1
            if heartbeat % 40 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/documents/{document_id}/file")
async def document_file(document_id: int):
    with connect() as connection:
        document = service.require_row(connection, "documents", document_id)
    path = Path(document["path"]).resolve()
    roots = [(database_path().parent / "uploads").resolve(), (service.seed_directory() / "docs").resolve()]
    if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
        raise HTTPException(404, "Document file is unavailable")
    media = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=document["filename"], content_disposition_type="inline")


@router.put("/messages/{message_id}")
async def edit_message(message_id: int, payload: dict = Body(...)):
    if not isinstance(payload.get("subject"), str) or not payload["subject"].strip() or not isinstance(payload.get("body"), str) or not payload["body"].strip():
        raise HTTPException(422, "A nonempty subject and body are required")
    with connect() as connection:
        message = service.require_row(connection, "messages_outbox", message_id)
        if message["sent_at"]:
            raise HTTPException(409, "This draft is already recorded as sent; its content is preserved")
        connection.execute("UPDATE messages_outbox SET subject=?,body=? WHERE id=?",
                           (payload["subject"].strip(), payload["body"].strip(), message_id))
    return {"id": message_id, "subject": payload["subject"].strip(), "body": payload["body"].strip()}


@router.post("/runs/{run_id}/send")
async def mark_sent(run_id: int):
    with connect() as connection:
        run = service.require_row(connection, "runs", run_id)
        if run["status"] != "completed":
            raise HTTPException(409, "Finish the review before recording message delivery")
        rows = list(connection.execute("SELECT sent_at FROM messages_outbox WHERE run_id=?", (run_id,)))
        if not rows:
            raise HTTPException(409, "No drafted messages are available")
        timestamp = service.now() if any(row[0] is None for row in rows) else rows[0][0]
        connection.execute("UPDATE messages_outbox SET sent_at=? WHERE run_id=? AND sent_at IS NULL", (timestamp, run_id))
    return {"sent_at": timestamp, "delivery_mode": "manual_outbox", "notice": "Recorded only; no email was transmitted."}


@router.post("/runs/{run_id}/override")
async def override(run_id: int, payload: dict = Body(...)):
    status = payload.get("new_status")
    reason = payload.get("reason")
    if status not in ("APPROVED", "PENDING", "REJECTED") or not isinstance(reason, str) or not reason.strip():
        raise HTTPException(422, "Override requires a valid new_status and a nonempty reason")
    with connect() as connection:
        run = service.require_row(connection, "runs", run_id)
        if run["status"] != "completed":
            raise HTTPException(409, "Only completed decisions can be overridden")
        decision = service.decode(run["decision_json"], {})
        previous = decision.get("decision")
        if previous == status:
            raise HTTPException(409, "The decision already has that status")
        connection.execute("INSERT INTO overrides(run_id,reason,old_status,new_status) VALUES (?,?,?,?)",
                           (run_id, reason.strip(), previous, status))
        decision["decision"] = status
        connection.execute("UPDATE runs SET decision_json=? WHERE id=?", (json.dumps(decision), run_id))
    return service.run_detail(run_id)


@router.post("/runs/{run_id}/rerun")
async def rerun(run_id: int, background: BackgroundTasks):
    with connect() as connection:
        previous = service.require_row(connection, "runs", run_id)
    identifier = service.new_run(previous["submission_id"], parent_run_id=run_id)
    background.add_task(run_pipeline, identifier, database_path())
    return {"run_id": identifier}


@router.get("/dashboard/stats")
async def statistics():
    return service.dashboard()


@router.get("/settings")
async def get_settings():
    return service.settings()


@router.put("/settings")
async def put_settings(payload: dict = Body(...)):
    merged = service.validate_settings({**service.settings(), **payload})
    try:
        json.dumps(merged, allow_nan=False)
    except (ValueError, TypeError):
        raise HTTPException(422, "Settings must contain finite JSON values")
    with connect() as connection:
        connection.executemany("INSERT INTO settings(key,value_json) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                               [(key, json.dumps(value)) for key, value in merged.items()])
    return merged


@router.get("/assumptions")
async def assumptions():
    path = BACKEND_DIR.parent / "ASSUMPTIONS.md"
    return {"markdown": path.read_text(encoding="utf-8") if path.is_file() else "No assumptions have been recorded."}
