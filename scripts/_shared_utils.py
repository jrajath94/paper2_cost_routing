#!/usr/bin/env python3
"""Shared utilities for the three-pass citation verification pipeline.

Provides string similarity, author/venue normalization, atomic file I/O,
and environment variable loading. Used by all verification pass scripts
and the adjudication module.

All functions use Python3 standard library only -- no pip installs.
"""

import os
import re
import json
import tempfile
import unicodedata
from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Venue normalization table -- sourced from paper-citation-verifier agent
# prompt.  Keys MUST be lowercase.  Values are the canonical short names.
# ---------------------------------------------------------------------------
VENUE_NORMALIZATION = {
    "advances in neural information processing systems": "NeurIPS",
    "neural information processing systems": "NeurIPS",
    "neurips": "NeurIPS",
    "nips": "NeurIPS",
    "international conference on machine learning": "ICML",
    "icml": "ICML",
    "international conference on learning representations": "ICLR",
    "iclr": "ICLR",
    "association for computational linguistics": "ACL",
    "acl": "ACL",
    "annual meeting of the association for computational linguistics": "ACL",
    "conference on empirical methods in natural language processing": "EMNLP",
    "empirical methods in natural language processing": "EMNLP",
    "emnlp": "EMNLP",
    "aaai conference on artificial intelligence": "AAAI",
    "aaai": "AAAI",
    "arxiv preprint": "arXiv",
    "arxiv": "arXiv",
    "ieee transactions on pattern analysis and machine intelligence": "IEEE TPAMI",
    "ieee tpami": "IEEE TPAMI",
    "nature machine intelligence": "Nature Machine Intelligence",
    "journal of machine learning research": "JMLR",
    "jmlr": "JMLR",
    "naacl": "NAACL",
    "north american chapter of the association for computational linguistics": "NAACL",
    "proceedings of the ieee conference on computer vision and pattern recognition": "CVPR",
    "cvpr": "CVPR",
    "european conference on computer vision": "ECCV",
    "eccv": "ECCV",
    "international conference on computer vision": "ICCV",
    "iccv": "ICCV",
}


# ---------------------------------------------------------------------------
# String similarity
# ---------------------------------------------------------------------------

def jaccard_word_similarity(s1, s2):
    """Jaccard similarity on word sets.

    Used by CrossRef pass (threshold 0.85 per locked decision).
    Returns float in [0.0, 1.0].
    """
    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def sequence_similarity(s1, s2):
    """SequenceMatcher ratio for title comparison.

    Used by Semantic Scholar and OpenAlex passes (threshold 0.85).
    Returns float in [0.0, 1.0].
    """
    return SequenceMatcher(None, s1.lower().strip(), s2.lower().strip()).ratio()


# ---------------------------------------------------------------------------
# Author name normalization
# ---------------------------------------------------------------------------

def normalize_author_name(name):
    """Normalize an author name: strip diacritics via NFKD, extract last name.

    Handles formats:
      - "First Last"
      - "Last, First"
      - "Last, F."
    Returns lowercase last name string.
    """
    if not name:
        return ""
    # NFKD decomposition then strip combining (diacritic) characters
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))
    ascii_name = ascii_name.strip()
    # "Last, First" or "Last, F." format
    parts = ascii_name.split(",")
    if len(parts) > 1:
        return parts[0].strip().lower()
    # "First Last" format -- last token is last name
    tokens = ascii_name.split()
    if tokens:
        return tokens[-1].strip().lower()
    return ""


def authors_match(expected, found):
    """Compare first-author last names only (per research recommendation).

    Args:
        expected: list of author name strings (expected/query side)
        found: list of author name strings (API result side)

    Returns True if first-author last names match.
    """
    if not expected or not found:
        return False
    expected_last = normalize_author_name(expected[0])
    found_last = normalize_author_name(found[0])
    return expected_last == found_last


# ---------------------------------------------------------------------------
# Venue normalization
# ---------------------------------------------------------------------------

def normalize_venue(venue):
    """Normalize venue name using the lookup table.

    Strips year suffixes (e.g., 'NeurIPS 2023' -> 'NeurIPS') before lookup.
    Returns original string if no mapping found.
    """
    if not venue:
        return ""
    # Strip trailing year (4-digit number) and whitespace
    clean = re.sub(r'\s*\d{4}\s*$', '', venue).strip()
    return VENUE_NORMALIZATION.get(clean.lower(), clean)


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------

def atomic_write(filepath, content):
    """Write content atomically: write to temp file, then os.rename.

    Prevents partial outputs on failures.
    """
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w', dir=dirpath, delete=False, suffix='.tmp'
    ) as f:
        f.write(content)
        tmppath = f.name
    os.rename(tmppath, filepath)


# ---------------------------------------------------------------------------
# Environment variable loading
# ---------------------------------------------------------------------------

def load_env(key, default=None):
    """Read a KEY=VALUE from the nearest .env file.

    Searches current directory and up to 3 parent directories.
    Simple parser -- no multiline, no interpolation.
    Falls back to os.environ, then to *default*.
    """
    # Walk up to find .env
    search_dir = os.getcwd()
    for _ in range(4):
        env_path = os.path.join(search_dir, '.env')
        if os.path.isfile(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == key:
                            return v
            break  # found .env but key not in it -- stop searching
        parent = os.path.dirname(search_dir)
        if parent == search_dir:
            break
        search_dir = parent
    # Fallback to OS environment
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Self-test when invoked directly
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=== _shared_utils self-test ===")

    # Jaccard
    assert jaccard_word_similarity("attention is all you need",
                                    "attention is all you need") == 1.0
    assert jaccard_word_similarity("", "hello") == 0.0
    print("[PASS] jaccard_word_similarity")

    # Sequence similarity
    assert sequence_similarity("attention is all you need",
                                "attention is all you need") == 1.0
    assert sequence_similarity("hello", "world") < 0.5
    print("[PASS] sequence_similarity")

    # Author normalization
    assert normalize_author_name("Yoshua Bengio") == "bengio"
    assert normalize_author_name("Bengio, Yoshua") == "bengio"
    assert normalize_author_name("Bengio, Y.") == "bengio"
    assert normalize_author_name("Rene Descartes") == "descartes"
    print("[PASS] normalize_author_name")

    # Authors match
    assert authors_match(["Vaswani, Ashish"], ["Ashish Vaswani"]) is True
    assert authors_match(["Vaswani, Ashish"], ["Yoshua Bengio"]) is False
    print("[PASS] authors_match")

    # Venue normalization
    assert normalize_venue("Advances in Neural Information Processing Systems") == "NeurIPS"
    assert normalize_venue("neurips") == "NeurIPS"
    assert normalize_venue("NeurIPS 2023") == "NeurIPS"
    assert normalize_venue("ICML 2024") == "ICML"
    assert normalize_venue("Unknown Venue") == "Unknown Venue"
    print("[PASS] normalize_venue")

    # Atomic write
    import tempfile as _tf
    test_dir = _tf.mkdtemp()
    test_path = os.path.join(test_dir, "test_atomic.txt")
    atomic_write(test_path, "hello world")
    with open(test_path) as f:
        assert f.read() == "hello world"
    os.remove(test_path)
    os.rmdir(test_dir)
    print("[PASS] atomic_write")

    print("\n=== All _shared_utils tests PASSED ===")
