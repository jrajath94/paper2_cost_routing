## 6. Discussion

### 6.1 Practical Deployment

CostRouter is designed as middleware: it sits between the user query stream and the topology execution backends. Queries arrive, the difficulty estimator runs a forward pass through a small classifier, the routing policy consults pre-computed cost-quality curves, and the selected topology receives the query. Total routing latency is under 50ms, negligible compared to the seconds or minutes that multi-agent topologies spend on execution.

What makes this practical is that CostRouter requires no changes to existing topology implementations. Organizations already running flat, hierarchical, or debate pipelines can drop it in front as a dispatcher. The cost model parameters (agents, rounds, depth, context growth) are configured once per topology and updated only when the topology pool changes. The difficulty estimator is the only component that needs periodic recalibration as the task distribution shifts \cite{wu_2023}.

### 6.2 Connection to Model-Level Routing

Chen et al.'s FrugalGPT \cite{chen_2023_frugalgpt} showed that routing queries to cheaper LLMs saves 50-90% of API cost at matched quality. RouteLLM \cite{ong_2024} extended this with learned routing policies. CostRouter operates at a different level of the stack. Where FrugalGPT asks "which model?", CostRouter asks "which structure?" The two are complementary, not competing.

Consider a deployment with three models (GPT-4o, GPT-4o-mini, Claude Sonnet) and three topologies (flat, hierarchical, debate). FrugalGPT alone searches a 3-model space. CostRouter alone searches a 3-topology space. Joint model-topology routing searches a 9-cell grid, and the cost differences across that grid span two orders of magnitude. A flat call to GPT-4o-mini costs roughly 1/50th of a debate topology with GPT-4o. Neither routing axis alone captures this full range.

So why didn't we implement joint routing? Scope. The topology cost algebra assumes a fixed backbone, and our difficulty estimator was trained on single-backbone data. Extending both to handle model-topology pairs requires a cost model over the full grid and training data for each cell. This is tractable but doubles the experimental surface; we leave it as the most obvious next step \cite{vsakota_2024}.

### 6.3 Limitations

We count five, and they matter.

First, all experiments use a single backbone (Claude Opus 4.6). The topology cost algebra's structural predictions should generalize across backbones since the cost multipliers depend on topology structure, not model identity. But the difficulty estimator's routing decisions are trained on Claude Opus 4.6 performance data and may not transfer. Running CostRouter with open-source backbones remains an open validation \cite{cemri_2025}.

Second, the quality threshold $\tau$ requires calibration data: tasks with known topology-accuracy pairs. In cold-start deployments with no historical data, $\tau$ must be set conservatively (high, defaulting to debate) and refined as data accumulates. We did not test online calibration strategies.

Third, 82 tasks across four benchmarks is enough to demonstrate the routing pattern but not enough to claim statistical precision on subgroup effects. The per-category breakdowns in Table 2 should be read as directional, not definitive. A production deployment would accumulate thousands of routing decisions and enable tighter estimates.

Fourth, CostRouter makes a single routing decision per query and commits to it. Real tasks evolve. A coding task might start as a clean decomposition problem (route to hierarchical) but reveal unexpected cross-module dependencies mid-execution that would be better handled by debate. Mid-task topology switching is architecturally possible but requires checkpointing agent state and transferring context. We don't attempt this \cite{kim_2024}.

Fifth, the cost algebra assumes fixed token prices. API providers change pricing, batch discounts apply, and self-hosted models have different cost structures entirely. The cost model's relative ordering of topologies is more stable than its absolute predictions; as long as flat remains cheaper than hierarchical, which remains cheaper than debate, routing decisions stay correct even if the magnitudes shift \cite{chen_2023_frugalgpt}.

### 6.4 Future Directions

Joint model-topology routing is the clearest extension. Can a single router simultaneously pick the cheapest model and the cheapest topology that together meet a quality floor? The search space grows multiplicatively, but the cost algebra decomposes: model cost and topology multiplier are roughly independent, so the joint cost is their product. A factored routing policy could search efficiently without exhaustive enumeration.

Beyond fixed topology pools, adaptive thresholds that adjust $\tau$ based on recent routing performance could prevent accuracy drift in non-stationary task distributions. Online learning from deployment feedback (each routed query produces a ground-truth accuracy signal) would let CostRouter refine its difficulty estimator continuously without manual recalibration \cite{ong_2024, aflow_2025}.

The topology cost algebra itself may generalize to new topology designs. Any multi-agent pattern with well-defined agent count, round count, and context growth can be slotted into the algebra and immediately become a routing candidate. Design a topology, plug in its cost parameters, and let CostRouter decide when to use it.
