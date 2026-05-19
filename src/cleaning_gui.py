#!/usr/bin/env python3
"""
cleaning_gui.py

Tkinter GUI for human validation of background data cleaning filters.

Two independent modes (1000 entries each, randomly sampled from the
1.08M cleaned background set):
  Integrity: "Is this a complete and meaningful scientific abstract?" (Yes / No)
  Language:  "Is this content in English?" (Yes / No)

Human labels serve as ground truth for tuning cleaning filter thresholds.

Usage:
    python cleaning_gui.py
"""

import argparse
import json
import os
import subprocess
import tempfile
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

DEFAULT_OUT = Path(__file__).resolve().parent / "output"
INTEGRITY_TASK = DEFAULT_OUT / "integrity_tasks.json"
LANGUAGE_TASK = DEFAULT_OUT / "language_tasks.json"

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


class CleaningApp:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.task_data = None
        self.entries = []
        self.mode = None  # "integrity" or "language"
        self.annotator_name = ""
        self.annotations = {}
        self.annotations_path = None
        self.current_index = 0

        self.font_size = BASE_FONT_SIZE
        self.theme = Theme(dark=_macos_is_dark())

        self.root = tk.Tk()
        self.root.title("Background Data Cleaning Validation")
        self.root.geometry("1100x800")
        self.root.minsize(900, 600)
        self.root.configure(bg=self.theme.bg)

        self.style = ttk.Style()
        self._apply_theme()

        # Zoom shortcuts
        self.root.bind("<Command-plus>", lambda e: self._zoom_in())
        self.root.bind("<Command-equal>", lambda e: self._zoom_in())
        self.root.bind("<Command-minus>", lambda e: self._zoom_out())
        self.root.bind("<Control-plus>", lambda e: self._zoom_in())
        self.root.bind("<Control-equal>", lambda e: self._zoom_in())
        self.root.bind("<Control-minus>", lambda e: self._zoom_out())

        self.status_var = tk.StringVar(value="")
        self.progress_label_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)

        self._show_start_frame()

    def _apply_theme(self):
        t = self.theme
        self.style.theme_use("clam")
        self.style.configure(".", background=t.bg, foreground=t.fg,
                             fieldbackground=t.entry_bg)
        self.style.configure("TFrame", background=t.bg)
        self.style.configure("TLabel", background=t.bg, foreground=t.fg)
        self.style.configure("TLabelframe", background=t.bg, foreground=t.fg)
        self.style.configure("TLabelframe.Label", background=t.bg,
                             foreground=t.fg)
        self.style.configure("TButton", background=t.bg, foreground=t.fg)
        self.style.configure("TCheckbutton", background=t.bg, foreground=t.fg)
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

    # ── Start frame ──────────────────────────────────────────────────────

    def _show_start_frame(self):
        self._clear_root()
        t = self.theme

        frame = ttk.Frame(self.root, padding=40)
        frame.pack(expand=True)

        ttk.Label(frame, text="Background Data Cleaning Validation",
                  font=("Helvetica", 20, "bold")).pack(pady=(0, 25))

        # Annotator name
        name_frame = ttk.Frame(frame)
        name_frame.pack(pady=10)
        ttk.Label(name_frame, text="Annotator name:",
                  font=("Helvetica", 12)).pack(side=tk.LEFT, padx=(0, 10))
        self.name_entry = ttk.Entry(name_frame, width=25,
                                    font=("Helvetica", 12))
        self.name_entry.pack(side=tk.LEFT)
        self.name_entry.focus()

        # Mode selection
        ttk.Label(frame, text="Choose test:",
                  font=("Helvetica", 13, "bold")).pack(pady=(20, 10))

        mode_frame = ttk.Frame(frame)
        mode_frame.pack(pady=5)

        integrity_btn = tk.Button(
            mode_frame,
            text="Abstract Integrity\n(Is this a valid abstract?)",
            font=("Helvetica", 13), padx=30, pady=15,
            bg=t.btn_yes_bg, fg="white", activebackground=t.btn_yes_active,
            command=lambda: self._start_mode("integrity"),
        )
        integrity_btn.pack(side=tk.LEFT, padx=15)

        language_btn = tk.Button(
            mode_frame,
            text="Language\n(Is this in English?)",
            font=("Helvetica", 13), padx=30, pady=15,
            bg="#1976D2", fg="white", activebackground="#1565C0",
            command=lambda: self._start_mode("language"),
        )
        language_btn.pack(side=tk.LEFT, padx=15)

        # Resume
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=20)
        ttk.Button(frame, text="Resume from existing file",
                   command=self._on_resume).pack()

        # Instructions
        ttk.Label(
            frame,
            text=(
                "Integrity: 1000 random entries from the cleaned 1.08M "
                "set \u2014 judge if abstract is complete and meaningful\n"
                "Language: 1000 random entries from the cleaned 1.08M "
                "set \u2014 judge if content is in English\n"
                "Annotations serve as ground truth for tuning filter "
                "thresholds\n"
                "Zoom: Cmd+/- or Ctrl+/-"
            ),
            font=("Helvetica", 10), foreground=t.hint_fg, justify=tk.LEFT,
        ).pack(pady=(15, 0))

    def _start_mode(self, mode):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Please enter your name.")
            return

        self.annotator_name = name
        self.mode = mode

        # Load task file
        task_path = INTEGRITY_TASK if mode == "integrity" else LANGUAGE_TASK
        if not task_path.exists():
            messagebox.showerror(
                "Task file missing",
                f"{task_path.name} not found.\n"
                "Run prepare_cleaning_tasks.py first.",
            )
            return

        self._load_task(task_path)
        if not self.entries:
            return

        self.annotations_path = self.output_dir / f"{mode}_{name}.json"

        if self.annotations_path.exists():
            if not messagebox.askyesno(
                "File exists",
                f"{self.annotations_path.name} already exists.\n"
                "Resume from it?",
            ):
                return
            self._load_annotations()
        else:
            self.annotations = {
                "annotator": name,
                "mode": mode,
                "task_file": task_path.name,
                "started": datetime.now(timezone.utc).isoformat(),
                "last_saved": "",
                "answers": {},
            }

        self._go_to_first_unanswered()
        self._show_question()

    def _on_resume(self):
        path = filedialog.askopenfilename(
            initialdir=str(self.output_dir),
            filetypes=[("JSON", "*.json")],
            title="Select annotations file",
        )
        if not path:
            return

        self.annotations_path = Path(path)
        self._load_annotations()

        self.mode = self.annotations.get("mode", "integrity")
        self.annotator_name = self.annotations.get("annotator", "unknown")

        task_path = INTEGRITY_TASK if self.mode == "integrity" else LANGUAGE_TASK
        self._load_task(task_path)
        if not self.entries:
            return

        self._go_to_first_unanswered()
        self._show_question()

    def _load_task(self, path):
        try:
            with open(path) as f:
                self.task_data = json.load(f)
            self.entries = self.task_data["entries"]
            if not self.entries:
                messagebox.showerror("Error", "Task file has no entries.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load task file:\n{e}")
            self.entries = []

    def _load_annotations(self):
        try:
            with open(self.annotations_path) as f:
                self.annotations = json.load(f)
        except Exception as e:
            messagebox.showerror("Error",
                                 f"Could not load annotations:\n{e}")
            self.annotations = {
                "annotator": "unknown", "mode": "integrity",
                "task_file": "", "started": "", "last_saved": "",
                "answers": {},
            }

    def _go_to_first_unanswered(self):
        answers = self.annotations.get("answers", {})
        for i in range(len(self.entries)):
            if str(i) not in answers:
                self.current_index = i
                return
        self.current_index = len(self.entries) - 1

    # ── Question screen ──────────────────────────────────────────────────

    def _show_question(self):
        self._clear_root()
        t = self.theme

        n_total = len(self.entries)
        n_done = len(self.annotations.get("answers", {}))

        # Top bar
        top = ttk.Frame(self.root, padding=(10, 5))
        top.pack(fill=tk.X)

        mode_label = ("Abstract Integrity" if self.mode == "integrity"
                       else "Language")
        self.progress_label_var.set(
            f"{mode_label}  —  Entry {self.current_index + 1} / {n_total}"
        )
        ttk.Label(top, textvariable=self.progress_label_var,
                  font=self._font(bold=True)).pack(side=tk.LEFT, padx=(0, 10))

        self.progress_var.set(n_done)
        ttk.Progressbar(top, variable=self.progress_var,
                        maximum=n_total, length=180).pack(
            side=tk.LEFT, padx=(0, 10))

        ttk.Label(top, text=f"{n_done}/{n_total} answered",
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

        # Content
        entry = self.entries[self.current_index]

        content = ttk.Frame(self.root, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Show title (both modes)
        ttk.Label(content, text="Title:",
                  font=self._font(bold=True)).pack(
            anchor=tk.W, pady=(0, 3))

        title_frame = tk.Frame(content, bg=t.title_bg, padx=15, pady=10,
                               relief=tk.GROOVE, borderwidth=1)
        title_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            title_frame, text=entry.get("title", "(no title)"),
            font=self._font(1, bold=True),
            bg=t.title_bg, fg=t.title_fg,
            wraplength=950, justify=tk.LEFT,
        ).pack(anchor=tk.W)

        # Show abstract
        ttk.Label(content, text="Abstract:",
                  font=self._font(bold=True)).pack(anchor=tk.W, pady=(0, 5))

        text_frame = ttk.Frame(content)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        abstract_text = entry.get("abstract", "")
        if not abstract_text.strip():
            abstract_text = "(empty — no abstract available)"

        text_w = tk.Text(
            text_frame, wrap=tk.WORD, font=self._font(),
            padx=12, pady=10,
            bg=t.text_bg, fg=t.fg,
            relief=tk.GROOVE, borderwidth=1,
            insertbackground=t.fg,
        )
        text_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                    command=text_w.yview)
        text_w.configure(yscrollcommand=text_scroll.set)
        text_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_w.insert("1.0", abstract_text)
        text_w.configure(state=tk.DISABLED)

        # Question + buttons
        ttk.Separator(content, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10)

        if self.mode == "integrity":
            question = ("Is this a complete and meaningful scientific "
                        "abstract?")
        else:
            question = "Is this content in English?"

        ttk.Label(
            content, text=question,
            font=self._font(2, bold=True),
        ).pack(anchor=tk.W, pady=(0, 15))

        # Previous answer indicator
        prev_answer = self.annotations.get("answers", {}).get(
            str(self.current_index))

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

        self.root.bind("y", lambda e: self._on_answer(True))
        self.root.bind("n", lambda e: self._on_answer(False))

        # Bottom status
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)
        bottom = ttk.Frame(self.root, padding=(10, 5))
        bottom.pack(fill=tk.X)

        hint = "Keyboard: Y = Yes, N = No"
        if prev_answer is not None:
            prev_str = "Yes" if prev_answer.get("answer") else "No"
            hint += (f"  |  Previously answered: {prev_str} "
                     "(answering again will overwrite)")

        ttk.Label(bottom, text=hint,
                  font=self._font(-3), foreground=t.hint_fg).pack(
            side=tk.LEFT)

        self.status_var.set("")
        ttk.Label(bottom, textvariable=self.status_var,
                  font=self._font(-3), foreground=t.hint_fg).pack(
            side=tk.RIGHT)

    def _on_answer(self, answer):
        self.root.unbind("y")
        self.root.unbind("n")

        key = str(self.current_index)
        self.annotations.setdefault("answers", {})[key] = {
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._save_to_disk()

        # Advance
        if self.current_index < len(self.entries) - 1:
            self.current_index += 1
            self._show_question()
        else:
            n_done = len(self.annotations.get("answers", {}))
            if n_done >= len(self.entries):
                messagebox.showinfo("Done", "All questions answered!")
            else:
                self._go_to_first_unanswered()
                self._show_question()

    # ── Navigation ───────────────────────────────────────────────────────

    def _go_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._show_question()

    def _skip_to_unanswered(self):
        answers = self.annotations.get("answers", {})
        start = self.current_index + 1
        for i in range(start, len(self.entries)):
            if str(i) not in answers:
                self.current_index = i
                self._show_question()
                return
        for i in range(0, start):
            if str(i) not in answers:
                self.current_index = i
                self._show_question()
                return
        self.status_var.set("All questions answered!")

    def _go_jump(self):
        try:
            target = int(self.jump_entry.get()) - 1
        except ValueError:
            self.status_var.set("Enter a valid number.")
            return
        if 0 <= target < len(self.entries):
            self.current_index = target
            self._show_question()
        else:
            self.status_var.set(
                f"Must be between 1 and {len(self.entries)}.")

    # ── Persistence ──────────────────────────────────────────────────────

    def _save_to_disk(self):
        self.annotations["last_saved"] = datetime.now(timezone.utc).isoformat()
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.output_dir), suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(self.annotations, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.annotations_path)
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
        description="Background Data Cleaning Validation GUI")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    app = CleaningApp(Path(args.output_dir))
    app.run()


if __name__ == "__main__":
    main()
