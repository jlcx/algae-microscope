"""Neighborhood expansion (SPEC.md §3): bounded frontier queries with a
per-hop budget and a pluggable ranking function for budget cuts."""

from __future__ import annotations

from typing import Callable, Iterable

from ..backends import Backend, ConsensusEdge, EdgeFilters, TypedEdge
from .model import Edge, Neighborhood, Node
from .witnesses import WitnessWeights

# score, then tie-breaks: edge multiplicity, then lower QID number (older,
# generally more notable entities win ties).
Score = tuple[float, int, int]

# A scorer maps (candidate qid, consensus edges to the graph, typed edges to
# the graph, witness weights) to a comparable score. §3.2: default is the max
# consensus strength of any connecting edge — effective count when witnesses
# are available, raw wp_count otherwise — and a fixed low score for nodes
# reachable only via typed WD edges.
Scorer = Callable[[str, list[ConsensusEdge], list[TypedEdge], WitnessWeights], Score]

TYPED_ONLY_SCORE = 0.5


def _qid_number(qid: str) -> int:
    try:
        return int(qid.lstrip("QP"))
    except ValueError:
        return 1 << 31


def default_scorer(qid: str, consensus: list[ConsensusEdge],
                   typed: list[TypedEdge], weights: WitnessWeights) -> Score:
    best = 0.0
    for edge in consensus:
        strength = (weights.effective_count(edge.langs)
                    if edge.langs is not None else float(edge.wp_count))
        best = max(best, strength)
    if best == 0.0 and typed:
        best = TYPED_ONLY_SCORE
    return (best, len(consensus) + len(typed), -_qid_number(qid))


def _consensus_edge(raw: ConsensusEdge, weights: WitnessWeights) -> Edge:
    return Edge(kind="consensus", src=raw.src, dst=raw.dst,
                wp_count=raw.wp_count, langs=raw.langs,
                effective_count=(weights.effective_count(raw.langs)
                                 if raw.langs is not None else None),
                wp_not_wd=raw.wp_not_wd)


def _typed_edge(raw: TypedEdge) -> Edge:
    return Edge(kind="typed", src=raw.src, dst=raw.dst, prop=raw.prop)


def _one_hop(backend: Backend, frontier: list[str], known: set[str],
             filters: EdgeFilters, budget: int, edge_limit: int,
             weights: WitnessWeights, scorer: Scorer):
    """Fetch edges touching `frontier`, pick the top-`budget` new nodes.

    Returns (new_qids, kept_edges, hop_provenance). kept_edges contains every
    fetched edge whose endpoints both land inside known ∪ new_qids.
    """
    batch = backend.get_edges(frontier, filters, limit=edge_limit)

    candidate_consensus: dict[str, list[ConsensusEdge]] = {}
    candidate_typed: dict[str, list[TypedEdge]] = {}
    for edge in batch.consensus:
        for endpoint in (edge.src, edge.dst):
            if endpoint not in known:
                candidate_consensus.setdefault(endpoint, []).append(edge)
    for edge in batch.typed:
        for endpoint in (edge.src, edge.dst):
            if endpoint not in known:
                candidate_typed.setdefault(endpoint, []).append(edge)

    candidates = set(candidate_consensus) | set(candidate_typed)
    ranked = sorted(
        candidates,
        key=lambda q: scorer(q, candidate_consensus.get(q, []),
                             candidate_typed.get(q, []), weights),
        reverse=True)
    new_qids = ranked[:budget]
    inside = known | set(new_qids)

    kept: list[Edge] = []
    for raw in batch.consensus:
        if raw.src in inside and raw.dst in inside:
            kept.append(_consensus_edge(raw, weights))
    for raw in batch.typed:
        if raw.src in inside and raw.dst in inside:
            kept.append(_typed_edge(raw))

    provenance = {
        "frontier_size": len(frontier),
        "candidates": len(candidates),
        "retained": len(new_qids),
        "truncated_by_budget": len(candidates) - len(new_qids),
        "consensus_truncated": batch.consensus_truncated,
        "typed_truncated": batch.typed_truncated,
    }
    return new_qids, kept, provenance


def _enrich_nodes(backend: Backend, neighborhood: Neighborhood) -> None:
    qids = list(neighborhood.nodes)
    entities = backend.get_entities(qids)
    for qid, info in entities.items():
        node = neighborhood.nodes.get(qid)
        if node:
            node.label = info.label
            node.wp_count = info.wp_count
    if backend.capabilities().dates:
        dates = backend.get_dates(qids)
        for qid, claims in dates.items():
            node = neighborhood.nodes.get(qid)
            if node:
                node.dates = claims


def expand(backend: Backend, seeds: list[str], hops: int, budget: int,
           filters: EdgeFilters | None = None,
           weights: WitnessWeights | None = None,
           edge_limit: int = 5000,
           scorer: Scorer | None = None) -> Neighborhood:
    """Expand `hops` rounds from `seeds` (§3.2), then fetch labels and dates
    for every retained node."""
    filters = filters or EdgeFilters()
    weights = weights or WitnessWeights()
    scorer = scorer or default_scorer

    capabilities = backend.capabilities()
    neighborhood = Neighborhood(
        seeds=list(seeds),
        params={"hops": hops, "budget": budget, "filters": filters.to_dict()},
        backend_mode=type(backend).__name__,
        capabilities=capabilities.to_dict(),
    )
    for qid in seeds:
        neighborhood.nodes[qid] = Node(qid=qid, label=qid, seed=True, hop=0)

    frontier = list(seeds)
    hop_records = []
    for hop in range(1, hops + 1):
        if not frontier:
            break
        new_qids, edges, record = _one_hop(
            backend, frontier, set(neighborhood.nodes), filters, budget,
            edge_limit, weights, scorer)
        record["hop"] = hop
        hop_records.append(record)
        for qid in new_qids:
            neighborhood.nodes[qid] = Node(qid=qid, label=qid, hop=hop)
        for edge in edges:
            neighborhood.add_edge(edge)
        frontier = new_qids

    # Closure pass: edges among the last frontier's nodes were never fetched
    # (each round only fetches edges touching the *previous* frontier). Only
    # edges with both endpoints already in the graph are needed, which
    # backends can serve far cheaper than a full frontier fetch.
    if frontier and hops > 0:
        batch = backend.get_edges_within(list(neighborhood.nodes), filters,
                                         limit=edge_limit)
        for raw in batch.consensus:
            neighborhood.add_edge(_consensus_edge(raw, weights))
        for raw in batch.typed:
            neighborhood.add_edge(_typed_edge(raw))

    neighborhood.provenance = {"hops": hop_records}
    _enrich_nodes(backend, neighborhood)
    return neighborhood


def expand_delta(backend: Backend, state_qids: Iterable[str], node: str,
                 budget: int, filters: EdgeFilters | None = None,
                 weights: WitnessWeights | None = None,
                 edge_limit: int = 5000,
                 scorer: Scorer | None = None) -> dict:
    """One more hop from a single node against a client-held state (§7):
    returns a delta {nodes, edges, provenance} of only what is new."""
    filters = filters or EdgeFilters()
    weights = weights or WitnessWeights()
    scorer = scorer or default_scorer
    known = set(state_qids) | {node}

    new_qids, edges, record = _one_hop(
        backend, [node], known, filters, budget, edge_limit, weights, scorer)

    delta = Neighborhood(seeds=[node], params={"budget": budget,
                                               "filters": filters.to_dict()},
                         backend_mode=type(backend).__name__,
                         capabilities=backend.capabilities().to_dict())
    for qid in new_qids:
        delta.nodes[qid] = Node(qid=qid, label=qid, hop=1)
    for edge in edges:
        delta.add_edge(edge)
    _enrich_nodes(backend, delta)

    return {
        "nodes": [n.to_dict() for n in delta.nodes.values()],
        "edges": [e.to_dict() for e in delta.edges.values()],
        "provenance": record,
    }
