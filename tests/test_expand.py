from server.backends import EdgeFilters
from server.neighborhood import WitnessWeights, expand, expand_delta
from server.neighborhood.model import Neighborhood

LSJBOT_WEIGHTS = WitnessWeights(families=[["ceb", "war", "sv", "vi"]])


def test_single_hop_all(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100,
               weights=LSJBOT_WEIGHTS)
    assert set(n.nodes) == {"Q1", "Q2", "Q3", "Q5"}
    assert n.nodes["Q1"].seed and n.nodes["Q1"].hop == 0
    assert n.nodes["Q2"].hop == 1
    # labels and dates were enriched
    assert n.nodes["Q2"].label == "Beta"
    assert any(d.property == "P569" for d in n.nodes["Q1"].dates)
    # nested date claim carried through
    assert any(d.source_property == "P108" for d in n.nodes["Q2"].dates)


def test_budget_ranking_prefers_effective_consensus(fixture_backend):
    # candidates from Q1: Q2 (eff 3), Q3 (eff 2 after Lsjbot cap), Q5 (typed-only)
    n = expand(fixture_backend, ["Q1"], hops=1, budget=2,
               weights=LSJBOT_WEIGHTS)
    assert set(n.nodes) == {"Q1", "Q2", "Q3"}
    # edges to the cut node are dropped
    assert all("Q5" not in (e.src, e.dst) for e in n.edges.values())
    hop = n.provenance["hops"][0]
    assert hop["candidates"] == 3
    assert hop["retained"] == 2
    assert hop["truncated_by_budget"] == 1


def test_budget_one_keeps_strongest(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=1, budget=1,
               weights=LSJBOT_WEIGHTS)
    assert set(n.nodes) == {"Q1", "Q2"}


def test_raw_counts_rank_differently(fixture_backend):
    # without clone families, Q1-Q3 (wp 5) outranks Q1-Q2 (wp 3)
    n = expand(fixture_backend, ["Q1"], hops=1, budget=1,
               weights=WitnessWeights())
    assert set(n.nodes) == {"Q1", "Q3"}


def test_wp_not_wd_flags(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100)
    by_id = n.edges
    assert by_id["c:Q1:Q3"].wp_not_wd is True
    assert by_id["c:Q1:Q2"].wp_not_wd is False


def test_closure_pass_fetches_frontier_internal_edges(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100)
    # Q2-Q3 touches neither seed; only the closure pass can find it
    assert "c:Q2:Q3" in n.edges


def test_get_edges_within_keeps_only_internal_edges(fixture_backend):
    batch = fixture_backend.get_edges_within(["Q1", "Q2", "Q3"])
    consensus_pairs = {(e.src, e.dst) for e in batch.consensus}
    assert consensus_pairs == {("Q1", "Q2"), ("Q1", "Q3"), ("Q2", "Q3")}
    typed = {(e.src, e.dst, e.prop) for e in batch.typed}
    assert typed == {("Q1", "Q2", "P50")}  # Q1->Q5 edge leaves the set


def test_two_hops(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=2, budget=100)
    assert "Q4" in n.nodes and n.nodes["Q4"].hop == 2
    # Q6 hangs off Q4 and is only reachable at hop 3
    assert "Q6" not in n.nodes
    n3 = expand(fixture_backend, ["Q1"], hops=3, budget=100)
    assert "Q6" in n3.nodes and n3.nodes["Q6"].hop == 3


def test_multi_seed_union(fixture_backend):
    n = expand(fixture_backend, ["Q1", "Q4"], hops=1, budget=100)
    assert {"Q1", "Q4"} <= {q for q, node in n.nodes.items() if node.seed}
    assert "Q6" in n.nodes  # typed edge from seed Q4


def test_edge_filters_pushdown(fixture_backend):
    filters = EdgeFilters(props="cg")
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100, filters=filters)
    typed_props = {e.prop for e in n.edges.values() if e.kind == "typed"}
    assert "P31" not in typed_props
    assert "P50" in typed_props


def test_min_consensus_filter(fixture_backend):
    filters = EdgeFilters(min_consensus=3, edge_kinds={"consensus"})
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100, filters=filters)
    assert all(e.wp_count >= 3 for e in n.edges.values())
    assert "Q5" not in n.nodes  # typed edges disabled


def test_degraded_no_witnesses(fixture_backend):
    fixture_backend.witnesses_supported = False
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100,
               weights=LSJBOT_WEIGHTS)
    edge = n.edges["c:Q1:Q3"]
    assert edge.langs is None
    assert edge.effective_count is None
    assert edge.wp_count == 5  # raw count still usable as opaque scalar


def test_serialization_roundtrip(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=2, budget=100,
               weights=LSJBOT_WEIGHTS)
    data = n.to_dict()
    assert data["schema"] == "algae-microscope-neighborhood"
    restored = Neighborhood.from_dict(data)
    assert set(restored.nodes) == set(n.nodes)
    assert set(restored.edges) == set(n.edges)
    assert restored.nodes["Q1"].dates[0].property == \
        n.nodes["Q1"].dates[0].property


def test_expand_delta(fixture_backend):
    n = expand(fixture_backend, ["Q1"], hops=1, budget=100)
    state = list(n.nodes)
    assert "Q4" not in state
    delta = expand_delta(fixture_backend, state, "Q2", budget=100)
    new_qids = {node["qid"] for node in delta["nodes"]}
    assert new_qids == {"Q4"}
    edge_ids = {e["id"] for e in delta["edges"]}
    assert "c:Q2:Q4" in edge_ids
