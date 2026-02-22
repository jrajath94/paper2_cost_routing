#!/usr/bin/env python3
"""Adjudication logic and verified_citations.json generation.

Implements locked adjudication rules:
  - 2+ matched AND metadata consistent -> "verified"
  - 2+ matched BUT metadata inconsistent -> "partial"
  - 1 matched -> "partial"
  - 0 matched -> "failed" (suspected_fabrication flag)

Preprint exception: arXiv papers < 3 months old with 1 S2 match -> "verified".

Usage:
  # Unit test adjudication
  python3 _adjudicate_citations.py --test-adjudicate

  # Build verified_citations.json from literature map + pass results
  python3 _adjudicate_citations.py paper/output/literature_map.json paper/output/_pass_results/
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import (
    normalize_author_name,
    normalize_venue,
    atomic_write,
)


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------

def adjudicate(passes):
    """Determine verification status from 3 pass results.

    Args:
        passes: list of dicts, each with at least a "status" key.
                Optional keys: "found_year", "found_authors", "source".

    Returns one of: "verified", "partial", "failed".
    """
    matched_count = sum(1 for p in passes if p.get("status") == "matched")

    if matched_count >= 2:
        matched_passes = [p for p in passes if p.get("status") == "matched"]
        if _metadata_consistent(matched_passes):
            return "verified"
        else:
            return "partial"  # Matched but metadata disagrees
    elif matched_count == 1:
        return "partial"
    else:
        return "failed"


def adjudicate_with_flags(passes, arxiv_id=None, arxiv_date=None):
    """Extended adjudication returning (status, flags).

    Handles the preprint exception: arXiv papers < 3 months old with
    S2 match get "verified" instead of "partial".

    Args:
        passes:     list of pass result dicts
        arxiv_id:   arXiv ID string (e.g., "2310.12345") or None
        arxiv_date: arXiv v1 submission date string (ISO) or None

    Returns (status, flags) where flags is a list of strings.
    """
    flags = []
    base_status = adjudicate(passes)

    if base_status == "failed":
        flags.append("suspected_fabrication")

    # Preprint exception: arXiv < 3 months, accept 1-pass if S2 found it
    if base_status == "partial" and arxiv_id:
        matched_count = sum(1 for p in passes if p.get("status") == "matched")
        if matched_count == 1:
            s2_matched = any(
                p.get("source") == "semantic_scholar" and p.get("status") == "matched"
                for p in passes
            )
            if s2_matched and _is_recent_preprint(arxiv_date):
                base_status = "verified"
                flags.append("preprint_exception")

    return base_status, flags


def _metadata_consistent(passes):
    """Check if matched passes agree on core metadata.

    After venue normalization, year should be exact match and
    first author last name should match across matched passes.
    """
    if len(passes) < 2:
        return True  # Single pass -- nothing to compare

    # Year agreement: all found_year values (where present) should match
    years = set()
    for p in passes:
        y = p.get("found_year")
        if y is not None:
            years.add(int(y))
    if len(years) > 1:
        return False  # Year disagreement

    # First author agreement across matched passes
    first_authors = []
    for p in passes:
        fa = p.get("found_authors")
        if fa and len(fa) > 0:
            first_authors.append(normalize_author_name(fa[0]))
    if len(set(first_authors)) > 1:
        return False  # First author disagreement

    return True


def _is_recent_preprint(arxiv_date, months=3):
    """Check if arXiv submission date is within last N months."""
    if not arxiv_date:
        return False
    try:
        if isinstance(arxiv_date, str):
            # Try ISO format
            dt = datetime.fromisoformat(arxiv_date.replace('Z', '+00:00'))
        else:
            dt = arxiv_date
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
        return dt >= cutoff
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Citation key generation
# ---------------------------------------------------------------------------

def generate_citation_key(paper):
    """Generate BibTeX key: lastname2023word.

    Args:
        paper: dict with "authors" (list), "year" (int), "title" (str)

    Returns citation key string.
    """
    if not paper.get("authors"):
        last_name = "unknown"
    else:
        first_author = paper["authors"][0]
        parts = first_author.split(",")
        if len(parts) > 1:
            last_name = parts[0].strip()
        else:
            last_name = first_author.split()[-1]
        last_name = re.sub(r'[^a-z]', '', last_name.lower())

    year = str(paper.get("year", ""))

    # First significant word from title
    skip_words = {"a", "an", "the", "on", "in", "of", "for", "and", "with", "to",
                  "is", "are", "by", "from", "at", "as", "its", "via", "using"}
    title_words = paper.get("title", "").lower().split()
    keyword = "unknown"
    for w in title_words:
        clean = re.sub(r'[^a-z]', '', w)
        if clean and clean not in skip_words:
            keyword = clean
            break

    return f"{last_name}{year}{keyword}"


# ---------------------------------------------------------------------------
# Build verified_citations.json
# ---------------------------------------------------------------------------

def build_verified_citations(literature_map_path, pass_results_dir):
    """Read literature_map.json and pass results, adjudicate, write output.

    Args:
        literature_map_path: path to literature_map.json
        pass_results_dir:    directory containing per-citation pass result JSON files

    Returns list of citation entry dicts.
    """
    with open(literature_map_path, 'r') as f:
        lit_map = json.load(f)

    papers = lit_map.get("papers", [])
    citations = []

    for paper in papers:
        paper_id = paper.get("id", "")
        # Load pass results for this paper
        passes = []
        for source in ["crossref", "semantic_scholar", "openalex"]:
            result_file = os.path.join(pass_results_dir, f"{paper_id}_{source}.json")
            if os.path.isfile(result_file):
                with open(result_file, 'r') as f:
                    passes.append(json.load(f))
            else:
                passes.append({
                    "source": source,
                    "status": "error",
                    "error_message": f"Pass result file not found: {result_file}",
                    "matched_fields": [],
                    "mismatched_fields": [],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        # Adjudicate
        arxiv_id = paper.get("arxiv_id")
        arxiv_date = paper.get("arxiv_date")
        status, flags = adjudicate_with_flags(passes, arxiv_id, arxiv_date)

        # Build citation entry per schema
        citation_key = generate_citation_key(paper)

        # Use the best found data from matched passes, falling back to input
        best_title = paper.get("title", "")
        best_authors = paper.get("authors", [])
        best_year = paper.get("year")
        best_venue = paper.get("venue", "")
        best_doi = None
        semantic_scholar_id = None
        openalex_id = None
        url = paper.get("url")

        for p in passes:
            if p.get("status") == "matched":
                if p.get("found_doi"):
                    best_doi = p["found_doi"]
                if p.get("semantic_scholar_id"):
                    semantic_scholar_id = p["semantic_scholar_id"]
                if p.get("openalex_id"):
                    openalex_id = p["openalex_id"]

        entry = {
            "citation_key": citation_key,
            "title": best_title,
            "authors": best_authors,
            "year": best_year,
            "venue": normalize_venue(best_venue),
            "doi": best_doi,
            "arxiv_id": arxiv_id,
            "semantic_scholar_id": semantic_scholar_id,
            "openalex_id": openalex_id,
            "url": url,
            "verification_status": status,
            "verification_passes": [
                {
                    "source": p.get("source", "unknown"),
                    "status": p.get("status", "error"),
                    "matched_fields": p.get("matched_fields", []),
                    "mismatched_fields": p.get("mismatched_fields", []),
                    "timestamp": p.get("timestamp", datetime.now(timezone.utc).isoformat()),
                }
                for p in passes
            ],
            "flags": flags,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        citations.append(entry)

    return citations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_test_adjudicate():
    """Run hardcoded test cases for adjudication logic."""
    print("=== Adjudication unit tests ===\n")

    # Test 1: 2/3 matched, consistent -> verified
    r = adjudicate([
        {"status": "matched", "found_year": 2023, "found_authors": ["Vaswani"]},
        {"status": "matched", "found_year": 2023, "found_authors": ["Vaswani"]},
        {"status": "not_found"},
    ])
    assert r == "verified", f"Test 1 failed: {r}"
    print("[PASS] 2/3 matched + consistent -> verified")

    # Test 2: 3/3 matched, consistent -> verified
    r = adjudicate([
        {"status": "matched", "found_year": 2017, "found_authors": ["Vaswani"]},
        {"status": "matched", "found_year": 2017, "found_authors": ["Vaswani"]},
        {"status": "matched", "found_year": 2017, "found_authors": ["Vaswani"]},
    ])
    assert r == "verified", f"Test 2 failed: {r}"
    print("[PASS] 3/3 matched + consistent -> verified")

    # Test 3: 2/3 matched but year disagrees -> partial
    r = adjudicate([
        {"status": "matched", "found_year": 2023, "found_authors": ["Smith"]},
        {"status": "matched", "found_year": 2024, "found_authors": ["Smith"]},
        {"status": "not_found"},
    ])
    assert r == "partial", f"Test 3 failed: {r}"
    print("[PASS] 2/3 matched + year disagree -> partial")

    # Test 4: 1/3 matched -> partial
    r = adjudicate([
        {"status": "matched", "found_year": 2023},
        {"status": "not_found"},
        {"status": "not_found"},
    ])
    assert r == "partial", f"Test 4 failed: {r}"
    print("[PASS] 1/3 matched -> partial")

    # Test 5: 0/3 matched -> failed
    r = adjudicate([
        {"status": "not_found"},
        {"status": "not_found"},
        {"status": "not_found"},
    ])
    assert r == "failed", f"Test 5 failed: {r}"
    print("[PASS] 0/3 matched -> failed")

    # Test 6: 0/3 (errors) -> failed
    r = adjudicate([
        {"status": "error"},
        {"status": "not_found"},
        {"status": "error"},
    ])
    assert r == "failed", f"Test 6 failed: {r}"
    print("[PASS] 0/3 (errors) -> failed")

    # Test 7: adjudicate_with_flags -- failed gets suspected_fabrication
    status, flags = adjudicate_with_flags([
        {"status": "not_found"},
        {"status": "not_found"},
        {"status": "not_found"},
    ])
    assert status == "failed", f"Test 7a failed: {status}"
    assert "suspected_fabrication" in flags, f"Test 7b failed: {flags}"
    print("[PASS] 0/3 failed -> suspected_fabrication flag")

    # Test 8: preprint exception
    recent_date = datetime.now(timezone.utc) - timedelta(days=30)
    status, flags = adjudicate_with_flags(
        [
            {"status": "not_found", "source": "crossref"},
            {"status": "matched", "source": "semantic_scholar", "found_year": 2026},
            {"status": "not_found", "source": "openalex"},
        ],
        arxiv_id="2602.12345",
        arxiv_date=recent_date.isoformat(),
    )
    assert status == "verified", f"Test 8a failed: {status}"
    assert "preprint_exception" in flags, f"Test 8b failed: {flags}"
    print("[PASS] preprint exception: recent arXiv + S2 match -> verified")

    # Test 9: citation key generation
    key = generate_citation_key({
        "authors": ["Vaswani, Ashish"],
        "year": 2017,
        "title": "Attention Is All You Need",
    })
    assert key == "vaswani2017attention", f"Test 9 failed: {key}"
    print("[PASS] citation key: vaswani2017attention")

    print("\n=== All adjudication tests PASSED ===")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 _adjudicate_citations.py --test-adjudicate")
        print("  python3 _adjudicate_citations.py <literature_map.json> <pass_results_dir/>")
        sys.exit(1)

    if sys.argv[1] == "--test-adjudicate":
        _run_test_adjudicate()
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: requires literature_map.json path and pass_results_dir", file=sys.stderr)
        sys.exit(1)

    lit_map_path = sys.argv[1]
    pass_results_dir = sys.argv[2]

    if not os.path.isfile(lit_map_path):
        print(f"Error: {lit_map_path} not found", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(pass_results_dir):
        print(f"Error: {pass_results_dir} not a directory", file=sys.stderr)
        sys.exit(1)

    citations = build_verified_citations(lit_map_path, pass_results_dir)

    output_path = os.path.join(
        os.path.dirname(lit_map_path), "verified_citations.json"
    )
    content = json.dumps(citations, indent=2, ensure_ascii=False)
    atomic_write(output_path, content + "\n")

    # Summary
    verified = sum(1 for c in citations if c["verification_status"] == "verified")
    partial = sum(1 for c in citations if c["verification_status"] == "partial")
    failed = sum(1 for c in citations if c["verification_status"] == "failed")
    print(f"Adjudication complete: {verified} verified, {partial} partial, {failed} failed")
    print(f"Output: {output_path}")

    if failed > 0:
        print(f"\nCRITICAL: {failed} citation(s) FAILED verification (suspected fabrication)")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
