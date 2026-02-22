#!/usr/bin/env python3
"""Figure generation pipeline with SciencePlots styling and VLM readability review.

Generates publication-quality figures from spec dicts: PDF (vector) and PNG
(300 DPI raster) with colorblind-safe palettes, figure metadata tracking,
reproducible per-figure scripts, and a VLM readability checklist.

Usage:
  python3 paper/scripts/_figure_generator.py --spec path/to/spec.json
  python3 paper/scripts/_figure_generator.py --self-test
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

# Project path setup -- same pattern as all other scripts
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# LaTeX / style detection
# ---------------------------------------------------------------------------

def check_latex_available():
    """Check if LaTeX is usable for SciencePlots rendering.

    First checks if the latex binary exists (shutil.which or TinyTeX path).
    Then does a quick smoke test to verify LaTeX can actually render text,
    because TinyTeX may be missing packages (e.g., type1cm.sty).

    Returns True if LaTeX is found AND functional, False otherwise.
    """
    import shutil as _shutil
    import subprocess as _sp

    latex_bin = _shutil.which("latex")
    if not latex_bin:
        tinytex_path = os.path.expanduser(
            "~/Library/TinyTeX/bin/universal-darwin/latex"
        )
        if os.path.isfile(tinytex_path):
            latex_bin = tinytex_path
        else:
            return False

    # Smoke test: verify LaTeX can render with SciencePlots-required packages.
    # SciencePlots IEEE style uses type1cm, type1ec, mathptmx -- if any are
    # missing, matplotlib will crash at savefig time. Better to detect early.
    import tempfile as _tf
    test_tex = r"""\documentclass{article}
\usepackage{type1cm}
\usepackage{type1ec}
\usepackage{mathptmx}
\begin{document}
test
\end{document}
"""
    try:
        with _tf.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "test.tex")
            with open(tex_path, "w") as f:
                f.write(test_tex)
            result = _sp.run(
                [latex_bin, "-interaction=nonstopmode", "-halt-on-error", "test.tex"],
                capture_output=True, text=True, timeout=15, cwd=tmpdir,
            )
            return result.returncode == 0
    except Exception:
        return False


def setup_style():
    """Configure matplotlib with SciencePlots styling and colorblind palette.

    Imports matplotlib (Agg backend) and scienceplots. Applies SciencePlots
    styles with LaTeX or no-latex fallback. Sets seaborn colorblind palette.

    Returns dict with {latex: bool, scienceplots: bool, style: str}.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    latex_ok = check_latex_available()
    sp_ok = False
    style_name = "default"

    # SciencePlots must be imported before plt.style.use (v2.0+ requirement)
    try:
        import scienceplots  # noqa: F401
        sp_ok = True
    except ImportError:
        print("WARNING: SciencePlots not installed, using default matplotlib style")

    if sp_ok:
        if latex_ok:
            plt.style.use(["science", "ieee"])
            style_name = "science+ieee"
        else:
            plt.style.use(["science", "no-latex"])
            style_name = "science+no-latex"

    # Colorblind-safe palette via seaborn
    try:
        import seaborn as sns
        sns.set_palette("colorblind")
    except ImportError:
        print("WARNING: seaborn not installed, using default palette")

    return {"latex": latex_ok, "scienceplots": sp_ok, "style": style_name}


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def _render_bar(ax, data):
    """Render a bar chart on the given axes."""
    labels = data["labels"]
    values = data["values"]
    errors = data.get("errors")
    groups = data.get("groups")

    if groups:
        # Grouped bar chart
        import numpy as np
        n_groups = len(groups)
        x = np.arange(len(labels))
        width = 0.8 / n_groups
        for i, (group_name, group_vals) in enumerate(groups.items()):
            offset = (i - n_groups / 2 + 0.5) * width
            ax.bar(x + offset, group_vals, width, label=group_name)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()
    else:
        ax.bar(labels, values, yerr=errors, capsize=3)


def _render_line(ax, data):
    """Render a line plot on the given axes."""
    x = data["x"]
    y_data = data["y"]
    labels = data.get("labels", [])
    errors = data.get("errors")

    # y can be a single list or list of lists (multiple series)
    if y_data and isinstance(y_data[0], (list, tuple)):
        for i, series in enumerate(y_data):
            label = labels[i] if i < len(labels) else f"Series {i+1}"
            ax.plot(x, series, label=label, marker="o", markersize=3)
        ax.legend()
    else:
        label = labels[0] if labels else None
        ax.plot(x, y_data, label=label, marker="o", markersize=3)
        if errors:
            ax.fill_between(
                x,
                [v - e for v, e in zip(y_data, errors)],
                [v + e for v, e in zip(y_data, errors)],
                alpha=0.2,
            )
        if label:
            ax.legend()


def _render_scatter(ax, data):
    """Render a scatter plot on the given axes."""
    ax.scatter(data["x"], data["y"], alpha=0.7)


def _render_heatmap(ax, data):
    """Render a heatmap on the given axes."""
    import numpy as np
    matrix = np.array(data["matrix"])
    im = ax.imshow(matrix, aspect="auto", cmap="viridis")
    ax.figure.colorbar(im, ax=ax)
    if "xlabels" in data:
        ax.set_xticks(range(len(data["xlabels"])))
        ax.set_xticklabels(data["xlabels"], rotation=45, ha="right")
    if "ylabels" in data:
        ax.set_yticks(range(len(data["ylabels"])))
        ax.set_yticklabels(data["ylabels"])


def _render_box(ax, data):
    """Render a box plot on the given axes."""
    groups = data["groups"]
    labels = list(groups.keys())
    values = list(groups.values())
    ax.boxplot(values, tick_labels=labels)


# Dispatch table for figure types
_RENDERERS = {
    "bar": _render_bar,
    "line": _render_line,
    "scatter": _render_scatter,
    "heatmap": _render_heatmap,
    "box": _render_box,
}


def _generate_reproducible_script(spec, output_dir):
    """Save a self-contained Python script that regenerates the figure.

    The script embeds the data so it can reproduce the figure independently.
    """
    fig_name = spec["fig_name"]
    scripts_dir = os.path.join(output_dir, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    script_path = os.path.join(scripts_dir, f"{fig_name}.py")

    # Build a standalone script with embedded data
    data_json = json.dumps(spec["data"], indent=2)
    figsize = spec.get("figsize", (6.5, 4.0))
    fig_type = spec["fig_type"]

    lines = [
        '#!/usr/bin/env python3',
        f'"""Reproducible script for figure: {fig_name}',
        f'',
        f'Generated: {datetime.now(timezone.utc).isoformat()}',
        f'Type: {fig_type}',
        f'"""',
        'import json',
        'import matplotlib',
        'matplotlib.use("Agg")',
        'import matplotlib.pyplot as plt',
        '',
        '# Attempt SciencePlots styling',
        'try:',
        '    import scienceplots  # noqa: F401',
        '    plt.style.use(["science", "ieee"])',
        'except (ImportError, OSError):',
        '    try:',
        '        plt.style.use(["science", "no-latex"])',
        '    except Exception:',
        '        pass',
        '',
        'try:',
        '    import seaborn as sns',
        '    sns.set_palette("colorblind")',
        'except ImportError:',
        '    pass',
        '',
        f'# Embedded data',
        f'data = json.loads({json.dumps(data_json)!r})',
        '',
        f'fig, ax = plt.subplots(figsize={figsize!r})',
    ]

    # Type-specific rendering code
    if fig_type == "bar":
        lines += [
            'labels = data["labels"]',
            'values = data["values"]',
            'errors = data.get("errors")',
            'ax.bar(labels, values, yerr=errors, capsize=3)',
        ]
    elif fig_type == "line":
        lines += [
            'x = data["x"]',
            'y_data = data["y"]',
            'labels = data.get("labels", [])',
            'if y_data and isinstance(y_data[0], (list, tuple)):',
            '    for i, series in enumerate(y_data):',
            '        label = labels[i] if i < len(labels) else f"Series {i+1}"',
            '        ax.plot(x, series, label=label, marker="o", markersize=3)',
            '    ax.legend()',
            'else:',
            '    ax.plot(x, y_data, marker="o", markersize=3)',
        ]
    elif fig_type == "scatter":
        lines += [
            'ax.scatter(data["x"], data["y"], alpha=0.7)',
        ]
    elif fig_type == "heatmap":
        lines += [
            'import numpy as np',
            'matrix = np.array(data["matrix"])',
            'im = ax.imshow(matrix, aspect="auto", cmap="viridis")',
            'fig.colorbar(im, ax=ax)',
        ]
    elif fig_type == "box":
        lines += [
            'groups = data["groups"]',
            'ax.boxplot(list(groups.values()), tick_labels=list(groups.keys()))',
        ]

    # Common final lines
    title = spec.get("title", "")
    xlabel = spec.get("xlabel", "")
    ylabel = spec.get("ylabel", "")
    lines += [
        '',
        f'ax.set_title({title!r})',
        f'ax.set_xlabel({xlabel!r})',
        f'ax.set_ylabel({ylabel!r})',
        '',
        f'fig.savefig("{fig_name}.pdf", bbox_inches="tight")',
        f'fig.savefig("{fig_name}.png", bbox_inches="tight", dpi=300)',
        'plt.close(fig)',
        f'print("Generated: {fig_name}.pdf and {fig_name}.png")',
    ]

    content = "\n".join(lines) + "\n"
    atomic_write(script_path, content)
    return script_path


def generate_figure(spec, output_dir=None):
    """Generate a figure from a spec dict.

    Args:
        spec: dict with fig_name, fig_type, data, title (optional),
              xlabel, ylabel, figsize (optional), section, caption (optional),
              data_source (optional).
        output_dir: base directory for figure output (default: paper/output/figures).

    Returns:
        dict with pdf_path, png_path, script_path.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_name = spec["fig_name"]
    fig_type = spec["fig_type"]
    if output_dir is None:
        output_dir = os.path.join("paper", "output", "figures")
    os.makedirs(output_dir, exist_ok=True)

    figsize = spec.get("figsize", (6.5, 4.0))
    # Convert list to tuple if needed (JSON round-trips produce lists)
    if isinstance(figsize, list):
        figsize = tuple(figsize)

    fig, ax = plt.subplots(figsize=figsize)

    # Dispatch rendering
    renderer = _RENDERERS.get(fig_type)
    if renderer is None:
        raise ValueError(f"Unknown figure type: {fig_type!r}. "
                         f"Supported: {list(_RENDERERS.keys())}")
    renderer(ax, spec["data"])

    # Set labels and title
    if spec.get("title"):
        ax.set_title(spec["title"])
    if spec.get("xlabel"):
        ax.set_xlabel(spec["xlabel"])
    if spec.get("ylabel"):
        ax.set_ylabel(spec["ylabel"])

    # Save PDF (vector) and PNG (raster preview)
    pdf_path = os.path.join(output_dir, f"{fig_name}.pdf")
    png_path = os.path.join(output_dir, f"{fig_name}.png")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=300)
    plt.close(fig)

    # Save reproducible script
    script_path = _generate_reproducible_script(spec, output_dir)

    # Update metadata
    fig_info = {
        "id": fig_name,
        "filename": f"{fig_name}.pdf",
        "script": f"figures/scripts/{fig_name}.py",
        "section": spec.get("section", ""),
        "caption": spec.get("caption", ""),
        "data_source": spec.get("data_source", ""),
        "dimensions": {
            "width_inches": figsize[0],
            "height_inches": figsize[1],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_figure_metadata(fig_info, output_dir=output_dir)

    return {
        "pdf_path": pdf_path,
        "png_path": png_path,
        "script_path": script_path,
    }


def update_figure_metadata(fig_info, output_dir=None):
    """Update figure_metadata.json with a new or updated entry.

    Reads existing metadata (or creates new), appends or replaces the entry
    matching fig_info["id"], writes back atomically.

    Args:
        fig_info: dict with id, filename, script, section, caption,
                  data_source, dimensions, generated_at.
        output_dir: base directory for figure output.
    """
    if output_dir is None:
        output_dir = os.path.join("paper", "output", "figures")
    meta_path = os.path.join(output_dir, "figure_metadata.json")

    # Load existing or start fresh
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    else:
        meta = {"figures": []}

    # Replace existing entry with same id, or append
    fig_id = fig_info["id"]
    meta["figures"] = [e for e in meta["figures"] if e.get("id") != fig_id]
    meta["figures"].append(fig_info)

    atomic_write(meta_path, json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# VLM readability checklist
# ---------------------------------------------------------------------------

def vlm_readability_checklist(fig_name):
    """Return VLM readability checklist for agent-based figure review.

    Returns dict with checklist items keyed by check name. Each value is
    a prompt string for the figure-generator agent to evaluate when it
    reads the PNG using Claude's native vision capability.
    """
    return {
        "axis_labels_readable": (
            f"Are all axis labels in {fig_name} readable at 50% zoom?"
        ),
        "colorblind_safe": (
            f"Is the color palette in {fig_name} colorblind-safe?"
        ),
        "error_bars_present": (
            f"Are error bars present in {fig_name} where expected?"
        ),
        "grayscale_interpretable": (
            f"Is {fig_name} interpretable in grayscale print?"
        ),
        "legend_clear": (
            f"Are legends in {fig_name} clear and non-overlapping with data?"
        ),
        "min_font_8pt": (
            f"Is the minimum font size in {fig_name} >= 8pt?"
        ),
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """Self-test: generate mock figures, verify outputs, clean up."""
    import traceback

    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, None))
            print(f"[PASS] {name}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()

    # Use a temp directory for all test output
    test_dir = tempfile.mkdtemp(prefix="fig_gen_test_")
    figures_dir = os.path.join(test_dir, "figures")
    scripts_dir = os.path.join(figures_dir, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)

    # 1. Setup style
    def test_setup_style():
        info = setup_style()
        assert isinstance(info, dict), "setup_style must return dict"
        assert "latex" in info, "missing 'latex' key"
        assert "scienceplots" in info, "missing 'scienceplots' key"
        assert "style" in info, "missing 'style' key"
        print(f"  Style: {info['style']}, LaTeX: {info['latex']}, SciencePlots: {info['scienceplots']}")

    check("setup_style", test_setup_style)

    # 2. Generate bar chart
    def test_bar_chart():
        spec = {
            "fig_name": "test_bar",
            "fig_type": "bar",
            "data": {
                "labels": ["Method A", "Method B", "Method C"],
                "values": [85.2, 79.8, 72.5],
                "errors": [1.3, 2.1, 1.8],
            },
            "title": "Mock Accuracy Comparison",
            "xlabel": "Method",
            "ylabel": "Accuracy (%)",
            "figsize": (6.5, 4.0),
            "section": "results",
            "caption": "Test bar chart with error bars.",
            "data_source": "mock",
        }
        result = generate_figure(spec, output_dir=figures_dir)
        assert os.path.isfile(result["pdf_path"]), f"PDF not found: {result['pdf_path']}"
        assert os.path.isfile(result["png_path"]), f"PNG not found: {result['png_path']}"
        assert os.path.isfile(result["script_path"]), f"Script not found: {result['script_path']}"
        # Verify PDF is non-empty
        assert os.path.getsize(result["pdf_path"]) > 0, "PDF is empty"
        assert os.path.getsize(result["png_path"]) > 0, "PNG is empty"

    check("bar_chart_generation", test_bar_chart)

    # 3. Generate line plot
    def test_line_plot():
        spec = {
            "fig_name": "test_line",
            "fig_type": "line",
            "data": {
                "x": [1, 2, 3, 4, 5],
                "y": [[10, 20, 25, 30, 35], [8, 15, 22, 28, 33]],
                "labels": ["Our Method", "Baseline"],
            },
            "title": "Mock Training Curve",
            "xlabel": "Epoch",
            "ylabel": "Score",
            "figsize": (6.5, 4.0),
            "section": "results",
            "caption": "Test line plot with two series.",
            "data_source": "mock",
        }
        result = generate_figure(spec, output_dir=figures_dir)
        assert os.path.isfile(result["pdf_path"]), f"PDF not found: {result['pdf_path']}"
        assert os.path.isfile(result["png_path"]), f"PNG not found: {result['png_path']}"
        assert os.path.isfile(result["script_path"]), f"Script not found: {result['script_path']}"

    check("line_plot_generation", test_line_plot)

    # 4. Verify figure_metadata.json
    def test_metadata():
        meta_path = os.path.join(figures_dir, "figure_metadata.json")
        assert os.path.isfile(meta_path), f"Metadata file not found: {meta_path}"
        with open(meta_path) as f:
            meta = json.load(f)
        assert "figures" in meta, "Missing 'figures' key in metadata"
        assert len(meta["figures"]) == 2, f"Expected 2 entries, got {len(meta['figures'])}"
        # Check required fields
        for entry in meta["figures"]:
            for key in ("id", "filename", "script", "section", "dimensions", "generated_at"):
                assert key in entry, f"Missing key '{key}' in metadata entry"

    check("figure_metadata_json", test_metadata)

    # 5. Verify reproducible scripts
    def test_reproducible_scripts():
        for name in ("test_bar", "test_line"):
            script_path = os.path.join(scripts_dir, f"{name}.py")
            assert os.path.isfile(script_path), f"Script not found: {script_path}"
            with open(script_path) as f:
                content = f.read()
            assert "matplotlib" in content, f"Script {name}.py missing matplotlib import"
            assert len(content) > 50, f"Script {name}.py suspiciously short"

    check("reproducible_scripts", test_reproducible_scripts)

    # 6. VLM readability checklist
    def test_vlm_checklist():
        checklist = vlm_readability_checklist("test_bar")
        assert isinstance(checklist, dict), "Checklist must be dict"
        expected_keys = {
            "axis_labels_readable",
            "colorblind_safe",
            "error_bars_present",
            "grayscale_interpretable",
            "legend_clear",
            "min_font_8pt",
        }
        assert set(checklist.keys()) == expected_keys, (
            f"Checklist keys mismatch: got {set(checklist.keys())}, expected {expected_keys}"
        )

    check("vlm_readability_checklist", test_vlm_checklist)

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n=== _figure_generator self-test: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    elif "--spec" in sys.argv:
        idx = sys.argv.index("--spec")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --spec requires a path argument", file=sys.stderr)
            sys.exit(1)
        spec_path = sys.argv[idx + 1]
        with open(spec_path) as f:
            spec = json.load(f)
        setup_style()
        result = generate_figure(spec)
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
        sys.exit(0)
