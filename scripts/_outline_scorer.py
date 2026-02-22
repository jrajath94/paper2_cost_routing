#!/usr/bin/env python3
"""Deterministic ToT-lite scoring for paper outline candidates.

Scores 3 candidate paper structures on flow, novelty, and engagement
dimensions using locked weights (0.40, 0.35, 0.25). Selects the best
candidate by weighted composite score.

Scoring uses locked weights:
  Weighted composite: flow * 0.40 + novelty * 0.35 + engagement * 0.25

All functions use Python3 standard library only -- no pip installs.

Usage:
  # Score candidates and select best, write output
  python3 paper/scripts/_outline_scorer.py <input_path> <output_path>

  # Self-test with embedded mock data
  python3 paper/scripts/_outline_scorer.py --self-test
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
# Constants -- locked scoring weights
# ---------------------------------------------------------------------------

WEIGHT_FLOW = 0.40
WEIGHT_NOVELTY = 0.35
WEIGHT_ENGAGEMENT = 0.25

# Verify weights sum to 1.0 at module load time
assert abs(WEIGHT_FLOW + WEIGHT_NOVELTY + WEIGHT_ENGAGEMENT - 1.0) < 1e-9, (
    f"Weights must sum to 1.0, got {WEIGHT_FLOW + WEIGHT_NOVELTY + WEIGHT_ENGAGEMENT}"
)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def validate_scores(scores: dict) -> bool:
    """Check that flow, novelty, engagement are integers in [1, 10].

    Args:
        scores: dict with keys flow, novelty, engagement

    Returns:
        True if all scores are valid, False otherwise.
    """
    for key in ("flow", "novelty", "engagement"):
        val = scores.get(key)
        if not isinstance(val, int):
            return False
        if val < 1 or val > 10:
            return False
    return True


def score_candidate(candidate: dict) -> dict:
    """Score a single candidate on 3 dimensions, return scores + weighted composite.

    Extracts flow, novelty, engagement from candidate["scores"], computes
    weighted composite using locked weights, returns dict with all 4 values.

    Args:
        candidate: dict with "scores" key containing flow, novelty, engagement

    Returns:
        dict with flow, novelty, engagement (integers) and weighted (float, 2 decimals)

    Raises:
        ValueError: If scores are missing or out of range [1, 10]
    """
    scores = candidate.get("scores", {})
    if not validate_scores(scores):
        raise ValueError(
            f"Invalid scores for candidate '{candidate.get('id', 'unknown')}': "
            f"flow, novelty, engagement must be integers in [1, 10]. "
            f"Got: {scores}"
        )

    flow = scores["flow"]
    novelty = scores["novelty"]
    engagement = scores["engagement"]

    weighted = round(
        flow * WEIGHT_FLOW + novelty * WEIGHT_NOVELTY + engagement * WEIGHT_ENGAGEMENT,
        2
    )

    return {
        "flow": flow,
        "novelty": novelty,
        "engagement": engagement,
        "weighted": weighted,
    }


def select_best(candidates: list) -> tuple:
    """Score all candidates and select the one with the highest weighted score.

    Tie-breaking: first candidate in the list wins (stable ordering).

    Args:
        candidates: list of candidate dicts, each with "id" and "scores" keys

    Returns:
        tuple of (best_id, scores_dict_for_all, rationale_string)
        - best_id: string ID of the winning candidate
        - scores_dict: dict mapping candidate IDs to their score dicts
        - rationale: string explaining why the winner was selected
    """
    if not candidates:
        raise ValueError("No candidates provided")

    scored = {}
    for c in candidates:
        cid = c["id"]
        scored[cid] = score_candidate(c)

    # Find best by weighted score (first candidate wins ties)
    best_id = max(scored, key=lambda cid: scored[cid]["weighted"])
    best_scores = scored[best_id]

    # Build rationale with dimension-level comparison
    others = {cid: s for cid, s in scored.items() if cid != best_id}
    comparison_parts = []
    for other_id, other_scores in others.items():
        advantages = []
        if best_scores["flow"] > other_scores["flow"]:
            advantages.append(f"flow ({best_scores['flow']} vs {other_scores['flow']})")
        if best_scores["novelty"] > other_scores["novelty"]:
            advantages.append(f"novelty ({best_scores['novelty']} vs {other_scores['novelty']})")
        if best_scores["engagement"] > other_scores["engagement"]:
            advantages.append(f"engagement ({best_scores['engagement']} vs {other_scores['engagement']})")

        if advantages:
            comparison_parts.append(
                f"Beats {other_id} on {', '.join(advantages)}"
            )
        else:
            comparison_parts.append(
                f"Ties or trails {other_id} on individual dimensions but wins on weighted composite"
            )

    rationale = (
        f"Selected {best_id} with weighted score {best_scores['weighted']} "
        f"(flow={best_scores['flow']}, novelty={best_scores['novelty']}, "
        f"engagement={best_scores['engagement']}). "
        + ". ".join(comparison_parts) + "."
    )

    return best_id, scored, rationale


def validate_candidate_structure(candidate: dict) -> list:
    """Validate that a candidate has all required fields.

    Args:
        candidate: dict representing a single candidate

    Returns:
        list of error message strings (empty if valid)
    """
    errors = []
    required_fields = ["id", "strategy", "rationale", "sections", "scores"]
    for field in required_fields:
        if field not in candidate:
            errors.append(f"Missing required field: {field}")

    if "strategy" in candidate:
        valid_strategies = {"problem-first", "insight-first", "evidence-first"}
        if candidate["strategy"] not in valid_strategies:
            errors.append(
                f"Invalid strategy '{candidate['strategy']}'. "
                f"Must be one of: {sorted(valid_strategies)}"
            )

    if "sections" in candidate:
        if not isinstance(candidate["sections"], list) or len(candidate["sections"]) == 0:
            errors.append("sections must be a non-empty list")

    if "scores" in candidate:
        scores = candidate["scores"]
        for dim in ("flow", "novelty", "engagement"):
            if dim not in scores:
                errors.append(f"Missing score dimension: {dim}")
            elif not isinstance(scores[dim], int):
                errors.append(f"Score '{dim}' must be an integer, got {type(scores[dim]).__name__}")
            elif scores[dim] < 1 or scores[dim] > 10:
                errors.append(f"Score '{dim}' must be 1-10, got {scores[dim]}")

    return errors


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    """Entry point: --self-test or input/output paths."""
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return

    if len(sys.argv) != 3:
        print("Usage:")
        print(f"  python3 {sys.argv[0]} <input_path> <output_path>")
        print(f"  python3 {sys.argv[0]} --self-test")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # Load input JSON
    with open(input_path) as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if len(candidates) != 3:
        print(f"ERROR: Expected exactly 3 candidates, got {len(candidates)}")
        sys.exit(1)

    # Validate each candidate
    all_errors = []
    for c in candidates:
        errors = validate_candidate_structure(c)
        if errors:
            all_errors.extend([f"  {c.get('id', '?')}: {e}" for e in errors])

    if all_errors:
        print("ERROR: Candidate validation failed:")
        for err in all_errors:
            print(err)
        sys.exit(1)

    # Score and select
    best_id, scores, rationale = select_best(candidates)

    # Build output
    output = {
        "scores": scores,
        "selected_candidate": best_id,
        "selection_rationale": rationale,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }

    atomic_write(output_path, json.dumps(output, indent=2) + "\n")

    print(f"Scoring complete: {best_id} selected")
    print(f"  Scores: {json.dumps(scores, indent=2)}")
    print(f"  Rationale: {rationale}")
    print(f"  Output: {output_path}")


# ---------------------------------------------------------------------------
# Self-test with embedded mock data
# ---------------------------------------------------------------------------

def self_test():
    """Run all self-test assertions with embedded mock data."""
    print("=== _outline_scorer self-test ===")
    print()

    # --- Test 1: Weights sum to 1.0 ---
    total = WEIGHT_FLOW + WEIGHT_NOVELTY + WEIGHT_ENGAGEMENT
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"
    print("[PASS] Weights sum to 1.0 (0.40 + 0.35 + 0.25)")

    # --- Test 2: score_candidate with known inputs ---
    candidate_a = {
        "id": "candidate_a",
        "scores": {"flow": 8, "novelty": 7, "engagement": 7}
    }
    result = score_candidate(candidate_a)
    assert result["flow"] == 8
    assert result["novelty"] == 7
    assert result["engagement"] == 7
    # 8*0.40 + 7*0.35 + 7*0.25 = 3.20 + 2.45 + 1.75 = 7.40
    assert result["weighted"] == 7.40, f"Expected 7.40, got {result['weighted']}"
    print("[PASS] score_candidate({flow:8, novelty:7, engagement:7}) -> weighted=7.40")

    # Additional known value check
    candidate_b = {
        "id": "candidate_b",
        "scores": {"flow": 7, "novelty": 8, "engagement": 8}
    }
    result_b = score_candidate(candidate_b)
    # 7*0.40 + 8*0.35 + 8*0.25 = 2.80 + 2.80 + 2.00 = 7.60
    assert result_b["weighted"] == 7.60, f"Expected 7.60, got {result_b['weighted']}"
    print("[PASS] score_candidate({flow:7, novelty:8, engagement:8}) -> weighted=7.60")

    # --- Test 3: select_best picks highest weighted score ---
    candidates = [
        {"id": "candidate_a", "scores": {"flow": 8, "novelty": 7, "engagement": 7}},
        {"id": "candidate_b", "scores": {"flow": 7, "novelty": 8, "engagement": 8}},
        {"id": "candidate_c", "scores": {"flow": 6, "novelty": 7, "engagement": 9}},
    ]
    best_id, scores, rationale = select_best(candidates)
    # candidate_a: 7.40, candidate_b: 7.60, candidate_c: 6*0.4+7*0.35+9*0.25 = 2.40+2.45+2.25 = 7.10
    assert best_id == "candidate_b", f"Expected candidate_b, got {best_id}"
    assert scores["candidate_b"]["weighted"] == 7.60
    assert scores["candidate_a"]["weighted"] == 7.40
    assert scores["candidate_c"]["weighted"] == 7.10
    assert "candidate_b" in rationale
    print("[PASS] select_best picks candidate_b (highest weighted=7.60)")

    # --- Test 4: Tie-breaking (first candidate wins) ---
    tied_candidates = [
        {"id": "first", "scores": {"flow": 5, "novelty": 5, "engagement": 5}},
        {"id": "second", "scores": {"flow": 5, "novelty": 5, "engagement": 5}},
        {"id": "third", "scores": {"flow": 5, "novelty": 5, "engagement": 5}},
    ]
    best_id_tie, _, _ = select_best(tied_candidates)
    assert best_id_tie == "first", f"Expected 'first' on tie, got {best_id_tie}"
    print("[PASS] Tie-breaking: first candidate wins on equal weighted scores")

    # --- Test 5: Invalid score range raises ValueError ---
    invalid_candidate = {
        "id": "bad",
        "scores": {"flow": 11, "novelty": 5, "engagement": 5}
    }
    try:
        score_candidate(invalid_candidate)
        assert False, "Should have raised ValueError for score > 10"
    except ValueError:
        pass
    print("[PASS] score_candidate raises ValueError for score > 10")

    # Test score < 1
    invalid_low = {
        "id": "bad_low",
        "scores": {"flow": 0, "novelty": 5, "engagement": 5}
    }
    try:
        score_candidate(invalid_low)
        assert False, "Should have raised ValueError for score < 1"
    except ValueError:
        pass
    print("[PASS] score_candidate raises ValueError for score < 1")

    # --- Test 6: validate_candidate_structure catches missing fields ---
    incomplete = {"id": "test", "strategy": "problem-first"}
    errors = validate_candidate_structure(incomplete)
    assert len(errors) >= 2, f"Expected >= 2 errors, got {len(errors)}: {errors}"
    missing_fields = [e for e in errors if "Missing required field" in e]
    assert len(missing_fields) >= 2, f"Expected >= 2 missing field errors: {errors}"
    print(f"[PASS] validate_candidate_structure catches {len(errors)} errors on incomplete candidate")

    # Invalid strategy
    bad_strategy = {
        "id": "test",
        "strategy": "random-order",
        "rationale": "test",
        "sections": [{"id": "intro"}],
        "scores": {"flow": 5, "novelty": 5, "engagement": 5}
    }
    errors = validate_candidate_structure(bad_strategy)
    strategy_errors = [e for e in errors if "Invalid strategy" in e]
    assert len(strategy_errors) == 1, f"Expected 1 strategy error: {errors}"
    print("[PASS] validate_candidate_structure catches invalid strategy")

    # --- Test 7: validate_scores edge cases ---
    assert validate_scores({"flow": 1, "novelty": 1, "engagement": 1}) is True
    assert validate_scores({"flow": 10, "novelty": 10, "engagement": 10}) is True
    assert validate_scores({"flow": 5, "novelty": 5, "engagement": 5}) is True
    assert validate_scores({"flow": 0, "novelty": 5, "engagement": 5}) is False
    assert validate_scores({"flow": 11, "novelty": 5, "engagement": 5}) is False
    assert validate_scores({"flow": 5.5, "novelty": 5, "engagement": 5}) is False
    assert validate_scores({"flow": 5}) is False
    print("[PASS] validate_scores boundary checks (1-10 integer range)")

    # --- Test 8: Full pipeline with mock data ---
    import tempfile
    tmpdir = tempfile.mkdtemp()
    input_path = os.path.join(tmpdir, "input.json")
    output_path = os.path.join(tmpdir, "output.json")

    mock_input = {
        "candidates": [
            {
                "id": "candidate_a",
                "strategy": "problem-first",
                "rationale": "Lead with the research gap",
                "sections": [{"id": "introduction", "title": "Introduction"}],
                "scores": {"flow": 8, "novelty": 7, "engagement": 7}
            },
            {
                "id": "candidate_b",
                "strategy": "insight-first",
                "rationale": "Lead with the novel observation",
                "sections": [{"id": "introduction", "title": "Introduction"}],
                "scores": {"flow": 7, "novelty": 8, "engagement": 8}
            },
            {
                "id": "candidate_c",
                "strategy": "evidence-first",
                "rationale": "Lead with surprising results",
                "sections": [{"id": "introduction", "title": "Introduction"}],
                "scores": {"flow": 6, "novelty": 7, "engagement": 9}
            },
        ]
    }

    with open(input_path, "w") as f:
        json.dump(mock_input, f)

    # Simulate main() pipeline manually
    with open(input_path) as f:
        data = json.load(f)

    candidates = data["candidates"]
    best_id, scores, rationale = select_best(candidates)
    output = {
        "scores": scores,
        "selected_candidate": best_id,
        "selection_rationale": rationale,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(output_path, json.dumps(output, indent=2) + "\n")

    with open(output_path) as f:
        written = json.load(f)

    assert written["selected_candidate"] == "candidate_b"
    assert written["scores"]["candidate_b"]["weighted"] == 7.60
    assert "scored_at" in written
    print("[PASS] Full pipeline writes correct output JSON")

    # Cleanup
    os.remove(input_path)
    os.remove(output_path)
    os.rmdir(tmpdir)

    print()
    print("=== All _outline_scorer tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
