import unittest
from engine.parser import _parse_grade

class TestParseGrade(unittest.TestCase):
    def test_valid_grades(self):
        """Test that all valid grades are parsed correctly."""
        valid_grades = ["1", "2+", "2-", "3", "F", "P", "PA", "UP", "SP", "FS"]
        for grade in valid_grades:
            with self.subTest(grade=grade):
                self.assertEqual(_parse_grade(grade), grade)

    def test_valid_grades_with_whitespace(self):
        """Test that whitespace is stripped from valid grades."""
        self.assertEqual(_parse_grade("  1  "), "1")
        self.assertEqual(_parse_grade("\tPA\n"), "PA")
        self.assertEqual(_parse_grade(" 2+ "), "2+")

    def test_invalid_grades(self):
        """Test that invalid grades return None."""
        invalid_grades = ["A", "B", "4", "invalid", "", " ", "2", "1+", "0"]
        for grade in invalid_grades:
            with self.subTest(grade=grade):
                self.assertIsNone(_parse_grade(grade))

    def test_case_sensitivity(self):
        """Test that grade parsing is case-sensitive where appropriate."""
        # Current implementation uses exact match against uppercase/specific strings.
        self.assertIsNone(_parse_grade("p"))
        self.assertIsNone(_parse_grade("pa"))
        self.assertIsNone(_parse_grade("f"))
        self.assertIsNone(_parse_grade("Fs"))

if __name__ == "__main__":
    unittest.main()
