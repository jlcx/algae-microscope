"""Postgres backend (SPEC.md §2.2): reads the ms_* contract views only.

Neighborhood expansion is pushed into SQL (`= ANY(...)` frontier queries with
server-side ordering and limits). Checks ms_contract_version at startup and
refuses to run against an unknown version; degrades to wp_count-only mode when
the langs witness column is absent or null-typed (§1.2).

Connections come from a small lazy pool and every backend call runs on its
own connection: psycopg serializes commands on a shared connection but not
transaction state, so one request's aborted transaction (e.g. a timed-out
label search) would poison every concurrent request with
InFailedSqlTransaction.
"""

from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
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
    MAX_CONNECTIONS = 8

    # Label prefix search needs a supporting index on the base table (owned
    # by algae-farmer, see contract/ms_views_v1.sql); without it the query
    # would seq-scan ~10^8 rows, so it is capped and fails fast with a hint.
    SEARCH_TIMEOUT_MS = 5000
    SEARCH_INDEX_HINT = (
        "label search timed out — the database is missing the supporting "
        "index; create it with: CREATE INDEX idx_wd_entities_label_lower ON "
        "wd_entities (lower(best_label) text_pattern_ops)")

    def __init__(self, config):
        try:
            import psycopg
        except ImportError as e:
            raise BackendError(
                "postgres mode requires psycopg: pip install 'algae-microscope[postgres]'"
            ) from e
        self._psycopg = psycopg
        self._dsn = config.backend.dsn
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._pool_lock = threading.Lock()
        self._live = 0
        conn = self._connect()
        try:
            self._contract_version = self._check_contract(conn)
            self._has_witnesses = self._detect_witnesses(conn)
            self._languages = (self._load_languages(conn)
                               if self._has_witnesses else {})
        finally:
            self._release(conn)

    # --- connection pool ---

    def _connect(self):
        try:
            conn = (self._psycopg.connect(self._dsn) if self._dsn
                    else self._psycopg.connect())
        except self._psycopg.OperationalError as e:
            raise BackendError(
                f"cannot connect to Postgres "
                f"(dsn={self._dsn or '<libpq defaults>'}): {e}".strip()) from e
        conn.read_only = True
        # autocommit so plain reads never accumulate transaction state
        conn.autocommit = True
        with self._pool_lock:
            self._live += 1
        return conn

    def _acquire(self):
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            pass
        with self._pool_lock:
            below_cap = self._live < self.MAX_CONNECTIONS
        if below_cap:
            return self._connect()
        return self._pool.get()  # wait for a free connection

    def _release(self, conn) -> None:
        if conn.closed:
            with self._pool_lock:
                self._live -= 1
        else:
            self._pool.put(conn)

    @contextmanager
    def _connection(self):
        conn = self._acquire()
        try:
            yield conn
        except Exception:
            # never return a connection with a failed transaction
            try:
                if not conn.closed:
                    conn.rollback()
            except Exception:
                conn.close()
            raise
        finally:
            self._release(conn)

    def close(self) -> None:
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            conn.close()
            with self._pool_lock:
                self._live -= 1

    # --- startup checks ---

    def _check_contract(self, conn) -> str:
        try:
            with conn.cursor() as cur:
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

    def _detect_witnesses(self, conn) -> bool:
        """True when ms_wp_links.langs exists and is a real array column
        (a pre-migration database exposes it as NULL, §1.2)."""
        with conn.cursor() as cur:
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

    def _load_languages(self, conn) -> dict[int, str]:
        with conn.cursor() as cur:
            cur.execute("SELECT lang_id, lang_code FROM ms_languages")
            return {lang_id: code for lang_id, code in cur.fetchall()}

    # --- Backend interface ---

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
        with self._connection() as conn, conn.cursor() as cur:
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

    @staticmethod
    def _prop_clause(filters: EdgeFilters, params: dict,
                     column: str = "prop") -> str:
        if filters.props == "cg":
            params["props"] = list(CG_RELS)
            return f"AND {column} = ANY(%(props)s)"
        if isinstance(filters.props, (list, tuple)):
            params["props"] = list(filters.props)
            return f"AND {column} = ANY(%(props)s)"
        return ""

    def _fetch_consensus(self, conn, where: str, params: dict,
                         limit: int, batch: EdgeBatch) -> None:
        langs_col = "l.langs" if self._has_witnesses else "NULL"
        sql = f"""
            SELECT l.src, l.dst, {langs_col}, l.wp_count,
                   {_WP_NOT_WD_SUBQUERY} AS wp_not_wd
            FROM ms_wp_links l
            WHERE {where}
              AND l.wp_count >= %(min_consensus)s
            ORDER BY l.wp_count DESC
            LIMIT %(limit)s
        """
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        if len(rows) > limit:
            batch.consensus_truncated = True
            rows = rows[:limit]
        batch.consensus = [
            ConsensusEdge(src=s, dst=d, langs=self._decode(langs),
                          wp_count=wp, wp_not_wd=flag)
            for s, d, langs, wp, flag in rows]

    def _fetch_typed(self, conn, where: str, prop_clause: str, params: dict,
                     limit: int, batch: EdgeBatch) -> None:
        sql = f"""
            SELECT l.src, l.dst, l.prop FROM ms_wd_links l
            WHERE {where}
              {prop_clause}
            LIMIT %(limit)s
        """
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        if len(rows) > limit:
            batch.typed_truncated = True
            rows = rows[:limit]
        batch.typed = [TypedEdge(src=s, dst=d, prop=p) for s, d, p in rows]

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
        with self._connection() as conn:
            if "consensus" in filters.edge_kinds:
                self._fetch_consensus(
                    conn, self._direction_clause(filters.direction, 'l.src', 'l.dst'),
                    params, limit, batch)
            if "typed" in filters.edge_kinds:
                self._fetch_typed(
                    conn, self._direction_clause(filters.direction, 'l.src', 'l.dst'),
                    self._prop_clause(filters, params, 'l.prop'),
                    params, limit, batch)
        return batch

    # Closure-pass edges: both endpoints known, so probe the (src, dst)
    # primary keys per pair instead of scanning every edge touching the
    # frontier — hub nodes make the touching-scan take minutes.
    _PAIR_CLAUSE = """(l.src, l.dst) IN (
        SELECT a.qid, b.qid FROM unnest(%(qids)s::text[]) a(qid)
        CROSS JOIN unnest(%(qids)s::text[]) b(qid))"""

    def get_edges_within(self, qids: Iterable[str],
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
        with self._connection() as conn:
            if "consensus" in filters.edge_kinds:
                self._fetch_consensus(conn, self._PAIR_CLAUSE, params, limit,
                                      batch)
            if "typed" in filters.edge_kinds:
                self._fetch_typed(conn, self._PAIR_CLAUSE,
                                  self._prop_clause(filters, params, 'l.prop'),
                                  params, limit, batch)
        return batch

    def get_dates(self, qids: Iterable[str]) -> dict[str, list[DateClaim]]:
        qids = list(qids)
        if not qids:
            return {}
        result: dict[str, list[DateClaim]] = {}
        with self._connection() as conn, conn.cursor() as cur:
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
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT src, dst, langs FROM ms_wp_links
                WHERE src = ANY(%s) AND dst = ANY(%s)
            """, (srcs, dsts))
            for src, dst, langs in cur.fetchall():
                if (src, dst) in wanted:
                    result[(src, dst)] = self._decode(langs) or []
        return result

    def search(self, text: str, limit: int = 10) -> list[SearchResult]:
        text = text.strip()
        if not text:
            return []
        try:
            with self._connection() as conn, conn.transaction(), \
                    conn.cursor() as cur:
                cur.execute(
                    f"SET LOCAL statement_timeout = {int(self.SEARCH_TIMEOUT_MS)}")
                # Case-insensitive prefix match served by the
                # lower(best_label) text_pattern_ops index (LIKE on the
                # indexed expression; ILIKE could not use it); exact match
                # first, ties broken toward well-covered entities.
                cur.execute(r"""
                    SELECT qid, best_label, wp_count,
                           (lower(best_label) = lower(%(t)s)) AS exact
                    FROM ms_entities
                    WHERE lower(best_label) LIKE lower(%(prefix)s)
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
                             description=f"{wp or 0} Wikipedia editions")
                for qid, label, wp, _exact in rows]
