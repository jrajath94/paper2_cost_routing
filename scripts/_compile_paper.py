#!/usr/bin/env python3
"""LaTeX compilation orchestrator with Pandoc conversion, Tectonic invocation,
and error recovery.

Converts markdown section drafts to LaTeX via Pandoc, assembles a NeurIPS
master document, compiles with Tectonic (auto-retry on recoverable errors),
and validates the output PDF.

Usage:
  python3 paper/scripts/_compile_paper.py --venue neurips --output-dir paper/output
  python3 paper/scripts/_compile_paper.py --self-test
"""

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# Standard section ordering for NeurIPS papers
# ---------------------------------------------------------------------------
SECTION_ORDER = [
    "introduction",
    "related_work",
    "methods",
    "experiments",
    "results",
    "discussion",
    "conclusion",
]

# Packages required in the NeurIPS preamble
STANDARD_PACKAGES = [
    ("inputenc", "utf8"),
    ("fontenc", "T1"),
    ("amsmath", None),
    ("amssymb", None),
    ("graphicx", None),
    ("booktabs", None),
    ("algorithm", None),
    ("algorithmic", None),
    ("hyperref", None),
    ("url", None),
]


# ---------------------------------------------------------------------------
# 1. check_prerequisites
# ---------------------------------------------------------------------------

def check_prerequisites(output_dir):
    """Verify required input files exist under output_dir.

    Returns dict with keys:
      found:    list of found paths
      missing:  list of missing paths
      warnings: list of warning strings
    """
    found = []
    missing = []
    warnings = []

    sections_dir = os.path.join(output_dir, "sections")
    md_files = sorted(glob.glob(os.path.join(sections_dir, "*.md")))

    if md_files:
        found.extend(md_files)
    else:
        warnings.append(f"No .md files found in {sections_dir}")

    # At minimum, introduction.md should exist
    intro_path = os.path.join(sections_dir, "introduction.md")
    if os.path.isfile(intro_path):
        if intro_path not in found:
            found.append(intro_path)
    else:
        missing.append(intro_path)
        warnings.append("introduction.md is missing -- paper will be incomplete")

    # bibliography.bib
    bib_path = os.path.join(output_dir, "bibliography.bib")
    if os.path.isfile(bib_path):
        found.append(bib_path)
    else:
        missing.append(bib_path)
        warnings.append("bibliography.bib missing -- citations will be unresolved")

    # figures/*.pdf
    figures_dir = os.path.join(output_dir, "figures")
    pdf_files = sorted(glob.glob(os.path.join(figures_dir, "*.pdf")))
    if pdf_files:
        found.extend(pdf_files)
    else:
        warnings.append(f"No .pdf figures found in {figures_dir}")

    return {"found": found, "missing": missing, "warnings": warnings}


# ---------------------------------------------------------------------------
# 2. check_tool_available
# ---------------------------------------------------------------------------

def check_tool_available(tool_name):
    """Check whether a CLI tool is on PATH.

    Returns True if found, False otherwise.  Prints install hints when missing.
    """
    if shutil.which(tool_name):
        return True

    hints = {
        "tectonic": "Install with: brew install tectonic  (macOS) or "
                    "curl --proto '=https' --tlsv1.2 -fsSL "
                    "https://drop-sh.fullyjustified.net | sh",
        "pandoc": "Pandoc 3.9 is expected. Install from https://pandoc.org/installing.html",
    }
    print(f"[WARN] {tool_name} not found on PATH. {hints.get(tool_name, '')}")
    return False


# ---------------------------------------------------------------------------
# 3. convert_section_md_to_tex
# ---------------------------------------------------------------------------

def convert_section_md_to_tex(md_path, tex_path):
    """Convert a single markdown section to LaTeX via Pandoc.

    Post-processing:
      a) Convert [FIGURE: caption | path] placeholders to LaTeX figure envs
      b) Strip top-level \\section{} headers (master doc provides them)
      c) Preserve \\cite{} commands (Pandoc +raw_tex handles this)

    Returns True on success, raises RuntimeError on failure.
    """
    cmd = [
        "pandoc", md_path,
        "-f", "markdown+raw_tex",
        "-t", "latex",
        "--wrap=preserve",
        "--no-highlight",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Pandoc failed on {md_path}: {result.stderr.strip()}"
        )

    tex = result.stdout

    # (a) Convert [FIGURE: caption | path] placeholders
    #     Pandoc escapes brackets and pipe, producing:
    #       {[}FIGURE: caption text \textbar{} figures/path\_name.pdf{]}
    #     We handle both raw (pre-pandoc) and escaped (post-pandoc) forms.
    def _build_figure_env(caption, fig_path):
        """Build a LaTeX figure environment from caption and path."""
        # Undo Pandoc's underscore escaping in path
        fig_path = fig_path.replace("\\_", "_")
        fig_path = fig_path.replace("\\", "/").strip()
        caption = caption.strip()
        stem = Path(fig_path).stem
        return (
            "\\begin{figure}[t]\n"
            "\\centering\n"
            f"\\includegraphics[width=\\linewidth]{{{fig_path}}}\n"
            f"\\caption{{{caption}}}\n"
            f"\\label{{fig:{stem}}}\n"
            "\\end{figure}"
        )

    # Pattern 1: Pandoc-escaped form
    #   {[}FIGURE: caption \textbar{} path{]}
    def _figure_repl_escaped(m):
        return _build_figure_env(m.group(1), m.group(2))

    tex = re.sub(
        r'\{\[\}FIGURE:\s*(.+?)\s*\\textbar\{\}\s*(.+?)\s*\{\]\}',
        _figure_repl_escaped,
        tex,
    )

    # Pattern 2: Raw form (if not processed by Pandoc or in raw_tex blocks)
    #   [FIGURE: caption | path]
    def _figure_repl_raw(m):
        return _build_figure_env(m.group(1), m.group(2))

    tex = re.sub(
        r'\[FIGURE:\s*(.+?)\s*\|\s*(.+?)\s*\]',
        _figure_repl_raw,
        tex,
    )

    # (b) Strip top-level \section{} headers -- master doc uses \input{}
    tex = re.sub(r'^\\section\{[^}]*\}\s*', '', tex, flags=re.MULTILINE)

    # Write result
    os.makedirs(os.path.dirname(os.path.abspath(tex_path)), exist_ok=True)
    with open(tex_path, "w") as f:
        f.write(tex)

    return True


# ---------------------------------------------------------------------------
# 4. assemble_master_document
# ---------------------------------------------------------------------------

def assemble_master_document(output_dir, venue="neurips", title="Untitled",
                             authors="Anonymous", abstract_text="",
                             blind=True):
    """Build paper.tex using NeurIPS template structure.

    Args:
        output_dir:    Root output directory (paper.tex written here)
        venue:         Venue name (currently only 'neurips' supported)
        title:         Paper title
        authors:       Author string (ignored in blind mode)
        abstract_text: Abstract body text
        blind:         If True, use anonymous/blind submission mode

    Returns path to the generated paper.tex.
    """
    lines = []

    # Document class
    lines.append("\\documentclass{article}")
    lines.append("")

    # Venue package
    if venue == "neurips":
        if blind:
            lines.append("\\usepackage{neurips_2025}")
        else:
            lines.append("\\usepackage[preprint]{neurips_2025}")
    lines.append("")

    # Standard packages
    for pkg, opt in STANDARD_PACKAGES:
        if opt:
            lines.append(f"\\usepackage[{opt}]{{{pkg}}}")
        else:
            lines.append(f"\\usepackage{{{pkg}}}")
    lines.append("")

    # Title and author
    lines.append(f"\\title{{{title}}}")
    lines.append("")
    if blind:
        lines.append("\\author{Anonymous}")
    else:
        lines.append(f"\\author{{{authors}}}")
    lines.append("")

    # Begin document
    lines.append("\\begin{document}")
    lines.append("\\maketitle")
    lines.append("")

    # Abstract
    lines.append("\\begin{abstract}")
    lines.append(abstract_text if abstract_text else "TODO: Write abstract.")
    lines.append("\\end{abstract}")
    lines.append("")

    # Section inputs
    for section in SECTION_ORDER:
        tex_file = os.path.join(output_dir, "sections", f"{section}.tex")
        if os.path.isfile(tex_file):
            # \input paths are relative to the main .tex file location
            lines.append(f"\\input{{sections/{section}}}")
    lines.append("")

    # Bibliography
    lines.append("\\bibliographystyle{plainnat}")
    lines.append("\\bibliography{bibliography}")
    lines.append("")

    # End document
    lines.append("\\end{document}")

    tex_content = "\n".join(lines) + "\n"
    tex_path = os.path.join(output_dir, "paper.tex")
    with open(tex_path, "w") as f:
        f.write(tex_content)

    return tex_path


# ---------------------------------------------------------------------------
# 5. parse_tectonic_error
# ---------------------------------------------------------------------------

def parse_tectonic_error(stderr):
    """Parse Tectonic stderr output into categorized issues.

    Returns dict with keys:
      errors:      list of error strings
      warnings:    list of warning strings
      blocking:    list of BLOCKING issues
      cosmetic:    list of COSMETIC issues
      recoverable: bool -- True if errors might resolve with a fix
    """
    errors = []
    warnings = []
    blocking = []
    cosmetic = []

    if not stderr:
        return {
            "errors": errors,
            "warnings": warnings,
            "blocking": blocking,
            "cosmetic": cosmetic,
            "recoverable": False,
        }

    for line in stderr.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Classify: error lines
        if re.search(r'(?i)\berror\b', line_stripped):
            errors.append(line_stripped)

            # Blocking: undefined references after all passes
            if "undefined reference" in line_stripped.lower():
                blocking.append(line_stripped)
            # Blocking: missing files
            elif "file not found" in line_stripped.lower() or \
                 "not found" in line_stripped.lower():
                blocking.append(line_stripped)
            # Blocking: missing packages not auto-resolved
            elif "package" in line_stripped.lower() and \
                 "not found" in line_stripped.lower():
                blocking.append(line_stripped)
            else:
                # Generic errors might be recoverable
                pass

        # Classify: warning lines
        elif re.search(r'(?i)\bwarning\b', line_stripped):
            warnings.append(line_stripped)

            # Cosmetic: overfull/underfull hbox
            hbox_match = re.search(
                r'(?i)(overfull|underfull)\s+\\hbox.*?(\d+\.?\d*)\s*pt',
                line_stripped
            )
            if hbox_match:
                cosmetic.append(line_stripped)
            else:
                cosmetic.append(line_stripped)

        # Overfull/underfull without "warning" keyword
        elif re.search(r'(?i)(overfull|underfull)\s+\\[hv]box', line_stripped):
            warnings.append(line_stripped)
            cosmetic.append(line_stripped)

        # Citation warnings (undefined citation)
        elif "undefined" in line_stripped.lower() and \
             "citation" in line_stripped.lower():
            warnings.append(line_stripped)
            blocking.append(line_stripped)

    # Recoverable: if we have errors but they look like they might resolve
    # with a second pass or minor fix
    recoverable = len(errors) > 0 and len(blocking) == 0

    return {
        "errors": errors,
        "warnings": warnings,
        "blocking": blocking,
        "cosmetic": cosmetic,
        "recoverable": recoverable,
    }


# ---------------------------------------------------------------------------
# 6. run_tectonic
# ---------------------------------------------------------------------------

def run_tectonic(tex_path, output_dir, max_retries=3):
    """Run Tectonic compilation with retry on recoverable errors.

    Args:
        tex_path:     Path to the master .tex file
        output_dir:   Directory for output files
        max_retries:  Maximum number of compilation attempts

    Returns dict with keys:
      success:   bool
      pdf_path:  path to generated PDF (or None)
      errors:    list of error strings
      warnings:  list of warning strings
      attempts:  number of attempts made
    """
    if not check_tool_available("tectonic"):
        return {
            "success": False,
            "pdf_path": None,
            "errors": ["tectonic not found on PATH"],
            "warnings": [],
            "attempts": 0,
        }

    all_errors = []
    all_warnings = []
    last_attempt = 0

    for attempt in range(1, max_retries + 1):
        last_attempt = attempt
        cmd = [
            "tectonic", "-X", "compile",
            tex_path,
            "--outdir", output_dir,
            "--keep-logs",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired:
            all_errors.append(f"Attempt {attempt}: tectonic timed out (120s)")
            continue

        parsed = parse_tectonic_error(result.stderr)
        all_errors.extend(parsed["errors"])
        all_warnings.extend(parsed["warnings"])

        if result.returncode == 0:
            pdf_name = Path(tex_path).stem + ".pdf"
            pdf_path = os.path.join(output_dir, pdf_name)
            return {
                "success": True,
                "pdf_path": pdf_path if os.path.isfile(pdf_path) else None,
                "errors": all_errors,
                "warnings": all_warnings,
                "attempts": attempt,
            }

        # Failed -- check if recoverable
        if parsed["recoverable"] and attempt < max_retries:
            print(f"  [RETRY] Attempt {attempt} failed (recoverable), retrying...")
            continue
        elif parsed["blocking"]:
            print(f"  [BLOCKED] Attempt {attempt} failed with blocking errors:")
            for b in parsed["blocking"]:
                print(f"    - {b}")
            break
        else:
            # Not recoverable and not obviously blocking -- stop
            break

    return {
        "success": False,
        "pdf_path": None,
        "errors": all_errors,
        "warnings": all_warnings,
        "attempts": last_attempt,
    }


# ---------------------------------------------------------------------------
# 7. validate_compilation
# ---------------------------------------------------------------------------

def validate_compilation(output_dir, venue_page_limit=9):
    """Post-compilation validation checks.

    Returns dict with keys:
      valid:                bool
      page_count:           int or None
      page_limit:           int
      unresolved_citations: list of unresolved citation keys
      warnings:             list of warning strings
    """
    warnings = []
    unresolved_citations = []

    pdf_path = os.path.join(output_dir, "paper.pdf")

    # Check PDF exists and is non-empty
    if not os.path.isfile(pdf_path):
        return {
            "valid": False,
            "page_count": None,
            "page_limit": venue_page_limit,
            "unresolved_citations": [],
            "warnings": ["paper.pdf does not exist"],
        }

    pdf_size = os.path.getsize(pdf_path)
    if pdf_size == 0:
        return {
            "valid": False,
            "page_count": None,
            "page_limit": venue_page_limit,
            "unresolved_citations": [],
            "warnings": ["paper.pdf is empty (0 bytes)"],
        }

    # Count pages -- try pdfinfo first, then file size heuristic
    page_count = None
    if shutil.which("pdfinfo"):
        try:
            result = subprocess.run(
                ["pdfinfo", pdf_path],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if line.startswith("Pages:"):
                    page_count = int(line.split(":")[1].strip())
                    break
        except (subprocess.TimeoutExpired, ValueError):
            pass

    # Fallback: rough heuristic from file size (a typical LaTeX page is ~30-60KB)
    if page_count is None:
        page_count = max(1, pdf_size // 40000)
        warnings.append(
            f"Page count estimated from file size ({pdf_size} bytes) -- "
            f"install poppler-utils for accurate count"
        )

    if page_count > venue_page_limit:
        warnings.append(
            f"Page count ({page_count}) exceeds venue limit ({venue_page_limit})"
        )

    # Check for unresolved citations in log
    log_path = os.path.join(output_dir, "paper.log")
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r", errors="replace") as f:
                log_content = f.read()
            # LaTeX marks unresolved citations with [?]
            undef_cites = re.findall(
                r"Citation\s+`([^']+)'\s+on\s+page",
                log_content
            )
            if undef_cites:
                unresolved_citations = list(set(undef_cites))
                warnings.append(
                    f"Unresolved citations: {', '.join(unresolved_citations)}"
                )
        except OSError:
            warnings.append("Could not read compilation log")

    valid = (
        pdf_size > 0
        and len(unresolved_citations) == 0
        and page_count <= venue_page_limit
    )

    return {
        "valid": valid,
        "page_count": page_count,
        "page_limit": venue_page_limit,
        "unresolved_citations": unresolved_citations,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. compile_paper (main orchestrator)
# ---------------------------------------------------------------------------

def compile_paper(venue="neurips", output_dir="paper/output", blind=True):
    """Main compilation orchestrator.

    Steps:
      0. Check tool availability (pandoc, tectonic)
      1. Check prerequisites (sections, bib, figures)
      2. Verify/warn about venue style file
      3. Convert sections/*.md to sections/*.tex
      4. Read paper_outline.json for title/abstract (fallback to placeholders)
      5. Assemble master document
      6. Run Tectonic
      7. Validate output

    Returns comprehensive result dict.
    """
    result = {
        "success": False,
        "steps": {},
        "errors": [],
        "warnings": [],
        "pdf_path": None,
    }

    # Step 0: Tool availability
    pandoc_ok = check_tool_available("pandoc")
    tectonic_ok = check_tool_available("tectonic")
    result["steps"]["tools"] = {
        "pandoc": pandoc_ok,
        "tectonic": tectonic_ok,
    }
    if not pandoc_ok:
        result["errors"].append("pandoc not found -- cannot convert markdown")
        return result

    # Step 1: Prerequisites
    prereqs = check_prerequisites(output_dir)
    result["steps"]["prerequisites"] = prereqs
    result["warnings"].extend(prereqs["warnings"])

    # Step 2: Venue style file
    if venue == "neurips":
        sty_path = os.path.join(output_dir, "neurips_2025.sty")
        if not os.path.isfile(sty_path):
            msg = (
                "neurips_2025.sty not found in output dir. "
                "Tectonic may auto-download it, or fetch manually: "
                "curl -O https://neurips.cc/Conferences/2026/CallForPapers"
            )
            result["warnings"].append(msg)
            print(f"  [WARN] {msg}")
    result["steps"]["venue_style"] = {"checked": True}

    # Step 3: Convert sections
    sections_dir = os.path.join(output_dir, "sections")
    converted = []
    conversion_errors = []
    md_files = sorted(glob.glob(os.path.join(sections_dir, "*.md")))
    for md_path in md_files:
        stem = Path(md_path).stem
        tex_path = os.path.join(sections_dir, f"{stem}.tex")
        try:
            convert_section_md_to_tex(md_path, tex_path)
            converted.append(stem)
            print(f"  [OK] Converted {stem}.md -> {stem}.tex")
        except Exception as e:
            conversion_errors.append(f"{stem}: {e}")
            print(f"  [ERR] Failed to convert {stem}.md: {e}")

    result["steps"]["conversion"] = {
        "converted": converted,
        "errors": conversion_errors,
    }
    result["errors"].extend(conversion_errors)

    # Step 4: Read paper_outline.json for title/abstract
    title = "Untitled Paper"
    abstract_text = ""
    outline_path = os.path.join(output_dir, "paper_outline.json")
    if os.path.isfile(outline_path):
        try:
            with open(outline_path, "r") as f:
                outline = json.load(f)
            title = outline.get("title", title)
            abstract_text = outline.get("abstract", abstract_text)
            print(f"  [OK] Loaded title/abstract from paper_outline.json")
        except (json.JSONDecodeError, OSError) as e:
            result["warnings"].append(f"Could not read paper_outline.json: {e}")
    else:
        result["warnings"].append(
            "paper_outline.json not found -- using placeholder title/abstract"
        )

    # Step 5: Assemble master document
    tex_path = assemble_master_document(
        output_dir, venue=venue, title=title,
        authors="Anonymous", abstract_text=abstract_text, blind=blind
    )
    result["steps"]["assembly"] = {"tex_path": tex_path}
    print(f"  [OK] Assembled master document: {tex_path}")

    # Step 6: Run Tectonic
    if not tectonic_ok:
        result["warnings"].append(
            "Skipping Tectonic compilation (not installed)"
        )
        result["steps"]["tectonic"] = {"skipped": True}
    else:
        tec_result = run_tectonic(tex_path, output_dir)
        result["steps"]["tectonic"] = tec_result
        result["errors"].extend(tec_result["errors"])
        result["warnings"].extend(tec_result["warnings"])
        if tec_result["success"]:
            result["pdf_path"] = tec_result["pdf_path"]
        else:
            result["errors"].append("Tectonic compilation failed")
            return result

    # Step 7: Validate
    if result.get("pdf_path") or os.path.isfile(
        os.path.join(output_dir, "paper.pdf")
    ):
        page_limit = 9 if venue == "neurips" else 10
        validation = validate_compilation(output_dir, venue_page_limit=page_limit)
        result["steps"]["validation"] = validation
        result["warnings"].extend(validation["warnings"])
        if not validation["valid"]:
            result["warnings"].append("Validation flagged issues (see details)")
    else:
        result["steps"]["validation"] = {"skipped": True, "reason": "No PDF"}

    result["success"] = len(
        [e for e in result["errors"] if "cosmetic" not in e.lower()]
    ) == 0 or result.get("pdf_path") is not None

    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    """Run all self-tests. Exit 0 if all pass, 1 if any fail."""
    print("=== _compile_paper self-test ===\n")
    all_passed = True

    # -----------------------------------------------------------------------
    # Test 1: convert_section_md_to_tex with markdown containing \cite{},
    #         math, [FIGURE: ...] placeholder, and lists
    # -----------------------------------------------------------------------
    test_dir = None
    try:
        if not check_tool_available("pandoc"):
            print("[SKIP] convert_section_md_to_tex: pandoc not installed")
        else:
            test_dir = tempfile.mkdtemp(prefix="compile_test_")
            md_content = r"""# Introduction

This paper builds on prior work \cite{vaswani2017attention} and recent
advances in $\alpha$-divergence estimation \cite{smith2024fast}.

We show that $E[X] = \sum_{i=1}^{n} x_i p(x_i)$ is tractable.

Key contributions:

- First contribution with \cite{brown2020language}
- Second contribution
- Third result using $$\mathcal{L} = -\log p(x)$$

[FIGURE: Training loss over epochs | figures/training_loss.pdf]

The results are summarized in Table 1.
"""
            md_path = os.path.join(test_dir, "introduction.md")
            tex_path = os.path.join(test_dir, "introduction.tex")
            with open(md_path, "w") as f:
                f.write(md_content)

            convert_section_md_to_tex(md_path, tex_path)

            with open(tex_path, "r") as f:
                tex = f.read()

            # Check \cite{} preserved
            assert "\\cite{vaswani2017attention}" in tex, \
                f"\\cite{{vaswani2017attention}} not preserved in output"
            assert "\\cite{smith2024fast}" in tex, \
                f"\\cite{{smith2024fast}} not preserved"
            assert "\\cite{brown2020language}" in tex, \
                f"\\cite{{brown2020language}} not preserved"

            # Check math preserved
            assert "\\alpha" in tex, "Math (\\alpha) not preserved"
            assert "\\sum_" in tex or "\\sum " in tex or "\\sum{" in tex, \
                "Math (\\sum) not preserved"

            # Check [FIGURE: ...] converted
            assert "\\begin{figure}" in tex, \
                "FIGURE placeholder not converted to figure environment"
            assert "\\includegraphics" in tex, \
                "\\includegraphics not found in FIGURE conversion"
            assert "training_loss" in tex, \
                "Figure path (training_loss) not in output"

            # Check top-level \section{} stripped
            assert "\\section{Introduction}" not in tex, \
                "Top-level \\section{} not stripped"

            print("[PASS] convert_section_md_to_tex: cite, math, figure, section-strip")

            shutil.rmtree(test_dir)
            test_dir = None

    except Exception as e:
        print(f"[FAIL] convert_section_md_to_tex: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -----------------------------------------------------------------------
    # Test 2: assemble_master_document produces valid LaTeX structure
    # -----------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="compile_test_asm_")
        sections_dir = os.path.join(test_dir, "sections")
        os.makedirs(sections_dir)

        # Create dummy .tex files for sections
        for sec in ["introduction", "methods", "conclusion"]:
            with open(os.path.join(sections_dir, f"{sec}.tex"), "w") as f:
                f.write(f"% {sec} content\n")

        tex_path = assemble_master_document(
            test_dir, venue="neurips",
            title="Test Paper Title",
            authors="Test Author",
            abstract_text="This is a test abstract.",
            blind=True,
        )

        with open(tex_path, "r") as f:
            tex = f.read()

        assert "\\documentclass{article}" in tex, "Missing \\documentclass"
        assert "\\usepackage{neurips_2025}" in tex, "Missing neurips package"
        assert "preprint" not in tex, "Blind mode should not have preprint"
        assert "\\begin{document}" in tex, "Missing \\begin{document}"
        assert "\\end{document}" in tex, "Missing \\end{document}"
        assert "\\maketitle" in tex, "Missing \\maketitle"
        assert "\\title{Test Paper Title}" in tex, "Title not set"
        assert "\\author{Anonymous}" in tex, "Blind mode should show Anonymous"
        assert "\\begin{abstract}" in tex, "Missing abstract env"
        assert "This is a test abstract." in tex, "Abstract text missing"
        assert "\\input{sections/introduction}" in tex, "Missing introduction input"
        assert "\\input{sections/methods}" in tex, "Missing methods input"
        assert "\\input{sections/conclusion}" in tex, "Missing conclusion input"
        # related_work.tex doesn't exist, so it should NOT be included
        assert "\\input{sections/related_work}" not in tex, \
            "related_work should not be included (no .tex file)"
        assert "\\bibliographystyle{plainnat}" in tex, "Missing bibliography style"
        assert "\\bibliography{bibliography}" in tex, "Missing bibliography"

        # Test preprint (non-blind) mode
        tex_path2 = assemble_master_document(
            test_dir, venue="neurips",
            title="Test", authors="Auth", abstract_text="Abs",
            blind=False,
        )
        with open(tex_path2, "r") as f:
            tex2 = f.read()
        assert "[preprint]" in tex2, "Non-blind should have preprint option"

        print("[PASS] assemble_master_document: LaTeX structure, blind/preprint modes")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] assemble_master_document: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -----------------------------------------------------------------------
    # Test 3: parse_tectonic_error -- blocking vs cosmetic classification
    # -----------------------------------------------------------------------
    try:
        # Test with blocking errors
        stderr_blocking = """
error: undefined reference `fig:missing'
error: file not found: missing_package.sty
warning: Overfull \\hbox (2.3pt too wide) in paragraph
"""
        parsed = parse_tectonic_error(stderr_blocking)
        assert len(parsed["errors"]) >= 2, \
            f"Expected >= 2 errors, got {len(parsed['errors'])}"
        assert len(parsed["blocking"]) >= 1, \
            f"Expected >= 1 blocking, got {len(parsed['blocking'])}"
        assert len(parsed["cosmetic"]) >= 1, \
            f"Expected >= 1 cosmetic, got {len(parsed['cosmetic'])}"
        assert parsed["recoverable"] is False, \
            "Should NOT be recoverable with blocking errors"

        # Test with only cosmetic warnings
        stderr_cosmetic = """
warning: Overfull \\hbox (1.2pt too wide) in paragraph at line 42
warning: Underfull \\hbox (badness 1000) at line 88
"""
        parsed2 = parse_tectonic_error(stderr_cosmetic)
        assert len(parsed2["errors"]) == 0, \
            f"Expected 0 errors, got {len(parsed2['errors'])}"
        assert len(parsed2["cosmetic"]) >= 1, \
            f"Expected >= 1 cosmetic, got {len(parsed2['cosmetic'])}"
        assert parsed2["recoverable"] is False, \
            "No errors means not recoverable (nothing to recover from)"

        # Test with empty stderr
        parsed3 = parse_tectonic_error("")
        assert len(parsed3["errors"]) == 0
        assert len(parsed3["warnings"]) == 0
        assert parsed3["recoverable"] is False

        # Test with recoverable errors (no blocking ones)
        stderr_recoverable = """
error: something went wrong in compilation pass
warning: some minor issue
"""
        parsed4 = parse_tectonic_error(stderr_recoverable)
        assert len(parsed4["errors"]) >= 1
        assert parsed4["recoverable"] is True, \
            "Errors without blocking issues should be recoverable"

        print("[PASS] parse_tectonic_error: blocking/cosmetic/recoverable classification")

    except Exception as e:
        print(f"[FAIL] parse_tectonic_error: {e}")
        all_passed = False

    # -----------------------------------------------------------------------
    # Test 4: check_prerequisites -- present and missing cases
    # -----------------------------------------------------------------------
    test_dir = None
    test_dir2 = None
    try:
        # Case A: Everything present
        test_dir = tempfile.mkdtemp(prefix="compile_test_prereq_")
        sections_dir = os.path.join(test_dir, "sections")
        figures_dir = os.path.join(test_dir, "figures")
        os.makedirs(sections_dir)
        os.makedirs(figures_dir)

        with open(os.path.join(sections_dir, "introduction.md"), "w") as f:
            f.write("# Intro\nContent here.\n")
        with open(os.path.join(test_dir, "bibliography.bib"), "w") as f:
            f.write("@article{test,\n  title={Test},\n  author={A},\n  year={2024}\n}\n")
        with open(os.path.join(figures_dir, "fig1.pdf"), "w") as f:
            f.write("%PDF-1.4 mock\n")

        result_a = check_prerequisites(test_dir)
        assert len(result_a["found"]) >= 3, \
            f"Expected >= 3 found, got {len(result_a['found'])}"
        assert len(result_a["missing"]) == 0, \
            f"Expected 0 missing, got {result_a['missing']}"

        # Case B: Empty directory (everything missing)
        test_dir2 = tempfile.mkdtemp(prefix="compile_test_prereq_empty_")
        os.makedirs(os.path.join(test_dir2, "sections"), exist_ok=True)
        result_b = check_prerequisites(test_dir2)
        assert len(result_b["missing"]) >= 1, \
            f"Expected >= 1 missing, got {len(result_b['missing'])}"
        assert len(result_b["warnings"]) >= 1, \
            f"Expected >= 1 warning, got {len(result_b['warnings'])}"

        print("[PASS] check_prerequisites: present and missing cases")

        shutil.rmtree(test_dir)
        shutil.rmtree(test_dir2)
        test_dir = None
        test_dir2 = None

    except Exception as e:
        print(f"[FAIL] check_prerequisites: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        if test_dir2 and os.path.exists(test_dir2):
            shutil.rmtree(test_dir2)

    # -----------------------------------------------------------------------
    # Test 5: validate_compilation logic with mocked results
    # -----------------------------------------------------------------------
    test_dir = None
    try:
        # Case A: No PDF at all
        test_dir = tempfile.mkdtemp(prefix="compile_test_validate_")
        result_a = validate_compilation(test_dir, venue_page_limit=9)
        assert result_a["valid"] is False, "Should be invalid with no PDF"
        assert result_a["page_count"] is None

        # Case B: Empty PDF
        pdf_path = os.path.join(test_dir, "paper.pdf")
        with open(pdf_path, "w") as f:
            pass  # 0 bytes
        result_b = validate_compilation(test_dir, venue_page_limit=9)
        assert result_b["valid"] is False, "Should be invalid with empty PDF"

        # Case C: Non-empty PDF (mock -- small file)
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n" + b"x" * 50000)  # ~50KB = ~1 page heuristic
        result_c = validate_compilation(test_dir, venue_page_limit=9)
        assert result_c["page_count"] is not None, "Page count should be estimated"
        assert result_c["page_count"] >= 1, "Should estimate at least 1 page"
        # With ~50KB and no unresolved citations, should be valid
        assert result_c["valid"] is True, \
            f"Should be valid for small PDF, got warnings: {result_c['warnings']}"

        print("[PASS] validate_compilation: no-pdf, empty-pdf, valid-pdf cases")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] validate_compilation: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -----------------------------------------------------------------------
    # Test 6: check_tool_available
    # -----------------------------------------------------------------------
    try:
        # Python3 should always be available
        assert check_tool_available("python3") is True, "python3 should be found"
        # A clearly non-existent tool
        assert check_tool_available("nonexistent_tool_xyz_123") is False, \
            "nonexistent tool should not be found"
        print("[PASS] check_tool_available: found and not-found cases")
    except Exception as e:
        print(f"[FAIL] check_tool_available: {e}")
        all_passed = False

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    if all_passed:
        print("=== All _compile_paper tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Some _compile_paper tests FAILED ===")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _run_self_test()
    else:
        import argparse
        parser = argparse.ArgumentParser(
            description="LaTeX compilation orchestrator"
        )
        parser.add_argument(
            "--venue", default="neurips",
            help="Target venue (default: neurips)"
        )
        parser.add_argument(
            "--output-dir", default="paper/output",
            help="Output directory (default: paper/output)"
        )
        parser.add_argument(
            "--no-blind", action="store_true",
            help="Disable blind/anonymous mode (use preprint)"
        )
        args = parser.parse_args()

        result = compile_paper(
            venue=args.venue,
            output_dir=args.output_dir,
            blind=not args.no_blind,
        )

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"Compilation {'SUCCEEDED' if result['success'] else 'FAILED'}")
        if result.get("pdf_path"):
            print(f"PDF: {result['pdf_path']}")
        if result["errors"]:
            print(f"\nErrors ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"  - {e}")
        if result["warnings"]:
            print(f"\nWarnings ({len(result['warnings'])}):")
            for w in result["warnings"]:
                print(f"  - {w}")
        print(f"{'=' * 60}")

        sys.exit(0 if result["success"] else 1)
