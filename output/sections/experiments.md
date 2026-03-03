## 4. Experimental Setup

We designed experiments to answer four questions. Can the topology cost algebra predict actual token costs from structure alone (RQ1)? Does per-query routing outperform static topology assignment (RQ2)? How close to the oracle Pareto frontier does CostRouter get (RQ3)? And how does routing performance degrade when the difficulty estimator is noisy (RQ4)?

### 4.1 Task Suite

We reuse the 82-task corpus from OrchestraBench \cite{orchestrabench_2026}: 30 coding tasks, 26 reasoning tasks, and 26 research tasks spanning easy and hard difficulty tiers. Each task has ground-truth D-I-T annotations (decomposability, iterativeness, tool diversity) and known per-topology accuracy from controlled single-run evaluations under flat, hierarchical, and debate topologies. That gives us 246 task-topology observations for training the difficulty estimator and accuracy profiles, plus 36 additional observations from a secondary backbone check on easy tasks.

We split the 82 tasks into training (60) and test (22) using stratified sampling to preserve category and difficulty proportions. The difficulty estimator and accuracy profiles are trained on the 60-task split. All reported results use the 22-task held-out set unless noted otherwise. Leave-one-out cross-validation over all 82 tasks is reported in Section 5.4 for calibration analysis.

### 4.2 Topology Candidates

CostRouter selects among three topology families, matching the OrchestraBench implementations:

- **Flat:** single ReAct-style agent in a tool-use loop. Cost: $c_{\text{base}}$.
- **Hierarchical:** planner-worker pipeline with $N = 3$ specialist agents and decomposition depth $D = 2$. Cost: $6 \cdot c_{\text{base}}$.
- **Debate:** two proposer agents plus a judge, running $R = 4$ rounds. Cost: $\sim 24\text{-}36 \cdot c_{\text{base}}$ depending on judge verbosity.

All topologies share the same backbone, tool suite, and token budget. The only variable is the orchestration structure.

### 4.3 Baselines

Six baselines span the space from naive static assignment to oracle hindsight:

- **Always-flat:** route every query to flat. Cheapest possible, but accuracy-limited on hard tasks.
- **Always-hierarchical:** route everything to hierarchical. Moderate cost, strong on decomposable tasks.
- **Always-debate:** route everything to debate. Most expensive, strongest on iterative reasoning.
- **FrugalGPT-adapted:** we adapt the FrugalGPT cascade \cite{chen_2023} from model routing to topology routing. Queries start flat; if a lightweight confidence check flags low confidence, the query escalates to hierarchical, then debate. This sequential cascade adds latency but provides a natural comparison point.
- **BAMAS-adapted:** we adapt Budget-Aware Agentic Routing \cite{zhang_2026} from model selection to topology selection, using its boundary-guided training objective to learn a routing policy under a fixed total budget constraint.
- **Oracle:** selects the cheapest topology that actually succeeds on each query, computed with perfect hindsight from the full results matrix. No real system can match this.

### 4.4 Metrics

Four metrics capture the cost-quality tradeoff:

- **Total token cost:** sum of tokens consumed across all test queries. The primary cost metric.
- **Accuracy:** fraction of queries answered correctly. The primary quality metric.
- **Cost-per-correct:** total token cost divided by correct answers. This penalizes methods that spend tokens on queries they ultimately get wrong.
- **Pareto efficiency:** area under the cost-accuracy Pareto curve when sweeping $\tau$. Higher means better cost-quality tradeoff across the full range of operating points.

### 4.5 Implementation Details

All experiments use Claude Opus 4.6 as the backbone LLM, consistent with the OrchestraBench protocol. Temperature is 1.0 (Claude default). Each topology wrapper enforces a 128K token generation budget within a 1M token context window. We record per-query token counts (input plus output), wall-clock time, and success/failure outcomes.

CostRouter's difficulty estimator is a two-layer MLP (64 hidden units, ReLU activation, dropout 0.2) trained for 100 epochs with Adam (learning rate $10^{-3}$). Training takes under 30 seconds on a single CPU core. Accuracy profiles per topology are estimated via isotonic regression on the training split. The quality threshold $\tau$ is selected from the Pareto frontier on a 10-task validation subset held out from the 60-task training split.

A note on statistical power: we run each method once on the 22-task test set. This is a single-run evaluation, consistent with the original OrchestraBench study. We can't report confidence intervals or significance tests from one trial per condition. The results establish directional effects and cost-accuracy tradeoffs; precise magnitudes require future replication with multiple seeds. We do report 95\% bootstrap confidence intervals on cost-per-correct by resampling over tasks.
