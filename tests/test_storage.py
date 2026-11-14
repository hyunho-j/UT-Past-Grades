import csv
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import build_database
from ut_past_grades.storage import GRADES, write_database


class StorageTests(unittest.TestCase):
    def test_pivot_keeps_text_course_and_grade_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "grades.db"
            details = ("Spring 2026", "00180", "HIS", " 315K", "History", "Full course description")
            sections, total = write_database([
                (*details, "A", 2), (*details, "A", 3), (*details, "B+", 4),
            ], database)
            self.assertEqual((sections, total), (1, 9))
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute('SELECT section_number, course, "A", "B+", "F", typeof(section_number), typeof(semester) FROM grade_distributions').fetchone()
                self.assertEqual(row, ("00180", "Full course description", 5, 4, 0, "text", "text"))
                columns = [row[1] for row in connection.execute("PRAGMA table_info(grade_distributions)")]
                self.assertNotIn("department_program", columns)
                self.assertNotIn("letter_grade", columns)
                self.assertTrue(all(grade in columns for grade in GRADES))
            before = database.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unsupported letter grade"):
                write_database([(*details, "Unknown", 1)], database)
            self.assertEqual(database.read_bytes(), before)

    def test_build_from_utf16_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root / "export.csv").open("w", encoding="utf-16", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(build_database.HEADER)
                writer.writerows([
                    ["Fall 2025", "12345", "Discarded department", "E", " 316L", "British Literature", "Keep this course", "A", "1,234"],
                    ["Fall 2025", "12345", "Discarded department", "E", " 316L", "British Literature", "Keep this course", "B", "2"],
                ])
            with patch.object(build_database, "ROOT", root):
                build_database.build_from_csv()
            with closing(sqlite3.connect(root / "ut_grades.db")) as connection:
                self.assertEqual(connection.execute('SELECT course, "A", "B", "Other" FROM grade_distributions').fetchall(), [("Keep this course", 1234, 2, 0)])

    def test_migrate_existing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "grades.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE grade_distributions (semester,section_number,course_prefix,course_number,course_title,course,letter_grade,student_count)")
                connection.executemany("INSERT INTO grade_distributions VALUES (?,?,?,?,?,?,?,?)", [
                    ("Summer 2022", "81275", "GOV", "S312L", "Government", "Full course", "A-", 4),
                    ("Summer 2022", "81275", "GOV", "S312L", "Government", "Full course", "Other", 2),
                ])
                connection.commit()
            build_database.migrate(database)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT "A-", "Other", "F" FROM grade_distributions').fetchall(), [(4, 2, 0)])


if __name__ == "__main__":
    unittest.main()
