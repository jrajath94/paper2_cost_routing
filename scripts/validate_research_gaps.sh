#!/usr/bin/env bash
# validate_research_gaps.sh
# Validates paper/output/research_gaps.json against schema requirements
# and Phase 5 constraints.
#
# Usage: ./paper/scripts/validate_research_gaps.sh
# Exit code: 0 if all checks pass, 1 if any fail.
# Dependencies: jq (standard on macOS)

set -euo pipefail

FILE="paper/output/research_gaps.json"
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

echo "=== Research Gaps Validation ==="
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
for field in topic gaps generated_at; do
  result=$(jq --arg f "$field" 'has($f)' "$FILE")
  check "Required field: $field" "$result"
done

# 4. Gaps array minimum (>= 3, locked constraint)
GAP_COUNT=$(jq '.gaps | length' "$FILE")
result=$(jq '.gaps | length >= 3' "$FILE")
check "Gaps array >= 3 (found: $GAP_COUNT)" "$result"

# 5. Each gap has required fields (sample first 3)
SAMPLE_SIZE=$(jq '[.gaps | length, 3] | min' "$FILE")
REQUIRED_GAP_FIELDS='["gap_id","description","novelty_score","evidence"]'
MISSING=$(jq --argjson req "$REQUIRED_GAP_FIELDS" \
  '[.gaps[:3][] | . as $g | $req[] | select($g[.] == null)] | length' "$FILE")
if [ "$MISSING" = "0" ]; then
  result="true"
else
  result="false"
fi
check "Required fields in first $SAMPLE_SIZE gaps (missing: $MISSING)" "$result"

# 6. Evidence minimum per gap (>= 3 items each)
LOW_EVIDENCE=$(jq '[.gaps[] | select((.evidence | length) < 3)] | length' "$FILE")
result=$(jq '[.gaps[] | select((.evidence | length) < 3)] | length == 0' "$FILE")
check "Evidence >= 3 per gap (violations: $LOW_EVIDENCE)" "$result"

# 7. Novelty scores in range 1-10
OUT_OF_RANGE=$(jq '[.gaps[] | select(.novelty_score < 1 or .novelty_score > 10)] | length' "$FILE")
result=$(jq '[.gaps[] | select(.novelty_score < 1 or .novelty_score > 10)] | length == 0' "$FILE")
check "Novelty scores in range 1-10 (out of range: $OUT_OF_RANGE)" "$result"

# 8. Feasibility present for scored gaps (novelty_score > 5.0)
HIGH_NOVELTY=$(jq '[.gaps[] | select(.novelty_score > 5.0)] | length' "$FILE")
MISSING_FEAS=$(jq '[.gaps[] | select(.novelty_score > 5.0) | select(.feasibility == null or (.feasibility | has("score") | not))] | length' "$FILE")
if [ "$HIGH_NOVELTY" = "0" ]; then
  # No high-novelty gaps, trivially passes
  result="true"
else
  result=$(jq '[.gaps[] | select(.novelty_score > 5.0) | select(.feasibility == null or (.feasibility | has("score") | not))] | length == 0' "$FILE")
fi
check "Feasibility present for high-novelty gaps ($HIGH_NOVELTY with score > 5.0, missing: $MISSING_FEAS)" "$result"

# 9. Confidence values valid (HIGH, MEDIUM, LOW)
INVALID_CONF=$(jq '[.gaps[] | select(.confidence != null) | select(.confidence != "HIGH" and .confidence != "MEDIUM" and .confidence != "LOW")] | length' "$FILE")
result=$(jq '[.gaps[] | select(.confidence != null) | select(.confidence != "HIGH" and .confidence != "MEDIUM" and .confidence != "LOW")] | length == 0' "$FILE")
check "Confidence values valid (invalid: $INVALID_CONF)" "$result"

# 10. Analysis metadata present
result=$(jq 'has("analysis_metadata") and (.analysis_metadata | has("papers_analyzed")) and (.analysis_metadata | has("clusters_identified"))' "$FILE")
check "Analysis metadata with papers_analyzed and clusters_identified" "$result"

# 11. Gap IDs unique
TOTAL_IDS=$(jq '[.gaps[].gap_id] | length' "$FILE")
UNIQUE_IDS=$(jq '[.gaps[].gap_id] | unique | length' "$FILE")
if [ "$TOTAL_IDS" = "$UNIQUE_IDS" ]; then
  result="true"
else
  result="false"
fi
check "Gap IDs unique ($UNIQUE_IDS unique of $TOTAL_IDS total)" "$result"

# Summary
echo ""
echo "=== Summary ==="
echo "Total gaps: $GAP_COUNT"
HIGHEST_NOVELTY=$(jq '[.gaps[].novelty_score] | max' "$FILE")
echo "Highest novelty score: $HIGHEST_NOVELTY"
RECOMMENDED=$(jq -r '.gaps[0].gap_id // "none"' "$FILE")
RECOMMENDED_DESC=$(jq -r '.gaps[0].description // "N/A" | .[0:80]' "$FILE")
echo "Recommended gap: $RECOMMENDED -- $RECOMMENDED_DESC"
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
