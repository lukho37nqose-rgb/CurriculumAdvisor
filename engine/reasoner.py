"""
Reasoning Engine — defines Goals and reasons about how to achieve them.
Supports backward chaining, gap analysis, pathway optimization,
and honours readiness assessment.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any
from .models import StudentRecord, Catalogue, CourseFact, MajorDefinition, ProgrammeRules
from .knowledge_graph import KnowledgeGraph
from .utils import _course_weight, _is_senior, _is_humanities, _normalise_major_keys, _infer_programme_key


@dataclass
class GoalRequirement:
    id: str
    label: str
    complete: bool
    current: Any
    required: Any
    detail: str = ""


@dataclass
class PathwayStep:
    semester: str
    courses: List[str]
    reason: str


@dataclass
class GoalReport:
    goal_id: str
    name: str
    complete: bool
    requirements: List[GoalRequirement]
    gap_description: str
    recommended_path: List[PathwayStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Goal:
    def __init__(self, student: StudentRecord, catalogue: Catalogue, graph: KnowledgeGraph):
        self.student = student
        self.catalogue = catalogue
        self.graph = graph

    def evaluate(self) -> GoalReport:
        raise NotImplementedError


class GraduateGoal(Goal):
    def evaluate(self) -> GoalReport:
        passed = self.student.passed_codes()
        programme_key = _infer_programme_key(self.student.programme)
        prog = self.catalogue.programmes.get(programme_key)
        
        if not prog:
            return GoalReport("graduate", "Graduate", False, [], "Programme rules not found", [])

        # 1. Credits
        credits_completed = sum(r.nqf_credits for r in self.student.results if r.mark is not None and r.mark >= 50)
        credits_ok = credits_completed >= prog.total_nqf_credits

        # 2. Level 7 credits
        level_7_credits = sum(r.nqf_credits for r in self.student.results if r.mark is not None and r.mark >= 50 and r.nqf_level == 7)
        level_7_ok = level_7_credits >= prog.level_7_nqf_credits

        # 3. Semester course equivalents
        sce_total = sum(_course_weight(r.code) for r in self.student.results if r.mark is not None and r.mark >= 50)
        sce_ok = sce_total >= prog.semester_course_equivalents

        # 4. Senior courses
        senior_sce = sum(_course_weight(r.code) for r in self.student.results if r.mark is not None and r.mark >= 50 and _is_senior(r.code))
        senior_ok = senior_sce >= prog.senior_course_equivalents

        # 5. Humanities courses
        humanities_sce = sum(_course_weight(r.code) for r in self.student.results if r.mark is not None and r.mark >= 50 and _is_humanities(r.code, self.catalogue))
        humanities_ok = humanities_sce >= prog.humanities_course_equivalents

        # 6. Majors
        major_keys = _normalise_major_keys(self.student.declared_majors, self.catalogue)
        major_goals = [CompleteMajorGoal(self.student, self.catalogue, self.graph, key).evaluate() for key in major_keys]
        majors_complete_count = sum(1 for m in major_goals if m.complete)
        majors_ok = majors_complete_count >= prog.required_majors

        # 7. Humanities major
        humanities_majors_complete = sum(
            1 for m in major_goals
            if m.complete and self.catalogue.majors.get(m.goal_id.split("_")[-1]) and
            self.catalogue.majors[m.goal_id.split("_")[-1]].qualification in ("BA", "BSocSc")
        )
        humanities_major_ok = humanities_majors_complete >= prog.required_humanities_majors

        reqs = [
            GoalRequirement("credits", "NQF Credits", credits_ok, credits_completed, prog.total_nqf_credits, f"{credits_completed}/{prog.total_nqf_credits} NQF credits completed"),
            GoalRequirement("level7", "NQF Level 7 Credits", level_7_ok, level_7_credits, prog.level_7_nqf_credits, f"{level_7_credits}/{prog.level_7_nqf_credits} Level 7 credits completed"),
            GoalRequirement("courses", "Semester Course Equivalents", sce_ok, sce_total, prog.semester_course_equivalents, f"{sce_total}/{prog.semester_course_equivalents} courses completed"),
            GoalRequirement("senior", "Senior Semester Courses", senior_ok, senior_sce, prog.senior_course_equivalents, f"{senior_sce}/{prog.senior_course_equivalents} senior courses completed"),
            GoalRequirement("humanities", "Humanities Semester Courses", humanities_ok, humanities_sce, prog.humanities_course_equivalents, f"{humanities_sce}/{prog.humanities_course_equivalents} Humanities courses completed"),
            GoalRequirement("majors", "Completed Majors", majors_ok, majors_complete_count, prog.required_majors, f"{majors_complete_count}/{prog.required_majors} majors completed"),
            GoalRequirement("humanities_major", "Humanities Major", humanities_major_ok, humanities_majors_complete, prog.required_humanities_majors, "At least one major must be in Humanities")
        ]

        complete = all(r.complete for r in reqs)
        
        # Gap analysis
        gaps = []
        if not credits_ok:
            gaps.append(f"Need {prog.total_nqf_credits - credits_completed} more NQF credits.")
        if not level_7_ok:
            gaps.append(f"Need {prog.level_7_nqf_credits - level_7_credits} more Level 7 credits (typically 3000-level courses).")
        if not sce_ok:
            gaps.append(f"Need {prog.semester_course_equivalents - sce_total} more semester-course equivalents.")
        if not senior_ok:
            gaps.append(f"Need {prog.senior_course_equivalents - senior_sce} more senior courses.")
        if not humanities_ok:
            gaps.append(f"Need {prog.humanities_course_equivalents - humanities_sce} more Humanities courses.")
        for m in major_goals:
            if not m.complete:
                gaps.append(f"Major '{m.name}' is incomplete: {m.gap_description}")

        gap_desc = " ".join(gaps) if gaps else "All graduation requirements met!"

        # Recommended path (backward chaining)
        path = self._compute_graduation_path(major_goals, prog)

        return GoalReport("graduate", "Graduate", complete, reqs, gap_desc, path)

    def _compute_graduation_path(self, major_goals: List[GoalReport], prog: ProgrammeRules) -> List[PathwayStep]:
        """Work backwards from graduation requirements to recommend a semester-by-semester plan."""
        passed = self.student.passed_codes()
        outstanding_courses = set()
        
        # 1. Collect all outstanding compulsory courses from programme rules
        for code in prog.required_courses:
            if code not in passed:
                outstanding_courses.add(code)

        # 2. Collect all outstanding compulsory courses from majors
        for m in major_goals:
            for req in m.requirements:
                if not req.complete and req.id.startswith("compulsory_"):
                    course_code = req.id.split("_", 1)[1]
                    outstanding_courses.add(course_code)
                elif not req.complete and req.id.startswith("choice_"):
                    # Choice group: add all options that are unlocked
                    group_name = req.id.split("_", 1)[1]
                    major_key = m.goal_id.split("_", 1)[1]
                    major_def = self.catalogue.majors.get(major_key)
                    if major_def:
                        for g in major_def.choice_groups:
                            if g.label == group_name:
                                for c in g.courses:
                                    if c not in passed:
                                        outstanding_courses.add(c)

        # Build dependency ordering of outstanding courses
        plan_courses = list(outstanding_courses)
        # Sort by NQF level so lower level courses are taken first
        plan_courses.sort(key=lambda c: self.catalogue.courses.get(c).nqf_level if self.catalogue.courses.get(c) else 5)

        # Group into semesters
        steps = []
        semester_num = 1
        max_per_sem = prog.max_courses_per_semester or 4
        
        current_passed = set(passed)
        remaining = list(plan_courses)

        while remaining and semester_num <= 8:
            sem_label = f"Semester {semester_num}"
            sem_courses = []
            
            # Find courses that have prerequisites met
            for c in list(remaining):
                course = self.catalogue.courses.get(c)
                if not course:
                    continue
                # Check if prerequisites are met in current_passed
                if all(p in current_passed for p in course.prerequisites):
                    sem_courses.append(c)
                    if len(sem_courses) >= max_per_sem:
                        break
            
            if not sem_courses:
                # If no courses are unlocked, we might have a deadlock or missing prereqs in catalogue.
                # Force add the first remaining course to avoid infinite loop
                sem_courses = remaining[:1]
            
            for c in sem_courses:
                remaining.remove(c)
                current_passed.add(c)
                
            steps.append(PathwayStep(
                semester=sem_label,
                courses=sem_courses,
                reason=f"Complete outstanding major requirements: {', '.join(sem_courses)}"
            ))
            semester_num += 1

        return steps


class CompleteMajorGoal(Goal):
    def __init__(self, student: StudentRecord, catalogue: Catalogue, graph: KnowledgeGraph, major_key: str):
        super().__init__(student, catalogue, graph)
        self.major_key = major_key

    def evaluate(self) -> GoalReport:
        major_def = self.catalogue.majors.get(self.major_key)
        if not major_def:
            return GoalReport(f"major_{self.major_key}", f"Complete {self.major_key}", False, [], f"Major '{self.major_key}' not found in catalogue", [])

        passed = self.student.passed_codes()
        reqs = []
        gaps = []

        # Compulsory courses
        for code in major_def.required_courses:
            is_done = code in passed
            reqs.append(GoalRequirement(
                id=f"compulsory_{code}",
                label=f"Pass {code}",
                complete=is_done,
                current=1 if is_done else 0,
                required=1,
                detail=f"Compulsory course {code}"
            ))
            if not is_done:
                gaps.append(f"Pass {code}.")

        # Choice groups
        for group in major_def.choice_groups:
            satisfied = [c for c in group.courses if c in passed]
            needed = group.required
            is_done = len(satisfied) >= needed
            reqs.append(GoalRequirement(
                id=f"choice_{group.label}",
                label=group.label,
                complete=is_done,
                current=len(satisfied),
                required=needed,
                detail=f"Choose {needed} from {group.courses}"
            ))
            if not is_done:
                gaps.append(f"Need {needed - len(satisfied)} more from {group.label}.")

        complete = all(r.complete for r in reqs)
        gap_desc = " ".join(gaps) if gaps else f"All requirements for {major_def.name} major met!"

        return GoalReport(f"major_{self.major_key}", major_def.name, complete, reqs, gap_desc)


class HonoursReadinessGoal(Goal):
    def __init__(self, student: StudentRecord, catalogue: Catalogue, graph: KnowledgeGraph, major_key: str):
        super().__init__(student, catalogue, graph)
        self.major_key = major_key

    def evaluate(self) -> GoalReport:
        major_def = self.catalogue.majors.get(self.major_key)
        if not major_def:
            return GoalReport(f"honours_{self.major_key}", f"Honours Readiness: {self.major_key}", False, [], "Major not found", [])

        # UCT Honours admission rules:
        # 1. Complete the undergraduate degree.
        # 2. Achieve a minimum average (usually 65% or 70%) in the senior (2000/3000-level) courses of the major.
        # Let's compute the current average of senior courses in this major.
        senior_codes = set()
        for code in major_def.required_courses:
            if _is_senior(code):
                senior_codes.add(code)
        for group in major_def.choice_groups:
            for code in group.courses:
                if _is_senior(code):
                    senior_codes.add(code)

        marks = []
        for code in senior_codes:
            result = self.student.result_for(code)
            if result and result.mark is not None:
                marks.append(result.mark)

        current_avg = sum(marks) / len(marks) if marks else 0.0
        target_avg = 70.0  # standard UCT Honours threshold
        
        # Remaining senior courses in the major
        passed = self.student.passed_codes()
        remaining_senior = [c for c in senior_codes if c not in passed]
        
        # Calculate required average on remaining courses to hit target
        total_senior_count = len(senior_codes)
        completed_count = len(marks)
        remaining_count = total_senior_count - completed_count
        
        req_avg_remaining = 0.0
        if remaining_count > 0:
            current_sum = sum(marks)
            target_sum = target_avg * total_senior_count
            needed_sum = target_sum - current_sum
            req_avg_remaining = needed_sum / remaining_count

        reqs = [
            GoalRequirement("average", "Senior Major Average", current_avg >= target_avg, round(current_avg, 1), target_avg, f"Current average: {round(current_avg, 1)}% (Target: {target_avg}%)"),
            GoalRequirement("remaining", "Remaining Senior Courses", len(remaining_senior) == 0, total_senior_count - len(remaining_senior), total_senior_count, f"{len(remaining_senior)} senior courses remaining")
        ]

        complete = current_avg >= target_avg and len(remaining_senior) == 0
        
        # Gap analysis
        gaps = []
        if current_avg < target_avg:
            gaps.append(f"Current average is {round(current_avg, 1)}%, which is below the {target_avg}% threshold.")
        if remaining_senior:
            gaps.append(f"Need to complete: {', '.join(remaining_senior)}.")
            if req_avg_remaining > 100:
                gaps.append(f"Warning: It is mathematically impossible to reach a {target_avg}% average because you need {round(req_avg_remaining, 1)}% on remaining courses.")
            elif req_avg_remaining > 0:
                gaps.append(f"You need to average at least {round(req_avg_remaining, 1)}% across your remaining {remaining_count} senior courses to qualify.")

        gap_desc = " ".join(gaps) if gaps else "Ready for Honours admission!"

        return GoalReport(
            f"honours_{self.major_key}",
            f"Honours Readiness: {major_def.name}",
            complete,
            reqs,
            gap_desc,
            metadata={
                "current_average": round(current_avg, 1),
                "target_average": target_avg,
                "remaining_count": remaining_count,
                "required_average_remaining": round(req_avg_remaining, 1) if req_avg_remaining > 0 else 0.0
            }
        )
