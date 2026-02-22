#!/usr/bin/env python3
"""Pass 1: CrossRef verification.

Queries api.crossref.org/works with query.bibliographic and compares
title (Jaccard word similarity, threshold 0.85), first author last name,
year (+/-1), and venue (normalized).

Returns: dict with source="crossref", status, matched/mismatched fields,
found metadata, DOI, and timestamp.

Usage:
  # Smoke test a single title
  python3 _verify_crossref.py --test "Attention Is All You Need"

  # Verify a citation passed as JSON on stdin
  python3 _verify_crossref.py --json '{"title":"...", "authors":[...], "year":2017}'
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Ensure sibling imports work regardless of cwd
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import (
    jaccard_word_similarity,
    normalize_author_name,
    authors_match,
    normalize_venue,
    load_env,
)

SIMILARITY_THRESHOLD = 0.85
REQUEST_DELAY_SEC = 0.35  # 350ms -- polite pool 3 req/sec for list queries


def query_crossref(title, mailto):
    """Query CrossRef works endpoint using query.bibliographic.

    Returns raw JSON response dict or raises on network error.
    """
    encoded = urllib.parse.quote(title)
    url = (
        f"https://api.crossref.org/works"
        f"?query.bibliographic={encoded}"
        f"&rows=3"
        f"&mailto={urllib.parse.quote(mailto)}"
    )
    req = urllib.request.Request(url)
    req.add_header("User-Agent", f"EBPaperEngine/1.0 (mailto:{mailto})")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def verify_crossref(title, authors=None, year=None, venue=None, mailto=None):
    """Run CrossRef verification pass for a single citation.

    Args:
        title:   expected paper title
        authors: list of author name strings (expected)
        year:    expected publication year (int or None)
        venue:   expected venue string (or None)
        mailto:  email for polite pool (loaded from .env if None)

    Returns dict conforming to verification_passes item schema.
    """
    if mailto is None:
        mailto = load_env("CROSSREF_MAILTO", "ebpaper@example.com")

    result = {
        "source": "crossref",
        "status": "not_found",
        "matched_fields": [],
        "mismatched_fields": [],
        "found_title": None,
        "found_authors": None,
        "found_year": None,
        "found_venue": None,
        "found_doi": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        time.sleep(REQUEST_DELAY_SEC)
        data = query_crossref(title, mailto)
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

    items = data.get("message", {}).get("items", [])
    if not items:
        return result  # not_found

    for item in items:
        found_title = " ".join(item.get("title", []))
        if not found_title:
            continue

        # Title comparison -- Jaccard word similarity (locked)
        sim = jaccard_word_similarity(title, found_title)
        if sim < SIMILARITY_THRESHOLD:
            continue

        # We have a candidate match -- populate found fields
        result["found_title"] = found_title
        result["found_doi"] = item.get("DOI")

        # Extract authors
        cr_authors = []
        for a in item.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            if family:
                cr_authors.append(f"{given} {family}".strip())
        result["found_authors"] = cr_authors

        # Extract year
        date_parts = item.get("published-print", item.get("published-online", {}))
        if date_parts and date_parts.get("date-parts"):
            try:
                result["found_year"] = int(date_parts["date-parts"][0][0])
            except (IndexError, TypeError, ValueError):
                pass

        # Extract venue
        container = item.get("container-title", [])
        result["found_venue"] = container[0] if container else None

        # Build matched / mismatched field lists
        result["matched_fields"].append("title")

        # Author check
        if authors and cr_authors:
            if authors_match(authors, cr_authors):
                result["matched_fields"].append("authors")
            else:
                result["mismatched_fields"].append({
                    "field": "authors",
                    "expected": authors[0] if authors else "",
                    "found": cr_authors[0] if cr_authors else "",
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

        # Venue check (after normalization)
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

    # Went through all items, none matched above threshold
    return result


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def _print_result(r):
    print(json.dumps(r, indent=2))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python3 _verify_crossref.py --test "Paper Title"')
        print('  python3 _verify_crossref.py --json \'{"title":"...", ...}\'')
        sys.exit(1)

    flag = sys.argv[1]

    if flag == "--test":
        if len(sys.argv) < 3:
            print("Error: --test requires a title argument", file=sys.stderr)
            sys.exit(1)
        title = sys.argv[2]
        r = verify_crossref(title)
        _print_result(r)
        sys.exit(0 if r["status"] == "matched" else 1)

    elif flag == "--json":
        if len(sys.argv) < 3:
            print("Error: --json requires a JSON argument", file=sys.stderr)
            sys.exit(1)
        data = json.loads(sys.argv[2])
        r = verify_crossref(
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
