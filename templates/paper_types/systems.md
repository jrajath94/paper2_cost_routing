---
paper_type: systems
description: Systems paper presenting architecture, implementation, and performance benchmarks
default: false
sections:
  - id: introduction
    title: Introduction
    required: true
    word_count: 1000
    citation_density: "5-8"
    figure_slots: 0
    argumentation: "Real-world problem -> limitations of existing systems -> design goals -> system overview -> contributions list"
  - id: related_work
    title: Related Work
    required: true
    word_count: 1200
    citation_density: "12-20"
    figure_slots: 0
    argumentation: "Existing systems comparison -> design space coverage -> positioning of this system's unique design point"
  - id: system_design
    title: System Design
    required: true
    word_count: 2000
    citation_density: "5-10"
    figure_slots: 2
    argumentation: "Design goals/constraints -> architecture overview (diagram required) -> component descriptions -> design rationale for key choices"
  - id: implementation
    title: Implementation
    required: true
    word_count: 1200
    citation_density: "3-6"
    figure_slots: 1
    argumentation: "Technology stack -> key implementation details -> optimizations -> deployment considerations"
  - id: benchmarks
    title: Benchmarks
    required: true
    word_count: 1200
    citation_density: "3-5"
    figure_slots: 2
    argumentation: "Benchmark suite description -> system comparisons -> microbenchmarks -> scalability analysis -> resource usage"
  - id: discussion
    title: Discussion
    required: true
    word_count: 800
    citation_density: "3-6"
    figure_slots: 0
    argumentation: "Lessons learned -> limitations -> deployment experiences -> generalizability analysis"
  - id: conclusion
    title: Conclusion
    required: true
    word_count: 400
    citation_density: "1-3"
    figure_slots: 0
    argumentation: "System contribution recap -> key benchmark result -> availability/open-source statement"
agent_ensemble:
  primary:
    - paper-section-writer
    - paper-peer-reviewer
    - paper-citation-verifier
  supporting:
    - paper-figure-generator
    - paper-latex-engineer
    - paper-experiment-runner
  optional: []
total_citation_target: "30-50"
total_figure_target: "5-8"
---

# Systems Paper Template

## Overview

Use this template for papers presenting a novel system, tool, or platform. Systems papers emphasize architecture diagrams, implementation details, and performance benchmarks rather than theoretical analysis or traditional ML experiments. The structure replaces the experiments/results split with System Design, Implementation, and Benchmarks sections. Architecture diagrams are required in the System Design section. experiment-runner is promoted to supporting because benchmarks require automated execution.

## Section-by-Section Guidance

### Introduction
Ground the paper in a real-world problem that existing systems fail to handle well. State explicit design goals (latency, throughput, scalability, ease of use). Provide a high-level system overview in 2-3 sentences before diving into detailed contributions.

### Related Work
Compare against existing systems on specific dimensions (design goals met, performance, deployment model). Cover both academic systems and industry tools where relevant. Use a comparison table showing which design goals each system addresses.

### System Design
This is the core section. Lead with an architecture diagram showing major components and their interactions. Describe each component's responsibility and interfaces. For every significant design choice, state alternatives considered and the rationale for the chosen approach. This section must provide enough detail for someone to reimplement the system.

### Implementation
Cover the technology stack, key implementation details that affect performance or correctness, and non-obvious engineering decisions. Discuss optimizations and their measured impact. Include deployment considerations (resource requirements, configuration, scaling).

### Benchmarks
Present a comprehensive benchmark suite: macro-benchmarks (end-to-end system performance vs. baselines), micro-benchmarks (individual component performance), and scalability analysis (varying load, data size, or resources). Report resource usage (CPU, memory, network). Include the benchmark environment specification.

### Discussion
Share lessons learned from building and deploying the system. Acknowledge limitations honestly. Discuss how the design generalizes to other domains or scales. If there are deployment experiences, share production insights.

### Conclusion
Summarize the system's contribution, highlight the most compelling benchmark result, and state whether the system is available (open-source link, deployment, etc.).

## Common Pitfalls

- **No architecture diagram:** Systems papers without architecture diagrams are almost always rejected. The diagram should be clear enough to understand the system at a glance.
- **Missing design rationale:** Stating "we used X" without explaining why X over Y is a red flag. Every design choice should be justified.
- **Incomplete benchmarks:** Microbenchmarks without end-to-end evaluation (or vice versa) leave reviewers unsatisfied. Both are expected.
- **No scalability analysis:** If the system claims to scale, show it scaling. Vary one dimension at a time and plot the result.
- **Hand-waving implementation:** "We implemented this in Python" is not enough. The implementation section should provide insight that helps others build similar systems.
