# CurriculumAdvisor public-release hardening

This release implements the software changes identified in the 1 July 2026 audit while retaining the existing FastAPI, static frontend, JSON catalogue, and database-free architecture.

## Implemented controls

### Academic correctness and interface state

- Faculty, programme, and pathway changes invalidate transcript, report, course, major, upload, filter, and pagination state.
- Upload controls become available only after the selected route has loaded successfully.
- Readmission output distinguishes identified risk, assessed non-risk, provisional non-risk, and an unverified position.
- Major completion and rule-authority status are displayed independently.
- Course badges use route-specific roles supplied by the backend rather than a faculty-wide elective flag.
- The report presents blocking rules as an `X/Y` count rather than a misleading degree-completion percentage.
- Recommendations disclose the total, group courses by route role, and progressively reveal additional results.
- Browser history uses push, replace, or no mutation according to the navigation context.
- Network and validation failures are shown inline and announced to assistive technology.

### Public-input boundaries

- Multipart uploads are read in chunks and stopped at 10 MB.
- PDFs are limited to 60 pages, 20,000 indirect objects, and 2,000,000 extracted text characters.
- Encrypted PDFs and non-PDF payloads are rejected with stable user-facing errors.
- PDF parsing runs in a threadpool and is bounded by a 20-second application timeout.
- Transcript text is limited to 500,000 characters.
- JSON transcript results are limited to 500 entries and 10 declared majors.
- Simulations are limited to 24 proposed courses.
- Protected POST endpoints use a per-client sliding-window rate limit.
- Analysis, simulation, and goals responses are marked `no-store`.

### Browser and transport controls

- Content Security Policy, anti-framing, MIME-sniffing, referrer, permissions, opener, and resource-policy headers are applied.
- HSTS is applied when the request reaches the app as HTTPS.
- CORS is disabled by default and can be enabled only for explicit origins through `ALLOWED_ORIGINS`.
- Gzip is enabled for responses larger than 1,000 bytes.
- Catalogue GET responses include ETags and public cache directives; personalised analysis responses are never cached.
- `/health` is a shallow liveness probe and `/ready` validates catalogue loading.

### Privacy and observability

- Uploaded transcript bytes and extracted transcript content are not persisted by the application.
- Request bodies and query strings are excluded from application request logs.
- Logs contain request ID, method, path, status, duration, upload byte count, parsing duration, and result count only.
- The frontend explains the in-memory processing and non-retention behaviour before upload.

### Engineering controls

- Runtime and development requirements are separated.
- Python 3.13 is pinned.
- GitHub Actions runs tests, Ruff, Bandit, and `pip-audit` before reviewed changes merge.
- Railway uses one Uvicorn worker, proxy-header support, a liveness health check, and restart controls.
- Regression tests cover the new public-release boundaries.

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `RATE_LIMIT_ENABLED` | `true` | Disable only in controlled test environments. |
| `RATE_LIMIT_REQUESTS` | `30` | Protected POST requests allowed per client per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding-window duration. |
| `ALLOWED_ORIGINS` | empty | Comma-separated approved cross-origin frontend origins. Leave empty for same-origin production. |

## Deployment assumptions

The built-in limiter is deliberately suitable for the recommended single-instance Railway deployment. Before adding replicas, replace it with an edge or shared-store limiter so one client cannot obtain a separate allowance from every instance.

The application enforces body limits even when requests are chunked. Where the hosting provider or an upstream WAF supports an additional request-body cap, set it slightly above 10 MB so multipart overhead is accepted but oversized payloads are rejected before reaching Python.

## Verification boundary

Software tests can prove that encoded rules are internally consistent and that the interface preserves uncertainty. They cannot prove that every handbook interpretation is institutionally authoritative. The 52 inherited Humanities/EBE scopes already marked unverified remain visibly unverified. Public wording must not represent the service as replacing Faculty, Senate, clinical, professional, admissions, capacity, timetable, concession, or live registration decisions.
