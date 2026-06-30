import unittest

from engine.models import StudentRecord, CourseResult, Catalogue, MajorDefinition, ProgrammeRules, CourseFact
from engine.knowledge_graph import KnowledgeGraph
from engine.simulator import SimulationEngine

class TestSimulationEngine(unittest.TestCase):
    def setUp(self):
        self.catalogue = Catalogue(
            courses={
                "CSC1015F": CourseFact(code="CSC1015F", name="CS1", nqf_credits=18, nqf_level=5, prerequisites=[], offered=["Semester 1"], department="CS"),
                "MAM1000W": CourseFact(code="MAM1000W", name="Math 1", nqf_credits=36, nqf_level=5, prerequisites=[], offered=["Full Year"], department="Math")
            },
            majors={
                "computer_science": MajorDefinition(key="computer_science", name="Computer Science", qualification="BSc", required_courses=["CSC1015F"]),
                "mathematics": MajorDefinition(key="mathematics", name="Mathematics", qualification="BSc", required_courses=["MAM1000W"])
            },
            programmes={
                "bsc": ProgrammeRules(
                    key="bsc", name="BSc", total_nqf_credits=360, level_7_nqf_credits=120,
                    semester_course_equivalents=20, senior_course_equivalents=10, humanities_course_equivalents=0,
                    required_majors=2, required_humanities_majors=0
                )
            },
            forbidden_combinations=[]
        )
        self.graph = KnowledgeGraph(self.catalogue)

        self.student = StudentRecord(
            student_id="TST001",
            name="Test Student",
            programme="BSc",
            declared_majors=["Computer Science"],
            results=[]
        )
        self.engine = SimulationEngine(self.student, self.catalogue, self.graph)

    def test_simulate_switch_majors_single(self):
        # Initial major is Computer Science
        # Switch to Mathematics
        report = self.engine.simulate_switch_majors(["Mathematics"])

        # Check original student object is unmodified
        self.assertEqual(self.student.declared_majors, ["Computer Science"])

        # Check report reflects the new major
        self.assertEqual(len(report.majors), 1)
        self.assertEqual(report.majors[0].key, "mathematics")
        self.assertEqual(report.majors[0].name, "Mathematics")

    def test_simulate_switch_majors_multiple(self):
        # Switch to two majors
        report = self.engine.simulate_switch_majors(["Computer Science", "Mathematics"])

        # Check original student object is unmodified
        self.assertEqual(self.student.declared_majors, ["Computer Science"])

        # Check report reflects the new majors
        self.assertEqual(len(report.majors), 2)
        major_keys = {m.key for m in report.majors}
        self.assertIn("computer_science", major_keys)
        self.assertIn("mathematics", major_keys)

    def test_simulate_switch_majors_empty(self):
        # Switch to empty list of majors
        report = self.engine.simulate_switch_majors([])

        # Check original is unmodified
        self.assertEqual(self.student.declared_majors, ["Computer Science"])

        # Check report has no majors
        self.assertEqual(len(report.majors), 0)

    def test_simulate_switch_majors_invalid(self):
        # Switch to an invalid major
        report = self.engine.simulate_switch_majors(["Unknown Major", "Mathematics"])

        # Check original is unmodified
        self.assertEqual(self.student.declared_majors, ["Computer Science"])

        # Unknown major is filtered out by _normalise_major_keys since it doesn't match
        # anything in the catalogue, so we should only see mathematics.
        self.assertEqual(len(report.majors), 1)
        self.assertEqual(report.majors[0].key, "mathematics")

if __name__ == "__main__":
    unittest.main()
