#!/usr/bin/env python3
"""
compare_abstract_lengths.py

Compare normalized abstract lengths between OpenAlex and Semantic Scholar
for the 3,518 papers that have abstracts in both sources.
"""

import csv
import json
import re
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "output"


def normalize(text):
    """Strip and collapse all whitespace to single spaces."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def main():
    # Load OpenAlex abstracts (keyed by entry_id)
    with open(OUT_DIR / "integrity_all_10000.json") as f:
        oa_data = json.load(f)
    oa_abstracts = {e["entry_id"]: e["abstract"] for e in oa_data["entries"]}

    # Load S2 matched data
    with open(OUT_DIR / "s2_matched_10k.csv") as f:
        reader = csv.DictReader(f)
        s2_rows = list(reader)

    # Filter to papers with abstracts in both
    pairs = []
    for row in s2_rows:
        if row["s2_has_abstract"] != "True":
            continue
        eid = int(row["entry_id"])
        oa_abs = normalize(oa_abstracts.get(eid, ""))
        s2_abs = normalize(row["s2_abstract"])
        if oa_abs and s2_abs:
            pairs.append({
                "entry_id": eid,
                "paper_id": row["paper_id"],
                "doi": row["doi"],
                "oa_len": len(oa_abs),
                "s2_len": len(s2_abs),
                "len_diff": len(s2_abs) - len(oa_abs),
                "len_ratio": min(len(oa_abs), len(s2_abs)) / max(len(oa_abs), len(s2_abs)),
                "exact_match": oa_abs.lower() == s2_abs.lower(),
            })

    print(f"Papers with abstracts in both sources: {len(pairs)}\n")

    # ── Exact match ─────────────────────────────────────────────────────
    exact = sum(1 for p in pairs if p["exact_match"])
    print(f"Exact match (case-insensitive, normalized): {exact} ({exact/len(pairs)*100:.1f}%)")
    print(f"Different: {len(pairs) - exact} ({(len(pairs)-exact)/len(pairs)*100:.1f}%)\n")

    # ── Length ratio distribution ───────────────────────────────────────
    buckets = {
        "identical length": (1.0, 1.0),
        ">99% ratio": (0.99, 1.0),
        "95-99%": (0.95, 0.99),
        "80-95%": (0.80, 0.95),
        "50-80%": (0.50, 0.80),
        "<50%": (0.0, 0.50),
    }

    print("Length ratio distribution (min/max):")
    for label, (lo, hi) in buckets.items():
        if label == "identical length":
            n = sum(1 for p in pairs if p["len_ratio"] == 1.0)
        elif label == ">99% ratio":
            n = sum(1 for p in pairs if 0.99 <= p["len_ratio"] < 1.0)
        else:
            n = sum(1 for p in pairs if lo <= p["len_ratio"] < hi)
        print(f"  {label:>20s}: {n:>5d} ({n/len(pairs)*100:5.1f}%)")

    # ── Length difference stats ─────────────────────────────────────────
    diffs = [p["len_diff"] for p in pairs]
    diffs_abs = [abs(d) for d in diffs]
    s2_longer = sum(1 for d in diffs if d > 0)
    oa_longer = sum(1 for d in diffs if d < 0)
    same_len = sum(1 for d in diffs if d == 0)

    print(f"\nLength difference (S2 - OA):")
    print(f"  S2 longer:  {s2_longer}")
    print(f"  OA longer:  {oa_longer}")
    print(f"  Same length: {same_len}")
    print(f"  Mean abs diff: {sum(diffs_abs)/len(diffs_abs):.1f} chars")
    print(f"  Median abs diff: {sorted(diffs_abs)[len(diffs_abs)//2]} chars")

    # ── Biggest outliers ────────────────────────────────────────────────
    pairs_sorted = sorted(pairs, key=lambda p: p["len_ratio"])
    print(f"\nTop 10 most different by length ratio:")
    print(f"  {'entry_id':>8s}  {'OA_len':>6s}  {'S2_len':>6s}  {'ratio':>6s}  {'diff':>6s}")
    for p in pairs_sorted[:10]:
        print(f"  {p['entry_id']:>8d}  {p['oa_len']:>6d}  {p['s2_len']:>6d}  "
              f"{p['len_ratio']:>6.3f}  {p['len_diff']:>+6d}")

    # ── Save full comparison ────────────────────────────────────────────
    out_path = OUT_DIR / "s2_oa_length_comparison.csv"
    fieldnames = ["entry_id", "paper_id", "doi", "oa_len", "s2_len", "len_diff", "len_ratio", "exact_match"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pairs)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
