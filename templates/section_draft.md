# Section Draft Template

Template for section-writer agent output. Each section draft follows this structure to ensure consistent quality, proper citation density, and self-assessment for the review loop.

---

## Section: {section_name}

**Target word count:** {target_words}
**Citation density target:** {citations_per_paragraph} citations per paragraph (minimum)
**Key arguments to cover:**
1. {argument_1}
2. {argument_2}
3. {argument_3}

---

## Draft

{section_body}

Write the full section here. Follow these guidelines:
- Open with a clear topic sentence establishing the section's purpose
- Each paragraph should advance one argument or present one piece of evidence
- Citations use `\cite{key}` format inline (e.g., "Recent work on multi-agent orchestration \cite{wu2023autogen} demonstrates...")
- Maintain logical flow between paragraphs with explicit transitions
- Close with a summary sentence that connects to the next section
- Avoid AI writing patterns: no "it is worth noting", "furthermore", "in conclusion", chains of hedging qualifiers
- Use active voice and concrete claims backed by citations or experiments

---

## Self-Assessment

**Quality (1-10):** {quality_score}
Justification: {quality_justification}

**Clarity (1-10):** {clarity_score}
Justification: {clarity_justification}

**Originality (1-10):** {originality_score}
Justification: {originality_justification}

**Significance (1-10):** {significance_score}
Justification: {significance_justification}

**Citation count:** {total_citations}
**Word count:** {actual_words}

---

## Known Weaknesses

List weaknesses the writer is aware of before review:
1. {weakness_1}
2. {weakness_2}

## Revision Notes

If this is a revision (round > 1), document what changed:
- **Review round:** {round_number}
- **Addressed feedback:** {list of feedback items addressed}
- **Remaining issues:** {items not yet addressed and why}

---

*Template version: 1.0*
*Used by: paper-section-writer agent*
*Output contract: Consumed by paper-peer-reviewer for critique*
