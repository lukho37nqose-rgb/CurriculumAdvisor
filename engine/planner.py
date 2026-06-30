"""
Planner — computes the optimal next courses to register for.

Given a student's current state, recommends which courses to take
next to make progress toward graduation and major completion.
Uses backward chaining: start from graduation goal, work backwards
to find what's needed now.
"""
from dataclasses import dataclass
from .models import StudentRecord, Catalogue, MajorDefinition
from .rule_engine import _prereqs_met, _is_senior, _course_weight


@dataclass
class CourseRecommendation:
    code: str
    name: str
    department: str
    offered: list[str]
    credits: int
    reason: str          # Why this course is recommended
    priority: int        # 1=critical (required for major), 2=important, 3=optional


def plan_next_semester(
    student: StudentRecord,
    catalogue: Catalogue,
    semester: str = "Semester 1",  # "Semester 1", "Semester 2", or "Full Year"
    max_courses: int = 4,
) -> list[CourseRecommendation]:
    """
    Recommend courses for the next semester using backward chaining.

    Priority order:
    1. Required courses for declared majors (prerequisites met)
    2. Choice group courses for declared majors (prerequisites met)
    3. Any senior course to meet senior-course requirement
    4. Any available course to meet total-course requirement
    """
    from .rule_engine import _normalise_major_keys

    passed = student.passed_codes()
    major_keys = _normalise_major_keys(student.declared_majors, catalogue)

    recommendations: list[CourseRecommendation] = []
    seen_codes: set[str] = set()

    def add(code: str, reason: str, priority: int) -> None:
        if code in seen_codes or code in passed:
            return
        course = catalogue.courses.get(code)
        if not course:
            return
        if not _prereqs_met(course, passed):
            return
        # Filter by semester offering
        if semester != "Any" and not any(
            semester.lower() in o.lower() or "full year" in o.lower() or "year" in o.lower()
            for o in course.offered
        ):
            return
        seen_codes.add(code)
        recommendations.append(CourseRecommendation(
            code=code,
            name=course.name,
            department=course.department,
            offered=course.offered,
            credits=course.nqf_credits,
            reason=reason,
            priority=priority,
        ))

    # --- Priority 1: Required courses for majors ---
    for key in major_keys:
        major_def = catalogue.majors.get(key)
        if not major_def:
            continue
        for code in major_def.required_courses:
            if code not in passed:
                add(code, f"Required for {major_def.name} major", 1)

    # --- Priority 2: Choice group courses for majors ---
    for key in major_keys:
        major_def = catalogue.majors.get(key)
        if not major_def:
            continue
        for group in major_def.choice_groups:
            satisfied = [c for c in group.courses if c in passed]
            if len(satisfied) < group.required:
                for code in group.courses:
                    add(code, f"{group.label} ({major_def.name} major)", 2)

    # --- Priority 3: Senior courses to meet senior-course requirement ---
    senior_passed = sum(
        _course_weight(c) for c in passed if _is_senior(c)
    )
    if senior_passed < 10:
        for code, course in catalogue.courses.items():
            if _is_senior(code) and code not in passed:
                add(code, "Counts toward senior-course requirement (10 needed)", 3)

    # --- Priority 4: Any available course ---
    for code, course in catalogue.courses.items():
        add(code, "Available elective", 4)

    # Sort by priority, then by course code
    recommendations.sort(key=lambda r: (r.priority, r.code))
    return recommendations[:max_courses]


def explain_requirement(
    requirement_id: str,
    student: StudentRecord,
    catalogue: Catalogue,
) -> str:
    """
    Backward-chaining explanation: given a requirement that is NOT met,
    explain what the student needs to do to satisfy it.
    """
    from .rule_engine import _normalise_major_keys, _course_weight, _is_senior

    passed = student.passed_codes()
    major_keys = _normalise_major_keys(student.declared_majors, catalogue)

    if requirement_id == "credits":
        completed = sum(
            r.nqf_credits for r in student.results
            if r.mark is not None and r.mark >= 50
        )
        needed = 360 - completed
        return (
            f"You need {needed} more NQF credits. "
            f"1000-level courses give 18 credits, 2000-level give 24, 3000-level give 30."
        )

    if requirement_id == "senior":
        senior_done = sum(_course_weight(c) for c in passed if _is_senior(c))
        needed = 10 - senior_done
        return (
            f"You need {needed:.1f} more senior (2000/3000-level) semester-course equivalents. "
            f"Register for 2000- or 3000-level courses."
        )

    if requirement_id == "majors":
        lines = []
        for key in major_keys:
            major_def = catalogue.majors.get(key)
            if not major_def:
                continue
            outstanding = []
            for code in major_def.required_courses:
                if code not in passed:
                    outstanding.append(code)
            for group in major_def.choice_groups:
                satisfied = [c for c in group.courses if c in passed]
                if len(satisfied) < group.required:
                    outstanding.append(
                        f"{group.required - len(satisfied)} from {group.label}"
                    )
            if outstanding:
                lines.append(f"{major_def.name}: still need {', '.join(outstanding)}")
        return "\n".join(lines) if lines else "Both majors are complete."

    if requirement_id == "level7":
        level7_done = sum(
            r.nqf_credits for r in student.results
            if r.mark is not None and r.mark >= 50 and r.nqf_level == 7
        )
        needed = 120 - level7_done
        return (
            f"You need {needed} more NQF Level 7 credits. "
            f"These come from 3000-level courses (30 credits each). "
            f"You need at least {needed // 30} more 3000-level courses."
        )

    return f"Requirement '{requirement_id}' is not yet met. See your faculty advisor for details."
