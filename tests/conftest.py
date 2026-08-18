"""Shared fixtures: an in-memory backend over a small fixture graph."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from server.backends import (Backend, Capabilities, ConsensusEdge, DateClaim,
                             EdgeFilters, EntityInfo, EdgeBatch, SearchResult,
                             TypedEdge, UnsupportedOperation)
from server.constants import CG_RELS


class FakeBackend(Backend):
    """In-memory backend mirroring Postgres semantics (including the
    wp_not_wd derivation and witness decoding)."""

    def __init__(self, entities, consensus, typed, dates=None,
                 witnesses_supported=True):
        # entities: {qid: (label, wp_count)}
        # consensus: [(src, dst, [lang codes])]
        # typed: [(src, dst, prop)]
        # dates: {qid: [(prop, time, precision, source_prop, source_target)]}
        self.entities = entities
        self.consensus = consensus
        self.typed = typed
        self.dates = dates or {}
        self.witnesses_supported = witnesses_supported
        self.edge_calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(witnesses=self.witnesses_supported, consensus=True,
                            dates=True, bulk=True, contract_version="1")

    def get_entities(self, qids):
        result = {}
        for qid in qids:
            label, wp = self.entities.get(qid, (qid, None))
            result[qid] = EntityInfo(qid=qid, label=label, wp_count=wp)
        return result

    def _wp_not_wd(self, src, dst):
        return not any((s == src and d == dst) or (s == dst and d == src)
                       for s, d, _ in self.typed)

    def get_edges(self, qids, filters=None, limit=None):
        self.edge_calls += 1
        qids = set(qids)
        filters = filters or EdgeFilters()
        batch = EdgeBatch()

        def touches(src, dst):
            if filters.direction == "out":
                return src in qids
            if filters.direction == "in":
                return dst in qids
            return src in qids or dst in qids

        if "consensus" in filters.edge_kinds:
            for src, dst, langs in self.consensus:
                if touches(src, dst) and len(langs) >= filters.min_consensus:
                    batch.consensus.append(ConsensusEdge(
                        src=src, dst=dst, wp_count=len(langs),
                        langs=list(langs) if self.witnesses_supported else None,
                        wp_not_wd=self._wp_not_wd(src, dst)))
        if "typed" in filters.edge_kinds:
            for src, dst, prop in self.typed:
                if not touches(src, dst):
                    continue
                if filters.props == "cg" and prop not in CG_RELS:
                    continue
                if isinstance(filters.props, (list, set, tuple)) \
                        and prop not in filters.props:
                    continue
                batch.typed.append(TypedEdge(src=src, dst=dst, prop=prop))
        if limit is not None:
            if len(batch.consensus) > limit:
                batch.consensus = batch.consensus[:limit]
                batch.consensus_truncated = True
            if len(batch.typed) > limit:
                batch.typed = batch.typed[:limit]
                batch.typed_truncated = True
        return batch

    def get_dates(self, qids):
        result = {}
        for qid in qids:
            claims = self.dates.get(qid)
            if claims:
                result[qid] = [DateClaim(property=p, time_value=t, precision=pr,
                                         source_property=sp, source_target=st)
                               for p, t, pr, sp, st in claims]
        return result

    def get_witnesses(self, pairs):
        if not self.witnesses_supported:
            raise UnsupportedOperation("no witnesses")
        wanted = set(pairs)
        return {(s, d): list(langs) for s, d, langs in self.consensus
                if (s, d) in wanted}

    def search(self, text, limit=10):
        text = text.lower()
        hits = [SearchResult(qid=qid, label=label)
                for qid, (label, _wp) in self.entities.items()
                if label.lower().startswith(text)]
        return hits[:limit]


@pytest.fixture
def fixture_backend():
    entities = {
        "Q1": ("Alpha", 50),
        "Q2": ("Beta", 40),
        "Q3": ("Gamma", 30),
        "Q4": ("Delta", 20),
        "Q5": ("Epsilon", 10),
        "Q6": ("Zeta", 5),
    }
    consensus = [
        # strong, WD-covered edge (typed P50 below) -> wp_not_wd False
        ("Q1", "Q2", ["en", "de", "fr"]),
        # bot-cluster heavy, no typed edge -> wp_not_wd True;
        # raw 5 but effective 2 with the Lsjbot family capped at 1
        ("Q1", "Q3", ["ceb", "war", "sv", "vi", "en"]),
        # second-hop edge
        ("Q2", "Q4", ["en", "de"]),
        # edge between two hop-1 nodes: only reachable via the closure pass
        ("Q2", "Q3", ["en"]),
    ]
    typed = [
        ("Q1", "Q2", "P50"),    # author (cg)
        ("Q1", "Q5", "P31"),    # instance of (non-cg) -> typed-only candidate
        ("Q4", "Q6", "P155"),   # follows (cg)
    ]
    dates = {
        "Q1": [("P569", "+1900-01-01T00:00:00Z", 9, "", ""),
               ("P570", "+1980-01-01T00:00:00Z", 9, "", "")],
        "Q2": [("P571", "+1950-00-00T00:00:00Z", 7, "", ""),
               ("P580", "+1960-01-01T00:00:00Z", 9, "P108", "Q1")],
    }
    return FakeBackend(entities, consensus, typed, dates)
