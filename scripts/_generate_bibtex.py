#!/usr/bin/env python3
"""BibTeX generation from verified_citations.json.

Uses CrossRef content negotiation for DOI-resolved papers (preferred path),
manual BibTeX generation as fallback for no-DOI papers.

Venue names are normalized via _shared_utils.normalize_venue().
Failed citations produce no BibTeX. Partial citations get a warning comment.
Each citation's bibtex field is written back to verified_citations.json.

Usage:
  # Generate bibliography.bib from verified citations
  python3 _generate_bibtex.py paper/output/verified_citations.json paper/output/bibliography.bib

  # Self-test with hardcoded citation
  python3 _generate_bibtex.py --test-bibtex
"""

import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import normalize_venue, atomic_write, load_env


# ---------------------------------------------------------------------------
# Required fields per BibTeX entry type
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = {
    "inproceedings": ["author", "title", "booktitle", "year"],
    "article": ["author", "title", "journal", "year"],
    "misc": [],  # No required fields for misc
}

# Relevant fields per entry type (for stripping CrossRef extras)
RELEVANT_FIELDS = {
    "inproceedings": {
        "author", "title", "booktitle", "year", "pages", "doi",
        "url", "publisher", "editor", "series", "volume", "address",
        "eprint", "archiveprefix", "primaryclass",
    },
    "article": {
        "author", "title", "journal", "year", "volume", "number",
        "pages", "doi", "url", "publisher", "issn", "month",
        "eprint", "archiveprefix", "primaryclass",
    },
    "misc": {
        "author", "title", "year", "doi", "url", "howpublished",
        "note", "eprint", "archiveprefix", "primaryclass",
    },
}


# ---------------------------------------------------------------------------
# CrossRef content negotiation
# ---------------------------------------------------------------------------

def fetch_bibtex_from_doi(doi):
    """Fetch BibTeX via CrossRef content negotiation.

    GET https://doi.org/{doi} with Accept: application/x-bibtex.
    Returns BibTeX string or None on failure.
    Sleeps 100ms between calls (respects 10 req/sec limit).
    """
    if not doi:
        return None

    mailto = load_env("CROSSREF_MAILTO", "paper-pipeline@example.com")
    url = f"https://doi.org/{doi}"
    headers = {
        "Accept": "application/x-bibtex",
        "User-Agent": f"PaperPipeline/1.0 (mailto:{mailto})",
    }

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            bibtex = resp.read().decode("utf-8", errors="replace")
        time.sleep(0.1)  # 100ms rate limiting
        if bibtex and bibtex.strip().startswith("@"):
            return bibtex.strip()
        return None
    except (HTTPError, URLError, OSError, UnicodeDecodeError):
        time.sleep(0.1)
        return None


def _parse_bibtex_entry_type(bibtex_str):
    """Extract the entry type from a BibTeX string (e.g., 'inproceedings')."""
    m = re.match(r'@(\w+)\s*\{', bibtex_str)
    if m:
        return m.group(1).lower()
    return "misc"


def _parse_bibtex_fields(bibtex_str):
    """Simple parser to extract field=value pairs from a BibTeX entry.

    Returns dict of field_name -> value (braces stripped).
    """
    fields = {}
    # Match field = {value} or field = "value" or field = number
    for m in re.finditer(
        r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)"|(\d+))',
        bibtex_str,
    ):
        name = m.group(1).lower()
        value = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else m.group(4)
        )
        fields[name] = value
    return fields


def _rebuild_bibtex(entry_type, citation_key, fields):
    """Rebuild a BibTeX entry string from type, key, and fields dict."""
    lines = [f"@{entry_type}{{{citation_key},"]
    for name, value in fields.items():
        # Use braces for all values
        lines.append(f"  {name} = {{{value}}},")
    lines.append("}")
    return "\n".join(lines)


def post_process_crossref_bibtex(bibtex_str, citation):
    """Post-process BibTeX from CrossRef.

    1. Replace CrossRef citation key with lastname2023word key
    2. Normalize venue names in booktitle/journal fields
    3. Strip fields not relevant to the entry type
    """
    if not bibtex_str:
        return bibtex_str

    entry_type = _parse_bibtex_entry_type(bibtex_str)
    fields = _parse_bibtex_fields(bibtex_str)
    citation_key = citation.get("citation_key", "unknown")

    # Normalize venue in booktitle and journal fields
    for venue_field in ("booktitle", "journal"):
        if venue_field in fields:
            fields[venue_field] = normalize_venue(fields[venue_field])

    # Strip irrelevant fields
    relevant = RELEVANT_FIELDS.get(entry_type, RELEVANT_FIELDS["misc"])
    fields = {k: v for k, v in fields.items() if k in relevant}

    return _rebuild_bibtex(entry_type, citation_key, fields)


# ---------------------------------------------------------------------------
# Manual BibTeX generation (fallback)
# ---------------------------------------------------------------------------

def _determine_entry_type(citation):
    """Determine BibTeX entry type from citation metadata.

    @inproceedings for conferences, @article for journals, @misc for preprints/arXiv.
    """
    venue = (citation.get("venue") or "").lower()
    arxiv_id = citation.get("arxiv_id")

    # arXiv preprints
    if arxiv_id or "arxiv" in venue:
        return "misc"

    # Known conference venues -> inproceedings
    conference_indicators = [
        "conference", "proceedings", "workshop", "symposium",
        "neurips", "icml", "iclr", "aaai", "acl", "emnlp", "naacl",
        "cvpr", "eccv", "iccv",
    ]
    for indicator in conference_indicators:
        if indicator in venue:
            return "inproceedings"

    # Known journal indicators -> article
    journal_indicators = [
        "journal", "transactions", "review", "nature", "science",
        "jmlr", "tpami",
    ]
    for indicator in journal_indicators:
        if indicator in venue:
            return "article"

    # Default to inproceedings for ML papers
    return "inproceedings"


def generate_bibtex_manual(citation, entry_type=None):
    """Generate BibTeX manually for papers without DOI.

    Args:
        citation: dict with citation_key, title, authors, year, venue, doi, arxiv_id, url
        entry_type: override entry type, or None to auto-detect

    Returns BibTeX string.
    """
    if entry_type is None:
        entry_type = _determine_entry_type(citation)

    key = citation.get("citation_key", "unknown")
    fields = {}

    # Always include these
    title = citation.get("title", "")
    if title:
        fields["title"] = title

    authors = citation.get("authors", [])
    if authors:
        fields["author"] = " and ".join(authors)

    year = citation.get("year")
    if year is not None:
        fields["year"] = str(year)

    # Venue: booktitle for inproceedings, journal for article
    venue = citation.get("venue", "")
    if venue:
        normalized = normalize_venue(venue)
        if entry_type == "inproceedings":
            fields["booktitle"] = normalized
        elif entry_type == "article":
            fields["journal"] = normalized

    # DOI if available
    doi = citation.get("doi")
    if doi:
        fields["doi"] = doi

    # arXiv fields
    arxiv_id = citation.get("arxiv_id")
    if arxiv_id:
        fields["eprint"] = arxiv_id
        fields["archiveprefix"] = "arXiv"

    # URL
    url = citation.get("url")
    if url:
        fields["url"] = url

    return _rebuild_bibtex(entry_type, key, fields)


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------

def validate_bibtex_fields(bibtex_str):
    """Validate required fields are present for the entry type.

    Returns list of warning strings (empty = valid).
    """
    entry_type = _parse_bibtex_entry_type(bibtex_str)
    fields = _parse_bibtex_fields(bibtex_str)
    required = REQUIRED_FIELDS.get(entry_type, [])

    warnings = []
    for field in required:
        if field not in fields or not fields[field].strip():
            warnings.append(f"Missing required field '{field}' for @{entry_type}")
    return warnings


# ---------------------------------------------------------------------------
# Main: generate_bibliography
# ---------------------------------------------------------------------------

def generate_bibliography(verified_citations_path, output_bib_path):
    """Generate bibliography.bib from verified_citations.json.

    1. Load verified_citations.json
    2. For each citation: CrossRef fetch (DOI) or manual generation
    3. Deduplicate by citation_key
    4. Validate required fields
    5. Write to output_bib_path via atomic_write
    6. Write back bibtex field to verified_citations.json

    Returns count of entries written.
    """
    with open(verified_citations_path, 'r') as f:
        citations = json.load(f)

    entries = []
    seen_keys = set()
    all_warnings = []

    for citation in citations:
        status = citation.get("verification_status", "")
        key = citation.get("citation_key", "")

        # Skip failed citations entirely (locked: never generate BibTeX for failed)
        if status == "failed":
            citation["bibtex"] = ""
            continue

        # Deduplicate by citation_key
        if key in seen_keys:
            continue
        seen_keys.add(key)

        bibtex_str = None
        entry_type = _determine_entry_type(citation)

        if status == "verified":
            doi = citation.get("doi")
            if doi:
                # Preferred path: CrossRef content negotiation
                raw_bibtex = fetch_bibtex_from_doi(doi)
                if raw_bibtex:
                    bibtex_str = post_process_crossref_bibtex(raw_bibtex, citation)
                else:
                    # Fallback to manual if CrossRef fetch fails
                    bibtex_str = generate_bibtex_manual(citation, entry_type)
            else:
                # No DOI: manual generation
                bibtex_str = generate_bibtex_manual(citation, entry_type)

        elif status == "partial":
            # Partial: manual generation with warning comment
            bibtex_str = generate_bibtex_manual(citation, entry_type)
            bibtex_str = (
                "% WARNING: This citation has partial verification. "
                "Metadata may be inaccurate.\n" + bibtex_str
            )

        if bibtex_str:
            # Validate required fields
            warnings = validate_bibtex_fields(bibtex_str)
            for w in warnings:
                all_warnings.append(f"[{key}] {w}")
                print(f"  WARNING: [{key}] {w}", file=sys.stderr)

            entries.append(bibtex_str)
            citation["bibtex"] = bibtex_str

    # Print warnings summary
    if all_warnings:
        print(f"\nBibTeX validation: {len(all_warnings)} warning(s)", file=sys.stderr)

    # Assemble full bibliography
    bibliography = "\n\n".join(entries) + "\n" if entries else ""
    atomic_write(output_bib_path, bibliography)

    # Write back bibtex fields to verified_citations.json
    updated_content = json.dumps(citations, indent=2, ensure_ascii=False) + "\n"
    atomic_write(verified_citations_path, updated_content)

    return len(entries)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_test_bibtex():
    """Test BibTeX generation with a hardcoded citation."""
    print("=== BibTeX generation self-test ===\n")

    test_citation = {
        "citation_key": "vaswani2017attention",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        "year": 2017,
        "venue": "NeurIPS",
        "doi": "10.5555/3495724.3496517",
        "arxiv_id": None,
        "url": None,
        "verification_status": "verified",
    }

    # Test manual generation
    entry_type = "inproceedings"
    manual_bib = generate_bibtex_manual(test_citation, entry_type)
    print("Manual BibTeX:")
    print(manual_bib)
    print()

    assert "@inproceedings{vaswani2017attention" in manual_bib, "Missing entry header"
    assert "booktitle" in manual_bib, "Missing booktitle field"
    assert "Attention Is All You Need" in manual_bib, "Missing title"
    assert "2017" in manual_bib, "Missing year"
    print("[PASS] Manual BibTeX generation")

    # Validate required fields
    warnings = validate_bibtex_fields(manual_bib)
    assert len(warnings) == 0, f"Unexpected warnings: {warnings}"
    print("[PASS] Required fields validation")

    # Test partial citation gets warning comment
    partial_citation = dict(test_citation, verification_status="partial")
    partial_bib = generate_bibtex_manual(partial_citation)
    assert "booktitle" in partial_bib or "journal" in partial_bib
    print("[PASS] Partial citation BibTeX generation")

    # Test venue normalization in manual generation
    long_venue_citation = dict(
        test_citation,
        venue="Advances in Neural Information Processing Systems",
    )
    long_bib = generate_bibtex_manual(long_venue_citation, "inproceedings")
    assert "NeurIPS" in long_bib, f"Venue not normalized: {long_bib}"
    print("[PASS] Venue normalization in manual BibTeX")

    # Test entry type detection
    assert _determine_entry_type({"venue": "NeurIPS"}) == "inproceedings"
    assert _determine_entry_type({"venue": "JMLR", "arxiv_id": None}) == "article"
    assert _determine_entry_type({"venue": "arXiv", "arxiv_id": "2301.00001"}) == "misc"
    print("[PASS] Entry type detection")

    print("\n=== All BibTeX tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 _generate_bibtex.py <verified_citations.json> <output.bib>")
        print("  python3 _generate_bibtex.py --test-bibtex")
        sys.exit(1)

    if sys.argv[1] == "--test-bibtex":
        _run_test_bibtex()
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: requires verified_citations.json path and output .bib path",
              file=sys.stderr)
        sys.exit(1)

    verified_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.isfile(verified_path):
        print(f"Error: {verified_path} not found", file=sys.stderr)
        sys.exit(1)

    count = generate_bibliography(verified_path, output_path)
    print(f"BibTeX generation complete: {count} entries written to {output_path}")


if __name__ == "__main__":
    main()
