"""CurriculumAdvisor FastAPI application.

Architecture:
1. The student selects a faculty on the landing page.
2. The faculty destination loads only that faculty's programmes.
3. The student selects a programme before uploading a transcript.
4. Every analysis endpoint builds a programme-scoped catalogue and reasons
   only from that route's prescribed curriculum, pathways, major rules, and
   explicitly represented elective pools.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from engine.catalogue import load_catalogue
from engine.knowledge_graph import KnowledgeGraph
from engine.models import Catalogue, CourseResult, StudentRecord
from engine.parser import TranscriptPdfError, parse_transcript_pdf, parse_transcript_text
from engine.reasoner import GraduateGoal, HonoursReadinessGoal
from engine.rule_engine import compute_report
from engine.scope import ProgrammeScope, build_programme_scope
from engine.simulator import SimulationEngine
from engine.utils import _infer_faculty_key, _infer_programme_key, _normalise_major_keys
from engine.web_security import (
    RequestSizeLimitMiddleware,
    SecurityAndObservabilityMiddleware,
    SlidingWindowRateLimitMiddleware,
)

LOGGER = logging.getLogger("curriculum_advisor")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024
MAX_PDF_PAGES = 60
MAX_PDF_OBJECTS = 20_000
MAX_PDF_TEXT_CHARACTERS = 2_000_000
MAX_JSON_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TRANSCRIPT_TEXT_CHARACTERS = 500_000
MAX_RESULTS = 500
MAX_DECLARED_MAJORS = 10
MAX_SIMULATED_COURSES = 24
PDF_PARSE_TIMEOUT_SECONDS = 20

app = FastAPI(title="CurriculumAdvisor API", version="10.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

app.add_middleware(
    RequestSizeLimitMiddleware,
    upload_limit_bytes=MAX_UPLOAD_REQUEST_BYTES,
    json_limit_bytes=MAX_JSON_REQUEST_BYTES,
)
app.add_middleware(
    SlidingWindowRateLimitMiddleware,
    requests_per_window=int(os.environ.get("RATE_LIMIT_REQUESTS", "30")),
    window_seconds=int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")),
)
app.add_middleware(SecurityAndObservabilityMiddleware)

_BASE = Path(__file__).parent
_STATIC = _BASE / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

FACULTY_META = {
    "uct_commerce": {
        "name": "Commerce",
        "short_name": "Commerce",
        "description": "Business Science, Commerce, Economics, Finance, Accounting and related programmes.",
        "available": True,
    },
    "uct_ebe": {
        "name": "Engineering & the Built Environment",
        "short_name": "EBE",
        "description": "Engineering, architecture, construction, property and geomatics programmes.",
        "available": True,
    },
    "uct_health": {
        "name": "Health Sciences",
        "short_name": "Health Sciences",
        "description": "Medicine, rehabilitation sciences, clinical training and other undergraduate health programmes.",
        "available": True,
    },
    "uct_humanities": {
        "name": "Humanities",
        "short_name": "Humanities",
        "description": "Arts, social sciences, performance, education and related programmes.",
        "available": True,
    },
    "uct_law": {
        "name": "Law",
        "short_name": "Law",
        "description": "Four-year, graduate-entry, combined and continuing-student LLB pathways.",
        "available": True,
    },
    "uct_science": {
        "name": "Science",
        "short_name": "Science",
        "description": "Regular and extended BSc routes across mathematical, computational, physical, earth and life sciences.",
        "available": True,
    },
}
AVAILABLE_FACULTIES = set(FACULTY_META)

# The ingestion catalogue and the programme-scoped catalogue are cached
# separately.  A graph must never be shared across programme boundaries.
_catalogues: dict[str, Catalogue] = {}
_scoped_catalogues: dict[tuple[str, str, str], Catalogue] = {}
_scopes: dict[tuple[str, str, str], ProgrammeScope] = {}
_graphs: dict[tuple[str, str, str], KnowledgeGraph] = {}
_faculty_contexts: dict[str, dict[str, Any]] = {}


def get_catalogue(faculty_key: str) -> Catalogue:
    if faculty_key not in AVAILABLE_FACULTIES:
        raise ValueError(
            f"Unknown faculty catalogue {faculty_key!r}. Expected one of: "
            f"{', '.join(sorted(AVAILABLE_FACULTIES))}."
        )
    if faculty_key not in _catalogues:
        _catalogues[faculty_key] = load_catalogue(faculty_key)
    return _catalogues[faculty_key]


def get_programme_catalogue_and_graph(
    faculty_key: str,
    programme_key: str,
    pathway_key: str = "",
) -> tuple[Catalogue, KnowledgeGraph, ProgrammeScope]:
    cache_key = (faculty_key, programme_key, pathway_key)
    if cache_key not in _scoped_catalogues:
        full_catalogue = get_catalogue(faculty_key)
        scoped, scope = build_programme_scope(
            faculty_key,
            full_catalogue,
            programme_key,
            pathway_key,
        )
        _scoped_catalogues[cache_key] = scoped
        _scopes[cache_key] = scope
        _graphs[cache_key] = KnowledgeGraph(scoped)
    return (
        _scoped_catalogues[cache_key],
        _graphs[cache_key],
        _scopes[cache_key],
    )


def _full_catalogue_or_422(faculty_key: str) -> Catalogue:
    try:
        return get_catalogue(faculty_key)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _scope_or_422(
    faculty_key: str,
    programme_key: str,
    pathway_key: str = "",
) -> tuple[Catalogue, KnowledgeGraph, ProgrammeScope]:
    if not faculty_key:
        raise HTTPException(status_code=422, detail="A faculty selection is required.")
    if faculty_key not in FACULTY_META:
        raise HTTPException(status_code=422, detail="Unknown faculty selection.")
    if not FACULTY_META[faculty_key].get("available", False):
        raise HTTPException(
            status_code=422, detail=f"{FACULTY_META[faculty_key]['name']} is not enabled yet."
        )
    # Validate the faculty before reporting a missing programme so malformed
    # faculty keys cannot hide behind a secondary validation error.
    _full_catalogue_or_422(faculty_key)
    if not programme_key:
        raise HTTPException(status_code=422, detail="A programme selection is required.")
    try:
        return get_programme_catalogue_and_graph(faculty_key, programme_key, pathway_key)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _bounded_text(value: Any, field_name: str, maximum: int) -> str:
    text = str(value or "").strip()
    if len(text) > maximum:
        raise ValueError(f"{field_name} exceeds the {maximum}-character limit.")
    return text


def _student_from_dict(body: dict) -> StudentRecord:
    if not isinstance(body, dict):
        raise ValueError("Student record must be a JSON object.")

    raw_results = body.get("results", [])
    if not isinstance(raw_results, list):
        raise ValueError("results must be a list.")
    if len(raw_results) > MAX_RESULTS:
        raise ValueError(f"results may contain at most {MAX_RESULTS} course records.")

    results: list[CourseResult] = []
    for index, raw in enumerate(raw_results):
        if not isinstance(raw, dict) or not raw.get("code"):
            raise ValueError(f"Result {index + 1} is missing a course code.")
        mark = raw.get("mark")
        if mark is not None:
            mark = int(mark)
            if not 0 <= mark <= 100:
                raise ValueError(f"Result {index + 1} has a mark outside 0-100.")
        nqf_level = int(raw.get("nqf_level", 0))
        nqf_credits = int(raw.get("nqf_credits", 0))
        if not 0 <= nqf_level <= 10:
            raise ValueError(f"Result {index + 1} has an invalid NQF level.")
        if nqf_credits < 0:
            raise ValueError(f"Result {index + 1} has invalid credits.")
        code = _bounded_text(raw["code"], f"Result {index + 1} course code", 20).upper()
        name = _bounded_text(raw.get("name", ""), f"Result {index + 1} course name", 300)
        grade = raw.get("grade")
        if grade is not None:
            grade = _bounded_text(grade, f"Result {index + 1} grade", 30)
        results.append(
            CourseResult(
                code=code,
                name=name,
                nqf_level=nqf_level,
                nqf_credits=nqf_credits,
                mark=mark,
                grade=grade,
                academic_year=(
                    int(raw["academic_year"]) if raw.get("academic_year") not in (None, "") else None
                ),
            )
        )

    declared_majors = body.get("declared_majors", [])
    if not isinstance(declared_majors, list):
        raise ValueError("declared_majors must be a list.")
    if len(declared_majors) > MAX_DECLARED_MAJORS:
        raise ValueError(f"declared_majors may contain at most {MAX_DECLARED_MAJORS} entries.")

    years_registered = (
        int(body["years_registered"]) if body.get("years_registered") not in (None, "") else None
    )
    if years_registered is not None and not 1 <= years_registered <= 20:
        raise ValueError("years_registered must be between 1 and 20.")

    return StudentRecord(
        student_id=_bounded_text(body.get("student_id", ""), "student_id", 50),
        name=_bounded_text(body.get("name", ""), "name", 200),
        programme=_bounded_text(body.get("programme", ""), "programme", 300),
        declared_majors=[
            _bounded_text(major, "declared major", 200) for major in declared_majors if str(major).strip()
        ],
        results=results,
        faculty_key=_bounded_text(body.get("faculty_key", ""), "faculty_key", 80),
        programme_key=_bounded_text(body.get("programme_key", ""), "programme_key", 120),
        pathway_key=_bounded_text(body.get("pathway_key", ""), "pathway_key", 120),
        years_registered=years_registered,
    )


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {key: _to_dict(value) for key, value in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, tuple):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _to_dict(value) for key, value in obj.items()}
    if isinstance(obj, set):
        return sorted(obj)
    return obj


def _cacheable_json(
    request: Request,
    payload: Any,
    *,
    max_age: int = 3600,
) -> Response:
    """Return deterministic JSON with ETag and short public caching."""
    body = json.dumps(
        _to_dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate=86400",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=body,
        media_type="application/json",
        headers=headers,
    )


def _primary_course_role(roles: tuple[str, ...]) -> str:
    for role in ("required", "support", "major_requirement", "elective"):
        if role in roles:
            return role
    return "outside_route"


def _scoped_course_payload(
    catalogue: Catalogue,
    scope: ProgrammeScope,
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for code, course in catalogue.courses.items():
        roles = scope.course_roles.get(code, ("outside_route",))
        row = _to_dict(course)
        row["route_role"] = _primary_course_role(roles)
        row["route_roles"] = list(roles)
        payload[code] = row
    return payload


async def _read_upload_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Transcript PDF exceeds the 10 MB upload limit.",
                )
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


def _parse_public_transcript(content: bytes) -> StudentRecord:
    return parse_transcript_pdf(
        io.BytesIO(content),
        max_pages=MAX_PDF_PAGES,
        max_objects=MAX_PDF_OBJECTS,
        max_text_characters=MAX_PDF_TEXT_CHARACTERS,
        reject_encrypted=True,
    )


def _bind_student_to_scope(
    student: StudentRecord,
    faculty_key: str,
    programme_key: str,
    pathway_key: str,
    catalogue: Catalogue,
) -> StudentRecord:
    """Attach the user's explicit route selections and reject clear mismatches."""
    inferred_faculty = _infer_faculty_key(student.programme) if student.programme else "unknown_faculty"
    if inferred_faculty != "unknown_faculty" and inferred_faculty != faculty_key:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The transcript appears to belong to {inferred_faculty}, but the selected "
                f"destination is {faculty_key}. Return to the faculty page and choose the correct faculty."
            ),
        )

    inferred_programme = _infer_programme_key(student.programme) if student.programme else "unknown_programme"

    # A standard transcript label often states only BA or BSocSc and omits the
    # regular/extended route. Reject a different degree family, but let the
    # student explicitly choose the route when the transcript is silent.
    def _family(key: str) -> str:
        if key.startswith("bsocsc_"):
            return "BSocSc"
        if key.startswith("ba_"):
            return "BA"
        if key.startswith("llb_"):
            return "LLB"
        if key.startswith("bsc_science"):
            return "BSc Science"
        return key

    programme_label = student.programme.lower()
    transcript_explicitly_extended = "extended" in programme_label
    law_route_explicit = faculty_key == "uct_law" and any(
        token in programme_label
        for token in (
            "two-year",
            "2-year",
            "three-year",
            "3-year",
            "four-year",
            "4-year",
            "five-year",
            "5-year",
            "combined",
            "graduate stream",
            "lb002",
            "lb003",
        )
    )
    route_conflict = (
        inferred_programme != "unknown_programme"
        and inferred_programme in get_catalogue(faculty_key).programmes
        and (
            _family(inferred_programme) != _family(programme_key)
            or (transcript_explicitly_extended and inferred_programme != programme_key)
            or (law_route_explicit and inferred_programme != programme_key)
        )
    )
    if route_conflict:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The transcript appears to match programme {inferred_programme!r}, but "
                f"{programme_key!r} was selected. Choose the degree family shown on the transcript."
            ),
        )

    student.faculty_key = faculty_key
    student.programme_key = programme_key
    student.pathway_key = pathway_key
    if not student.programme:
        student.programme = catalogue.programmes[programme_key].name
    return student


def _context_from_body(
    body: dict,
    student: StudentRecord,
) -> tuple[StudentRecord, Catalogue, KnowledgeGraph, ProgrammeScope]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    faculty_key = _bounded_text(
        body.get("faculty") or student.faculty_key or "",
        "faculty",
        80,
    )
    programme_key = _bounded_text(
        body.get("programme_key") or student.programme_key or "",
        "programme_key",
        120,
    )
    pathway_key = _bounded_text(
        body.get("pathway_key") or student.pathway_key or "",
        "pathway_key",
        120,
    )
    catalogue, graph, scope = _scope_or_422(faculty_key, programme_key, pathway_key)
    student = _bind_student_to_scope(student, faculty_key, programme_key, pathway_key, catalogue)
    return student, catalogue, graph, scope


def _faculty_context(faculty_key: str) -> dict[str, Any]:
    if faculty_key not in FACULTY_META:
        raise HTTPException(status_code=404, detail="Unknown faculty.")
    if faculty_key in _faculty_contexts:
        return _faculty_contexts[faculty_key]
    meta = FACULTY_META[faculty_key]
    if not meta.get("available", True):
        return {"key": faculty_key, **meta, "programmes": [], "status": "coming_soon"}
    catalogue = _full_catalogue_or_422(faculty_key)
    programmes = []
    for key, programme in sorted(catalogue.programmes.items(), key=lambda item: item[1].name):
        preview_pathway = programme.default_pathway_key or (next(iter(programme.pathways), ""))
        scoped, _, scope = _scope_or_422(faculty_key, key, preview_pathway)
        programmes.append(
            {
                "key": key,
                "name": programme.name,
                "qualification_codes": programme.qualification_codes,
                "route_type": programme.route_type,
                "programme_type": programme.programme_type,
                "degree_category": programme.degree_category,
                "availability": programme.availability,
                "availability_note": programme.availability_note,
                "minimum_duration_years": programme.minimum_duration_years,
                "maximum_registration_years": programme.maximum_registration_years,
                "minimum_nqf_credits": programme.total_nqf_credits,
                "minimum_nqf_level_7_credits": programme.level_7_nqf_credits,
                "level_credit_requirements": programme.level_credit_requirements,
                "minimum_semester_courses": programme.semester_course_equivalents,
                "minimum_senior_courses": programme.senior_course_equivalents,
                "minimum_humanities_courses": programme.humanities_course_equivalents,
                "required_majors": programme.required_majors,
                "required_humanities_majors": programme.required_humanities_majors,
                "major_count": len(scoped.majors),
                "course_count": len(scoped.courses),
                "elective_count": len(scope.elective_course_codes),
                "scope_status": scope.status,
                "scope_warnings": list(scope.warnings),
                "source": programme.source,
                "pathway_required": programme.pathway_required,
                "default_pathway_key": programme.default_pathway_key,
                "pathways": [
                    {
                        "key": pathway.key,
                        "name": pathway.name,
                        "verification_status": pathway.verification_status,
                        "availability": pathway.availability,
                        "availability_note": pathway.availability_note,
                        "source": pathway.source,
                    }
                    for pathway in sorted(programme.pathways.values(), key=lambda item: item.name)
                ],
                "admission_notes": programme.admission_notes,
                "progression_notes": programme.progression_notes,
                "award_notes": programme.award_notes,
                "majors": [
                    {
                        "key": major.key,
                        "name": major.name,
                        "category": major.qualification,
                        "faculty_owned": major.faculty_owned,
                        "handbook_code": major.handbook_code,
                        "verification_status": major.verification_status,
                        "required_co_majors": major.required_co_majors,
                        "admission_limited": major.admission_limited,
                        "admission_note": major.admission_note,
                        "source": major.source,
                    }
                    for major in sorted(scoped.majors.values(), key=lambda major: major.name)
                ],
            }
        )
    context = {
        "key": faculty_key,
        **meta,
        "status": "available",
        "programmes": programmes,
        "catalogue_version": catalogue.catalogue_version,
        "source": catalogue.source,
        "catalogue_issues": len(catalogue.data_issues),
    }
    _faculty_contexts[faculty_key] = context
    return context


@app.get("/")
def index():
    html_file = _STATIC / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file), media_type="text/html")
    return JSONResponse({"error": "Frontend not found."}, status_code=404)


@app.get("/faculty/{faculty_key}")
def faculty_destination(faculty_key: str):
    if faculty_key not in FACULTY_META:
        raise HTTPException(status_code=404, detail="Unknown faculty.")
    return index()


@app.get("/faculties")
def list_faculties(request: Request):
    payload = [
        {
            "key": key,
            **meta,
            "status": "available" if meta.get("available", False) else "coming_soon",
        }
        for key, meta in FACULTY_META.items()
    ]
    return _cacheable_json(request, payload)


@app.get("/faculties/{faculty_key}")
def faculty_context(request: Request, faculty_key: str):
    return _cacheable_json(request, _faculty_context(faculty_key))


@app.get("/health")
def health():
    """Shallow liveness probe; it deliberately does not load catalogue data."""
    return {
        "status": "ok",
        "service": "CurriculumAdvisor",
        "version": app.version,
    }


@app.get("/ready")
def readiness():
    """Verify that each enabled faculty catalogue can be loaded."""
    loaded: dict[str, dict[str, int]] = {}
    failures: dict[str, str] = {}
    for faculty_key, meta in FACULTY_META.items():
        if not meta.get("available", False):
            continue
        try:
            catalogue = get_catalogue(faculty_key)
            loaded[faculty_key] = {
                "programmes": len(catalogue.programmes),
                "courses": len(catalogue.courses),
                "majors": len(catalogue.majors),
                "catalogue_issues": len(catalogue.data_issues),
            }
        except Exception as exc:
            LOGGER.exception("catalogue_readiness_failed faculty=%s", faculty_key)
            failures[faculty_key] = type(exc).__name__
    status_code = 200 if not failures else 503
    return JSONResponse(
        {
            "status": "ready" if not failures else "not_ready",
            "faculties": loaded,
            "failures": failures,
        },
        status_code=status_code,
    )


@app.get("/catalogue")
def catalogue_view(
    request: Request,
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    catalogue, _, scope = _scope_or_422(faculty_key, programme_key, pathway_key)
    return _cacheable_json(request, _scoped_course_payload(catalogue, scope))


@app.get("/majors")
def majors_view(
    request: Request,
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    catalogue, _, _ = _scope_or_422(faculty_key, programme_key, pathway_key)
    return _cacheable_json(request, catalogue.majors)


@app.get("/programme")
def programme_view(
    request: Request,
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    catalogue, _, scope = _scope_or_422(faculty_key, programme_key, pathway_key)
    programme = catalogue.programmes[programme_key]
    payload = {
        "programme": _to_dict(programme),
        "scope": _to_dict(scope),
        "major_count": len(catalogue.majors),
        "course_count": len(catalogue.courses),
        "verified_major_count": sum(
            1 for major in catalogue.majors.values() if major.verification_status == "verified"
        ),
    }
    return _cacheable_json(request, payload)


@app.post("/analyse")
async def analyse_pdf(
    file: Annotated[UploadFile, File(...)],
    faculty: str = Query(..., min_length=1, max_length=80),
    programme: str = Query(..., min_length=1, max_length=120),
    pathway: str = Query("", max_length=120),
    majors: str = Query("", max_length=1000),
    years_registered: int | None = Query(None, ge=1, le=20),
):
    if not file.filename or len(file.filename) > 255 or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    if file.content_type not in {
        None,
        "",
        "application/pdf",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await _read_upload_limited(file)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if b"%PDF-" not in content[:1024]:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

    parse_started = time.perf_counter()
    try:
        student = await asyncio.wait_for(
            run_in_threadpool(_parse_public_transcript, content),
            timeout=PDF_PARSE_TIMEOUT_SECONDS,
        )
    except TranscriptPdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        LOGGER.warning(
            "transcript_parse_timeout duration_ms=%.1f bytes=%s",
            (time.perf_counter() - parse_started) * 1000,
            len(content),
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "The PDF took too long to process safely. Please export a "
                "fresh, simplified transcript PDF and try again."
            ),
        ) from exc
    except Exception as exc:
        LOGGER.exception(
            "transcript_parse_failed duration_ms=%.1f bytes=%s",
            (time.perf_counter() - parse_started) * 1000,
            len(content),
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "The transcript could not be read reliably. Please download "
                "a fresh UCT transcript PDF and try again."
            ),
        ) from exc

    LOGGER.info(
        "transcript_parse_complete duration_ms=%.1f bytes=%s results=%s",
        (time.perf_counter() - parse_started) * 1000,
        len(content),
        len(student.results),
    )
    if not student.results and not student.student_id:
        raise HTTPException(
            status_code=422, detail="The PDF did not contain recognisable UCT transcript data."
        )

    catalogue, _, _ = _scope_or_422(faculty, programme, pathway)
    student = _bind_student_to_scope(student, faculty, programme, pathway, catalogue)
    selected_majors = [value.strip() for value in majors.split(",") if value.strip()]
    if len(selected_majors) > MAX_DECLARED_MAJORS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_DECLARED_MAJORS} majors may be supplied.",
        )
    if any(len(value) > 200 for value in selected_majors):
        raise HTTPException(status_code=422, detail="A supplied major name is too long.")
    if selected_majors:
        student.declared_majors = selected_majors
    if years_registered is not None:
        student.years_registered = years_registered
    return JSONResponse(_to_dict(compute_report(student, catalogue)))


@app.post("/analyse/text")
async def analyse_text(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    text = str(body.get("text", ""))
    if not text.strip():
        raise HTTPException(status_code=400, detail="No transcript text provided.")
    if len(text) > MAX_TRANSCRIPT_TEXT_CHARACTERS:
        raise HTTPException(
            status_code=413,
            detail=(f"Transcript text exceeds the {MAX_TRANSCRIPT_TEXT_CHARACTERS:,}-character limit."),
        )
    student = parse_transcript_text(text)
    if not student.results and not student.student_id:
        raise HTTPException(
            status_code=422, detail="The text did not contain recognisable UCT transcript data."
        )
    student, catalogue, _, _ = _context_from_body(body, student)
    return JSONResponse(_to_dict(compute_report(student, catalogue)))


@app.post("/analyse/json")
async def analyse_json(body: dict):
    try:
        student = _student_from_dict(body)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, _, _ = _context_from_body(body, student)
    return JSONResponse(_to_dict(compute_report(student, catalogue)))


@app.post("/simulate/fail")
async def simulate_fail(body: dict):
    try:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        student = _student_from_dict(body.get("student", {}))
        course_code = _bounded_text(body.get("course_code", ""), "course_code", 20).upper()
        if not course_code:
            raise ValueError("course_code is required.")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, graph, _ = _context_from_body(body, student)
    try:
        report, blocked = SimulationEngine(student, catalogue, graph).simulate_fail_course(course_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse({"report": _to_dict(report), "blocked_courses": blocked})


@app.post("/simulate/pass")
async def simulate_pass(body: dict):
    try:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        student = _student_from_dict(body.get("student", {}))
        course_code = _bounded_text(body.get("course_code", ""), "course_code", 20).upper()
        mark = int(body.get("mark", 75))
        if not course_code:
            raise ValueError("course_code is required.")
        if not 0 <= mark <= 100:
            raise ValueError("mark must be between 0 and 100.")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, graph, _ = _context_from_body(body, student)
    try:
        report = SimulationEngine(student, catalogue, graph).simulate_pass_course(course_code, mark)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(_to_dict(report))


@app.post("/simulate/switch")
async def simulate_switch(body: dict):
    try:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        student = _student_from_dict(body.get("student", {}))
        new_majors = body.get("new_majors", [])
        if not isinstance(new_majors, list):
            raise ValueError("new_majors must be a list.")
        if len(new_majors) > MAX_DECLARED_MAJORS:
            raise ValueError(f"new_majors may contain at most {MAX_DECLARED_MAJORS} entries.")
        new_majors = [_bounded_text(major, "new major", 200) for major in new_majors if str(major).strip()]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, graph, _ = _context_from_body(body, student)
    return JSONResponse(
        _to_dict(SimulationEngine(student, catalogue, graph).simulate_switch_majors(new_majors))
    )


@app.post("/simulate/semester")
async def simulate_semester(body: dict):
    try:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        student = _student_from_dict(body.get("student", {}))
        courses_to_take = []
        raw_courses = body.get("courses", [])
        if not isinstance(raw_courses, list):
            raise ValueError("courses must be a list.")
        if len(raw_courses) > MAX_SIMULATED_COURSES:
            raise ValueError(f"A simulated semester may contain at most {MAX_SIMULATED_COURSES} courses.")
        for item in raw_courses:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError("Each simulated course must be [course_code, mark].")
            code = _bounded_text(item[0], "simulated course code", 20).upper()
            mark = int(item[1])
            if not code or not 0 <= mark <= 100:
                raise ValueError("Simulated course codes are required and marks must be 0-100.")
            courses_to_take.append((code, mark))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, graph, _ = _context_from_body(body, student)
    try:
        report = SimulationEngine(student, catalogue, graph).simulate_future_semester(courses_to_take)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(_to_dict(report))


@app.post("/goals")
async def evaluate_goals(body: dict):
    try:
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        student = _student_from_dict(body.get("student", {}))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {exc}") from exc
    student, catalogue, graph, _ = _context_from_body(body, student)
    grad_report = GraduateGoal(student, catalogue, graph).evaluate()
    honours_reports = []
    for major in student.declared_majors:
        normalised = _normalise_major_keys([major], catalogue)
        if normalised:
            honours_reports.append(HonoursReadinessGoal(student, catalogue, graph, normalised[0]).evaluate())
    return JSONResponse(
        {
            "graduation_goal": _to_dict(grad_report),
            "honours_goals": _to_dict(honours_reports),
        }
    )


@app.get("/dependencies")
def get_dependencies(
    start: str = Query(..., min_length=1, max_length=20),
    end: str = Query(..., min_length=1, max_length=20),
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    _, graph, _ = _scope_or_422(faculty_key, programme_key, pathway_key)
    return {"path": graph.get_dependency_path(start.upper(), end.upper())}


@app.get("/dependencies/unlocked")
def get_unlocked(
    course_code: str = Query(..., min_length=1, max_length=20),
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    _, graph, _ = _scope_or_422(faculty_key, programme_key, pathway_key)
    return {"unlocked": sorted(graph.get_all_unlocked_courses(course_code.upper()))}


@app.get("/dependencies/blocked")
def get_blocked(
    course_code: str = Query(..., min_length=1, max_length=20),
    faculty_key: str = Query(..., min_length=1, max_length=80),
    programme_key: str = Query(..., min_length=1, max_length=120),
    pathway_key: str = Query("", max_length=120),
):
    _, graph, _ = _scope_or_422(faculty_key, programme_key, pathway_key)
    return {"blocked": sorted(graph.get_blocked_courses({course_code.upper()}))}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app:app",
        # Containers must bind all interfaces; exposure is controlled by the platform proxy.
        host="0.0.0.0",  # nosec B104
        port=port,
        reload=os.environ.get("APP_RELOAD", "false").lower() == "true",
    )
