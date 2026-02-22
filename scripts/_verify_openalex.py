#!/usr/bin/env python3
"""Pass 3: OpenAlex verification.

Queries api.openalex.org/works with api_key parameter (required since
Feb 13, 2026) and compares title (SequenceMatcher, threshold 0.85),
first author last name, year, and venue (normalized).

Returns: dict with source="openalex", status, matched/mismatched fields,
found metadata, openalex_id, and timestamp.

Usage:
  python3 _verify_openalex.py --test "Attention Is All You Need"
  python3 _verify_openalex.py --json '{"title":"...", "authors":[...], "year":2017}'
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
REQUEST_DELAY_SEC = 0.35  # 350ms between requests


def query_openalex(title, api_key, mailto):
    """Query OpenAlex works endpoint with title search.

    CRITICAL: API key required since Feb 13, 2026.
    Returns raw JSON response dict.
    """
    encoded = urllib.parse.quote(title)
    url = (
        f"https://api.openalex.org/works"
        f"?filter=title.search:{encoded}"
        f"&per_page=3"
        f"&api_key={urllib.parse.quote(api_key)}"
        f"&mailto={urllib.parse.quote(mailto)}"
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def verify_openalex(title, authors=None, year=None, venue=None,
                    api_key=None, mailto=None):
    """Run OpenAlex verification pass for a single citation.

    Args:
        title:   expected paper title
        authors: list of author name strings (expected)
        year:    expected publication year (int or None)
        venue:   expected venue string (or None)
        api_key: OpenAlex API key (loaded from .env if None)
        mailto:  email for polite pool (loaded from .env if None)

    Returns dict conforming to verification_passes item schema.
    """
    if api_key is None:
        api_key = load_env("OPENALEX_API_KEY", "")
    if mailto is None:
        mailto = load_env("CROSSREF_MAILTO", "ebpaper@example.com")

    result = {
        "source": "openalex",
        "status": "not_found",
        "matched_fields": [],
        "mismatched_fields": [],
        "found_title": None,
        "found_authors": None,
        "found_year": None,
        "found_venue": None,
        "found_doi": None,
        "openalex_id": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not api_key:
        result["status"] = "error"
        result["error_message"] = (
            "OPENALEX_API_KEY not set in .env. "
            "OpenAlex requires API key since Feb 13, 2026. "
            "Get a free key at https://openalex.org"
        )
        print(
            "WARNING: OPENALEX_API_KEY not set -- OpenAlex pass will return error",
            file=sys.stderr,
        )
        return result

    try:
        time.sleep(REQUEST_DELAY_SEC)
        data = query_openalex(title, api_key, mailto)
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

    works = data.get("results", [])
    if not works:
        return result  # not_found

    for work in works:
        found_title = work.get("title", "")
        if not found_title:
            continue

        # Title comparison -- SequenceMatcher (for OpenAlex pass)
        sim = sequence_similarity(title, found_title)
        if sim < SIMILARITY_THRESHOLD:
            continue

        # Candidate match -- populate found fields
        result["found_title"] = found_title
        result["openalex_id"] = work.get("id")

        # Extract authors from authorships[].author.display_name
        # OpenAlex uses inverted name format: "Last, First"
        oa_authors = []
        for authorship in work.get("authorships", []):
            author_obj = authorship.get("author", {})
            display_name = author_obj.get("display_name", "")
            if display_name:
                oa_authors.append(display_name)
        result["found_authors"] = oa_authors

        # Year
        result["found_year"] = work.get("publication_year")

        # Venue -- from primary_location.source.display_name
        primary_loc = work.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        result["found_venue"] = source.get("display_name")

        # DOI
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        result["found_doi"] = doi

        # Build matched / mismatched
        result["matched_fields"].append("title")

        # Author check
        if authors and oa_authors:
            if authors_match(authors, oa_authors):
                result["matched_fields"].append("authors")
            else:
                result["mismatched_fields"].append({
                    "field": "authors",
                    "expected": authors[0] if authors else "",
                    "found": oa_authors[0] if oa_authors else "",
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

    return result  # not_found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_result(r):
    print(json.dumps(r, indent=2))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python3 _verify_openalex.py --test "Paper Title"')
        print('  python3 _verify_openalex.py --json \'{"title":"...", ...}\'')
        sys.exit(1)

    flag = sys.argv[1]

    if flag == "--test":
        if len(sys.argv) < 3:
            print("Error: --test requires a title argument", file=sys.stderr)
            sys.exit(1)
        title = sys.argv[2]
        r = verify_openalex(title)
        _print_result(r)
        sys.exit(0 if r["status"] == "matched" else 1)

    elif flag == "--json":
        if len(sys.argv) < 3:
            print("Error: --json requires a JSON argument", file=sys.stderr)
            sys.exit(1)
        data = json.loads(sys.argv[2])
        r = verify_openalex(
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
