# UT-Past-Grades

Launch the desktop app:

```powershell
uv run main.py
```

Paste course listings into the large text box and click **Get distributions**
(or press **Ctrl+Enter**). The buttons at the top also let you paste from the
clipboard, copy results as Markdown, and clear both text areas.

Toggle **Combine sections** at the top to merge the requested sections with the
same database course title and semester. The results refresh immediately. Counts
are added and percentages are recalculated from the combined total. Toggle it
off to return to individual sections. Only sections in the pasted input are included.

The app accepts Markdown tables or plain text, for example:

```text
| 2026 Spring | HIS 315K | 39345 |
| 2025 Spring | HIS 315K | 38960 | The United States, 1492-1865. | Rachel Ozanne |
Spring 2026 HIS 315K 39340
```

Use either `2026 Spring` or `Spring 2026`. Each entry needs the semester, course,
and section in that order. Extra columns and trailing links are ignored.
Repeated entries appear once. Check the recognized section count below the
results; text without a recognizable entry is ignored. Sections with no database
records are listed explicitly.

Results compare grade counts and percentages across sections, with totals.
Percentages include the source's `Other` category. The app reads `ut_grades.db`
beside `main.py` without modifying it. It uses Python's standard library,
including Tkinter for the window.

For command-line output instead of a window:

```powershell
uv run main.py --text "2026 Spring | HIS 315K | 39345"
uv run main.py --file courses.txt
uv run main.py --file courses.txt --combine-sections
```

Use `--database path/to/ut_grades.db` to select another database.
You can also run `python main.py` with a Python installation that includes Tkinter.

Run verification with `python -m unittest discover -s tests -v`.
Rebuild the combined database from all CSV grade exports in the project root with
`python build_database.py`.

The database omits the unused `department_program` column from the CSV exports
and retains `course`. Each row stores a course section and semester, with integer
count columns `A+`, `A`, `A-`, `B+`, `B`, `B-`, `C+`, `C`, `C-`, `D+`, `D`, `D-`,
`F`, and `Other`. Missing grades default to zero. Duplicate counts for the same
section details and grade are added. Section numbers and semesters remain text.
Use double quotes for grade names in SQL, for example `SELECT "A-" FROM grade_distributions`.

To convert an older database that uses `letter_grade` and `student_count` columns
without the original CSV files, run `python build_database.py --migrate` once.
The conversion verifies every section's grade counts before replacing the database.
