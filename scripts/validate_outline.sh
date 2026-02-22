#!/usr/bin/env bash
# validate_outline.sh
# Validates paper/output/paper_outline.json against schema requirements
# and Phase 6 constraints (ToT-lite outline with 3 candidates).
#
# Usage: ./paper/scripts/validate_outline.sh
# Exit code: 0 if all checks pass, 1 if any fail.
# Dependencies: jq (standard on macOS)

set -euo pipefail

FILE="paper/output/paper_outline.json"
PASS=0
FAIL=0

check() {
  local label="$1"
  local result="$2"
  if [ "$result" = "true" ]; then
    echo "[PASS] $label"
    PASS=$((PASS + 1))
  else
    echo "[FAIL] $label"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Paper Outline Validation ==="
echo ""

# 1. File exists
if [ ! -f "$FILE" ]; then
  echo "[FAIL] File exists: $FILE not found"
  echo ""
  echo "=== RESULT: FAILED (file missing) ==="
  exit 1
fi
check "File exists" "true"

# 2. Valid JSON
if jq . "$FILE" > /dev/null 2>&1; then
  check "Valid JSON" "true"
else
  echo "[FAIL] Valid JSON: $FILE is not valid JSON"
  echo ""
  echo "=== RESULT: FAILED (invalid JSON) ==="
  exit 1
fi

# 3. Required top-level fields
for field in paper_type agent_ensemble candidates scores selected_candidate selection_rationale sections figure_plan total_word_count venue generated_at; do
  result=$(jq --arg f "$field" 'has($f)' "$FILE")
  check "Required field: $field" "$result"
done

# 4. Exactly 3 candidates
CANDIDATE_COUNT=$(jq '.candidates | length' "$FILE")
result=$(jq '.candidates | length == 3' "$FILE")
check "Exactly 3 candidates (found: $CANDIDATE_COUNT)" "$result"

# 5. Each candidate has required fields: id, strategy, rationale, sections
REQUIRED_CAND_FIELDS='["id","strategy","rationale","sections"]'
for idx in 0 1 2; do
  MISSING=$(jq --argjson req "$REQUIRED_CAND_FIELDS" \
    --argjson idx "$idx" \
    '[.candidates[$idx] | . as $c | $req[] | select($c[.] == null)] | length' "$FILE")
  result=$( [ "$MISSING" = "0" ] && echo "true" || echo "false" )
  CID=$(jq -r --argjson idx "$idx" '.candidates[$idx].id // "unknown"' "$FILE")
  check "Candidate $idx ($CID) has required fields (missing: $MISSING)" "$result"
done

# 6. Strategy values are valid enum
VALID_STRATEGIES='["problem-first","insight-first","evidence-first"]'
INVALID_STRAT=$(jq --argjson valid "$VALID_STRATEGIES" \
  '[.candidates[].strategy | select(. as $s | $valid | index($s) == null)] | length' "$FILE")
result=$( [ "$INVALID_STRAT" = "0" ] && echo "true" || echo "false" )
check "Strategy values are valid enum (invalid: $INVALID_STRAT)" "$result"

# 7. All 3 candidates have all required sections from empirical template
REQUIRED_SECTIONS='["introduction","related_work","methods","experiments","results","discussion","conclusion"]'
for idx in 0 1 2; do
  MISSING_SECS=$(jq --argjson req "$REQUIRED_SECTIONS" \
    --argjson idx "$idx" \
    '[.candidates[$idx].sections[].id] as $ids | [$req[] | select(. as $r | $ids | index($r) == null)] | length' "$FILE")
  CID=$(jq -r --argjson idx "$idx" '.candidates[$idx].id // "unknown"' "$FILE")
  result=$( [ "$MISSING_SECS" = "0" ] && echo "true" || echo "false" )
  check "Candidate $idx ($CID) has all 7 required sections (missing: $MISSING_SECS)" "$result"
done

# 8. Scores exist for all 3 candidates with flow/novelty/engagement in range 1-10
for cand in candidate_a candidate_b candidate_c; do
  HAS_SCORES=$(jq --arg c "$cand" '.scores | has($c)' "$FILE")
  check "Scores exist for $cand" "$HAS_SCORES"

  if [ "$HAS_SCORES" = "true" ]; then
    for dim in flow novelty engagement; do
      VAL=$(jq --arg c "$cand" --arg d "$dim" '.scores[$c][$d]' "$FILE")
      IN_RANGE=$(jq --arg c "$cand" --arg d "$dim" \
        '.scores[$c][$d] >= 1 and .scores[$c][$d] <= 10' "$FILE")
      check "Score $cand.$dim in range 1-10 (value: $VAL)" "$IN_RANGE"
    done
  fi
done

# 9. selected_candidate matches one of the candidate IDs
SELECTED=$(jq -r '.selected_candidate' "$FILE")
MATCH=$(jq '[.candidates[].id] | index(.selected_candidate) != null' "$FILE" 2>/dev/null || echo "false")
# More robust check
MATCH=$(jq --arg sel "$SELECTED" '[.candidates[].id] as $ids | $ids | index($sel) != null' "$FILE")
check "selected_candidate '$SELECTED' matches a candidate ID" "$MATCH"

# 10. Top-level sections array is non-empty
SEC_COUNT=$(jq '.sections | length' "$FILE")
result=$(jq '.sections | length > 0' "$FILE")
check "Top-level sections array is non-empty (count: $SEC_COUNT)" "$result"

# 11. Each top-level section has agent, word_count_target, citation_density
MISSING_SEC_FIELDS=$(jq '[.sections[] | select(.agent == null or .word_count_target == null or .citation_density == null)] | length' "$FILE")
result=$( [ "$MISSING_SEC_FIELDS" = "0" ] && echo "true" || echo "false" )
check "Each section has agent, word_count_target, citation_density (missing: $MISSING_SEC_FIELDS)" "$result"

# 12. total_word_count is positive integer
TOTAL_WC=$(jq '.total_word_count' "$FILE")
result=$(jq '.total_word_count > 0' "$FILE")
check "total_word_count is positive (value: $TOTAL_WC)" "$result"

# Summary
echo ""
echo "=== Summary ==="
echo "Section count: $SEC_COUNT"
echo "Total word count: $TOTAL_WC"
SELECTED_STRATEGY=$(jq -r --arg sel "$SELECTED" '.candidates[] | select(.id == $sel) | .strategy' "$FILE")
echo "Selected strategy: $SELECTED_STRATEGY"
echo "Checks passed: $PASS"
echo "Checks failed: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "=== RESULT: ALL CHECKS PASSED ==="
  exit 0
else
  echo "=== RESULT: $FAIL CHECK(S) FAILED ==="
  exit 1
fi
