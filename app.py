"""
FastAPI backend — serves the Rule Engine over HTTP.

Endpoints:
  GET  /                 — serve the frontend HTML
  POST /analyse          — upload transcript PDF or JSON, get full Report
  POST /analyse/text     — send raw transcript text, get full Report
  POST /analyse/json     — send pre-parsed student record JSON, get full Report
  GET  /catalogue        — return the course catalogue
  GET  /majors           — return all major definitions
  GET  /health           — health check
"""
import dataclasses
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from engine.catalogue import load_catalogue
from engine.parser import parse_transcript_pdf, parse_transcript_text
from engine.rule_engine import compute_report
from engine.models import StudentRecord, CourseResult, Catalogue
from engine.knowledge_graph import KnowledgeGraph
from engine.reasoner import GraduateGoal, HonoursReadinessGoal, CompleteMajorGoal
from engine.simulator import SimulationEngine
from engine.utils import _infer_faculty_key

app = FastAPI(title="CurriculumAdvisor API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_BASE = Path(__file__).parent
_STATIC = _BASE / "static"

# Cache loaded catalogues and graphs
_catalogues: dict[str, Catalogue] = {}
_graphs: dict[str, KnowledgeGraph] = {}


def get_catalogue_and_graph(faculty_key: str) -> tuple[Catalogue, KnowledgeGraph]:
    if faculty_key not in _catalogues:
        try:
            cat = load_catalogue(faculty_key)
            _catalogues[faculty_key] = cat
            _graphs[faculty_key] = KnowledgeGraph(cat)
        except Exception:
            # Fallback to humanities
            if "uct_humanities" not in _catalogues:
                cat = load_catalogue("uct_humanities")
                _catalogues["uct_humanities"] = cat
                _graphs["uct_humanities"] = KnowledgeGraph(cat)
            return _catalogues["uct_humanities"], _graphs["uct_humanities"]
    return _catalogues[faculty_key], _graphs[faculty_key]


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to dicts for JSON serialisation."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, set):
        return list(obj)
    return obj


@app.get("/health")
def health():
    cat, _ = get_catalogue_and_graph("uct_humanities")
    return {"status": "ok", "courses_loaded": len(cat.courses)}


@app.get("/")
def index():
    """Serve the frontend HTML."""
    html_file = _STATIC / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file), media_type="text/html")
    return JSONResponse({"error": "Frontend not found. Run: copy Downloads/app_2.py static/index.html"}, status_code=404)


@app.get("/catalogue")
def get_catalogue():
    cat, _ = get_catalogue_and_graph("uct_humanities")
    return _to_dict(cat.courses)


@app.get("/majors")
def get_majors():
    cat, _ = get_catalogue_and_graph("uct_humanities")
    return _to_dict(cat.majors)


@app.post("/analyse")
async def analyse_pdf(file: UploadFile = File(...)):
    """Upload a UCT transcript PDF and receive a full graduation report."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    import io
    content = await file.read()

    try:
        student = parse_transcript_pdf(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse transcript: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, _ = get_catalogue_and_graph(faculty_key)
    report = compute_report(student, catalogue)
    return JSONResponse(_to_dict(report))


@app.post("/analyse/text")
async def analyse_text(body: dict):
    """Send raw transcript text and receive a full graduation report."""
    text = body.get("text", "")
    if not text.strip():
        raise HTTPException(status_code=400, detail="No transcript text provided.")
    student = parse_transcript_text(text)
    faculty_key = _infer_faculty_key(student.programme)
    catalogue, _ = get_catalogue_and_graph(faculty_key)
    report = compute_report(student, catalogue)
    return JSONResponse(_to_dict(report))


@app.post("/analyse/json")
async def analyse_json(body: dict):
    """
    Send a pre-parsed student record as JSON and receive a full graduation report.
    Useful for the frontend's manual entry mode.

    Expected body:
    {
      "student_id": "NQSLUK001",
      "name": "Lukho Nqose",
      "programme": "Bachelor of Social Science",
      "declared_majors": ["Philosophy", "Politics & Governance"],
      "results": [
        {"code": "PHI1024F", "name": "...", "nqf_level": 5, "nqf_credits": 18, "mark": 57, "grade": "3"}
      ]
    }
    """
    try:
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in body.get("results", [])
        ]
        student = StudentRecord(
            student_id=body.get("student_id", ""),
            name=body.get("name", ""),
            programme=body.get("programme", "Bachelor of Arts"),
            declared_majors=body.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, _ = get_catalogue_and_graph(faculty_key)
    report = compute_report(student, catalogue)
    return JSONResponse(_to_dict(report))


# ---------------------------------------------------------------------------
# Simulation & Reasoning Endpoints
# ---------------------------------------------------------------------------

@app.post("/simulate/fail")
async def simulate_fail(body: dict):
    """
    Simulate failing a course.
    Expected body:
    {
      "student": { ... StudentRecord ... },
      "course_code": "PHI3023F"
    }
    """
    try:
        student_data = body.get("student", {})
        course_code = body.get("course_code", "")
        
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in student_data.get("results", [])
        ]
        student = StudentRecord(
            student_id=student_data.get("student_id", ""),
            name=student_data.get("name", ""),
            programme=student_data.get("programme", "Bachelor of Arts"),
            declared_majors=student_data.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, graph = get_catalogue_and_graph(faculty_key)
    simulator = SimulationEngine(student, catalogue, graph)
    report, blocked = simulator.simulate_fail_course(course_code)
    return JSONResponse({
        "report": _to_dict(report),
        "blocked_courses": blocked
    })


@app.post("/simulate/pass")
async def simulate_pass(body: dict):
    """
    Simulate passing a course.
    Expected body:
    {
      "student": { ... StudentRecord ... },
      "course_code": "PHI3023F",
      "mark": 75
    }
    """
    try:
        student_data = body.get("student", {})
        course_code = body.get("course_code", "")
        mark = body.get("mark", 75)
        
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in student_data.get("results", [])
        ]
        student = StudentRecord(
            student_id=student_data.get("student_id", ""),
            name=student_data.get("name", ""),
            programme=student_data.get("programme", "Bachelor of Arts"),
            declared_majors=student_data.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, graph = get_catalogue_and_graph(faculty_key)
    simulator = SimulationEngine(student, catalogue, graph)
    report = simulator.simulate_pass_course(course_code, mark)
    return JSONResponse(_to_dict(report))


@app.post("/simulate/switch")
async def simulate_switch(body: dict):
    """
    Simulate switching majors.
    Expected body:
    {
      "student": { ... StudentRecord ... },
      "new_majors": ["Philosophy", "Sociology"]
    }
    """
    try:
        student_data = body.get("student", {})
        new_majors = body.get("new_majors", [])
        
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in student_data.get("results", [])
        ]
        student = StudentRecord(
            student_id=student_data.get("student_id", ""),
            name=student_data.get("name", ""),
            programme=student_data.get("programme", "Bachelor of Arts"),
            declared_majors=student_data.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, graph = get_catalogue_and_graph(faculty_key)
    simulator = SimulationEngine(student, catalogue, graph)
    report = simulator.simulate_switch_majors(new_majors)
    return JSONResponse(_to_dict(report))


@app.post("/simulate/semester")
async def simulate_semester(body: dict):
    """
    Simulate taking a set of courses next semester.
    Expected body:
    {
      "student": { ... StudentRecord ... },
      "courses": [["PHI3023F", 75], ["POL3029F", 70]]
    }
    """
    try:
        student_data = body.get("student", {})
        courses_to_take = [(c[0], c[1]) for c in body.get("courses", [])]
        
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in student_data.get("results", [])
        ]
        student = StudentRecord(
            student_id=student_data.get("student_id", ""),
            name=student_data.get("name", ""),
            programme=student_data.get("programme", "Bachelor of Arts"),
            declared_majors=student_data.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    faculty_key = _infer_faculty_key(student.programme)
    catalogue, graph = get_catalogue_and_graph(faculty_key)
    simulator = SimulationEngine(student, catalogue, graph)
    report = simulator.simulate_future_semester(courses_to_take)
    return JSONResponse(_to_dict(report))


@app.post("/goals")
async def evaluate_goals(body: dict):
    """
    Evaluate goals for a student.
    Expected body:
    {
      "student": { ... StudentRecord ... }
    }
    """
    try:
        student_data = body.get("student", {})
        
        results = [
            CourseResult(
                code=r["code"],
                name=r.get("name", ""),
                nqf_level=int(r.get("nqf_level", 5)),
                nqf_credits=int(r.get("nqf_credits", 18)),
                mark=r.get("mark"),
                grade=r.get("grade"),
            )
            for r in student_data.get("results", [])
        ]
        student = StudentRecord(
            student_id=student_data.get("student_id", ""),
            name=student_data.get("name", ""),
            programme=student_data.get("programme", "Bachelor of Arts"),
            declared_majors=student_data.get("declared_majors", []),
            results=results,
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid student record: {e}")

    # Evaluate Graduate Goal
    faculty_key = _infer_faculty_key(student.programme)
    catalogue, graph = get_catalogue_and_graph(faculty_key)
    grad_goal = GraduateGoal(student, catalogue, graph)
    grad_report = grad_goal.evaluate()

    # Evaluate Honours Readiness for each declared major
    honours_reports = []
    for major in student.declared_majors:
        # Normalise major name to key
        from engine.utils import _normalise_major_keys
        norm_keys = _normalise_major_keys([major], catalogue)
        if norm_keys:
            honours_goal = HonoursReadinessGoal(student, catalogue, graph, norm_keys[0])
            honours_reports.append(honours_goal.evaluate())

    return JSONResponse({
        "graduation_goal": _to_dict(grad_report),
        "honours_goals": _to_dict(honours_reports)
    })


@app.get("/dependencies")
def get_dependencies(start: str, end: str, faculty_key: str = "uct_humanities"):
    """Get the dependency path between two courses."""
    _, graph = get_catalogue_and_graph(faculty_key)
    path = graph.get_dependency_path(start.upper(), end.upper())
    return {"path": path}


@app.get("/dependencies/unlocked")
def get_unlocked(course_code: str, faculty_key: str = "uct_humanities"):
    """Get all courses unlocked by passing this course."""
    _, graph = get_catalogue_and_graph(faculty_key)
    unlocked = graph.get_all_unlocked_courses(course_code.upper())
    return {"unlocked": sorted(list(unlocked))}


@app.get("/dependencies/blocked")
def get_blocked(course_code: str, faculty_key: str = "uct_humanities"):
    """Get all courses blocked by failing this course."""
    _, graph = get_catalogue_and_graph(faculty_key)
    blocked = graph.get_blocked_courses({course_code.upper()})
    return {"blocked": sorted(list(blocked))}


@app.get("/debug/student")
def debug_student(faculty_key: str = "uct_ebe"):
    """Debug endpoint to inspect raw parsed student record and catalogue majors."""
    import os
    from pathlib import Path
    from engine.utils import _normalise_major_keys
    
    # Search for the transcript in downloads
    downloads_path = Path(os.environ.get("DEBUG_DOWNLOADS_DIR", "/tmp"))
    pdf_files = list(downloads_path.glob("*.pdf"))
    
    target_pdf = None
    for f in pdf_files:
        if "thapelo" in f.name.lower() or "mapengo" in f.name.lower() or "uct_sr_unoff" in f.name.lower():
            target_pdf = f
            break
            
    if not target_pdf:
        raise HTTPException(status_code=404, detail="Student transcript PDF not found in Downloads.")
        
    try:
        student = parse_transcript_pdf(target_pdf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing transcript: {e}")
        
    cat, _ = get_catalogue_and_graph(faculty_key)
    
    return {
        "transcript_file": target_pdf.name,
        "student_record": _to_dict(student),
        "normalised_majors": _normalise_major_keys(student.declared_majors, cat),
        "catalogue_majors": {k: v.name for k, v in cat.majors.items()}
    }


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
