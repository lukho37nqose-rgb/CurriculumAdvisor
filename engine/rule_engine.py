"""
Rule Engine — the core of CurriculumAdvisor.

"Store facts, compute views."

This module takes raw facts (StudentRecord + Catalogue) and computes
everything: graduation eligibility, major progress, eligible courses,
exclusion risk, distinction eligibility, and warnings.

No conclusions are stored in the JSON. Everything is derived here.
"""
from dataclasses import dataclass, field
from typing import Optional
from .models import StudentRecord, Catalogue, MajorDefinition, CourseFact
from .reasoning import Evidence, build_major_completion_graph, build_total_nqf_credits_graph, ReasoningGraph, build_credit_reasoning_graph
from .utils import _course_weight, _is_senior, _is_humanities, _normalise_major_keys, _infer_programme_key


# ---------------------------------------------------------------------------
# Output types — these are the "views" computed from facts
# ---------------------------------------------------------------------------

@dataclass
class Requirement:
    id: str
    label: str
    complete: bool
    current: float
    required: float
    detail: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    explanation: str = ""
    status: str = "verified"
    confidence: float = 1.0
    assumptions: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class MajorProgress:
    key: str
    name: str
    complete: bool
    completed_requirements: list[str]
    outstanding_requirements: list[str]


@dataclass
class EligibleCourse:
    code: str
    name: str
    credits: int
    department: str
    offered: list[str]
    is_major_requirement: bool = False
    major_key: Optional[str] = None
    major_name: Optional[str] = None
    reason: str = ""


@dataclass
class ExclusionRisk:
    at_risk: bool
    reasons: list[str]


@dataclass
class SubjectDistinction:
    major: str
    average: float
    senior_courses_assessed: int


@dataclass
class Distinction:
    qualification_eligible: bool
    provisional: bool
    subjects: list[SubjectDistinction]


@dataclass
class Report:
    """The complete computed view for a student. Matches the app_2.py DEMO contract."""
    graduation_eligible: bool
    credits_completed: int
    level_7_credits: int
    semester_course_equivalents: float
    requirements: list[Requirement]
    majors: list[MajorProgress]
    eligible_courses: list[EligibleCourse]
    exclusion_risk: ExclusionRisk
    distinction: Distinction
    warnings: list[str]
    failed_attempts: dict[str, int]   # code -> number of failures
    student_name: str = ""            # for display in the UI


# ---------------------------------------------------------------------------
# Major progress computation
# ---------------------------------------------------------------------------

def _compute_major_progress(
    major_def: MajorDefinition,
    student: StudentRecord,
    base_graph: Optional[ReasoningGraph] = None,
) -> MajorProgress:
    completed_reqs: list[str] = []
    outstanding_reqs: list[str] = []
    graph = build_major_completion_graph(student, major_def, base_graph)

    # Required courses
    for code in major_def.required_courses:
        requirement = graph.conclusions[f"major_required_course:{major_def.key}:{code}"]
        if requirement.result:
            completed_reqs.append(f"Pass {code}")
        else:
            outstanding_reqs.append(f"Pass {code}")

    # Choice groups
    for index, group in enumerate(major_def.choice_groups):
        requirement = graph.conclusions[f"major_choice_group:{major_def.key}:{index}"]
        satisfied = int(requirement.current)
        needed = group.required
        label = group.label or "Elective"
        if requirement.result:
            completed_reqs.append(f"{label}: {satisfied}/{needed}")
        else:
            outstanding_reqs.append(
                f"{label}: {satisfied}/{needed} - need {needed - satisfied} more from {group.courses}"
            )

    complete = graph.conclusions[f"major_complete:{major_def.key}"].result
    return MajorProgress(
        key=major_def.key,
        name=major_def.name,
        complete=complete,
        completed_requirements=completed_reqs,
        outstanding_requirements=outstanding_reqs,
    )


# ---------------------------------------------------------------------------
# Eligible courses computation (prerequisites met, not yet passed)
# ---------------------------------------------------------------------------

def _prereqs_met(course: CourseFact, passed: set[str]) -> bool:
    return all(p in passed for p in course.prerequisites)


def _compute_eligible_courses(
    student: StudentRecord,
    catalogue: Catalogue,
) -> list[EligibleCourse]:
    passed = student.passed_codes()
    major_keys = _normalise_major_keys(student.declared_majors, catalogue)

    major_defs = []
    for m_key in major_keys:
        m_def = catalogue.majors.get(m_key)
        if m_def:
            major_defs.append((m_key, m_def))

    eligible = []
    for code, course in catalogue.courses.items():
        if code in passed:
            continue  # already passed
        if not _prereqs_met(course, passed):
            continue  # prerequisites not met

        # Check if it belongs to any declared major
        is_major = False
        major_key = None
        major_name = None
        reason = ""

        for m_key, m_def in major_defs:
            if code in m_def.required_courses:
                is_major = True
                major_key = m_key
                major_name = m_def.name
                reason = f"Required for {m_def.name} major"
                break
            
            # Check choice groups
            for group in m_def.choice_groups:
                if code in group.courses:
                    is_major = True
                    major_key = m_key
                    major_name = m_def.name
                    reason = f"{group.label} ({m_def.name} major), pick {group.required}"
                    break
            if is_major:
                break

        eligible.append(EligibleCourse(
            code=code,
            name=course.name,
            credits=course.nqf_credits,
            department=course.department,
            offered=course.offered,
            is_major_requirement=is_major,
            major_key=major_key,
            major_name=major_name,
            reason=reason,
        ))

    # Sort: major requirements first, then senior courses, then alphabetically
    eligible.sort(key=lambda c: (not c.is_major_requirement, not _is_senior(c.code), c.code))
    return eligible


# ---------------------------------------------------------------------------
# Exclusion risk
# ---------------------------------------------------------------------------

def _compute_exclusion_risk(
    student: StudentRecord,
    catalogue: Catalogue,
    programme_key: str,
) -> ExclusionRisk:
    """
    Check UCT readmission minimums.
    We infer the student's year from how many courses they've attempted.
    """
    prog = catalogue.programmes.get(programme_key)
    if not prog:
        return ExclusionRisk(at_risk=False, reasons=[])

    passed = student.passed_codes()
    passed_count = len(passed)
    senior_passed = 0
    for c in passed:
        if _is_senior(c):
            senior_passed += 1

    # Infer year from number of courses attempted (rough heuristic)
    attempted = len(student.attempted_codes())
    if attempted <= 8:
        year = 1
    elif attempted <= 16:
        year = 2
    elif attempted <= 24:
        year = 3
    else:
        year = 4

    reasons = []

    # Readmission minimums from degree_requirements.json
    readmission_table = {
        "regular_ba_bsocsc": [
            (1, 5, 0),
            (2, 9, 0),
            (3, 13, 2),
        ],
        "extended_ba_bsocsc": [
            (1, 4, 0),
            (2, 8, 0),
            (3, 12, 2),
            (4, 15, 4),
        ],
    }

    for (req_year, min_passed, min_senior) in readmission_table.get(programme_key, []):
        if year >= req_year:
            if passed_count < min_passed:
                reasons.append(
                    f"By end of year {req_year}: need {min_passed} passed courses, "
                    f"have {passed_count}"
                )
            if min_senior > 0 and senior_passed < min_senior:
                reasons.append(
                    f"By end of year {req_year}: need {min_senior} senior courses passed, "
                    f"have {senior_passed}"
                )

    return ExclusionRisk(at_risk=len(reasons) > 0, reasons=reasons)


# ---------------------------------------------------------------------------
# Distinction computation
# ---------------------------------------------------------------------------

def _compute_distinction(
    student: StudentRecord,
    catalogue: Catalogue,
    major_keys: list[str],
) -> Distinction:
    """
    UCT distinction: 75%+ average across all senior courses in a major.
    Provisional if not all senior courses have been completed yet.
    """
    subjects: list[SubjectDistinction] = []
    qualification_eligible = True
    is_provisional = False

    for key in major_keys:
        major_def = catalogue.majors.get(key)
        if not major_def:
            continue

        # Collect all senior courses for this major
        senior_codes = set()
        for code in major_def.required_courses:
            if _is_senior(code):
                senior_codes.add(code)
        for group in major_def.choice_groups:
            for code in group.courses:
                if _is_senior(code):
                    senior_codes.add(code)

        # Get marks for senior courses the student has results for
        marks = []
        for code in senior_codes:
            result = student.result_for(code)
            if result and result.mark is not None:
                marks.append(result.mark)

        if not marks:
            qualification_eligible = False
            continue

        avg = sum(marks) / len(marks)
        if len(marks) < len(senior_codes):
            is_provisional = True
            
        if avg < 75:
            qualification_eligible = False

        subjects.append(SubjectDistinction(
            major=major_def.name,
            average=round(avg, 1),
            senior_courses_assessed=len(marks),
        ))

    return Distinction(
        qualification_eligible=qualification_eligible and len(subjects) > 0,
        provisional=is_provisional,
        subjects=subjects,
    )


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

def _compute_warnings(
    student: StudentRecord,
    catalogue: Catalogue,
    major_keys: list[str],
) -> list[str]:
    warnings = []
    passed = student.passed_codes()

    # Warn about failed courses
    for result in student.results:
        if result.mark is not None and result.mark < 50:
            warnings.append(
                f"{result.code} ({result.name}): failed with {result.mark}% — "
                "you may need to repeat this course."
            )

    # Warn about forbidden major combinations
    for (a, b) in catalogue.forbidden_combinations:
        if a in major_keys and b in major_keys:
            warnings.append(
                f"Forbidden major combination: {a} and {b} cannot be taken together."
            )

    # Warn if declared majors not in catalogue
    for key in major_keys:
        if key not in catalogue.majors:
            warnings.append(
                f"Major '{key}' is not in the course catalogue. "
                "Check spelling or contact your faculty advisor."
            )

    return warnings


# ---------------------------------------------------------------------------
# Failed attempts tracking
# ---------------------------------------------------------------------------

def _compute_failed_attempts(student: StudentRecord) -> dict[str, int]:
    """Count how many times each course was failed."""
    counts: dict[str, int] = {}
    for result in student.results:
        if result.mark is not None and result.mark < 50:
            counts[result.code] = counts.get(result.code, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Programme key inference
# ---------------------------------------------------------------------------

# Imported from utils


# ---------------------------------------------------------------------------
# Major key normalisation
# ---------------------------------------------------------------------------

# Imported from utils


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _compute_credits(student: StudentRecord) -> tuple[int, int]:
    credits_completed = sum(
        r.nqf_credits for r in student.results
        if r.mark is not None and r.mark >= 50
    )
    level_7_credits = sum(
        r.nqf_credits for r in student.results
        if r.mark is not None and r.mark >= 50 and r.nqf_level == 7
    )
    return credits_completed, level_7_credits


def _compute_course_equivalents(student: StudentRecord, catalogue: Catalogue) -> tuple[float, float, float]:
    sce_total = sum(
        _course_weight(r.code)
        for r in student.results
        if r.mark is not None and r.mark >= 50
    )
    senior_sce = sum(
        _course_weight(r.code)
        for r in student.results
        if r.mark is not None and r.mark >= 50 and _is_senior(r.code)
    )
    humanities_sce = sum(
        _course_weight(r.code)
        for r in student.results
        if r.mark is not None and r.mark >= 50 and _is_humanities(r.code, catalogue)
    )
    return sce_total, senior_sce, humanities_sce


def _compute_all_major_progresses(student: StudentRecord, catalogue: Catalogue, major_keys: list[str]) -> tuple[list[MajorProgress], int, int]:
    major_progresses = []
    base_graph = None
    for key in major_keys:
        major_def = catalogue.majors.get(key)
        if major_def:
            if base_graph is None:
                base_graph = build_credit_reasoning_graph(student)
            major_progresses.append(_compute_major_progress(major_def, student, base_graph))

    majors_complete = sum(1 for m in major_progresses if m.complete)
    humanities_majors_complete = sum(
        1 for m in major_progresses
        if m.complete and catalogue.majors.get(m.key) and
        catalogue.majors[m.key].qualification in ("BA", "BSocSc")
    )
    return major_progresses, majors_complete, humanities_majors_complete


def _check_forbidden_combinations(catalogue: Catalogue, major_keys: list[str]) -> bool:
    for (a, b) in catalogue.forbidden_combinations:
        if a in major_keys and b in major_keys:
            return False
    return True


def _build_requirements(
    student: StudentRecord,
    catalogue: Catalogue,
    programme_key: str,
    prog,
    sce_total: float,
    senior_sce: float,
    humanities_sce: float,
    credits_completed: int,
    level_7_credits: int,
    majors_complete: int,
    humanities_majors_complete: int,
    forbidden_ok: bool
) -> list[Requirement]:
    # We infer years from the number of courses attempted
    attempted_count = len(student.attempted_codes())
    inferred_years = max(1, (attempted_count + 7) // 8)  # ~8 courses/year
    
    # Fallback values if programme rules are not found
    min_years = 3
    total_nqf_credits = 360
    level_7_nqf_credits = 120
    semester_course_equivalents = 20
    senior_course_equivalents = 10
    humanities_course_equivalents = 12
    required_majors = 2
    required_humanities_majors = 1

    if prog:
        min_years = 4 if "extended" in prog.key or "augmented" in prog.key or prog.key == "bsw" else 3
        total_nqf_credits = prog.total_nqf_credits
        level_7_nqf_credits = prog.level_7_nqf_credits
        semester_course_equivalents = prog.semester_course_equivalents
        senior_course_equivalents = prog.senior_course_equivalents
        humanities_course_equivalents = prog.humanities_course_equivalents
        required_majors = prog.required_majors
        required_humanities_majors = prog.required_humanities_majors

    duration_ok = inferred_years >= min_years
    programme_name = prog.name if prog else programme_key
    total_credits_graph = build_total_nqf_credits_graph(
        student=student,
        required_credits=total_nqf_credits,
        programme_key=programme_key,
        programme_name=programme_name,
        assumptions=["Programme rules inferred from programme title."],
    )
    total_credits_conclusion = total_credits_graph.conclusions[
        f"{programme_key.upper()}_TOTAL_NQF_CREDITS"
    ]

    requirements = [
        Requirement(
            id="duration",
            label=f"Minimum {min_years} years of study",
            complete=duration_ok,
            current=float(inferred_years),
            required=float(min_years),
            detail="Inferred from number of courses attempted",
        ),
        Requirement(
            id="courses",
            label="Semester course equivalents",
            complete=sce_total >= semester_course_equivalents,
            current=sce_total,
            required=float(semester_course_equivalents),
            detail=f"{sce_total:.1f} of {semester_course_equivalents} required semester-course equivalents passed",
        ),
        Requirement(
            id="senior",
            label="Senior semester courses (2000/3000-level)",
            complete=senior_sce >= senior_course_equivalents,
            current=senior_sce,
            required=float(senior_course_equivalents),
            detail=f"{senior_sce:.1f} of {senior_course_equivalents} required senior courses passed",
        ),
    ]
    
    if humanities_course_equivalents > 0:
        requirements.append(Requirement(
            id="humanities",
            label="Humanities semester courses",
            complete=humanities_sce >= humanities_course_equivalents,
            current=humanities_sce,
            required=float(humanities_course_equivalents),
            detail=f"{humanities_sce:.1f} of {humanities_course_equivalents} required Humanities courses passed",
        ))
        
    requirements.extend([
        Requirement(
            id="credits",
            label="NQF credits",
            complete=total_credits_conclusion.result,
            current=total_credits_conclusion.current,
            required=total_credits_conclusion.required,
            detail=f"{credits_completed} of {total_nqf_credits} NQF credits completed",
            evidence=total_credits_conclusion.evidence,
            applied_rules=total_credits_conclusion.applied_rules,
            explanation=total_credits_conclusion.explanation,
            status=total_credits_conclusion.status,
            confidence=total_credits_conclusion.confidence,
            assumptions=total_credits_conclusion.assumptions,
            depends_on=total_credits_conclusion.depends_on,
        ),
        Requirement(
            id="level7",
            label="NQF Level 7 credits",
            complete=level_7_credits >= level_7_nqf_credits,
            current=float(level_7_credits),
            required=float(level_7_nqf_credits),
            detail=f"{level_7_credits} of {level_7_nqf_credits} NQF Level 7 credits completed",
        ),
        Requirement(
            id="majors",
            label="Completed majors",
            complete=majors_complete >= required_majors,
            current=float(majors_complete),
            required=float(required_majors),
            detail=f"{majors_complete} of {required_majors} majors completed",
        ),
    ])
    
    if required_humanities_majors > 0:
        requirements.append(Requirement(
            id="humanities_major",
            label="At least one Humanities major",
            complete=humanities_majors_complete >= required_humanities_majors,
            current=float(humanities_majors_complete),
            required=float(required_humanities_majors),
            detail="At least one major must be offered by the Humanities Faculty",
        ))
        
    requirements.extend([
        Requirement(
            id="major_combination",
            label="Valid major combination",
            complete=forbidden_ok,
            current=1.0 if forbidden_ok else 0.0,
            required=1.0,
            detail="" if forbidden_ok else "Selected majors cannot be combined",
        ),
        Requirement(
            id="qualification_match",
            label="Qualification type",
            complete=True,
            current=1.0,
            required=1.0,
            detail="BA, BSocSc, or mixed (student may choose)",
        ),
    ])

    return requirements


def compute_report(student: StudentRecord, catalogue: Catalogue) -> Report:
    """
    Compute the full graduation report from raw facts.
    This is the only place where conclusions are drawn.
    """
    programme_key = _infer_programme_key(student.programme)
    prog = catalogue.programmes.get(programme_key)

    major_keys = _normalise_major_keys(student.declared_majors, catalogue)

    credits_completed, level_7_credits = _compute_credits(student)
    sce_total, senior_sce, humanities_sce = _compute_course_equivalents(student, catalogue)
    major_progresses, majors_complete, humanities_majors_complete = _compute_all_major_progresses(student, catalogue, major_keys)
    forbidden_ok = _check_forbidden_combinations(catalogue, major_keys)

    requirements = _build_requirements(
        student, catalogue, programme_key, prog,
        sce_total, senior_sce, humanities_sce,
        credits_completed, level_7_credits,
        majors_complete, humanities_majors_complete,
        forbidden_ok
    )

    graduation_eligible = all(r.complete for r in requirements)

    eligible_courses = _compute_eligible_courses(student, catalogue)
    exclusion_risk = _compute_exclusion_risk(student, catalogue, programme_key)
    distinction = _compute_distinction(student, catalogue, major_keys)
    warnings = _compute_warnings(student, catalogue, major_keys)
    failed_attempts = _compute_failed_attempts(student)

    return Report(
        graduation_eligible=graduation_eligible,
        credits_completed=credits_completed,
        level_7_credits=level_7_credits,
        semester_course_equivalents=sce_total,
        requirements=requirements,
        majors=major_progresses,
        eligible_courses=eligible_courses,
        exclusion_risk=exclusion_risk,
        distinction=distinction,
        warnings=warnings,
        failed_attempts=failed_attempts,
        student_name=student.name,
    )
