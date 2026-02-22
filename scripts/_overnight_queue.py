#!/usr/bin/env python3
"""Autoresearch overnight queue processor with git-based keep/discard.

Processes experiment variations sequentially: git commit per experiment,
keep improvements, discard regressions (git checkout to best commit).
JSONL log entry written BEFORE any git revert. Supports resume by
tracking completed experiment IDs.

Usage:
  python3 paper/scripts/_overnight_queue.py --queue paper/experiments/queue.json
  python3 paper/scripts/_overnight_queue.py --self-test
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# Completed experiment tracking
# ---------------------------------------------------------------------------

def load_completed_experiments(log_path="paper/experiments/experiment_log.jsonl"):
    """Read JSONL log, return set of experiment IDs that have been processed.

    Each line in the JSONL is a decision record with an "experiment_id" field.
    Returns all IDs regardless of kept/discarded status (for resume support).
    If the file does not exist, returns an empty set.
    """
    if not os.path.isfile(log_path):
        return set()
    completed = set()
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if "experiment_id" in entry:
                    completed.add(entry["experiment_id"])
            except json.JSONDecodeError:
                continue
    return completed


# ---------------------------------------------------------------------------
# Best metric tracking
# ---------------------------------------------------------------------------

def load_best_metric(log_path="paper/experiments/experiment_log.jsonl"):
    """Read JSONL log, find the most recent 'kept' entry.

    Returns (current_metric, commit_sha) from the most recent kept entry.
    If no 'kept' entries exist, returns (None, None).
    """
    if not os.path.isfile(log_path):
        return (None, None)
    best_metric = None
    best_sha = None
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("action") == "kept":
                    best_metric = entry.get("current_metric")
                    best_sha = entry.get("commit_sha")
            except json.JSONDecodeError:
                continue
    return (best_metric, best_sha)


# ---------------------------------------------------------------------------
# Metric comparison
# ---------------------------------------------------------------------------

def is_improvement(current, best, direction="higher_is_better"):
    """Compare metrics to determine if current is an improvement over best.

    If best is None (first experiment), always returns True.
    For 'higher_is_better': current > best (strict).
    For 'lower_is_better': current < best (strict).
    Ties are NOT improvements (conservative).
    """
    if best is None:
        return True
    if direction == "higher_is_better":
        return current > best
    elif direction == "lower_is_better":
        return current < best
    else:
        raise ValueError(f"Unknown direction: {direction!r}")


# ---------------------------------------------------------------------------
# Composite metric
# ---------------------------------------------------------------------------

def compute_composite_metric(metrics_dict, weights):
    """Compute weighted composite metric for non-scalar comparison.

    Takes dict of {metric_name: value} and weights dict {metric_name: weight}.
    Computes weighted sum of metric values. When used with normalization
    history, values should be pre-normalized to [0, 1]. For direct use,
    returns the raw weighted sum.

    Returns composite float.
    """
    composite = 0.0
    for metric_name, weight in weights.items():
        if metric_name in metrics_dict:
            composite += metrics_dict[metric_name] * weight
    return composite


# ---------------------------------------------------------------------------
# Decision logging
# ---------------------------------------------------------------------------

def log_experiment_decision(exp_id, action, current_metric, best_metric,
                            commit_sha,
                            log_path="paper/experiments/experiment_log.jsonl"):
    """Append JSONL entry for an experiment decision.

    Fields: experiment_id, action ('kept'/'discarded'), current_metric,
    best_metric, commit_sha, timestamp.

    MUST be called BEFORE any git revert to preserve audit trail.
    Creates parent directories if needed.
    """
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    entry = {
        "experiment_id": exp_id,
        "action": action,
        "current_metric": current_metric,
        "best_metric": best_metric,
        "commit_sha": commit_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Git revert
# ---------------------------------------------------------------------------

def git_revert_to_best(best_sha):
    """Revert experiment results to the best known commit.

    Uses targeted git checkout (not git reset --hard):
      git checkout {best_sha} -- paper/experiments/results/

    Matches Phase 2 ratchet pattern.
    """
    result = subprocess.run(
        ["git", "checkout", best_sha, "--", "paper/experiments/results/"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"WARNING: git checkout to {best_sha} failed: {result.stderr}")
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Queue processing
# ---------------------------------------------------------------------------

def process_queue(queue_path="paper/experiments/queue.json"):
    """Main entry point: process experiment queue.

    a. Load queue JSON, validate required fields
    b. Load completed experiments from log
    c. Load current best metric and SHA
    d. For each experiment in queue["experiments"]:
       - Skip if ID in completed set (resume support)
       - For each seed: create spec, run experiment, commit, compare, keep/discard
    e. Return final best metric and summary dict
    """
    from _experiment_runner import run_experiment, git_commit_experiment

    # a. Load and validate queue
    with open(queue_path) as f:
        queue = json.load(f)
    required_fields = ["queue_id", "metric_direction", "experiments"]
    for field in required_fields:
        if field not in queue:
            raise ValueError(f"Queue missing required field: {field}")

    direction = queue["metric_direction"]
    log_path = "paper/experiments/experiment_log.jsonl"
    use_composite = "composite_metric" in queue and queue["composite_metric"]

    # b. Load completed experiments
    completed = load_completed_experiments(log_path)

    # c. Load current best metric and SHA
    best_metric, best_sha = load_best_metric(log_path)

    summary = {
        "queue_id": queue["queue_id"],
        "total_experiments": len(queue["experiments"]),
        "skipped": 0,
        "kept": 0,
        "discarded": 0,
        "final_best_metric": best_metric,
        "final_best_sha": best_sha,
    }

    # d. Process each experiment
    for experiment in queue["experiments"]:
        exp_id = experiment["id"]

        # Skip if already completed (resume support)
        if exp_id in completed:
            summary["skipped"] += 1
            print(f"SKIP: {exp_id} (already completed)")
            continue

        seeds = experiment.get("seeds", [42])
        overrides = experiment.get("overrides", {})

        for seed in seeds:
            # Create experiment spec by merging base with overrides
            spec = {}
            if queue.get("base_spec"):
                base_spec_path = queue["base_spec"]
                if os.path.isfile(base_spec_path):
                    with open(base_spec_path) as f:
                        spec = json.load(f)

            # Apply overrides
            spec.update(overrides)
            spec["seed"] = seed
            spec["experiment_name"] = f"{exp_id}_seed{seed}"

            # Write spec to paper/experiments/specs/
            specs_dir = "paper/experiments/specs"
            os.makedirs(specs_dir, exist_ok=True)
            spec_path = os.path.join(specs_dir, f"{exp_id}_seed{seed}.json")
            atomic_write(spec_path, json.dumps(spec, indent=2))

            # Run experiment
            result_dir = run_experiment(spec_path)

            # Git commit results
            commit_sha = git_commit_experiment(spec["experiment_name"], result_dir)

            # Read metric from result
            metrics_path = os.path.join(result_dir, "metrics.json")
            current_metric = None
            if os.path.isfile(metrics_path):
                with open(metrics_path) as f:
                    metrics_data = json.load(f)
                if use_composite:
                    # Composite metric from multiple dimensions
                    raw_metrics = metrics_data.get("metrics", {})
                    current_metric = compute_composite_metric(
                        raw_metrics, queue["composite_metric"]
                    )
                else:
                    # Primary metric (scalar)
                    pm = metrics_data.get("primary_metric", {})
                    current_metric = pm.get("value")

            # Compare and decide
            improved = is_improvement(current_metric, best_metric, direction)

            if improved:
                # ALWAYS log BEFORE any potential revert
                log_experiment_decision(
                    exp_id, "kept", current_metric, best_metric,
                    commit_sha, log_path=log_path,
                )
                best_metric = current_metric
                best_sha = commit_sha
                summary["kept"] += 1
                print(f"KEPT: {exp_id} (seed={seed}, metric={current_metric})")
            else:
                # Log BEFORE revert (critical ordering)
                log_experiment_decision(
                    exp_id, "discarded", current_metric, best_metric,
                    commit_sha, log_path=log_path,
                )
                # Revert to best
                if best_sha:
                    git_revert_to_best(best_sha)
                summary["discarded"] += 1
                print(f"DISCARDED: {exp_id} (seed={seed}, metric={current_metric})")

    summary["final_best_metric"] = best_metric
    summary["final_best_sha"] = best_sha
    return summary


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("=== _overnight_queue self-test ===\n")
        all_passed = True

        # Test 1: load_completed_experiments with 3 entries
        try:
            test_dir = tempfile.mkdtemp(prefix="oq_test_")
            log_path = os.path.join(test_dir, "experiment_log.jsonl")
            entries = [
                {"experiment_id": "exp_1", "action": "kept", "current_metric": 0.85, "best_metric": None, "commit_sha": "aaa", "timestamp": "2026-01-01T00:00:00Z"},
                {"experiment_id": "exp_2", "action": "discarded", "current_metric": 0.80, "best_metric": 0.85, "commit_sha": "bbb", "timestamp": "2026-01-01T00:01:00Z"},
                {"experiment_id": "exp_3", "action": "kept", "current_metric": 0.90, "best_metric": 0.85, "commit_sha": "ccc", "timestamp": "2026-01-01T00:02:00Z"},
            ]
            with open(log_path, "w") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
            result = load_completed_experiments(log_path)
            assert isinstance(result, set), f"Expected set, got {type(result)}"
            assert result == {"exp_1", "exp_2", "exp_3"}, f"Expected 3 IDs, got {result}"
            shutil.rmtree(test_dir)
            print("[PASS] load_completed_experiments: 3 entries -> set of 3 IDs")
        except NotImplementedError:
            print("[FAIL] load_completed_experiments: not implemented")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except Exception as e:
            print(f"[FAIL] load_completed_experiments: {e}")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Test 2: load_completed_experiments with missing file
        try:
            result = load_completed_experiments("/nonexistent/path/log.jsonl")
            assert isinstance(result, set), f"Expected set, got {type(result)}"
            assert len(result) == 0, f"Expected empty set, got {result}"
            print("[PASS] load_completed_experiments: missing file -> empty set")
        except NotImplementedError:
            print("[FAIL] load_completed_experiments (missing file): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] load_completed_experiments (missing file): {e}")
            all_passed = False

        # Test 3: is_improvement (5.0, 4.0, "higher_is_better") -> True
        try:
            assert is_improvement(5.0, 4.0, "higher_is_better") is True
            print("[PASS] is_improvement: 5.0 > 4.0 (higher_is_better) -> True")
        except NotImplementedError:
            print("[FAIL] is_improvement (higher True): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] is_improvement (higher True): {e}")
            all_passed = False

        # Test 4: is_improvement (4.0, 5.0, "higher_is_better") -> False
        try:
            assert is_improvement(4.0, 5.0, "higher_is_better") is False
            print("[PASS] is_improvement: 4.0 < 5.0 (higher_is_better) -> False")
        except NotImplementedError:
            print("[FAIL] is_improvement (higher False): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] is_improvement (higher False): {e}")
            all_passed = False

        # Test 5: is_improvement (5.0, 5.0, "higher_is_better") -> False (tie)
        try:
            assert is_improvement(5.0, 5.0, "higher_is_better") is False
            print("[PASS] is_improvement: 5.0 == 5.0 (tie) -> False")
        except NotImplementedError:
            print("[FAIL] is_improvement (tie): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] is_improvement (tie): {e}")
            all_passed = False

        # Test 6: is_improvement (3.0, 4.0, "lower_is_better") -> True
        try:
            assert is_improvement(3.0, 4.0, "lower_is_better") is True
            print("[PASS] is_improvement: 3.0 < 4.0 (lower_is_better) -> True")
        except NotImplementedError:
            print("[FAIL] is_improvement (lower True): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] is_improvement (lower True): {e}")
            all_passed = False

        # Test 7: is_improvement (5.0, None, "higher_is_better") -> True (first experiment)
        try:
            assert is_improvement(5.0, None, "higher_is_better") is True
            print("[PASS] is_improvement: first experiment (best=None) -> True")
        except NotImplementedError:
            print("[FAIL] is_improvement (first exp): not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] is_improvement (first exp): {e}")
            all_passed = False

        # Test 8: log_experiment_decision writes valid JSONL
        try:
            test_dir = tempfile.mkdtemp(prefix="oq_log_test_")
            log_path = os.path.join(test_dir, "sub", "experiment_log.jsonl")
            log_experiment_decision(
                "test_exp", "kept", 0.92, None, "abc123", log_path=log_path
            )
            assert os.path.isfile(log_path), f"Log file not created: {log_path}"
            with open(log_path) as f:
                line = f.readline().strip()
            entry = json.loads(line)
            assert entry["experiment_id"] == "test_exp"
            assert entry["action"] == "kept"
            assert entry["current_metric"] == 0.92
            assert entry["best_metric"] is None
            assert entry["commit_sha"] == "abc123"
            assert "timestamp" in entry
            shutil.rmtree(test_dir)
            print("[PASS] log_experiment_decision: writes valid JSONL")
        except NotImplementedError:
            print("[FAIL] log_experiment_decision: not implemented")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except Exception as e:
            print(f"[FAIL] log_experiment_decision: {e}")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Test 9: Resume -- pre-populate log with 2 IDs, queue has 3
        # Only the 3rd experiment should be processed
        try:
            test_dir = tempfile.mkdtemp(prefix="oq_resume_test_")
            log_path = os.path.join(test_dir, "experiment_log.jsonl")
            # Pre-populate with 2 completed experiments
            with open(log_path, "w") as f:
                f.write(json.dumps({"experiment_id": "exp_a", "action": "kept", "current_metric": 0.80, "best_metric": None, "commit_sha": "sha1", "timestamp": "2026-01-01T00:00:00Z"}) + "\n")
                f.write(json.dumps({"experiment_id": "exp_b", "action": "kept", "current_metric": 0.85, "best_metric": 0.80, "commit_sha": "sha2", "timestamp": "2026-01-01T00:01:00Z"}) + "\n")

            completed = load_completed_experiments(log_path)
            assert "exp_a" in completed, "exp_a should be completed"
            assert "exp_b" in completed, "exp_b should be completed"
            assert "exp_c" not in completed, "exp_c should NOT be completed"

            # Verify that only exp_c would need processing
            queue_experiments = [
                {"id": "exp_a", "seeds": [42]},
                {"id": "exp_b", "seeds": [42]},
                {"id": "exp_c", "seeds": [42]},
            ]
            to_run = [e for e in queue_experiments if e["id"] not in completed]
            assert len(to_run) == 1, f"Expected 1 to run, got {len(to_run)}"
            assert to_run[0]["id"] == "exp_c", f"Expected exp_c, got {to_run[0]['id']}"

            shutil.rmtree(test_dir)
            print("[PASS] resume: 2 of 3 completed, only 1 to run")
        except NotImplementedError:
            print("[FAIL] resume: not implemented")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except Exception as e:
            print(f"[FAIL] resume: {e}")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Test 10: compute_composite_metric
        try:
            metrics = {"accuracy": 0.9, "f1": 0.85}
            weights = {"accuracy": 0.6, "f1": 0.4}
            result = compute_composite_metric(metrics, weights)
            expected = 0.9 * 0.6 + 0.85 * 0.4  # = 0.54 + 0.34 = 0.88
            assert abs(result - expected) < 1e-6, f"Expected ~{expected}, got {result}"
            print(f"[PASS] compute_composite_metric: weighted sum = {result:.4f}")
        except NotImplementedError:
            print("[FAIL] compute_composite_metric: not implemented")
            all_passed = False
        except Exception as e:
            print(f"[FAIL] compute_composite_metric: {e}")
            all_passed = False

        # Test 11: load_best_metric
        try:
            test_dir = tempfile.mkdtemp(prefix="oq_best_test_")
            log_path = os.path.join(test_dir, "experiment_log.jsonl")
            entries = [
                {"experiment_id": "exp_1", "action": "kept", "current_metric": 0.85, "best_metric": None, "commit_sha": "aaa", "timestamp": "2026-01-01T00:00:00Z"},
                {"experiment_id": "exp_2", "action": "discarded", "current_metric": 0.80, "best_metric": 0.85, "commit_sha": "bbb", "timestamp": "2026-01-01T00:01:00Z"},
                {"experiment_id": "exp_3", "action": "kept", "current_metric": 0.90, "best_metric": 0.85, "commit_sha": "ccc", "timestamp": "2026-01-01T00:02:00Z"},
            ]
            with open(log_path, "w") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
            metric, sha = load_best_metric(log_path)
            assert metric == 0.90, f"Expected 0.90, got {metric}"
            assert sha == "ccc", f"Expected 'ccc', got {sha}"
            shutil.rmtree(test_dir)
            print("[PASS] load_best_metric: returns most recent kept entry")
        except NotImplementedError:
            print("[FAIL] load_best_metric: not implemented")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except Exception as e:
            print(f"[FAIL] load_best_metric: {e}")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Test 12: load_best_metric with no kept entries
        try:
            test_dir = tempfile.mkdtemp(prefix="oq_best_none_test_")
            log_path = os.path.join(test_dir, "experiment_log.jsonl")
            with open(log_path, "w") as f:
                f.write(json.dumps({"experiment_id": "exp_1", "action": "discarded", "current_metric": 0.80, "best_metric": 0.85, "commit_sha": "xxx", "timestamp": "2026-01-01T00:00:00Z"}) + "\n")
            metric, sha = load_best_metric(log_path)
            assert metric is None, f"Expected None, got {metric}"
            assert sha is None, f"Expected None, got {sha}"
            shutil.rmtree(test_dir)
            print("[PASS] load_best_metric: no kept entries -> (None, None)")
        except NotImplementedError:
            print("[FAIL] load_best_metric (no kept): not implemented")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
        except Exception as e:
            print(f"[FAIL] load_best_metric (no kept): {e}")
            all_passed = False
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        print()
        if all_passed:
            print("=== All _overnight_queue tests PASSED ===")
            sys.exit(0)
        else:
            print("=== Some _overnight_queue tests FAILED ===")
            sys.exit(1)

    elif "--queue" in sys.argv:
        idx = sys.argv.index("--queue")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --queue requires a path argument", file=sys.stderr)
            sys.exit(1)
        queue_path = sys.argv[idx + 1]
        result = process_queue(queue_path)
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
        sys.exit(0)
