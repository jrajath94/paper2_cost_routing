#!/usr/bin/env bash
# validate_literature_map.sh
# Validates paper/output/literature_map.json against schema requirements
# and CONTEXT.md coverage thresholds.
#
# Usage: ./paper/scripts/validate_literature_map.sh
# Exit code: 0 if all checks pass, 1 if any fail.
# Dependencies: jq (standard on macOS)

set -euo pipefail

FILE="paper/output/literature_map.json"
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

echo "=== Literature Map Validation ==="
echo ""

# 1. File exists and is valid JSON
if [ ! -f "$FILE" ]; then
  echo "[FAIL] File exists: $FILE not found"
  echo ""
  echo "=== RESULT: FAILED (file missing) ==="
  exit 1
fi

if jq . "$FILE" > /dev/null 2>&1; then
  check "Valid JSON" "true"
else
  echo "[FAIL] Valid JSON: $FILE is not valid JSON"
  echo ""
  echo "=== RESULT: FAILED (invalid JSON) ==="
  exit 1
fi

# 2. Required top-level fields
for field in topic papers generated_at total_papers; do
  result=$(jq --arg f "$field" 'has($f)' "$FILE")
  check "Required field: $field" "$result"
done

result=$(jq 'has("search_metadata") and (.search_metadata | has("databases_searched"))' "$FILE")
check "Required field: search_metadata.databases_searched" "$result"

# 3. Total papers >= 50
TOTAL=$(jq '.total_papers' "$FILE")
result=$(jq '.total_papers >= 50' "$FILE")
check "Total papers >= 50 (found: $TOTAL)" "$result"

# 4. Recency: 40%+ from 2023-2026
TOTAL_COUNT=$(jq '.papers | length' "$FILE")
RECENT_COUNT=$(jq '[.papers[] | select(.year >= 2023)] | length' "$FILE")
if [ "$TOTAL_COUNT" -gt 0 ]; then
  RECENCY_PCT=$(python3 -c "print(f'{$RECENT_COUNT / $TOTAL_COUNT * 100:.1f}')")
  result=$(jq '[.papers[] | select(.year >= 2023)] | length as $recent | ($recent / (.papers | length)) >= 0.4' "$FILE")
else
  RECENCY_PCT="0.0"
  result="false"
fi
check "Recency >= 40% from 2023-2026 ($RECENT_COUNT/$TOTAL_COUNT = ${RECENCY_PCT}%)" "$result"

# 5. All 3 databases searched
DB_COUNT=$(jq '.search_metadata.databases_searched | length' "$FILE")
result=$(jq '.search_metadata.databases_searched | length >= 3' "$FILE")
check "Databases searched >= 3 (found: $DB_COUNT)" "$result"

# 6. Required fields per paper (sample first 5)
SAMPLE_SIZE=$(jq '[.papers | length, 5] | min' "$FILE")
REQUIRED_FIELDS='["id","title","authors","year","venue","contribution","relevance_score"]'
MISSING=$(jq --argjson req "$REQUIRED_FIELDS" \
  '[.papers[:5][] | . as $p | $req[] | select($p[.] == null)] | length' "$FILE")
if [ "$MISSING" = "0" ]; then
  result="true"
else
  result="false"
fi
check "Required fields present in first $SAMPLE_SIZE papers (missing: $MISSING)" "$result"

# 7. No paper has relevance_score < 3.0
LOW_SCORE_COUNT=$(jq '[.papers[] | select(.relevance_score < 3.0)] | length' "$FILE")
result=$(jq '[.papers[] | select(.relevance_score < 3.0)] | length == 0' "$FILE")
check "All papers relevance_score >= 3.0 (below threshold: $LOW_SCORE_COUNT)" "$result"

# 8. Clusters array exists with >= 3 entries
if jq -e '.clusters' "$FILE" > /dev/null 2>&1; then
  CLUSTER_COUNT=$(jq '.clusters | length' "$FILE")
  result=$(jq '.clusters | length >= 3' "$FILE")
  check "Clusters >= 3 (found: $CLUSTER_COUNT)" "$result"
else
  check "Clusters array exists" "false"
fi

# Summary
echo ""
echo "=== Summary ==="
echo "Total papers: $TOTAL"
echo "Recency: ${RECENCY_PCT}% from 2023-2026"
echo "Databases: $DB_COUNT"
echo "Clusters: ${CLUSTER_COUNT:-0}"
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
