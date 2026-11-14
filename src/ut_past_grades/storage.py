"""Shared schema and verified writes for the grade-column database."""
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

GRADES = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "Other")
DETAIL_COLUMNS = ("semester", "section_number", "course_prefix", "course_number", "course_title", "course")
GRADE_COLUMNS_SQL = ", ".join(f'"{grade}"' for grade in GRADES)
SCHEMA = "CREATE TABLE grade_distributions (\n" + ",\n".join([
    *(f"{column} TEXT NOT NULL" for column in DETAIL_COLUMNS),
    *(f'"{grade}" INTEGER NOT NULL DEFAULT 0 CHECK ("{grade}" >= 0)' for grade in GRADES),
]) + "\n);"


def write_database(records, database: Path) -> tuple[int, int]:
    """Pivot (six course fields, letter grade, count) records and replace atomically.

    Identical section details are grouped, and repeated grade counts are added.
    Every resulting section/grade count is verified before replacing the file.
    """
    sections = {}
    for record in records:
        if len(record) != 8:
            raise ValueError("Expected six course fields, a letter grade, and a count")
        *details, grade, count = record
        if grade not in GRADES:
            raise ValueError(f"Unsupported letter grade: {grade!r}")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"Invalid grade count: {count!r}")
        sections.setdefault(tuple(details), Counter())[grade] += count
    if not sections:
        raise ValueError("No grade records to import")
    database = Path(database)
    with tempfile.NamedTemporaryFile(dir=database.parent, prefix=database.name + ".", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.executescript(SCHEMA)
            placeholders = ",".join("?" for _ in range(len(DETAIL_COLUMNS) + len(GRADES)))
            connection.executemany(
                f"INSERT INTO grade_distributions VALUES ({placeholders})",
                ((*details, *(counts.get(grade, 0) for grade in GRADES))
                 for details, counts in sections.items()),
            )
            connection.execute("CREATE INDEX idx_grades_course ON grade_distributions (course_prefix, course_number, semester)")
            connection.execute("CREATE INDEX idx_grades_semester ON grade_distributions (semester)")
            connection.commit()
            actual_rows = 0
            for row in connection.execute("SELECT * FROM grade_distributions"):
                details, counts = row[:6], row[6:]
                if details not in sections or counts != tuple(sections[details].get(grade, 0) for grade in GRADES):
                    raise ValueError("Database grade counts do not match the input")
                actual_rows += 1
            if actual_rows != len(sections):
                raise ValueError("Database section count does not match the input")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed")
        temporary.replace(database)
    finally:
        temporary.unlink(missing_ok=True)
    return len(sections), sum(sum(counts.values()) for counts in sections.values())
