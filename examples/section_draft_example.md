# Example Section Draft: Introduction

> **NOTE:** This is a few-shot example for the section-writer agent. The content is fictional but demonstrates proper citation density, argumentation flow, and self-assessment format.

---

## Section: Introduction

**Target word count:** 500
**Citation density target:** 2-3 citations per paragraph
**Key arguments to cover:**
1. LLM agents are increasingly used for complex tasks but orchestration remains ad hoc
2. Existing multi-agent frameworks lack principled task decomposition
3. Our contribution: a hierarchical orchestration framework with formal guarantees

---

## Draft

Large language model agents have demonstrated remarkable capabilities across diverse tasks, from code generation \cite{chen2021codex} to scientific reasoning \cite{taylor2022galactica}. As individual agent capabilities have matured, the research community has shifted attention to multi-agent systems where specialized agents collaborate on complex tasks that exceed any single agent's capacity \cite{wu2023autogen, chen2023agentverse}. This shift mirrors the broader trajectory of distributed computing: individual processors reached practical limits, and the field turned to principled orchestration of many processors working in concert.

Despite this growing interest, current multi-agent LLM frameworks rely on ad hoc orchestration strategies. AutoGen \cite{wu2023autogen} uses static conversation patterns where developers manually specify which agents communicate and in what order. CrewAI \cite{joao2024crewai} assigns fixed roles without adapting to task complexity. MetaGPT \cite{hong2023metagpt} encodes software engineering workflows directly into agent pipelines, limiting generalizability to other domains. These approaches work for well-understood task types but break down when the task structure is unknown at design time -- precisely the setting where multi-agent systems should provide the most value.

The core challenge is task decomposition under uncertainty. Given a complex task with unknown structure, how should an orchestrator decompose it into subtasks, assign agents to subtasks, and coordinate their outputs? This problem has deep roots in distributed systems \cite{lynch1996distributed} and hierarchical planning \cite{nau2003shop2}, but existing solutions assume known task schemas. In the LLM agent setting, both the task space and the agent capability space are open-ended, making classical approaches insufficient.

We address this gap with HARMONY (Hierarchical Agent oRchestration with MOdular decomposition and dYnamic assignment), a framework that decomposes tasks into a hierarchy of subtasks, dynamically spawns specialized agents for each subtask, and coordinates their outputs through a formal communication protocol. Unlike prior work, HARMONY does not require pre-specified agent roles or conversation patterns. Instead, it uses a lightweight meta-agent to analyze task structure, determine the appropriate decomposition granularity, and select agent configurations from a capability registry. Our key contributions are:

1. A formal model of hierarchical task decomposition for LLM agents that provides completeness guarantees under stated assumptions (Section 3).
2. A dynamic agent spawning mechanism that adapts the number and specialization of agents to task complexity, reducing token costs by 40\% on simple tasks while maintaining performance on complex ones (Section 4).
3. Comprehensive evaluation across four domains -- code generation, mathematical reasoning, web navigation, and open-ended research -- demonstrating consistent improvements over static orchestration baselines (Section 5).

---

## Self-Assessment

**Quality (1-10):** 7
Justification: Claims are clearly stated and the contribution list is specific. The comparison to distributed systems provides grounding. Weakness: the "formal guarantees" claim needs to be carefully supported in Section 3 -- overpromising here could hurt credibility.

**Clarity (1-10):** 8
Justification: Logical flow from individual agents -> multi-agent -> orchestration challenge -> our solution. The distributed computing analogy helps accessibility. The acronym HARMONY is a bit forced but memorable.

**Originality (1-10):** 7
Justification: The framing of orchestration as hierarchical decomposition under uncertainty is novel. Individual components (meta-agents, dynamic spawning) exist but their formal combination is new.

**Significance (1-10):** 6
Justification: Addresses a real problem but the introduction doesn't yet convey why this matters beyond the research community. Adding a practical impact paragraph would strengthen significance.

**Citation count:** 8
**Word count:** 487

---

## Known Weaknesses

1. The "formal guarantees" claim in contribution #1 sets high expectations -- if Section 3 delivers only empirical validation, reviewers will flag the mismatch.
2. The practical impact motivation is thin -- who benefits from better orchestration and why should practitioners care?
3. The acronym HARMONY feels contrived and might distract reviewers.

## Revision Notes

- **Review round:** 1 (initial draft)
- **Addressed feedback:** N/A (first draft)
- **Remaining issues:** See known weaknesses above

---

*Example version: 1.0*
*Demonstrates: ~500-word introduction with proper citation density and self-assessment*
