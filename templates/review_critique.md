# Review Critique Template

Template for peer-reviewer agent output. Follows the NeurIPS review format with structured scores, specific feedback, and actionable suggestions.

---

## Review: {section_name}

**Reviewer persona:** {reviewer_type} (methodology | novelty | clarity)
**Review round:** {round_number}
**Date:** {review_date}

---

## Scores (NeurIPS Rubric)

| Dimension    | Score (1-10) | Justification |
|-------------|-------------|---------------|
| Quality     | {quality}   | {quality_justification} |
| Clarity     | {clarity}   | {clarity_justification} |
| Originality | {originality} | {originality_justification} |
| Significance | {significance} | {significance_justification} |

**Overall recommendation:** {strong_reject | reject | weak_reject | borderline | weak_accept | accept | strong_accept}
**Confidence:** {1-5} ({low | moderate | high | very_high | expert})

---

## Strengths

1. {strength_1}
2. {strength_2}
3. {strength_3}

Be specific. Reference exact passages, arguments, or evidence that works well.

---

## Weaknesses

1. {weakness_1}
2. {weakness_2}
3. {weakness_3}

Be specific. Every weakness should have a concrete suggestion for improvement.

---

## Questions for Authors

1. {question_1}
2. {question_2}

Questions that, if answered satisfactorily, could change the assessment.

---

## Specific Suggestions

### Critical (must address before acceptance)

| Location | Issue | Suggestion |
|----------|-------|------------|
| {section, paragraph, or line} | {what's wrong} | {how to fix it} |

### Major (should address)

| Location | Issue | Suggestion |
|----------|-------|------------|
| {section, paragraph, or line} | {what's wrong} | {how to fix it} |

### Minor (nice to have)

| Location | Issue | Suggestion |
|----------|-------|------------|
| {section, paragraph, or line} | {what's wrong} | {how to fix it} |

---

## Line-by-Line Comments

Format: `[Section.Paragraph.Sentence]` or `[Line N]`

- `[Intro.2.1]` {comment about specific text}
- `[Methods.3.4]` {comment about specific text}
- `[Results.1.2]` {comment about specific text}

---

## AI Writing Pattern Check

Flagged phrases or patterns that may trigger AI detection:
- {flagged_pattern_1} -- Suggestion: {rewrite}
- {flagged_pattern_2} -- Suggestion: {rewrite}

---

## Summary

{2-3 sentence summary of the review, highlighting the most important issue to address}

---

*Template version: 1.0*
*Used by: paper-peer-reviewer agent*
*Output contract: @paper/schemas/quality_scores.schema.json for structured scores*
