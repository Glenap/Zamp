# VendorGate

Vendor onboarding case study PS-2. Upload form data and up to four PDF/image documents,
run nine audited stages, inspect evidence and deterministic findings, review draft
messages, and keep a history of decisions and reasoned manual overrides.

## Run locally

Requires Python 3.11+ and Node.js 22.13+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python backend/seed/seed.py --reset
cd frontend
npm ci
npm run build
cd ..
$env:LLM_PROVIDER = 'mock'
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 for the built app. `/health` returns `{"ok":true}`.
For frontend development run `cd frontend` then `npm run dev` in a second terminal;
Vite proxies API requests to port 8000.

## Provider modes

- **mock** is an explicitly labeled offline demo. It parses text from actual sample
  documents and runs real deterministic rules. It does not read scenario expectations
  to choose outcomes. Image-only evidence needs manual review. The hosted demo cannot
  extract text from arbitrary uploaded PDFs without a real provider.
- **openai** or **anthropic** uses the selected provider for document reading and
  message drafting only. Set the matching API key and `LLM_MODEL` to a model supporting
  document/image input. Every response is schema-validated, retried once on failure,
  then marked for manual review. Real mode never falls back to mock.

Export variables in your shell; `.env.example` is documentation, not auto-loaded.

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `openai`, `anthropic`, or explicit `mock` |
| `LLM_MODEL` | Required provider model in real mode |
| `OPENAI_API_KEY` | OpenAI secret, server only |
| `ANTHROPIC_API_KEY` | Anthropic secret, server only |
| `VENDORGATE_DB_PATH` | Local SQLite file; relative values resolve under backend/ |
| `VENDORGATE_SEED_DIR` | Optional alternative local fixture directory |
| `VITE_API_BASE_URL` | Optional separate backend origin for frontend builds |

No API keys are committed or included in the browser bundle. The current hosted
publication uses mock mode because no provider credential has been configured.
Real provider HTTP requests were not exercised during verification.

## Review workflow

1. Open **New review**, select one of six synthetic scenarios, and start review.
2. Watch the nine stages, each labeled AI or RULE. Expand the audit to inspect input,
   output, settings snapshot, rule version, timestamps and duration.
3. Inspect APPROVED/PENDING/REJECTED, risk indicators, evidence and corrective actions.
4. Edit draft vendor/internal messages. **Record as sent** records an operator action;
   this application does not transmit email. Dispatch the message separately first.
5. Rerun, submit corrected documents, or override a completed decision with a reason.
   Historical stage results and override records are retained.
6. Use Dashboard, Run history, Settings and Assumptions for review and configuration.

Approval means the configured case-study consistency checks passed, not that the
vendor is legally eligible for payment. The sanctions and high-risk lists are
fictional fixtures, not live compliance data.

## Seed fixtures

```powershell
python backend/seed/seed.py --reset
python backend/seed/seed.py --reset --as-of 2026-11-23 --db data/demo.sqlite3 --output-dir tmp/demo-seed
```

20 existing vendors, six scenario forms, 18 document references and 17 unique PDFs.
Seed reset restores the vendor registry and settings but preserves existing reviews
and their audit history. PDFs and all entities/accounts are visibly synthetic.
Documents use W-9, GST, German VAT, incorporation, bank-letter and cheque layouts.
The poor bank scan has noise, rotation, blur and no text layer.

| Scenario | Intended case-study outcome |
| --- | --- |
| S1 Brightline Logistics | APPROVED: complete, consistent US evidence |
| S2 Sundaram Fasteners | PENDING: cheque holder differs without alias evidence |
| S3 Silvercrest Rapid | REJECTED: account reuse from Northwind, recent incorporation |
| S4 Rheinblick | PENDING: wrong-country tax form and unreadable bank scan |
| S5 Rheinblick resubmission | APPROVED: corrected VAT/bank evidence, linked to S4 |
| S6 Configured fictional entity | REJECTED: mock sanctions-list match |

Expected outcomes are fixture metadata, never pipeline outputs. Frozen evidence is
anchored to its generation date; regenerate before a future demo so document-age
rules still apply to fresh evidence. IDs/checksums are structurally valid but are
not registration or ownership verifications. IBAN helpers currently cover DE/GB.

## Tests

```powershell
python -m pytest backend -q
cd frontend
npm run build
cd ../sites/vendorgate
npm ci
python scripts/prepare_fixtures.py
npm test
```

Python tests cover schema/seed/PDF/checksums, all nine pipeline stages, provider
failures and API operations. Hosted tests run the actual Worker API and pipeline
against SQLite through a D1-compatible adapter, including all six scenarios,
uploads, outbox, overrides and settings. Temporary DBs isolate test records.

## ChatGPT Sites deployment

The user approved a JavaScript backend for Sites while retaining the Python stack.
`sites/vendorgate/worker/` implements the same API and deterministic stages. Sites
D1 stores structured records and audit; R2 stores uploads. The React build and sample
PDFs are bundled into the Worker. The Site remains owner-private and uses platform
ChatGPT sign-in. Local FastAPI is a single-user development server.

From the root, after installing frontend and hosted dependencies:

```powershell
npm run build
```

The build prepares `dist/server/index.js` and D1 migrations in `dist/.openai/drizzle/`.
Publication uses the Sites source/save/deploy workflow. Schema changes are generated
with `cd sites/vendorgate` then `npm run db:generate`; never alter applied migrations.
Runtime provider secrets belong in Sites environment configuration, not source.
Hosted queued reviews execute when their SSE stream opens; keep the review open
until completion. Partial audit persists if a request is interrupted; rerun the
review after interruption. No email service is connected.

See AGENTS.md for working rules and API_CONTRACT.md for endpoint definitions.
