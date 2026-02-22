#!/usr/bin/env python3
"""Statistical significance tests and confidence intervals for experiment analysis.

Provides paired significance tests (t-test or Wilcoxon), confidence intervals
via t-distribution, Cohen's d effect size, and markdown table formatting.

Usage:
  python3 paper/scripts/_stats_utils.py --self-test
"""

import os
import sys

# ---------------------------------------------------------------------------
# Path setup for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Statistical significance
# ---------------------------------------------------------------------------

def compute_significance(our_scores, baseline_scores, alpha=0.05):
    """Compute statistical significance between our method and a baseline.

    Performs Shapiro-Wilk normality check on pairwise differences.
    Uses paired t-test if normal (p > 0.05), Wilcoxon signed-rank otherwise.

    Args:
        our_scores: list/array of metric values from our method
        baseline_scores: list/array of metric values from the baseline
        alpha: significance level (default 0.05)

    Returns:
        dict with: test, statistic, p_value, significant, alpha, n_samples
    """
    our = np.array(our_scores, dtype=float)
    base = np.array(baseline_scores, dtype=float)
    diffs = our - base

    # Shapiro-Wilk normality test on differences
    _, normality_p = stats.shapiro(diffs)

    if normality_p > 0.05:
        # Normal differences: paired t-test
        stat, p_value = stats.ttest_rel(our, base)
        test_name = "paired_t_test"
    else:
        # Non-normal differences: Wilcoxon signed-rank
        stat, p_value = stats.wilcoxon(our, base)
        test_name = "wilcoxon_signed_rank"

    return {
        "test": test_name,
        "statistic": float(stat),
        "p_value": float(p_value),
        "significant": bool(p_value < alpha),
        "alpha": alpha,
        "n_samples": len(our),
    }


# ---------------------------------------------------------------------------
# Confidence intervals
# ---------------------------------------------------------------------------

def compute_confidence_interval(values, confidence=0.95):
    """Compute confidence interval using the t-distribution.

    Args:
        values: list/array of numeric values
        confidence: confidence level (default 0.95)

    Returns:
        dict with: mean, std, ci_lower, ci_upper, confidence, n
    """
    arr = np.array(values, dtype=float)
    n = len(arr)

    if n < 5:
        print(f"WARNING: CI with n={n} is unreliable (need n >= 5)")

    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    se = stats.sem(arr)
    ci = stats.t.interval(confidence, df=n - 1, loc=mean, scale=se)

    return {
        "mean": mean,
        "std": std,
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "confidence": confidence,
        "n": n,
    }


# ---------------------------------------------------------------------------
# Effect size (Cohen's d)
# ---------------------------------------------------------------------------

def compute_effect_size(our_scores, baseline_scores):
    """Compute Cohen's d effect size between two groups.

    Cohen's d = (mean1 - mean2) / pooled_std

    Interpretation thresholds:
      |d| < 0.2  -> negligible
      |d| < 0.5  -> small
      |d| < 0.8  -> medium
      |d| >= 0.8 -> large

    Returns:
        dict with: cohens_d, interpretation
    """
    our = np.array(our_scores, dtype=float)
    base = np.array(baseline_scores, dtype=float)

    n1, n2 = len(our), len(base)
    var1 = np.var(our, ddof=1)
    var2 = np.var(base, ddof=1)

    # Pooled standard deviation
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    if pooled_std == 0:
        d = 0.0
    else:
        d = float((np.mean(our) - np.mean(base)) / pooled_std)

    abs_d = abs(d)
    if abs_d < 0.2:
        interpretation = "negligible"
    elif abs_d < 0.5:
        interpretation = "small"
    elif abs_d < 0.8:
        interpretation = "medium"
    else:
        interpretation = "large"

    return {
        "cohens_d": d,
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Results table formatting
# ---------------------------------------------------------------------------

def format_results_table(results_dict):
    """Format experiment results as a markdown table with mean +/- std per cell.

    Args:
        results_dict: dict of {method_name: {metric_name: [values]}}
            e.g., {"Ours": {"accuracy": [0.92, 0.93, 0.91]},
                   "Baseline": {"accuracy": [0.85, 0.86, 0.84]}}

    Returns:
        str: formatted markdown table
    """
    if not results_dict:
        return "| Method |\n|--------|\n"

    # Collect all metric names across all methods
    all_metrics = set()
    for method_data in results_dict.values():
        all_metrics.update(method_data.keys())
    all_metrics = sorted(all_metrics)

    # Build header
    header = "| Method | " + " | ".join(all_metrics) + " |"
    separator = "|--------|" + "|".join(["--------" for _ in all_metrics]) + "|"

    # Build rows
    rows = []
    for method_name, method_data in results_dict.items():
        cells = []
        for metric in all_metrics:
            if metric in method_data:
                vals = np.array(method_data[metric], dtype=float)
                mean = np.mean(vals)
                std = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
                cells.append(f"{mean:.3f} +/- {std:.3f}")
            else:
                cells.append("--")
        rows.append(f"| {method_name} | " + " | ".join(cells) + " |")

    return "\n".join([header, separator] + rows)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" not in sys.argv:
        print("Usage: python3 paper/scripts/_stats_utils.py --self-test")
        sys.exit(1)

    print("=== _stats_utils self-test ===\n")
    all_passed = True

    # Test 1: Significance test -- paired t-test with clearly different data
    try:
        # Known paired data: our method is consistently better
        our = [90, 91, 92, 93, 94, 95, 96, 97, 98, 99]
        base = [80, 81, 82, 83, 84, 85, 86, 87, 88, 89]
        result = compute_significance(our, base)
        assert result["significant"] is True, f"Expected significant, got p={result['p_value']}"
        assert result["p_value"] < 0.05, f"Expected p < 0.05, got {result['p_value']}"
        assert result["n_samples"] == 10
        print(f"[PASS] significance test (t-test): test={result['test']}, p={result['p_value']:.6f}")
    except Exception as e:
        print(f"[FAIL] significance test (t-test): {e}")
        all_passed = False

    # Test 2: Significance test -- Wilcoxon chosen for non-normal diffs
    try:
        # Non-normal differences (heavy outlier)
        our_nonnorm = [50, 51, 52, 53, 54, 55, 56, 57, 58, 200]
        base_nonnorm = [40, 41, 42, 43, 44, 45, 46, 47, 48, 49]
        result2 = compute_significance(our_nonnorm, base_nonnorm)
        # With such extreme outlier, Shapiro-Wilk should detect non-normality
        # Either test name is acceptable -- the key point is significant
        assert result2["significant"] is True, f"Expected significant, got p={result2['p_value']}"
        print(f"[PASS] significance test (non-normal): test={result2['test']}, p={result2['p_value']:.6f}")
    except Exception as e:
        print(f"[FAIL] significance test (non-normal): {e}")
        all_passed = False

    # Test 3: Confidence interval for [1, 2, 3, 4, 5]
    try:
        ci_result = compute_confidence_interval([1, 2, 3, 4, 5], confidence=0.95)
        assert abs(ci_result["mean"] - 3.0) < 1e-10, f"Expected mean=3.0, got {ci_result['mean']}"
        assert ci_result["ci_lower"] < 3.0 < ci_result["ci_upper"], "Mean should be within CI bounds"
        assert ci_result["n"] == 5
        assert ci_result["confidence"] == 0.95
        # For [1,2,3,4,5], 95% CI should be approximately [0.73, 5.27]
        assert ci_result["ci_lower"] > 0.0, f"CI lower bound too low: {ci_result['ci_lower']}"
        assert ci_result["ci_upper"] < 6.0, f"CI upper bound too high: {ci_result['ci_upper']}"
        print(f"[PASS] confidence interval: mean={ci_result['mean']}, CI=[{ci_result['ci_lower']:.3f}, {ci_result['ci_upper']:.3f}]")
    except Exception as e:
        print(f"[FAIL] confidence interval: {e}")
        all_passed = False

    # Test 4: Cohen's d for identical lists (d=0)
    try:
        identical = [1, 2, 3, 4, 5]
        es_identical = compute_effect_size(identical, identical)
        assert es_identical["cohens_d"] == 0.0, f"Expected d=0.0, got {es_identical['cohens_d']}"
        assert es_identical["interpretation"] == "negligible"
        print(f"[PASS] effect size (identical): d={es_identical['cohens_d']}, interp={es_identical['interpretation']}")
    except Exception as e:
        print(f"[FAIL] effect size (identical): {e}")
        all_passed = False

    # Test 5: Cohen's d for clearly different lists (d > 0.8)
    try:
        high = [100, 101, 102, 103, 104]
        low = [50, 51, 52, 53, 54]
        es_diff = compute_effect_size(high, low)
        assert es_diff["cohens_d"] > 0.8, f"Expected d > 0.8, got {es_diff['cohens_d']}"
        assert es_diff["interpretation"] == "large"
        print(f"[PASS] effect size (large): d={es_diff['cohens_d']:.3f}, interp={es_diff['interpretation']}")
    except Exception as e:
        print(f"[FAIL] effect size (large): {e}")
        all_passed = False

    # Test 6: format_results_table produces valid markdown
    try:
        test_results = {
            "Ours": {"accuracy": [0.92, 0.93, 0.91], "f1": [0.88, 0.89, 0.87]},
            "Baseline": {"accuracy": [0.85, 0.86, 0.84], "f1": [0.80, 0.81, 0.79]},
        }
        table = format_results_table(test_results)
        assert "| Method |" in table, "Missing header"
        assert "|--------|" in table, "Missing separator"
        assert "Ours" in table, "Missing method name"
        assert "Baseline" in table, "Missing method name"
        assert "+/-" in table, "Missing +/- notation"
        lines = table.strip().split("\n")
        assert len(lines) == 4, f"Expected 4 lines (header, sep, 2 data), got {len(lines)}"
        # Each line should have the same number of pipes
        pipe_counts = [line.count("|") for line in lines]
        assert len(set(pipe_counts)) == 1, f"Inconsistent pipe counts: {pipe_counts}"
        print(f"[PASS] format_results_table: {len(lines)} lines, valid markdown")
    except Exception as e:
        print(f"[FAIL] format_results_table: {e}")
        all_passed = False

    print()
    if all_passed:
        print("=== All _stats_utils tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Some _stats_utils tests FAILED ===")
        sys.exit(1)
