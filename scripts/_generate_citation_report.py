#!/usr/bin/env python3
"""Generate human-readable citation verification report.

Reads verified_citations.json and produces a markdown report with:
- Summary statistics (total, verified, partial, failed)
- Verified citations table (sorted by year desc)
- Partial citations with specific issues
- CRITICAL section for failed citations (suspected fabrication)
- Verification coverage and pipeline gate status

Usage:
  # Generate report from verified citations
  python3 _generate_citation_report.py paper/output/verified_citations.json paper/output/citation_report.md

  # Self-test with hardcoded data
  python3 _generate_citation_report.py --test-report
"""

import json
import os
import sys
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import atomic_write


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(verified_citations_path, output_report_path):
    """Generate markdown citation verification report.

    1. Load verified_citations.json
    2. Compute summary stats
    3. Generate markdown with sections for verified, partial, failed
    4. Write to output_report_path via atomic_write
    """
    with open(verified_citations_path, 'r') as f:
        citations = json.load(f)

    total = len(citations)
    verified = [c for c in citations if c.get("verification_status") == "verified"]
    partial = [c for c in citations if c.get("verification_status") == "partial"]
    failed = [c for c in citations if c.get("verification_status") == "failed"]

    verified_count = len(verified)
    partial_count = len(partial)
    failed_count = len(failed)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = []

    # Header
    lines.append("# Citation Verification Report")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count | Percentage |")
    lines.append("|--------|-------|------------|")

    def pct(n):
        return f"{(n / total * 100):.1f}%" if total > 0 else "0.0%"

    lines.append(f"| Verified | {verified_count} | {pct(verified_count)} |")
    lines.append(f"| Partial | {partial_count} | {pct(partial_count)} |")
    lines.append(f"| Failed | {failed_count} | {pct(failed_count)} |")
    lines.append(f"| **Total** | **{total}** | **100%** |")
    lines.append("")

    # Verified citations table (sorted by year desc)
    lines.append("## Verified Citations")
    lines.append("")
    if verified:
        sorted_verified = sorted(verified, key=lambda c: c.get("year", 0), reverse=True)
        lines.append("| Citation Key | Title | Year | Venue | DOI |")
        lines.append("|-------------|-------|------|-------|-----|")
        for c in sorted_verified:
            key = c.get("citation_key", "")
            title = c.get("title", "")
            # Truncate long titles for table readability
            if len(title) > 60:
                title = title[:57] + "..."
            year = c.get("year", "")
            venue = c.get("venue", "")
            doi = c.get("doi") or "-"
            lines.append(f"| {key} | {title} | {year} | {venue} | {doi} |")
        lines.append("")
    else:
        lines.append("*No verified citations.*")
        lines.append("")

    # Partial citations with issues
    lines.append("## Partial Citations")
    lines.append("")
    if partial:
        lines.append("These citations have incomplete or inconsistent verification. "
                      "Review recommended before submission.")
        lines.append("")
        lines.append("| Citation Key | Title | Issues | Pass Results |")
        lines.append("|-------------|-------|--------|--------------|")
        for c in partial:
            key = c.get("citation_key", "")
            title = c.get("title", "")
            if len(title) > 50:
                title = title[:47] + "..."
            flags = c.get("flags", [])
            issues = ", ".join(flags) if flags else "metadata inconsistency"
            # Summarize pass results
            passes = c.get("verification_passes", [])
            pass_summary = []
            for p in passes:
                src = p.get("source", "?")
                st = p.get("status", "?")
                pass_summary.append(f"{src}={st}")
            pass_str = ", ".join(pass_summary)
            lines.append(f"| {key} | {title} | {issues} | {pass_str} |")
        lines.append("")
    else:
        lines.append("*No partial citations.*")
        lines.append("")

    # CRITICAL: Failed citations
    if failed_count > 0:
        lines.append("## CRITICAL: Failed Citations")
        lines.append("")
        lines.append("> **WARNING:** The following citations could not be verified in ANY "
                      "academic database. They MUST be removed or corrected before submission.")
        lines.append("")
        for c in failed:
            key = c.get("citation_key", "")
            title = c.get("title", "")
            year = c.get("year", "")
            authors = c.get("authors", [])
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            flags = c.get("flags", [])
            is_fabrication = "suspected_fabrication" in flags

            lines.append(f"### {key}")
            lines.append("")
            lines.append(f"- **Title:** {title}")
            lines.append(f"- **Authors:** {author_str}")
            lines.append(f"- **Year:** {year}")
            if is_fabrication:
                lines.append("- **Flag:** SUSPECTED FABRICATION")
            lines.append("")

            # Show pass details
            passes = c.get("verification_passes", [])
            lines.append("**Verification attempts:**")
            lines.append("")
            for p in passes:
                src = p.get("source", "unknown")
                st = p.get("status", "unknown")
                lines.append(f"- {src}: {st}")
            lines.append("")
            lines.append("**Action required:** This citation MUST be removed or corrected "
                          "before submission. If this is a real paper, provide the correct "
                          "title, authors, and DOI for manual verification.")
            lines.append("")
    else:
        lines.append("## Failed Citations")
        lines.append("")
        lines.append("*No failed citations. All citations passed verification.*")
        lines.append("")

    # Verification Coverage
    lines.append("## Verification Coverage")
    lines.append("")
    lines.append(f"- **Verified:** {pct(verified_count)} ({verified_count}/{total})")
    lines.append(f"- **Partial:** {pct(partial_count)} ({partial_count}/{total})")
    lines.append(f"- **Failed:** {pct(failed_count)} ({failed_count}/{total})")
    lines.append("")

    gate_status = "PASS" if failed_count == 0 else "FAIL"
    gate_icon = "PASS" if failed_count == 0 else "FAIL"
    lines.append(f"**Pipeline Gate:** {gate_icon}")
    if gate_status == "FAIL":
        lines.append(f"  - {failed_count} citation(s) failed verification. "
                      "Paper CANNOT proceed to submission.")
    else:
        lines.append("  - All citations verified or partially verified. "
                      "Paper may proceed to submission (review partial citations).")
    lines.append("")

    report = "\n".join(lines)
    atomic_write(output_report_path, report)

    return {
        "total": total,
        "verified": verified_count,
        "partial": partial_count,
        "failed": failed_count,
        "gate": gate_status,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_test_report():
    """Generate report from hardcoded test data."""
    print("=== Citation report self-test ===\n")

    test_citations = [
        {
            "citation_key": "vaswani2017attention",
            "title": "Attention Is All You Need",
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "year": 2017,
            "venue": "NeurIPS",
            "doi": "10.5555/3495724.3496517",
            "verification_status": "verified",
            "verification_passes": [
                {"source": "crossref", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "semantic_scholar", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "openalex", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
            ],
            "flags": [],
        },
        {
            "citation_key": "devlin2019bert",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "authors": ["Jacob Devlin", "Ming-Wei Chang"],
            "year": 2019,
            "venue": "NAACL",
            "doi": "10.18653/v1/N19-1423",
            "verification_status": "verified",
            "verification_passes": [
                {"source": "crossref", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "semantic_scholar", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "openalex", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
            ],
            "flags": [],
        },
        {
            "citation_key": "smith2025preprint",
            "title": "A New Approach to Something",
            "authors": ["John Smith"],
            "year": 2025,
            "venue": "arXiv",
            "doi": None,
            "verification_status": "partial",
            "verification_passes": [
                {"source": "crossref", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "semantic_scholar", "status": "matched", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "openalex", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
            ],
            "flags": ["single_pass_match"],
        },
        {
            "citation_key": "fake2024quantum",
            "title": "Quantum Neural Transformers for Recursive Self-Improvement",
            "authors": ["Fake Author"],
            "year": 2024,
            "venue": "Unknown",
            "doi": None,
            "verification_status": "failed",
            "verification_passes": [
                {"source": "crossref", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "semantic_scholar", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
                {"source": "openalex", "status": "not_found", "timestamp": "2026-01-01T00:00:00Z"},
            ],
            "flags": ["suspected_fabrication"],
        },
    ]

    # Generate report to stdout
    import tempfile
    tmp_citations = os.path.join(tempfile.mkdtemp(), "test_citations.json")
    tmp_report = os.path.join(os.path.dirname(tmp_citations), "test_report.md")

    with open(tmp_citations, 'w') as f:
        json.dump(test_citations, f, indent=2)

    stats = generate_report(tmp_citations, tmp_report)

    with open(tmp_report, 'r') as f:
        report_content = f.read()

    print(report_content)
    print("---")
    print(f"Stats: {stats}")

    # Validate
    assert stats["total"] == 4, f"Expected 4 total, got {stats['total']}"
    assert stats["verified"] == 2, f"Expected 2 verified, got {stats['verified']}"
    assert stats["partial"] == 1, f"Expected 1 partial, got {stats['partial']}"
    assert stats["failed"] == 1, f"Expected 1 failed, got {stats['failed']}"
    assert stats["gate"] == "FAIL", f"Expected FAIL gate, got {stats['gate']}"
    print("[PASS] Stats correct")

    assert "# Citation Verification Report" in report_content
    print("[PASS] Report has header")

    assert "CRITICAL" in report_content
    print("[PASS] Report has CRITICAL section")

    assert "suspected_fabrication" in report_content.lower() or "SUSPECTED FABRICATION" in report_content
    print("[PASS] Fabrication flag in report")

    assert "MUST be removed" in report_content
    print("[PASS] Removal instruction present")

    assert "**Pipeline Gate:** FAIL" in report_content
    print("[PASS] Pipeline gate shows FAIL")

    # Clean up
    os.remove(tmp_citations)
    os.remove(tmp_report)
    os.rmdir(os.path.dirname(tmp_citations))

    print("\n=== All citation report tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 _generate_citation_report.py <verified_citations.json> <output_report.md>")
        print("  python3 _generate_citation_report.py --test-report")
        sys.exit(1)

    if sys.argv[1] == "--test-report":
        _run_test_report()
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: requires verified_citations.json path and output report path",
              file=sys.stderr)
        sys.exit(1)

    verified_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.isfile(verified_path):
        print(f"Error: {verified_path} not found", file=sys.stderr)
        sys.exit(1)

    stats = generate_report(verified_path, output_path)
    print(f"Citation report generated: {output_path}")
    print(f"  Total: {stats['total']}, Verified: {stats['verified']}, "
          f"Partial: {stats['partial']}, Failed: {stats['failed']}")
    print(f"  Pipeline gate: {stats['gate']}")


if __name__ == "__main__":
    main()
