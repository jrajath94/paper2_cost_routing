---
paper_type: survey
description: Comprehensive survey organizing and synthesizing a research area
default: false
sections:
  - id: introduction
    title: Introduction
    required: true
    word_count: 1200
    citation_density: "8-12"
    figure_slots: 0
    argumentation: "Field overview -> why a survey is needed now -> scope and inclusion criteria -> contribution of this survey -> paper organization"
  - id: background
    title: Background
    required: true
    word_count: 1000
    citation_density: "10-15"
    figure_slots: 0
    argumentation: "Foundational concepts -> historical development -> key definitions and terminology"
  - id: taxonomy
    title: Taxonomy
    required: true
    word_count: 1500
    citation_density: "15-25"
    figure_slots: 2
    argumentation: "Classification criteria -> taxonomy tree/diagram -> category definitions -> scope of each category"
  - id: detailed_review
    title: Detailed Review
    required: true
    word_count: 3000
    citation_density: "30-50"
    figure_slots: 1
    argumentation: "Per-category deep dive -> representative methods -> comparison tables -> evolution within each category"
  - id: analysis
    title: Comparative Analysis
    required: true
    word_count: 1500
    citation_density: "10-20"
    figure_slots: 1
    argumentation: "Cross-category comparison -> performance benchmarks -> trade-off analysis -> trend identification"
  - id: open_problems
    title: Open Problems and Future Directions
    required: true
    word_count: 1000
    citation_density: "5-10"
    figure_slots: 0
    argumentation: "Unsolved challenges -> promising directions -> gaps in current research -> emerging trends"
  - id: conclusion
    title: Conclusion
    required: true
    word_count: 400
    citation_density: "1-3"
    figure_slots: 0
    argumentation: "Survey scope recap -> key findings -> most impactful open directions"
agent_ensemble:
  primary:
    - paper-section-writer
    - paper-peer-reviewer
    - paper-citation-verifier
    - paper-literature-scout
  supporting:
    - paper-figure-generator
    - paper-latex-engineer
  optional: []
total_citation_target: "80-150"
total_figure_target: "3-6"
---

# Survey Paper Template

## Overview

Use this template for papers that systematically review, organize, and synthesize a research area. Surveys require significantly higher citation density than other paper types -- the Detailed Review section alone targets 30-50 citations. The structure emphasizes taxonomy and comparative analysis over novel experiments. Literature-scout is promoted to a primary agent because comprehensive coverage is essential.

## Section-by-Section Guidance

### Introduction
Establish why the field needs a survey now (rapid growth, fragmentation, emerging applications). Define the scope precisely -- what is included and what is excluded. State the survey's contribution beyond merely listing papers (novel taxonomy, identified trends, unified framework). Include a search methodology description (databases searched, keywords, inclusion/exclusion criteria).

### Background
Cover foundational concepts that readers need to understand the surveyed area. Trace the historical development briefly, establishing when and why the field emerged. Define key terminology that the rest of the survey uses consistently.

### Taxonomy
Present a clear classification of approaches in the surveyed area. Use a taxonomy diagram or tree structure. Define each category with crisp boundaries. Justify why this taxonomy is useful compared to alternative classifications. Each category should be illustrated with 2-3 representative works.

### Detailed Review
The core of the survey. For each taxonomy category, provide a thorough review of representative methods. Use comparison tables with consistent dimensions (approach, key idea, strengths, limitations, datasets, reported performance). Trace the evolution within each category.

### Comparative Analysis
Go beyond category-level review to cross-category comparison. Identify performance benchmarks where methods from different categories have been compared. Analyze trade-offs (accuracy vs. efficiency, generality vs. specialization). Identify trends across the field.

### Open Problems and Future Directions
Identify unsolved challenges that cut across categories. Highlight promising research directions with specific actionable suggestions. Note gaps in current research coverage (missing evaluations, underexplored combinations, scalability questions).

### Conclusion
Recap the survey's scope and key findings. Highlight the 2-3 most impactful open directions. Provide a forward-looking statement about where the field is heading.

## Common Pitfalls

- **List of summaries:** A survey must synthesize, not just list. Group by themes, compare across works, identify trends.
- **Incomplete coverage:** Missing seminal or recent works undermines credibility. Use systematic search methodology and document it.
- **Stale taxonomy:** If the taxonomy doesn't accommodate recent advances, it needs revision. Test by classifying the newest works.
- **No analysis:** Summary without analysis adds little value. The comparative analysis section must provide insights not obvious from individual paper readings.
- **Bias toward own work:** If your own papers dominate, the survey appears self-serving. Maintain balanced coverage.
