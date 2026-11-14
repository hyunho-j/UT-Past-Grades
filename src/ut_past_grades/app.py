"""Desktop paste interface and optional command-line mode."""
import argparse
import sqlite3
from pathlib import Path
from .lookup import DEFAULT_DATABASE, lookup

def launch_gui(database: Path, *, combine_sections: bool = False):
    try:
        import tkinter as tk
    except ImportError as error:
        raise RuntimeError("The desktop window requires Python with Tkinter installed.") from error
    from tkinter import messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(
            "The desktop window could not start. Check this Python installation's "
            "Tcl/Tk support. You can still use --text or --file for command-line output. "
            f"Details: {error}"
        ) from error
    root.title("UT Grade Distributions")
    root.geometry("1200x800")
    root.minsize(700, 500)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    toolbar = ttk.Frame(root, padding=10)
    toolbar.grid(row=0, column=0, sticky="ew")
    panels = ttk.Panedwindow(root, orient=tk.VERTICAL)
    panels.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
    input_frame = ttk.Labelframe(panels, text="Paste course listings or Markdown tables", padding=8)
    output_frame = ttk.Labelframe(panels, text="Grade distributions (Markdown)", padding=8)
    panels.add(input_frame, weight=1)
    panels.add(output_frame, weight=2)
    entry = ScrolledText(input_frame, wrap=tk.WORD, height=12, undo=True)
    entry.pack(fill=tk.BOTH, expand=True)
    result = ScrolledText(output_frame, wrap=tk.NONE, height=20, state=tk.DISABLED,
                         font="TkFixedFont")
    result.pack(fill=tk.BOTH, expand=True)
    horizontal = ttk.Scrollbar(output_frame, orient=tk.HORIZONTAL, command=result.xview)
    horizontal.pack(fill=tk.X)
    result.configure(xscrollcommand=horizontal.set)
    status = tk.StringVar(value="Example: 2026 Spring | HIS 315K | 39345")
    combine = tk.BooleanVar(value=combine_sections)
    ttk.Label(root, textvariable=status, padding=(10, 0, 10, 10)).grid(row=2, column=0, sticky="w")

    def show_output(text):
        result.configure(state=tk.NORMAL)
        result.delete("1.0", tk.END)
        result.insert("1.0", text)
        result.configure(state=tk.DISABLED)

    def run_lookup(event=None):
        try:
            text = lookup(entry.get("1.0", "end-1c"), database,
                          combine_sections=combine.get())
        except (ValueError, OSError, sqlite3.Error) as error:
            show_output(str(error))
            status.set("Lookup failed. Check the input or database.")
        else:
            show_output(text)
            status.set(text.splitlines()[-1])
        return "break"

    def paste():
        try:
            text = root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Paste", "The clipboard does not contain text.")
            return
        entry.delete("1.0", tk.END)
        entry.insert("1.0", text)
        entry.focus_set()

    def clear():
        entry.delete("1.0", tk.END)
        show_output("")
        status.set("Paste course listings, then click Get distributions.")
        entry.focus_set()

    def copy():
        text = result.get("1.0", "end-1c")
        if text:
            root.clipboard_clear()
            root.clipboard_append(text)
            status.set("Results copied as Markdown.")

    for label, command in [("Paste", paste), ("Get distributions", run_lookup),
                           ("Copy results", copy), ("Clear", clear)]:
        ttk.Button(toolbar, text=label, command=command).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Checkbutton(toolbar, text="Combine sections", variable=combine,
                    style="Toolbutton",
                    command=lambda: run_lookup() if entry.get("1.0", "end-1c").strip() else None,
                    ).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(toolbar, text="Ctrl+Enter to look up").pack(side=tk.LEFT, padx=8)
    root.bind("<Control-Return>", run_lookup)
    entry.focus_set()
    root.mainloop()

def main():
    parser = argparse.ArgumentParser(description="Look up grade distributions from pasted UT course listings.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--combine-sections", action="store_true",
                        help="Combine requested sections with the same course title and semester")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--text", help="Print results for this text instead of opening a window")
    inputs.add_argument("--file", type=Path, help="Read course listings from a UTF-8 text file")
    args = parser.parse_args()
    if args.text is not None or args.file is not None:
        try:
            text = args.text if args.text is not None else args.file.read_text(encoding="utf-8-sig")
            print(lookup(text, args.database, combine_sections=args.combine_sections))
        except (ValueError, OSError, sqlite3.Error) as error:
            parser.exit(1, f"Error: {error}\n")
    else:
        try:
            launch_gui(args.database, combine_sections=args.combine_sections)
        except RuntimeError as error:
            parser.exit(1, f"Error: {error}\n")
