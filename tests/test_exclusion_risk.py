import unittest

from engine.models import Catalogue, CourseResult, ProgrammeRules, StudentRecord
from engine.rule_engine import _compute_exclusion_risk

class TestExclusionRisk(unittest.TestCase):
    def setUp(self):
        self.catalogue = Catalogue(
            courses={},
            majors={},
            programmes={
                "regular_ba_bsocsc": ProgrammeRules(
                    key="regular_ba_bsocsc",
                    name="Regular BA/BSocSc",
                    total_nqf_credits=360,
                    level_7_nqf_credits=120,
                    semester_course_equivalents=20,
                    senior_course_equivalents=10,
                    humanities_course_equivalents=12,
                    required_majors=2,
                    required_humanities_majors=1,
                ),
                "extended_ba_bsocsc": ProgrammeRules(
                    key="extended_ba_bsocsc",
                    name="Extended BA/BSocSc",
                    total_nqf_credits=360,
                    level_7_nqf_credits=120,
                    semester_course_equivalents=20,
                    senior_course_equivalents=10,
                    humanities_course_equivalents=12,
                    required_majors=2,
                    required_humanities_majors=1,
                ),
            },
            forbidden_combinations=[],
        )

    def _create_results(self, count: int, passed: int, senior: int) -> list[CourseResult]:
        results = []
        for i in range(count):
            is_passed = i < passed
            is_senior = i < senior

            # Junior code: AAA1000F, Senior code: AAA2000F
            code = f"AAA{'2' if is_senior else '1'}00{i}F"
            mark = 60 if is_passed else 40

            results.append(CourseResult(
                code=code,
                name=f"Course {i}",
                nqf_level=6 if is_senior else 5,
                nqf_credits=18,
                mark=mark,
                grade="2-" if is_passed else "F"
            ))
        return results

    def _create_student(self, attempted: int, passed: int, senior: int = 0) -> StudentRecord:
        results = self._create_results(attempted, passed, senior)
        return StudentRecord(
            student_id="TEST01",
            name="Test Student",
            programme="Some Programme",
            declared_majors=[],
            results=results
        )

    def test_missing_programme(self):
        student = self._create_student(5, 5)
        risk = _compute_exclusion_risk(student, self.catalogue, "unknown_prog")
        self.assertFalse(risk.at_risk)
        self.assertEqual(len(risk.reasons), 0)

    # Regular BA/BSocSc Tests
    def test_regular_year_1_not_at_risk(self):
        # Year 1 (<= 8 attempted)
        # Needs 5 passed
        student = self._create_student(attempted=8, passed=5)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_regular_year_1_at_risk(self):
        # Year 1 (<= 8 attempted)
        # Needs 5 passed
        student = self._create_student(attempted=8, passed=4)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 1)
        self.assertIn("need 5 passed courses, have 4", risk.reasons[0])

    def test_regular_year_2_not_at_risk(self):
        # Year 2 (<= 16 attempted)
        # Needs 9 passed
        student = self._create_student(attempted=16, passed=9)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_regular_year_2_at_risk(self):
        # Year 2 (<= 16 attempted)
        # Needs 9 passed
        student = self._create_student(attempted=16, passed=8)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 1)
        self.assertIn("need 9 passed courses, have 8", risk.reasons[0])

    def test_regular_year_3_not_at_risk(self):
        # Year 3 (<= 24 attempted)
        # Needs 13 passed, 2 senior
        student = self._create_student(attempted=24, passed=13, senior=2)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_regular_year_3_at_risk_passed(self):
        # Year 3 (<= 24 attempted)
        # Needs 13 passed, 2 senior
        student = self._create_student(attempted=24, passed=12, senior=2)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 1)
        self.assertIn("need 13 passed courses, have 12", risk.reasons[0])

    def test_regular_year_3_at_risk_senior(self):
        # Year 3 (<= 24 attempted)
        # Needs 13 passed, 2 senior
        student = self._create_student(attempted=24, passed=13, senior=1)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 1)
        self.assertIn("need 2 senior courses passed, have 1", risk.reasons[0])

    def test_regular_year_3_at_risk_both(self):
        # Year 3 (<= 24 attempted)
        # Needs 13 passed, 2 senior
        student = self._create_student(attempted=24, passed=12, senior=1)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 2)

    def test_regular_year_4(self):
        # Year 4 (> 24 attempted)
        # No new reqs, but must still meet year 3 reqs
        student = self._create_student(attempted=25, passed=12, senior=1)
        risk = _compute_exclusion_risk(student, self.catalogue, "regular_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 2)

    # Extended BA/BSocSc Tests
    def test_extended_year_1_not_at_risk(self):
        student = self._create_student(attempted=8, passed=4)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_extended_year_1_at_risk(self):
        student = self._create_student(attempted=8, passed=3)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertTrue(risk.at_risk)

    def test_extended_year_2_not_at_risk(self):
        student = self._create_student(attempted=16, passed=8)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_extended_year_2_at_risk(self):
        student = self._create_student(attempted=16, passed=7)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertTrue(risk.at_risk)

    def test_extended_year_3_not_at_risk(self):
        student = self._create_student(attempted=24, passed=12, senior=2)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_extended_year_3_at_risk(self):
        student = self._create_student(attempted=24, passed=12, senior=1)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertTrue(risk.at_risk)

    def test_extended_year_4_not_at_risk(self):
        student = self._create_student(attempted=25, passed=15, senior=4)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertFalse(risk.at_risk)

    def test_extended_year_4_at_risk(self):
        student = self._create_student(attempted=25, passed=14, senior=4)
        risk = _compute_exclusion_risk(student, self.catalogue, "extended_ba_bsocsc")
        self.assertTrue(risk.at_risk)
        self.assertEqual(len(risk.reasons), 1)

if __name__ == "__main__":
    unittest.main()
