"""Combine all root CSV grade exports (UTF-16, tab-delimited) using stdlib."""

import csv
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HEADER = [
    "Semester", "Section Number", "Department/Program", "Course Prefix",
    "Course Number", "Course Title", "Course", "Letter Grade", "",
]
SCHEMA = """
CREATE TABLE grade_distributions (
    semester TEXT NOT NULL,
    section_number TEXT NOT NULL,
    department_program TEXT NOT NULL,
    course_prefix TEXT NOT NULL,
    course_number TEXT NOT NULL,
    course_title TEXT NOT NULL,
    course TEXT NOT NULL,
    letter_grade TEXT NOT NULL,
    student_count INTEGER NOT NULL CHECK (student_count >= 0)
);
"""


def main():
    sources = sorted(ROOT.glob("*.csv"))
    if not sources:
        raise ValueError("No CSV grade exports found in the project root")
    database = ROOT / "ut_grades.db"
    temporary = database.with_suffix(".db.tmp")
    expected_rows = Counter()
    expected_students = Counter()
    expected_records = Counter()
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.execute("DROP TABLE IF EXISTS grade_distributions")
            connection.executescript(SCHEMA)
            for source in sources:
                with source.open(encoding="utf-16", newline="") as handle:
                    reader = csv.reader(handle, delimiter="\t", strict=True)
                    if next(reader) != HEADER:
                        raise ValueError(f"Unexpected header in {source.name}")
                    batch = []
                    for line, row in enumerate(reader, 2):
                        if len(row) != 9 or not re.fullmatch(
                            r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", row[-1]
                        ):
                            raise ValueError(f"Invalid record: {source.name}:{line}")
                        count = int(row[-1].replace(",", ""))
                        record = (*row[:8], count)
                        batch.append(record)
                        expected_records[record] += 1
                        expected_rows[source.name] += 1
                        expected_students[source.name] += count
                        if len(batch) >= 5000:
                            connection.executemany(
                                "INSERT INTO grade_distributions VALUES (?,?,?,?,?,?,?,?,?)",
                                batch,
                            )
                            batch.clear()
                    connection.executemany(
                        "INSERT INTO grade_distributions VALUES (?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
            connection.execute(
                "CREATE INDEX idx_grades_course ON grade_distributions "
                "(course_prefix, course_number, semester)"
            )
            connection.execute(
                "CREATE INDEX idx_grades_semester ON grade_distributions (semester)"
            )
            actual_records = Counter(connection.execute("SELECT * FROM grade_distributions"))
            if actual_records != expected_records:
                raise ValueError("Database records do not match source records")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
            connection.commit()
        temporary.replace(database)
    finally:
        temporary.unlink(missing_ok=True)
    for source in sources:
        print(f"{source.name}: {expected_rows[source.name]:,} rows; "
              f"{expected_students[source.name]:,} student-grade counts")
    print(f"Total: {sum(expected_rows.values()):,} rows")
    print(f"Created {database.name}; all source records verified.")


if __name__ == "__main__":
    main()
