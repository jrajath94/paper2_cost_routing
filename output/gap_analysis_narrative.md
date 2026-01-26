# Gap Analysis Narrative: Cost-Aware Topology Routing for Multi-Agent LLM Deployments

## 1. Literature Landscape

We surveyed 52 papers across 6 clusters spanning model-level routing, topology optimization, budget-aware agents, token efficiency, inference cost systems, and difficulty estimation. The field is rapidly evolving: 38 of 52 papers were published in 2025, with several appearing in top venues (ICLR, NeurIPS, ACL, EMNLP).

### Cluster Summary

| Cluster | Papers | Key Finding |
|---------|--------|-------------|
| model-routing | 16 | Mature field. FrugalGPT->RouteLLM->Router-R1 progression shows 40-98% cost reduction at model level. |
| topology-optimization | 13 | Rapidly growing. AgentBalance, GTD, AgentConductor all 2025. Topology matters but selection is ad-hoc. |
| budget-agents | 5 | BAMAS and BudgetMLAgent show explicit budgets work. BATS proves budget awareness helps single agents. |
| token-efficiency | 7 | AgentDropout achieves 94.5% token reduction. Optima shows 2.8x gains. But all within fixed topologies. |
| inference-cost | 7 | C3PO provides formal cost guarantees. Cascadia optimizes serving. All model-cascade level. |
| difficulty-estimation | 5 | DAAO's VAE difficulty estimator is the state-of-the-art. Scaling laws show 2-6x MAS overhead. |

## 2. The Central Gap: Model Routing Has Not Been Extended to Topologies

The dominant pattern in model routing is clear: estimate difficulty, route to the cheapest option meeting a quality bar, save 40-98%. This principle has been validated across FrugalGPT (2023), Hybrid LLM (ICLR 2024), RouteLLM (ICLR 2025), AutoMix (NeurIPS 2024), C3PO (NeurIPS 2025), and BEST-Route (2025).

Meanwhile, multi-agent topology research shows that topology choice matters enormously. Sparse Debate achieves comparable quality at far lower cost than fully-connected. Scaling Agent Systems finds 2-6x cost overhead varies by topology. AgentConductor shows 68% token reduction via difficulty-aware density.

**But nobody connects these two lines.** No paper asks: "Given a task, what is the cheapest topology (single-agent, flat, debate, hierarchical) that meets the quality threshold?"

### Closest Work

- **AgentBalance (Dec 2025):** Closest to our gap. Does backbone-then-topology under budgets. But uses static optimization, not a learned per-query router. Sequential, not joint.
- **BAMAS (Nov 2025):** Uses RL for topology selection under budgets. But trained per-task distribution, not generalizable.
- **DAAO (2025):** Has the difficulty estimator but routes within fixed operator pipelines, not across topologies.
- **MasRouter (ACL 2025):** Routes LLMs for MAS but within a fixed collaboration mode. Does not select the topology.

## 3. Five Research Gaps Identified

### GAP-001 (TOP): Cost-Aware Topology Routing via Difficulty Estimation
**Novelty: 8 | Feasibility: 8 | Confidence: HIGH**

The core gap. Apply the FrugalGPT principle at the topology level: a lightweight router estimates task difficulty and selects the cheapest topology meeting a quality threshold. This bridges model-routing (cluster 1) and topology-optimization (cluster 2) while leveraging difficulty-estimation (cluster 6).

### GAP-002: Probabilistic Cost Guarantees for Topology Selection
**Novelty: 7 | Feasibility: 7 | Confidence: MEDIUM**

Extend C3PO's conformal prediction from model cascades to topology selection. Provide provable P(cost > budget) bounds for topology routing decisions.

### GAP-003: Cross-Topology Token Cost Characterization
**Novelty: 6 | Feasibility: 9 | Confidence: HIGH**

Map the Pareto frontier of topology choices: where does single-agent beat debate? Where is hierarchical cost-justified? The empirical foundation missing from all existing work.

### GAP-004: Joint Backbone + Topology Co-optimization
**Novelty: 6 | Feasibility: 6 | Confidence: MEDIUM**

Move beyond AgentBalance's sequential backbone-then-topology to true joint optimization. Harder but potentially more impactful for large deployments.

### GAP-005: Difficulty-Aware Debate Topology Routing
**Novelty: 7 | Feasibility: 8 | Confidence: HIGH**

Focused application of difficulty-aware routing within debate variants (chain, star, fully-connected). Well-scoped for a single contribution.

## 4. Selected Topic: GAP-001

### Hypothesis

A lightweight router that estimates task difficulty and selects the cheapest multi-agent topology (single-agent, flat, debate, hierarchical) meeting a quality threshold achieves equivalent accuracy to always-debate at 40-60% lower token cost.

### Why This Gap

1. **High novelty (8/10):** AgentBalance and BAMAS exist but neither frames this as a learned per-query router. The position paper (2505.22467) explicitly calls this a research priority.
2. **High feasibility (8/10):** Topology implementations exist. Difficulty estimators exist (DAAO's VAE). Router architectures exist (RouteLLM, FrugalGPT). The contribution is the combination and validation.
3. **High impact:** Directly addresses the #1 practitioner question: "Which multi-agent setup should I use?" Applicable to every MAS deployment.
4. **ICML 2026 fit:** Systems + ML paper combining learned routing with empirical cost analysis. Aligns with ICML's interest in efficient ML systems.

### Success Criteria

- Router achieves within 2% accuracy of always-best-topology oracle
- 40-60% token cost reduction vs always-debate baseline
- Generalizes across 3+ task domains (math reasoning, code generation, QA)
- Router overhead <1% of total inference cost
- Pareto-dominates AgentBalance and BAMAS baselines under matched budgets

### Venue Target

ICML 2026 (submission deadline ~Feb 2026, notification ~May 2026)

### Proposed Method Sketch

1. **Cost Profiling Phase:** Run 4 topologies (single, flat, debate, hierarchical) on standard benchmarks. Record (task, topology, quality, token_cost) tuples.
2. **Difficulty Estimator:** Train VAE-based estimator (following DAAO) on task descriptions.
3. **Topology Router:** Train lightweight classifier mapping difficulty features to cheapest-meeting-threshold topology. Use FrugalGPT-style cascade as fallback.
4. **Cost Guarantee Module:** Optional conformal prediction layer (from C3PO) to bound P(cost > budget).
5. **Evaluation:** Compare against always-debate, always-best-fixed, AgentBalance, BAMAS, random, and oracle baselines.
