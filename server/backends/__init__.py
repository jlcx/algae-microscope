"""Backend seam (SPEC.md §2.1): Postgres and API-only modes are
interchangeable behind this interface; capabilities drive UI adaptation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Capabilities:
    witnesses: bool
    consensus: bool
    dates: bool
    bulk: bool
    contract_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "witnesses": self.witnesses,
            "consensus": self.consensus,
            "dates": self.dates,
            "bulk": self.bulk,
            "contract_version": self.contract_version,
        }


@dataclass
class EntityInfo:
    qid: str
    label: str
    wp_count: int | None = None


@dataclass
class ConsensusEdge:
    src: str
    dst: str
    wp_count: int
    # Witness language codes (decoded); None when the backend lacks witness
    # support (§1.2 degraded mode).
    langs: list[str] | None = None
    # True when no typed edge exists in either direction between the pair
    # (queries/wp_not_wd.sql semantics); None if not computed.
    wp_not_wd: bool | None = None


@dataclass
class TypedEdge:
    src: str
    dst: str
    prop: str


@dataclass
class DateClaim:
    property: str
    time_value: str
    precision: int
    source_property: str = ""   # nested: parent claim's property; '' top-level
    source_target: str = ""     # nested: parent claim's target QID

    def to_dict(self) -> dict:
        return {
            "property": self.property,
            "time_value": self.time_value,
            "precision": self.precision,
            "source_property": self.source_property,
            "source_target": self.source_target,
        }


@dataclass
class EdgeFilters:
    """Fetch-time edge filters (§3.3), pushed into SQL where possible."""
    min_consensus: int = 0
    props: str | list[str] = "all"      # 'cg', 'all', or explicit list
    edge_kinds: set[str] = field(default_factory=lambda: {"consensus", "typed"})
    direction: str = "both"             # 'both', 'out', 'in'

    def to_dict(self) -> dict:
        return {
            "min_consensus": self.min_consensus,
            "props": self.props if isinstance(self.props, str) else list(self.props),
            "edge_kinds": sorted(self.edge_kinds),
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "EdgeFilters":
        f = cls()
        if not data:
            return f
        if "min_consensus" in data:
            f.min_consensus = int(data["min_consensus"])
        if "props" in data and data["props"] is not None:
            f.props = data["props"]
        if "edge_kinds" in data and data["edge_kinds"] is not None:
            f.edge_kinds = set(data["edge_kinds"])
        if "direction" in data and data["direction"] is not None:
            f.direction = data["direction"]
        return f


@dataclass
class EdgeBatch:
    consensus: list[ConsensusEdge] = field(default_factory=list)
    typed: list[TypedEdge] = field(default_factory=list)
    # True if a server-side limit cut off results for the respective kind.
    consensus_truncated: bool = False
    typed_truncated: bool = False


@dataclass
class SearchResult:
    qid: str
    label: str
    description: str = ""


class BackendError(Exception):
    pass


class UnsupportedOperation(BackendError):
    """Raised when a backend is asked for data outside its capabilities."""


class Backend(ABC):
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def get_entities(self, qids: Iterable[str]) -> dict[str, EntityInfo]: ...

    @abstractmethod
    def get_edges(self, qids: Iterable[str],
                  filters: EdgeFilters | None = None,
                  limit: int | None = None) -> EdgeBatch:
        """All edges touching any of `qids`, honoring filters and a per-kind
        result limit."""

    def get_edges_within(self, qids: Iterable[str],
                         filters: EdgeFilters | None = None,
                         limit: int | None = None) -> EdgeBatch:
        """Edges whose BOTH endpoints are in `qids` (the expansion closure
        pass, §3.2). Default: fetch-and-filter; backends override when they
        can do better (Postgres probes the primary key per pair instead of
        scanning every edge of hub nodes)."""
        qids = list(qids)
        inside = set(qids)
        batch = self.get_edges(qids, filters, limit)
        batch.consensus = [e for e in batch.consensus
                           if e.src in inside and e.dst in inside]
        batch.typed = [e for e in batch.typed
                       if e.src in inside and e.dst in inside]
        return batch

    @abstractmethod
    def get_dates(self, qids: Iterable[str]) -> dict[str, list[DateClaim]]: ...

    @abstractmethod
    def get_witnesses(self, pairs: Iterable[tuple[str, str]]
                      ) -> dict[tuple[str, str], list[str]]:
        """Witness language codes per (src, dst) consensus pair. Raises
        UnsupportedOperation when the backend lacks witnesses."""

    @abstractmethod
    def search(self, text: str, limit: int = 10) -> list[SearchResult]: ...

    def close(self) -> None:
        pass


def make_backend(config) -> Backend:
    """Instantiate the backend selected by config.backend.mode."""
    mode = config.backend.mode
    if mode == "postgres":
        from .postgres import PostgresBackend
        return PostgresBackend(config)
    if mode == "api":
        from .api_only import ApiOnlyBackend
        return ApiOnlyBackend(config)
    raise BackendError(f"unknown backend mode: {mode!r} (expected 'postgres' or 'api')")
