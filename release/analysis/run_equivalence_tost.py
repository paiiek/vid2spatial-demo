"""Non-inferiority / equivalence analysis of authored-output satisfaction (N=12).

Reviewer 2 (#3) correctly notes that a non-significant Wilcoxon does not license
"no quality cost". This runs the analysis that does bear on the question:

  1. Paired TOST (two one-sided tests) on T2 self-rated satisfaction, with the
     equivalence bound set to +-0.5 Likert points -- half a scale step, the
     smallest difference that is even expressible on a 7-point item.
  2. A one-sided non-inferiority test at the same margin (the directional claim
     that actually matters: Vid2Spatial is not WORSE).
  3. The observed difference with a 90% CI (the interval TOST inverts).

Reads the raw study file; prints and stores the result.

Usage:  python3 test/run_equivalence_tost.py
"""

import json
import math
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data/efficiency_study/study_result.json"
OUT = REPO / "results/equivalence_tost.json"

MARGIN = 0.5  # equivalence bound, Likert points


def t_cdf(t, df):
    """Student-t CDF via the regularized incomplete beta function."""
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return p if t <= 0 else 1.0 - p


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a,b) by continued fraction (Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1 - x) + a * math.log(x) - lbeta) * _betacf(b, a, 1 - x) / b


def _betacf(a, b, x, itmax=300, eps=3e-16):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def collect_pairs(field="q_satisfy", task="T2"):
    """Return per-participant (manual, vid2spatial) pairs for one questionnaire item."""
    data = json.loads(RAW.read_text())
    pairs = []
    for p in data:
        by_cond = {}
        for tr in p["trials"]:
            if tr["task"] != task:
                continue
            by_cond[tr["cond"]] = tr["questionnaire"][field]
        if "Manual" in by_cond and "Vid2Spatial" in by_cond:
            pairs.append((p["meta"]["pid"], by_cond["Manual"], by_cond["Vid2Spatial"]))
    return pairs


def main():
    pairs = collect_pairs()
    n = len(pairs)
    diffs = [vs - man for _, man, vs in pairs]  # positive = Vid2Spatial better
    mean_d = statistics.fmean(diffs)
    sd_d = statistics.stdev(diffs)
    se = sd_d / math.sqrt(n)
    df = n - 1

    # TOST: reject non-equivalence if BOTH one-sided tests reject
    t_lower = (mean_d - (-MARGIN)) / se   # H0: d <= -margin
    t_upper = (mean_d - MARGIN) / se      # H0: d >= +margin
    p_lower = 1.0 - t_cdf(t_lower, df)    # one-sided, upper tail
    p_upper = t_cdf(t_upper, df)          # one-sided, lower tail
    p_tost = max(p_lower, p_upper)

    # 90% CI (the interval TOST inverts at alpha=.05)
    tcrit = _tinv(0.95, df)
    ci = (mean_d - tcrit * se, mean_d + tcrit * se)

    res = {
        "n": n,
        "item": "T2 self-rated satisfaction",
        "equivalence_margin_likert": MARGIN,
        "mean_difference_vs_minus_manual": mean_d,
        "sd_of_differences": sd_d,
        "ci90": list(ci),
        "tost": {
            "p_lower_bound_test": p_lower,
            "p_upper_bound_test": p_upper,
            "p_tost": p_tost,
            "equivalent_at_alpha_05": p_tost < 0.05,
        },
        "non_inferiority": {
            "margin": MARGIN,
            "p": p_lower,
            "non_inferior_at_alpha_05": p_lower < 0.05,
        },
        "raw_differences": diffs,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))

    print(f"  N = {n}   item = T2 satisfaction   margin = +-{MARGIN} Likert")
    print(f"  mean diff (VS - Manual) = {mean_d:+.3f}  (SD {sd_d:.3f})")
    print(f"  90% CI = [{ci[0]:+.3f}, {ci[1]:+.3f}]")
    print(f"  TOST:            p = {p_tost:.4f}  -> equivalent: {res['tost']['equivalent_at_alpha_05']}")
    print(f"  non-inferiority: p = {p_lower:.4f}  -> non-inferior: "
          f"{res['non_inferiority']['non_inferior_at_alpha_05']}")
    print(f"\n  -> {OUT.relative_to(REPO)}")


def _tinv(p, df, lo=-50.0, hi=50.0):
    """Inverse Student-t CDF by bisection."""
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


if __name__ == "__main__":
    main()
