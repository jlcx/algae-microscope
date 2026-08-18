"""Postgres backend (SPEC.md §2.2): reads the ms_* contract views only.

Neighborhood expansion is pushed into SQL (`= ANY(...)` frontier queries with
server-side ordering and limits). Checks ms_contract_version at startup and
refuses to run against an unknown version; degrades to wp_count-only mode when
the langs witness column is absent or null-typed (§1.2).
"""

from __future__ import annotations

from typing import Iterable

from .. import SUPPORTED_CONTRACT_VERSIONS
from ..constants import CG_RELS
from . import (Backend, BackendError, Capabilities, ConsensusEdge, DateClaim,
               EdgeBatch, EdgeFilters, EntityInfo, SearchResult, TypedEdge,
               UnsupportedOperation)

_WP_NOT_WD_SUBQUERY = """
NOT EXISTS (
    SELECT 1 FROM ms_wd_links w
    WHERE (w.src = l.src AND w.dst = l.dst)
       OR (w.src = l.dst AND w.dst = l.src)
)
"""


class PostgresBackend(Backend):
    def __init__(self, config):
        try:
            import psycopg
        except ImportError as e:
            raise BackendError(
                "postgres mode requires psycopg: pip install 'algae-microscope[postgres]'"
            ) from e
        self._psycopg = psycopg
        dsn = config.backend.dsn
        try:
            self._conn = psycopg.connect(dsn) if dsn else psycopg.connect()
        except psycopg.OperationalError as e:
            raise BackendError(
                f"cannot connect to Postgres (dsn={dsn or '<libpq defaults>'}): "
                f"{e}".strip()) from e
        self._conn.read_only = True
        # autocommit so reads don't accumulate in one never-ending transaction
        self._conn.autocommit = True
        self._contract_version = self._check_contract()
        self._has_witnesses = self._detect_witnesses()
        self._languages = self._load_languages() if self._has_witnesses else {}

    def _check_contract(self) -> str:
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT ms_contract_version FROM ms_meta")
                version = cur.fetchone()[0]
        except self._psycopg.errors.UndefinedTable as e:
            raise BackendError(
                "database has no ms_meta view — apply the query contract first "
                "(contract/ms_views_v1.sql, or `algae-microscope contract`)"
            ) from e
        if int(version) not in SUPPORTED_CONTRACT_VERSIONS:
            raise BackendError(
                f"unsupported ms_contract_version {version}; this build supports "
                f"{sorted(SUPPORTED_CONTRACT_VERSIONS)}"
            )
        return str(version)

    def _detect_witnesses(self) -> bool:
        """True when ms_wp_links.langs exists and is a real array column
        (a pre-migration database exposes it as NULL, §1.2)."""
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'ms_wp_links' AND column_name = 'langs'
            """)
            row = cur.fetchone()
            if row is None:
                return False
            if row[0] != 'ARRAY':
                return False
            cur.execute("SELECT langs FROM ms_wp_links LIMIT 1")
            sample = cur.fetchone()
            return sample is None or sample[0] is not None

    def _load_languages(self) -> dict[int, str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT lang_id, lang_code FROM ms_languages")
            return {lang_id: code for lang_id, code in cur.fetchall()}

    def capabilities(self) -> Capabilities:
        return Capabilities(
            witnesses=self._has_witnesses,
            consensus=True,
            dates=True,
            bulk=True,
            contract_version=self._contract_version,
        )

    def _decode(self, langs: list[int] | None) -> list[str] | None:
        if langs is None:
            return None
        return [self._languages.get(i, f"#{i}") for i in langs]

    def get_entities(self, qids: Iterable[str]) -> dict[str, EntityInfo]:
        qids = list(qids)
        if not qids:
            return {}
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT qid, best_label, wp_count FROM ms_entities WHERE qid = ANY(%s)",
                (qids,))
            found = {qid: EntityInfo(qid=qid, label=label or qid, wp_count=wp)
                     for qid, label, wp in cur.fetchall()}
        for qid in qids:
            if qid not in found:
                found[qid] = EntityInfo(qid=qid, label=qid, wp_count=None)
        return found

    @staticmethod
    def _direction_clause(direction: str, column_src: str = "src",
                          column_dst: str = "dst") -> str:
        if direction == "out":
            return f"{column_src} = ANY(%(qids)s)"
        if direction == "in":
            return f"{column_dst} = ANY(%(qids)s)"
        return f"({column_src} = ANY(%(qids)s) OR {column_dst} = ANY(%(qids)s))"

    def get_edges(self, qids: Iterable[str],
                  filters: EdgeFilters | None = None,
                  limit: int | None = None) -> EdgeBatch:
        qids = list(qids)
        filters = filters or EdgeFilters()
        batch = EdgeBatch()
        if not qids:
            return batch
        limit = limit or 5000
        params: dict = {"qids": qids, "limit": limit + 1,
                        "min_consensus": filters.min_consensus}

        if "consensus" in filters.edge_kinds:
            langs_col = "l.langs" if self._has_witnesses else "NULL"
            sql = f"""
                SELECT l.src, l.dst, {langs_col}, l.wp_count,
                       {_WP_NOT_WD_SUBQUERY} AS wp_not_wd
                FROM ms_wp_links l
                WHERE {self._direction_clause(filters.direction, 'l.src', 'l.dst')}
                  AND l.wp_count >= %(min_consensus)s
                ORDER BY l.wp_count DESC
                LIMIT %(limit)s
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            if len(rows) > limit:
                batch.consensus_truncated = True
                rows = rows[:limit]
            batch.consensus = [
                ConsensusEdge(src=s, dst=d, langs=self._decode(langs),
                              wp_count=wp, wp_not_wd=flag)
                for s, d, langs, wp, flag in rows]

        if "typed" in filters.edge_kinds:
            prop_clause = ""
            if filters.props == "cg":
                params["props"] = list(CG_RELS)
                prop_clause = "AND prop = ANY(%(props)s)"
            elif isinstance(filters.props, (list, tuple)):
                params["props"] = list(filters.props)
                prop_clause = "AND prop = ANY(%(props)s)"
            sql = f"""
                SELECT src, dst, prop FROM ms_wd_links
                WHERE {self._direction_clause(filters.direction)}
                  {prop_clause}
                LIMIT %(limit)s
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            if len(rows) > limit:
                batch.typed_truncated = True
                rows = rows[:limit]
            batch.typed = [TypedEdge(src=s, dst=d, prop=p) for s, d, p in rows]

        return batch

    def get_edges_within(self, qids: Iterable[str],
                         filters: EdgeFilters | None = None,
                         limit: int | None = None) -> EdgeBatch:
        """Closure-pass edges: both endpoints known, so probe the (src, dst)
        primary keys per pair instead of scanning every edge touching the
        frontier — hub nodes make the touching-scan take minutes."""
        qids = list(qids)
        filters = filters or EdgeFilters()
        batch = EdgeBatch()
        if not qids:
            return batch
        limit = limit or 5000
        params: dict = {"qids": qids, "limit": limit + 1,
                        "min_consensus": filters.min_consensus}
        pair_clause = """(l.src, l.dst) IN (
            SELECT a.qid, b.qid FROM unnest(%(qids)s::text[]) a(qid)
            CROSS JOIN unnest(%(qids)s::text[]) b(qid))"""

        if "consensus" in filters.edge_kinds:
            langs_col = "l.langs" if self._has_witnesses else "NULL"
            sql = f"""
                SELECT l.src, l.dst, {langs_col}, l.wp_count,
                       {_WP_NOT_WD_SUBQUERY} AS wp_not_wd
                FROM ms_wp_links l
                WHERE {pair_clause}
                  AND l.wp_count >= %(min_consensus)s
                ORDER BY l.wp_count DESC
                LIMIT %(limit)s
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            if len(rows) > limit:
                batch.consensus_truncated = True
                rows = rows[:limit]
            batch.consensus = [
                ConsensusEdge(src=s, dst=d, langs=self._decode(langs),
                              wp_count=wp, wp_not_wd=flag)
                for s, d, langs, wp, flag in rows]

        if "typed" in filters.edge_kinds:
            prop_clause = ""
            if filters.props == "cg":
                params["props"] = list(CG_RELS)
                prop_clause = "AND l.prop = ANY(%(props)s)"
            elif isinstance(filters.props, (list, tuple)):
                params["props"] = list(filters.props)
                prop_clause = "AND l.prop = ANY(%(props)s)"
            sql = f"""
                SELECT l.src, l.dst, l.prop FROM ms_wd_links l
                WHERE {pair_clause}
                  {prop_clause}
                LIMIT %(limit)s
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            if len(rows) > limit:
                batch.typed_truncated = True
                rows = rows[:limit]
            batch.typed = [TypedEdge(src=s, dst=d, prop=p) for s, d, p in rows]

        return batch

    def get_dates(self, qids: Iterable[str]) -> dict[str, list[DateClaim]]:
        qids = list(qids)
        if not qids:
            return {}
        result: dict[str, list[DateClaim]] = {}
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT qid, property, time_value, precision,
                       source_property, source_target
                FROM ms_dates WHERE qid = ANY(%s)
            """, (qids,))
            for qid, prop, tv, prec, sp, st in cur.fetchall():
                result.setdefault(qid, []).append(DateClaim(
                    property=prop, time_value=tv, precision=prec,
                    source_property=sp or "", source_target=st or ""))
        return result

    def get_witnesses(self, pairs: Iterable[tuple[str, str]]
                      ) -> dict[tuple[str, str], list[str]]:
        if not self._has_witnesses:
            raise UnsupportedOperation("backend has no witness arrays")
        pairs = list(pairs)
        if not pairs:
            return {}
        srcs = [p[0] for p in pairs]
        dsts = [p[1] for p in pairs]
        wanted = set(pairs)
        result: dict[tuple[str, str], list[str]] = {}
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT src, dst, langs FROM ms_wp_links
                WHERE src = ANY(%s) AND dst = ANY(%s)
            """, (srcs, dsts))
            for src, dst, langs in cur.fetchall():
                if (src, dst) in wanted:
                    result[(src, dst)] = self._decode(langs) or []
        return result

    # Label prefix search needs a supporting index on the base table (owned
    # by algae-farmer, see contract/ms_views_v1.sql); without it the query
    # would seq-scan ~10^8 rows, so it is capped and fails fast with a hint.
    SEARCH_TIMEOUT_MS = 5000
    SEARCH_INDEX_HINT = (
        "label search timed out — the database is missing the supporting "
        "index; create it with: CREATE INDEX idx_wd_entities_label ON "
        "wd_entities (best_label text_pattern_ops)")

    def search(self, text: str, limit: int = 10) -> list[SearchResult]:
        text = text.strip()
        if not text:
            return []
        try:
            with self._conn.transaction(), self._conn.cursor() as cur:
                cur.execute(
                    f"SET LOCAL statement_timeout = {int(self.SEARCH_TIMEOUT_MS)}")
                # Case-sensitive prefix match (LIKE can use the
                # text_pattern_ops index, ILIKE cannot); exact match first,
                # ties broken toward well-covered entities.
                cur.execute(r"""
                    SELECT qid, best_label, wp_count,
                           (best_label = %(t)s) AS exact
                    FROM ms_entities
                    WHERE best_label LIKE %(prefix)s
                    ORDER BY exact DESC, wp_count DESC NULLS LAST
                    LIMIT %(limit)s
                """, {"t": text,
                      "prefix": text.replace('\\', r'\\').replace('%', r'\%')
                                    .replace('_', r'\_') + '%',
                      "limit": limit})
                rows = cur.fetchall()
        except self._psycopg.errors.QueryCanceled as e:
            raise BackendError(self.SEARCH_INDEX_HINT) from e
        return [SearchResult(qid=qid, label=label,
                             description=f"wp_count={wp}")
                for qid, label, wp, _exact in rows]

    def close(self) -> None:
        self._conn.close()
