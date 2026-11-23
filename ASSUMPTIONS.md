# Assumptions

- Task 1 contains setup and fixtures only. `pipeline.py` and `llm.py` are reserved
  modules; stages remain empty. No SSE, extraction, decisions or review UI yet.
- The user explicitly requested synthetic seed data despite the production rule
  against fake pipeline outputs. Fixtures are labeled, use `.example` email domains,
  and never create fabricated runs, stage results or messages.
- The earlier `vendor-review/` demo and archives remain untouched and gitignored.
- Plain `sqlite3` is used. IDs for seed submissions are stable strings S1-S6;
  vendor IDs and other record IDs are integers. JSON is stored as validated JSON text.
- `stage_results` stores the requested `started_at` and `duration_ms`; an end time
  can be derived. No additional audit behavior is implemented in this task.
- Expected statuses in scenarios.json are intended test outcomes for future stages,
  not current app outputs. S2 is pending until the bank-holder alias is evidenced;
  S3 and S6 are rejection cases; S4 is pending; S1/S5 are approval cases.
- All scenario identifiers are structurally valid. S4's W-9 EIN is also well formed;
  its intentional defect is the wrong jurisdiction, not a broken number. Fixture
  checksums do not establish real registration, authenticity or bank ownership.
- GSTIN checksum and PAN-shaped body are checked. EIN/IFSC have no checksum.
  IBAN validation covers DE and GB international checksums and format only; it does
  not verify bank-directory entries or domestic account checks. German VAT uses
  MOD 11,10. UK seed vendors have no tax ID rather than an unverified invented one.
- UK is a required-doc configuration key; GB maps to UK. EU is a fallback policy
  group with listed member codes. `other` is the remaining-country policy.
- High-risk jurisdiction codes XZ/XY/XQ and all 15 sanctions names are fictional.
  They are not live compliance datasets. The free-mail list is an illustrative default.
- Threshold boundaries: review band includes 0.65 and excludes 0.85; risk score bands
  assume integers to avoid gaps between 30/31 and 60/61.
- S3's incorporation date is 30 days before the seed reference date. UTC today is
  the default; `--as-of` pins replay. The checked-in snapshot uses 2026-11-23.
- Seed reset clears all data in the selected development database. Tests always use
  temporary databases and fixture folders. Normal startup preserves settings.
- The frontend has no backend connection yet and displays only VendorGate, as asked.
- Credentials are read from exported environment variables in future tasks; no
  dotenv loading or provider dependency is needed for Task 1.

## Complete application and hosted implementation

- The latest user request authorizes completing the full pipeline/UI, superseding
  Task 1-only scope. The user explicitly approved adding a JavaScript backend for
  ChatGPT Sites while retaining Python/FastAPI in this repository.
- The current hosted Site is owner-private. Its platform access boundary protects
  shared single-owner review records. Local FastAPI remains a development server.
- D1 stores hosted relational records and R2 stores uploaded document bytes. The
  hosted Worker bundles the React app and synthetic PDF fixtures.
- Hosted and local APIs share API_CONTRACT.md. Hosted pipeline execution is attached
  to an open SSE request; interrupted runs can be rerun and retain partial audit.
- No provider key was supplied. Publication uses explicit mock mode. Real vision
  requires a configured provider key and model; missing credentials never trigger
  a silent mock fallback. Real provider requests have not been exercised in tests.
- Mock mode reads actual fixture text, not scenario IDs or expected decisions.
  Image-only evidence requests manual review; custom hosted PDFs/images need a real
  provider. All LLM outputs are schema-validated before use, with one retry.
- Seed reset now restores only existing vendors and settings, preserving reviews,
  documents, runs and overrides. This supersedes the initial reset-clears-all note.
- Current policy keys are required_docs, sanctions_list, new_company_days, and UK
  maps to GB. High-risk codes XZ/XY/XW are fictional. These supersede earlier key
  assumptions written before the foundation configuration was reconciled.
- Manual outbox delivery is an operator acknowledgement only. The app never claims
  to have transmitted email; the operator dispatches messages separately.
- Scenario evidence is a dated snapshot. Reseed/rebuild for future demonstrations
  rather than altering submitted dates independently of the actual document bytes.
- A failure in message drafting or audit can change the final decision to PENDING
  even if the historical stage-7 result was APPROVED; final status is recomputed.
- Dashboard time savings are illustrative only when a configured baseline is used;
  no measured business saving is claimed. Hosted implementation will expose a note.
