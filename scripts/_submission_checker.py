#!/usr/bin/env python3
"""Submission readiness checker with venue-specific validation, anonymization
detection, citation cross-validation, and checklist generation.

Validates a compiled paper against venue requirements (NeurIPS by default),
checking page count, anonymization, citations, figures, abstract length,
required sections, and reproducibility package completeness.

Usage:
  python3 paper/scripts/_submission_checker.py --venue neurips --output-dir paper/output
  python3 paper/scripts/_submission_checker.py --self-test
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup for sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# 1. load_venue_config
# ---------------------------------------------------------------------------

def load_venue_config(venue="neurips"):
    """Read paper/venues/{venue}.md and parse key configuration values.

    Extracts from markdown table format:
      - page_limit (int)
      - abstract_word_limit (int)
      - anonymization_required (bool)
      - required_sections (list of strings)

    Returns dict with parsed values and defaults for missing fields.
    """
    project_root = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
    venue_path = os.path.join(project_root, "paper", "venues", f"{venue}.md")

    config = {
        "venue": venue,
        "page_limit": 9,
        "abstract_word_limit": 250,
        "anonymization_required": True,
        "required_sections": [
            "introduction", "related_work", "methods",
            "experiments", "results", "discussion", "conclusion",
        ],
    }

    if not os.path.isfile(venue_path):
        return config

    try:
        with open(venue_path, "r") as f:
            content = f.read()
    except OSError:
        return config

    # Parse page limit from table: "| Page limit | 9 pages ..."
    page_match = re.search(
        r'\|\s*Page limit\s*\|\s*(\d+)\s*pages?',
        content, re.IGNORECASE
    )
    if page_match:
        config["page_limit"] = int(page_match.group(1))

    # Parse abstract word limit from checklist or text: "250-word limit" or "250 words"
    abstract_match = re.search(
        r'(?:abstract|Abstract)\s+(?:is\s+)?within\s+(\d+)[- ]word',
        content, re.IGNORECASE
    )
    if abstract_match:
        config["abstract_word_limit"] = int(abstract_match.group(1))

    # Parse anonymization from text
    if "double-blind" in content.lower() or "double blind" in content.lower():
        config["anonymization_required"] = True
    elif "single-blind" in content.lower():
        config["anonymization_required"] = False

    return config


# ---------------------------------------------------------------------------
# 2. check_compilation
# ---------------------------------------------------------------------------

def check_compilation(output_dir):
    """Verify compilation artifacts exist and are valid.

    Checks:
      - paper.pdf exists and is non-empty
      - paper.tex exists
      - No .log files with 'error' lines (if tectonic logs exist)

    Returns dict with status and details.
    """
    result = {"status": "pass", "details": ""}
    issues = []

    pdf_path = os.path.join(output_dir, "paper.pdf")
    tex_path = os.path.join(output_dir, "paper.tex")

    if not os.path.isfile(pdf_path):
        issues.append("paper.pdf not found")
    elif os.path.getsize(pdf_path) == 0:
        issues.append("paper.pdf is empty (0 bytes)")

    if not os.path.isfile(tex_path):
        issues.append("paper.tex not found")

    # Check log files for errors
    log_files = glob.glob(os.path.join(output_dir, "*.log"))
    for log_file in log_files:
        try:
            with open(log_file, "r", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(r'^\s*!\s+', line) or \
                       re.search(r'(?i)^.*error(?!.*warning).*$', line):
                        issues.append(
                            f"Error in {os.path.basename(log_file)} "
                            f"line {line_num}: {line.strip()[:100]}"
                        )
        except OSError:
            pass

    if issues:
        result["status"] = "fail"
        result["details"] = "; ".join(issues)
    else:
        result["details"] = "PDF and LaTeX source present"

    return result


# ---------------------------------------------------------------------------
# 3. check_page_count
# ---------------------------------------------------------------------------

def check_page_count(pdf_path, limit=9):
    """Check PDF page count against venue limit.

    Tries pdfinfo (from poppler) first, then falls back to counting
    /Type /Page occurrences in the PDF binary (rough heuristic).

    Returns dict with status, page_count, limit, and details.
    """
    result = {
        "status": "pass",
        "page_count": None,
        "limit": limit,
        "details": "",
    }

    if not os.path.isfile(pdf_path):
        result["status"] = "fail"
        result["details"] = f"PDF not found: {pdf_path}"
        return result

    page_count = None

    # Method 1: pdfinfo
    if shutil.which("pdfinfo"):
        try:
            proc = subprocess.run(
                ["pdfinfo", pdf_path],
                capture_output=True, text=True, timeout=10
            )
            for line in proc.stdout.splitlines():
                if line.startswith("Pages:"):
                    page_count = int(line.split(":")[1].strip())
                    break
        except (subprocess.TimeoutExpired, ValueError):
            pass

    # Method 2: binary heuristic -- count /Type /Page (not /Pages)
    if page_count is None:
        try:
            with open(pdf_path, "rb") as f:
                data = f.read()
            # Match /Type /Page but not /Type /Pages
            count = len(re.findall(rb'/Type\s*/Page(?!s)', data))
            page_count = max(1, count) if count > 0 else 1
            result["details"] = "Page count estimated via binary heuristic"
        except OSError:
            result["status"] = "fail"
            result["details"] = "Could not read PDF file"
            return result

    result["page_count"] = page_count

    if page_count > limit:
        result["status"] = "fail"
        result["details"] = (
            f"Page count ({page_count}) exceeds venue limit ({limit})"
        )
    else:
        if not result["details"]:
            result["details"] = f"{page_count} pages (limit: {limit})"

    return result


# ---------------------------------------------------------------------------
# 4. check_anonymization
# ---------------------------------------------------------------------------

def check_anonymization(tex_dir):
    """Scan .tex files for anonymization violations.

    Detects:
      - Author names (non-"Anonymous" in \\author{})
      - Institution names (University, Institute, Lab, Inc., Corp.)
      - URLs (http/https/www, except arxiv.org)
      - Acknowledgments section
      - Self-citation patterns ("our previous work", "we previously", etc.)

    Returns dict with status and list of violation dicts.
    """
    violations = []

    # Gather all .tex files recursively
    tex_files = []
    if os.path.isfile(tex_dir):
        tex_files = [tex_dir]
    elif os.path.isdir(tex_dir):
        for root, _dirs, files in os.walk(tex_dir):
            for fname in files:
                if fname.endswith(".tex"):
                    tex_files.append(os.path.join(root, fname))

    for tex_path in tex_files:
        try:
            with open(tex_path, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue

        rel_path = os.path.basename(tex_path)

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip comments
            if stripped.startswith("%"):
                continue

            # Check \\author{} for non-Anonymous content
            author_match = re.search(r'\\author\{([^}]+)\}', stripped)
            if author_match:
                author_text = author_match.group(1).strip()
                if author_text.lower() != "anonymous" and author_text:
                    violations.append({
                        "type": "author_name",
                        "file": rel_path,
                        "line": line_num,
                        "text": stripped[:120],
                    })

            # Check for institution names (but not inside comments or
            # as part of generic academic citations)
            institution_pattern = re.compile(
                r'\b(University|Institute|Laboratory|Lab|Inc\.|Corp\.|'
                r'Corporation|Department\s+of)\b',
                re.IGNORECASE
            )
            # Only flag if it looks like self-identification, not a citation
            if institution_pattern.search(stripped):
                # Exclude lines that are clearly citing other work
                if not re.search(r'\\cite[tp]?\{', stripped) and \
                   not re.search(r'et\s+al\.', stripped) and \
                   not stripped.startswith("\\bibitem"):
                    violations.append({
                        "type": "institution_name",
                        "file": rel_path,
                        "line": line_num,
                        "text": stripped[:120],
                    })

            # Check for URLs (except arxiv.org which is acceptable)
            url_pattern = re.compile(
                r'(?:https?://|www\.)[^\s\}]+',
                re.IGNORECASE
            )
            urls = url_pattern.findall(stripped)
            for url in urls:
                if "arxiv.org" not in url.lower():
                    violations.append({
                        "type": "url",
                        "file": rel_path,
                        "line": line_num,
                        "text": url[:120],
                    })

            # Check for acknowledgments section
            if re.search(r'\\begin\{ack\}', stripped) or \
               re.search(r'\\section\*?\{Acknowledgm', stripped, re.IGNORECASE):
                violations.append({
                    "type": "acknowledgments",
                    "file": rel_path,
                    "line": line_num,
                    "text": stripped[:120],
                })

            # Check for self-citation patterns
            self_cite_patterns = [
                r'\bour\s+previous\s+work\b',
                r'\bour\s+(?:earlier|prior)\s+(?:work|method|approach|paper)\b',
                r'\bwe\s+previously\b',
                r'\bour\s+method\b',
                r'\bin\s+our\s+(?:earlier|prior|previous)\b',
                r'\bwe\s+(?:have\s+)?(?:shown|demonstrated|proposed|introduced)\s+in\b',
            ]
            for pattern in self_cite_patterns:
                if re.search(pattern, stripped, re.IGNORECASE):
                    violations.append({
                        "type": "self_citation",
                        "file": rel_path,
                        "line": line_num,
                        "text": stripped[:120],
                    })
                    break  # One violation per line for self-citation

    status = "fail" if violations else "pass"
    return {"status": status, "violations": violations}


# ---------------------------------------------------------------------------
# 5. check_citations_complete
# ---------------------------------------------------------------------------

def check_citations_complete(output_dir):
    """Cross-validate citations between .tex files and bibliography.bib.

    Extracts \\cite{}, \\citep{}, \\citet{} keys from .tex files and
    @entry{key, from .bib files. Reports missing bib entries (BLOCKING)
    and uncited bib entries (WARNING).

    Returns dict with status and key lists.
    """
    cited_keys = set()
    bib_keys = set()

    # Extract cited keys from all .tex files
    tex_files = glob.glob(os.path.join(output_dir, "**", "*.tex"), recursive=True)
    for tex_path in tex_files:
        try:
            with open(tex_path, "r", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        # Match \cite{key1,key2}, \citep{key}, \citet{key}, \citeauthor{key}
        cite_matches = re.findall(
            r'\\cite[tp]?\*?\{([^}]+)\}', content
        )
        for match in cite_matches:
            for key in match.split(","):
                key = key.strip()
                if key:
                    cited_keys.add(key)

    # Extract bib keys from .bib files
    bib_files = glob.glob(os.path.join(output_dir, "**", "*.bib"), recursive=True)
    for bib_path in bib_files:
        try:
            with open(bib_path, "r", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        # Match @article{key, @inproceedings{key, etc.
        bib_matches = re.findall(r'@\w+\{(\w[^,\s]*)', content)
        for key in bib_matches:
            bib_keys.add(key.strip())

    missing_from_bib = sorted(cited_keys - bib_keys)
    uncited_in_bib = sorted(bib_keys - cited_keys)

    status = "fail" if missing_from_bib else "pass"

    return {
        "status": status,
        "cited_keys": sorted(cited_keys),
        "bib_keys": sorted(bib_keys),
        "missing_from_bib": missing_from_bib,
        "uncited_in_bib": uncited_in_bib,
    }


# ---------------------------------------------------------------------------
# 6. check_figures_present
# ---------------------------------------------------------------------------

def check_figures_present(output_dir):
    """Verify all \\includegraphics references have corresponding files.

    Scans .tex files for \\includegraphics{path} and checks each
    referenced figure file exists relative to output_dir.

    Returns dict with status and figure lists.
    """
    referenced = []
    missing = []

    tex_files = glob.glob(os.path.join(output_dir, "**", "*.tex"), recursive=True)
    for tex_path in tex_files:
        try:
            with open(tex_path, "r", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        # Match \includegraphics[options]{path} or \includegraphics{path}
        fig_matches = re.findall(
            r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', content
        )
        for fig_path in fig_matches:
            fig_path = fig_path.strip()
            referenced.append(fig_path)

            # Check if file exists (relative to output_dir or absolute)
            abs_path = os.path.join(output_dir, fig_path)
            if not os.path.isfile(abs_path):
                # Also check with common extensions
                found = False
                for ext in [".pdf", ".png", ".jpg", ".eps"]:
                    if os.path.isfile(abs_path + ext):
                        found = True
                        break
                if not found:
                    missing.append(fig_path)

    status = "fail" if missing else "pass"
    return {
        "status": status,
        "referenced_figures": referenced,
        "missing_figures": missing,
    }


# ---------------------------------------------------------------------------
# 7. check_abstract
# ---------------------------------------------------------------------------

def check_abstract(output_dir, word_limit=250):
    """Check abstract word count against venue limit.

    Extracts text between \\begin{abstract} and \\end{abstract}
    from paper.tex. Strips LaTeX commands for word counting.

    Returns dict with status, word_count, and limit.
    """
    tex_path = os.path.join(output_dir, "paper.tex")
    result = {
        "status": "pass",
        "word_count": 0,
        "limit": word_limit,
    }

    if not os.path.isfile(tex_path):
        result["status"] = "fail"
        result["details"] = "paper.tex not found"
        return result

    try:
        with open(tex_path, "r", errors="replace") as f:
            content = f.read()
    except OSError:
        result["status"] = "fail"
        result["details"] = "Could not read paper.tex"
        return result

    # Extract abstract text
    abstract_match = re.search(
        r'\\begin\{abstract\}(.*?)\\end\{abstract\}',
        content, re.DOTALL
    )
    if not abstract_match:
        result["status"] = "fail"
        result["details"] = "No abstract found in paper.tex"
        return result

    abstract_text = abstract_match.group(1)

    # Strip LaTeX commands for word counting
    clean = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', abstract_text)
    clean = re.sub(r'\\[a-zA-Z]+', '', clean)
    clean = re.sub(r'[{}$~^_]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    word_count = len(clean.split()) if clean else 0
    result["word_count"] = word_count

    if word_count > word_limit:
        result["status"] = "fail"
        result["details"] = (
            f"Abstract has {word_count} words (limit: {word_limit})"
        )
    else:
        result["details"] = f"{word_count} words (limit: {word_limit})"

    return result


# ---------------------------------------------------------------------------
# 8. check_required_sections
# ---------------------------------------------------------------------------

def check_required_sections(output_dir, required=None):
    """Verify all required sections are present.

    Checks for \\input{sections/X} in paper.tex for each required section,
    and verifies the corresponding .tex file exists.

    Returns dict with status, found sections, and missing sections.
    """
    if required is None:
        required = [
            "introduction", "related_work", "methods",
            "experiments", "results", "discussion", "conclusion",
        ]

    tex_path = os.path.join(output_dir, "paper.tex")
    found = []
    missing = []

    if not os.path.isfile(tex_path):
        return {
            "status": "fail",
            "found": [],
            "missing": required[:],
        }

    try:
        with open(tex_path, "r", errors="replace") as f:
            content = f.read()
    except OSError:
        return {
            "status": "fail",
            "found": [],
            "missing": required[:],
        }

    for section in required:
        # Check if \input{sections/section_name} is in paper.tex
        pattern = rf'\\input\{{sections/{re.escape(section)}\}}'
        if re.search(pattern, content):
            # Also check the .tex file exists
            sec_path = os.path.join(output_dir, "sections", f"{section}.tex")
            if os.path.isfile(sec_path):
                found.append(section)
            else:
                missing.append(section)
        else:
            missing.append(section)

    status = "fail" if missing else "pass"
    return {"status": status, "found": found, "missing": missing}


# ---------------------------------------------------------------------------
# 9. check_reproducibility_package
# ---------------------------------------------------------------------------

def check_reproducibility_package(repro_dir="reproducibility"):
    """Verify reproducibility package completeness.

    Checks for required files: pyproject.toml, Makefile, checksums.sha256,
    README.md.

    Returns dict with status, found files, and missing files.
    """
    required_files = [
        "pyproject.toml",
        "Makefile",
        "checksums.sha256",
        "README.md",
    ]

    found = []
    missing = []

    for fname in required_files:
        fpath = os.path.join(repro_dir, fname)
        if os.path.isfile(fpath):
            found.append(fname)
        else:
            missing.append(fname)

    status = "fail" if missing else "pass"
    return {"status": status, "found": found, "missing": missing}


# ---------------------------------------------------------------------------
# 10. run_submission_check (main orchestrator)
# ---------------------------------------------------------------------------

def run_submission_check(venue="neurips", output_dir="paper/output",
                         repro_dir="reproducibility"):
    """Run all submission checks and generate reports.

    Orchestrates all individual checks, aggregates results into
    submission_readiness.json and submission_checklist.md.

    Returns dict with overall_ready, checks, summary, blocking_issues,
    and recommendations.
    """
    # Load venue config
    config = load_venue_config(venue)

    checks = []
    blocking_issues = []
    recommendations = []

    # 1. Compilation check
    comp = check_compilation(output_dir)
    checks.append({
        "category": "compilation",
        "item": "PDF compiles without errors",
        "status": comp["status"],
        "details": comp["details"],
    })
    if comp["status"] == "fail":
        blocking_issues.append(f"Compilation: {comp['details']}")

    # 2. Page count check
    pdf_path = os.path.join(output_dir, "paper.pdf")
    pages = check_page_count(pdf_path, limit=config["page_limit"])
    checks.append({
        "category": "format",
        "item": "Page count within venue limit",
        "status": pages["status"],
        "details": pages.get("details", ""),
    })
    if pages["status"] == "fail":
        blocking_issues.append(f"Format: {pages['details']}")

    # 3. Anonymization check
    if config["anonymization_required"]:
        anon = check_anonymization(output_dir)
        status = anon["status"]
        violation_count = len(anon["violations"])
        details = (
            f"{violation_count} violation(s) found"
            if violation_count > 0
            else "No anonymization violations"
        )
        checks.append({
            "category": "anonymization",
            "item": "No identifying information in paper",
            "status": status,
            "details": details,
        })
        if status == "fail":
            blocking_issues.append(
                f"Anonymization: {violation_count} violation(s)"
            )
            for v in anon["violations"][:5]:
                blocking_issues.append(
                    f"  - [{v['type']}] {v['file']}:{v['line']}: {v['text'][:80]}"
                )

    # 4. Citation completeness
    cites = check_citations_complete(output_dir)
    cite_details = []
    if cites["missing_from_bib"]:
        cite_details.append(
            f"{len(cites['missing_from_bib'])} cited but not in bib"
        )
    if cites["uncited_in_bib"]:
        cite_details.append(
            f"{len(cites['uncited_in_bib'])} in bib but not cited"
        )
    if not cite_details:
        cite_details.append("All citations match bibliography")
    checks.append({
        "category": "citations",
        "item": "All citations have bibliography entries",
        "status": cites["status"],
        "details": "; ".join(cite_details),
    })
    if cites["missing_from_bib"]:
        blocking_issues.append(
            f"Citations: Missing bib entries for: "
            f"{', '.join(cites['missing_from_bib'][:5])}"
        )
    if cites["uncited_in_bib"]:
        recommendations.append(
            f"Remove or cite unused bib entries: "
            f"{', '.join(cites['uncited_in_bib'][:5])}"
        )

    # 5. Figures check
    figs = check_figures_present(output_dir)
    fig_details = (
        f"{len(figs['missing_figures'])} missing figure(s)"
        if figs["missing_figures"]
        else f"{len(figs['referenced_figures'])} figure(s), all present"
    )
    checks.append({
        "category": "content",
        "item": "All figures present and referenced",
        "status": figs["status"],
        "details": fig_details,
    })
    if figs["status"] == "fail":
        blocking_issues.append(
            f"Figures: Missing: {', '.join(figs['missing_figures'][:5])}"
        )

    # 6. Abstract check
    abstract = check_abstract(output_dir, config["abstract_word_limit"])
    checks.append({
        "category": "content",
        "item": f"Abstract within {config['abstract_word_limit']}-word limit",
        "status": abstract["status"],
        "details": abstract.get("details", ""),
    })
    if abstract["status"] == "fail":
        blocking_issues.append(
            f"Abstract: {abstract.get('details', 'check failed')}"
        )

    # 7. Required sections check
    sections = check_required_sections(output_dir, config["required_sections"])
    sec_details = (
        f"{len(sections['missing'])} section(s) missing: "
        f"{', '.join(sections['missing'])}"
        if sections["missing"]
        else f"All {len(sections['found'])} required sections present"
    )
    checks.append({
        "category": "content",
        "item": "All required sections present",
        "status": sections["status"],
        "details": sec_details,
    })
    if sections["status"] == "fail":
        blocking_issues.append(
            f"Sections: Missing: {', '.join(sections['missing'])}"
        )

    # 8. Reproducibility package check
    repro = check_reproducibility_package(repro_dir)
    repro_details = (
        f"Missing: {', '.join(repro['missing'])}"
        if repro["missing"]
        else f"All {len(repro['found'])} required files present"
    )
    checks.append({
        "category": "supplementary",
        "item": "Reproducibility package complete",
        "status": repro["status"],
        "details": repro_details,
    })
    if repro["status"] == "fail":
        recommendations.append(
            f"Generate reproducibility package: "
            f"python3 paper/scripts/_repro_package.py"
        )

    # Aggregate
    total = len(checks)
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    skipped = sum(1 for c in checks if c["status"] == "skip")

    overall_ready = failed == 0

    result = {
        "venue": venue,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall_ready": overall_ready,
        "checks": checks,
        "summary": {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "blocking_issues": blocking_issues,
        "recommendations": recommendations,
    }

    # Write submission_readiness.json
    readiness_path = os.path.join(output_dir, "submission_readiness.json")
    os.makedirs(output_dir, exist_ok=True)
    atomic_write(readiness_path, json.dumps(result, indent=2))

    # Write submission_checklist.md
    checklist_md = generate_checklist_report(result, venue)
    checklist_path = os.path.join(output_dir, "submission_checklist.md")
    atomic_write(checklist_path, checklist_md)

    return result


# ---------------------------------------------------------------------------
# 11. generate_checklist_report
# ---------------------------------------------------------------------------

def generate_checklist_report(results, venue="neurips"):
    """Generate human-readable markdown checklist from check results.

    Groups checks by category with pass/fail checkboxes.
    Lists blocking issues at top and recommendations at bottom.

    Args:
        results: dict from run_submission_check
        venue: venue name for header

    Returns:
        str: formatted markdown report
    """
    lines = []
    lines.append(f"# Submission Readiness Checklist -- {venue.upper()}")
    lines.append("")
    lines.append(
        f"**Generated:** {results.get('checked_at', 'N/A')}"
    )
    overall = "READY" if results.get("overall_ready") else "NOT READY"
    lines.append(f"**Overall:** {overall}")
    lines.append("")

    summary = results.get("summary", {})
    lines.append(
        f"**Checks:** {summary.get('passed', 0)}/{summary.get('total_checks', 0)} "
        f"passed, {summary.get('failed', 0)} failed, "
        f"{summary.get('skipped', 0)} skipped"
    )
    lines.append("")

    # Blocking issues at top
    blocking = results.get("blocking_issues", [])
    if blocking:
        lines.append("## Blocking Issues")
        lines.append("")
        for issue in blocking:
            lines.append(f"- {issue}")
        lines.append("")

    # Group checks by category
    categories = {}
    for check in results.get("checks", []):
        cat = check.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(check)

    lines.append("## Checklist")
    lines.append("")

    for cat, cat_checks in categories.items():
        lines.append(f"### {cat.title()}")
        lines.append("")
        for check in cat_checks:
            status = check.get("status", "skip")
            checkbox = "[x]" if status == "pass" else "[ ]"
            item = check.get("item", "Unknown check")
            details = check.get("details", "")
            status_label = status.upper()
            lines.append(f"- {checkbox} **{status_label}** -- {item}")
            if details:
                lines.append(f"  - {details}")
        lines.append("")

    # Recommendations
    recs = results.get("recommendations", [])
    if recs:
        lines.append("## Recommendations")
        lines.append("")
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by _submission_checker.py*")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    """Run all self-tests. Exit 0 if all pass, 1 if any fail."""
    print("=== _submission_checker self-test ===\n")
    all_passed = True

    # -------------------------------------------------------------------
    # Test 1: check_anonymization with clean and violating .tex content
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_anon_")

        # Clean file (should pass)
        clean_tex = (
            "\\documentclass{article}\n"
            "\\author{Anonymous}\n"
            "\\begin{document}\n"
            "Prior work \\cite{smith2024} showed strong results.\n"
            "We build on attention mechanisms \\cite{vaswani2017attention}.\n"
            "See https://arxiv.org/abs/2301.00001 for details.\n"
            "\\end{document}\n"
        )
        clean_path = os.path.join(test_dir, "clean.tex")
        with open(clean_path, "w") as f:
            f.write(clean_tex)

        result_clean = check_anonymization(test_dir)
        # Clean file should have no author_name, url, self_citation violations
        # (it may flag the arxiv URL but we allow arxiv.org)
        author_violations = [
            v for v in result_clean["violations"]
            if v["type"] == "author_name"
        ]
        url_violations = [
            v for v in result_clean["violations"]
            if v["type"] == "url"
        ]
        self_cite_violations = [
            v for v in result_clean["violations"]
            if v["type"] == "self_citation"
        ]
        assert len(author_violations) == 0, \
            f"Clean file should have no author violations, got {author_violations}"
        assert len(url_violations) == 0, \
            f"Clean file should have no URL violations (arxiv allowed), got {url_violations}"
        assert len(self_cite_violations) == 0, \
            f"Clean file should have no self-citation violations, got {self_cite_violations}"

        # Violating file
        dirty_tex = (
            "\\documentclass{article}\n"
            "\\author{John Smith and Jane Doe}\n"
            "\\begin{document}\n"
            "Our previous work showed promising results.\n"
            "Code at https://github.com/johndoe/myrepo.\n"
            "\\begin{ack}\n"
            "We thank the reviewers.\n"
            "\\end{ack}\n"
            "\\end{document}\n"
        )
        dirty_dir = os.path.join(test_dir, "dirty")
        os.makedirs(dirty_dir)
        dirty_path = os.path.join(dirty_dir, "paper.tex")
        with open(dirty_path, "w") as f:
            f.write(dirty_tex)

        result_dirty = check_anonymization(dirty_dir)
        assert result_dirty["status"] == "fail", \
            "Dirty file should fail anonymization"

        violation_types = {v["type"] for v in result_dirty["violations"]}
        assert "author_name" in violation_types, \
            f"Should detect author name, got types: {violation_types}"
        assert "url" in violation_types, \
            f"Should detect GitHub URL, got types: {violation_types}"
        assert "self_citation" in violation_types, \
            f"Should detect self-citation pattern, got types: {violation_types}"
        assert "acknowledgments" in violation_types, \
            f"Should detect acknowledgments, got types: {violation_types}"

        print("[PASS] check_anonymization: clean file passes, dirty file catches "
              "author/url/self-cite/ack violations")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_anonymization: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 2: check_citations_complete with matching and mismatched keys
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_cite_")

        # Create .tex file with citations
        tex_content = (
            "As shown by \\cite{vaswani2017attention} and \\citep{brown2020language},\n"
            "the results of \\citet{smith2024fast} confirm our hypothesis.\n"
            "Multi-cite: \\cite{jones2023, lee2024}.\n"
        )
        with open(os.path.join(test_dir, "paper.tex"), "w") as f:
            f.write(tex_content)

        # Create .bib file (missing one, has extra one)
        bib_content = (
            "@article{vaswani2017attention,\n"
            "  title={Attention Is All You Need},\n"
            "  author={Vaswani, Ashish},\n"
            "  year={2017}\n"
            "}\n"
            "@inproceedings{brown2020language,\n"
            "  title={Language Models are Few-Shot Learners},\n"
            "  author={Brown, Tom},\n"
            "  year={2020}\n"
            "}\n"
            "@article{smith2024fast,\n"
            "  title={Fast Methods},\n"
            "  author={Smith, Alice},\n"
            "  year={2024}\n"
            "}\n"
            "@article{unused2023paper,\n"
            "  title={Unused Paper},\n"
            "  author={Nobody},\n"
            "  year={2023}\n"
            "}\n"
        )
        with open(os.path.join(test_dir, "bibliography.bib"), "w") as f:
            f.write(bib_content)

        result = check_citations_complete(test_dir)

        # jones2023 and lee2024 should be missing from bib
        assert "jones2023" in result["missing_from_bib"], \
            f"jones2023 should be missing from bib, got: {result['missing_from_bib']}"
        assert "lee2024" in result["missing_from_bib"], \
            f"lee2024 should be missing from bib, got: {result['missing_from_bib']}"
        assert result["status"] == "fail", \
            "Should fail with missing bib entries"

        # unused2023paper should be uncited
        assert "unused2023paper" in result["uncited_in_bib"], \
            f"unused2023paper should be uncited, got: {result['uncited_in_bib']}"

        # vaswani2017attention should be in both
        assert "vaswani2017attention" in result["cited_keys"]
        assert "vaswani2017attention" in result["bib_keys"]

        print("[PASS] check_citations_complete: detects missing bib entries "
              "and uncited references across cite/citep/citet")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_citations_complete: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 3: check_figures_present with present and missing figures
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_fig_")
        fig_dir = os.path.join(test_dir, "figures")
        os.makedirs(fig_dir)

        # Create a .tex with figure references
        tex_content = (
            "\\includegraphics[width=\\linewidth]{figures/training_loss.pdf}\n"
            "\\includegraphics{figures/architecture.png}\n"
            "\\includegraphics[scale=0.5]{figures/missing_figure.pdf}\n"
        )
        with open(os.path.join(test_dir, "paper.tex"), "w") as f:
            f.write(tex_content)

        # Create some figure files (not all)
        with open(os.path.join(fig_dir, "training_loss.pdf"), "w") as f:
            f.write("%PDF mock")
        with open(os.path.join(fig_dir, "architecture.png"), "w") as f:
            f.write("PNG mock")

        result = check_figures_present(test_dir)
        assert result["status"] == "fail", "Should fail with missing figure"
        assert len(result["referenced_figures"]) == 3, \
            f"Expected 3 references, got {len(result['referenced_figures'])}"
        assert "figures/missing_figure.pdf" in result["missing_figures"], \
            f"missing_figure.pdf should be in missing, got: {result['missing_figures']}"
        assert len(result["missing_figures"]) == 1, \
            f"Expected 1 missing, got {len(result['missing_figures'])}"

        print("[PASS] check_figures_present: detects present and missing figures")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_figures_present: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 4: check_abstract with over-limit and under-limit abstracts
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_abs_")

        # Under limit (10 words)
        tex_under = (
            "\\begin{abstract}\n"
            "This paper presents a novel approach to machine learning.\n"
            "\\end{abstract}\n"
        )
        with open(os.path.join(test_dir, "paper.tex"), "w") as f:
            f.write(tex_under)

        result_under = check_abstract(test_dir, word_limit=250)
        assert result_under["status"] == "pass", \
            f"Short abstract should pass, got status={result_under['status']}"
        assert result_under["word_count"] > 0, \
            "Word count should be > 0"
        assert result_under["word_count"] <= 250, \
            f"Word count {result_under['word_count']} should be <= 250"

        # Over limit
        words_300 = " ".join(["word"] * 300)
        tex_over = (
            "\\begin{abstract}\n"
            f"{words_300}\n"
            "\\end{abstract}\n"
        )
        with open(os.path.join(test_dir, "paper.tex"), "w") as f:
            f.write(tex_over)

        result_over = check_abstract(test_dir, word_limit=250)
        assert result_over["status"] == "fail", \
            f"Long abstract should fail, got status={result_over['status']}"
        assert result_over["word_count"] >= 300, \
            f"Expected >= 300 words, got {result_over['word_count']}"

        print("[PASS] check_abstract: under-limit passes, over-limit fails")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_abstract: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 5: check_required_sections with complete and incomplete lists
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_sec_")
        sections_dir = os.path.join(test_dir, "sections")
        os.makedirs(sections_dir)

        # Create paper.tex with some section inputs
        tex_content = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\input{sections/introduction}\n"
            "\\input{sections/methods}\n"
            "\\input{sections/conclusion}\n"
            "\\end{document}\n"
        )
        with open(os.path.join(test_dir, "paper.tex"), "w") as f:
            f.write(tex_content)

        # Create corresponding .tex files
        for sec in ["introduction", "methods", "conclusion"]:
            with open(os.path.join(sections_dir, f"{sec}.tex"), "w") as f:
                f.write(f"% {sec} content\n")

        # Test with full requirement list -- should have missing sections
        required = ["introduction", "methods", "results", "conclusion"]
        result = check_required_sections(test_dir, required)
        assert result["status"] == "fail", "Should fail with missing sections"
        assert "results" in result["missing"], \
            f"results should be missing, got: {result['missing']}"
        assert "introduction" in result["found"], \
            f"introduction should be found, got: {result['found']}"

        # Test with subset that all exist
        result_pass = check_required_sections(
            test_dir, ["introduction", "methods", "conclusion"]
        )
        assert result_pass["status"] == "pass", \
            f"All-present check should pass, got: {result_pass}"

        print("[PASS] check_required_sections: detects complete and missing sections")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_required_sections: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 6: check_page_count with PDF binary heuristic
    # -------------------------------------------------------------------
    test_dir = None
    try:
        test_dir = tempfile.mkdtemp(prefix="subcheck_pages_")

        # Create a minimal PDF-like file with /Type /Page markers
        pdf_content = b"%PDF-1.4\n"
        # Add 3 page objects
        for i in range(3):
            pdf_content += f"obj {i}\n/Type /Page\nendobj\n".encode()
        # Add a /Type /Pages (catalog) -- should NOT be counted
        pdf_content += b"obj 99\n/Type /Pages\nendobj\n"
        pdf_content += b"%%EOF\n"

        pdf_path = os.path.join(test_dir, "paper.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)

        result = check_page_count(pdf_path, limit=9)
        assert result["page_count"] is not None, "Page count should be estimated"
        assert result["page_count"] == 3, \
            f"Expected 3 pages from heuristic, got {result['page_count']}"
        assert result["status"] == "pass", \
            f"3 pages should be under limit 9, got status={result['status']}"

        # Test over limit
        result_over = check_page_count(pdf_path, limit=2)
        assert result_over["status"] == "fail", \
            f"3 pages should exceed limit 2, got status={result_over['status']}"

        # Test missing PDF
        result_missing = check_page_count(
            os.path.join(test_dir, "nonexistent.pdf"), limit=9
        )
        assert result_missing["status"] == "fail", \
            "Missing PDF should fail"

        print("[PASS] check_page_count: binary heuristic counts /Type /Page, "
              "not /Type /Pages; handles missing PDF")

        shutil.rmtree(test_dir)
        test_dir = None

    except Exception as e:
        print(f"[FAIL] check_page_count: {e}")
        all_passed = False
        if test_dir and os.path.exists(test_dir):
            shutil.rmtree(test_dir)

    # -------------------------------------------------------------------
    # Test 7: generate_checklist_report produces markdown with checkboxes
    # -------------------------------------------------------------------
    try:
        mock_results = {
            "venue": "neurips",
            "checked_at": "2026-03-15T00:00:00Z",
            "overall_ready": False,
            "checks": [
                {
                    "category": "compilation",
                    "item": "PDF compiles without errors",
                    "status": "pass",
                    "details": "PDF present",
                },
                {
                    "category": "format",
                    "item": "Page count within limit",
                    "status": "fail",
                    "details": "12 pages (limit: 9)",
                },
                {
                    "category": "citations",
                    "item": "All citations verified",
                    "status": "pass",
                    "details": "All 30 citations match",
                },
            ],
            "summary": {
                "total_checks": 3,
                "passed": 2,
                "failed": 1,
                "skipped": 0,
            },
            "blocking_issues": ["Page count exceeds limit"],
            "recommendations": ["Reduce content to fit 9 pages"],
        }

        report = generate_checklist_report(mock_results, "neurips")

        assert "# Submission Readiness Checklist" in report, \
            "Missing checklist header"
        assert "NEURIPS" in report, "Missing venue name"
        assert "NOT READY" in report, "Should show NOT READY"
        assert "[x]" in report, "Should have passing checkboxes"
        assert "[ ]" in report, "Should have failing checkboxes"
        assert "## Blocking Issues" in report, "Should have blocking issues section"
        assert "## Recommendations" in report, "Should have recommendations section"
        assert "## Checklist" in report, "Should have checklist section"
        assert "PASS" in report, "Should show PASS status"
        assert "FAIL" in report, "Should show FAIL status"

        print("[PASS] generate_checklist_report: markdown with checkboxes, "
              "blocking issues, recommendations")

    except Exception as e:
        print(f"[FAIL] generate_checklist_report: {e}")
        all_passed = False

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    print()
    if all_passed:
        print("=== All _submission_checker tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Some _submission_checker tests FAILED ===")
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
            description="Submission readiness checker"
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
            "--repro-dir", default="reproducibility",
            help="Reproducibility package dir (default: reproducibility)"
        )
        args = parser.parse_args()

        result = run_submission_check(
            venue=args.venue,
            output_dir=args.output_dir,
            repro_dir=args.repro_dir,
        )

        # Print summary
        overall = "READY" if result["overall_ready"] else "NOT READY"
        summary = result["summary"]
        print(f"\n{'=' * 60}")
        print(f"Submission Check: {overall}")
        print(f"Venue: {result['venue']}")
        print(
            f"Checks: {summary['passed']}/{summary['total_checks']} passed, "
            f"{summary['failed']} failed"
        )
        if result["blocking_issues"]:
            print(f"\nBlocking Issues:")
            for issue in result["blocking_issues"]:
                print(f"  - {issue}")
        if result["recommendations"]:
            print(f"\nRecommendations:")
            for rec in result["recommendations"]:
                print(f"  - {rec}")
        print(f"{'=' * 60}")

        sys.exit(0 if result["overall_ready"] else 1)
