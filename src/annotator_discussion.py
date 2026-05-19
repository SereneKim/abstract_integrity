#!/usr/bin/env python3
"""
annotator_discussion.py

Tkinter GUI for resolving inter-annotator disagreements on the abstract
integrity task.  Loads all four annotators' answers (A1, A2,
Claude Opus 4.6, Codex GPT-5.4) for the first N entries, shows every
entry where at least one annotator disagrees, and lets the annotators
jointly decide Yes / No with an optional comment.

Usage:
    python annotator_discussion.py
    python annotator_discussion.py --n 1000
"""

import argparse
import json
import os
import subprocess
import tempfile
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk

DEFAULT_OUT = Path(__file__).resolve().parent / "output"
INTEGRITY_TASK = DEFAULT_OUT / "integrity_tasks.json"
A1_FILE = DEFAULT_OUT / "integrity_A1.json"
A2_FILE = DEFAULT_OUT / "integrity_A2.json"
CLAUDE_FILE = DEFAULT_OUT / "integrity_claude.json"
CODEX_FILE = DEFAULT_OUT / "integrity_Codex_GPT54_first1000.json"
DISCUSSION_FILE = DEFAULT_OUT / "integrity_discussion.json"

ANNOTATOR_FILES = [
    ("A1", A1_FILE),
    ("A2", A2_FILE),
    ("Claude", CLAUDE_FILE),
    ("Codex", CODEX_FILE),
]

BASE_FONT_SIZE = 13
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 22


# ── Dark mode detection ──────────────────────────────────────────────────

def _macos_is_dark():
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return False


class Theme:
    def __init__(self, dark=False):
        self.dark = dark
        if dark:
            self.bg = "#1E1E1E"
            self.fg = "#E0E0E0"
            self.entry_bg = "#2A2A2A"
            self.entry_fg = "#E0E0E0"
            self.text_bg = "#2C2C1E"
            self.title_bg = "#2A2A3A"
            self.title_fg = "#E0E0E0"
            self.btn_yes_bg = "#2E7D32"
            self.btn_yes_active = "#388E3C"
            self.btn_no_bg = "#C62828"
            self.btn_no_active = "#D32F2F"
            self.hint_fg = "#888888"
            self.disagree_fg = "#FFB74D"
        else:
            self.bg = "#FFFFFF"
            self.fg = "#000000"
            self.entry_bg = "#FFFFFF"
            self.entry_fg = "#000000"
            self.text_bg = "#F5F5EA"
            self.title_bg = "#E8E8F8"
            self.title_fg = "#000000"
            self.btn_yes_bg = "#4CAF50"
            self.btn_yes_active = "#45A049"
            self.btn_no_bg = "#F44336"
            self.btn_no_active = "#E53935"
            self.hint_fg = "gray"
            self.disagree_fg = "#E65100"


class DiscussionApp:
    def __init__(self, n_entries: int):
        self.n_entries = n_entries
        self.font_size = BASE_FONT_SIZE
        self.theme = Theme(dark=_macos_is_dark())

        self.entries = []          # task entries (only disagreements)
        self.disagreements = []    # list of (entry_id, entry, votes_dict)
        self.discussion = {}       # loaded/saved discussion JSON
        self.current_pos = 0       # position within self.disagreements

        self.root = tk.Tk()
        self.root.title("Annotator Discussion — Disagreements")
        self.root.geometry("1100x850")
        self.root.minsize(900, 650)
        self.root.configure(bg=self.theme.bg)

        self.style = ttk.Style()
        self._apply_theme()

        self.root.bind("<Command-plus>", lambda e: self._zoom_in())
        self.root.bind("<Command-equal>", lambda e: self._zoom_in())
        self.root.bind("<Command-minus>", lambda e: self._zoom_out())
        self.root.bind("<Control-plus>", lambda e: self._zoom_in())
        self.root.bind("<Control-equal>", lambda e: self._zoom_in())
        self.root.bind("<Control-minus>", lambda e: self._zoom_out())

        self.status_var = tk.StringVar(value="")
        self.progress_label_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)

        if not self._load_data():
            return

        self._load_discussion()
        self._go_to_first_unanswered()
        self._show_question()

    def _apply_theme(self):
        t = self.theme
        self.style.theme_use("clam")
        self.style.configure(".", background=t.bg, foreground=t.fg,
                             fieldbackground=t.entry_bg)
        self.style.configure("TFrame", background=t.bg)
        self.style.configure("TLabel", background=t.bg, foreground=t.fg)
        self.style.configure("TButton", background=t.bg, foreground=t.fg)
        self.style.configure("TSeparator", background=t.bg)
        self.style.configure("TEntry", fieldbackground=t.entry_bg,
                             foreground=t.entry_fg)
        self.style.configure("Horizontal.TProgressbar", background="#4CAF50",
                             troughcolor=t.entry_bg)

    def run(self):
        self.root.mainloop()

    # ── Fonts / zoom ─────────────────────────────────────────────────────

    def _font(self, size_delta=0, bold=False):
        weight = "bold" if bold else "normal"
        return ("Helvetica", self.font_size + size_delta, weight)

    def _zoom_in(self):
        if self.font_size < MAX_FONT_SIZE:
            self.font_size += 1
            self._show_question()

    def _zoom_out(self):
        if self.font_size > MIN_FONT_SIZE:
            self.font_size -= 1
            self._show_question()

    # ── Data loading ─────────────────────────────────────────────────────

    def _load_data(self):
        # Check task file exists
        if not INTEGRITY_TASK.exists():
            messagebox.showerror("Missing file",
                                 f"Task file not found:\n{INTEGRITY_TASK}")
            return False

        # Load all annotator files that exist
        annotator_answers = {}  # name -> {str(entry_id): bool}
        for name, path in ANNOTATOR_FILES:
            if not path.exists():
                messagebox.showwarning("Missing file",
                                       f"{name} annotations not found:\n{path}\n"
                                       f"Skipping this annotator.")
                continue
            with open(path) as f:
                data = json.load(f)
            annotator_answers[name] = {
                k: v["answer"] for k, v in data["answers"].items()
            }

        if len(annotator_answers) < 2:
            messagebox.showerror("Not enough annotators",
                                 "Need at least 2 annotator files.")
            return False

        self.annotator_names = list(annotator_answers.keys())

        with open(INTEGRITY_TASK) as f:
            task_data = json.load(f)
        all_entries = {e["entry_id"]: e for e in task_data["entries"]}

        self.disagreements = []
        for i in range(self.n_entries):
            key = str(i)
            votes = {}
            for name in self.annotator_names:
                if key in annotator_answers[name]:
                    votes[name] = annotator_answers[name][key]
            if len(votes) < 2:
                continue
            # Disagreement = not all votes the same
            unique_votes = set(votes.values())
            if len(unique_votes) > 1:
                self.disagreements.append((i, all_entries[i], votes))

        if not self.disagreements:
            messagebox.showinfo("No disagreements",
                                f"No disagreements found in the first "
                                f"{self.n_entries} entries.")
            return False

        return True

    def _load_discussion(self):
        if DISCUSSION_FILE.exists():
            with open(DISCUSSION_FILE) as f:
                self.discussion = json.load(f)
        else:
            self.discussion = {
                "description": "Joint resolution of integrity disagreements",
                "n_entries": self.n_entries,
                "started": datetime.now(timezone.utc).isoformat(),
                "last_saved": "",
                "answers": {},
            }

    def _go_to_first_unanswered(self):
        answers = self.discussion.get("answers", {})
        for pos, (entry_id, _, _) in enumerate(self.disagreements):
            if str(entry_id) not in answers:
                self.current_pos = pos
                return
        self.current_pos = 0

    # ── Question screen ──────────────────────────────────────────────────

    def _show_question(self):
        self._clear_root()
        t = self.theme

        n_total = len(self.disagreements)
        n_done = sum(1 for eid, _, _ in self.disagreements
                     if str(eid) in self.discussion.get("answers", {}))

        entry_id, entry, votes = self.disagreements[self.current_pos]

        # ── Top bar ──────────────────────────────────────────────────────
        top = ttk.Frame(self.root, padding=(10, 5))
        top.pack(fill=tk.X)

        self.progress_label_var.set(
            f"Disagreement {self.current_pos + 1} / {n_total}  "
            f"(entry {entry_id})")
        ttk.Label(top, textvariable=self.progress_label_var,
                  font=self._font(bold=True)).pack(side=tk.LEFT, padx=(0, 10))

        self.progress_var.set(n_done)
        ttk.Progressbar(top, variable=self.progress_var,
                        maximum=n_total, length=180).pack(
            side=tk.LEFT, padx=(0, 10))

        ttk.Label(top, text=f"{n_done}/{n_total} resolved",
                  font=self._font(-2)).pack(side=tk.LEFT, padx=(0, 15))

        ttk.Separator(top, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        # Navigation
        ttk.Button(top, text="<< Prev", command=self._go_prev).pack(
            side=tk.LEFT, padx=3)
        ttk.Button(top, text="Skip >>",
                   command=self._skip_to_unanswered).pack(
            side=tk.LEFT, padx=3)

        ttk.Separator(top, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(top, text="Go to:", font=self._font(-2)).pack(side=tk.LEFT)
        self.jump_entry = ttk.Entry(top, width=6)
        self.jump_entry.pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="Go", command=self._go_jump).pack(
            side=tk.LEFT, padx=3)
        self.jump_entry.bind("<Return>", lambda e: self._go_jump())

        ttk.Separator(top, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(top, text="A-", width=3, command=self._zoom_out).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(top, text="A+", width=3, command=self._zoom_in).pack(
            side=tk.LEFT, padx=2)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # ── Content area ─────────────────────────────────────────────────
        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Annotator votes — show all four with color coding
        vote_frame = ttk.Frame(content)
        vote_frame.pack(anchor=tk.W, pady=(0, 10))
        for name in self.annotator_names:
            if name not in votes:
                continue
            ans = votes[name]
            label_text = f"  {name}: {'Yes' if ans else 'No'}  "
            fg = t.btn_yes_bg if ans else t.btn_no_bg
            tk.Label(vote_frame, text=label_text,
                     font=self._font(0, bold=True),
                     bg=t.bg, fg=fg).pack(side=tk.LEFT, padx=(0, 6))

        # Title
        ttk.Label(content, text="Title:",
                  font=self._font(bold=True)).pack(anchor=tk.W, pady=(0, 3))

        title_frame = tk.Frame(content, bg=t.title_bg, padx=15, pady=10,
                               relief=tk.GROOVE, borderwidth=1)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            title_frame, text=entry.get("title", "(no title)"),
            font=self._font(1, bold=True),
            bg=t.title_bg, fg=t.title_fg,
            wraplength=950, justify=tk.LEFT,
        ).pack(anchor=tk.W)

        # Abstract
        ttk.Label(content, text="Abstract:",
                  font=self._font(bold=True)).pack(anchor=tk.W, pady=(0, 5))

        text_frame = ttk.Frame(content)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        abstract_text = entry.get("abstract", "")
        if not abstract_text.strip():
            abstract_text = "(empty — no abstract available)"

        text_w = tk.Text(
            text_frame, wrap=tk.WORD, font=self._font(),
            padx=12, pady=10,
            bg=t.text_bg, fg=t.fg,
            relief=tk.GROOVE, borderwidth=1,
            insertbackground=t.fg, height=8,
        )
        text_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                    command=text_w.yview)
        text_w.configure(yscrollcommand=text_scroll.set)
        text_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_w.insert("1.0", abstract_text)
        text_w.configure(state=tk.DISABLED)

        # ── Question + comment + buttons ─────────────────────────────────
        ttk.Separator(content, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        ttk.Label(
            content,
            text="Is this a complete and meaningful scientific abstract?",
            font=self._font(2, bold=True),
        ).pack(anchor=tk.W, pady=(0, 8))

        # Comment field
        comment_row = ttk.Frame(content)
        comment_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(comment_row, text="Comment (optional):",
                  font=self._font(-1)).pack(side=tk.LEFT, padx=(0, 8))
        self.comment_entry = tk.Entry(
            comment_row, font=self._font(-1),
            bg=t.entry_bg, fg=t.entry_fg,
            insertbackground=t.fg, relief=tk.GROOVE, borderwidth=1,
        )
        self.comment_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Pre-fill comment if previously answered
        prev = self.discussion.get("answers", {}).get(str(entry_id))
        if prev and prev.get("comment"):
            self.comment_entry.insert(0, prev["comment"])

        # Buttons
        btn_frame = ttk.Frame(content)
        btn_frame.pack(pady=5)

        tk.Button(
            btn_frame, text="Yes", font=self._font(2, bold=True),
            bg=t.btn_yes_bg, fg="white", activebackground=t.btn_yes_active,
            padx=50, pady=15, relief=tk.RAISED, borderwidth=2,
            command=lambda: self._on_answer(True),
        ).pack(side=tk.LEFT, padx=20)

        tk.Button(
            btn_frame, text="No", font=self._font(2, bold=True),
            bg=t.btn_no_bg, fg="white", activebackground=t.btn_no_active,
            padx=50, pady=15, relief=tk.RAISED, borderwidth=2,
            command=lambda: self._on_answer(False),
        ).pack(side=tk.LEFT, padx=20)

        # Only fire Y/N shortcuts when focus is NOT in the comment field
        def _key_yes(e):
            if e.widget != self.comment_entry:
                self._on_answer(True)
        def _key_no(e):
            if e.widget != self.comment_entry:
                self._on_answer(False)
        self.root.bind("y", _key_yes)
        self.root.bind("n", _key_no)

        # ── Bottom status ────────────────────────────────────────────────
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)
        bottom = ttk.Frame(self.root, padding=(10, 5))
        bottom.pack(fill=tk.X)

        hint = "Keyboard: Y = Yes, N = No"
        if prev is not None:
            prev_str = "Yes" if prev.get("answer") else "No"
            hint += (f"  |  Previously resolved: {prev_str} "
                     "(answering again will overwrite)")

        ttk.Label(bottom, text=hint,
                  font=self._font(-3), foreground=t.hint_fg).pack(
            side=tk.LEFT)

        self.status_var.set("")
        ttk.Label(bottom, textvariable=self.status_var,
                  font=self._font(-3), foreground=t.hint_fg).pack(
            side=tk.RIGHT)

    # ── Answer handling ──────────────────────────────────────────────────

    def _on_answer(self, answer):
        self.root.unbind("y")
        self.root.unbind("n")

        entry_id, _, votes = self.disagreements[self.current_pos]
        comment = self.comment_entry.get().strip()

        record = {
            "answer": answer,
            "original_votes": votes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if comment:
            record["comment"] = comment

        self.discussion.setdefault("answers", {})[str(entry_id)] = record
        self._save_to_disk()

        # Advance
        if self.current_pos < len(self.disagreements) - 1:
            self.current_pos += 1
            self._show_question()
        else:
            n_done = sum(1 for eid, _, _ in self.disagreements
                         if str(eid) in self.discussion.get("answers", {}))
            if n_done >= len(self.disagreements):
                messagebox.showinfo("Done",
                                    "All disagreements have been resolved!")
            else:
                self._go_to_first_unanswered()
                self._show_question()

    # ── Navigation ───────────────────────────────────────────────────────

    def _go_prev(self):
        if self.current_pos > 0:
            self.current_pos -= 1
            self._show_question()

    def _skip_to_unanswered(self):
        answers = self.discussion.get("answers", {})
        start = self.current_pos + 1
        n = len(self.disagreements)
        for offset in range(n):
            pos = (start + offset) % n
            entry_id = self.disagreements[pos][0]
            if str(entry_id) not in answers:
                self.current_pos = pos
                self._show_question()
                return
        self.status_var.set("All disagreements resolved!")

    def _go_jump(self):
        try:
            target = int(self.jump_entry.get()) - 1
        except ValueError:
            self.status_var.set("Enter a valid number.")
            return
        if 0 <= target < len(self.disagreements):
            self.current_pos = target
            self._show_question()
        else:
            self.status_var.set(
                f"Must be between 1 and {len(self.disagreements)}.")

    # ── Persistence ──────────────────────────────────────────────────────

    def _save_to_disk(self):
        self.discussion["last_saved"] = datetime.now(timezone.utc).isoformat()
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(DEFAULT_OUT), suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(self.discussion, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, DISCUSSION_FILE)
        except Exception as e:
            self.status_var.set(f"Save error: {e}")

    # ── Helpers ──────────────────────────────────────────────────────────

    def _clear_root(self):
        try:
            self.root.unbind("y")
            self.root.unbind("n")
        except Exception:
            pass
        for w in self.root.winfo_children():
            w.destroy()


def main():
    parser = argparse.ArgumentParser(
        description="Annotator Discussion GUI — resolve disagreements")
    parser.add_argument("--n", type=int, default=1000,
                        help="Number of entries to compare (default: 1000)")
    args = parser.parse_args()

    app = DiscussionApp(n_entries=args.n)
    app.run()


if __name__ == "__main__":
    main()
