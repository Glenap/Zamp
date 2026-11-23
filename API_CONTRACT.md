Base URL http://localhost:8000. JSON unless noted.
Hosted deployment uses the same endpoints at its Site origin.
GET /api/runtime -> {"llm_provider","demo_mode","delivery_mode"}
`delivery_mode=manual_outbox`: /send records the operator's manual delivery; it
does not transmit email. Real provider modes require LLM_MODEL and the provider
key; mock mode is explicitly labeled and cannot OCR custom uploads or scans.
Hosted queued runs start when the review SSE stream is opened. The stream
replays durable stage events on reconnect; no pipeline result comes from a
scenario's expected_decision. Private Sites access protects the hosted records.
Enums: run.status queued|running|completed|failed; decision
APPROVED|PENDING|REJECTED; stage.status
queued|running|passed|warning|failed|needs_manual_review; stage.type AI|RULE.
Stages: 1 Intake&completeness(RULE) 2 Doc classification&extraction(AI)
3 Required-document check(RULE) 4 Format validation(RULE) 5 Cross-reference
consistency(RULE) 6 Risk&fraud screening(RULE) 7 Decision engine(RULE)
8 Communication drafting(AI) 9 Audit log(RULE)
Endpoints:
GET /health -> {"ok":true}
GET /api/scenarios -> [{"id","title","description","expected_decision",
  "form":{...},"documents":["file.pdf"]}]
POST /api/submissions (multipart: form_json, files 0..4, optional
  parent_submission_id) -> {"submission_id"}
POST /api/scenarios/{id}/load -> {"submission_id"}
POST /api/submissions/{id}/runs -> {"run_id"}
GET /api/runs/{run_id}/events (SSE): run_started{run_id,started_at};
  stage_started{stage_no,name,type}; stage_completed{stage_no,status,summary,
  duration_ms,findings,data}; run_completed{run_id,decision,risk_score,
  elapsed_ms}; run_error{message}
GET /api/runs?status=&q=&limit=&offset= -> {"total","items":[{"run_id",
  "vendor_name","country","decision","risk_score","duration_ms","created_at",
  "parent_run_id"}]}
GET /api/runs/{run_id} -> {run_id, submission_id, parent_run_id, status,
  decision, risk_score, risk_breakdown:[{signal,weight,triggered,detail}],
  reasons:[{stage_no,field,message,evidence}], what_would_change:[...],
  confidence, form, documents:[{id,filename,doc_type_detected,url}],
  stages:[{stage_no,name,type,status,summary,duration_ms,findings,data}],
  messages:[{id,audience,subject,body,sent_at}], overrides:[{reason,
  old_status,new_status,created_at}], diff_from_parent:{resolved,still_open,
  new}|null}
GET /api/documents/{id}/file -> bytes
PUT /api/messages/{id} {subject,body}
POST /api/runs/{run_id}/send -> {"sent_at"}
POST /api/runs/{run_id}/override {new_status,reason}
POST /api/runs/{run_id}/rerun -> {"run_id"}
POST /api/submissions/{id}/resubmit (multipart, parent set) -> {submission_id}
GET /api/dashboard/stats -> {total, auto_approved_pct, pending_pct,
  rejected_pct, avg_review_ms, flags_caught, manual_hours_saved,
  outcomes:[{decision,count}], top_reasons:[{reason,count}]}
GET/PUT /api/settings ; GET /api/assumptions -> {"markdown"}
