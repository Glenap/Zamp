# AGENTS.md — VendorGate

VendorGate is an end-to-end vendor onboarding case study (PS-2). Run the real pipeline for the live interview. Mock provider and frontend modes are explicit and limited to offline testing and demos.

## Stack and global rules
- Backend: Python 3.11+, FastAPI, SQLite, pytest, rapidfuzz, jsonschema, reportlab.
- Frontend: React + Vite + TypeScript + Tailwind + React Router + Recharts.
  Light theme, Inter font, rounded-xl cards, green=approved, amber=pending,
  red=rejected. Proper loading/empty/error states. No lorem ipsum.
- Live updates: Server-Sent Events.
- LLM only through backend/llm.py. Env: LLM_PROVIDER (openai|anthropic|mock),
  OPENAI_API_KEY / ANTHROPIC_API_KEY, LLM_MODEL. Never hardcode keys.
  Mock mode returns deterministic canned output so tests and offline demos work.
  Real mode must never silently fall back to mock.
- RULE 1: deterministic logic (regex, checksums, fuzzy match, thresholds,
  decision engine) is plain code. NEVER delegate it to the LLM.
- RULE 2: LLM is used only for (a) reading/extracting documents, (b) drafting
  vendor and internal messages.
- RULE 3: every LLM output is validated against a JSON schema; retry once; then
  stage = "needs_manual_review". The pipeline must never crash.
- RULE 4: never silently guess. Ambiguity is stated in the reasoning.
- RULE 5: all thresholds, required docs per country, lists live in
  backend/config/settings.json (editable via Settings page), not hardcoded.
- RULE 6: every stage writes input, output, status, timestamps, duration,
  rule_version to the audit log.
- RULE 7: each stage shows an "AI" or "RULE" badge.
- RULE 8: small commented functions. I must explain every decision live.
- RULE 9: log every assumption in ASSUMPTIONS.md (append only).
- RULE 10: do not build things I did not ask for; ask before major
  architecture changes.

Folder structure:
backend/ main.py, db.py, llm.py, pipeline.py, config/settings.json,
  rules/, stages/ (s1_intake.py ... s9_audit.py), prompts/, seed/, tests/
frontend/ src/{api,pages,components}
AGENTS.md, API_CONTRACT.md, README.md, DEMO_SCRIPT.md, ASSUMPTIONS.md

## API contract
Implement and consume the endpoint definitions in [API_CONTRACT.md](API_CONTRACT.md). Update the contract first if an agreed change is needed.

## Working agreement
- Work one phase at a time. Stop at each checkpoint after running the tests and app, and report how to verify.
- Run parallel tracks in separate worktrees with only their assigned files. Merge in the phase's specified order and test after each merge.

## Commands
- Backend: `python -m uvicorn backend.main:app --reload`
- Frontend: `cd frontend` then `npm run dev`
- Tests: `python -m pytest backend`
- Reset: `python backend/seed/seed.py --reset`
