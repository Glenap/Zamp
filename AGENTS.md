# AGENTS.md — VendorGate

## What this project is
VendorGate is an automated vendor onboarding review process (case study PS-2).
Input: a vendor submission (form JSON + 1-4 PDF/image documents).
Output: status APPROVED / PENDING / REJECTED with visible reasoning, a drafted
vendor message for non-approved cases, and a full audit trail.
It must actually run end-to-end. No mock outputs, no fake data in the pipeline.

## Stack
- Backend: Python 3.11+, FastAPI, SQLite (SQLAlchemy or plain sqlite3), pytest
- Frontend: React + Vite + Tailwind (light theme, clean, modern)
- Live updates: Server-Sent Events (SSE)
- LLM: accessed ONLY through backend/llm.py (provider-agnostic wrapper).
  Provider and key come from env vars: LLM_PROVIDER (openai|anthropic),
  OPENAI_API_KEY / ANTHROPIC_API_KEY. Never hardcode keys.

## Core design rules
1. Deterministic logic (regex, checksums, fuzzy matching, thresholds, decision
   engine) is written in plain code. NEVER delegate it to the LLM.
2. The LLM is used only for: (a) reading/extracting documents, (b) drafting
   vendor and internal messages.
3. Every LLM output is validated against a JSON schema. On failure: retry once,
   then mark the stage "needs_manual_review". Never crash the pipeline.
4. Never silently guess. If data is ambiguous, say so in the reasoning.
5. All thresholds and per-country required docs live in a config table / JSON
   (settings), not hardcoded in stage files.
6. Every stage writes input, output, status, timestamps, duration and
   rule_version to the audit log.
7. Each stage has a type badge: "AI" or "RULE".

## Folder structure
backend/
  main.py            FastAPI app + routes + SSE
  db.py              schema + helpers
  llm.py             LLM wrapper
  config/            settings.json (thresholds, required docs, lists)
  rules/             validators (iban.py, gstin.py, ein.py, aba.py, names.py ...)
  stages/            one file per stage (s1_intake.py ... s9_audit.py)
  pipeline.py        orchestrates stages, emits events
  seed/              seed script, sample PDFs, scenarios.json
  tests/
frontend/
  src/pages, src/components
README.md, DEMO_SCRIPT.md, ASSUMPTIONS.md

## Working agreement
- Work on ONE task at a time. Do not build things I did not ask for.
- After each task: run the tests, run the app, and tell me exactly how to verify.
- Keep functions small and commented where the logic is non-obvious
  (I must explain every decision in a live interview).
- Ask before any major architecture change.
- Log every assumption you make into ASSUMPTIONS.md.

## Commands (keep these updated)
- Backend: cd backend && uvicorn main:app --reload
- Frontend: cd frontend && npm run dev
- Tests: cd backend && pytest
- Seed/reset: python backend/seed/seed.py --reset
