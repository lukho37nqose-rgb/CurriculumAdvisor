"""
Catalogue loader — reads raw JSON facts into typed models.
No logic, no conclusions. Just structured data.
"""
import json
from pathlib import Path
from .models import (
    Catalogue, CourseFact, MajorDefinition, ChoiceGroup,
    ProgrammeRules
)

_BASE = Path(__file__).parent.parent  # workspace root


def _nqf_level_from_code(code: str) -> int:
    """Infer NQF level from course code year digit."""
    for ch in code:
        if ch.isdigit():
            year = int(ch)
            if year == 1:
                return 5
            elif year == 2:
                return 6
            elif year == 3:
                return 7
    return 5  # fallback


def load_catalogue(
    faculty_key: str = "uct_humanities",
    courses_path: Path | None = None,
    requirements_path: Path | None = None,
) -> Catalogue:
    data_dir = _BASE / "data" / faculty_key
    courses_path = courses_path or data_dir / "courses.json"
    requirements_path = requirements_path or data_dir / "degree_requirements.json"

    with open(courses_path, encoding="utf-8") as f:
        raw_courses = json.load(f)

    with open(requirements_path, encoding="utf-8") as f:
        raw_reqs = json.load(f)

    # --- Courses ---
    courses: dict[str, CourseFact] = {}
    for c in raw_courses:
        code = c["code"]
        # Determine NQF level from code if not stored
        nqf_level = _nqf_level_from_code(code)
        # Credits: 1000-level=18, 2000-level=24, 3000-level=30
        nqf_credits = c.get("credits", {18: 18, 5: 18, 6: 24, 7: 30}.get(nqf_level, 18))
        if isinstance(nqf_credits, dict):
            nqf_credits = 18
        courses[code] = CourseFact(
            code=code,
            name=c.get("name", ""),
            nqf_credits=int(nqf_credits),
            nqf_level=nqf_level,
            prerequisites=c.get("prerequisites", []),
            offered=c.get("offered", []),
            department=c.get("department", ""),
            description=c.get("description", ""),
        )

    # --- Majors ---
    majors: dict[str, MajorDefinition] = {}
    for key, m in raw_reqs.get("majors", {}).items():
        choice_groups = []
        for g in m.get("choice_groups", []):
            choice_groups.append(ChoiceGroup(
                label=g.get("name", g.get("label", "")),
                required=g.get("choose", g.get("required", 1)),
                courses=g.get("courses", []),
            ))
        majors[key] = MajorDefinition(
            key=key,
            name=m.get("name", key),
            qualification=m.get("qualification", "BA"),
            required_courses=m.get("required_courses", []),
            choice_groups=choice_groups,
        )

    # --- Programmes ---
    programmes: dict[str, ProgrammeRules] = {}
    for key, p in raw_reqs.get("programmes", {}).items():
        programmes[key] = ProgrammeRules(
            key=key,
            name=p.get("name", key),
            total_nqf_credits=p.get("minimum_nqf_credits", p.get("total_nqf_credits", 360)),
            level_7_nqf_credits=p.get("minimum_nqf_level_7_credits", p.get("level_7_nqf_credits", 120)),
            semester_course_equivalents=p.get("minimum_semester_courses", p.get("semester_course_equivalents", 20)),
            senior_course_equivalents=p.get("minimum_senior_semester_courses", p.get("senior_course_equivalents", 10)),
            humanities_course_equivalents=p.get("minimum_humanities_semester_courses", p.get("humanities_course_equivalents", 12)),
            required_majors=p.get("minimum_majors", p.get("required_majors", 2)),
            required_humanities_majors=p.get("minimum_humanities_majors", p.get("required_humanities_majors", 1)),
            max_courses_per_semester=p.get("max_courses_per_semester"),
            required_courses=p.get("required_courses", []),
        )

    # --- Forbidden combinations ---
    forbidden: list[tuple[str, str]] = []
    for pair in raw_reqs.get("forbidden_major_combinations", []):
        if isinstance(pair, list) and len(pair) == 2:
            forbidden.append((pair[0], pair[1]))

    return Catalogue(
        courses=courses,
        majors=majors,
        programmes=programmes,
        forbidden_combinations=forbidden,
    )
