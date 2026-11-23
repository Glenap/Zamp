# VendorGate

Task 1 foundation for the PS-2 vendor onboarding case study: FastAPI health endpoint,
SQLite schema, synthetic seed fixtures and PDF documents, plus a React/Vite/Tailwind
page that displays **VendorGate**. Pipeline stages, LLM integration, SSE and review UI
are reserved for later tasks.

## Setup

Requires Python 3.11+ and Node.js 22.12+ with npm. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
cd ..
python backend/seed/seed.py --reset
```

On macOS/Linux activate with `source .venv/bin/activate`.

## Environment

`backend/.env.example` documents the variables. Export variables in your shell;
the app does not automatically load `.env` files.

| Variable | Default / purpose |
| --- | --- |
| `VENDORGATE_DB_PATH` | `backend/data/vendorgate.sqlite3`; relative values resolve under `backend/` |
| `LLM_PROVIDER` | Future wrapper selector, `openai` or `anthropic`; unused in Task 1 |
| `OPENAI_API_KEY` | Future OpenAI credential; no key needed for setup, seed or health |
| `ANTHROPIC_API_KEY` | Future Anthropic credential; no key needed for setup, seed or health |

Do not commit keys. SQLite files, local env files and dependencies are gitignored.

## Run and verify

Backend, in one terminal:

```powershell
cd backend
python -m uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/health>; expect `{"status":"ok","database":"ok"}`.
API documentation is at <http://127.0.0.1:8000/docs>.

Frontend, in another terminal:

```powershell
cd frontend
npm run dev
```

Open the local URL Vite prints (normally <http://localhost:5173>). The light page
displays only **VendorGate**. It does not call a pipeline or show simulated results.

Tests and frontend build:

```powershell
cd backend
python -m pytest
cd ../frontend
npm run build
```

## Seed data and documents

```powershell
python backend/seed/seed.py --reset
# Reproducible snapshot, optional isolated database and fixture destination:
python backend/seed/seed.py --reset --as-of 2026-11-23 --db data/demo.sqlite3 --output-dir tmp/demo-seed
```

`--reset` deletes **all rows in the selected SQLite database**, including runs and
overrides, then reloads defaults and fixtures. Use it only on a development/demo DB.
Without reset, existing rows/settings are preserved; use reset to refresh a dated
fixture set. Default reference date is UTC today, so S3 is incorporated 30 days before
that date. `--as-of` pins the date for replay.

The seed creates 20 existing vendors, 6 submissions, 18 document references and 17
unique PDFs under `backend/seed/docs/`. S5 shares S4's incorporation PDF and has
`parent_submission_id: S4`. Documents are not pre-classified, and no runs, stage
results, messages or overrides are fabricated. `backend/seed/scenarios.json` contains
the forms, filenames, expected-outcome descriptions and intentional-defect comments.

| Scenario | Fixture intent |
| --- | --- |
| S1 | Brightline Logistics LLC, consistent US EIN/W-9/bank/incorporation evidence |
| S2 | Sundaram Fasteners Pvt Ltd, valid GSTIN/IFSC, cheque holder Sundaram Traders |
| S3 | New company reuses approved Northwind's account `740015920061`; age 30 days |
| S4 | German vendor, wrong US W-9 and noisy, rotated, blurred image-only bank PDF |
| S5 | S4 resubmission with German VAT certificate and clear bank letter |
| S6 | Exact hit in the fictional sanctions list |

Open each PDF directly to inspect the country/document layouts. The degraded scan
has no text layer. Every PDF is visibly marked synthetic; identifiers are structurally
valid test examples, not proof of registration, account ownership or eligibility.
GSTIN, ABA, German/GB IBAN and German VAT checksums are covered by tests; EIN and
IFSC have format checks, not checksums. IBAN support currently covers DE and GB only.

## Structure

```text
backend/
  main.py, db.py, llm.py, pipeline.py
  config/settings.json
  rules/                 format/checksum helpers only
  stages/                empty; reserved for later tasks
  seed/                  generator, scenarios.json, docs/
  tests/
frontend/
  src/main.jsx, src/styles.css
  src/pages/, src/components/
AGENTS.md, DEMO_SCRIPT.md, ASSUMPTIONS.md
```

Settings JSON initializes the SQLite `settings` table. Ordinary startup preserves
operator-edited settings; seed reset reloads the JSON defaults. Name review band is
`0.65 <= score < 0.85`, with match at `>=0.85`; risk bands use integer scores.
These are stored configuration only, not implemented decision logic.
