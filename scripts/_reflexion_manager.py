#!/usr/bin/env python3
"""Reflexion loop manager for drafting critique pipeline.

Manages episodic memory (file-based critiques and plans), score delta
decisions, quality ratchet actions, and quality history entries for
the /paper:draft and /paper:review commands.

Score delta logic (from 07-RESEARCH.md):
  current_aggregate = average(quality, clarity, originality, significance)
  if current_aggregate >= 7.0: stop   # Threshold met
  elif round >= 3: stop               # Hard cap
  elif delta < 0.5 for 2 consecutive rounds: stop  # Diminishing returns
  else: continue

All functions use Python3 standard library only -- no pip installs.

Usage:
  python3 paper/scripts/_reflexion_manager.py --self-test
"""

import glob
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# 1. compute_aggregate
# ---------------------------------------------------------------------------

def compute_aggregate(scores):
    """Average of quality, clarity, originality, significance (all 1-10 int).

    Returns float rounded to 1 decimal.
    """
    dims = ["quality", "clarity", "originality", "significance"]
    total = sum(scores[d] for d in dims)
    return round(total / len(dims), 1)


# ---------------------------------------------------------------------------
# 2. should_continue_loop
# ---------------------------------------------------------------------------

def should_continue_loop(current_aggregate, round_num, score_history,
                         max_rounds=3, threshold=7.0, min_delta=0.5):
    """Decide whether to continue the Reflexion loop.

    Args:
        current_aggregate: Current round's aggregate score.
        round_num: Current round number (1-based).
        score_history: List of aggregate scores from prior rounds (oldest first).
        max_rounds: Hard cap on rounds (default 3 for draft Reflexion).
        threshold: Score threshold to stop (default 7.0).
        min_delta: Minimum improvement delta (default 0.5).

    Returns:
        (continue: bool, reason: str)
    """
    # Check threshold
    if current_aggregate >= threshold:
        return (False, f"Threshold met: {current_aggregate} >= {threshold}")

    # Check max rounds
    if round_num >= max_rounds:
        return (False, f"Max rounds reached: round {round_num} >= {max_rounds}")

    # Check diminishing returns: delta < min_delta for 2 consecutive rounds
    # Need at least 2 prior scores + current to check 2 consecutive deltas
    full_history = score_history + [current_aggregate]
    if len(full_history) >= 3:
        deltas = [full_history[i] - full_history[i - 1] for i in range(1, len(full_history))]
        # Check last 2 deltas
        if len(deltas) >= 2 and deltas[-1] < min_delta and deltas[-2] < min_delta:
            return (False, f"Diminishing returns: last 2 deltas ({deltas[-2]:.1f}, {deltas[-1]:.1f}) < {min_delta}")

    return (True, f"Continuing: round {round_num}, score {current_aggregate}")


# ---------------------------------------------------------------------------
# 3. determine_ratchet_action
# ---------------------------------------------------------------------------

def determine_ratchet_action(current_score, previous_best):
    """Returns 'accepted' if current >= previous_best (or previous_best is None),
    'rejected' otherwise.
    """
    if previous_best is None:
        return "accepted"
    if current_score >= previous_best:
        return "accepted"
    return "rejected"


# ---------------------------------------------------------------------------
# 4. create_critique_file
# ---------------------------------------------------------------------------

def create_critique_file(section_name, round_num, scores, issues_addressed,
                         new_issues, improvement_items, episodic_summary,
                         output_dir):
    """Write critique markdown following the format from 07-RESEARCH.md.

    Returns file path.
    """
    aggregate = compute_aggregate(scores)

    # Build score assessment table
    lines = [
        f"# Reflexion Critique: {section_name} - Round {round_num}",
        "",
        "## Score Assessment",
        "| Dimension    | Score |",
        "|-------------|-------|",
        f"| Quality     | {scores['quality']}   |",
        f"| Clarity     | {scores['clarity']}   |",
        f"| Originality | {scores['originality']}   |",
        f"| Significance| {scores['significance']}   |",
        f"| Aggregate   | {aggregate} |",
        "",
    ]

    # Issues Addressed
    if round_num > 1 and issues_addressed:
        lines.append(f"## Issues Addressed (from Round {round_num - 1} Plan)")
        for issue in issues_addressed:
            lines.append(f"- {issue}")
        lines.append("")
    else:
        lines.append(f"## Issues Addressed (from Round {round_num - 1} Plan)")
        lines.append("- N/A (first round)")
        lines.append("")

    # New Issues Found
    lines.append("## New Issues Found")
    if new_issues:
        for i, issue in enumerate(new_issues, 1):
            lines.append(f"{i}. {issue}")
    else:
        lines.append("None")
    lines.append("")

    # Improvement Plan
    lines.append(f"## Improvement Plan for Round {round_num + 1}")
    if improvement_items:
        for i, item in enumerate(improvement_items, 1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("None needed")
    lines.append("")

    # Episodic Memory Summary
    lines.append("## Episodic Memory Summary")
    lines.append(episodic_summary)
    lines.append("")

    content = "\n".join(lines)

    # Write file
    section_dir = os.path.join(output_dir, section_name)
    os.makedirs(section_dir, exist_ok=True)
    filepath = os.path.join(section_dir, f"round_{round_num}_critique.md")
    with open(filepath, "w") as f:
        f.write(content)

    return filepath


# ---------------------------------------------------------------------------
# 5. create_plan_file
# ---------------------------------------------------------------------------

def create_plan_file(section_name, round_num, improvement_items, output_dir):
    """Write improvement plan markdown.

    Each item has {section, location, problem, fix, priority}.
    Returns file path.
    """
    lines = [
        f"# Improvement Plan: {section_name} - Round {round_num}",
        "",
        "## Action Items",
        "",
    ]

    for i, item in enumerate(improvement_items, 1):
        lines.append(f"### Item {i} (Priority: {item.get('priority', 'medium')})")
        lines.append(f"- **Section:** {item.get('section', section_name)}")
        lines.append(f"- **Location:** {item.get('location', 'unspecified')}")
        lines.append(f"- **Problem:** {item.get('problem', 'unspecified')}")
        lines.append(f"- **Fix:** {item.get('fix', 'unspecified')}")
        lines.append("")

    content = "\n".join(lines)

    section_dir = os.path.join(output_dir, section_name)
    os.makedirs(section_dir, exist_ok=True)
    filepath = os.path.join(section_dir, f"round_{round_num}_plan.md")
    with open(filepath, "w") as f:
        f.write(content)

    return filepath


# ---------------------------------------------------------------------------
# 6. load_episodic_memory
# ---------------------------------------------------------------------------

def load_episodic_memory(section_name, reflexion_dir):
    """Load all prior critiques and plans for a given section, sorted by round.

    Returns {"critiques": [...], "plans": [...]} where each entry is
    {"round": int, "filepath": str, "content": str}.
    """
    section_dir = os.path.join(reflexion_dir, section_name)
    critiques = []
    plans = []

    if not os.path.isdir(section_dir):
        return {"critiques": [], "plans": []}

    for filename in sorted(os.listdir(section_dir)):
        filepath = os.path.join(section_dir, filename)
        if not os.path.isfile(filepath):
            continue

        # Extract round number from filename
        match = re.match(r"round_(\d+)_(critique|plan)\.md", filename)
        if not match:
            continue

        round_num = int(match.group(1))
        file_type = match.group(2)

        with open(filepath, "r") as f:
            content = f.read()

        entry = {"round": round_num, "filepath": filepath, "content": content}

        if file_type == "critique":
            critiques.append(entry)
        else:
            plans.append(entry)

    # Sort by round number
    critiques.sort(key=lambda x: x["round"])
    plans.sort(key=lambda x: x["round"])

    return {"critiques": critiques, "plans": plans}


# ---------------------------------------------------------------------------
# 7. build_quality_history_entry
# ---------------------------------------------------------------------------

def build_quality_history_entry(section, aggregate_score, scores, reviewer_id,
                                round_num, previous_best, action, commit_sha):
    """Build a dict matching quality_history.schema.json.

    Returns dict with all required fields.
    """
    return {
        "section": section,
        "aggregate_score": aggregate_score,
        "scores": {
            "quality": scores["quality"],
            "clarity": scores["clarity"],
            "originality": scores["originality"],
            "significance": scores["significance"],
        },
        "reviewer_id": reviewer_id,
        "round": round_num,
        "previous_best": previous_best,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
    }


# ---------------------------------------------------------------------------
# Self-test with embedded mock data
# ---------------------------------------------------------------------------

def self_test():
    """Run all self-test assertions with embedded mock data."""
    print("=== _reflexion_manager self-test ===")
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

    # -- Mock data: 3 rounds of scores for "introduction" section --
    round1_scores = {"quality": 5, "clarity": 6, "originality": 4, "significance": 5}
    round2_scores = {"quality": 6, "clarity": 7, "originality": 5, "significance": 6}
    round3_scores = {"quality": 7, "clarity": 7, "originality": 6, "significance": 8}

    # ---- Test 1: create_critique_file writes correctly formatted critique ----
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = create_critique_file(
            section_name="introduction",
            round_num=1,
            scores=round1_scores,
            issues_addressed=[],
            new_issues=["Paragraph 2 lacks citation for central claim"],
            improvement_items=["Add citation for claim in paragraph 2"],
            episodic_summary="Round 1: Initial draft scored 5.0.",
            output_dir=tmpdir,
        )
        expected_path = os.path.join(tmpdir, "introduction", "round_1_critique.md")
        check("Test 1: create_critique_file writes to correct path",
              filepath == expected_path,
              f"Expected {expected_path}, got {filepath}")
        check("Test 1b: critique file exists", os.path.isfile(filepath))
        content = open(filepath).read()
        check("Test 1c: critique contains section header",
              "# Reflexion Critique: introduction - Round 1" in content,
              f"Content: {content[:200]}")
        check("Test 1d: critique contains score table",
              "| Quality" in content and "| Aggregate" in content)

    # ---- Test 2: create_plan_file writes improvement plan ----
    with tempfile.TemporaryDirectory() as tmpdir:
        items = [
            {"section": "introduction", "location": "paragraph 2",
             "problem": "Missing citation", "fix": "Add Smith2024 citation", "priority": "high"},
            {"section": "introduction", "location": "paragraph 4",
             "problem": "Vague claim", "fix": "Add specific metric", "priority": "medium"},
        ]
        filepath = create_plan_file(
            section_name="introduction",
            round_num=1,
            improvement_items=items,
            output_dir=tmpdir,
        )
        expected_path = os.path.join(tmpdir, "introduction", "round_1_plan.md")
        check("Test 2: create_plan_file writes to correct path",
              filepath == expected_path)
        content = open(filepath).read()
        check("Test 2b: plan contains items",
              "Missing citation" in content and "Vague claim" in content)
        check("Test 2c: plan contains priority",
              "Priority: high" in content and "Priority: medium" in content)

    # ---- Test 3: should_continue_loop returns False when aggregate >= 7.0 ----
    cont, reason = should_continue_loop(7.5, 1, [])
    check("Test 3: stop when aggregate >= threshold",
          cont is False and "Threshold met" in reason,
          f"got ({cont}, {reason})")

    # ---- Test 4: should_continue_loop returns False when round >= 3 ----
    cont, reason = should_continue_loop(5.0, 3, [4.0, 4.5])
    check("Test 4: stop when round >= max_rounds",
          cont is False and "Max rounds" in reason,
          f"got ({cont}, {reason})")

    # ---- Test 5: should_continue_loop returns False for diminishing returns ----
    # History: [4.0, 4.3, 4.5] -- deltas are 0.3 and 0.2, both < 0.5
    cont, reason = should_continue_loop(4.5, 3, [4.0, 4.3], max_rounds=5)
    check("Test 5: stop on diminishing returns (2 consecutive deltas < 0.5)",
          cont is False and "Diminishing returns" in reason,
          f"got ({cont}, {reason})")

    # ---- Test 6: should_continue_loop returns True when improving ----
    cont, reason = should_continue_loop(5.5, 1, [])
    check("Test 6: continue when round < max and improving",
          cont is True and "Continuing" in reason,
          f"got ({cont}, {reason})")

    # Also test with decent delta
    cont, reason = should_continue_loop(6.0, 2, [5.0], max_rounds=3)
    check("Test 6b: continue when delta >= min_delta",
          cont is True,
          f"got ({cont}, {reason})")

    # ---- Test 7: load_episodic_memory returns sorted critiques and plans ----
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock files in reverse order to test sorting
        section_dir = os.path.join(tmpdir, "introduction")
        os.makedirs(section_dir)

        for r in [3, 1, 2]:
            with open(os.path.join(section_dir, f"round_{r}_critique.md"), "w") as f:
                f.write(f"Critique round {r}")
            with open(os.path.join(section_dir, f"round_{r}_plan.md"), "w") as f:
                f.write(f"Plan round {r}")

        memory = load_episodic_memory("introduction", tmpdir)
        check("Test 7: load_episodic_memory returns critiques sorted by round",
              [c["round"] for c in memory["critiques"]] == [1, 2, 3],
              f"got {[c['round'] for c in memory['critiques']]}")
        check("Test 7b: load_episodic_memory returns plans sorted by round",
              [p["round"] for p in memory["plans"]] == [1, 2, 3])
        check("Test 7c: episodic memory contains correct content",
              memory["critiques"][0]["content"] == "Critique round 1")

    # ---- Test 8: compute_aggregate averages correctly ----
    agg = compute_aggregate(round1_scores)  # (5+6+4+5)/4 = 5.0
    check("Test 8: compute_aggregate averages correctly",
          agg == 5.0, f"Expected 5.0, got {agg}")
    agg2 = compute_aggregate(round2_scores)  # (6+7+5+6)/4 = 6.0
    check("Test 8b: compute_aggregate round 2",
          agg2 == 6.0, f"Expected 6.0, got {agg2}")
    agg3 = compute_aggregate(round3_scores)  # (7+7+6+8)/4 = 7.0
    check("Test 8c: compute_aggregate round 3",
          agg3 == 7.0, f"Expected 7.0, got {agg3}")

    # ---- Test 9: determine_ratchet_action ----
    check("Test 9a: accepted when current >= previous_best",
          determine_ratchet_action(6.5, 6.0) == "accepted")
    check("Test 9b: accepted when current == previous_best",
          determine_ratchet_action(6.0, 6.0) == "accepted")
    check("Test 9c: rejected when current < previous_best",
          determine_ratchet_action(5.5, 6.0) == "rejected")
    check("Test 9d: accepted when previous_best is None (first review)",
          determine_ratchet_action(5.0, None) == "accepted")

    # ---- Test: build_quality_history_entry matches schema ----
    entry = build_quality_history_entry(
        section="introduction",
        aggregate_score=5.0,
        scores=round1_scores,
        reviewer_id="aggregate",
        round_num=1,
        previous_best=None,
        action="accepted",
        commit_sha="abc123f",
    )
    required_fields = ["section", "aggregate_score", "scores", "reviewer_id",
                       "round", "previous_best", "action", "timestamp", "commit_sha"]
    missing = [f for f in required_fields if f not in entry]
    check("Test: build_quality_history_entry has all required fields",
          len(missing) == 0, f"Missing: {missing}")
    check("Test: quality_history entry has correct score structure",
          all(k in entry["scores"] for k in ["quality", "clarity", "originality", "significance"]))
    check("Test: quality_history entry action is valid enum",
          entry["action"] in ("accepted", "rejected"))

    # ---- Integration test: full 3-round Reflexion simulation ----
    with tempfile.TemporaryDirectory() as tmpdir:
        history = []

        for round_num, scores in enumerate([round1_scores, round2_scores, round3_scores], 1):
            agg = compute_aggregate(scores)
            history.append(agg)

            # Create critique and plan
            create_critique_file(
                section_name="introduction",
                round_num=round_num,
                scores=scores,
                issues_addressed=[f"Fixed issue from round {round_num - 1}"] if round_num > 1 else [],
                new_issues=[f"New issue in round {round_num}"],
                improvement_items=[f"Fix issue from round {round_num}"],
                episodic_summary=f"Round {round_num}: scored {agg}",
                output_dir=tmpdir,
            )
            create_plan_file(
                section_name="introduction",
                round_num=round_num,
                improvement_items=[{
                    "section": "introduction",
                    "location": f"paragraph {round_num}",
                    "problem": f"Issue {round_num}",
                    "fix": f"Fix {round_num}",
                    "priority": "high",
                }],
                output_dir=tmpdir,
            )

        # Load episodic memory after 3 rounds
        memory = load_episodic_memory("introduction", tmpdir)
        check("Integration: 3 critiques loaded",
              len(memory["critiques"]) == 3)
        check("Integration: 3 plans loaded",
              len(memory["plans"]) == 3)

        # Score delta decision after round 3 (aggregate 7.0 meets threshold)
        cont, reason = should_continue_loop(7.0, 3, [5.0, 6.0])
        check("Integration: stops at round 3 with 7.0 (threshold met)",
              cont is False, f"got ({cont}, {reason})")

    print()
    print(f"=== _reflexion_manager self-test: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)
    print("=== All _reflexion_manager tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    else:
        print("Usage:")
        print(f"  python3 {sys.argv[0]} --self-test")
        sys.exit(1)
