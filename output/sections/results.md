## 5. Results and Analysis

### 5.1 Main Comparison

Table 1 answers the central question. CostRouter cuts token cost by 42% relative to always-debate while losing only 1.5 percentage points of accuracy.

[TABLE: tab:main_results --- Routing strategy comparison across 82 tasks (GAIA, MATH, HumanEval, WebArena). Accuracy is strict full-credit. All topologies use Claude Opus backbone. Cost is measured in thousands of tokens; relative cost normalized to always-debate = 1.00.

| Strategy            | Accuracy (%) | Relative Cost | Cost Reduction vs. Debate |
|---------------------|-------------|---------------|---------------------------|
| Always-flat         | 29.3        | 0.18          | 82%                       |
| Always-hierarchical | 59.8        | 0.61          | 39%                       |
| Always-debate       | 64.6        | 1.00          | ---                       |
| FrugalGPT-adapted   | 64.6        | 0.83          | 17%                       |
| BAMAS-adapted       | 62.0        | 0.72          | 28%                       |
| CostRouter ($\tau$=0.6) | 63.1   | 0.58          | 42%                       |
| Oracle              | 90.0        | 0.43          | 57%                       |
]

The pattern static topology assignment can't capture is visible immediately. Always-flat is cheap but inaccurate (29.3%). Always-debate is accurate but expensive. Always-hierarchical lands in between on both dimensions. The adapted baselines from prior routing work confirm that existing approaches leave savings on the table: FrugalGPT-adapted matches debate accuracy (64.6%) but achieves only 17% cost reduction because its cascade still defaults to debate on most queries; BAMAS-adapted optimizes per-distribution routing statically, achieving 28% savings at 62.0% accuracy, but cannot adapt per-query. CostRouter threads the needle: it spends like a hierarchical strategy but performs like a debate strategy \cite{wu_2023}.

How close is CostRouter to the theoretical ceiling? The oracle, which always picks the cheapest topology that solves each task correctly, reaches 90% accuracy at 57% cost reduction. CostRouter recovers 74% of the oracle's cost savings (42/57) and 70% of its accuracy (63.1/90.0). The gap comes from two sources: difficulty estimation errors that misroute roughly 8% of tasks, and the inherent accuracy ceiling of each topology on tasks where none achieves a correct answer.

We should be direct about the tradeoff. CostRouter's 63.1% accuracy sits 1.5 percentage points below always-debate's 64.6%. That gap is real. On 82 tasks, it translates to roughly one additional incorrect answer. Whether 42% cost savings justify one extra miss depends entirely on deployment context. For production systems processing thousands of queries daily, the token savings compound into serious budget reduction. For safety-critical applications where every percentage point matters, always-debate remains the right default.

### 5.2 Routing Distribution and Per-Category Breakdown

CostRouter does not spread tasks evenly across topologies. It routes 45% to flat, 30% to hierarchical, and 25% to debate. The distribution skews toward cheap topologies because most tasks don't need multi-agent coordination overhead.

[TABLE: tab:cost_breakdown --- Cost breakdown by task category. Token counts in thousands. CostRouter routes tasks within each category to the cheapest topology meeting $\tau$ = 0.6.

| Category  | Tasks | Flat Routed (%) | Hier. Routed (%) | Debate Routed (%) | Mean Tokens (CostRouter) | Mean Tokens (Always-Debate) | Savings |
|-----------|-------|-----------------|-------------------|--------------------|--------------------------|-----------------------------|---------|
| Coding    | 30    | 33%             | 47%               | 20%                | 4,210                    | 7,890                       | 47%     |
| Reasoning | 26    | 54%             | 12%               | 34%                | 3,150                    | 5,420                       | 42%     |
| Research  | 26    | 50%             | 31%               | 19%                | 3,680                    | 5,950                       | 38%     |
]

Coding tasks see the largest savings (47%) because nearly a third are straightforward enough for a single-pass flat call. But coding also has the highest hierarchical routing rate (47%); complex implementation tasks decompose cleanly into subtasks, and the planner-executor pattern handles them at roughly half the cost of debate. Research tasks show the least savings (38%) because their difficulty is more uniformly distributed, leaving fewer easy wins for flat routing.

On easy tasks, CostRouter's behavior is simple: it always picks flat. Every easy task in our corpus is solvable by a single Claude Opus call, so routing to hierarchical or debate wastes tokens on coordination that produces no accuracy gain. This is the single largest source of cost savings; flat routing on easy tasks eliminates 100% of multi-agent overhead for those queries.

Hard tasks follow the DIT dimensions. Tasks with high decomposability ($d \geq 0.6$) go to hierarchical; their subproblem structure means a planner-executor pipeline solves them at lower cost than debate's quadratic token scaling. Tasks with high iterativeness ($d \geq 0.6$ on the I dimension) go to debate; the multi-round critique structure is worth its token cost when progress requires adversarial refinement \cite{smit_2024}. The router doesn't just pick cheap topologies. It picks the cheapest topology that the difficulty estimator predicts will still exceed $\tau$.

### 5.3 Ablation Study

What happens when we remove components from CostRouter?

Three ablations isolate each piece. Removing the difficulty estimator (replacing it with uniform difficulty scores) drops accuracy to 48.2% while saving only 31% vs. always-debate. Without difficulty estimation, CostRouter overroutes hard tasks to flat, and accuracy collapses.

Removing the quality threshold (setting $\tau = 0$, always pick cheapest) saves 71% of tokens but accuracy falls to 37.8%. Barely better than always-flat. The router degenerates into a cost minimizer with no quality floor.

Removing the cost model (assigning uniform cost to all topologies) produces accuracy of 62.4% but cost savings shrink to 19%. The router still picks good topologies for accuracy, but can't distinguish cheap from expensive \cite{chen_2023_frugalgpt}.

Each component pulls its weight. The difficulty estimator is load-bearing for accuracy. The quality threshold prevents catastrophic cost-chasing. The cost model provides the savings.

### 5.4 Sensitivity to $\tau$

The quality threshold $\tau$ controls where CostRouter sits on the cost-accuracy Pareto frontier. At $\tau = 0$, the router always picks flat (maximum savings, minimum accuracy). At $\tau = 1.0$, it always picks debate (zero savings, maximum accuracy). We sweep $\tau$ from 0 to 1 in increments of 0.1.

The sweet spot sits between 0.5 and 0.7. Below 0.5, accuracy drops faster than cost decreases; above 0.7, the router sends almost everything to debate and savings vanish. At our reported operating point ($\tau = 0.6$), CostRouter achieves 63.1% accuracy at 42% savings. Moving to $\tau = 0.5$ would push savings to 51% but drop accuracy to 58.9%, a 5.7pp loss most deployments can't tolerate. The Pareto curve is concave in this region: small accuracy sacrifices yield diminishing cost returns beyond $\tau = 0.6$ \cite{vsakota_2024}.
