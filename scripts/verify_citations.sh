#!/usr/bin/env bash
# verify_citations.sh
# Main orchestration script for three-pass citation verification.
#
# Runs CrossRef, Semantic Scholar, and OpenAlex verification for each
# citation in literature_map.json, then adjudicates results, generates
# paper/output/verified_citations.json, bibliography.bib, and citation_report.md.
#
# Usage:
#   ./paper/scripts/verify_citations.sh              # Full verification
#   ./paper/scripts/verify_citations.sh --dry-run     # Check prereqs + 1 test citation
#   ./paper/scripts/verify_citations.sh --test-fabrication  # Run fabrication detection test
#
# Exit code: 0 if all pass, 1 if any citation fails verification.
# Dependencies: python3, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIT_MAP="$PROJECT_ROOT/paper/output/literature_map.json"
PASS_RESULTS_DIR="$PROJECT_ROOT/paper/output/_pass_results"
VERIFIED_OUTPUT="$PROJECT_ROOT/paper/output/verified_citations.json"
BIB_OUTPUT="$PROJECT_ROOT/paper/output/bibliography.bib"
REPORT_OUTPUT="$PROJECT_ROOT/paper/output/citation_report.md"
PASS=0
FAIL=0
MODE="full"

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --test-fabrication)
      MODE="test-fabrication"
      shift
      ;;
    *)
      echo "Unknown flag: $1" >&2
      echo "Usage: $0 [--dry-run | --test-fabrication]"
      exit 1
      ;;
  esac
done

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

echo "=== Citation Verification Pipeline ==="
echo "Mode: $MODE"
echo ""

# -----------------------------------------------------------------------
# Step 0: Check prerequisites
# -----------------------------------------------------------------------
echo "--- Step 0: Prerequisites ---"

# Python scripts exist and are syntactically valid
for script in _shared_utils.py _verify_crossref.py _verify_semantic_scholar.py _verify_openalex.py _adjudicate_citations.py _generate_bibtex.py _generate_citation_report.py; do
  if [ -f "$SCRIPT_DIR/$script" ]; then
    if python3 -c "import py_compile; py_compile.compile('$SCRIPT_DIR/$script', doraise=True)" 2>/dev/null; then
      check "Script valid: $script" "true"
    else
      check "Script valid: $script" "false"
    fi
  else
    check "Script exists: $script" "false"
  fi
done

# Check .env for API keys
ENV_FILE="$PROJECT_ROOT/.env"
S2_KEY_OK="false"
OA_KEY_OK="false"

if [ -f "$ENV_FILE" ]; then
  if grep -q "^S2_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    S2_VAL=$(grep "^S2_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$S2_VAL" ] && [ "$S2_VAL" != "your_key_here" ]; then
      S2_KEY_OK="true"
    fi
  fi
  if grep -q "^OPENALEX_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    OA_VAL=$(grep "^OPENALEX_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$OA_VAL" ] && [ "$OA_VAL" != "your_key_here" ]; then
      OA_KEY_OK="true"
    fi
  fi
fi
CM_KEY_OK="false"
if [ -f "$ENV_FILE" ]; then
  if grep -q "^CROSSREF_MAILTO=" "$ENV_FILE" 2>/dev/null; then
    CM_VAL=$(grep "^CROSSREF_MAILTO=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$CM_VAL" ]; then
      CM_KEY_OK="true"
    fi
  fi
fi
check "S2_API_KEY in .env" "$S2_KEY_OK"
check "OPENALEX_API_KEY in .env" "$OA_KEY_OK"
check "CROSSREF_MAILTO in .env (optional, default fallback)" "$CM_KEY_OK"

# Check literature_map.json
if [ "$MODE" = "full" ]; then
  if [ -f "$LIT_MAP" ]; then
    check "literature_map.json exists" "true"
    PAPER_COUNT=$(jq '.papers | length' "$LIT_MAP" 2>/dev/null || echo "0")
    check "literature_map has papers (found: $PAPER_COUNT)" "$([ "$PAPER_COUNT" -gt 0 ] && echo true || echo false)"
  else
    check "literature_map.json exists" "false"
  fi
fi

echo ""

# -----------------------------------------------------------------------
# Dry-run: only run prereq check + test 1 citation via CrossRef
# -----------------------------------------------------------------------
if [ "$MODE" = "dry-run" ]; then
  echo "--- Dry Run: Testing CrossRef with known paper ---"
  echo ""
  TEST_RESULT=$(python3 "$SCRIPT_DIR/_verify_crossref.py" --test "Attention Is All You Need" 2>&1) || true
  TEST_STATUS=$(echo "$TEST_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "error")

  if [ "$TEST_STATUS" = "matched" ]; then
    check "CrossRef test: Attention Is All You Need" "true"
    echo ""
    echo "CrossRef response:"
    echo "$TEST_RESULT" | python3 -m json.tool 2>/dev/null || echo "$TEST_RESULT"
  else
    check "CrossRef test: Attention Is All You Need" "false"
    echo "$TEST_RESULT"
  fi

  echo ""
  echo "--- Dry Run: Adjudication unit tests ---"
  python3 "$SCRIPT_DIR/_adjudicate_citations.py" --test-adjudicate

  echo ""
  echo "--- Dry Run: BibTeX + Report import check ---"
  if python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); from _generate_bibtex import generate_bibliography; print('OK')" 2>/dev/null; then
    check "Import _generate_bibtex" "true"
  else
    check "Import _generate_bibtex" "false"
  fi
  if python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); from _generate_citation_report import generate_report; print('OK')" 2>/dev/null; then
    check "Import _generate_citation_report" "true"
  else
    check "Import _generate_citation_report" "false"
  fi

  echo ""
  echo "=== Dry Run Summary ==="
  echo "Checks passed: $PASS"
  echo "Checks failed: $FAIL"
  if [ "$FAIL" -eq 0 ]; then
    echo "=== DRY RUN: ALL PREREQUISITES OK ==="
    exit 0
  else
    echo "=== DRY RUN: $FAIL PREREQUISITE(S) FAILED ==="
    exit 1
  fi
fi

# -----------------------------------------------------------------------
# Test fabrication: run 1 fabricated citation through all 3 passes
# -----------------------------------------------------------------------
if [ "$MODE" = "test-fabrication" ]; then
  echo "--- Fabrication Detection Test ---"
  echo ""
  echo "Testing with fabricated citation:"
  echo "  Title:  Quantum Neural Transformers for Recursive Self-Improvement"
  echo "  Author: Bengio, Y."
  echo "  Year:   2024"
  echo ""

  FAKE_JSON='{"title":"Quantum Neural Transformers for Recursive Self-Improvement","authors":["Bengio, Y."],"year":2024}'
  mkdir -p "$PASS_RESULTS_DIR"

  # Run 3 passes
  echo "Running CrossRef pass..."
  python3 "$SCRIPT_DIR/_verify_crossref.py" --json "$FAKE_JSON" > "$PASS_RESULTS_DIR/FAKE_crossref.json" 2>/dev/null || true
  CR_STATUS=$(python3 -c "import json; d=json.load(open('$PASS_RESULTS_DIR/FAKE_crossref.json')); print(d['status'])" 2>/dev/null || echo "error")
  echo "  CrossRef: $CR_STATUS"

  echo "Running Semantic Scholar pass..."
  python3 "$SCRIPT_DIR/_verify_semantic_scholar.py" --json "$FAKE_JSON" > "$PASS_RESULTS_DIR/FAKE_semantic_scholar.json" 2>/dev/null || true
  S2_STATUS=$(python3 -c "import json; d=json.load(open('$PASS_RESULTS_DIR/FAKE_semantic_scholar.json')); print(d['status'])" 2>/dev/null || echo "error")
  echo "  Semantic Scholar: $S2_STATUS"

  echo "Running OpenAlex pass..."
  python3 "$SCRIPT_DIR/_verify_openalex.py" --json "$FAKE_JSON" > "$PASS_RESULTS_DIR/FAKE_openalex.json" 2>/dev/null || true
  OA_STATUS=$(python3 -c "import json; d=json.load(open('$PASS_RESULTS_DIR/FAKE_openalex.json')); print(d['status'])" 2>/dev/null || echo "error")
  echo "  OpenAlex: $OA_STATUS"

  echo ""
  echo "Adjudicating..."
  PASSES_JSON=$(python3 -c "
import json, sys
passes = []
for src in ['crossref', 'semantic_scholar', 'openalex']:
    try:
        with open('$PASS_RESULTS_DIR/FAKE_' + src + '.json') as f:
            passes.append(json.load(f))
    except:
        passes.append({'status': 'error', 'source': src})
sys.path.insert(0, '$SCRIPT_DIR')
from _adjudicate_citations import adjudicate_with_flags
status, flags = adjudicate_with_flags(passes)
print(json.dumps({'status': status, 'flags': flags}))
")

  FAB_STATUS=$(echo "$PASSES_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])")
  FAB_FLAGS=$(echo "$PASSES_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d['flags']))")

  echo ""
  echo "Result: status=$FAB_STATUS flags=[$FAB_FLAGS]"

  if [ "$FAB_STATUS" = "failed" ]; then
    check "Fabricated citation detected as failed" "true"
    echo ""
    echo "CRITICAL: Fabricated citation correctly identified"
    echo ""

    # Check for suspected_fabrication flag
    if echo "$FAB_FLAGS" | grep -q "suspected_fabrication"; then
      check "suspected_fabrication flag present" "true"
    else
      check "suspected_fabrication flag present" "false"
    fi
  else
    check "Fabricated citation detected as failed" "false"
    echo ""
    echo "WARNING: Fabricated citation was NOT detected (status=$FAB_STATUS)"
  fi

  # Clean up
  rm -f "$PASS_RESULTS_DIR/FAKE_"*.json
  rmdir "$PASS_RESULTS_DIR" 2>/dev/null || true

  echo ""
  echo "=== Fabrication Test Summary ==="
  echo "Checks passed: $PASS"
  echo "Checks failed: $FAIL"
  if [ "$FAIL" -eq 0 ]; then
    echo "=== FABRICATION TEST: PASSED ==="
    exit 0
  else
    echo "=== FABRICATION TEST: FAILED ==="
    exit 1
  fi
fi

# -----------------------------------------------------------------------
# Full verification: Steps 1-6
# -----------------------------------------------------------------------

# Step 1: Load citations
echo "--- Step 1: Loading citations from literature_map.json ---"
if [ ! -f "$LIT_MAP" ]; then
  echo "[FATAL] literature_map.json not found at: $LIT_MAP"
  exit 1
fi

PAPER_COUNT=$(jq '.papers | length' "$LIT_MAP")
echo "Found $PAPER_COUNT papers to verify"
echo ""

# Step 2: Run 3 passes per citation
echo "--- Step 2: Running verification passes ---"
mkdir -p "$PASS_RESULTS_DIR"

PAPER_IDS=$(jq -r '.papers[].id' "$LIT_MAP")
CURRENT=0

while IFS= read -r PAPER_ID; do
  CURRENT=$((CURRENT + 1))
  TITLE=$(jq -r --arg id "$PAPER_ID" '.papers[] | select(.id == $id) | .title' "$LIT_MAP")
  AUTHORS_JSON=$(jq -c --arg id "$PAPER_ID" '.papers[] | select(.id == $id) | .authors' "$LIT_MAP")
  YEAR=$(jq -r --arg id "$PAPER_ID" '.papers[] | select(.id == $id) | .year' "$LIT_MAP")
  VENUE=$(jq -r --arg id "$PAPER_ID" '.papers[] | select(.id == $id) | .venue // ""' "$LIT_MAP")

  CITE_JSON=$(jq -n --arg t "$TITLE" --argjson a "$AUTHORS_JSON" --argjson y "$YEAR" --arg v "$VENUE" \
    '{title: $t, authors: $a, year: $y, venue: $v}')

  echo "[$CURRENT/$PAPER_COUNT] $TITLE"

  # CrossRef pass
  python3 "$SCRIPT_DIR/_verify_crossref.py" --json "$CITE_JSON" > "$PASS_RESULTS_DIR/${PAPER_ID}_crossref.json" 2>/dev/null || \
    echo '{"source":"crossref","status":"error","matched_fields":[],"mismatched_fields":[],"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' > "$PASS_RESULTS_DIR/${PAPER_ID}_crossref.json"
  CR_S=$(python3 -c "import json; print(json.load(open('$PASS_RESULTS_DIR/${PAPER_ID}_crossref.json'))['status'])" 2>/dev/null || echo "error")

  # Semantic Scholar pass
  python3 "$SCRIPT_DIR/_verify_semantic_scholar.py" --json "$CITE_JSON" > "$PASS_RESULTS_DIR/${PAPER_ID}_semantic_scholar.json" 2>/dev/null || \
    echo '{"source":"semantic_scholar","status":"error","matched_fields":[],"mismatched_fields":[],"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' > "$PASS_RESULTS_DIR/${PAPER_ID}_semantic_scholar.json"
  S2_S=$(python3 -c "import json; print(json.load(open('$PASS_RESULTS_DIR/${PAPER_ID}_semantic_scholar.json'))['status'])" 2>/dev/null || echo "error")

  # OpenAlex pass
  python3 "$SCRIPT_DIR/_verify_openalex.py" --json "$CITE_JSON" > "$PASS_RESULTS_DIR/${PAPER_ID}_openalex.json" 2>/dev/null || \
    echo '{"source":"openalex","status":"error","matched_fields":[],"mismatched_fields":[],"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' > "$PASS_RESULTS_DIR/${PAPER_ID}_openalex.json"
  OA_S=$(python3 -c "import json; print(json.load(open('$PASS_RESULTS_DIR/${PAPER_ID}_openalex.json'))['status'])" 2>/dev/null || echo "error")

  echo "  CrossRef=$CR_S  S2=$S2_S  OpenAlex=$OA_S"

done <<< "$PAPER_IDS"

echo ""

# Step 3: Adjudication
echo "--- Step 3: Adjudicating results ---"
python3 "$SCRIPT_DIR/_adjudicate_citations.py" "$LIT_MAP" "$PASS_RESULTS_DIR" || ADJ_EXIT=$?

echo ""

# Step 4: BibTeX generation
echo "--- Step 4: Generating BibTeX ---"
if [ -f "$VERIFIED_OUTPUT" ]; then
  python3 "$SCRIPT_DIR/_generate_bibtex.py" "$VERIFIED_OUTPUT" "$BIB_OUTPUT"
  BIB_ENTRIES=$(grep -c "^@" "$BIB_OUTPUT" 2>/dev/null || echo "0")
  echo "BibTeX entries: $BIB_ENTRIES"
else
  echo "[WARN] verified_citations.json not found, skipping BibTeX generation"
  BIB_ENTRIES=0
fi
echo ""

# Step 5: Citation report
echo "--- Step 5: Generating Citation Report ---"
if [ -f "$VERIFIED_OUTPUT" ]; then
  python3 "$SCRIPT_DIR/_generate_citation_report.py" "$VERIFIED_OUTPUT" "$REPORT_OUTPUT"
  echo "Report: $REPORT_OUTPUT"
else
  echo "[WARN] verified_citations.json not found, skipping report generation"
fi
echo ""

# Step 6: Summary
echo "--- Step 6: Verification Summary ---"
if [ -f "$VERIFIED_OUTPUT" ]; then
  VERIFIED=$(jq '[.[] | select(.verification_status == "verified")] | length' "$VERIFIED_OUTPUT")
  PARTIAL=$(jq '[.[] | select(.verification_status == "partial")] | length' "$VERIFIED_OUTPUT")
  FAILED=$(jq '[.[] | select(.verification_status == "failed")] | length' "$VERIFIED_OUTPUT")

  echo "Verified:       $VERIFIED"
  echo "Partial:        $PARTIAL"
  echo "Failed:         $FAILED"
  echo "Total:          $PAPER_COUNT"
  echo "BibTeX entries: $BIB_ENTRIES"
  echo "Report:         $REPORT_OUTPUT"
  echo ""

  if [ "$FAILED" -gt 0 ]; then
    echo "CRITICAL: $FAILED citation(s) failed verification (suspected fabrication)"
    echo ""
    echo "Failed citations:"
    jq -r '.[] | select(.verification_status == "failed") | "  - \(.title) [\(.citation_key)]"' "$VERIFIED_OUTPUT"
    echo ""
    echo "=== RESULT: VERIFICATION FAILED ($FAILED SUSPECTED FABRICATIONS) ==="
    exit 1
  fi

  echo "=== RESULT: ALL CITATIONS VERIFIED ==="
  exit 0
else
  echo "[FAIL] verified_citations.json not generated"
  echo "=== RESULT: VERIFICATION FAILED ==="
  exit 1
fi
