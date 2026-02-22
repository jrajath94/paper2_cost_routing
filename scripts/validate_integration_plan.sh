#!/usr/bin/env bash
# validate_integration_plan.sh
# Validates paper/output/integration_plan.json against schema requirements
# and Phase 6 constraints (terminology, narrative arc, section map).
#
# Usage: ./paper/scripts/validate_integration_plan.sh
# Exit code: 0 if all checks pass, 1 if any fail.
# Dependencies: jq (standard on macOS)

set -euo pipefail

FILE="paper/output/integration_plan.json"
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

echo "=== Integration Plan Validation ==="
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
for field in terminology narrative_arc section_map cross_section_constraints abstract_status neurips_checklist_slots generated_at; do
  result=$(jq --arg f "$field" 'has($f)' "$FILE")
  check "Required field: $field" "$result"
done

# 4. narrative_arc has all 6 required keys
REQUIRED_ARC='["problem","gap","insight","method","evidence","implication"]'
MISSING_ARC=$(jq --argjson req "$REQUIRED_ARC" \
  '. as $root | [$req[] | select(. as $k | $root.narrative_arc | has($k) | not)] | length' "$FILE")
result=$( [ "$MISSING_ARC" = "0" ] && echo "true" || echo "false" )
check "narrative_arc has all 6 keys (missing: $MISSING_ARC)" "$result"

# 5. section_map is non-empty array
SECTION_COUNT=$(jq '.section_map | length' "$FILE")
result=$(jq '.section_map | length > 0' "$FILE")
check "section_map is non-empty array (count: $SECTION_COUNT)" "$result"

# 6. Each section_map entry has required fields
REQUIRED_SM_FIELDS='["section_id","agent","citation_density_target","word_count_target","narrative_role"]'
MISSING_SM=$(jq --argjson req "$REQUIRED_SM_FIELDS" \
  '[.section_map[] | . as $entry | $req[] | . as $field | select($entry[$field] == null)] | length' "$FILE")
result=$( [ "$MISSING_SM" = "0" ] && echo "true" || echo "false" )
check "Each section_map entry has required fields (missing: $MISSING_SM)" "$result"

# 7. abstract_status is "deferred_to_post_draft"
ABSTRACT_STATUS=$(jq -r '.abstract_status' "$FILE")
result=$( [ "$ABSTRACT_STATUS" = "deferred_to_post_draft" ] && echo "true" || echo "false" )
check "abstract_status is 'deferred_to_post_draft' (got: $ABSTRACT_STATUS)" "$result"

# 8. neurips_checklist_slots has at least: limitations, broader_impact, reproducibility
for slot in limitations broader_impact reproducibility; do
  result=$(jq --arg s "$slot" '.neurips_checklist_slots | has($s)' "$FILE")
  check "neurips_checklist_slots has '$slot'" "$result"
done

# 9. terminology has at least 3 entries (our_method + at least 2 key concepts)
TERM_COUNT=$(jq '.terminology | keys | length' "$FILE")
result=$(jq '.terminology | keys | length >= 3' "$FILE")
check "terminology has >= 3 entries (found: $TERM_COUNT)" "$result"

# 10. cross_section_constraints is non-empty array
CONSTRAINT_COUNT=$(jq '.cross_section_constraints | length' "$FILE")
result=$(jq '.cross_section_constraints | length > 0' "$FILE")
check "cross_section_constraints is non-empty (count: $CONSTRAINT_COUNT)" "$result"

# Summary
echo ""
echo "=== Summary ==="
echo "Terminology count: $TERM_COUNT"
echo "Section map count: $SECTION_COUNT"
CHECKLIST_COUNT=$(jq '.neurips_checklist_slots | keys | length' "$FILE")
echo "Checklist slot count: $CHECKLIST_COUNT"
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
