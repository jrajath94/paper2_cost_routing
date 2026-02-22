#!/usr/bin/env python3
"""Pass 2: Semantic Scholar verification.

Queries /paper/search with S2 API key and compares title
(SequenceMatcher, threshold 0.85), first author last name, year, and
venue (normalized).

Returns: dict with source="semantic_scholar", status, matched/mismatched
fields, found metadata, semantic_scholar_id, citation_count, and timestamp.

Usage:
  python3 _verify_semantic_scholar.py --test "Attention Is All You Need"
  python3 _verify_semantic_scholar.py --json '{"title":"...", "authors":[...], "year":2017}'
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import (
    sequence_similarity,
    normalize_author_name,
    authors_match,
    normalize_venue,
    load_env,
)

SIMILARITY_THRESHOLD = 0.85
REQUEST_DELAY_SEC = 1.0  # 1 req/sec authenticated limit (locked decision)


def query_semantic_scholar(title, api_key):
    """Query Semantic Scholar paper search endpoint.

    Returns raw JSON response dict.
    """
    encoded = urllib.parse.quote(title)
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={encoded}"
        f"&limit=3"
        f"&fields=title,authors,year,venue,externalIds,citationCount"
    )
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("x-api-key", api_key)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def verify_semantic_scholar(title, authors=None, year=None, venue=None, api_key=None):
    """Run Semantic Scholar verification pass for a single citation.

    Args:
        title:   expected paper title
        authors: list of author name strings (expected)
        year:    expected publication year (int or None)
        venue:   expected venue string (or None)
        api_key: S2 API key (loaded from .env if None)

    Returns dict conforming to verification_passes item schema.
    """
    if api_key is None:
        api_key = load_env("S2_API_KEY", "")

    result = {
        "source": "semantic_scholar",
        "status": "not_found",
        "matched_fields": [],
        "mismatched_fields": [],
        "found_title": None,
        "found_authors": None,
        "found_year": None,
        "found_venue": None,
        "found_doi": None,
        "semantic_scholar_id": None,
        "citation_count": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not api_key:
        result["status"] = "error"
        result["error_message"] = "S2_API_KEY not set in .env"
        return result

    try:
        time.sleep(REQUEST_DELAY_SEC)
        data = query_semantic_scholar(title, api_key)
    except urllib.error.HTTPError as e:
        result["status"] = "error"
        result["error_message"] = f"HTTP {e.code}"
        if e.code == 429:
            result["rate_limit"] = True
        return result
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)
        return result

    papers = data.get("data", [])
    if not papers:
        return result  # not_found

    for paper in papers:
        found_title = paper.get("title", "")
        if not found_title:
            continue

        # Title comparison -- SequenceMatcher (for S2 pass)
        sim = sequence_similarity(title, found_title)
        if sim < SIMILARITY_THRESHOLD:
            continue

        # Candidate match -- populate found fields
        result["found_title"] = found_title
        result["semantic_scholar_id"] = paper.get("paperId")
        result["citation_count"] = paper.get("citationCount")

        # Extract authors
        s2_authors = []
        for a in paper.get("authors", []):
            name = a.get("name", "")
            if name:
                s2_authors.append(name)
        result["found_authors"] = s2_authors

        # Year
        result["found_year"] = paper.get("year")

        # Venue
        result["found_venue"] = paper.get("venue")

        # DOI from externalIds
        ext_ids = paper.get("externalIds", {}) or {}
        result["found_doi"] = ext_ids.get("DOI")

        # Build matched / mismatched
        result["matched_fields"].append("title")

        # Author check
        if authors and s2_authors:
            if authors_match(authors, s2_authors):
                result["matched_fields"].append("authors")
            else:
                result["mismatched_fields"].append({
                    "field": "authors",
                    "expected": authors[0] if authors else "",
                    "found": s2_authors[0] if s2_authors else "",
                })

        # Year check (exact or +/-1)
        if year is not None and result["found_year"] is not None:
            if abs(year - result["found_year"]) <= 1:
                result["matched_fields"].append("year")
            else:
                result["mismatched_fields"].append({
                    "field": "year",
                    "expected": str(year),
                    "found": str(result["found_year"]),
                })

        # Venue check
        if venue and result["found_venue"]:
            norm_expected = normalize_venue(venue)
            norm_found = normalize_venue(result["found_venue"])
            if norm_expected.lower() == norm_found.lower():
                result["matched_fields"].append("venue")
            else:
                result["mismatched_fields"].append({
                    "field": "venue",
                    "expected": norm_expected,
                    "found": norm_found,
                })

        result["status"] = "matched"
        return result

    return result  # not_found -- no candidate above threshold


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_result(r):
    print(json.dumps(r, indent=2))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python3 _verify_semantic_scholar.py --test "Paper Title"')
        print('  python3 _verify_semantic_scholar.py --json \'{"title":"...", ...}\'')
        sys.exit(1)

    flag = sys.argv[1]

    if flag == "--test":
        if len(sys.argv) < 3:
            print("Error: --test requires a title argument", file=sys.stderr)
            sys.exit(1)
        title = sys.argv[2]
        r = verify_semantic_scholar(title)
        _print_result(r)
        sys.exit(0 if r["status"] == "matched" else 1)

    elif flag == "--json":
        if len(sys.argv) < 3:
            print("Error: --json requires a JSON argument", file=sys.stderr)
            sys.exit(1)
        data = json.loads(sys.argv[2])
        r = verify_semantic_scholar(
            title=data["title"],
            authors=data.get("authors"),
            year=data.get("year"),
            venue=data.get("venue"),
        )
        _print_result(r)
        sys.exit(0 if r["status"] == "matched" else 1)

    else:
        print(f"Unknown flag: {flag}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
