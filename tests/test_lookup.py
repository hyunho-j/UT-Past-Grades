import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ut_past_grades.lookup import CourseRequest, lookup, parse_requests

SAMPLE = """
pull the distribution for:
| 2026 Spring | HIS 315K | 39345 |
| :---------- | :------- | :---- |
and
| 2025 Spring | HIS 315K | 38960 | The United States, 1492-1865. | Rachel Ozanne<br> | [CV](https://example.com/11075260/) |
| 2025 Spring | HIS 315K | 38955 | The United States, 1492-1865. | Rachel Ozanne<br> |
| 2026 Spring | HIS 315K | 39340 | The United States, 1492-1865. | Rachel Ozanne<br> |
| 2026 Spring | HIS 315K | 39335 | The United States, 1492-1865. | Rachel Ozanne<br> |
"""

class LookupTests(unittest.TestCase):
    def test_original_prompt(self):
        requests = parse_requests(SAMPLE)
        self.assertEqual([r.section for r in requests], ["39345", "38960", "38955", "39340", "39335"])
        output = lookup(SAMPLE)
        lines = [line for line in output.splitlines() if line.startswith("|")]
        self.assertTrue(all([i for i, char in enumerate(line) if char == "|"] ==
                            [i for i, char in enumerate(lines[0]) if char == "|"]
                            for line in lines))
        output = " ".join(output.split())
        self.assertIn("| A | 190 (61.89%) | 225 (70.53%) | 230 (72.10%) | 223 (69.69%) | 211 (66.14%) |", output)
        self.assertIn("| **Total** | **307** | **319** | **319** | **320** | **319** |", output)

    def test_variants_and_duplicates(self):
        text = "spring 2026, **his-315k**, section no. 39345\n2026 Spring | HIS 315K | 39345"
        self.assertEqual(parse_requests(text), [CourseRequest("Spring 2026", "HIS", "315K", "39345")])
        self.assertEqual(parse_requests("Fall 2024\nCS 314\nUnique number: 12345")[0].prefix, "CS")

    def test_single_letter_department_in_markdown(self):
        text = '''
| 2025 Fall | E 316L | 36840 | British Literature. | George Christian<br> | [**George Christian CV**](https://utdirect.utexas.edu/apps/student/coursedocs/courses/nlogon/download/13824596/ "download cv for George Christian")<br> | [**Download**](https://utdirect.utexas.edu/apps/student/coursedocs/courses/nlogon/download/16260265/ "download syllabus") |
| :-------- | :----- | :---- | :------------------ | :------------------- |
| 2025 Fall | E 316L | 36835 | British Literature. | George Christian<br> | [**Download**](https://utdirect.utexas.edu/apps/student/coursedocs/courses/nlogon/download/16260265/ "download syllabus") |
'''
        self.assertEqual(parse_requests(text), [
            CourseRequest("Fall 2025", "E", "316L", "36840"),
            CourseRequest("Fall 2025", "E", "316L", "36835"),
        ])
        output = lookup(text)
        self.assertIn("Recognized 2 unique course section(s); found 2.", output)
        self.assertIn("| **Total** | **22** | **23** |", " ".join(output.split()))

    def test_middle_dot_and_summer_prefix(self):
        self.assertEqual(parse_requests("Summer 2022 · GOV S312L · 81275"), [
            CourseRequest("Summer 2022", "GOV", "S312L", "81275"),
        ])
        self.assertIn("**390**", lookup("Summer 2022 · GOV S312L · 81275"))

    def test_no_entries(self):
        with self.assertRaisesRegex(ValueError, "No course entries"):
            lookup("Rachel Ozanne https://example.com/11075260/")

    def test_missing_and_found(self):
        output = lookup("Spring 2026 HIS 315K 39345\nSpring 2099 HIS 315K 39345")
        self.assertIn("found 1", output)
        self.assertIn("No records found for:\n- Spring 2099", output)

    def test_aggregation_and_zero_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "grades.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE grade_distributions (semester, course_prefix, course_number, section_number, letter_grade, student_count, course_title DEFAULT 'History')")
                connection.executemany("INSERT INTO grade_distributions (semester,course_prefix,course_number,section_number,letter_grade,student_count) VALUES (?,?,?,?,?,?)", [
                    ("Spring 2026", "HIS", " 315K", "39345", "A", 1),
                    ("Spring 2026", "HIS", " 315K", "39345", "A", 2),
                    ("Spring 2026", "HIS", " 315K", "39340", "A", 0),
                ])
                connection.commit()
            output = lookup("Spring 2026 HIS 315K 39345\nSpring 2026 HIS 315K 39340", database)
            self.assertIn("| A | 3 (100.00%) | 0 (N/A) |", " ".join(output.split()))

    def test_missing_database_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                lookup("Spring 2026 HIS 315K 39345", database)
            self.assertFalse(database.exists())

    def test_combine_sections_by_title_and_semester(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "grades.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE grade_distributions (semester, course_prefix, course_number, section_number, letter_grade, student_count, course_title)")
                connection.executemany("INSERT INTO grade_distributions VALUES (?,?,?,?,?,?,?)", [
                    ("Fall 2025", "E", " 316L", "10001", "A", 1, "British Literature"),
                    ("Fall 2025", "E", " 316L", "10001", "B", 1, "British Literature"),
                    ("Fall 2025", "E", " 316L", "10002", "A", 6, "British Literature"),
                    ("Fall 2025", "E", " 316L", "10003", "A", 10, "Different Title"),
                    ("Spring 2026", "E", " 316L", "10004", "A", 20, "British Literature"),
                ])
                connection.commit()
            text = "\n".join([
                "Fall 2025 E 316L 10001", "Fall 2025 E 316L 10002",
                "Fall 2025 E 316L 10003", "Spring 2026 E 316L 10004",
                "Fall 2025 E 316L 10001", "Fall 2025 E 316L 99999",
            ])
            combined = lookup(text, database, combine_sections=True)
            compact = " ".join(combined.split())
            self.assertNotIn("10001", combined.splitlines()[2])
            self.assertNotIn("10002", combined.splitlines()[2])
            self.assertIn("| A | 7 (87.50%) | 10 (100.00%) | 20 (100.00%) |", compact)
            self.assertIn("| **Total** | **8** | **10** | **20** |", compact)
            self.assertIn("No records found for:", combined)
            self.assertIn("Recognized 5 unique course section(s); found 4.", combined)
            separate = " ".join(lookup(text, database, combine_sections=False).split())
            self.assertIn("| **Total** | **2** | **6** | **10** | **20** |", separate)

if __name__ == "__main__":
    unittest.main()
