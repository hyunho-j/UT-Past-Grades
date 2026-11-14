"""Parse pasted listings and query grade distributions without modifying SQLite."""
import html
import re
import sqlite3
from contextlib import closing
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "ut_grades.db"
GRADES = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "Other")
TERM = r"(?:Spring|Summer|Fall|Winter)"
SEP = r"[\s|,;:·–—-]*"
ENTRY = re.compile(
    rf"\b(?:(?P<year_first>20\d{{2}})\s+(?P<term_after>{TERM})"
    rf"|(?P<term_first>{TERM})\s+(?P<year_after>20\d{{2}}))\b"
    rf"{SEP}(?P<prefix>[A-Z]{{1,4}})[\s-]*(?P<number>S?\d{{3}}[A-Z]{{0,2}})\b"
    rf"{SEP}(?:(?:section(?:\s+(?:no\.?|number))?|unique(?:\s+number)?)"
    rf"[\s:#.]*)?(?P<section>\d{{1,5}})\b", re.IGNORECASE,
)

@dataclass(frozen=True)
class CourseRequest:
    semester: str
    prefix: str
    number: str
    section: str

    @property
    def label(self):
        return f"{self.semester} · {self.prefix} {self.number} · {self.section}"

def parse_requests(text: str) -> list[CourseRequest]:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    text = text.replace("**", "").replace("`", "")
    requests = []
    for match in ENTRY.finditer(text):
        term = match["term_after"] or match["term_first"]
        year = match["year_first"] or match["year_after"]
        request = CourseRequest(f"{term.title()} {year}", match["prefix"].upper(),
                                match["number"].upper(), str(int(match["section"])))
        if request not in requests:
            requests.append(request)
    return requests

def lookup(text: str, database: Path = DEFAULT_DATABASE, *, combine_sections: bool = False) -> str:
    requests = parse_requests(text)
    if not requests:
        raise ValueError("No course entries found. Include a semester, course, and section together, "
                         "for example: 2026 Spring | HIS 315K | 39345.")
    database = Path(database).resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Database not found: {database}")
    found, missing = [], []
    titles = {}
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        for request in requests:
            rows = connection.execute(
                """SELECT letter_grade, SUM(student_count), course_title FROM grade_distributions
                   WHERE semester = ? AND TRIM(course_prefix) = ?
                     AND TRIM(course_number) = ? AND TRIM(section_number) = ?
                   GROUP BY course_title, letter_grade""",
                (request.semester, request.prefix, request.number, request.section),
            ).fetchall()
            if rows:
                counts = Counter()
                for grade, count, _ in rows:
                    counts[grade] += count
                found.append((request, counts))
                titles[request] = tuple(sorted({title.strip() for _, _, title in rows}))
            else:
                missing.append(request)
    output = []
    if found:
        columns = [(f"{request.semester} · {request.prefix} {request.number}", counts)
                   for request, counts in found]
        if combine_sections:
            groups = {}
            for request, counts in found:
                key = (request.semester, tuple(title.casefold() for title in titles[request]))
                if key not in groups:
                    groups[key] = ([], Counter())
                members, combined = groups[key]
                members.append(request)
                combined.update(counts)
            columns = []
            for members, counts in groups.values():
                first = members[0]
                courses = "/".join(dict.fromkeys(f"{r.prefix} {r.number}" for r in members))
                label = f"{first.semester} · {courses}"
                columns.append((label, counts))
        output.append("Each cell shows count (percentage of the column total).\n")
        table = [["Grade", *(label for label, _ in columns)]]
        totals = [sum(counts.values()) for _, counts in columns]
        extras = sorted({g for _, counts in columns for g in counts} - set(GRADES))
        for grade in (*GRADES, *extras):
            if not any(grade in counts for _, counts in columns):
                continue
            cells = []
            for (_, counts), total in zip(columns, totals):
                count = counts.get(grade, 0)
                cells.append(f"{count:,} ({count / total:.2%})" if total else f"{count:,} (N/A)")
            table.append([grade, *cells])
        table.append(["**Total**", *(f"**{n:,}**" for n in totals)])
        widths = [max(4, *(len(cell) for cell in column)) for column in zip(*table)]
        for index, row in enumerate(table):
            cells = [cell.ljust(width) if column == 0 else cell.rjust(width)
                     for column, (cell, width) in enumerate(zip(row, widths))]
            output.append("| " + " | ".join(cells) + " |")
            if index == 0:
                separators = [":" + "-" * (widths[0] - 1)]
                separators.extend("-" * (width - 1) + ":" for width in widths[1:])
                output.append("| " + " | ".join(separators) + " |")
        output.append("\nPercentages include Other. Grades absent from every requested section are omitted.")
    if missing:
        output.append("\nNo records found for:")
        output.extend(f"- {request.label}" for request in missing)
    output.append(f"\nRecognized {len(requests)} unique course section(s); found {len(found)}.")
    return "\n".join(output)
