"""
Simulation Engine — simulates future academic states.
Allows students to ask "What if" questions and see the impact on their graduation status.
"""
import copy
from typing import List, Dict, Set, Tuple, Optional, Any
from .models import StudentRecord, CourseResult, Catalogue
from .knowledge_graph import KnowledgeGraph
from .rule_engine import compute_report, Report
from .reasoner import GraduateGoal, HonoursReadinessGoal


class SimulationEngine:
    def __init__(self, student: StudentRecord, catalogue: Catalogue, graph: KnowledgeGraph):
        self.student = student
        self.catalogue = catalogue
        self.graph = graph

    def simulate_fail_course(self, course_code: str) -> Tuple[Report, List[str]]:
        """Simulate failing a course. Returns the new report and a list of blocked courses."""
        sim_student = copy.deepcopy(self.student)
        
        # Find the course result and set mark to 40 (fail)
        found = False
        for r in sim_student.results:
            if r.code == course_code:
                r.mark = 40
                r.grade = "F"
                found = True
                break
        
        if not found:
            # Add a failed attempt
            sim_student.results.append(CourseResult(
                code=course_code,
                name=self.catalogue.courses.get(course_code).name if course_code in self.catalogue.courses else "Simulated Course",
                nqf_level=5,
                nqf_credits=18,
                mark=40,
                grade="F"
            ))

        # Compute new report
        new_report = compute_report(sim_student, self.catalogue)
        
        # Find blocked courses
        blocked = self.graph.get_all_unlocked_courses(course_code)
        blocked_list = sorted(list(blocked))

        return new_report, blocked_list

    def simulate_pass_course(self, course_code: str, mark: int = 75) -> Report:
        """Simulate passing a course with a specific mark."""
        sim_student = copy.deepcopy(self.student)
        
        # Find the course result and set mark to pass
        found = False
        grade = "1" if mark >= 75 else "2+" if mark >= 70 else "2-" if mark >= 60 else "3"
        
        for r in sim_student.results:
            if r.code == course_code:
                r.mark = mark
                r.grade = grade
                found = True
                break
        
        if not found:
            course_fact = self.catalogue.courses.get(course_code)
            nqf_level = course_fact.nqf_level if course_fact else 5
            nqf_credits = course_fact.nqf_credits if course_fact else 18
            name = course_fact.name if course_fact else "Simulated Course"
            
            sim_student.results.append(CourseResult(
                code=course_code,
                name=name,
                nqf_level=nqf_level,
                nqf_credits=nqf_credits,
                mark=mark,
                grade=grade
            ))

        return compute_report(sim_student, self.catalogue)

    def simulate_switch_majors(self, new_majors: List[str]) -> Report:
        """Simulate switching to a new set of majors."""
        sim_student = copy.deepcopy(self.student)
        sim_student.declared_majors = new_majors
        return compute_report(sim_student, self.catalogue)

    def simulate_future_semester(self, courses_to_take: List[Tuple[str, int]]) -> Report:
        """Simulate taking a set of courses next semester with expected marks."""
        sim_student = copy.deepcopy(self.student)
        
        for code, mark in courses_to_take:
            course_fact = self.catalogue.courses.get(code)
            nqf_level = course_fact.nqf_level if course_fact else 5
            nqf_credits = course_fact.nqf_credits if course_fact else 18
            name = course_fact.name if course_fact else "Simulated Course"
            grade = "1" if mark >= 75 else "2+" if mark >= 70 else "2-" if mark >= 60 else "3" if mark >= 50 else "F"
            
            # Remove any existing attempt for this course to replace it
            sim_student.results = [r for r in sim_student.results if r.code != code]
            
            sim_student.results.append(CourseResult(
                code=code,
                name=name,
                nqf_level=nqf_level,
                nqf_credits=nqf_credits,
                mark=mark,
                grade=grade
            ))

        return compute_report(sim_student, self.catalogue)
