# CurriculumAdvisor public-release implementation report

**Implementation date:** 1 July 2026  
**Release target:** Railway, single FastAPI instance  
**Architecture retained:** FastAPI + static HTML/CSS/JavaScript + version-controlled JSON catalogues

## Outcome

All software changes identified in the audit have been implemented without a framework rewrite or database introduction. The work focused on academic-state correctness, explicit uncertainty, public-input hardening, privacy, transport security, performance, accessibility, and deployment hygiene.

## Audit-to-implementation mapping

| Audit item | Implementation |
|---|---|
| Stale route data | Central `resetRouteState()` invalidates route, transcript, result, major, course, upload, filter, and pagination state on faculty/programme/pathway changes. |
| Readmission uncertainty | Four explicit display outcomes preserve risk, verified non-risk, provisional non-risk, and unverified status. |
| Major completion hides verification | Completion and rule-authority badges are rendered independently. |
| Course role not route-specific | `ProgrammeScope.course_roles` is returned by the scoped catalogue API and used by the frontend. |
| Upload checked after full read | Uploads are streamed in 64 KB chunks and aborted above 10 MB. |
| PDF blocks event loop | Parsing runs in Starlette's threadpool under a 20-second timeout. |
| History duplication | Navigation explicitly selects push, replace, or no history mutation. |
| Route-load failure state | Route controls remain hidden until all route data loads; failures render inline. |
| Recommendation truncation | The report discloses X of N, groups by role, and offers progressive batches. |
| Misleading completion percentage | Replaced with an X/Y blocking-rules-satisfied indicator. |
| Unbounded public endpoints | Result, major, text, simulation, request-byte, page, object, and extracted-text bounds added. |
| Missing rate limits | Sliding-window per-client limit added to analysis, simulation, and goals POST endpoints. |
| Missing security headers | CSP, no-sniff, anti-framing, referrer, permissions, COOP/CORP, and HTTPS HSTS added. |
| Transcript privacy ambiguity | On-page notice plus `PRIVACY.md`; application logs exclude bodies, queries, and transcript content. |
| Heavy `/faculties` | Endpoint now returns landing metadata only; full context loads after faculty selection. |
| Compression/cache | Gzip, ETags, and public cache directives added to catalogue GET responses; personal reports are no-store. |
| Health probe loads catalogue | `/health` is shallow; `/ready` validates all catalogues separately. |
| Accessibility | Tab semantics, labels, live regions, focus movement, text status distinctions, keyboard tabs, and client validation added. |
| Development/deployment hygiene | Dev requirements, Python pin, Ruff/Bandit config, GitHub Actions, Railway health/restart settings, and one-worker start command added. |
| Inline static assets | CSS and JavaScript moved into `/static/app.css` and `/static/app.js`. |

## Verification completed

- `pytest -q`: **196 passed, plus 19 subtests**.
- Complete route matrix: **192 of 192 scopes** passed `/programme`, `/catalogue`, `/majors`, and empty-record `/analyse/json` smoke checks.
- `ruff check .`: **passed**.
- `bandit -q -r app.py engine`: **passed with no unresolved finding**.
- `node --check static/app.js`: **passed**.
- Application starts successfully under Uvicorn and serves hardened headers.

## Verification limitations

- The local `pip-audit` vulnerability lookup could not resolve PyPI from the isolated implementation environment. The GitHub Actions workflow performs this online check and must pass before production deployment.
- The sandbox's Chromium administrator policy blocked navigation to the local test server. Browser-behaviour regressions are covered by automated source/API tests, but a final manual desktop/mobile acceptance pass should be performed on the Railway preview URL before promoting that deployment.

## Remaining governance requirement

The software is hardened for public traffic, but institutional authority is not a software property. Faculty rule owners must still validate handbook interpretation route by route. Existing unverified scopes remain visibly unverified and cannot produce a falsely definitive conclusion. See `docs/ACADEMIC_VALIDATION_CHECKLIST.md`.
