## 3. CostRouter: Topology-Level Cost Routing

Section 1 argued that topology cost is structural and predictable. This section makes that claim precise. We formalize the cost algebra (Section 3.1), build a difficulty estimator for per-query routing (Section 3.2), describe the CostRouter architecture (Section 3.3), define the quality threshold mechanism (Section 3.4), and prove a bound on cost savings (Section 3.5).

### 3.1 Topology Cost Algebra

Every multi-agent topology induces a token flow pattern. Tokens flow between agents as messages, accumulate in context windows, and multiply through rounds of interaction. The total token cost depends on three structural parameters: the number of agents $N$, the decomposition depth $D$ (for hierarchical topologies), and the number of interaction rounds $R$ (for debate topologies). We derive cost formulas by tracing token flow through each topology class.

**Flat topology.** A single agent executes the task in a ReAct-style loop. One context window, one stream of generation. The token cost is simply the base cost of processing the query and generating a response:

$$C_{\text{flat}} = c_{\text{base}}$$

where $c_{\text{base}}$ denotes total tokens (input plus output) for a single-agent execution. This is our cost unit; all other topologies express cost as multiples of $c_{\text{base}}$.

**Hierarchical topology.** A coordinator agent receives the task, decomposes it into subtasks, and dispatches each to a specialist. Each specialist processes its subtask independently. At decomposition depth $D = 1$, the coordinator pays $c_{\text{base}}$ for planning and each of $N$ specialists pays $c_{\text{base}}$ for execution. But real hierarchical pipelines go deeper: a specialist may further decompose its subtask, creating $D$ levels of fan-out. At each level, the coordinator's context grows because it must track all outstanding subtasks. Summing across levels:

$$C_{\text{hier}} = c_{\text{base}} \cdot N \cdot D$$

Why linear in both $N$ and $D$? The tree structure keeps branches roughly independent, so costs add rather than multiply. Coordinator overhead (planning, dispatching, aggregating) is absorbed into the per-level cost since each level requires a coordinator pass. We validate this empirically in Section 5.1; the linear model fits actual token counts with $R^2 = 0.96$.

**Debate topology.** $N$ agents each propose solutions, then critique each other's proposals across $R$ rounds. In each round, every agent reads every other agent's output from the previous round. This creates quadratic token flow: each of $N$ agents reads $N - 1$ messages per round, and the context window grows with each round as the full debate history accumulates:

$$C_{\text{debate}} = c_{\text{base}} \cdot N^2 \cdot R$$

Why $N^2$ and not $N(N-1)$? Each agent also re-reads its own prior output in context, and the judge agent (if present) reads all $N$ outputs per round. The $N^2$ approximation is tight. With $N = 3$ agents and $R = 4$ rounds, debate costs $36 \cdot c_{\text{base}}$. That is the 24x figure from the introduction adjusted for $N^2$ rather than $N$; with a two-proposer-plus-judge setup ($N = 3$, effective pairs = 3), the realized cost lands at $\sim 24$-$36 \times c_{\text{base}}$ depending on judge verbosity.

Three properties of this algebra matter for routing. First, the formulas depend only on topology structure ($N$, $D$, $R$), not on the backbone LLM or the specific query. Cost multipliers are known before execution. Second, the ordering is stable: for any fixed $c_{\text{base}}$, flat $<$ hierarchical $<$ debate whenever $N \cdot D < N^2 \cdot R$. Third, the cost gap grows with structural parameters. A debate with $N = 5, R = 6$ costs $150 \times c_{\text{base}}$. Flat costs $1 \times c_{\text{base}}$. The potential savings from routing to the right topology are enormous.

### 3.2 Difficulty Estimation

CostRouter needs to predict, before execution, whether a query requires a complex topology or whether flat execution suffices. We frame this as difficulty estimation: mapping each query to a score $d \in [0, 1]$, where $d = 0$ means flat will almost certainly succeed and $d = 1$ means only the most complex topology has a reasonable chance. This is related to query difficulty estimation in RouteLLM \cite{ong_2025}, but lifted from model selection to topology selection.

We use a lightweight classifier trained on features from the D-I-T task characterization framework of OrchestraBench \cite{orchestrabench_2026}. Each task in the training set has known D (decomposability), I (iterativeness), and T (tool diversity) scores, plus observed accuracy under each topology. The classifier takes as input a feature vector extracted from the query text:

- **Lexical complexity:** sentence count, average sentence length, vocabulary richness (type-token ratio)
- **Structural indicators:** count of explicit subtask markers ("first," "then," "finally"), presence of conditional logic ("if," "unless"), enumerated constraints
- **Domain signals:** tool keywords (code, search, calculate, navigate), domain vocabulary density

These features are cheap to compute. No LLM call is needed. A two-layer MLP with 64 hidden units maps the feature vector to a difficulty score $d$. Training data comes from the 82 OrchestraBench tasks with known per-topology accuracy; we augment with 200 synthetic variations generated by paraphrasing task descriptions while preserving D-I-T annotations.

Is a classifier trained on 282 examples accurate enough? We address this in Section 5.4 with calibration analysis. The short answer: difficulty estimation doesn't need to be perfect. It needs to be good enough to separate easy queries (where flat suffices) from hard ones (where debate pays for itself). Binary separation is easier than fine-grained difficulty regression, and our classifier achieves 84\% accuracy on the easy-vs-hard split using leave-one-out cross-validation.

### 3.3 CostRouter Architecture

CostRouter takes three inputs: a query $q$, a topology pool $\mathcal{T} = \{t_1, \ldots, t_K\}$, and a quality threshold $\tau \in [0, 1]$. It outputs the selected topology $t^*$ that minimizes expected cost subject to expected accuracy meeting $\tau$.

Two stages.

**Stage 1: Accuracy prediction.** For each topology $t_i \in \mathcal{T}$, CostRouter estimates the expected accuracy $\hat{a}_i(q)$ of running query $q$ under topology $t_i$. This uses the difficulty score $d(q)$ from Section 3.2 combined with pre-computed accuracy profiles per topology. Each topology has an accuracy function $a_i(d)$ learned from training data: accuracy as a function of difficulty. For flat, accuracy drops steeply with difficulty. For debate, it degrades more gracefully. These profiles are monotonically decreasing functions estimated via isotonic regression on the training set.

**Stage 2: Cost-constrained selection.** CostRouter filters topologies whose predicted accuracy falls below $\tau$: the candidate set is $\mathcal{T}_\tau = \{t_i \mid \hat{a}_i(q) \geq \tau\}$. Among candidates, it selects the cheapest:

$$t^* = \arg\min_{t_i \in \mathcal{T}_\tau} C(t_i)$$

where $C(t_i)$ is the cost from the topology cost algebra (Section 3.1). If no topology meets the threshold ($\mathcal{T}_\tau = \emptyset$), CostRouter defaults to the topology with highest predicted accuracy regardless of cost.

<!-- Figure: CostRouter architecture diagram (to be generated) -->

The entire routing decision requires one forward pass through a two-layer MLP and $K$ lookups into pre-computed accuracy curves. For $K = 3$ topologies, this takes under 2 milliseconds on CPU. Zero LLM tokens consumed for the routing itself, and the computational overhead is negligible relative to whatever multi-agent execution follows.

**Algorithm 1: CostRouter Routing**

```
Input: query q, topology pool T = {t_1, ..., t_K}, threshold tau
Output: selected topology t*

1. Extract features x from q (lexical, structural, domain)
2. Compute difficulty score d = MLP(x)
3. For each t_i in T:
     Predict accuracy: a_hat_i = accuracy_profile_i(d)
     Compute cost: c_i = cost_algebra(t_i)
4. Filter: T_tau = {t_i | a_hat_i >= tau}
5. If T_tau is empty:
     Return argmax_i a_hat_i
6. Return argmin_{t_i in T_tau} c_i
```

### 3.4 Quality Threshold Selection

The threshold $\tau$ controls where CostRouter operates on the cost-accuracy Pareto frontier. High $\tau$ (say 0.95) means CostRouter will only route to cheap topologies when it is very confident they will succeed; this is conservative, saving cost only on the easiest queries. Low $\tau$ (say 0.70) allows aggressive cost-cutting, routing more queries to flat at the risk of accuracy loss on borderline cases.

How should a practitioner choose $\tau$? We propose selecting it from the Pareto frontier of cost versus accuracy on a validation set. Sweep $\tau$ from 0.5 to 1.0 in increments of 0.05. At each value, compute average cost and average accuracy of CostRouter's routing decisions. Plot the resulting curve. The Pareto-optimal points are those where no other $\tau$ achieves both lower cost and higher accuracy. The practitioner picks the point that matches their preference.

This is analogous to threshold selection in FrugalGPT \cite{chen_2023}, where a confidence threshold controls when to cascade to a more expensive model, and to the boundary-guided training of BAMAS \cite{zhang_2026}, which learns routing policies under explicit budget constraints. The key difference: CostRouter's threshold operates over topology families rather than model tiers, and the cost axis spans a much wider range (1x to 36x rather than 2x to 3x between model tiers).

We find empirically (Section 5.4) that the Pareto frontier is convex and well-behaved, with a clear "knee" around $\tau = 0.5$. Below this knee, accuracy drops faster than cost decreases. Above it, savings diminish as the router sends most queries to expensive topologies. The sweet spot sits between $\tau = 0.5$ and $\tau = 0.7$, with our reported operating point at $\tau = 0.6$.

### 3.5 Theoretical Cost Savings Bound

Can we bound how close CostRouter gets to oracle routing? The oracle selects, with perfect hindsight, the cheapest topology that actually succeeds on each query. No real system can match the oracle because difficulty estimation is imperfect. But we can characterize the gap.

**Theorem 1.** Let $\alpha$ denote the accuracy of the difficulty estimator on the binary easy/hard classification (i.e., the probability that CostRouter correctly identifies whether flat topology suffices). Let $C_{\text{oracle}}$ denote the oracle's total cost across a query set $Q$, and $C_{\text{router}}$ denote CostRouter's total cost. Let $\gamma = \max_{t_i, t_j \in \mathcal{T}} C(t_i) / C(t_j)$ be the maximum cost ratio between any two topologies in the pool. Then:

$$C_{\text{router}} \leq C_{\text{oracle}} + (1 - \alpha) \cdot \gamma \cdot |Q| \cdot c_{\text{base}}$$

*Proof sketch.* When the difficulty estimator is correct (probability $\alpha$), CostRouter makes the same selection as the oracle. When incorrect (probability $1 - \alpha$), the worst case is routing to the most expensive topology when the cheapest would have sufficed, paying an excess of at most $\gamma \cdot c_{\text{base}}$ per query. Summing over $|Q|$ queries yields the bound.

In practical terms: with $\alpha = 0.84$ (our classifier's accuracy), $\gamma = 36$ (debate-to-flat cost ratio), and 82 queries, the bound says CostRouter's excess cost over oracle is at most $16\% \cdot 36 \cdot 82 \cdot c_{\text{base}} \approx 472 \cdot c_{\text{base}}$. The oracle's total cost across 82 queries is roughly $400\text{-}600 \cdot c_{\text{base}}$ (since it routes most queries to flat), so the bound is loose. The empirical gap is much tighter: CostRouter achieves within $(1 + \epsilon)$ of oracle cost with $\epsilon \approx 0.08\text{-}0.12$ across our benchmarks (Section 5.2).

The bound tightens as $\alpha$ increases and as $\gamma$ decreases (i.e., with more moderate topology cost ratios). It also points to a clear improvement path: better difficulty estimation directly translates to cost savings. Every percentage point improvement in $\alpha$ reduces excess cost proportionally.

One subtlety worth flagging: the bound assumes the accuracy profiles from Section 3.3 are well-calibrated. If predicted accuracy systematically overestimates a topology's capability, CostRouter will over-route to cheap topologies and miss the quality threshold. Section 5.4 verifies calibration empirically with reliability diagrams.
