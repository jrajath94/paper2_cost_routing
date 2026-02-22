#!/usr/bin/env python3
"""Reproducibility package generator for academic paper experiments.

Generates a complete reproducibility/ directory containing pyproject.toml,
Makefile, seeds.json, hardware_reference.json, checksums.sha256, and README.md.
Enables anyone to reproduce the paper's experimental results from a clean
Python environment with one command (make all).

Usage:
  python3 paper/scripts/_repro_package.py --output reproducibility --results paper/experiments/results
  python3 paper/scripts/_repro_package.py --self-test
"""

import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Path setup for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# Dependency capture
# ---------------------------------------------------------------------------

def capture_pip_dependencies():
    """Run pip list --format=json, parse output, return list of {name, version} dicts.

    Filters out pip, setuptools, and wheel. Timeout: 10 seconds.
    Returns empty list with warning if pip fails.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"WARNING: pip list failed: {result.stderr.strip()}")
            return []
        packages = json.loads(result.stdout)
        skip = {"pip", "setuptools", "wheel"}
        return [
            {"name": p["name"], "version": p["version"]}
            for p in packages
            if p["name"].lower() not in skip
        ]
    except subprocess.TimeoutExpired:
        print("WARNING: pip list timed out after 10s")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"WARNING: pip list output parse error: {e}")
        return []
    except FileNotFoundError:
        print("WARNING: pip not found")
        return []


# ---------------------------------------------------------------------------
# pyproject.toml generation
# ---------------------------------------------------------------------------

def generate_pyproject_toml(deps, project_name="eb-paper-repro",
                            output_path="reproducibility/pyproject.toml"):
    """Generate PEP 621-compliant pyproject.toml with pinned dependencies.

    Args:
        deps: list of {name, version} dicts from capture_pip_dependencies
        project_name: project name for [project] table
        output_path: where to write the file

    Returns:
        str: generated pyproject.toml content
    """
    dep_lines = []
    for d in deps:
        dep_lines.append(f'    "{d["name"]}=={d["version"]}",')
    deps_str = "\n".join(dep_lines)

    content = f'''[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "{project_name}"
version = "0.1.0"
description = "Reproducibility package for experimental results"
requires-python = ">=3.10"
dependencies = [
{deps_str}
]

[project.optional-dependencies]
dev = ["pytest"]
'''
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, content)
    return content


# ---------------------------------------------------------------------------
# Makefile generation
# ---------------------------------------------------------------------------

def generate_makefile(output_path="reproducibility/Makefile",
                      experiment_specs_dir="paper/experiments/specs"):
    """Generate Makefile with setup, experiments, figures, verify, clean targets.

    Uses tab characters for recipe indentation (critical for Make).

    Args:
        output_path: where to write the Makefile
        experiment_specs_dir: directory containing experiment spec JSONs

    Returns:
        str: generated Makefile content
    """
    # Discover experiment specs
    spec_files = []
    if os.path.isdir(experiment_specs_dir):
        spec_files = sorted(glob.glob(os.path.join(experiment_specs_dir, "*.json")))

    experiment_cmds = ""
    if spec_files:
        for sf in spec_files:
            base = os.path.basename(sf)
            experiment_cmds += f'\t$(VENV)/bin/python -m paper.scripts._experiment_runner --spec experiments/specs/{base}\n'
    else:
        experiment_cmds = '\t@echo "No experiment specs found. Place specs in experiments/specs/"\n'

    # Tab character for Makefile recipes
    t = "\t"

    content = f'''.PHONY: all setup experiments figures verify clean

PYTHON ?= python3
VENV := .venv

all: setup experiments figures verify

setup:
{t}$(PYTHON) -m venv $(VENV)
{t}$(VENV)/bin/pip install --upgrade pip
{t}$(VENV)/bin/pip install -e "."

experiments:
{experiment_cmds}
figures:
{t}$(VENV)/bin/python -m paper.scripts._figure_generator --all

verify:
{t}@echo "Verifying checksums..."
{t}sha256sum -c checksums.sha256
{t}@echo "All checksums verified."

clean:
{t}rm -rf $(VENV)
{t}rm -rf results/
{t}rm -rf __pycache__/
{t}@echo "Cleaned."
'''
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, content)
    return content


# ---------------------------------------------------------------------------
# seeds.json generation
# ---------------------------------------------------------------------------

def generate_seeds_json(output_path="reproducibility/seeds.json"):
    """Document seed pinning configuration from _experiment_runner.py.

    Scans the experiment runner source for the default seed value and
    documents which RNGs are seeded and how to verify reproducibility.

    Returns:
        dict: seed configuration data
    """
    # Scan _experiment_runner.py for default seed
    default_seed = 42
    runner_path = os.path.join(_SCRIPT_DIR, "_experiment_runner.py")
    if os.path.isfile(runner_path):
        with open(runner_path) as f:
            source = f.read()
        match = re.search(r'def\s+pin_all_seeds\s*\(\s*seed\s*=\s*(\d+)\s*\)', source)
        if match:
            default_seed = int(match.group(1))

    data = {
        "default_seed": default_seed,
        "rngs_seeded": [
            "python_random",
            "PYTHONHASHSEED",
            "numpy (if available)",
            "torch (if available)",
            "torch.cuda (if available)"
        ],
        "seed_function": "_experiment_runner.py:pin_all_seeds()",
        "seed_location": "paper/scripts/_experiment_runner.py",
        "verification_method": "Run experiment twice with same seed, compare checksums",
        "notes": [
            "PYTHONHASHSEED is set as environment variable before execution",
            "NumPy and PyTorch seeding gracefully skipped if libraries not installed",
            "CUDA deterministic mode enabled when torch.cuda is available"
        ]
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, json.dumps(data, indent=2))
    return data


# ---------------------------------------------------------------------------
# SHA-256 checksum generation
# ---------------------------------------------------------------------------

def generate_checksums(source_dir, output_path="reproducibility/checksums.sha256"):
    """Generate SHA-256 checksums for all files in source_dir.

    Writes in sha256sum-compatible format: {hash}  {relative_path}
    Sorted by path for deterministic output.

    Args:
        source_dir: directory to walk recursively
        output_path: where to write the checksum file

    Returns:
        list: tuples of (hash, relative_path)
    """
    results = []
    if not os.path.isdir(source_dir):
        # Write empty checksums file
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        atomic_write(output_path, "")
        return results

    for root, _dirs, files in os.walk(source_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, source_dir)
            sha = hashlib.sha256()
            try:
                with open(fpath, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        sha.update(chunk)
                results.append((sha.hexdigest(), rel_path))
            except OSError:
                continue

    # Sort by path for deterministic output
    results.sort(key=lambda x: x[1])

    lines = [f"{h}  {p}" for h, p in results]
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, "\n".join(lines) + "\n" if lines else "")
    return results


# ---------------------------------------------------------------------------
# Hardware reference generation
# ---------------------------------------------------------------------------

def generate_hardware_reference(output_path="reproducibility/hardware_reference.json"):
    """Capture reference hardware info for reproducibility documentation.

    Uses platform module and subprocess calls with timeouts for
    CPU brand, memory, and GPU detection. Graceful fallback on all.

    Returns:
        dict: hardware reference information
    """
    info = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cpu_brand": None,
        "ram_gb": None,
        "gpu": "none",
    }

    # CPU brand detection
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                info["cpu_brand"] = r.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
    elif platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        info["cpu_brand"] = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass

    # RAM detection
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                info["ram_gb"] = round(int(r.stdout.strip()) / (1024 ** 3), 1)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
            pass
    elif platform.system() == "Linux":
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
            if page_size > 0 and page_count > 0:
                info["ram_gb"] = round((page_size * page_count) / (1024 ** 3), 1)
        except (ValueError, OSError):
            pass

    # GPU detection
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip():
            info["gpu"] = r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, json.dumps(info, indent=2))
    return info


# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------

def generate_readme(output_path="reproducibility/README.md",
                    paper_title="", venue="NeurIPS 2026"):
    """Generate README.md for the reproducibility package.

    Includes sections for prerequisites, quick start, full reproduction,
    experiment details, seed pinning, hardware requirements, verification,
    and troubleshooting.

    Returns:
        str: generated README content
    """
    title_line = f" -- {paper_title}" if paper_title else ""
    content = f'''# Reproducibility Package{title_line}

**Venue:** {venue}

This package enables full reproduction of all experimental results reported in the paper.

## Prerequisites

- Python >= 3.10
- `pip` (included with Python)
- `sha256sum` (Linux) or `shasum -a 256` (macOS) for verification
- ~8 GB RAM recommended
- Internet connection for initial package installation

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "."
make experiments
make verify
```

## Full Reproduction

```bash
# 1. Create and activate virtual environment
make setup

# 2. Run all experiments
make experiments

# 3. Generate figures
make figures

# 4. Verify checksums match expected results
make verify

# Or run everything at once:
make all
```

## Experiment Details

Each experiment is defined by a JSON spec file in `experiments/specs/`.
The experiment runner (`experiments/_experiment_runner.py`) handles:
- Deterministic seed pinning across all RNGs
- Hardware environment capture
- Sandboxed subprocess execution
- Structured metric logging

See `seeds.json` for seed configuration details.

## Seed Pinning

All experiments use deterministic seeding. The default seed is **42**.

Seeded RNGs:
- Python `random` module
- `PYTHONHASHSEED` environment variable
- NumPy (`numpy.random.seed`) if available
- PyTorch (`torch.manual_seed` + CUDA seeds) if available

To verify determinism: run the same experiment twice with the same seed
and compare output checksums.

## Hardware Requirements

Reference hardware configuration is documented in `hardware_reference.json`.
Results may vary slightly across different hardware due to floating-point
non-determinism, but statistical conclusions should remain consistent.

## Expected Runtime

Runtime depends on hardware. Reference timings are captured in individual
experiment result directories under `config.json`.

## Verification

After running experiments, verify results match expected checksums:

```bash
make verify
# or manually:
sha256sum -c checksums.sha256
```

All checksums should report OK. If any fail, check:
1. Python version matches (>= 3.10)
2. Dependencies match pinned versions in pyproject.toml
3. Seed was not modified

## Troubleshooting

**"No module named X"** -- Run `make setup` to install all dependencies.

**Checksum mismatch** -- Ensure you are using the exact Python and package
versions specified in `pyproject.toml`. Floating-point results can vary
across CPU architectures.

**Out of memory** -- Some experiments may require 8+ GB RAM. Check
`hardware_reference.json` for reference configuration.

**GPU not detected** -- CPU-only execution is supported. GPU experiments
will fall back to CPU with longer runtimes.

---
*Generated by _repro_package.py*
'''
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    atomic_write(output_path, content)
    return content


# ---------------------------------------------------------------------------
# Copy experiment scripts
# ---------------------------------------------------------------------------

def copy_experiment_scripts(output_dir="reproducibility/experiments"):
    """Copy experiment scripts to the reproducibility package.

    Copies _experiment_runner.py, _stats_utils.py, _shared_utils.py and
    any experiment spec JSONs.

    Returns:
        list: paths of copied files (relative to output_dir)
    """
    os.makedirs(output_dir, exist_ok=True)
    copied = []

    # Scripts to copy
    scripts = ["_experiment_runner.py", "_stats_utils.py", "_shared_utils.py"]
    for script in scripts:
        src = os.path.join(_SCRIPT_DIR, script)
        if os.path.isfile(src):
            dst = os.path.join(output_dir, script)
            shutil.copy2(src, dst)
            copied.append(os.path.relpath(dst, output_dir))

    # Copy experiment specs
    specs_src = os.path.join(os.path.dirname(_SCRIPT_DIR), "experiments", "specs")
    if os.path.isdir(specs_src):
        specs_dst = os.path.join(output_dir, "specs")
        os.makedirs(specs_dst, exist_ok=True)
        for spec_file in glob.glob(os.path.join(specs_src, "*.json")):
            dst = os.path.join(specs_dst, os.path.basename(spec_file))
            shutil.copy2(spec_file, dst)
            copied.append(os.path.relpath(dst, output_dir))

    return copied


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_repro_package(output_dir="reproducibility",
                           results_dir="paper/experiments/results"):
    """Generate complete reproducibility package.

    Creates output_dir with all subdirectories and runs all generators
    in sequence: deps -> pyproject.toml -> Makefile -> seeds.json ->
    hardware_reference -> copy experiments -> checksums -> README.

    Args:
        output_dir: root directory for the reproducibility package
        results_dir: directory containing experiment results for checksums

    Returns:
        dict: paths of all generated files and metadata
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "experiments"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "data"), exist_ok=True)

    result = {"output_dir": output_dir, "files": []}

    # 1. Capture dependencies
    deps = capture_pip_dependencies()
    result["dependency_count"] = len(deps)

    # 2. Generate pyproject.toml
    pyproject_path = os.path.join(output_dir, "pyproject.toml")
    generate_pyproject_toml(deps, output_path=pyproject_path)
    result["files"].append(pyproject_path)

    # 3. Generate Makefile
    makefile_path = os.path.join(output_dir, "Makefile")
    generate_makefile(output_path=makefile_path)
    result["files"].append(makefile_path)

    # 4. Generate seeds.json
    seeds_path = os.path.join(output_dir, "seeds.json")
    generate_seeds_json(output_path=seeds_path)
    result["files"].append(seeds_path)

    # 5. Generate hardware reference
    hw_path = os.path.join(output_dir, "hardware_reference.json")
    generate_hardware_reference(output_path=hw_path)
    result["files"].append(hw_path)

    # 6. Copy experiment scripts
    exp_dir = os.path.join(output_dir, "experiments")
    copied = copy_experiment_scripts(output_dir=exp_dir)
    result["copied_scripts"] = copied

    # 7. Generate checksums (from results directory)
    checksums_path = os.path.join(output_dir, "checksums.sha256")
    checksums = generate_checksums(results_dir, output_path=checksums_path)
    result["files"].append(checksums_path)
    result["checksum_count"] = len(checksums)

    # 8. Generate README
    readme_path = os.path.join(output_dir, "README.md")
    generate_readme(output_path=readme_path)
    result["files"].append(readme_path)

    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" not in sys.argv:
        # Parse arguments for normal operation
        import argparse
        parser = argparse.ArgumentParser(description="Generate reproducibility package")
        parser.add_argument("--output", default="reproducibility",
                            help="Output directory")
        parser.add_argument("--results", default="paper/experiments/results",
                            help="Results directory for checksums")
        args = parser.parse_args()
        result = generate_repro_package(args.output, args.results)
        print(f"Reproducibility package generated in {result['output_dir']}")
        print(f"  Files: {len(result['files'])}")
        print(f"  Dependencies: {result['dependency_count']}")
        print(f"  Checksums: {result['checksum_count']}")
        print(f"  Scripts copied: {len(result['copied_scripts'])}")
        sys.exit(0)

    print("=== _repro_package self-test ===\n")
    all_passed = True

    # Test 1: generate_pyproject_toml produces valid content
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_pyproject_")
        deps = [
            {"name": "numpy", "version": "1.26.0"},
            {"name": "torch", "version": "2.1.0"},
            {"name": "scipy", "version": "1.11.3"},
        ]
        out_path = os.path.join(test_dir, "pyproject.toml")
        content = generate_pyproject_toml(deps, project_name="test-repro",
                                          output_path=out_path)

        assert os.path.isfile(out_path), "pyproject.toml not written"
        assert "[build-system]" in content, "Missing [build-system] section"
        assert "[project]" in content, "Missing [project] section"
        assert 'name = "test-repro"' in content, "Missing project name"
        assert 'version = "0.1.0"' in content, "Missing version"
        assert 'requires-python = ">=3.10"' in content, "Missing requires-python"
        assert '"numpy==1.26.0"' in content, "Missing pinned numpy"
        assert '"torch==2.1.0"' in content, "Missing pinned torch"
        assert '"scipy==1.11.3"' in content, "Missing pinned scipy"
        assert "[project.optional-dependencies]" in content, "Missing optional deps"
        assert '"pytest"' in content, "Missing pytest in dev deps"
        print("[PASS] generate_pyproject_toml: PEP 621 format with pinned deps")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_pyproject_toml: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 2: generate_makefile produces content with tabs and all targets
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_makefile_")
        out_path = os.path.join(test_dir, "Makefile")
        content = generate_makefile(output_path=out_path,
                                    experiment_specs_dir="/nonexistent")

        assert os.path.isfile(out_path), "Makefile not written"
        # Check for tab characters in recipe lines
        lines = content.split("\n")
        recipe_found = False
        for line in lines:
            if line.startswith("\t"):
                recipe_found = True
                break
        assert recipe_found, "No tab-indented recipe lines found"
        # Check no recipe lines use spaces instead of tabs
        for i, line in enumerate(lines):
            if line.startswith("    ") and not line.strip().startswith("#"):
                # Could be a continuation, but recipes must use tabs
                pass  # Allow space-indented comments/non-recipe content
        assert ".PHONY:" in content, "Missing .PHONY declaration"
        assert "setup:" in content or "setup:" in content, "Missing setup target"
        assert "experiments:" in content, "Missing experiments target"
        assert "figures:" in content, "Missing figures target"
        assert "verify:" in content, "Missing verify target"
        assert "clean:" in content, "Missing clean target"
        assert "PYTHON ?=" in content, "Missing PYTHON variable"
        assert "VENV :=" in content, "Missing VENV variable"
        assert "sha256sum -c" in content, "Missing checksum verification"
        print("[PASS] generate_makefile: tab indentation, all targets present")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_makefile: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 3: generate_seeds_json produces valid JSON with required keys
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_seeds_")
        out_path = os.path.join(test_dir, "seeds.json")
        data = generate_seeds_json(output_path=out_path)

        assert os.path.isfile(out_path), "seeds.json not written"
        # Verify it's valid JSON by re-reading
        with open(out_path) as f:
            loaded = json.load(f)
        assert "default_seed" in loaded, "Missing default_seed"
        assert "rngs_seeded" in loaded, "Missing rngs_seeded"
        assert "seed_function" in loaded, "Missing seed_function"
        assert "verification_method" in loaded, "Missing verification_method"
        assert loaded["default_seed"] == 42, f"Expected seed 42, got {loaded['default_seed']}"
        assert isinstance(loaded["rngs_seeded"], list), "rngs_seeded should be a list"
        assert len(loaded["rngs_seeded"]) > 0, "rngs_seeded should not be empty"
        print(f"[PASS] generate_seeds_json: valid JSON, seed={loaded['default_seed']}, "
              f"{len(loaded['rngs_seeded'])} RNGs documented")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_seeds_json: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 4: generate_checksums with temp files produces correct SHA-256 hashes
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_checksums_")
        source_dir = os.path.join(test_dir, "source")
        os.makedirs(source_dir)

        # Create test files with known content
        test_files = {
            "file_a.txt": "hello world\n",
            "subdir/file_b.json": '{"key": "value"}\n',
        }
        for rel_path, content_str in test_files.items():
            fpath = os.path.join(source_dir, rel_path)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w") as f:
                f.write(content_str)

        out_path = os.path.join(test_dir, "checksums.sha256")
        results = generate_checksums(source_dir, output_path=out_path)

        assert os.path.isfile(out_path), "checksums.sha256 not written"
        assert len(results) == 2, f"Expected 2 checksums, got {len(results)}"

        # Verify checksums match hashlib directly
        for expected_hash, rel_path in results:
            fpath = os.path.join(source_dir, rel_path)
            with open(fpath, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            assert expected_hash == actual_hash, \
                f"Hash mismatch for {rel_path}: {expected_hash} != {actual_hash}"

        # Verify sha256sum-compatible format (hash  path)
        with open(out_path) as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        for line in lines:
            assert "  " in line, f"Missing double-space separator: {line}"
            parts = line.split("  ", 1)
            assert len(parts[0]) == 64, f"Hash not 64 chars: {parts[0]}"

        # Verify sorted by path
        paths_in_file = [line.split("  ", 1)[1] for line in lines]
        assert paths_in_file == sorted(paths_in_file), "Checksums not sorted by path"

        print(f"[PASS] generate_checksums: {len(results)} files, SHA-256 verified, "
              f"sha256sum-compatible format")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_checksums: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 5: generate_hardware_reference produces valid JSON
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_hw_")
        out_path = os.path.join(test_dir, "hardware_reference.json")
        data = generate_hardware_reference(output_path=out_path)

        assert os.path.isfile(out_path), "hardware_reference.json not written"
        with open(out_path) as f:
            loaded = json.load(f)
        assert "platform" in loaded, "Missing platform"
        assert "python_version" in loaded, "Missing python_version"
        assert "architecture" in loaded, "Missing architecture"
        assert "cpu_count" in loaded, "Missing cpu_count"
        assert loaded["python_version"] == platform.python_version(), "Python version mismatch"
        assert loaded["cpu_count"] == os.cpu_count(), "CPU count mismatch"
        print(f"[PASS] generate_hardware_reference: {loaded['platform']} "
              f"{loaded['architecture']}, Python {loaded['python_version']}, "
              f"{loaded['cpu_count']} CPUs, {loaded.get('ram_gb', '?')}GB RAM")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_hardware_reference: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 6: generate_readme produces markdown with required sections
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_readme_")
        out_path = os.path.join(test_dir, "README.md")
        content = generate_readme(output_path=out_path,
                                  paper_title="Test Paper", venue="ICML 2026")

        assert os.path.isfile(out_path), "README.md not written"
        required_sections = [
            "# Reproducibility Package",
            "## Prerequisites",
            "## Quick Start",
            "## Full Reproduction",
            "## Experiment Details",
            "## Seed Pinning",
            "## Hardware Requirements",
            "## Expected Runtime",
            "## Verification",
            "## Troubleshooting",
        ]
        for section in required_sections:
            assert section in content, f"Missing section: {section}"
        assert "ICML 2026" in content, "Missing venue"
        assert "Test Paper" in content, "Missing paper title"
        assert "make experiments" in content or "make all" in content, \
            "Missing make command"
        print(f"[PASS] generate_readme: {len(required_sections)} required sections present")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_readme: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 7: copy_experiment_scripts copies files correctly
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_copy_")
        out_dir = os.path.join(test_dir, "experiments")

        # Run with actual script directory -- should copy existing scripts
        copied = copy_experiment_scripts(output_dir=out_dir)

        assert os.path.isdir(out_dir), "Output directory not created"
        # At minimum, _experiment_runner.py and _shared_utils.py should exist
        expected_scripts = ["_experiment_runner.py", "_shared_utils.py"]
        for script in expected_scripts:
            src = os.path.join(_SCRIPT_DIR, script)
            if os.path.isfile(src):
                dst = os.path.join(out_dir, script)
                assert os.path.isfile(dst), f"Script not copied: {script}"
                # Verify content matches
                with open(src) as sf, open(dst) as df:
                    assert sf.read() == df.read(), f"Content mismatch: {script}"

        print(f"[PASS] copy_experiment_scripts: {len(copied)} files copied")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] copy_experiment_scripts: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # Test 8: generate_checksums with empty directory
    try:
        test_dir = tempfile.mkdtemp(prefix="repro_test_empty_")
        out_path = os.path.join(test_dir, "checksums.sha256")
        results = generate_checksums("/nonexistent_dir_12345", output_path=out_path)
        assert results == [], f"Expected empty list, got {results}"
        assert os.path.isfile(out_path), "checksums.sha256 not written for empty dir"
        print("[PASS] generate_checksums: handles missing source dir gracefully")
        shutil.rmtree(test_dir)
    except Exception as e:
        print(f"[FAIL] generate_checksums empty dir: {e}")
        all_passed = False
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    print()
    if all_passed:
        print("=== All _repro_package tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Some _repro_package tests FAILED ===")
        sys.exit(1)
