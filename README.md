# CurriculumAdvisor — UCT Undergraduate 2026

CurriculumAdvisor is a FastAPI website that analyses a UCT transcript only after the student selects an explicit **faculty**, **programme**, and—where required—an explicit **pathway, stream, specialisation or curriculum cohort**.

All six undergraduate faculty destinations are enabled:

- Humanities;
- Engineering & the Built Environment;
- Law;
- Science;
- Health Sciences;
- Commerce.

## Coverage

| Faculty | Routes | Scopes | Course facts | Majors | Structurally verified scopes |
|---|---:|---:|---:|---:|---:|
| Humanities | 24 | 56 | 888 | 42 | 30 |
| EBE | 28 | 40 | 354 | 0 | 14 |
| Law | 4 | 5 | 499 | 0 | 5 |
| Science | 2 | 4 | 241 | 22 | 4 |
| Health Sciences | 14 | 16 | 433 | 0 | 16 |
| Commerce | 71 | 71 | 316 | 0 | 71 |
| **Total** | **143** | **192** | **2,731** | **64** | **140** |

A structurally verified scope means that its static programme references resolve against the catalogue. It does not verify live offerings, admissions, capacity, timetable compatibility, clinical placement, practice hours, professional accreditation, concessions or Senate decisions. The 52 inherited Humanities/EBE scopes marked unverified remain deliberately visible rather than being upgraded without evidence.

## User flow

1. Select the faculty shown on the academic record.
2. Select the exact qualification and plan.
3. Select a required pathway, stream, specialisation or curriculum cohort.
4. Select intended majors only where the qualification uses majors.
5. Supply years registered where known.
6. Upload a transcript.
7. Review completion, progression, awards, course options and verification limits.

## Faculty models

**Humanities** combines flexible BA/BSocSc major structures with prescribed professional, performance, education and arts qualifications.

**EBE** uses prescribed yearly curricula, streams, ASPECT routes, curriculum cohorts, progression thresholds and controlled elective categories.

**Law** uses Preliminary, Intermediate and Final Levels, route-specific sequencing, a research/elective component and non-law curriculum categories.

**Science** uses a flexible BSc with regular/EDP routes, one or more composable majors, course equivalences, Science-credit rules and cohort-specific progression.

**Health Sciences** uses prescribed professional curricula, Fundamentals gateways, academic-year and clinical-stage progression, programme-specific failure thresholds and explicit human-confirmation conditions for clinical and professional evidence.

**Commerce** separates BCom, BBusSci and Advanced Diploma qualifications; standard, augmented and extended routes; named specialisations; first-attempt GPA rules; professional progression gates; and controlled elective pools.

## Conclusion states

- `eligible` — all blocking requirements are complete and verified;
- `not_eligible` — at least one blocking requirement is incomplete;
- `requires_verification` — apparent completion depends on provisional, discretionary, conflicting or unverified evidence.

## Core safety rules

- `AB`, `DPR` and `INC` are failures; `PA`, `UP` and `SP` are passes.
- Every attempt remains visible, but one course code awards credit once.
- Catalogue credits and NQF levels outrank PDF-layout inference.
- Unknown courses are excluded unless the selected route expressly permits an approved/open category.
- One course cannot be allocated to several elective pools unless a rule explicitly permits it.
- Courses outside the selected faculty/programme/pathway cannot leak into positive advice.
- Zero-credit compulsory assessments can satisfy a course requirement without inflating credits.
- Clinical hours, placements, logbooks, professional registration, professional exemptions and Senate/Faculty decisions are not inferred from marks.
- Commerce first-attempt GPA evidence is kept separate from the later attempt that may award credit.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload
```

For tests and security tooling:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
bandit -q -r app.py engine
pip-audit -r requirements.txt
```

Open `http://127.0.0.1:8000`.

## Tests

```bash
python -m pytest -q
```

Current verification: **196 tests passed, plus 19 subtests**. The release also passes Ruff and Bandit source checks; CI performs an online `pip-audit` dependency check.

## Deterministic catalogue builds

```bash
python tools/build_structured_humanities.py
python tools/build_ebe_2026.py
python tools/build_law_2026.py
python tools/build_science_2026.py
python tools/build_health_2026.py
python tools/build_commerce_2026.py
python -m pytest -q
```

Generated JSON catalogues are included. Builder scripts use extracted handbook-text locations configured near the top of each script; the source PDFs themselves are not redistributed inside the repository.

## Main endpoints

- `GET /`
- `GET /faculty/{faculty_key}`
- `GET /health` — shallow process liveness
- `GET /ready` — catalogue readiness
- `GET /faculties` — lightweight landing metadata
- `GET /faculties/{faculty_key}`
- `GET /programme?faculty_key=...&programme_key=...&pathway_key=...`
- `GET /catalogue?faculty_key=...&programme_key=...&pathway_key=...`
- `GET /majors?faculty_key=...&programme_key=...`
- `POST /analyse`
- `POST /analyse/text`
- `POST /analyse/json`
- simulation and goals endpoints

## Source hierarchy

1. The relevant 2026 UCT faculty handbook.
2. The 2026 UCT General Rules and Policies handbook.
3. Current institutional systems and authorised staff for live offerings, capacity, concessions, admissions, clinical placement, professional requirements and registration decisions.

See `HUMANITIES_BUILD.md`, `EBE_BUILD.md`, `LAW_BUILD.md`, `SCIENCE_BUILD.md`, `HEALTH_BUILD.md`, `COMMERCE_BUILD.md`, `DATA_ARCHITECTURE.md` and `ROUTE_MANIFEST.md`.


## Public-release controls

The public release adds route-state invalidation, route-specific course roles, explicit uncertainty language, bounded and streamed PDF processing, input limits, per-client rate limiting, security headers, privacy-preserving logs, ETags, gzip, accessibility semantics, CI checks and Railway health configuration. See:

- `docs/PUBLIC_RELEASE.md` for the implementation and deployment assumptions;
- `PRIVACY.md` for transcript processing and retention;
- `SECURITY.md` for production controls and vulnerability reporting;
- `docs/ACADEMIC_VALIDATION_CHECKLIST.md` for the remaining faculty rule-owner sign-off.

### Production environment

The bundled frontend and API are intended to run on the same origin. Leave `ALLOWED_ORIGINS` empty unless a separately hosted, approved frontend genuinely requires CORS. Keep `RATE_LIMIT_ENABLED=true`. The default public limit is 30 protected analysis/simulation/goal requests per client per 60 seconds.

Railway deployment uses one Uvicorn worker and `/health` as its liveness check. Monitor `/ready` separately. Before adding replicas, move rate limiting to a shared edge or store.
