---
paper_type: theoretical
description: Theory paper with formal proofs, lemmas, and mathematical analysis
default: false
sections:
  - id: introduction
    title: Introduction
    required: true
    word_count: 1000
    citation_density: "5-8"
    figure_slots: 0
    argumentation: "Open problem statement -> prior theoretical results -> gap in existing analysis -> contribution summary with theorem highlights"
  - id: related_work
    title: Related Work
    required: true
    word_count: 1200
    citation_density: "15-25"
    figure_slots: 0
    argumentation: "Prior theoretical frameworks -> their limitations -> how this work extends or unifies them"
  - id: preliminaries
    title: Preliminaries
    required: true
    word_count: 800
    citation_density: "8-15"
    figure_slots: 0
    argumentation: "Notation -> definitions -> key prior results cited with precise theorem references -> assumptions stated"
  - id: main_results
    title: Main Results
    required: true
    word_count: 2500
    citation_density: "5-10"
    figure_slots: 1
    argumentation: "Theorem statement -> proof sketch -> full proof -> corollaries -> discussion of tightness/optimality"
  - id: discussion
    title: Discussion
    required: true
    word_count: 800
    citation_density: "3-6"
    figure_slots: 0
    argumentation: "Implications of results -> connections to open problems -> limitations of analysis -> conjectures"
  - id: conclusion
    title: Conclusion
    required: true
    word_count: 400
    citation_density: "1-3"
    figure_slots: 0
    argumentation: "Result summary -> significance of theoretical contribution -> open directions"
agent_ensemble:
  primary:
    - paper-section-writer
    - paper-peer-reviewer
    - paper-citation-verifier
  supporting:
    - paper-latex-engineer
  optional:
    - paper-figure-generator
total_citation_target: "30-50"
total_figure_target: "0-2"
---

# Theoretical Paper Template

## Overview

Use this template for papers whose primary contribution is a formal theoretical result -- new bounds, convergence proofs, complexity results, or impossibility theorems. The structure replaces the experiments/results split with a Preliminaries section and a proof-oriented Main Results section. Figures are minimal (typically illustrative diagrams of proof structure or comparison tables, not data plots).

## Section-by-Section Guidance

### Introduction
State the open problem clearly with mathematical precision. Summarize the best prior results (with explicit bounds/rates), identify where existing theory falls short, and preview the main theorem(s) with informal statements. Provide a roadmap.

### Related Work
Organize by theoretical framework rather than chronologically. Trace the evolution of key results, noting which assumptions each relies on. Position this work's contribution relative to the tightest known bounds or strongest existing results.

### Preliminaries
Define all notation, state necessary definitions, and cite prior results that the proofs build on. Reference specific theorem numbers from cited works. State assumptions explicitly -- reviewers will scrutinize which assumptions are needed and whether they are realistic.

### Main Results
Present theorems in increasing order of generality or difficulty. For each: state the theorem formally, give a proof sketch for intuition, then provide the full proof. Discuss tightness (is the bound achievable?) and compare against prior bounds. Corollaries that have practical implications should be highlighted.

### Discussion
Interpret the theoretical results in terms of practical implications. Connect to open problems in the field. Acknowledge limitations of the analysis (e.g., which assumptions could be relaxed and what would change). State conjectures for future work.

### Conclusion
Summarize the main results concisely, state the significance of the theoretical contribution to the broader field, and identify the most promising open directions.

## Common Pitfalls

- **Undefined notation:** Every symbol must be defined before use. Inconsistent notation across sections is a common rejection reason.
- **Missing proof details:** Proof sketches are helpful for intuition but the full proof must be rigorous. Defer long proofs to appendix if needed, but they must exist.
- **Unrealistic assumptions:** State assumptions clearly and discuss which are necessary vs. convenient. Reviewers reject when assumptions are too strong to be useful.
- **No comparison to prior bounds:** Theory papers must explicitly compare against the best known results and explain the improvement.
- **Disconnected from practice:** Even theory papers benefit from discussing practical implications or empirical validation of predicted behavior.
