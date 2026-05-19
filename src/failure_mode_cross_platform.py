#!/usr/bin/env python3
"""
failure_mode_cross_platform.py

Analysis 1: Do specific OpenAlex failure modes correlate with S2 abstract absence?
Analysis 2: What failure modes appear in length-mismatched pairs?
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "output"


def normalize(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def main():
    # ── Load data ───────────────────────────────────────────────────────
    with open(OUT_DIR / "integrity_all_10000.json") as f:
        oa_data = json.load(f)
    oa_by_eid = {e["entry_id"]: e for e in oa_data["entries"]}

    with open(OUT_DIR / "s2_matched_10k.csv") as f:
        s2_rows = list(csv.DictReader(f))
    s2_by_eid = {int(r["entry_id"]): r for r in s2_rows}

    # ── Categorize all 10K papers ───────────────────────────────────────
    categories = {
        "unmatched_in_s2": [],       # not found in S2 at all
        "matched_no_s2_abstract": [], # found but no abstract
        "matched_with_s2_abstract": [],  # found with abstract
    }

    for eid, oa in oa_by_eid.items():
        s2 = s2_by_eid.get(eid)
        if not s2 or s2["match_method"] == "unmatched":
            categories["unmatched_in_s2"].append(oa)
        elif s2["s2_has_abstract"] != "True":
            categories["matched_no_s2_abstract"].append(oa)
        else:
            categories["matched_with_s2_abstract"].append(oa)

    # ════════════════════════════════════════════════════════════════════
    # ANALYSIS 1: Failure modes vs S2 availability
    # ════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("ANALYSIS 1: OpenAlex failure modes vs S2 abstract availability")
    print("=" * 70)

    for cat_name, cat_entries in categories.items():
        n = len(cat_entries)
        valid = sum(1 for e in cat_entries if e["claude_label"] == "Valid")
        rejected = n - valid
        print(f"\n{cat_name} (n={n}):")
        print(f"  Valid:    {valid:>5d} ({valid/n*100:5.1f}%)")
        print(f"  Rejected: {rejected:>5d} ({rejected/n*100:5.1f}%)")

        if rejected > 0:
            modes = Counter(e["failure_mode"] for e in cat_entries if e["claude_label"] != "Valid")
            for mode, count in modes.most_common():
                print(f"    {mode:>40s}: {count:>4d} ({count/rejected*100:5.1f}% of rejected, "
                      f"{count/n*100:5.1f}% of group)")

    # Rejection rate comparison table
    print(f"\n{'':─<70}")
    print(f"Rejection rate comparison:")
    print(f"  {'Category':<30s}  {'N':>6s}  {'Rejected':>8s}  {'Rate':>6s}")
    for cat_name, cat_entries in categories.items():
        n = len(cat_entries)
        rej = sum(1 for e in cat_entries if e["claude_label"] != "Valid")
        print(f"  {cat_name:<30s}  {n:>6d}  {rej:>8d}  {rej/n*100:>5.1f}%")

    # ════════════════════════════════════════════════════════════════════
    # ANALYSIS 2: Failure modes in length-mismatched pairs
    # ════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("ANALYSIS 2: OpenAlex failure modes by length match category")
    print("=" * 70)

    # Build length comparison for papers with abstracts in both
    length_cats = {
        "exact_text_match": [],     # identical after normalization
        "same_length_diff_text": [],  # same length, different text
        "near_identical (>99%)": [],  # length ratio >99% but not identical
        "similar (95-99%)": [],
        "moderate (80-95%)": [],
        "different (50-80%)": [],
        "very_different (<50%)": [],
    }

    for oa in categories["matched_with_s2_abstract"]:
        eid = oa["entry_id"]
        s2 = s2_by_eid[eid]
        oa_abs = normalize(oa["abstract"])
        s2_abs = normalize(s2["s2_abstract"])

        if not oa_abs or not s2_abs:
            continue

        exact = oa_abs.lower() == s2_abs.lower()
        ratio = min(len(oa_abs), len(s2_abs)) / max(len(oa_abs), len(s2_abs))

        entry = {**oa, "len_ratio": ratio, "oa_len": len(oa_abs), "s2_len": len(s2_abs)}

        if exact:
            length_cats["exact_text_match"].append(entry)
        elif ratio == 1.0:
            length_cats["same_length_diff_text"].append(entry)
        elif ratio >= 0.99:
            length_cats["near_identical (>99%)"].append(entry)
        elif ratio >= 0.95:
            length_cats["similar (95-99%)"].append(entry)
        elif ratio >= 0.80:
            length_cats["moderate (80-95%)"].append(entry)
        elif ratio >= 0.50:
            length_cats["different (50-80%)"].append(entry)
        else:
            length_cats["very_different (<50%)"].append(entry)

    print(f"\n{'Category':<30s}  {'N':>5s}  {'Valid':>5s}  {'Rejected':>8s}  {'Rej%':>5s}")
    print("─" * 60)
    for cat_name, cat_entries in length_cats.items():
        n = len(cat_entries)
        if n == 0:
            print(f"{cat_name:<30s}  {0:>5d}")
            continue
        valid = sum(1 for e in cat_entries if e["claude_label"] == "Valid")
        rej = n - valid
        print(f"{cat_name:<30s}  {n:>5d}  {valid:>5d}  {rej:>8d}  {rej/n*100:>5.1f}%")

    # Failure mode breakdown for mismatched pairs (ratio < 0.95)
    mismatched = []
    for cat_name in ["moderate (80-95%)", "different (50-80%)", "very_different (<50%)"]:
        mismatched.extend(length_cats[cat_name])

    print(f"\n{'':─<70}")
    print(f"Failure mode breakdown for significantly mismatched pairs (ratio < 95%, n={len(mismatched)}):")
    if mismatched:
        valid_m = sum(1 for e in mismatched if e["claude_label"] == "Valid")
        rej_m = len(mismatched) - valid_m
        print(f"  Valid in OA:    {valid_m} ({valid_m/len(mismatched)*100:.1f}%)")
        print(f"  Rejected in OA: {rej_m} ({rej_m/len(mismatched)*100:.1f}%)")
        if rej_m:
            modes = Counter(e["failure_mode"] for e in mismatched if e["claude_label"] != "Valid")
            print(f"\n  Failure modes (rejected only):")
            for mode, count in modes.most_common():
                print(f"    {mode:>40s}: {count:>4d} ({count/rej_m*100:5.1f}%)")

        # For valid OA entries with big length diff: which source is longer?
        valid_mismatch = [e for e in mismatched if e["claude_label"] == "Valid"]
        if valid_mismatch:
            s2_longer = sum(1 for e in valid_mismatch if e["s2_len"] > e["oa_len"])
            oa_longer = sum(1 for e in valid_mismatch if e["oa_len"] > e["s2_len"])
            print(f"\n  Among valid OA entries with big length diff (n={len(valid_mismatch)}):")
            print(f"    S2 abstract longer: {s2_longer}")
            print(f"    OA abstract longer: {oa_longer}")


if __name__ == "__main__":
    main()
