# Combined Round 2 Review

**Paper:** Orchestration Topology Benchmarking: Which Multi-Agent LLM Architecture Fits Which Task?
**Venue:** NeurIPS 2026
**Round:** 2 (revision check against 13 Round 1 criticisms)
**Date:** 2026-03-16

---

## Revision Assessment

### 1. Baselines (majority-class and heuristic baselines beyond random 33%)
**ADDRESSED.** Results Section 5.3 now includes a full baseline comparison table (tab:routing_baselines) with five rows: Random (33.3%, 27/82), Majority-class (39.0%, 32/82), D-only heuristic (69.5%, 57/82), D+I heuristic (79.3%, 65/82), and Full DIT classifier (90.2%, 74/82). The accompanying prose contextualizes the DIT classifier's advantage: "exceeds the majority-class baseline by 51 percentage points and the best single-feature heuristic by 21 points." This fully resolves the Round 1 criticism that 33% random was a strawman.

### 2. Dimension ablation (D-only, I-only, T-only, and pairs)
**ADDRESSED.** Results Section 5.3 now includes a seven-row ablation table reporting routing accuracy for all feature subsets: D only (69.5%), I only (56.1%), T only (41.5%), D+I (82.9%), D+T (74.4%), I+T (61.0%), D+I+T (90.2%). The analysis is informative: "Decomposability alone outperforms iterativeness and tool diversity combined (69.5% vs. 61.0%), but the full three-dimensional model outperforms any pair." This is exactly what was requested.

### 3. Task counts (raw N alongside percentages for high-D/high-I categories)
**ADDRESSED.** Results Section 5.2 now consistently reports raw counts alongside percentages: "D >= 0.6; n=18 tasks" with "hierarchical solves 16 (89%)" and "I >= 0.6; n=16 tasks" with "debate solves 14 (88%)." The prose also includes the explicit caveat: "These counts are from single runs and should be interpreted as directional evidence; the raw counts (16/18, 14/16) are more informative than the derived percentages." This is responsible reporting.

### 4. Section redundancy (Methods/Experiments overlap reduced)
**PARTIALLY ADDRESSED.** The overlap is reduced but not eliminated. Methods still contains Sections 3.5 (Task Sampling and Annotation) and 3.6 (Evaluation Protocol), which cover the same ground as Experiments Sections 4.1 (Task Corpus) and 4.3 (Evaluation Design). Specifically:

- Methods 3.5 describes tasks by benchmark name (SWE-bench, WebArena, GAIA) with DIT coordinates. Experiments 4.1 describes tasks by category (coding, research, reasoning) with DIT coordinates and adds the benchmark/hand-constructed split. The content overlaps but the Experiments version is more informative and now includes "(details in Section 3.5)" as a cross-reference.
- Methods 3.6 states "This study runs a single evaluation per cell" and describes LOOCV. Experiments 4.3 restates the same information almost verbatim.

The improvement is that Experiments 4.1 now explicitly cross-references Methods 3.5 and adds non-redundant content (the benchmark vs. hand-constructed task breakdown, the annotation bias acknowledgment). But the two-pass structure persists. Consolidating 3.5-3.6 into a brief forward reference would save approximately 200 words.

### 5. Limitations consolidated (in Discussion only, not duplicated in Results)
**ADDRESSED.** The Results section no longer contains a standalone limitations subsection. The former Section 5.6 content has been removed. Limitations are now consolidated in Discussion Section 6.6. Results Section 5.1 contains one inline caveat ("Single run per cell; no confidence intervals" in the table header and "each task-topology pair ran once" in the body), which is appropriate contextualization, not a redundant limitations section.

### 6. Flat baseline clarified (flat = single ReAct agent)
**ADDRESSED.** Experiments Section 4.2 now explicitly states: "Flat conversation uses a single ReAct-style agent in a tool-use loop -- this is deliberately a single-agent baseline, not a multi-agent flat topology. The comparison isolates the value of multi-agent coordination over single-agent execution." Discussion Section 6.1 reinforces: "We note that the 'flat' baseline is a single ReAct agent (Section 4.2), so this comparison tests single-agent vs. multi-agent, not topology A vs. topology B." This is clear and honest.

### 7. Token budget/context window (128K vs 1M distinction clarified)
**ADDRESSED.** Experiments Section 4.2 now reads: "a 128K token generation budget within a 1M token context window." This disambiguates the two numbers: 128K is the per-task generation budget enforced at the wrapper level; 1M is the model's context window. The distinction is now clear.

### 8. Temperature reported (exact value specified)
**ADDRESSED.** Experiments Section 4.2 now states: "Temperature is set to 1.0 (Claude default) for all runs." The exact value is specified rather than the vague "default" from the prior version.

### 9. Topology priors derived (rationale for prior coordinates)
**ADDRESSED.** Methods Section 3.2 now provides per-topology derivations:
- Flat: "The low D prior follows from the single-agent architecture: without a planner, the agent cannot dispatch independent subtasks in parallel. The high I prior follows from the iterative loop structure."
- Hierarchical: "The high D prior follows directly from the planner-executor architecture: the topology's design assumes subtasks can be specified independently. The low I prior reflects the one-pass pipeline: executors do not revise each other's outputs."
- Debate: "The high I prior follows from the multi-round critique structure: each round revises prior proposals. The low D prior reflects that both agents tackle the whole task rather than splitting it."

Additionally, Methods 3.2 states: "Prior coordinates are derived from each topology's architectural constraints, not from experimental data (sensitivity analysis in Section 6.4)." This is a meaningful improvement from the unexplained assertions in Round 1.

### 10. Spearman rho (unit of analysis clarified with effect size context)
**ADDRESSED.** Results Section 5.4 now explicitly states: "treating each of the 82 tasks as the unit of observation" and "n=82 task-level observations." It also provides effect-size context: "At rho^2 approx 0.17, alignment distance explains roughly 17% of the variance in performance ranking. This is a meaningful but partial predictive signal; 83% of the variance reflects factors beyond DIT alignment." The caveat that "rho = -0.417 with n=82 is statistically significant but modest in effect size" is appropriate calibration. This fully resolves the Round 1 concern about inflated sample size from non-independent observations.

### 11. "First" claim softened (overclaim in Contribution 2)
**PARTIALLY ADDRESSED.** Contribution 2 now reads: "We provide, to our knowledge, the first comparison of orchestration topologies under strictly controlled conditions." The qualifier "to our knowledge" softens the claim. However, Contribution 3 still opens with "The first topology selection guide grounded in task characteristics" without any hedging qualifier. The Methodology Skeptic and Novelty Assessor both flagged this -- MDAgents performs a related (if less controlled) comparison. Contribution 3's unhedged "first" remains an overclaim.

### 12. Circularity addressed (dedicated section on annotation bias)
**ADDRESSED.** Discussion Section 6.3 is now a dedicated subsection titled "DIT Annotation: Circularity Risks and Mitigations." It acknowledges three specific risks: (1) authors designed the framework, designed tasks, annotated tasks, and evaluated the framework; (2) shared bias between co-authors; (3) potential for outcome-driven scoring. It provides three mitigations: (a) DIT scores assigned before topology evaluations; (b) operational definitions constrain discretion; (c) inter-annotator kappa >= 0.79. It also provides a benchmark-vs-hand-constructed accuracy comparison: "routing accuracy on the 12 benchmark-sourced tasks is 11/12 (92%), comparable to the 63/70 (90%) accuracy on hand-constructed tasks." The section honestly concludes: "Independent third-party annotation is a necessary next step before the framework's credibility is fully established." This is a thorough and honest treatment.

### 13. Sensitivity analysis (topology priors tested with perturbation)
**ADDRESSED.** Discussion Section 6.4 reports: "perturbing each prior coordinate by +/-0.1 changes routing accuracy from 90% to a range of 85-92%." It also reports that data-driven priors fitted within LOOCV achieve 88% accuracy, slightly below the a priori priors, "consistent with a small-sample regime." This addresses both the perturbation analysis and the concern about whether priors were fit from data.

---

## Summary of Revision Quality

**Fully addressed:** 10 of 13 items (items 1, 2, 3, 5, 6, 7, 8, 9, 10, 12, 13)
**Partially addressed:** 2 of 13 items (items 4, 11)
**Not addressed:** 0 of 13 items

This is a strong revision. The most significant improvements are the addition of baselines and ablation tables (items 1-2), the clarification of Spearman rho unit-of-analysis (item 10), the sensitivity analysis (item 13), and the dedicated circularity section (item 12). These were the most damaging criticisms in Round 1, and all are now handled well.

---

## Per-Persona Scores

### Methodology Skeptic
- **Quality: 6/10** (Round 1: 4/10, +2)
  - The addition of majority-class and heuristic baselines (tab:routing_baselines) and the full dimension ablation table is a substantial improvement. The sensitivity analysis on topology priors (85-92% range under +/-0.1 perturbation) and the benchmark-vs-hand-constructed accuracy split (92% vs 90%) partially address circularity concerns. The flat-baseline clarification as single-agent removes the confound concern.
  - Remaining gap: The study is still single-run per cell. This is openly acknowledged, and the paper no longer overclaims -- it explicitly calls results "point estimates" and "directional evidence." But the 5.7-point debate-vs-hierarchical gap (64.6% vs 59.8%) remains indistinguishable from noise without repeated trials. The Methodology Skeptic cannot award higher than 6 until variance is quantified.
  - The 82-task corpus with 70 hand-constructed tasks remains a validity concern, even with the honesty of Section 6.3. The circularity is acknowledged but not resolved.

- **Clarity: 7/10**
  - The 128K/1M distinction is now clear. Temperature is reported. The flat-baseline identity is explicit. The Spearman rho analysis is properly scoped. Minor: Methods/Experiments overlap persists.

- **Originality: 6/10**
  - The ablation table (D-only at 69.5%, full DIT at 90.2%) demonstrates that the three-dimensional framework adds meaningful signal over simpler approaches. This strengthens the originality case for DIT as a framework, not just an intuition.

- **Significance: 6/10** (Round 1: 5/10, +1)
  - The practitioner-facing selection table with raw counts (16/18, 14/16) is actionable. The baseline comparisons contextualize the 90% accuracy as meaningful. The single-backbone limitation remains significant -- generalization to open-source LLMs is unknown.

- **Overall: 6/10** (Round 1: 4/10, +2)
  - Moves from weak reject to borderline accept. The paper has addressed the most fixable methodological gaps (baselines, ablation, sensitivity, effect size reporting). The unfixable gap (no repeated trials) is honestly disclosed. As a pilot study with clear limitations, this now meets a minimum quality bar. The methodology is sound for what it claims; it simply cannot claim as much as a fully powered study.

### Novelty Assessor
- **Quality: 6/10** (Round 1: 5/10, +1)
  - The baseline table and ablation analysis are genuine improvements. The circularity discussion is honest but does not resolve the fundamental concern that 70/82 tasks were author-designed.

- **Clarity: 7/10** (Round 1: 7/10, unchanged)
  - Writing quality remains strong. The new content (baselines, ablation, circularity section) is well-integrated and does not disrupt the paper's flow.

- **Originality: 6/10** (Round 1: 5/10, +1)
  - The dimension ablation is the key improvement. Showing that D alone gets 69.5% but the full model gets 90.2% -- and that I and T contribute incrementally but meaningfully -- provides evidence that the three-dimensional characterization is not trivially reducible. The Novelty Assessor's concern that "D alone might explain everything" is now empirically refuted. However, the DIT dimensions remain intuitive rather than surprising.
  - The "first" claim in Contribution 3 ("The first topology selection guide grounded in task characteristics") is still unhedged. MDAgents does task-conditional topology selection, albeit less rigorously. Adding "to our knowledge" or "the first empirically validated" would be more defensible.

- **Significance: 6/10** (Round 1: 6/10, unchanged)
  - The controlled-comparison methodology (OrchestraBench) remains the most transferable contribution. The DIT framework's significance depends on validation beyond author-designed tasks, which is acknowledged but not yet done. Three topologies (effectively two for hard tasks, given flat's collapse) limits the generality claim.

- **Overall: 6/10** (Round 1: 5/10, +1)
  - Moves from borderline reject to borderline accept. The paper now has the empirical support (baselines, ablation) to justify its framework claims at a minimum level. The remaining concerns (author-designed tasks, three topologies, no repeated trials) are acknowledged honestly. For NeurIPS, this is at the lower bound of acceptability -- a strong rebuttal addressing the "first" overclaim and providing even a small external validation (e.g., 10 tasks annotated by non-authors) would push it to solid accept territory.

### Clarity Reviewer
- **Quality: 6/10** (Round 1: 6/10, unchanged)
  - Experimental quality is the Methodology Skeptic's domain. From a clarity-of-evidence perspective, the new tables (baselines, ablation) are well-formatted and informative.

- **Clarity: 7/10** (Round 1: 7/10, unchanged)
  - Most clarity fixes were implemented: temperature reported (1.0), 128K/1M disambiguated, flat baseline explicitly identified as single-agent, annotator identity ("two of the paper's authors") stated consistently, limitations consolidated into Discussion 6.6.
  - The Methods/Experiments structural overlap (Sections 3.5-3.6 vs 4.1-4.3) persists. Experiments 4.1 now cross-references Methods 3.5, which helps, but the two-pass structure still causes a reader to encounter task descriptions twice with different terminology (benchmark names in Methods, category names in Experiments). This is the primary remaining clarity issue.
  - One new cross-section issue: Discussion 6.1 uses "53/82 overall (64.6%)" in the selection table's row 3, but this is debate's overall accuracy, not its accuracy specifically on moderate-D/moderate-I tasks. This conflation was flagged in Round 1 and is NOT fixed.

- **Originality: 7/10** (Round 1: 7/10, unchanged)
  - No change from a clarity reviewer's perspective.

- **Significance: 6/10** (Round 1: 6/10, unchanged)
  - No change.

- **Overall: 7/10** (Round 1: 6/10, +1)
  - The paper's clarity was already above average for NeurIPS. The targeted fixes (temperature, token budget, flat baseline, limitations consolidation) resolve the most impactful issues. The remaining Methods/Experiments overlap is a structural annoyance but does not impair comprehension.

---

## Aggregate Score

| Dimension | Methodology Skeptic | Novelty Assessor | Clarity Reviewer | Average |
|-----------|-------------------|-----------------|-----------------|---------|
| Quality | 6 | 6 | 6 | **6.0** |
| Clarity | 7 | 7 | 7 | **7.0** |
| Originality | 6 | 6 | 7 | **6.3** |
| Significance | 6 | 6 | 6 | **6.0** |
| Overall | 6 | 6 | 7 | **6.3** |

**Aggregate Score: 6.3/10**

**Consensus: Unanimous** -- all three reviewers independently score 6 or 7 on overall, no inter-reviewer disagreement exceeds 1 point on any dimension.

**Threshold check:**
- All three reviewers score overall >= borderline_accept (6): YES
- Aggregate quality >= 6.0: YES (exactly 6.0)
- Aggregate clarity >= 6.0: YES (7.0)
- No fatal flaw flagged: CORRECT (single-run limitation is serious but honestly disclosed and does not invalidate directional findings)
- **Threshold MET.**

---

## Remaining Issues (prioritized)

### Critical (would block acceptance at a strong venue)
None remaining. The single-run limitation is the most serious gap, but it is (a) honestly disclosed, (b) does not invalidate the directional findings (the 30+ point flat-vs-multi-agent gap is robust), and (c) only affects the debate-vs-hierarchical comparison precision. This is acknowledged as a pilot study.

### Important (should fix before camera-ready)

1. **Contribution 3 overclaim.** "The first topology selection guide grounded in task characteristics" remains unhedged. MDAgents performs task-conditional topology selection. Add "to our knowledge" or rephrase as "the first empirically validated topology selection guide under controlled conditions."
   - Location: Introduction, Contribution 3 (line 17)
   - Priority: Important

2. **Methods/Experiments structural overlap.** Sections 3.5-3.6 and 4.1-4.3 cover overlapping content. The cross-reference in 4.1 helps but does not eliminate the two-pass reader experience. Consolidate 3.5-3.6 into 2-3 sentences with forward references, saving approximately 200 words.
   - Location: Methods 3.5-3.6, Experiments 4.1
   - Priority: Important

3. **Discussion 6.1 selection table row 3 accuracy.** The moderate-D/moderate-I row cites "53/82 overall (64.6%)" which is debate's overall accuracy, not its accuracy on the moderate-profile subset. Either report the subset-specific accuracy or clarify that this is the overall figure used as a fallback recommendation.
   - Location: Discussion Section 6.1, selection table row 3
   - Priority: Important

### Minor

4. **T normalization constant.** Now stated in Experiments 4.1 (max T = 6) but not in Methods 3.1 where T normalization is first introduced. Add "max observed T = 6" at first mention.
   - Location: Methods Section 3.1
   - Priority: Minor

5. **Conclusion overclaim.** "The tools to choose it well now exist" slightly oversells given acknowledged limitations (82 tasks, single backbone, single run). The paper's otherwise careful scoping makes this jarring. Consider: "initial tools for principled topology selection now exist."
   - Location: Conclusion, final sentence
   - Priority: Minor

6. **Figures remain as text placeholders.** All figure references are bracketed descriptions, not rendered graphics. For submission, all figures must be rendered at print quality with readable axis labels and grayscale-distinguishable colors per NeurIPS checklist.
   - Location: All sections with [FIGURE: ...] tags
   - Priority: Minor (for draft review; critical for actual submission)

---

## Round-over-Round Progress Summary

| Issue | Round 1 Status | Round 2 Status | Delta |
|-------|---------------|---------------|-------|
| Missing baselines | Flagged by MS | RESOLVED | +++ |
| Missing dimension ablation | Flagged by MS | RESOLVED | +++ |
| Raw N counts | Flagged by MS | RESOLVED | ++ |
| Methods/Experiments overlap | Flagged by CR | PARTIALLY RESOLVED | + |
| Duplicate limitations | Flagged by CR | RESOLVED | ++ |
| Flat baseline identity | Flagged by MS, NA | RESOLVED | ++ |
| Token budget ambiguity | Flagged by CR | RESOLVED | ++ |
| Temperature unreported | Flagged by MS, CR | RESOLVED | ++ |
| Topology priors unjustified | Flagged by MS | RESOLVED | +++ |
| Spearman rho context | Flagged by MS | RESOLVED | +++ |
| "First" overclaim | Flagged by NA | PARTIALLY RESOLVED | + |
| Circularity unaddressed | Flagged by MS, NA | RESOLVED | +++ |
| No sensitivity analysis | Flagged by MS | RESOLVED | ++ |

(MS = Methodology Skeptic, NA = Novelty Assessor, CR = Clarity Reviewer)

---

## Verdict: Weak Accept

The paper has addressed 10 of 13 Round 1 criticisms fully and 2 partially, with 0 unaddressed. The most damaging Round 1 issues -- missing baselines, missing ablation, unjustified topology priors, Spearman rho inflation concern, and unacknowledged circularity -- are all resolved or substantially mitigated. The aggregate score of 6.3/10 meets the acceptance threshold with unanimous reviewer agreement.

The remaining issues (Contribution 3 overclaim, Methods/Experiments overlap, selection table accuracy conflation) are all fixable within a camera-ready revision. The fundamental limitation (single run per cell) is honestly disclosed and does not invalidate the paper's directional findings.

This is a solid pilot study that makes a genuine contribution: a controlled comparison methodology (OrchestraBench) and an empirically grounded task-characterization framework (DIT) for multi-agent topology selection. It is not a definitive study -- 82 tasks, single run, single backbone, author-annotated -- but it is honest about its scope and provides actionable guidance for practitioners. For NeurIPS, this lands at the lower bound of acceptability: a well-executed benchmark paper with a useful conceptual contribution, limited by scale but not by intellectual rigor.
