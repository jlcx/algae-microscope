"""API-only backend (SPEC.md §2.3): live Wikidata APIs, no local database.

Shows Wikidata structure and dates only — no cross-language consensus, no
witnesses (capabilities are false; the UI adapts). Claim extraction mirrors
algae-farmer wd_preproc (commit f1833232): wikibase-item/property mainsnaks
and qualifiers become typed edges; ALL_TIMES mainsnaks and nested qualifier
dates on TIMES_PLUS_NESTED claims become date claims; best_label and wp_count
follow the same sitelink rules.

Requests carry a proper User-Agent, are rate limited, and entity JSON is
cached on disk keyed by (qid, revision) with a TTL-based revision check.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable

from ..constants import ALL_TIMES, CG_RELS, LANG_ORDER, TIMES_PLUS_NESTED
from . import (Backend, BackendError, Capabilities, DateClaim, EdgeBatch,
               EdgeFilters, EntityInfo, SearchResult, TypedEdge,
               UnsupportedOperation)

API_BASE = "https://www.wikidata.org/w/api.php"
SPARQL_BASE = "https://query.wikidata.org/sparql"
BATCH = 50  # documented cap on ids per wbgetentities call
MAX_TIME_VALUE_LEN = 32  # matches wd_dates.time_value VARCHAR(32)

_SITELINK_EXCLUDE = ("quote", "source", "books", "news", "versity", "voyage",
                     "species", "commons", "data", "media", "meta")


def _is_wikipedia_sitelink(key: str) -> bool:
    return (key.endswith("wiki")
            and not any(part in key for part in _SITELINK_EXCLUDE)
            and key != "wikidatawiki")


def best_label(entity: dict) -> str:
    """Mirror wd_preproc: LANG_ORDER sitelink titles, then the 'mul' label,
    then LANG_ORDER labels, then any label, then the QID."""
    sitelinks = entity.get("sitelinks") or {}
    for lang in LANG_ORDER:
        title = (sitelinks.get(f"{lang}wiki") or {}).get("title")
        if title:
            return title
    labels = entity.get("labels") or {}
    mul = (labels.get("mul") or {}).get("value")
    if mul:
        return mul
    for lang in LANG_ORDER:
        value = (labels.get(lang) or {}).get("value")
        if value:
            return value
    for obj in labels.values():
        if obj.get("value"):
            return obj["value"]
    return entity.get("id", "?")


def wp_count(entity: dict) -> int:
    return sum(1 for key in (entity.get("sitelinks") or {})
               if _is_wikipedia_sitelink(key))


def _item_target(snak: dict) -> str | None:
    if snak.get("datatype") not in ("wikibase-item", "wikibase-property"):
        return None
    value = (snak.get("datavalue") or {}).get("value")
    if not isinstance(value, dict):
        return None  # somevalue/novalue snaks have no target
    return value.get("id")


def extract_typed_edges(entity: dict) -> list[TypedEdge]:
    qid = entity.get("id")
    edges = []
    for prop, claims in (entity.get("claims") or {}).items():
        for claim in claims:
            target = _item_target(claim.get("mainsnak") or {})
            if target:
                edges.append(TypedEdge(src=qid, dst=target, prop=prop))
            for qprop, qvals in (claim.get("qualifiers") or {}).items():
                for qval in qvals:
                    target = _item_target(qval)
                    if target:
                        edges.append(TypedEdge(src=qid, dst=target, prop=qprop))
    return edges


def _time_value(snak: dict) -> tuple[str, int] | None:
    """(time, precision) from a snak, or None — mirrors wd_preproc's
    extract_time_value option chaining (value may be absent or non-dict)."""
    value = (snak.get("datavalue") or {}).get("value")
    if not isinstance(value, dict):
        return None
    tv, prec = value.get("time"), value.get("precision")
    if not tv or prec is None or len(tv) > MAX_TIME_VALUE_LEN:
        return None
    return tv, int(prec)


def extract_dates(entity: dict) -> list[DateClaim]:
    dates = []
    for prop, claims in (entity.get("claims") or {}).items():
        for claim in claims:
            mainsnak = claim.get("mainsnak") or {}
            if prop in ALL_TIMES:
                tv_prec = _time_value(mainsnak)
                if tv_prec:
                    dates.append(DateClaim(property=prop, time_value=tv_prec[0],
                                           precision=tv_prec[1]))
            if prop in TIMES_PLUS_NESTED and claim.get("qualifiers"):
                source_target = _item_target(mainsnak) or ""
                for qprop, qvals in claim["qualifiers"].items():
                    if qprop not in ALL_TIMES:
                        continue
                    for qval in qvals:
                        tv_prec = _time_value(qval)
                        if tv_prec:
                            dates.append(DateClaim(
                                property=qprop, time_value=tv_prec[0],
                                precision=tv_prec[1],
                                source_property=prop,
                                source_target=source_target))
    return dates


class _EntityCache:
    """On-disk entity JSON cache keyed by (qid, revision), §2.4/§6.3: entries
    younger than the TTL are served directly; older entries are revalidated
    against the current revision id and refreshed only when it changed."""

    def __init__(self, cache_dir: str, ttl_seconds: int):
        self.dir = Path(cache_dir).expanduser() / "entities"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    def _path(self, qid: str) -> Path:
        return self.dir / f"{qid}.json"

    def load(self, qid: str) -> dict | None:
        try:
            with open(self._path(qid)) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def store(self, qid: str, entity: dict) -> None:
        record = {"revision": entity.get("lastrevid"),
                  "fetched": time.time(), "entity": entity}
        tmp = self._path(qid).with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(record, f)
        tmp.replace(self._path(qid))

    def touch(self, qid: str) -> None:
        record = self.load(qid)
        if record:
            record["fetched"] = time.time()
            tmp = self._path(qid).with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(record, f)
            tmp.replace(self._path(qid))

    def fresh(self, record: dict) -> bool:
        return time.time() - record.get("fetched", 0) < self.ttl


class ApiOnlyBackend(Backend):
    def __init__(self, config):
        api_config = config.api_backend
        self.user_agent = api_config.user_agent
        self.min_interval = api_config.min_request_interval
        self.sparql_inbound = api_config.sparql_inbound
        self.sparql_limit = api_config.sparql_limit
        self.cache = _EntityCache(api_config.cache_dir,
                                  api_config.cache_ttl_seconds)
        self._lock = threading.Lock()
        self._last_request = 0.0

    def capabilities(self) -> Capabilities:
        return Capabilities(witnesses=False, consensus=False, dates=True,
                            bulk=False, contract_version=None)

    # --- HTTP plumbing ---

    def _request(self, url: str, params: dict | None = None) -> dict:
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            with self._lock:
                wait = self._last_request + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last_request = time.monotonic()
            req = urllib.request.Request(url)
            req.add_header("User-Agent", self.user_agent)
            req.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise BackendError(f"API request failed: {e}") from e
            except urllib.error.URLError as e:
                raise BackendError(f"API request failed: {e}") from e
        raise BackendError("API request failed after retries")

    def _api(self, **params) -> dict:
        params.setdefault("format", "json")
        result = self._request(API_BASE, params)
        if "error" in result:
            raise BackendError(f"Wikidata API error: {result['error']}")
        return result

    # --- entity fetch + cache ---

    def _fetch_entities(self, qids: list[str]) -> dict[str, dict]:
        fetched: dict[str, dict] = {}
        for i in range(0, len(qids), BATCH):
            chunk = qids[i:i + BATCH]
            result = self._api(action="wbgetentities", ids="|".join(chunk),
                               props="labels|claims|sitelinks|info")
            for qid, entity in (result.get("entities") or {}).items():
                if "missing" not in entity:
                    fetched[qid] = entity
                    self.cache.store(qid, entity)
        return fetched

    def _revisions(self, qids: list[str]) -> dict[str, int]:
        revs: dict[str, int] = {}
        for i in range(0, len(qids), BATCH):
            chunk = qids[i:i + BATCH]
            result = self._api(action="wbgetentities", ids="|".join(chunk),
                               props="info")
            for qid, entity in (result.get("entities") or {}).items():
                if "missing" not in entity and entity.get("lastrevid"):
                    revs[qid] = entity["lastrevid"]
        return revs

    def _entities_json(self, qids: Iterable[str]) -> dict[str, dict]:
        qids = [q for q in dict.fromkeys(qids)]  # dedupe, keep order
        result: dict[str, dict] = {}
        stale: list[str] = []
        missing: list[str] = []
        for qid in qids:
            record = self.cache.load(qid)
            if record is None:
                missing.append(qid)
            elif self.cache.fresh(record):
                result[qid] = record["entity"]
            else:
                stale.append(qid)
        if stale:
            current = self._revisions(stale)
            refetch = []
            for qid in stale:
                record = self.cache.load(qid)
                if record and current.get(qid) == record.get("revision"):
                    self.cache.touch(qid)
                    result[qid] = record["entity"]
                else:
                    refetch.append(qid)
            missing.extend(refetch)
        if missing:
            result.update(self._fetch_entities(missing))
        return result

    # --- Backend interface ---

    def get_entities(self, qids: Iterable[str]) -> dict[str, EntityInfo]:
        qids = list(qids)
        entities = self._entities_json(qids)
        result = {}
        for qid in qids:
            entity = entities.get(qid)
            if entity is None:
                result[qid] = EntityInfo(qid=qid, label=qid, wp_count=None)
            else:
                result[qid] = EntityInfo(qid=qid, label=best_label(entity),
                                         wp_count=wp_count(entity))
        return result

    def _prop_allowed(self, prop: str, props) -> bool:
        if props == "all":
            return True
        if props == "cg":
            return prop in CG_RELS
        return prop in props

    def get_edges(self, qids: Iterable[str],
                  filters: EdgeFilters | None = None,
                  limit: int | None = None) -> EdgeBatch:
        qids = list(qids)
        filters = filters or EdgeFilters()
        limit = limit or 5000
        batch = EdgeBatch()
        if not qids or "typed" not in filters.edge_kinds:
            return batch
        seen: set[tuple[str, str, str]] = set()
        edges: list[TypedEdge] = []

        if filters.direction in ("both", "out"):
            entities = self._entities_json(qids)
            for entity in entities.values():
                for edge in extract_typed_edges(entity):
                    key = (edge.src, edge.dst, edge.prop)
                    if (self._prop_allowed(edge.prop, filters.props)
                            and key not in seen):
                        seen.add(key)
                        edges.append(edge)

        if filters.direction in ("both", "in") and self.sparql_inbound:
            for qid in qids:
                for edge in self._sparql_inbound(qid, filters.props):
                    key = (edge.src, edge.dst, edge.prop)
                    if key not in seen:
                        seen.add(key)
                        edges.append(edge)

        if len(edges) > limit:
            batch.typed_truncated = True
            edges = edges[:limit]
        batch.typed = edges
        return batch

    def get_edges_within(self, qids, filters=None, limit=None):
        """Closure pass: outbound claims of the member entities already cover
        every edge among them (an inbound edge is the other side's outbound),
        so no SPARQL round-trips are needed."""
        qids = list(qids)
        filters = filters or EdgeFilters()
        limit = limit or 5000
        batch = EdgeBatch()
        if not qids or "typed" not in filters.edge_kinds:
            return batch
        inside = set(qids)
        seen: set[tuple[str, str, str]] = set()
        edges: list[TypedEdge] = []
        for entity in self._entities_json(qids).values():
            for edge in extract_typed_edges(entity):
                key = (edge.src, edge.dst, edge.prop)
                if (edge.dst in inside
                        and self._prop_allowed(edge.prop, filters.props)
                        and key not in seen):
                    seen.add(key)
                    edges.append(edge)
        if len(edges) > limit:
            batch.typed_truncated = True
            edges = edges[:limit]
        batch.typed = edges
        return batch

    def _sparql_inbound(self, qid: str, props) -> list[TypedEdge]:
        """Inbound typed edges via SPARQL — bounded and optional (§2.3)."""
        if isinstance(props, (list, tuple)):
            prop_values = " ".join(f"wdt:{p}" for p in props)
        elif props == "cg":
            prop_values = " ".join(f"wdt:{p}" for p in CG_RELS)
        else:
            prop_values = None
        clause = f"VALUES ?prop {{ {prop_values} }}" if prop_values else ""
        query = f"""
        SELECT ?src ?prop WHERE {{
          {clause}
          ?src ?prop wd:{qid} .
          FILTER(STRSTARTS(STR(?prop), "http://www.wikidata.org/prop/direct/"))
        }} LIMIT {int(self.sparql_limit)}
        """
        try:
            result = self._request(SPARQL_BASE,
                                   {"query": query, "format": "json"})
        except BackendError:
            return []  # inbound edges are best-effort
        edges = []
        for binding in result.get("results", {}).get("bindings", []):
            src = binding["src"]["value"].rsplit("/", 1)[-1]
            prop = binding["prop"]["value"].rsplit("/", 1)[-1]
            if src.startswith("Q"):
                edges.append(TypedEdge(src=src, dst=qid, prop=prop))
        return edges

    def get_dates(self, qids: Iterable[str]) -> dict[str, list[DateClaim]]:
        entities = self._entities_json(qids)
        return {qid: extract_dates(entity) for qid, entity in entities.items()}

    def get_witnesses(self, pairs):
        raise UnsupportedOperation("API-only mode has no witness data (§2.3)")

    def search(self, text: str, limit: int = 10) -> list[SearchResult]:
        text = text.strip()
        if not text:
            return []
        result = self._api(action="wbsearchentities", search=text,
                           language="en", uselang="en", type="item",
                           limit=limit)
        return [SearchResult(qid=hit["id"], label=hit.get("label", hit["id"]),
                             description=hit.get("description", ""))
                for hit in result.get("search", [])]
