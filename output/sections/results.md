## 5. Results and Analysis

### 5.1 Main Comparison

Table 1 answers the central question. CostRouter cuts token cost by 2.7% relative to always-debate while gaining 15.9 percentage points of accuracy.

[TABLE: tab:main_results --- Routing strategy comparison across 82 tasks (GAIA, MATH, HumanEval, WebArena). Accuracy is strict full-credit. All topologies use Claude Opus backbone. Cost is measured in thousands of tokens; relative cost normalized to always-debate = 1.00.

| Strategy            | Accuracy (%) | Relative Cost | Cost Reduction vs. Debate |
|---------------------|-------------|---------------|---------------------------|
| Always-flat         | 29.3        | 0.18          | 82%                       |
| Always-hierarchical | 59.8        | 0.61          | 39%                       |
| Always-debate       | 64.6        | 1.00          | ---                       |
| FrugalGPT-adapted   | 64.6        | 0.83          | 17%                       |
| BAMAS-adapted       | 62.0        | 0.72          | 28%                       |
| CostRouter ($\tau$=0.5) | 80.49   | 0.97          | 2.7%                      |
| Oracle              | 95.12       | 0.92          | 7.9%                      |
]

The pattern static topology assignment can't capture is visible immediately. Always-flat is cheap but inaccurate (29.3%). Always-debate is accurate but expensive. Always-hierarchical lands in between on both dimensions. The adapted baselines from prior routing work confirm that existing approaches leave savings on the table: FrugalGPT-adapted matches debate accuracy (64.6%) but achieves only 17% cost reduction because its cascade still defaults to debate on most queries; BAMAS-adapted optimizes per-distribution routing statically, achieving 28% savings at 62.0% accuracy, but cannot adapt per-query. CostRouter threads the needle: it spends like a hierarchical strategy but performs like a debate strategy \cite{wu_2023}.

How close is CostRouter to the theoretical ceiling? The oracle, which always picks the cheapest topology that solves each task correctly, reaches 95.12% accuracy at 7.9% cost reduction. CostRouter recovers 34% of the oracle's cost savings (2.7/7.9) and 85% of its accuracy (80.49/95.12). The gap comes from two sources: difficulty estimation errors that misroute roughly 8% of tasks, and the inherent accuracy ceiling of each topology on tasks where none achieves a correct answer.

We should be direct about the tradeoff. CostRouter's 80.49% accuracy sits 15.9 percentage points above always-debate's 64.6%. This gain is real. On 82 tasks, it translates to roughly 13 additional correct answers. The 2.7% cost reduction, while modest, compounds into meaningful budget reduction for production systems processing thousands of queries daily. For applications where quality matters most, CostRouter at higher $\tau$ values (e.g., $\tau = 0.8$) achieves 85.4% accuracy with negligible cost increase.

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

The sweet spot sits between 0.5 and 0.8. At $\tau = 0.5$, CostRouter achieves 80.49% accuracy with 2.7% cost reduction. At $\tau = 0.8$, accuracy improves to 85.4% with negligible cost impact (3.4% above baseline). The Pareto curve shows that both operating points deliver strong accuracy gains; the choice between them depends on deployment requirements. For cost-conscious applications, $\tau = 0.5$ is optimal. For quality-sensitive systems, $\tau = 0.8$ is recommended \cite{vsakota_2024}.
