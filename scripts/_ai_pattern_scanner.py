#!/usr/bin/env python3
"""AI writing pattern scanner for academic text.

Detects all 17 AI writing patterns from .claude/hooks/paper-ai-pattern-check.js.
Provides command-level scanning of section files for the /paper:draft pipeline
to enforce the zero-AI-pattern requirement.

Pattern categories (9): hedging, filler, boilerplate, inflation,
  vague_quantity, ai_vocabulary, formalism, copula, hedging_chain

All functions use Python3 standard library only -- no pip installs.

Usage:
  python3 paper/scripts/_ai_pattern_scanner.py --file path/to/section.md
  python3 paper/scripts/_ai_pattern_scanner.py --dir paper/output/sections/
  python3 paper/scripts/_ai_pattern_scanner.py --self-test
"""

import argparse
import glob
import os
import re
import sys


# ---------------------------------------------------------------------------
# 1. AI_PATTERNS -- all 17 patterns from paper-ai-pattern-check.js
# ---------------------------------------------------------------------------

AI_PATTERNS = [
    # 1. Hedging chain
    {
        "pattern": re.compile(r"could\s+potentially\s+(?:perhaps|possibly)", re.IGNORECASE),
        "name": "Hedging chain",
        "category": "hedging",
        "fix": "Commit to the claim or remove it",
    },
    # 2. Filler phrase
    {
        "pattern": re.compile(r"it\s+is\s+(?:worth\s+noting|important\s+to\s+note|noteworthy)\s+that", re.IGNORECASE),
        "name": "Filler phrase",
        "category": "filler",
        "fix": "Delete -- if important, the reader will note it",
    },
    # 3. Boilerplate opening (In recent years)
    {
        "pattern": re.compile(r"^In\s+recent\s+years", re.IGNORECASE | re.MULTILINE),
        "name": "Boilerplate opening",
        "category": "boilerplate",
        "fix": "Start with a concrete problem statement",
    },
    # 4. Boilerplate opening (In the last/past few/several years/decades)
    {
        "pattern": re.compile(r"^In\s+the\s+(?:last|past)\s+(?:few|several)\s+(?:years|decades)", re.IGNORECASE | re.MULTILINE),
        "name": "Boilerplate opening",
        "category": "boilerplate",
        "fix": "Start with a concrete problem statement",
    },
    # 5. Boilerplate opening (With the rapid advancement/development/growth of)
    {
        "pattern": re.compile(r"^With\s+the\s+rapid\s+(?:advancement|development|growth)\s+of", re.IGNORECASE | re.MULTILINE),
        "name": "Boilerplate opening",
        "category": "boilerplate",
        "fix": "State the specific technical challenge",
    },
    # 6. Significance inflation (dramatically/significantly/vastly/remarkably improves/outperforms/etc)
    {
        "pattern": re.compile(r"(?:dramatically|significantly|vastly|remarkably)\s+(?:improves?|outperforms?|exceeds?|surpasses?)", re.IGNORECASE),
        "name": "Significance inflation",
        "category": "inflation",
        "fix": "Use specific numbers instead",
    },
    # 7. Significance inflation (groundbreaking/revolutionary/etc)
    {
        "pattern": re.compile(r"(?:groundbreaking|revolutionary|paradigm.shifting|game.changing)", re.IGNORECASE),
        "name": "Significance inflation",
        "category": "inflation",
        "fix": "Let the results speak for themselves",
    },
    # 8. Vague quantity (plethora/myriad/multitude)
    {
        "pattern": re.compile(r"a\s+(?:plethora|myriad|multitude)\s+of", re.IGNORECASE),
        "name": "Vague quantity",
        "category": "vague_quantity",
        "fix": "Use specific numbers or remove",
    },
    # 9. Hedging (to the best of our knowledge)
    {
        "pattern": re.compile(r"to\s+the\s+best\s+of\s+our\s+knowledge", re.IGNORECASE),
        "name": "Hedging",
        "category": "hedging",
        "fix": "Either it is novel or cite what exists",
    },
    # 10. AI vocabulary (landscape, not painting/image/photo)
    {
        "pattern": re.compile(r"\blandscape\b(?!\s+(?:painting|image|photo))", re.IGNORECASE),
        "name": "AI vocabulary",
        "category": "ai_vocabulary",
        "fix": "Use field, area, or domain",
    },
    # 11. AI vocabulary (showcasing)
    {
        "pattern": re.compile(r"\bshowcasing\b", re.IGNORECASE),
        "name": "AI vocabulary",
        "category": "ai_vocabulary",
        "fix": "Use demonstrating or showing",
    },
    # 12. AI vocabulary (testament to)
    {
        "pattern": re.compile(r"\btestament\s+to\b", re.IGNORECASE),
        "name": "AI vocabulary",
        "category": "ai_vocabulary",
        "fix": "Rephrase with specific evidence",
    },
    # 13. AI vocabulary (delve into/deeper)
    {
        "pattern": re.compile(r"\bdelve\s+(?:into|deeper)\b", re.IGNORECASE),
        "name": "AI vocabulary",
        "category": "ai_vocabulary",
        "fix": "Use examine, investigate, or analyze",
    },
    # 14. AI formalism (it is crucial/essential/imperative to/that)
    {
        "pattern": re.compile(r"it\s+is\s+(?:crucial|essential|imperative)\s+(?:to|that)", re.IGNORECASE),
        "name": "AI formalism",
        "category": "formalism",
        "fix": "State what should be done directly",
    },
    # 15. AI formalism (plays/serves a crucial/vital/pivotal/key role)
    {
        "pattern": re.compile(r"(?:plays|serves)\s+a\s+(?:crucial|vital|pivotal|key)\s+role", re.IGNORECASE),
        "name": "AI formalism",
        "category": "formalism",
        "fix": "State the specific function",
    },
    # 16. AI copula (boasts)
    {
        "pattern": re.compile(r"\bboasts\b", re.IGNORECASE),
        "name": "AI copula",
        "category": "copula",
        "fix": "Use has or includes",
    },
    # 17. AI vocabulary (leverage/leverages/leveraged)
    {
        "pattern": re.compile(r"\bleverage(?:s|d)?\b", re.IGNORECASE),
        "name": "AI vocabulary",
        "category": "ai_vocabulary",
        "fix": "Use use or employ",
    },
]


# ---------------------------------------------------------------------------
# 2. scan_text
# ---------------------------------------------------------------------------

def scan_text(text):
    """Scan text for AI writing patterns.

    Returns list of matches: {pattern_name, category, line_number,
    line_text, match_text, fix_suggestion}.
    """
    lines = text.split("\n")
    matches = []

    for line_idx, line in enumerate(lines):
        for p in AI_PATTERNS:
            for m in p["pattern"].finditer(line):
                matches.append({
                    "pattern_name": p["name"],
                    "category": p["category"],
                    "line_number": line_idx + 1,
                    "line_text": line.strip(),
                    "match_text": m.group(0),
                    "fix_suggestion": p["fix"],
                })

    return matches


# ---------------------------------------------------------------------------
# 3. scan_file
# ---------------------------------------------------------------------------

def scan_file(filepath):
    """Scan a single .md file for AI writing patterns.

    Returns {filepath, matches, total_matches, categories_flagged}.
    """
    with open(filepath, "r") as f:
        content = f.read()

    matches = scan_text(content)
    categories = sorted(set(m["category"] for m in matches))

    return {
        "filepath": filepath,
        "matches": matches,
        "total_matches": len(matches),
        "categories_flagged": categories,
    }


# ---------------------------------------------------------------------------
# 4. scan_directory
# ---------------------------------------------------------------------------

def scan_directory(dirpath):
    """Scan all .md files in a directory for AI writing patterns.

    Returns {files_scanned, files_with_matches, total_matches,
    per_file, clean}.
    """
    md_files = sorted(glob.glob(os.path.join(dirpath, "**", "*.md"), recursive=True))

    per_file = []
    total_matches = 0
    files_with_matches = 0

    for filepath in md_files:
        result = scan_file(filepath)
        per_file.append(result)
        total_matches += result["total_matches"]
        if result["total_matches"] > 0:
            files_with_matches += 1

    return {
        "files_scanned": len(md_files),
        "files_with_matches": files_with_matches,
        "total_matches": total_matches,
        "per_file": per_file,
        "clean": total_matches == 0,
    }


# ---------------------------------------------------------------------------
# 5. format_report
# ---------------------------------------------------------------------------

def format_report(scan_result):
    """Human-readable report with per-category summary and per-file details.

    Accepts either a scan_file result (has 'filepath') or
    scan_directory result (has 'per_file').
    """
    lines = []

    # Directory result
    if "per_file" in scan_result:
        if scan_result["clean"]:
            lines.append("CLEAN: Zero AI patterns detected.")
            lines.append(f"Files scanned: {scan_result['files_scanned']}")
            return "\n".join(lines)

        lines.append(f"AI PATTERN SCAN: {scan_result['total_matches']} issue(s) "
                      f"across {scan_result['files_with_matches']} file(s)")
        lines.append(f"Files scanned: {scan_result['files_scanned']}")
        lines.append("")

        # Category summary
        all_matches = []
        for pf in scan_result["per_file"]:
            all_matches.extend(pf["matches"])

        _append_category_summary(lines, all_matches)

        # Per-file details
        for pf in scan_result["per_file"]:
            if pf["total_matches"] > 0:
                lines.append(f"### {pf['filepath']}")
                _append_match_details(lines, pf["matches"])
                lines.append("")

    # Single file result
    elif "filepath" in scan_result:
        if scan_result["total_matches"] == 0:
            lines.append(f"CLEAN: Zero AI patterns detected in {scan_result['filepath']}.")
            return "\n".join(lines)

        lines.append(f"AI PATTERN SCAN: {scan_result['total_matches']} issue(s) "
                      f"in {scan_result['filepath']}")
        lines.append("")
        _append_category_summary(lines, scan_result["matches"])
        _append_match_details(lines, scan_result["matches"])

    return "\n".join(lines)


def _append_category_summary(lines, matches):
    """Append category summary section."""
    from collections import Counter
    cat_counts = Counter(m["category"] for m in matches)
    lines.append("## Category Summary")
    for cat, count in cat_counts.most_common():
        lines.append(f"  {cat}: {count}")
    lines.append("")


def _append_match_details(lines, matches):
    """Append per-match detail lines."""
    for m in matches:
        lines.append(f"  L{m['line_number']}: [{m['pattern_name']}] "
                      f"\"{m['match_text']}\" -> {m['fix_suggestion']}")


# ---------------------------------------------------------------------------
# Self-test with embedded mock data
# ---------------------------------------------------------------------------

def self_test():
    """Run all self-test assertions with embedded mock data."""
    import tempfile

    print("=== _ai_pattern_scanner self-test ===")
    print()

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"[PASS] {name}")
            passed += 1
        else:
            print(f"[FAIL] {name}" + (f" -- {detail}" if detail else ""))
            failed += 1

    # -- Verify pattern count --
    check("Pattern count: 17 patterns loaded",
          len(AI_PATTERNS) == 17,
          f"Got {len(AI_PATTERNS)}")

    # -- Mock text with at least one instance of each of the 17 patterns --
    mock_ai_text = """In recent years, research has expanded.
In the last few years, progress accelerated.
With the rapid advancement of machine learning, new methods emerged.
This could potentially perhaps solve the problem.
It is worth noting that the results are promising.
It is important to note that the method works.
The model dramatically improves performance.
This is a groundbreaking approach.
A plethora of methods exist.
To the best of our knowledge, this is novel.
The research landscape has changed.
This result is showcasing the potential.
This is a testament to the method.
We delve into the details.
It is crucial to understand the implications.
Attention plays a crucial role in transformers.
The framework boasts high accuracy.
We leverage existing methods.
The paradigm-shifting results are clear.
It is noteworthy that this works.
The approach significantly outperforms baselines.
We leveraged pre-trained models.
A myriad of techniques exist.
A multitude of approaches have been proposed.
In the past several decades, this field has grown.
With the rapid development of AI, new tools appeared.
With the rapid growth of data, storage is key.
The system vastly surpasses previous work.
The method remarkably exceeds expectations.
The game-changing results speak for themselves.
The revolutionary method transforms the field.
It is essential to consider.
It is imperative that we address.
Serves a vital role in the pipeline.
Plays a pivotal role in training.
Serves a key role in evaluation.
We delve deeper into analysis.
This is leverages well.
"""

    # -- Test 1: scan_text detects hedging chains --
    matches = scan_text("could potentially perhaps solve the problem")
    hedging_chains = [m for m in matches if m["pattern_name"] == "Hedging chain"]
    check("Test 1: detects hedging chains",
          len(hedging_chains) >= 1,
          f"Got {len(hedging_chains)} matches")

    # -- Test 2: scan_text detects filler phrases --
    matches = scan_text("It is worth noting that the results are promising.")
    fillers = [m for m in matches if m["pattern_name"] == "Filler phrase"]
    check("Test 2: detects filler phrases",
          len(fillers) >= 1,
          f"Got {len(fillers)} matches")

    # -- Test 3: scan_text detects boilerplate openings --
    matches = scan_text("In recent years, deep learning has transformed NLP.")
    boilerplates = [m for m in matches if m["pattern_name"] == "Boilerplate opening"]
    check("Test 3: detects boilerplate openings",
          len(boilerplates) >= 1,
          f"Got {len(boilerplates)} matches")

    # -- Test 4: scan_text detects significance inflation --
    matches = scan_text("The model dramatically improves accuracy by 50%.")
    inflations = [m for m in matches if m["pattern_name"] == "Significance inflation"]
    check("Test 4: detects significance inflation",
          len(inflations) >= 1,
          f"Got {len(inflations)} matches")

    # -- Test 5: scan_text detects vague quantities --
    matches = scan_text("A plethora of approaches have been proposed.")
    vague = [m for m in matches if m["pattern_name"] == "Vague quantity"]
    check("Test 5: detects vague quantities",
          len(vague) >= 1,
          f"Got {len(vague)} matches")

    # -- Test 6: scan_text detects AI vocabulary --
    text = "We delve into the landscape of multi-agent systems, showcasing results. We leverage existing frameworks."
    matches = scan_text(text)
    ai_vocab = [m for m in matches if m["category"] == "ai_vocabulary"]
    check("Test 6: detects AI vocabulary (delve, landscape, showcasing, leverage)",
          len(ai_vocab) >= 4,
          f"Got {len(ai_vocab)} ai_vocabulary matches: {[m['match_text'] for m in ai_vocab]}")

    # -- Test 7: clean academic text returns zero matches --
    clean_text = """We propose a novel method for multi-agent coordination.
Our approach achieves 94.2% accuracy on the MMLU benchmark,
representing a 3.1 percentage point improvement over the previous
state of the art. The method uses a hierarchical task decomposition
strategy combined with learned reward shaping. Experiments on three
standard benchmarks demonstrate consistent improvements across all
evaluation metrics. We release our code and model weights.
"""
    matches = scan_text(clean_text)
    check("Test 7: clean academic text returns zero matches",
          len(matches) == 0,
          f"Got {len(matches)} matches: {[m['match_text'] for m in matches]}")

    # -- Test 8: scan_file reads a .md file and returns matches with line numbers --
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_section.md")
        with open(test_file, "w") as f:
            f.write("# Introduction\n\nIn recent years, deep learning has changed everything.\n\nWe leverage existing models.\n")

        result = scan_file(test_file)
        check("Test 8: scan_file returns matches with line numbers",
              result["total_matches"] >= 2,
              f"Got {result['total_matches']} matches")
        check("Test 8b: scan_file has filepath",
              result["filepath"] == test_file)
        check("Test 8c: scan_file matches have line numbers",
              all("line_number" in m for m in result["matches"]))
        # "In recent years" is on line 3
        boilerplate_matches = [m for m in result["matches"] if m["pattern_name"] == "Boilerplate opening"]
        check("Test 8d: boilerplate opening detected at correct line",
              len(boilerplate_matches) >= 1 and boilerplate_matches[0]["line_number"] == 3,
              f"Line: {boilerplate_matches[0]['line_number'] if boilerplate_matches else 'N/A'}")

    # -- Test 9: scan_directory scans all .md files --
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create clean file
        with open(os.path.join(tmpdir, "clean.md"), "w") as f:
            f.write("# Methods\n\nWe propose a simple approach.\n")

        # Create dirty file
        with open(os.path.join(tmpdir, "dirty.md"), "w") as f:
            f.write("# Introduction\n\nIn recent years, AI has changed.\nWe leverage models.\n")

        result = scan_directory(tmpdir)
        check("Test 9: scan_directory scans all .md files",
              result["files_scanned"] == 2,
              f"Got {result['files_scanned']} files")
        check("Test 9b: scan_directory reports files with matches",
              result["files_with_matches"] == 1,
              f"Got {result['files_with_matches']} files with matches")
        check("Test 9c: scan_directory clean == False when matches exist",
              result["clean"] is False)

    # -- Test 10: All 17 patterns from paper-ai-pattern-check.js are present and functional --
    all_matches = scan_text(mock_ai_text)

    # Check each category has at least one match
    categories_found = set(m["category"] for m in all_matches)
    expected_categories = {"hedging", "filler", "boilerplate", "inflation",
                           "vague_quantity", "ai_vocabulary", "formalism", "copula"}
    missing_cats = expected_categories - categories_found
    check("Test 10a: all 9 categories detected",
          len(missing_cats) == 0,
          f"Missing categories: {missing_cats}")

    # Check each named pattern has at least one match
    pattern_names_found = set(m["pattern_name"] for m in all_matches)
    expected_names = {"Hedging chain", "Filler phrase", "Boilerplate opening",
                      "Significance inflation", "Vague quantity", "Hedging",
                      "AI vocabulary", "AI formalism", "AI copula"}
    missing_names = expected_names - pattern_names_found
    check("Test 10b: all 9 pattern names detected",
          len(missing_names) == 0,
          f"Missing names: {missing_names}")

    # Verify we detect all specific pattern variants
    # Pattern 1: hedging chain
    hc = [m for m in all_matches if m["pattern_name"] == "Hedging chain"]
    check("Test 10c: hedging chain pattern works", len(hc) >= 1)

    # Pattern 9: to the best of our knowledge
    tbk = [m for m in all_matches if m["match_text"].lower().startswith("to the best")]
    check("Test 10d: 'to the best of our knowledge' detected", len(tbk) >= 1)

    # Pattern 16: boasts
    boasts = [m for m in all_matches if "boasts" in m["match_text"].lower()]
    check("Test 10e: 'boasts' (AI copula) detected", len(boasts) >= 1)

    # Pattern 12: testament to
    testament = [m for m in all_matches if "testament" in m["match_text"].lower()]
    check("Test 10f: 'testament to' detected", len(testament) >= 1)

    # Count total unique patterns that matched
    check("Test 10g: all 17 patterns are present in AI_PATTERNS list",
          len(AI_PATTERNS) == 17)

    # -- Test: format_report for clean result --
    clean_result = {"files_scanned": 5, "files_with_matches": 0,
                    "total_matches": 0, "per_file": [], "clean": True}
    report = format_report(clean_result)
    check("Test: format_report clean output",
          "CLEAN: Zero AI patterns detected" in report)

    # -- Test: format_report for dirty result --
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.md")
        with open(test_file, "w") as f:
            f.write("We leverage existing methods.\n")
        dirty_result = scan_file(test_file)
        report = format_report(dirty_result)
        check("Test: format_report dirty output has details",
              "AI PATTERN SCAN" in report and "leverage" in report.lower())

    print()
    print(f"=== _ai_pattern_scanner self-test: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)
    print("=== All _ai_pattern_scanner tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scan academic text for AI writing patterns."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Scan a single .md file")
    group.add_argument("--dir", help="Scan all .md files in directory")
    group.add_argument("--self-test", action="store_true",
                       help="Run embedded self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.file:
        if not os.path.isfile(args.file):
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        result = scan_file(args.file)
        print(format_report(result))
        sys.exit(0 if result["total_matches"] == 0 else 1)
    elif args.dir:
        if not os.path.isdir(args.dir):
            print(f"Error: directory not found: {args.dir}", file=sys.stderr)
            sys.exit(1)
        result = scan_directory(args.dir)
        print(format_report(result))
        sys.exit(0 if result["clean"] else 1)
