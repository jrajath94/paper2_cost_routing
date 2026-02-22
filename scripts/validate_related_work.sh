#!/usr/bin/env bash
# validate_related_work.sh
# Validates paper/output/related_work_draft.md against Phase 6
# constraints: citation density, paper count, thematic structure.
#
# Usage: ./paper/scripts/validate_related_work.sh
# Exit code: 0 if all checks pass, 1 if any fail.
# Dependencies: grep, wc (standard on macOS)

set -euo pipefail

FILE="paper/output/related_work_draft.md"
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

echo "=== Related Work Draft Validation ==="
echo ""

# 1. File exists and is non-empty
if [ ! -f "$FILE" ]; then
  echo "[FAIL] File exists: $FILE not found"
  echo ""
  echo "=== RESULT: FAILED (file missing) ==="
  exit 1
fi
check "File exists" "true"

FILE_SIZE=$(wc -c < "$FILE" | tr -d ' ')
result=$( [ "$FILE_SIZE" -gt 0 ] && echo "true" || echo "false" )
check "File is non-empty (size: ${FILE_SIZE} bytes)" "$result"

# 2. Word count >= 1200 (within -20% of 1500 target)
WORD_COUNT=$(wc -w < "$FILE" | tr -d ' ')
result=$( [ "$WORD_COUNT" -ge 1200 ] && echo "true" || echo "false" )
check "Word count >= 1200 (found: $WORD_COUNT)" "$result"

# 3. Unique citation keys >= 15 (CONTEXT.md target: 15-25 unique citations)
# Match patterns like \cite{key}, \citep{key}, \citet{key}, \cite{key1,key2}
CITE_COUNT=$(grep -oE '\\cite[pt]?\{[^}]+\}' "$FILE" 2>/dev/null | wc -l | tr -d ' ')
# Count unique citation keys (splitting comma-separated)
UNIQUE_KEYS=$(grep -oE '\\cite[pt]?\{[^}]+\}' "$FILE" 2>/dev/null | \
  grep -oE '\{[^}]+\}' | tr -d '{}' | tr ',' '\n' | \
  sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort -u | wc -l | tr -d ' ')
result=$( [ "$UNIQUE_KEYS" -ge 15 ] && echo "true" || echo "false" )
check "Unique citation keys >= 15 (found: $UNIQUE_KEYS unique keys, $CITE_COUNT cite commands)" "$result"

# 4. Has at least 3 thematic cluster headings (lines starting with ## or ###)
HEADING_COUNT=$(grep -cE '^#{2,3} ' "$FILE" 2>/dev/null || echo "0")
result=$( [ "$HEADING_COUNT" -ge 3 ] && echo "true" || echo "false" )
check "At least 3 thematic cluster headings (found: $HEADING_COUNT)" "$result"

# 5. No "In recent years" opening (banned pattern from section-writer)
BANNED_COUNT=$(grep -ci 'In recent years' "$FILE" 2>/dev/null; echo $?)
# grep -c exits 1 when no matches, which is what we want (0 matches = good)
BANNED_COUNT=$(grep -ci 'In recent years' "$FILE" 2>/dev/null || true)
BANNED_COUNT=$(echo "$BANNED_COUNT" | tr -d '[:space:]')
result=$( [ "$BANNED_COUNT" = "0" ] || [ -z "$BANNED_COUNT" ] && echo "true" || echo "false" )
check "No 'In recent years' banned pattern (found: $BANNED_COUNT)" "$result"

# Summary
echo ""
echo "=== Summary ==="
echo "Word count: $WORD_COUNT"
echo "Citation commands: $CITE_COUNT"
echo "Unique citation keys: $UNIQUE_KEYS"
echo "Cluster headings: $HEADING_COUNT"
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
