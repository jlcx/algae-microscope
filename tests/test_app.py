"""API endpoint tests (SPEC.md §7) against the fake backend."""

import pytest
from fastapi.testclient import TestClient

from server.api import create_app
from server.config import Config


@pytest.fixture
def client(fixture_backend):
    config = Config()
    app = create_app(config=config, backend=fixture_backend)
    return TestClient(app)


def test_capabilities(client):
    caps = client.get("/api/capabilities").json()
    assert caps["witnesses"] is True
    assert caps["consensus"] is True
    assert caps["contract_version"] == "1"


def test_config_endpoint(client):
    config = client.get("/api/config").json()
    assert config["witnesses"]["clone_families"] == [["ceb", "war", "sv", "vi"]]
    assert "P50" in config["cg_rels"]
    assert config["prop_categories"]["P828"] == "causation"


def test_search(client):
    hits = client.get("/api/search", params={"q": "Alp"}).json()
    assert hits[0]["qid"] == "Q1"


def test_neighborhood_with_label_seed(client):
    resp = client.post("/api/neighborhood",
                       json={"seeds": ["Alpha"], "hops": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema"] == "algae-microscope-neighborhood"
    qids = {n["qid"] for n in data["nodes"]}
    assert "Q1" in qids and "Q2" in qids
    # effective count uses the Lsjbot default family config
    edge = next(e for e in data["edges"] if e["id"] == "c:Q1:Q3")
    assert edge["wp_count"] == 5
    assert edge["effective_count"] == 2.0
    assert edge["wp_not_wd"] is True


def test_neighborhood_requires_seeds(client):
    assert client.post("/api/neighborhood", json={}).status_code == 422


def test_hops_clamped_to_max(client):
    resp = client.post("/api/neighborhood",
                       json={"seeds": ["Q1"], "hops": 99})
    assert resp.json()["params"]["hops"] == 3  # config max_hops


def test_expand_delta(client):
    base = client.post("/api/neighborhood",
                       json={"seeds": ["Q1"], "hops": 1}).json()
    state = [n["qid"] for n in base["nodes"]]
    delta = client.post("/api/neighborhood/expand",
                        json={"state": state, "node": "Q2"}).json()
    assert {n["qid"] for n in delta["nodes"]} == {"Q4"}


def test_entity_detail(client):
    data = client.get("/api/entity/Q1").json()
    assert data["label"] == "Alpha"
    assert any(d["property"] == "P570" for d in data["dates"])
    assert client.get("/api/entity/notaqid").status_code == 422


def test_edge_detail(client):
    data = client.get("/api/edge/Q1/Q2").json()
    assert len(data["consensus"]) == 1
    assert data["consensus"][0]["langs"] == ["en", "de", "fr"]
    assert any(e["prop"] == "P50" for e in data["typed"])


def test_witness_ops(client):
    data = client.get("/api/witness_ops", params={
        "a_src": "Q1", "a_dst": "Q2", "b_src": "Q1", "b_dst": "Q3"}).json()
    assert data["shared"] == ["en"]
    assert "de" in data["only_a"]
    assert "ceb" in data["only_b"]


def test_unhandled_errors_carry_detail(fixture_backend):
    """Unexpected exceptions must surface their message, not a bare
    'Internal Server Error'."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("wires crossed")
    fixture_backend.get_edges = boom
    app = create_app(config=Config(), backend=fixture_backend)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/neighborhood", json={"seeds": ["Q1"]})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "RuntimeError: wires crossed"


def test_witness_ops_unsupported(client, fixture_backend):
    fixture_backend.witnesses_supported = False
    resp = client.get("/api/witness_ops", params={
        "a_src": "Q1", "a_dst": "Q2", "b_src": "Q1", "b_dst": "Q3"})
    assert resp.status_code == 501
