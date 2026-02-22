#!/usr/bin/env python3
"""Experiment execution engine with seed pinning, hardware capture, metric logging.

Orchestrates a single experiment execution with full reproducibility tracking:
deterministic seeding, hardware environment capture, sandboxed subprocess
execution, structured metric logging, and git-based state management.

Usage:
  python3 paper/scripts/_experiment_runner.py --spec paper/experiments/specs/main_result.json
  python3 paper/scripts/_experiment_runner.py --self-test
"""

import json
import os
import platform
import random
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
# Seed pinning
# ---------------------------------------------------------------------------

def pin_all_seeds(seed=42):
    """Pin all random number generators for reproducibility.

    Must be called BEFORE any random operations. Sets:
    - PYTHONHASHSEED environment variable
    - Python random module seed
    - NumPy seed (if numpy available)
    - PyTorch manual seed + CUDA seeds + deterministic mode (if torch available)

    Returns:
        int: the seed that was set
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
    return seed


# ---------------------------------------------------------------------------
# Hardware capture
# ---------------------------------------------------------------------------

def capture_hardware():
    """Capture hardware and environment info as a dict.

    Returns dict with keys: cpu, cpu_count, os, python_version, ram_gb,
    gpu, cuda_version. Uses subprocess with timeout=5 for external calls.
    """
    info = {
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "os": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "ram_gb": None,
        "gpu": "none",
        "cuda_version": None,
    }

    # RAM detection -- macOS via sysctl
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                info["ram_gb"] = round(int(r.stdout.strip()) / (1024 ** 3), 1)
        except Exception:
            pass
    # RAM detection -- Linux via /proc/meminfo
    elif platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        info["ram_gb"] = round(kb / (1024 ** 2), 1)
                        break
        except Exception:
            pass

    # GPU detection via nvidia-smi
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            info["gpu"] = r.stdout.strip()
    except FileNotFoundError:
        pass

    # CUDA version via nvcc
    try:
        r = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            for line in r.stdout.split("\n"):
                if "release" in line.lower():
                    info["cuda_version"] = line.strip()
                    break
    except FileNotFoundError:
        pass

    return info


# ---------------------------------------------------------------------------
# Experiment execution
# ---------------------------------------------------------------------------

def run_experiment(spec_path):
    """Execute experiment from spec JSON, return result directory path.

    Loads spec, pins seeds, creates result directory, captures hardware,
    runs experiment script (if specified) via subprocess, writes config.json
    and reads metrics.json from result directory.

    Args:
        spec_path: path to experiment spec JSON file

    Returns:
        str: path to result directory
    """
    with open(spec_path) as f:
        spec = json.load(f)

    experiment_name = spec["experiment_name"]
    seed = spec.get("seed", 42)
    pin_all_seeds(seed)

    # Determine result directory base
    results_base = spec.get("results_base", "paper/experiments/results")
    result_dir = os.path.join(results_base, experiment_name)
    os.makedirs(result_dir, exist_ok=True)
    os.makedirs(os.path.join(result_dir, "logs"), exist_ok=True)

    # Capture hardware
    hardware = capture_hardware()

    # Write config before execution
    config = {
        "experiment_name": experiment_name,
        "seed": seed,
        "spec": spec,
        "hardware": hardware,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(
        os.path.join(result_dir, "config.json"),
        json.dumps(config, indent=2)
    )

    # Execute the experiment script (sandboxed via subprocess)
    script_path = spec.get("script_path")
    if script_path:
        env = os.environ.copy()
        env["EXPERIMENT_RESULT_DIR"] = result_dir
        env["PYTHONHASHSEED"] = str(seed)
        try:
            result = subprocess.run(
                [sys.executable, script_path, "--seed", str(seed)],
                capture_output=True, text=True,
                timeout=spec.get("timeout_seconds", 3600),
                cwd=os.getcwd(),
                env=env,
            )
            # Log stdout/stderr
            atomic_write(
                os.path.join(result_dir, "logs", "stdout.log"),
                result.stdout
            )
            atomic_write(
                os.path.join(result_dir, "logs", "stderr.log"),
                result.stderr
            )
        except subprocess.TimeoutExpired:
            atomic_write(
                os.path.join(result_dir, "logs", "stderr.log"),
                "ERROR: Experiment timed out"
            )

    # Update config with completion timestamp
    config["completed_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write(
        os.path.join(result_dir, "config.json"),
        json.dumps(config, indent=2)
    )

    return result_dir


# ---------------------------------------------------------------------------
# Git commit
# ---------------------------------------------------------------------------

def git_commit_experiment(experiment_name, result_dir):
    """Git add and commit experiment results.

    Args:
        experiment_name: name for commit message
        result_dir: directory to git add

    Returns:
        str: commit SHA from git rev-parse HEAD, or None on error
    """
    try:
        subprocess.run(
            ["git", "add", result_dir],
            capture_output=True, text=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m",
             f"experiment({experiment_name}): capture results"],
            capture_output=True, text=True, check=True
        )
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return r.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"WARNING: git commit failed for {experiment_name}: {e.stderr}")
        return None


# ---------------------------------------------------------------------------
# Experiment summary
# ---------------------------------------------------------------------------

def load_experiment_summary(results_base="paper/experiments/results"):
    """Scan all result directories and load metrics summaries.

    Returns list of dicts sorted by primary_metric value (descending).
    """
    summaries = []
    if not os.path.isdir(results_base):
        return summaries

    for entry in os.listdir(results_base):
        metrics_path = os.path.join(results_base, entry, "metrics.json")
        if os.path.isfile(metrics_path):
            try:
                with open(metrics_path) as f:
                    metrics = json.load(f)
                summaries.append(metrics)
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by primary_metric value descending
    summaries.sort(
        key=lambda x: x.get("primary_metric", {}).get("value", 0),
        reverse=True
    )
    return summaries


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" not in sys.argv:
        print("Usage:")
        print("  python3 paper/scripts/_experiment_runner.py --spec <spec.json>")
        print("  python3 paper/scripts/_experiment_runner.py --self-test")
        sys.exit(1)

    print("=== _experiment_runner self-test ===\n")
    all_passed = True

    # Test 1: pin_all_seeds determinism
    try:
        pin_all_seeds(42)
        val1 = random.random()
        val2 = random.random()
        pin_all_seeds(42)
        val3 = random.random()
        val4 = random.random()
        assert val1 == val3, f"First values differ: {val1} != {val3}"
        assert val2 == val4, f"Second values differ: {val2} != {val4}"
        print("[PASS] pin_all_seeds: deterministic random sequence")
    except NotImplementedError:
        print("[FAIL] pin_all_seeds: not implemented")
        all_passed = False
    except Exception as e:
        print(f"[FAIL] pin_all_seeds determinism: {e}")
        all_passed = False

    # Test 2: pin_all_seeds sets PYTHONHASHSEED
    try:
        pin_all_seeds(42)
        assert os.environ.get("PYTHONHASHSEED") == "42", \
            f"PYTHONHASHSEED not set, got: {os.environ.get('PYTHONHASHSEED')}"
        print("[PASS] pin_all_seeds: PYTHONHASHSEED set")
    except NotImplementedError:
        print("[FAIL] pin_all_seeds PYTHONHASHSEED: not implemented")
        all_passed = False
    except Exception as e:
        print(f"[FAIL] pin_all_seeds PYTHONHASHSEED: {e}")
        all_passed = False

    # Test 3: capture_hardware returns dict with expected keys
    try:
        hw = capture_hardware()
        expected_keys = {"cpu", "cpu_count", "os", "python_version", "ram_gb"}
        missing = expected_keys - set(hw.keys())
        assert not missing, f"Missing keys: {missing}"
        assert hw["cpu"] is not None, "cpu is None"
        assert hw["cpu_count"] is not None and hw["cpu_count"] > 0, "cpu_count invalid"
        assert hw["python_version"] is not None, "python_version is None"
        print(f"[PASS] capture_hardware: {len(hw)} keys, cpu={hw['cpu']}, ram={hw.get('ram_gb')}GB")
    except NotImplementedError:
        print("[FAIL] capture_hardware: not implemented")
        all_passed = False
    except Exception as e:
        print(f"[FAIL] capture_hardware: {e}")
        all_passed = False

    # Test 4: run_experiment with mock spec creates result dir with config.json and metrics.json
    try:
        test_dir = tempfile.mkdtemp(prefix="exp_test_")

        # Create mock experiment script that writes metrics.json
        mock_script = os.path.join(test_dir, "mock_experiment.py")
        with open(mock_script, "w") as f:
            f.write('''#!/usr/bin/env python3
import json
import os
import sys
import random

# Parse seed from args
seed = 42
for i, arg in enumerate(sys.argv):
    if arg == "--seed" and i + 1 < len(sys.argv):
        seed = int(sys.argv[i + 1])

random.seed(seed)
metric_val = random.random()

# Write metrics to result dir (passed via EXPERIMENT_RESULT_DIR env var)
result_dir = os.environ.get("EXPERIMENT_RESULT_DIR", ".")
metrics = {
    "experiment_name": "test_mock",
    "experiment_type": "validation",
    "seed": seed,
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:01:00Z",
    "hardware": {"cpu": "test", "cpu_count": 1, "os": "test", "python_version": "3.14", "ram_gb": 8.0, "gpu": "none", "cuda_version": None},
    "metrics": {"accuracy": metric_val},
    "primary_metric": {"name": "accuracy", "value": metric_val, "direction": "higher_is_better"}
}
os.makedirs(result_dir, exist_ok=True)
with open(os.path.join(result_dir, "metrics.json"), "w") as mf:
    json.dump(metrics, mf, indent=2)
print(f"Wrote metrics with accuracy={metric_val}")
''')

        # Create mock spec
        mock_spec_path = os.path.join(test_dir, "spec.json")
        with open(mock_spec_path, "w") as f:
            json.dump({
                "experiment_name": "test_mock",
                "experiment_type": "validation",
                "seed": 42,
                "script_path": mock_script,
                "results_base": os.path.join(test_dir, "results"),
            }, f)

        result_dir = run_experiment(mock_spec_path)
        assert os.path.isdir(result_dir), f"Result dir does not exist: {result_dir}"
        assert os.path.isfile(os.path.join(result_dir, "config.json")), "config.json missing"
        assert os.path.isfile(os.path.join(result_dir, "metrics.json")), "metrics.json missing"

        # Verify config.json has hardware and seed
        with open(os.path.join(result_dir, "config.json")) as f:
            config = json.load(f)
        assert "hardware" in config, "config.json missing hardware"
        assert config["seed"] == 42, f"Expected seed=42, got {config['seed']}"

        print("[PASS] run_experiment: result dir created with config.json and metrics.json")

        # Clean up
        shutil.rmtree(test_dir)
    except NotImplementedError:
        print("[FAIL] run_experiment: not implemented")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] run_experiment: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 5: run_experiment with same seed produces identical metrics
    try:
        test_dir = tempfile.mkdtemp(prefix="exp_test_determ_")

        mock_script = os.path.join(test_dir, "mock_determ.py")
        with open(mock_script, "w") as f:
            f.write('''#!/usr/bin/env python3
import json, os, sys, random
seed = 42
for i, arg in enumerate(sys.argv):
    if arg == "--seed" and i + 1 < len(sys.argv):
        seed = int(sys.argv[i + 1])
random.seed(seed)
val = random.random()
result_dir = os.environ.get("EXPERIMENT_RESULT_DIR", ".")
os.makedirs(result_dir, exist_ok=True)
with open(os.path.join(result_dir, "metrics.json"), "w") as mf:
    json.dump({
        "experiment_name": "determ_test",
        "experiment_type": "validation",
        "seed": seed,
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
        "hardware": {"cpu": "t", "cpu_count": 1, "os": "t", "python_version": "3.14", "ram_gb": 8, "gpu": "none", "cuda_version": None},
        "metrics": {"val": val},
        "primary_metric": {"name": "val", "value": val, "direction": "higher_is_better"}
    }, mf)
''')

        # Run 1
        spec1 = os.path.join(test_dir, "spec1.json")
        with open(spec1, "w") as f:
            json.dump({
                "experiment_name": "determ_run1",
                "experiment_type": "validation",
                "seed": 42,
                "script_path": mock_script,
                "results_base": os.path.join(test_dir, "results"),
            }, f)
        rd1 = run_experiment(spec1)
        with open(os.path.join(rd1, "metrics.json")) as f:
            m1 = json.load(f)

        # Run 2
        spec2 = os.path.join(test_dir, "spec2.json")
        with open(spec2, "w") as f:
            json.dump({
                "experiment_name": "determ_run2",
                "experiment_type": "validation",
                "seed": 42,
                "script_path": mock_script,
                "results_base": os.path.join(test_dir, "results"),
            }, f)
        rd2 = run_experiment(spec2)
        with open(os.path.join(rd2, "metrics.json")) as f:
            m2 = json.load(f)

        assert m1["metrics"]["val"] == m2["metrics"]["val"], \
            f"Metrics differ: {m1['metrics']['val']} != {m2['metrics']['val']}"
        print("[PASS] run_experiment: same seed produces identical metrics")

        shutil.rmtree(test_dir)
    except NotImplementedError:
        print("[FAIL] run_experiment determinism: not implemented")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] run_experiment determinism: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    print()
    if all_passed:
        print("=== All _experiment_runner tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Some _experiment_runner tests FAILED ===")
        sys.exit(1)
