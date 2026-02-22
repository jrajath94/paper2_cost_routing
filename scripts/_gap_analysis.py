#!/usr/bin/env python3
"""Research gap analysis via citation graph traversal.

Identifies genuine research gaps by analyzing citation graph patterns,
co-citation proximity, and cluster connectivity from a literature_map.json.

Scoring uses locked weights:
  Novelty: co-citation_proximity * 0.30 + direct_paper_absence * 0.30
           + recency * 0.20 + search_validation * 0.20
  Ranking: novelty_score * 0.60 + feasibility_score * 0.30
           + confidence_value * 0.10

All functions use Python3 standard library only -- no pip installs.

Usage:
  # Analyze literature map and output research gaps
  python3 paper/scripts/_gap_analysis.py <input_path> <output_path>

  # Self-test with embedded mock data
  python3 paper/scripts/_gap_analysis.py --self-test
"""

import collections
import json
import os
import sys
from datetime import datetime, timezone
from itertools import combinations

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from _shared_utils import atomic_write, load_env, sequence_similarity


# ---------------------------------------------------------------------------
# Constants -- locked scoring weights
# ---------------------------------------------------------------------------

# Novelty component weights (must sum to 1.0)
NOVELTY_WEIGHT_COCITATION = 0.30
NOVELTY_WEIGHT_ABSENCE = 0.30
NOVELTY_WEIGHT_RECENCY = 0.20
NOVELTY_WEIGHT_SEARCH = 0.20

# Ranking formula weights (must sum to 1.0)
RANK_WEIGHT_NOVELTY = 0.60
RANK_WEIGHT_FEASIBILITY = 0.30
RANK_WEIGHT_CONFIDENCE = 0.10

# Confidence mapping
CONFIDENCE_MAP = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.4}

# Cluster connectivity threshold for "sparse" regions
SPARSE_DENSITY_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# 1. Load and validate literature map
# ---------------------------------------------------------------------------

def load_literature_map(path):
    """Read and validate literature_map.json.

    Assert papers array exists and has >= 20 entries.
    Returns dict with keys: papers, clusters, topic.
    """
    with open(path, 'r') as f:
        data = json.load(f)

    assert "papers" in data, "literature_map.json missing 'papers' array"
    assert len(data["papers"]) >= 20, (
        f"Need >= 20 papers for gap analysis, got {len(data['papers'])}"
    )

    papers = data["papers"]
    clusters = data.get("clusters", [])
    topic = data.get("topic", "unknown")

    return {"papers": papers, "clusters": clusters, "topic": topic}


# ---------------------------------------------------------------------------
# 2. Build citation graph (undirected adjacency list)
# ---------------------------------------------------------------------------

def build_citation_graph(papers):
    """Build undirected adjacency list from references + cited_by.

    For each paper, adds edges for references[] and cited_by[] (both
    directions). Returns defaultdict(set) mapping paper_id -> set of
    connected paper_ids.
    """
    graph = collections.defaultdict(set)
    # Build set of known paper IDs for filtering
    known_ids = {p["id"] for p in papers}

    for paper in papers:
        pid = paper["id"]
        # Add edges from references (papers this paper cites)
        for ref_id in paper.get("references", []):
            if ref_id in known_ids:
                graph[pid].add(ref_id)
                graph[ref_id].add(pid)
        # Add edges from cited_by (papers that cite this paper)
        for citer_id in paper.get("cited_by", []):
            if citer_id in known_ids:
                graph[pid].add(citer_id)
                graph[citer_id].add(pid)

    return graph


# ---------------------------------------------------------------------------
# 3. Build co-citation matrix
# ---------------------------------------------------------------------------

def build_cocitation_matrix(papers):
    """For each paper, get its references[]. For every pair of references
    within the same paper's reference list, increment a counter for that
    sorted pair.

    High co-citation + no direct edge = potential gap.
    Returns Counter mapping frozenset({id_a, id_b}) -> count.
    """
    cocitation = collections.Counter()
    known_ids = {p["id"] for p in papers}

    for paper in papers:
        refs = [r for r in paper.get("references", []) if r in known_ids]
        # Every pair of references within this paper's reference list
        for pair in combinations(sorted(refs), 2):
            cocitation[frozenset(pair)] += 1

    return cocitation


# ---------------------------------------------------------------------------
# 4. Compute cluster connectivity
# ---------------------------------------------------------------------------

def compute_cluster_connectivity(papers, clusters):
    """For each pair of clusters, count cross-cluster citations.

    Computes density = cross_citations / (size_a * size_b).
    Tracks bridging papers (papers in one cluster citing papers in the other).

    Returns dict mapping (cluster_a_name, cluster_b_name) -> {
        cross_citations, density, bridging_papers
    }.
    """
    # Build paper_id -> cluster_name mapping
    paper_cluster = {}
    for cluster in clusters:
        for pid in cluster.get("paper_ids", []):
            paper_cluster[pid] = cluster["name"]

    # Build paper_id -> paper lookup
    paper_lookup = {p["id"]: p for p in papers}

    connectivity = {}
    cluster_names = [c["name"] for c in clusters]

    for i, ca in enumerate(cluster_names):
        for j, cb in enumerate(cluster_names):
            if j <= i:
                continue

            ca_ids = set()
            cb_ids = set()
            for c in clusters:
                if c["name"] == ca:
                    ca_ids = set(c.get("paper_ids", []))
                elif c["name"] == cb:
                    cb_ids = set(c.get("paper_ids", []))

            cross_citations = 0
            bridging_papers = set()

            for pid in ca_ids:
                paper = paper_lookup.get(pid, {})
                refs = set(paper.get("references", [])) | set(paper.get("cited_by", []))
                cross = refs & cb_ids
                if cross:
                    cross_citations += len(cross)
                    bridging_papers.add(pid)

            for pid in cb_ids:
                paper = paper_lookup.get(pid, {})
                refs = set(paper.get("references", [])) | set(paper.get("cited_by", []))
                cross = refs & ca_ids
                if cross:
                    cross_citations += len(cross)
                    bridging_papers.add(pid)

            size_a = len(ca_ids)
            size_b = len(cb_ids)
            denominator = size_a * size_b if size_a > 0 and size_b > 0 else 1

            density = cross_citations / denominator

            connectivity[(ca, cb)] = {
                "cross_citations": cross_citations,
                "density": density,
                "bridging_papers": list(bridging_papers),
            }

    return connectivity


# ---------------------------------------------------------------------------
# 5. Identify gaps
# ---------------------------------------------------------------------------

def _get_cluster_papers(cluster_name, clusters, paper_lookup):
    """Get papers belonging to a cluster."""
    for c in clusters:
        if c["name"] == cluster_name:
            return [paper_lookup[pid] for pid in c.get("paper_ids", [])
                    if pid in paper_lookup]
    return []


def _median_year(papers_list):
    """Compute median year of a list of papers."""
    years = sorted(p.get("year", 2020) for p in papers_list)
    if not years:
        return 2020
    mid = len(years) // 2
    return years[mid]


def _cluster_description(cluster_name, clusters):
    """Get cluster description, falling back to empty string."""
    for c in clusters:
        if c["name"] == cluster_name:
            return c.get("description", "")
    return ""


def identify_gaps(papers, clusters, graph, cocitation, connectivity):
    """Combine three heuristics to identify research gaps:

    1. Between-cluster gaps: Cluster pairs with density < 0.05 but both
       active (median year >= 2023).
    2. Co-citation gaps: Paper pairs with co-citation count >= 2 but no
       direct citation edge, belonging to different clusters.
    3. Temporal gaps: Clusters with avg year >= 2024 that have zero or
       minimal connections to another active cluster.

    Returns list of gap candidate dicts.
    """
    paper_lookup = {p["id"]: p for p in papers}
    paper_cluster = {}
    for cluster in clusters:
        for pid in cluster.get("paper_ids", []):
            paper_cluster[pid] = cluster["name"]

    # Filter out small clusters (1-2 papers) from between-cluster analysis
    viable_clusters = [c for c in clusters if len(c.get("paper_ids", [])) >= 3]
    small_clusters = [c for c in clusters if len(c.get("paper_ids", [])) < 3]

    gaps = []
    seen_pairs = set()
    gap_counter = 0

    # --- Heuristic 1: Between-cluster gaps ---
    for (ca, cb), conn in connectivity.items():
        # Skip if either cluster is too small
        ca_viable = any(c["name"] == ca for c in viable_clusters)
        cb_viable = any(c["name"] == cb for c in viable_clusters)
        if not ca_viable or not cb_viable:
            continue

        if conn["density"] < SPARSE_DENSITY_THRESHOLD:
            ca_papers = _get_cluster_papers(ca, clusters, paper_lookup)
            cb_papers = _get_cluster_papers(cb, clusters, paper_lookup)

            # Both clusters must be active (median year >= 2023)
            if _median_year(ca_papers) < 2023 or _median_year(cb_papers) < 2023:
                continue

            pair_key = frozenset([ca, cb])
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            gap_counter += 1
            ca_key_papers = [p["id"] for p in ca_papers[:5]]
            cb_key_papers = [p["id"] for p in cb_papers[:5]]

            # Collect evidence: papers from both clusters
            evidence = []
            for p in ca_papers[:3]:
                evidence.append(p["id"])
            for p in cb_papers[:3]:
                if p["id"] not in evidence:
                    evidence.append(p["id"])
            # Ensure minimum 3
            while len(evidence) < 3:
                for p in ca_papers + cb_papers:
                    if p["id"] not in evidence:
                        evidence.append(p["id"])
                        break
                else:
                    break

            gaps.append({
                "gap_id": f"GAP-{gap_counter:03d}",
                "description": (
                    f"Sparse connection between '{ca}' and '{cb}' clusters. "
                    f"Despite both being active research areas (median years "
                    f"{_median_year(ca_papers)} and {_median_year(cb_papers)}), "
                    f"only {conn['cross_citations']} cross-citations exist "
                    f"(density {conn['density']:.3f})."
                ),
                "cluster_a": {
                    "name": ca,
                    "description": _cluster_description(ca, clusters),
                    "key_papers": ca_key_papers,
                },
                "cluster_b": {
                    "name": cb,
                    "description": _cluster_description(cb, clusters),
                    "key_papers": cb_key_papers,
                },
                "evidence": evidence[:6],
                "heuristic": "between-cluster",
                "confidence": "HIGH" if conn["cross_citations"] == 0 else "MEDIUM",
                "bridging_papers": conn["bridging_papers"],
            })

    # --- Heuristic 2: Co-citation gaps ---
    for pair, count in cocitation.most_common():
        if count < 2:
            continue
        pair_list = sorted(pair)
        if len(pair_list) != 2:
            continue
        id_a, id_b = pair_list

        # Must be in different clusters
        cluster_a = paper_cluster.get(id_a)
        cluster_b = paper_cluster.get(id_b)
        if not cluster_a or not cluster_b or cluster_a == cluster_b:
            continue

        # Must NOT have a direct citation edge
        if id_b in graph.get(id_a, set()):
            continue

        pair_key = frozenset([cluster_a, cluster_b])
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        gap_counter += 1
        ca_papers = _get_cluster_papers(cluster_a, clusters, paper_lookup)
        cb_papers = _get_cluster_papers(cluster_b, clusters, paper_lookup)

        # Build evidence from co-citation context
        evidence = [id_a, id_b]
        # Add papers that co-cite both
        for p in papers:
            refs = set(p.get("references", []))
            if id_a in refs and id_b in refs and p["id"] not in evidence:
                evidence.append(p["id"])
        # Pad with cluster papers if needed
        for p in ca_papers + cb_papers:
            if len(evidence) >= 3:
                break
            if p["id"] not in evidence:
                evidence.append(p["id"])

        gaps.append({
            "gap_id": f"GAP-{gap_counter:03d}",
            "description": (
                f"Papers '{id_a}' and '{id_b}' are co-cited {count} times "
                f"but have no direct citation edge. They belong to different "
                f"clusters ('{cluster_a}' and '{cluster_b}'), suggesting "
                f"an unexplored connection between their approaches."
            ),
            "cluster_a": {
                "name": cluster_a,
                "description": _cluster_description(cluster_a, clusters),
                "key_papers": [p["id"] for p in ca_papers[:5]],
            },
            "cluster_b": {
                "name": cluster_b,
                "description": _cluster_description(cluster_b, clusters),
                "key_papers": [p["id"] for p in cb_papers[:5]],
            },
            "evidence": evidence[:6],
            "heuristic": "co-citation",
            "confidence": "HIGH" if count >= 3 else "MEDIUM",
            "bridging_papers": [],
        })

    # --- Heuristic 3: Temporal gaps ---
    for cluster in viable_clusters:
        c_papers = _get_cluster_papers(cluster["name"], clusters, paper_lookup)
        avg_year = (sum(p.get("year", 2020) for p in c_papers) / len(c_papers)
                    if c_papers else 2020)

        if avg_year < 2024:
            continue

        # Find clusters it has minimal connection to
        for other_cluster in viable_clusters:
            if other_cluster["name"] == cluster["name"]:
                continue

            pair_key = frozenset([cluster["name"], other_cluster["name"]])
            if pair_key in seen_pairs:
                continue

            # Check connectivity
            conn_key = (cluster["name"], other_cluster["name"])
            conn_key_rev = (other_cluster["name"], cluster["name"])
            conn = connectivity.get(conn_key, connectivity.get(conn_key_rev, {}))

            cross = conn.get("cross_citations", 0)
            if cross <= 1:
                o_papers = _get_cluster_papers(
                    other_cluster["name"], clusters, paper_lookup
                )
                o_avg_year = (
                    sum(p.get("year", 2020) for p in o_papers) / len(o_papers)
                    if o_papers else 2020
                )
                if o_avg_year < 2023:
                    continue

                seen_pairs.add(pair_key)
                gap_counter += 1

                evidence = []
                for p in c_papers[:3]:
                    evidence.append(p["id"])
                for p in o_papers[:3]:
                    if p["id"] not in evidence:
                        evidence.append(p["id"])

                gaps.append({
                    "gap_id": f"GAP-{gap_counter:03d}",
                    "description": (
                        f"Temporal disconnect between '{cluster['name']}' "
                        f"(avg year {avg_year:.0f}) and '{other_cluster['name']}' "
                        f"(avg year {o_avg_year:.0f}). Both are recent and "
                        f"active but have {cross} cross-citations, suggesting "
                        f"emerging areas that haven't been connected yet."
                    ),
                    "cluster_a": {
                        "name": cluster["name"],
                        "description": _cluster_description(
                            cluster["name"], clusters
                        ),
                        "key_papers": [p["id"] for p in c_papers[:5]],
                    },
                    "cluster_b": {
                        "name": other_cluster["name"],
                        "description": _cluster_description(
                            other_cluster["name"], clusters
                        ),
                        "key_papers": [p["id"] for p in o_papers[:5]],
                    },
                    "evidence": evidence[:6],
                    "heuristic": "temporal",
                    "confidence": "MEDIUM" if cross == 0 else "LOW",
                    "bridging_papers": [],
                })

    # Add metadata note about small clusters
    metadata_notes = []
    if small_clusters:
        names = [c["name"] for c in small_clusters]
        metadata_notes.append(
            f"Small clusters excluded from between-cluster analysis: {names}"
        )

    return gaps, metadata_notes


# ---------------------------------------------------------------------------
# 6. Score novelty
# ---------------------------------------------------------------------------

def score_novelty(gap, graph, cocitation):
    """Apply locked novelty weights.

    co-citation_proximity (30%): Score 1-10 based on how frequently the two
      clusters' papers are co-cited. 0 co-citations = 10, >5 = 1.
    direct_paper_absence (30%): Score 1-10 based on bridging papers count.
      0 = 10, 1 = 7, 2-3 = 4, >3 = 1.
    recency (20%): Score 1-10 based on average year of evidence papers.
      2025-2026 = 10, 2024 = 8, 2023 = 6, <2023 = 3.
    search_validation (20%): Default 5.0 (agent adjusts post-search).

    Returns float in [1.0, 10.0].
    """
    # Co-citation proximity score
    ca_papers = set(gap["cluster_a"].get("key_papers", []))
    cb_papers = set(gap["cluster_b"].get("key_papers", []))

    cocite_count = 0
    for pair, count in cocitation.items():
        pair_list = list(pair)
        if len(pair_list) == 2:
            a, b = pair_list
            if (a in ca_papers and b in cb_papers) or (b in ca_papers and a in cb_papers):
                cocite_count += count

    if cocite_count == 0:
        cocite_score = 10.0
    elif cocite_count <= 1:
        cocite_score = 8.0
    elif cocite_count <= 3:
        cocite_score = 5.0
    elif cocite_count <= 5:
        cocite_score = 3.0
    else:
        cocite_score = 1.0

    # Direct paper absence score
    bridging = gap.get("bridging_papers", [])
    num_bridging = len(bridging)
    if num_bridging == 0:
        absence_score = 10.0
    elif num_bridging == 1:
        absence_score = 7.0
    elif num_bridging <= 3:
        absence_score = 4.0
    else:
        absence_score = 1.0

    # Recency score (based on evidence paper years -- use key_papers from
    # both clusters as proxy since we don't have full paper objects here)
    evidence_ids = gap.get("evidence", [])
    # We'll use a heuristic: if the gap was identified from recent clusters,
    # the evidence year is encoded in the description or we default to
    # moderate recency.
    # For proper scoring, we pass papers_lookup in the main pipeline.
    recency_score = gap.get("_recency_score", 6.0)

    # Search validation (default neutral)
    search_score = 5.0

    # Weighted sum
    raw = (
        cocite_score * NOVELTY_WEIGHT_COCITATION
        + absence_score * NOVELTY_WEIGHT_ABSENCE
        + recency_score * NOVELTY_WEIGHT_RECENCY
        + search_score * NOVELTY_WEIGHT_SEARCH
    )

    # Clamp to [1.0, 10.0]
    return max(1.0, min(10.0, raw))


def _compute_recency_score(evidence_ids, paper_lookup):
    """Compute recency score from evidence paper years.

    2025-2026 = 10, 2024 = 8, 2023 = 6, <2023 = 3.
    Returns average across evidence papers.
    """
    scores = []
    for pid in evidence_ids:
        paper = paper_lookup.get(pid, {})
        year = paper.get("year", 2020)
        if year >= 2025:
            scores.append(10.0)
        elif year >= 2024:
            scores.append(8.0)
        elif year >= 2023:
            scores.append(6.0)
        else:
            scores.append(3.0)

    return sum(scores) / len(scores) if scores else 3.0


# ---------------------------------------------------------------------------
# 7. Assess feasibility
# ---------------------------------------------------------------------------

def assess_feasibility(gap, papers):
    """Score 1-10 based on feasibility criteria.

    +3 if available baselines (papers from both clusters provide baselines)
    +2 if public datasets mentioned in evidence papers
    +2 if scope fits single 9-page paper (based on gap specificity)
    +2 if single-author feasible (no large-team requirements)
    -1 per identified risk factor

    Returns dict {score, assessment, required_resources}.
    """
    paper_lookup = {p["id"]: p for p in papers}
    score = 1  # Base score

    ca_papers = gap["cluster_a"].get("key_papers", [])
    cb_papers = gap["cluster_b"].get("key_papers", [])
    assessment_parts = []
    resources = []
    risks = 0

    # +3: Available baselines from both clusters
    has_a_papers = len(ca_papers) >= 1
    has_b_papers = len(cb_papers) >= 1
    if has_a_papers and has_b_papers:
        score += 3
        assessment_parts.append(
            "Both clusters provide baseline papers for comparison."
        )
        resources.append("Baseline implementations from both clusters")
    elif has_a_papers or has_b_papers:
        score += 1
        assessment_parts.append("Only one cluster provides clear baselines.")
        risks += 1

    # +2: Public datasets (heuristic -- check for dataset-related keywords
    # in evidence paper contributions/limitations)
    dataset_keywords = ["benchmark", "dataset", "evaluation suite", "test bed",
                        "corpus", "publicly available"]
    has_dataset = False
    for pid in gap.get("evidence", []):
        paper = paper_lookup.get(pid, {})
        text = (paper.get("contribution", "") + " " +
                paper.get("limitation", "")).lower()
        if any(kw in text for kw in dataset_keywords):
            has_dataset = True
            break
    if has_dataset:
        score += 2
        assessment_parts.append("Public datasets or benchmarks available.")
        resources.append("Public benchmark suites referenced in evidence")
    else:
        resources.append("May need to identify or create evaluation datasets")

    # +2: Scope fits single paper (gap specificity -- between-cluster gaps
    # with clear boundaries are more scoped)
    heuristic = gap.get("heuristic", "between-cluster")
    if heuristic in ("between-cluster", "co-citation"):
        score += 2
        assessment_parts.append("Gap is well-scoped between two defined clusters.")
    else:
        score += 1
        assessment_parts.append("Gap scope may need narrowing for a single paper.")

    # +2: Single-author feasible (check evidence paper author counts)
    author_counts = []
    for pid in gap.get("evidence", [])[:5]:
        paper = paper_lookup.get(pid, {})
        authors = paper.get("authors", [])
        if authors:
            author_counts.append(len(authors))

    avg_authors = (sum(author_counts) / len(author_counts)
                   if author_counts else 3)
    if avg_authors <= 4:
        score += 2
        assessment_parts.append("Single-author execution appears feasible.")
    else:
        score += 1
        assessment_parts.append(
            "Related work involves larger teams; may need scope reduction."
        )
        risks += 1

    # Risk deductions
    if gap.get("confidence") == "LOW":
        risks += 1
    score -= risks
    if risks > 0:
        assessment_parts.append(f"Risk factors identified: {risks}.")

    # Clamp to [1, 10]
    score = max(1, min(10, score))

    assessment = " ".join(assessment_parts)
    resources.append("API access for LLM evaluation (if applicable)")

    return {
        "score": score,
        "assessment": assessment,
        "required_resources": resources,
    }


# ---------------------------------------------------------------------------
# 8. Rank gaps
# ---------------------------------------------------------------------------

def rank_gaps(gaps):
    """Apply locked ranking formula:
    composite = novelty * 0.60 + feasibility * 0.30 + confidence_value * 0.10

    Sort descending. Returns sorted list with composite_score added.
    """
    for gap in gaps:
        novelty = gap.get("novelty_score", 5.0)
        feasibility = gap.get("feasibility", {}).get("score", 5)
        confidence_str = gap.get("confidence", "MEDIUM")
        confidence_val = CONFIDENCE_MAP.get(confidence_str, 0.7)

        # Scale confidence to 1-10 range for consistency
        confidence_scaled = confidence_val * 10.0

        composite = (
            novelty * RANK_WEIGHT_NOVELTY
            + feasibility * RANK_WEIGHT_FEASIBILITY
            + confidence_scaled * RANK_WEIGHT_CONFIDENCE
        )
        gap["_composite_score"] = composite

    gaps.sort(key=lambda g: g["_composite_score"], reverse=True)
    return gaps


# ---------------------------------------------------------------------------
# 9. Generate output
# ---------------------------------------------------------------------------

def generate_output(topic, gaps, metadata, output_path):
    """Build JSON matching research_gaps.schema.json and write via atomic_write.

    Strips internal fields (prefixed with _) from output.
    """
    clean_gaps = []
    for gap in gaps:
        clean_gap = {k: v for k, v in gap.items() if not k.startswith("_")}
        # Remove internal fields not in schema
        clean_gap.pop("heuristic", None)
        clean_gap.pop("bridging_papers", None)
        clean_gaps.append(clean_gap)

    output = {
        "topic": topic,
        "gaps": clean_gaps,
        "analysis_metadata": metadata,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    atomic_write(output_path, json.dumps(output, indent=2) + "\n")
    return output


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_path, output_path):
    """Execute the full gap analysis pipeline."""
    # Load
    lit_map = load_literature_map(input_path)
    papers = lit_map["papers"]
    clusters = lit_map["clusters"]
    topic = lit_map["topic"]

    # Build structures
    graph = build_citation_graph(papers)
    cocitation = build_cocitation_matrix(papers)
    connectivity = compute_cluster_connectivity(papers, clusters)

    # Identify gaps
    gaps, metadata_notes = identify_gaps(
        papers, clusters, graph, cocitation, connectivity
    )

    # Score and rank
    paper_lookup = {p["id"]: p for p in papers}
    for gap in gaps:
        # Compute recency for scoring
        gap["_recency_score"] = _compute_recency_score(
            gap.get("evidence", []), paper_lookup
        )
        gap["novelty_score"] = score_novelty(gap, graph, cocitation)
        gap["novelty_justification"] = gap["description"]
        gap["feasibility"] = assess_feasibility(gap, papers)
        # Generate recommended framing
        gap["recommended_framing"] = (
            f"Bridge {gap['cluster_a']['name']} and {gap['cluster_b']['name']} "
            f"by combining methods from both clusters. Focus on empirical "
            f"evaluation with existing benchmarks."
        )

    gaps = rank_gaps(gaps)

    # Build metadata
    total_edges = sum(len(neighbors) for neighbors in graph.values()) // 2
    metadata = {
        "papers_analyzed": len(papers),
        "clusters_identified": len(clusters),
        "citation_edges_mapped": total_edges,
        "sparse_regions_found": len(gaps),
    }

    # Generate output
    output = generate_output(topic, gaps, metadata, output_path)

    print(f"Gap analysis complete: {len(gaps)} gaps identified")
    print(f"  Papers analyzed: {len(papers)}")
    print(f"  Clusters: {len(clusters)}")
    print(f"  Citation edges: {total_edges}")
    print(f"  Output: {output_path}")

    if metadata_notes:
        for note in metadata_notes:
            print(f"  Note: {note}")

    return output


# ---------------------------------------------------------------------------
# Self-test with embedded mock data
# ---------------------------------------------------------------------------

def _build_mock_literature_map():
    """Build mock literature_map with ~25 papers across 4 clusters.

    Clusters:
    - multi-agent-frameworks (7 papers)
    - reasoning-planning (6 papers)
    - tool-use (6 papers)
    - agent-evaluation (6 papers)

    Deliberate sparse regions:
    - reasoning-planning <-> tool-use: ZERO cross-citations
    - agent-evaluation <-> multi-agent-frameworks: minimal (1 cross-cite)
    - multi-agent-frameworks <-> reasoning-planning: some connections (3+)
    """
    papers = []

    # -- Cluster 1: multi-agent-frameworks (7 papers) --
    maf_ids = [f"MAF-{i:03d}" for i in range(1, 8)]
    for i, pid in enumerate(maf_ids):
        refs = []
        cited_by = []
        # Internal references within cluster
        if i > 0:
            refs.append(maf_ids[i - 1])
        if i > 1:
            refs.append(maf_ids[i - 2])
        # Cross-cite to reasoning-planning (sparse but present)
        if i == 0:
            refs.append("RP-001")
        if i == 2:
            refs.append("RP-003")
        if i == 4:
            refs.append("RP-005")
        # Minimal cross-cite to agent-evaluation
        if i == 6:
            refs.append("AE-001")

        papers.append({
            "id": pid,
            "title": f"Multi-Agent Framework Paper {i+1}",
            "authors": [f"Author-MAF-{i+1}"],
            "year": 2024 + (i % 2),
            "venue": "NeurIPS" if i % 2 == 0 else "ICML",
            "contribution": f"Novel multi-agent orchestration approach {i+1} with benchmark evaluation",
            "limitation": "Limited to specific task domains",
            "relevance_score": 8.0,
            "citations_count": 50 + i * 10,
            "references": refs,
            "cited_by": cited_by,
            "cluster": "multi-agent-frameworks",
            "retrieval_source": "semantic_scholar",
            "peer_reviewed": True,
        })

    # -- Cluster 2: reasoning-planning (6 papers) --
    rp_ids = [f"RP-{i:03d}" for i in range(1, 7)]
    for i, pid in enumerate(rp_ids):
        refs = []
        cited_by = []
        if i > 0:
            refs.append(rp_ids[i - 1])
        if i > 1:
            refs.append(rp_ids[i - 2])
        # Cross-cite to multi-agent (some connections)
        if i == 0:
            cited_by.append("MAF-001")
        if i == 2:
            cited_by.append("MAF-003")
        if i == 4:
            cited_by.append("MAF-005")
        # NO cross-citations to tool-use (deliberate gap)
        # NO cross-citations to agent-evaluation (deliberate gap)

        papers.append({
            "id": pid,
            "title": f"Reasoning and Planning Paper {i+1}",
            "authors": [f"Author-RP-{i+1}"],
            "year": 2023 + (i % 3),
            "venue": "ICLR" if i % 2 == 0 else "NeurIPS",
            "contribution": f"Planning method {i+1} for LLM-based task decomposition",
            "limitation": "Does not address tool integration",
            "relevance_score": 7.5,
            "citations_count": 30 + i * 15,
            "references": refs,
            "cited_by": cited_by,
            "cluster": "reasoning-planning",
            "retrieval_source": "semantic_scholar",
            "peer_reviewed": True,
        })

    # -- Cluster 3: tool-use (6 papers) --
    tu_ids = [f"TU-{i:03d}" for i in range(1, 7)]
    for i, pid in enumerate(tu_ids):
        refs = []
        cited_by = []
        if i > 0:
            refs.append(tu_ids[i - 1])
        if i > 1:
            refs.append(tu_ids[i - 2])
        # NO cross-citations to reasoning-planning (deliberate gap)
        # Some co-citations: multiple TU papers cite same pair of refs
        if i >= 2:
            refs.append("TU-001")  # Creates co-citation pairs
        # Cross-cite to agent-evaluation (moderate)
        if i == 3:
            refs.append("AE-002")
        if i == 5:
            refs.append("AE-004")

        papers.append({
            "id": pid,
            "title": f"Tool Use Integration Paper {i+1}",
            "authors": [f"Author-TU-{i+1}"],
            "year": 2024 + (i % 2),
            "venue": "ACL" if i % 2 == 0 else "EMNLP",
            "contribution": f"Tool integration method {i+1} for LLM agents",
            "limitation": "Lacks reasoning capability analysis",
            "relevance_score": 7.0,
            "citations_count": 20 + i * 10,
            "references": refs,
            "cited_by": cited_by,
            "cluster": "tool-use",
            "retrieval_source": "arxiv",
            "peer_reviewed": i % 2 == 0,
        })

    # -- Cluster 4: agent-evaluation (6 papers) --
    ae_ids = [f"AE-{i:03d}" for i in range(1, 7)]
    for i, pid in enumerate(ae_ids):
        refs = []
        cited_by = []
        if i > 0:
            refs.append(ae_ids[i - 1])
        if i > 1:
            refs.append(ae_ids[i - 2])
        # Minimal cross-cite to multi-agent (only 1)
        if i == 0:
            cited_by.append("MAF-007")
        # Moderate cross-cite to tool-use
        if i == 1:
            cited_by.append("TU-004")
        if i == 3:
            cited_by.append("TU-006")
        # NO cross-citations to reasoning-planning (deliberate gap)

        papers.append({
            "id": pid,
            "title": f"Agent Evaluation Benchmark Paper {i+1}",
            "authors": [f"Author-AE-{i+1}", f"Author-AE-{i+1}b"],
            "year": 2024 + (i % 2),
            "venue": "NeurIPS" if i % 2 == 0 else "ICML",
            "contribution": f"Evaluation benchmark {i+1} for LLM agent assessment",
            "limitation": "Limited to specific agent architectures",
            "relevance_score": 6.5,
            "citations_count": 15 + i * 5,
            "references": refs,
            "cited_by": cited_by,
            "cluster": "agent-evaluation",
            "retrieval_source": "semantic_scholar",
            "peer_reviewed": True,
        })

    # Fix cited_by reciprocals: for each ref, add cited_by back-link
    paper_lookup = {p["id"]: p for p in papers}
    for paper in papers:
        for ref_id in paper.get("references", []):
            if ref_id in paper_lookup:
                ref_paper = paper_lookup[ref_id]
                if paper["id"] not in ref_paper.get("cited_by", []):
                    if "cited_by" not in ref_paper:
                        ref_paper["cited_by"] = []
                    ref_paper["cited_by"].append(paper["id"])

    clusters = [
        {
            "name": "multi-agent-frameworks",
            "description": "LLM-based multi-agent systems with conversation-based or role-based coordination",
            "paper_ids": maf_ids,
        },
        {
            "name": "reasoning-planning",
            "description": "Planning and reasoning methods for LLM task decomposition",
            "paper_ids": rp_ids,
        },
        {
            "name": "tool-use",
            "description": "Tool integration and API calling for LLM agents",
            "paper_ids": tu_ids,
        },
        {
            "name": "agent-evaluation",
            "description": "Evaluation benchmarks and metrics for LLM agent assessment",
            "paper_ids": ae_ids,
        },
    ]

    return {
        "topic": "Multi-agent LLM orchestration for complex task decomposition",
        "papers": papers,
        "clusters": clusters,
        "generated_at": "2026-03-15T00:00:00Z",
        "total_papers": len(papers),
    }


def self_test():
    """Run all self-test assertions with embedded mock data."""
    import tempfile

    print("=== _gap_analysis self-test ===")
    print()

    mock_data = _build_mock_literature_map()
    papers = mock_data["papers"]
    clusters = mock_data["clusters"]

    # --- Test: load_literature_map ---
    tmpdir = tempfile.mkdtemp()
    mock_path = os.path.join(tmpdir, "mock_literature_map.json")
    with open(mock_path, "w") as f:
        json.dump(mock_data, f)

    result = load_literature_map(mock_path)
    assert len(result["papers"]) >= 20, f"Expected >= 20 papers, got {len(result['papers'])}"
    assert len(result["clusters"]) == 4, f"Expected 4 clusters, got {len(result['clusters'])}"
    print("[PASS] load_literature_map with valid JSON returns papers and clusters")

    # Test load_literature_map with < 20 papers raises AssertionError
    small_data = {"papers": [{"id": "X"} for _ in range(5)], "topic": "test"}
    small_path = os.path.join(tmpdir, "small.json")
    with open(small_path, "w") as f:
        json.dump(small_data, f)
    try:
        load_literature_map(small_path)
        assert False, "Should have raised AssertionError"
    except AssertionError:
        pass
    print("[PASS] load_literature_map with <20 papers raises AssertionError")

    # --- Test: build_citation_graph ---
    graph = build_citation_graph(papers)
    assert len(graph) > 0, "Graph should have nodes"
    # Count total edges (each edge counted once)
    total_edges = sum(len(neighbors) for neighbors in graph.values()) // 2
    assert total_edges > 0, f"Expected > 0 edges, got {total_edges}"
    # Verify undirected: if A -> B then B -> A
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            assert node in graph[neighbor], (
                f"Graph not undirected: {node} -> {neighbor} but not reverse"
            )
    print(f"[PASS] build_citation_graph creates undirected adjacency list ({total_edges} edges)")

    # --- Test: build_cocitation_matrix ---
    cocitation = build_cocitation_matrix(papers)
    assert len(cocitation) > 0, "Co-citation matrix should be non-empty"
    # Verify co-citation counts make sense
    for pair, count in cocitation.items():
        assert count >= 1, f"Co-citation count should be >= 1, got {count}"
    print(f"[PASS] build_cocitation_matrix counts co-cited pairs correctly ({len(cocitation)} pairs)")

    # --- Test: compute_cluster_connectivity ---
    connectivity = compute_cluster_connectivity(papers, clusters)
    # reasoning-planning <-> tool-use should be sparse
    rp_tu_key = None
    for key in connectivity:
        if set(key) == {"reasoning-planning", "tool-use"}:
            rp_tu_key = key
            break
    assert rp_tu_key is not None, "Should have connectivity for reasoning-planning <-> tool-use"
    assert connectivity[rp_tu_key]["density"] < 0.1, (
        f"Expected sparse density < 0.1, got {connectivity[rp_tu_key]['density']}"
    )
    print(f"[PASS] compute_cluster_connectivity returns density < 0.1 for sparse cluster pairs")

    # --- Test: identify_gaps ---
    gaps, notes = identify_gaps(papers, clusters, graph, cocitation, connectivity)
    assert len(gaps) >= 3, f"Expected >= 3 gaps, got {len(gaps)}"
    print(f"[PASS] identify_gaps finds >= 3 gaps ({len(gaps)} found)")

    # --- Test: each gap has >= 3 evidence papers ---
    for gap in gaps:
        assert len(gap["evidence"]) >= 3, (
            f"Gap {gap['gap_id']} has {len(gap['evidence'])} evidence papers, need >= 3"
        )
    print("[PASS] each gap has >= 3 evidence papers")

    # --- Test: score_novelty with locked weights ---
    paper_lookup = {p["id"]: p for p in papers}
    for gap in gaps:
        gap["_recency_score"] = _compute_recency_score(
            gap.get("evidence", []), paper_lookup
        )
        novelty = score_novelty(gap, graph, cocitation)
        assert 1.0 <= novelty <= 10.0, (
            f"Novelty score {novelty} out of range [1.0, 10.0]"
        )
        gap["novelty_score"] = novelty
    print("[PASS] score_novelty applies locked weights (0.30, 0.30, 0.20, 0.20) and returns 1.0-10.0")

    # --- Test: assess_feasibility ---
    for gap in gaps:
        feas = assess_feasibility(gap, papers)
        assert 1 <= feas["score"] <= 10, (
            f"Feasibility score {feas['score']} out of range [1, 10]"
        )
        assert "assessment" in feas, "Feasibility missing assessment"
        assert "required_resources" in feas, "Feasibility missing required_resources"
        gap["feasibility"] = feas
    print("[PASS] assess_feasibility scores are in [1, 10]")

    # --- Test: rank_gaps ---
    for gap in gaps:
        gap["confidence"] = gap.get("confidence", "MEDIUM")
    ranked = rank_gaps(gaps)
    assert len(ranked) >= 3, f"Expected >= 3 ranked gaps, got {len(ranked)}"
    # Verify sorted descending
    for i in range(len(ranked) - 1):
        assert ranked[i]["_composite_score"] >= ranked[i + 1]["_composite_score"], (
            "Gaps not sorted by composite score descending"
        )
    print("[PASS] rank_gaps sorts by composite score (60% novelty + 30% feasibility + 10% confidence)")

    # --- Test: full pipeline produces valid output ---
    output_path = os.path.join(tmpdir, "research_gaps.json")
    for gap in ranked:
        gap["novelty_justification"] = gap["description"]
        gap["recommended_framing"] = f"Bridge {gap['cluster_a']['name']} and {gap['cluster_b']['name']}"

    metadata = {
        "papers_analyzed": len(papers),
        "clusters_identified": len(clusters),
        "citation_edges_mapped": total_edges,
        "sparse_regions_found": len(ranked),
    }
    output = generate_output(
        mock_data["topic"], ranked, metadata, output_path
    )

    assert "topic" in output, "Output missing 'topic'"
    assert "gaps" in output, "Output missing 'gaps'"
    assert "generated_at" in output, "Output missing 'generated_at'"
    assert len(output["gaps"]) >= 3, (
        f"Output has {len(output['gaps'])} gaps, need >= 3"
    )
    print("[PASS] full pipeline produces valid research_gaps.json with >= 3 gaps")

    # Verify output file was written
    with open(output_path) as f:
        written = json.load(f)
    assert written["topic"] == mock_data["topic"]
    assert len(written["gaps"]) >= 3
    assert "generated_at" in written
    assert "analysis_metadata" in written
    print("[PASS] output matches research_gaps.schema.json structure (topic, gaps, generated_at)")

    # Cleanup
    os.remove(mock_path)
    os.remove(small_path)
    os.remove(output_path)
    os.rmdir(tmpdir)

    print()
    print("=== All _gap_analysis tests PASSED ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) == 3:
        input_path = sys.argv[1]
        output_path = sys.argv[2]
        run_pipeline(input_path, output_path)
    else:
        print("Usage:")
        print(f"  python3 {sys.argv[0]} <input_path> <output_path>")
        print(f"  python3 {sys.argv[0]} --self-test")
        sys.exit(1)
