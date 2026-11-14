"""Combine all root CSV grade exports (UTF-16, tab-delimited) using stdlib."""

import csv
import re
import sqlite3
import argparse
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from ut_past_grades.storage import write_database
HEADER = [
    "Semester", "Section Number", "Department/Program", "Course Prefix",
    "Course Number", "Course Title", "Course", "Letter Grade", "",
]
def build_from_csv():
    sources = sorted(ROOT.glob("*.csv"))
    if not sources:
        raise ValueError("No CSV grade exports found in the project root")
    database = ROOT / "ut_grades.db"
    expected_rows = Counter()
    expected_students = Counter()

    def records():
        for source in sources:
            with source.open(encoding="utf-16", newline="") as handle:
                reader = csv.reader(handle, delimiter="\t", strict=True)
                if next(reader) != HEADER:
                    raise ValueError(f"Unexpected header in {source.name}")
                for line, row in enumerate(reader, 2):
                    if len(row) != 9 or not re.fullmatch(
                        r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", row[-1]
                    ):
                        raise ValueError(f"Invalid record: {source.name}:{line}")
                    count = int(row[-1].replace(",", ""))
                    expected_rows[source.name] += 1
                    expected_students[source.name] += count
                    yield (*row[:2], *row[3:8], count)

    section_count, student_count = write_database(records(), database)
    for source in sources:
        print(f"{source.name}: {expected_rows[source.name]:,} rows; "
              f"{expected_students[source.name]:,} student-grade counts")
    print(f"Imported {sum(expected_rows.values()):,} grade records into {section_count:,} section rows.")
    print(f"Created {database.name}; {student_count:,} grade counts verified.")


def migrate(database: Path):
    """Convert an existing database with letter_grade/student_count columns."""
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        records = connection.execute(
            "SELECT semester, section_number, course_prefix, course_number, course_title, "
            "course, letter_grade, student_count FROM grade_distributions ORDER BY rowid"
        ).fetchall()
    before = database.stat().st_size
    sections, total = write_database(records, database)
    print(f"Converted {len(records):,} grade rows to {sections:,} section rows; {total:,} grade counts verified.")
    print(f"Database size: {before / 1048576:.2f} -> {database.stat().st_size / 1048576:.2f} MiB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true", help="Convert the existing database instead of reading CSV files")
    args = parser.parse_args()
    if args.migrate:
        migrate(ROOT / "ut_grades.db")
    else:
        build_from_csv()


if __name__ == "__main__":
    main()
