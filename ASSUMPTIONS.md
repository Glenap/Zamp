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
