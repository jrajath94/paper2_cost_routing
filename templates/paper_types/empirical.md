---
paper_type: empirical
description: Standard empirical ML paper with experiments, baselines, and ablations
default: true
sections:
  - id: introduction
    title: Introduction
    required: true
    word_count: 1000
    citation_density: "5-8"
    figure_slots: 0
    argumentation: "Problem statement -> existing approaches -> gap identification -> contributions list -> roadmap paragraph"
  - id: related_work
    title: Related Work
    required: true
    word_count: 1500
    citation_density: "15-25"
    figure_slots: 0
    argumentation: "Thematic clusters (3-5) -> per-cluster limitations -> positioning of this work"
  - id: methods
    title: Methods
    required: true
    word_count: 1500
    citation_density: "5-10"
    figure_slots: 1
    argumentation: "Problem formalization -> proposed approach -> algorithm/architecture details -> complexity/cost analysis"
  - id: experiments
    title: Experiments
    required: true
    word_count: 1000
    citation_density: "3-5"
    figure_slots: 2
    argumentation: "Research questions -> experimental setup -> datasets -> baselines -> evaluation metrics"
  - id: results
    title: Results
    required: true
    word_count: 1000
    citation_density: "2-5"
    figure_slots: 2
    argumentation: "Main results table -> per-baseline comparison -> ablation study -> statistical significance"
  - id: discussion
    title: Discussion
    required: true
    word_count: 800
    citation_density: "3-6"
    figure_slots: 0
    argumentation: "Key findings interpretation -> limitations -> broader impact -> future work"
  - id: conclusion
    title: Conclusion
    required: true
    word_count: 400
    citation_density: "1-3"
    figure_slots: 0
    argumentation: "Contribution recap -> main result highlight -> forward-looking statement"
agent_ensemble:
  primary:
    - paper-section-writer
    - paper-peer-reviewer
    - paper-citation-verifier
  supporting:
    - paper-figure-generator
    - paper-latex-engineer
  optional:
    - paper-experiment-runner
total_citation_target: "40-60"
total_figure_target: "4-8"
---

# Empirical Paper Template

## Overview

Use this template for papers that present a novel method or system and evaluate it through experiments on datasets with quantitative metrics. This is the default template and matches the shape of the first paper (LLM agent experiments). The structure follows the standard ML conference format expected at NeurIPS, ICML, and ICLR.

## Section-by-Section Guidance

### Introduction
Open with a concrete problem statement grounded in real-world or theoretical stakes. Survey existing approaches briefly (Related Work handles depth), identify the specific gap, and state contributions as a numbered list. End with a section roadmap.

### Related Work
Organize by 3-5 thematic clusters, not paper-by-paper summaries. For each cluster, summarize the collective contribution, note limitations, and position this work relative to the cluster. Every sentence must cite at least one source.

### Methods
Formalize the problem, present the proposed approach with enough detail for reproducibility, include algorithm pseudocode or architecture diagrams where helpful. Discuss computational complexity and any design choices with rationale.

### Experiments
State specific research questions the experiments answer. Describe datasets, baselines, evaluation metrics, and hyperparameter selection. Justify why each baseline was chosen. Include implementation details necessary for reproducibility.

### Results
Lead with the main results table comparing against all baselines. Follow with ablation studies showing which components matter. Report statistical significance (p-values or confidence intervals). Present negative results honestly.

### Discussion
Interpret key findings, connect back to the research questions, acknowledge limitations explicitly, discuss broader implications and societal impact, and outline concrete future work directions.

### Conclusion
Recap the contribution in 2-3 sentences, highlight the single most important result, and close with a forward-looking statement about impact or next steps.

## Common Pitfalls

- **Weak baselines:** Comparing only against strawman methods undermines credibility. Include strong recent baselines from top venues.
- **Missing ablations:** Reviewers expect to see which components of your method actually contribute. Ablate key design choices.
- **No error bars:** Report variance across runs with different seeds. Single-run results are not publishable.
- **Overclaiming:** Let the numbers speak. Avoid "dramatically outperforms" -- state the actual improvement percentage.
- **Disconnected discussion:** The Discussion section must connect back to the Introduction's claims and the Results' evidence.
