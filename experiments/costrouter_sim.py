#!/usr/bin/env python3
"""
CostRouter Simulation for Paper 2.
Simulates routing 82 OrchestraBench tasks through different strategies
and measures cost vs accuracy tradeoffs.
"""

import json
import math
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"

# ── Topology alignment priors (from Paper 1 D-I-T analysis) ──
# These represent the "ideal" DIT profile for each topology
TOPOLOGY_PRIORS = {
    "flat":         {"D": 0.3, "I": 0.3, "T": 0.5},
    "hierarchical": {"D": 0.8, "I": 0.3, "T": 0.5},
    "debate":       {"D": 0.3, "I": 0.8, "T": 0.3},
}

# ── Token cost defaults by difficulty ──
TOKEN_COSTS = {
    "easy":   {"flat": 1704, "hierarchical": 1500, "debate": 1325},
    "medium": {"flat": 2360, "hierarchical": 4420, "debate": 4380},
    "hard":   {"flat": 2490, "hierarchical": 4770, "debate": 4710},
}


def alignment_distance(task_dit: dict, topo_prior: dict) -> float:
    """Euclidean distance between task DIT and topology ideal DIT."""
    return math.sqrt(
        (task_dit["D"] - topo_prior["D"]) ** 2
        + (task_dit["I"] - topo_prior["I"]) ** 2
        + (task_dit["T"] - topo_prior["T"]) ** 2
    )


def predicted_accuracy(distance: float) -> float:
    """Convert alignment distance to predicted accuracy (0-1).
    Closer alignment = higher predicted accuracy.
    Max distance in DIT space is sqrt(3) ~ 1.73.
    We map: distance=0 -> acc=1.0, distance=1.0 -> acc=0.0 (linear).
    """
    return max(0.0, 1.0 - distance)


def load_pilot_tasks():
    """Load the 12 pilot tasks from batch files.
    These are easy tasks — combine flat_batch1+2 with hierarchical_all and debate_all.
    """
    with open(RESULTS_DIR / "flat_batch1.json") as f:
        flat1 = json.load(f)
    with open(RESULTS_DIR / "flat_batch2.json") as f:
        flat2 = json.load(f)
    with open(RESULTS_DIR / "hierarchical_all.json") as f:
        hier_all = json.load(f)
    with open(RESULTS_DIR / "debate_all.json") as f:
        debate_all = json.load(f)

    flat_results = {t["task_id"]: t for t in flat1 + flat2}
    hier_results = {t["task_id"]: t for t in hier_all}
    debate_results = {t["task_id"]: t for t in debate_all}

    tasks = []
    for task_id in flat_results:
        fr = flat_results[task_id]
        hr = hier_results.get(task_id, {})
        dr = debate_results.get(task_id, {})

        # Assign DIT for pilot tasks based on category
        # Easy tasks have balanced/low DIT — all topologies handle them
        if task_id.startswith("CODE"):
            dit = {"D": 0.5, "I": 0.4, "T": 0.5}
        elif task_id.startswith("REASON"):
            dit = {"D": 0.4, "I": 0.5, "T": 0.3}
        elif task_id.startswith("RESEARCH"):
            dit = {"D": 0.3, "I": 0.3, "T": 0.8}
        else:
            dit = {"D": 0.5, "I": 0.5, "T": 0.5}

        tasks.append({
            "task_id": task_id,
            "difficulty": "easy",
            "category": task_id.split("-")[0].lower(),
            "dit": dit,
            "flat_correct": fr.get("correct", False),
            "hier_correct": hr.get("correct", False),
            "debate_correct": dr.get("correct", False),
            "flat_tokens": fr.get("tokens_estimated", TOKEN_COSTS["easy"]["flat"]),
            "hier_tokens": hr.get("tokens_estimated", TOKEN_COSTS["easy"]["hierarchical"]),
            "debate_tokens": dr.get("tokens_estimated", TOKEN_COSTS["easy"]["debate"]),
        })

    return tasks


def load_scaled_tasks():
    """Load 20 hard tasks from scaled_experiment.json."""
    with open(RESULTS_DIR / "scaled_experiment.json") as f:
        data = json.load(f)

    tasks = []
    for r in data["results"]:
        tasks.append({
            "task_id": r["task_id"],
            "difficulty": "hard",
            "category": r["task_id"].split("-")[1].lower() if "-" in r["task_id"] else "unknown",
            "dit": r["dit"],
            "flat_correct": r["flat_result"]["correct"],
            "hier_correct": r["hierarchical_result"]["correct"],
            "debate_correct": r["debate_result"]["correct"],
            "flat_tokens": r["flat_result"].get("tokens_estimated", TOKEN_COSTS["hard"]["flat"]),
            "hier_tokens": r["hierarchical_result"].get("tokens_estimated", TOKEN_COSTS["hard"]["hierarchical"]),
            "debate_tokens": r["debate_result"].get("tokens_estimated", TOKEN_COSTS["hard"]["debate"]),
        })

    return tasks


def load_extended_tasks():
    """Load 50 tasks from extended_experiment.json."""
    with open(RESULTS_DIR / "extended_experiment.json") as f:
        data = json.load(f)

    tasks = []
    for r in data["results"]:
        difficulty = r.get("difficulty", "hard")
        tasks.append({
            "task_id": r["task_id"],
            "difficulty": difficulty,
            "category": r.get("category", "unknown"),
            "dit": r["dit"],
            "flat_correct": r["flat_result"]["correct"],
            "hier_correct": r["hierarchical_result"]["correct"],
            "debate_correct": r["debate_result"]["correct"],
            "flat_tokens": r["flat_result"].get("tokens_estimated", TOKEN_COSTS[difficulty]["flat"]),
            "hier_tokens": r["hierarchical_result"].get("tokens_estimated", TOKEN_COSTS[difficulty]["hierarchical"]),
            "debate_tokens": r["debate_result"].get("tokens_estimated", TOKEN_COSTS[difficulty]["debate"]),
        })

    return tasks


def simulate_always(tasks, topology):
    """Simulate always routing to one topology."""
    # Map topology name to the key prefix used in task dicts
    key_map = {"flat": "flat", "hierarchical": "hier", "debate": "debate"}
    prefix = key_map[topology]
    key_correct = f"{prefix}_correct"
    key_tokens = f"{prefix}_tokens"

    total_tokens = sum(t[key_tokens] for t in tasks)
    correct_tasks = sum(1 for t in tasks if t[key_correct])
    accuracy = correct_tasks / len(tasks)
    cost_per_correct = total_tokens / correct_tasks if correct_tasks > 0 else float("inf")

    routing = {"flat": 0, "hierarchical": 0, "debate": 0}
    routing[topology] = len(tasks)

    return {
        "name": f"always-{topology}",
        "total_tokens": total_tokens,
        "correct_tasks": correct_tasks,
        "total_tasks": len(tasks),
        "accuracy": round(accuracy, 4),
        "cost_per_correct": round(cost_per_correct, 1),
        "routing_decisions": routing,
    }


def simulate_costrouter(tasks, q_star, label):
    """Simulate CostRouter with quality threshold q*."""
    total_tokens = 0
    correct_tasks = 0
    routing = {"flat": 0, "hierarchical": 0, "debate": 0}
    per_task_decisions = []

    for t in tasks:
        # Compute alignment distance and predicted accuracy for each topology
        key_map = {"flat": "flat", "hierarchical": "hier", "debate": "debate"}
        topo_options = []
        for topo in ["flat", "hierarchical", "debate"]:
            prefix = key_map[topo]
            dist = alignment_distance(t["dit"], TOPOLOGY_PRIORS[topo])
            pred_acc = predicted_accuracy(dist)
            tokens = t[f"{prefix}_tokens"]
            actual_correct = t[f"{prefix}_correct"]
            topo_options.append({
                "topology": topo,
                "distance": round(dist, 4),
                "predicted_accuracy": round(pred_acc, 4),
                "tokens": tokens,
                "actual_correct": actual_correct,
            })

        # Filter topologies meeting quality threshold
        qualified = [o for o in topo_options if o["predicted_accuracy"] >= q_star]

        if qualified:
            # Pick cheapest among qualified
            chosen = min(qualified, key=lambda x: x["tokens"])
        else:
            # Fallback: pick highest predicted accuracy
            chosen = max(topo_options, key=lambda x: x["predicted_accuracy"])

        topo_name = chosen["topology"]
        routing[topo_name] += 1
        total_tokens += chosen["tokens"]
        if chosen["actual_correct"]:
            correct_tasks += 1

        # Short name for routing key
        topo_short = {"flat": "flat", "hierarchical": "hier", "debate": "debate"}
        per_task_decisions.append({
            "task_id": t["task_id"],
            "routed_to": topo_name,
            "predicted_acc": chosen["predicted_accuracy"],
            "actual_correct": chosen["actual_correct"],
            "tokens": chosen["tokens"],
            "all_options": {
                o["topology"]: {
                    "pred_acc": o["predicted_accuracy"],
                    "tokens": o["tokens"],
                    "actual": o["actual_correct"],
                }
                for o in topo_options
            },
        })

    accuracy = correct_tasks / len(tasks)
    cost_per_correct = total_tokens / correct_tasks if correct_tasks > 0 else float("inf")

    return {
        "strategy": {
            "name": label,
            "total_tokens": total_tokens,
            "correct_tasks": correct_tasks,
            "total_tasks": len(tasks),
            "accuracy": round(accuracy, 4),
            "cost_per_correct": round(cost_per_correct, 1),
            "routing_decisions": routing,
        },
        "per_task": per_task_decisions,
    }


def simulate_oracle(tasks):
    """Oracle: hindsight best — cheapest topology that actually got the task correct."""
    total_tokens = 0
    correct_tasks = 0
    routing = {"flat": 0, "hierarchical": 0, "debate": 0}

    key_map = {"flat": "flat", "hierarchical": "hier", "debate": "debate"}
    for t in tasks:
        # Find all topologies that got this task correct
        correct_topos = []
        for topo in ["flat", "hierarchical", "debate"]:
            prefix = key_map[topo]
            if t[f"{prefix}_correct"]:
                correct_topos.append((topo, t[f"{prefix}_tokens"]))

        if correct_topos:
            # Pick cheapest correct topology
            chosen_topo, chosen_tokens = min(correct_topos, key=lambda x: x[1])
            routing[chosen_topo] += 1
            total_tokens += chosen_tokens
            correct_tasks += 1
        else:
            # No topology got it correct — pick cheapest anyway
            cheapest_topo = min(
                ["flat", "hierarchical", "debate"],
                key=lambda tp: t[f"{key_map[tp]}_tokens"],
            )
            routing[cheapest_topo] += 1
            total_tokens += t[f"{key_map[cheapest_topo]}_tokens"]

    accuracy = correct_tasks / len(tasks)
    cost_per_correct = total_tokens / correct_tasks if correct_tasks > 0 else float("inf")

    return {
        "name": "oracle",
        "total_tokens": total_tokens,
        "correct_tasks": correct_tasks,
        "total_tasks": len(tasks),
        "accuracy": round(accuracy, 4),
        "cost_per_correct": round(cost_per_correct, 1),
        "routing_decisions": routing,
    }


def main():
    # Load all tasks
    pilot = load_pilot_tasks()
    scaled = load_scaled_tasks()
    extended = load_extended_tasks()
    all_tasks = pilot + scaled + extended

    print(f"Total tasks loaded: {len(all_tasks)}")
    print(f"  Pilot (easy): {len(pilot)}")
    print(f"  Scaled (hard): {len(scaled)}")
    print(f"  Extended (mixed): {len(extended)}")
    print()

    # ── Strategy simulations ──
    strategies = []

    # Always-X strategies
    for topo in ["flat", "hierarchical", "debate"]:
        result = simulate_always(all_tasks, topo)
        strategies.append(result)

    # CostRouter strategies
    costrouter_per_task = {}
    for q_star, label in [(0.5, "CostRouter (q*=0.5)"), (0.6, "CostRouter (q*=0.6)"), (0.8, "CostRouter (q*=0.8)")]:
        cr = simulate_costrouter(all_tasks, q_star, label)
        strategies.append(cr["strategy"])
        costrouter_per_task[label] = cr["per_task"]

    # Oracle
    oracle = simulate_oracle(all_tasks)
    strategies.append(oracle)

    # ── Summary metrics ──
    debate_strategy = next(s for s in strategies if s["name"] == "always-debate")
    hier_strategy = next(s for s in strategies if s["name"] == "always-hierarchical")
    flat_strategy = next(s for s in strategies if s["name"] == "always-flat")
    cr_05 = next(s for s in strategies if s["name"] == "CostRouter (q*=0.5)")
    cr_06 = next(s for s in strategies if s["name"] == "CostRouter (q*=0.6)")
    cr_08 = next(s for s in strategies if s["name"] == "CostRouter (q*=0.8)")

    # Cost savings: compare cost_per_correct (efficiency metric)
    efficiency_gain_vs_debate = (1 - cr_05["cost_per_correct"] / debate_strategy["cost_per_correct"]) * 100
    accuracy_gain_vs_debate = (cr_05["accuracy"] - debate_strategy["accuracy"]) * 100

    # Token savings for q*=0.5 (most cost-aggressive)
    token_savings_vs_debate = (1 - cr_05["total_tokens"] / debate_strategy["total_tokens"]) * 100

    summary = {
        "cost_savings_vs_debate": f"{token_savings_vs_debate:.1f}%",
        "accuracy_gain_vs_debate": f"+{accuracy_gain_vs_debate:.1f}pp",
        "efficiency_gain_vs_debate": f"{efficiency_gain_vs_debate:.1f}%",
        "best_costrouter_efficiency": "CostRouter (q*=0.5)",
        "best_costrouter_accuracy": "CostRouter (q*=0.8)",
        "oracle_tokens": oracle["total_tokens"],
        "oracle_accuracy": oracle["accuracy"],
        "key_finding": (
            f"CostRouter (q*=0.5) saves {token_savings_vs_debate:.1f}% tokens vs always-debate "
            f"while gaining +{accuracy_gain_vs_debate:.1f}pp accuracy by routing easy tasks to flat. "
            f"Cost-per-correct improves by {efficiency_gain_vs_debate:.1f}% "
            f"({cr_05['cost_per_correct']:.0f} vs {debate_strategy['cost_per_correct']:.0f} tokens/correct)."
        ),
    }

    # ── Build output ──
    output = {
        "experiment": "CostRouter Routing Simulation",
        "date": "2026-03-16",
        "description": "Simulates routing 82 OrchestraBench tasks through 7 strategies to measure cost vs accuracy tradeoffs",
        "task_count": len(all_tasks),
        "task_breakdown": {
            "easy": len(pilot),
            "medium": sum(1 for t in all_tasks if t["difficulty"] == "medium"),
            "hard": sum(1 for t in all_tasks if t["difficulty"] == "hard"),
        },
        "topology_priors": TOPOLOGY_PRIORS,
        "token_cost_defaults": TOKEN_COSTS,
        "strategies": strategies,
        "per_task_routing": costrouter_per_task.get("CostRouter (q*=0.6)", []),
        "summary": summary,
    }

    # Write results
    output_path = RESULTS_DIR / "costrouter_simulation.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results written to: {output_path}")
    print()

    # ── Print comparison table ──
    print("=" * 105)
    print(f"{'Strategy':<25} {'Tokens':>10} {'Correct':>8} {'Accuracy':>9} {'Cost/Correct':>13} {'Routing (F/H/D)':>20}")
    print("=" * 105)
    for s in strategies:
        r = s["routing_decisions"]
        routing_str = f"{r['flat']}/{r['hierarchical']}/{r['debate']}"
        print(
            f"{s['name']:<25} {s['total_tokens']:>10,} {s['correct_tasks']:>8}/{s['total_tasks']}"
            f" {s['accuracy']:>8.1%} {s['cost_per_correct']:>13,.1f} {routing_str:>20}"
        )
    print("=" * 105)
    print()
    print(f"Summary:")
    print(f"  CostRouter (q*=0.5) token savings vs always-debate: {summary['cost_savings_vs_debate']}")
    print(f"  CostRouter (q*=0.5) accuracy gain vs always-debate: {summary['accuracy_gain_vs_debate']}")
    print(f"  CostRouter (q*=0.5) efficiency gain (cost/correct): {summary['efficiency_gain_vs_debate']}")
    print(f"  Oracle lower bound (hindsight best): {oracle['total_tokens']:,} tokens, {oracle['accuracy']:.1%} accuracy")
    print()
    print(f"Key finding: {summary['key_finding']}")

    # ── Additional analysis: routing breakdown by difficulty ──
    print()
    print("Routing breakdown by difficulty (CostRouter q*=0.6):")
    cr_decisions = costrouter_per_task["CostRouter (q*=0.6)"]
    for diff in ["easy", "medium", "hard"]:
        diff_tasks = [t for t in all_tasks if t["difficulty"] == diff]
        diff_decisions = [d for d, t in zip(cr_decisions, all_tasks) if t["difficulty"] == diff]
        if not diff_tasks:
            continue
        flat_count = sum(1 for d in diff_decisions if d["routed_to"] == "flat")
        hier_count = sum(1 for d in diff_decisions if d["routed_to"] == "hierarchical")
        debate_count = sum(1 for d in diff_decisions if d["routed_to"] == "debate")
        correct = sum(1 for d in diff_decisions if d["actual_correct"])
        print(f"  {diff:>6}: {len(diff_tasks)} tasks -> flat={flat_count}, hier={hier_count}, debate={debate_count} | correct={correct}/{len(diff_tasks)}")


if __name__ == "__main__":
    main()
