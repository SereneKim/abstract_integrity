#!/usr/bin/env python3
"""
prepare_cleaning_tasks.py

Sample 20,000 papers from the 1.08M cleaned background data for human
annotation of abstract quality and language. The human labels serve as
ground truth for tuning cleaning thresholds (e.g. abstract length cutoff,
langid confidence) to optimal F1 scores.

Two independent random samples of 10,000 each (no overlap):
  1. Abstract integrity: Is the abstract complete and meaningful?
  2. Language: Is the content in English?

Usage:
    python prepare_cleaning_tasks.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────

DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "validation_HDBSCAN_KNN_A2" / "data"
)
BG_FULL_PATH = DATA_DIR / (
    "OpenAlex_random_sample_2M_with_titlemeta_titleabs_abstract_new.parquet"
)
CLEANED_PATH = DATA_DIR / "cleaned_for_encoding.parquet"
OUT_DIR = Path(__file__).resolve().parent / "output"

N_PER_SAMPLE = 10_000


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load cleaned IDs (the 1.08M set we want to validate)
    print("Loading cleaned IDs...", flush=True)
    cleaned_ids = set(
        pd.read_parquet(CLEANED_PATH, columns=["id"])["id"]
    )
    print(f"  {len(cleaned_ids):,} cleaned IDs", flush=True)

    # Load 2M file for abstracts and titles, then subset to cleaned
    print("Loading 2M background data (abstracts + titles)...", flush=True)
    bg = pd.read_parquet(BG_FULL_PATH, columns=["id", "title", "abstract"])
    bg = bg[bg["id"].isin(cleaned_ids)].reset_index(drop=True)
    print(f"  {len(bg):,} cleaned papers with abstracts", flush=True)

    # Stats
    bg["abs_len"] = bg["abstract"].fillna("").str.len()
    n_short = (bg["abs_len"] < 60).sum()
    print(f"  Abstracts < 60 chars: {n_short:,} ({n_short/len(bg)*100:.2f}%)")

    # ── 2 independent samples of 1000 (no overlap) ──────────────────────

    rng = np.random.default_rng(42)
    all_indices = rng.permutation(len(bg))

    integrity_idx = all_indices[:N_PER_SAMPLE]
    language_idx = all_indices[N_PER_SAMPLE:2 * N_PER_SAMPLE]

    integrity_df = bg.iloc[integrity_idx]
    language_df = bg.iloc[language_idx]

    assert len(set(integrity_df["id"]) & set(language_df["id"])) == 0

    print(
        f"\nSampled {N_PER_SAMPLE} for integrity, "
        f"{N_PER_SAMPLE} for language (no overlap)",
        flush=True,
    )

    # ── Build integrity task file ────────────────────────────────────────

    integrity_entries = []
    for _, row in integrity_df.iterrows():
        abstract = row["abstract"] if pd.notna(row["abstract"]) else ""
        title = row["title"] if pd.notna(row["title"]) else ""
        integrity_entries.append({
            "paper_id": row["id"],
            "title": title,
            "abstract": abstract,
            "abstract_length": len(abstract),
        })

    rng_shuffle = np.random.default_rng(42)
    order = rng_shuffle.permutation(len(integrity_entries))
    integrity_entries = [integrity_entries[i] for i in order]
    for eid, entry in enumerate(integrity_entries):
        entry["entry_id"] = eid

    integrity_task = {
        "metadata": {
            "test_type": "integrity",
            "description": (
                "Human annotation of abstract quality in the 1.08M "
                "cleaned background set. Ground truth for tuning "
                "abstract length and quality filters."
            ),
            "n_entries": len(integrity_entries),
            "seed": 42,
            "source": "cleaned_for_encoding.parquet (1.08M)",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
        "entries": integrity_entries,
    }

    integrity_path = OUT_DIR / "integrity_tasks.json"
    with open(integrity_path, "w") as f:
        json.dump(integrity_task, f, indent=2, ensure_ascii=False)
    print(f"Wrote {integrity_path} ({len(integrity_entries)} entries)")

    # ── Build language task file ─────────────────────────────────────────

    language_entries = []
    for _, row in language_df.iterrows():
        abstract = row["abstract"] if pd.notna(row["abstract"]) else ""
        title = row["title"] if pd.notna(row["title"]) else ""
        language_entries.append({
            "paper_id": row["id"],
            "title": title,
            "abstract": abstract,
        })

    rng_shuffle_l = np.random.default_rng(43)
    order_l = rng_shuffle_l.permutation(len(language_entries))
    language_entries = [language_entries[i] for i in order_l]
    for eid, entry in enumerate(language_entries):
        entry["entry_id"] = eid

    language_task = {
        "metadata": {
            "test_type": "language",
            "description": (
                "Human annotation of language in the 1.08M cleaned "
                "background set. Ground truth for tuning language "
                "detection filters."
            ),
            "n_entries": len(language_entries),
            "seed": 42,
            "source": "cleaned_for_encoding.parquet (1.08M)",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
        "entries": language_entries,
    }

    language_path = OUT_DIR / "language_tasks.json"
    with open(language_path, "w") as f:
        json.dump(language_task, f, indent=2, ensure_ascii=False)
    print(f"Wrote {language_path} ({len(language_entries)} entries)")

    # ── Summary stats ────────────────────────────────────────────────────

    print("\n── Summary ──")
    for name, entries in [
        ("Integrity", integrity_entries),
        ("Language", language_entries),
    ]:
        abstracts = [e["abstract"] for e in entries]
        n_empty = sum(1 for a in abstracts if not a.strip())
        n_short = sum(1 for a in abstracts if 0 < len(a.strip()) < 60)
        n_normal = sum(1 for a in abstracts if len(a.strip()) >= 60)
        print(f"  {name}: {len(entries)} entries")
        print(f"    Empty: {n_empty}, Short (<60): {n_short}, "
              f"Normal (>=60): {n_normal}")


if __name__ == "__main__":
    main()
