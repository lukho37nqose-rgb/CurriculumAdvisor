"""
Pure data models — no logic, no computed conclusions.
These are the raw facts the system stores.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CourseResult:
    """A single course attempt by a student."""
    code: str
    name: str
    nqf_level: int          # 5, 6, or 7
    nqf_credits: int        # 18, 24, or 30
    mark: Optional[int]     # 0-100, None if not yet graded
    grade: Optional[str]    # "1", "2+", "2-", "3", "F", None


@dataclass
class StudentRecord:
    """Raw facts extracted from a UCT transcript. No conclusions."""
    student_id: str
    name: str
    programme: str                          # e.g. "Bachelor of Social Science"
    declared_majors: list[str]              # e.g. ["African Studies", "Philosophy"]
    results: list[CourseResult] = field(default_factory=list)

    def passed_codes(self) -> set[str]:
        """Courses with a passing grade (mark >= 50)."""
        return {
            r.code for r in self.results
            if r.mark is not None and r.mark >= 50
        }

    def failed_codes(self) -> set[str]:
        """Courses with a failing grade (mark < 50)."""
        return {
            r.code for r in self.results
            if r.mark is not None and r.mark < 50
        }

    def attempted_codes(self) -> set[str]:
        """All courses with a recorded mark."""
        return {r.code for r in self.results if r.mark is not None}

    def result_for(self, code: str) -> Optional[CourseResult]:
        for r in self.results:
            if r.code == code:
                return r
        return None


@dataclass
class ChoiceGroup:
    """A group of courses from which a student must choose N."""
    label: str
    required: int           # how many must be chosen
    courses: list[str]      # course codes


@dataclass
class MajorDefinition:
    """Raw definition of a major — just facts about what it requires."""
    key: str
    name: str
    qualification: str      # "BA" or "BSocSc"
    required_courses: list[str]
    choice_groups: list[ChoiceGroup] = field(default_factory=list)


@dataclass
class ProgrammeRules:
    """Raw programme rules — just the numbers."""
    key: str
    name: str
    total_nqf_credits: int          # 360
    level_7_nqf_credits: int        # 120
    semester_course_equivalents: int # 20
    senior_course_equivalents: int  # 10
    humanities_course_equivalents: int  # 12
    required_majors: int            # 2
    required_humanities_majors: int # 1
    max_courses_per_semester: Optional[int] = None  # None = no limit (extended = 3)
    required_courses: list[str] = field(default_factory=list)


@dataclass
class CourseFact:
    """A course in the catalogue — pure facts, no 'satisfies' conclusions."""
    code: str
    name: str
    nqf_credits: int
    nqf_level: int
    prerequisites: list[str]
    offered: list[str]          # ["Semester 1", "Semester 2", "Full Year"]
    department: str
    description: str = ""


@dataclass
class Catalogue:
    """The full fact store: courses + degree requirements."""
    courses: dict[str, CourseFact]              # code -> CourseFact
    majors: dict[str, MajorDefinition]          # key -> MajorDefinition
    programmes: dict[str, ProgrammeRules]       # key -> ProgrammeRules
    forbidden_combinations: list[tuple[str, str]]  # pairs of major keys
