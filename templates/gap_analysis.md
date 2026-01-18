# Gap Analysis Template

Template for gap-analyzer narrative output. Provides a human-readable companion to the structured `research_gaps.json` file, offering detailed justification and recommended framing for each identified gap.

---

## Gap Analysis: {topic}

**Literature corpus:** {total_papers} papers from {literature_map_path}
**Clusters identified:** {cluster_count}
**Analysis date:** {date}

---

## Gap {gap_number}: {gap_title}

### Description

{2-3 sentence description of the research gap. What area is unexplored? Why does it matter?}

### Supporting Evidence

The existence of this gap is supported by the following citation patterns:

1. **{paper_1_id}** ({authors}, {year}): {How this paper relates to the gap -- what it covers and what it leaves open}
2. **{paper_2_id}** ({authors}, {year}): {How this paper relates to the gap}
3. **{paper_3_id}** ({authors}, {year}): {How this paper relates to the gap}

**Citation pattern analysis:** {Describe the specific citation graph pattern -- e.g., "Papers in cluster A cite each other extensively but have zero cross-citations with cluster B, despite both addressing {shared_topic}"}

### Cluster Descriptions

**Cluster A: {cluster_a_name}**
- Core papers: {list of key paper IDs}
- Focus: {what this cluster researches}
- Methods: {typical approaches used}

**Cluster B: {cluster_b_name}**
- Core papers: {list of key paper IDs}
- Focus: {what this cluster researches}
- Methods: {typical approaches used}

**Connection density:** {sparse | moderate | dense} -- {specific co-citation or cross-reference count}

### Novelty Justification

**Novelty score:** {1-10}

{Why this score? Reference specific evidence:}
- Co-citation proximity: {Are papers in the two clusters ever co-cited? How often?}
- Direct papers: {Are there any papers that directly bridge this gap? If so, what do they miss?}
- Recency: {Is this gap recent (new clusters diverging) or long-standing (persistent blind spot)?}
- Search validation: {What searches were run to confirm no existing work bridges this gap?}

### Feasibility Assessment

**Feasibility score:** {1-10}

{Why this score? Be concrete:}
- **Required data:** {What datasets are needed? Are they publicly available?}
- **Required compute:** {Local-only? GPU needed? Approximate training time?}
- **Required baselines:** {What existing systems need to be reproduced or compared against?}
- **Scope:** {Can this be addressed in a single paper (9 pages + appendix)?}
- **Risk factors:** {What could make this infeasible?}

### Recommended Framing

{1-2 paragraph suggestion for how a paper could address this gap. Include:}
- Proposed title angle
- Which cluster's methods to extend and how
- What the key experiment or contribution would be
- How to position for the target venue

---

## Summary Ranking

| Rank | Gap ID | Novelty | Feasibility | Confidence | Recommended? |
|------|--------|---------|-------------|------------|-------------|
| 1    | {gap_id} | {score} | {score} | {HIGH/MED/LOW} | {Yes/No} |
| 2    | {gap_id} | {score} | {score} | {HIGH/MED/LOW} | {Yes/No} |
| 3    | {gap_id} | {score} | {score} | {HIGH/MED/LOW} | {Yes/No} |

**Selected gap:** {gap_id} -- {one-line rationale for selection}

---

*Template version: 1.0*
*Used by: paper-gap-analyzer agent*
*Structured output: @paper/schemas/research_gaps.schema.json*
