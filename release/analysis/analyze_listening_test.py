#!/usr/bin/env python3
"""Listening test (N = 20, blind): Friedman per question + Bonferroni-corrected
Wilcoxon signed-rank post-hocs on per-listener condition means.

Input : data/listening_test/ratings.csv  (pid, clip, condition, Q1..Q4; 5-point)
Output: results/listening_test_stats.json

Conditions: baseline = stereo pan, nodepth = HRTF direction only,
            proposed = HRTF direction + d_rel distance cue.
Questions : Q1 direction match, Q2 naturalness, Q3 distance realism, Q4 overall.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data/listening_test/ratings.csv"
OUT = REPO / "results/listening_test_stats.json"

CONDITIONS = ["proposed", "nodepth", "baseline"]
QUESTIONS = ["Q1", "Q2", "Q3", "Q4"]
PAIRS = [("proposed", "nodepth"), ("proposed", "baseline"), ("nodepth", "baseline")]


def main():
    cells = defaultdict(list)  # (pid, cond, q) -> ratings over clips
    for r in csv.DictReader(open(RAW)):
        for q in QUESTIONS:
            if r[q] != "":
                cells[(r["pid"], r["condition"], q)].append(float(r[q]))
    pids = sorted({k[0] for k in cells})

    def means(c, q):
        return np.array([np.mean(cells[(p, c, q)]) for p in pids])

    out = {"n_listeners": len(pids), "questions": {}}
    for q in QUESTIONS:
        chi2, p_f = stats.friedmanchisquare(*(means(c, q) for c in CONDITIONS))
        post = {}
        for a, b in PAIRS:
            _, p = stats.wilcoxon(means(a, q), means(b, q), alternative="two-sided")
            post[f"{a}_vs_{b}"] = {
                "p": float(p),
                "p_bonferroni": float(min(1.0, p * len(PAIRS))),
                "mean_diff": float(np.mean(means(a, q) - means(b, q))),
            }
        out["questions"][q] = {
            "means": {c: float(np.mean(means(c, q))) for c in CONDITIONS},
            "friedman": {"chi2": float(chi2), "p": float(p_f)},
            "wilcoxon": post,
        }
        print(f"{q}: Friedman chi2={chi2:.2f} p={p_f:.4f}  " + "  ".join(
            f"{k} p_bonf={v['p_bonferroni']:.3f}" for k, v in post.items()))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n  -> {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
