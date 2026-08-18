"""Serializable neighborhood object (SPEC.md §6.2).

The expanded neighborhood is the unit of server→web transfer, CLI export, and
permalink state, and the input format for downstream sheaf analysis and future
CauseGraph ingestion. The schema is versioned; bump NEIGHBORHOOD_SCHEMA_VERSION
on incompatible changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import NEIGHBORHOOD_SCHEMA_VERSION, __version__
from ..backends import DateClaim


@dataclass
class Node:
    qid: str
    label: str
    wp_count: int | None = None
    seed: bool = False
    hop: int = 0
    dates: list[DateClaim] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "qid": self.qid,
            "label": self.label,
            "wp_count": self.wp_count,
            "seed": self.seed,
            "hop": self.hop,
            "dates": [d.to_dict() for d in self.dates],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            qid=data["qid"], label=data.get("label", data["qid"]),
            wp_count=data.get("wp_count"), seed=data.get("seed", False),
            hop=data.get("hop", 0),
            dates=[DateClaim(**d) for d in data.get("dates", [])])


@dataclass
class Edge:
    """A single parallel edge. Consensus and typed edges between the same
    pair are kept distinct (§3.4)."""
    kind: str                    # 'consensus' or 'typed'
    src: str
    dst: str
    prop: str | None = None      # typed only
    wp_count: int | None = None  # consensus only
    langs: list[str] | None = None       # witness codes; None if unsupported
    effective_count: float | None = None
    wp_not_wd: bool | None = None
    # Extensible annotation map for e.g. precomputed obstruction data (§9.2).
    annotations: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        if self.kind == "typed":
            return f"t:{self.src}:{self.dst}:{self.prop}"
        return f"c:{self.src}:{self.dst}"

    def to_dict(self) -> dict:
        d = {"id": self.id, "kind": self.kind, "src": self.src, "dst": self.dst}
        if self.kind == "typed":
            d["prop"] = self.prop
        else:
            d["wp_count"] = self.wp_count
            d["langs"] = self.langs
            d["effective_count"] = self.effective_count
            d["wp_not_wd"] = self.wp_not_wd
        if self.annotations:
            d["annotations"] = self.annotations
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            kind=data["kind"], src=data["src"], dst=data["dst"],
            prop=data.get("prop"), wp_count=data.get("wp_count"),
            langs=data.get("langs"),
            effective_count=data.get("effective_count"),
            wp_not_wd=data.get("wp_not_wd"),
            annotations=data.get("annotations", {}))


@dataclass
class Neighborhood:
    seeds: list[str]
    params: dict                 # {hops, budget, filters}
    backend_mode: str
    capabilities: dict
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    def add_edge(self, edge: Edge) -> None:
        self.edges.setdefault(edge.id, edge)

    def to_dict(self) -> dict:
        return {
            "schema": "algae-microscope-neighborhood",
            "schema_version": NEIGHBORHOOD_SCHEMA_VERSION,
            "generated_by": f"algae-microscope/{__version__}",
            "seeds": self.seeds,
            "params": self.params,
            "backend": {"mode": self.backend_mode,
                        "capabilities": self.capabilities},
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Neighborhood":
        version = data.get("schema_version")
        if version != NEIGHBORHOOD_SCHEMA_VERSION:
            raise ValueError(f"unsupported neighborhood schema_version: {version}")
        backend = data.get("backend", {})
        neighborhood = cls(
            seeds=data.get("seeds", []), params=data.get("params", {}),
            backend_mode=backend.get("mode", "?"),
            capabilities=backend.get("capabilities", {}),
            provenance=data.get("provenance", {}))
        for nd in data.get("nodes", []):
            node = Node.from_dict(nd)
            neighborhood.nodes[node.qid] = node
        for ed in data.get("edges", []):
            neighborhood.add_edge(Edge.from_dict(ed))
        return neighborhood
