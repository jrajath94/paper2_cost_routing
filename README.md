# Cost-Aware Topology Routing

_for Multi-Agent LLM Deployments_

> Earlier formulation of the cost-quality Pareto problem in multi-agent orchestration. Argues that simpler topologies are cost-optimal for easy tasks and expensive multi-agent topologies only justify their cost on hard tasks where the quality gap is large.

**Target venue:** [NeurIPS 2026 (workshop track)](https://neurips.cc/Conferences/2026)  •  **Status:** Submission package compiled (PDF: 98 KB)

---

## 📋 Headline Numbers

| Metric | Value |
|---|---|
| Target cost reduction | 40-60% |
| Quality preservation target | ≥95% of peak success rate |
| Position in series | Companion to Paper 4 (ParetOrch — fully developed version) |

## 📄 Abstract (excerpt)

Treats multi-agent topology selection as a cost-quality Pareto problem. The right topology depends not just on task difficulty but on the marginal cost of capability — a question prior work largely ignores by assuming compute is free or fixed.

## 🤖 Independent Review (Sakana AI Scientist v2)

This paper has been reviewed by [Sakana AI Scientist v2](https://github.com/SakanaAI/AI-Scientist-v2)'s `perform_llm_review` module via the MiniMax-M2.7 backend. The review uses NeurIPS-style reviewer guidelines.

| Metric | Score |
|---|---|
| Overall | **6** / 10 |
| Decision | **Accept** |
| Soundness | 3 / 4 |
| Confidence | 3 / 5 |

**Top weaknesses identified:**

- Single backbone evaluation (Claude Opus 4.6) - generalization to other LLMs unvalidated
- Small test set (22 tasks) with single-run evaluation - insufficient statistical power for precise claims
- Difficulty estimator achieves only 84% accuracy on binary easy/hard split, trained on 282 examples
- Large accuracy gap between Oracle (90%) and CostRouter (63.1%) suggests significant routing error
- Cold-start problem for τ calibration not adequately addressed

> _Full review JSON: [`ai_scientist/reviews/minimax_review.json`](ai_scientist/reviews/minimax_review.json)._

## 🔬 Reproducibility

```bash
# Clone
git clone https://github.com/jrajath94/paper2_cost_routing.git
cd paper2_cost_routing

# Recompile the PDF (needs Tectonic or pdflatex)
tectonic output/paper.tex   # produces output/paper.pdf

# Browse the materials:
#   output/sections/   — per-section markdown + .tex
#   output/figures/    — figures (PDF + PNG)
#   output/reviews/    — citation, data, math, figure, AI-pattern audits
#   experiments/       — task suite + results JSON
#   ai_scientist/      — Sakana AI Scientist v2 review pipeline outputs
```


## 📁 Repository Layout

```
paper2_cost_routing/
├── README.md              ← you are here
├── paper.pdf              ← compiled PDF
├── output/                ← LaTeX source, sections, figures, reviews, bibliography
│   ├── paper.tex / main.tex
│   ├── sections/
│   ├── figures/
│   ├── reviews/           (audits: citation, data, math, figure, consistency, AI patterns)
│   └── bibliography.bib / references.bib
├── experiments/           ← task suite + results data
├── scripts/               ← pipeline scripts (literature retrieval, citation verification, etc.)
├── ai_scientist/          ← Sakana AI Scientist v2 outputs (independent review JSON)
├── state/                 ← paper state and pipeline log
└── venues/                ← venue configs (NeurIPS / TMLR / JAIR formatting rules)
```

## 🛠️ Tooling

This paper was developed with a custom multi-agent research pipeline using:
- **Claude Opus 4.6 / Sonnet 4.6** (via [Claude Code](https://www.anthropic.com/claude-code)) — main author + reviewer agents
- **Sakana AI Scientist v2** — independent NeurIPS-style review
- **MiniMax-M2.7** — bulk-pass review and ideation calls
- **Tectonic** — LaTeX compilation
- **Semantic Scholar / OpenAlex / CrossRef** APIs for citation verification

## 📚 Part of the Multi-Agent Orchestration paper series

| # | Repo | Title | Venue |
|---|---|---|---|
| 1 | [`paper1_orchestrabench`](https://github.com/jrajath94/paper1_orchestrabench) | OrchestraBench: which topology fits which task? | NeurIPS 2026 |
| 2 | [`paper2_cost_routing`](https://github.com/jrajath94/paper2_cost_routing) | Cost-Aware Topology Routing | NeurIPS 2026 (W) |
| 3 | [`paper3_failure_planning`](https://github.com/jrajath94/paper3_failure_planning) | Failure-Aware Planning for LLM Agents | TMLR |
| 4 | [`paper4_paretorch`](https://github.com/jrajath94/paper4_paretorch) | ParetOrch: Cost-Quality Pareto Optimization | NeurIPS 2026 |
| 5 | [`paper5_adaptswitch`](https://github.com/jrajath94/paper5_adaptswitch) | AdaptSwitch: Runtime Topology Switching | JAIR |

## 📜 License

Code: MIT.  Paper text and figures: CC BY 4.0.

## 🤝 Citation

If you use this work, please cite (BibTeX entries to be finalized at submission):

```bibtex
@article{paper2_cost_routing_2026,
  title  = {Cost-Aware Topology Routing: for Multi-Agent LLM Deployments},
  author = {Rajath, J.},
  year   = {2026},
  journal= {Under review at NeurIPS 2026 (workshop track)},
}
```
