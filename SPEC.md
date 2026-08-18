# algae-microscope Specification

**algae-microscope** is an interactive tool for exploring and visualizing neighborhoods of the ALGAE graph. It generalizes the original `microscope` script (a single-QID, single-hop, terminal-output Python utility in algae-farmer) into a standalone application with multi-seed, multi-hop neighborhood expansion, a graph view, and a temporal ("CauseGraph-like") view that lays entities out along a time axis using Wikidata date claims.

The tool is read-only with respect to ALGAE. It lives in its own repository and consumes ALGAE data through a small, versioned query contract. It can also run in a degraded **API-only mode** against the live Wikidata/Wikipedia APIs, with no local database, for use by people without an ALGAE installation.

This spec covers the data-access contract, neighborhood model, view semantics, architecture, and API.

---

## 1. Relationship to algae-farmer

### 1.1 Separation of concerns

| Concern | Owner |
|---|---|
| Dump processing, aggregation, DB schema, loading | algae-farmer |
| Read-only query views consumed by microscope | algae-farmer (versioned with the schema they read) |
| Neighborhood expansion, layout, rendering, API-only fallback | algae-microscope |
| Temporal layout module | algae-microscope initially; designed for later extraction/reuse by CauseGraph |

### 1.2 Query contract

algae-farmer exposes a set of SQL views (or equivalently, microscope ships a query module pinned to a schema version) constituting the entire surface microscope reads. Target surface:

```sql
-- Consensus edges with per-language witness provenance
CREATE VIEW ms_wp_links AS
SELECT src, dst, langs, wp_count       -- langs int2[]; wp_count generated from langs
FROM wp_links;

-- Typed Wikidata edges
CREATE VIEW ms_wd_links AS
SELECT src, dst, prop FROM wd_links;

-- Entity labels and coverage
CREATE VIEW ms_entities AS
SELECT qid, best_label, wp_count FROM wd_entities;

-- Date claims (top-level and nested), for temporal layout
CREATE VIEW ms_dates AS
SELECT qid, property, time_value, precision, source_property, source_target
FROM wd_dates;

-- Language dimension (append-only registry backing the int2[] witness arrays)
CREATE VIEW ms_languages AS
SELECT lang_id, lang_code FROM languages;
```

**Schema version pinning.** The contract carries a version number (`ms_contract_version`, stored in a one-row metadata view). microscope checks it at startup and refuses to run against an unknown version rather than silently misreading witness arrays.

**Witness-first design constraint.** microscope is designed against the per-language witness array (`langs int2[]` + `languages` dimension table), not the lossy `wp_count INT` column. If it connects to a pre-migration database where `langs` is absent, it degrades: witness-dependent features (§4.2, §5.1 edge encodings) are disabled and `wp_count` is used as an opaque scalar. This is a compatibility shim, not a design target.

---

## 2. Data Backends

All data access goes through a single backend interface so that Postgres and API-only modes are interchangeable from the application's point of view. This is the same seam pattern used in `alignment_sheaf.py`.

### 2.1 Backend interface

```
get_entities(qids)            -> {qid: {label, wp_count?, ...}}
get_edges(qids, direction)    -> consensus edges + typed edges touching any qid
get_dates(qids)               -> date claims per qid
get_witnesses(edges)          -> per-edge language witness sets (may be unsupported)
capabilities()                -> {witnesses: bool, consensus: bool, dates: bool,
                                  bulk: bool, contract_version: str|None}
```

Backends declare capabilities; the UI adapts rather than erroring (e.g., no witness legend in API-only mode).

### 2.2 Postgres backend

Connects to an ALGAE database via the §1.2 contract views. Full capability set. Neighborhood expansion is pushed into SQL (`WHERE src = ANY($1) OR dst = ANY($1)`) with server-side limits and ordering, so multi-hop expansion is a sequence of bounded frontier queries rather than client-side filtering.

### 2.3 API-only backend

Runs against live public APIs with no local data:

| Data | Source |
|---|---|
| Entity JSON, labels, sitelinks | Wikidata `wbgetentities` |
| Typed edges (claims) | Same entity JSON — `wikibase-item` mainsnaks, mirroring `wd_preproc` §2.2 extraction rules |
| Date claims | Same entity JSON — properties in `all_times`, incl. nested qualifiers in `times_plus_nested` |
| Inbound typed edges | Wikidata SPARQL (`?x ?p <qid>`), bounded and optional |

**What API-only mode does not have:** cross-language link consensus and witness arrays. Computing even a shallow approximation live (fetching and parsing article wikitext across languages) is explicitly out of scope for the initial version — the cost is high and the result would be a misleadingly sparse imitation of the pipeline's output. API-only mode therefore shows **Wikidata structure and dates only**, clearly labeled as such. The `consensus` and `witnesses` capabilities are false.

Rate limiting, caching (on-disk response cache keyed by entity revision), and a proper User-Agent are required; the backend must be usable without hammering the APIs during interactive exploration.

### 2.4 Constants sharing

`cg_rels`, `all_times`, `times_plus_nested`, `combined_inverses`, and `likely_nonspecific` are needed by both repos (algae-farmer at extraction time, microscope at display/layout time). Initial approach: vendor a copy in microscope with a provenance header naming the algae-farmer commit it was copied from. If drift becomes a problem, promote to a tiny shared package; don't build that infrastructure preemptively.

---

## 3. Neighborhood Model

### 3.1 Seeds

A neighborhood is defined by one or more **seed entities** (QIDs). Multiple seeds support the primary comparative use cases: examining the region between two entities, or the union of several related entities' surroundings.

Seed input accepts QIDs directly, or free-text resolved to QIDs via label search (Postgres: `ms_entities` lookup; API-only: `wbsearchentities`).

### 3.2 Expansion

Expansion proceeds in **hops** from the seed frontier:

- `hops` (default 1, max configurable, suggested ceiling 3): number of expansion rounds.
- Each round fetches all edges touching the current frontier, adds newly seen entities to the graph, and forms the next frontier from them.
- **Per-hop budget:** each round retains at most `budget` new nodes (default 100), ranked by a scoring function, to keep hop-2+ expansions from exploding on hub entities.

**Ranking for budget cuts.** Default score for a candidate node is the maximum consensus strength of any edge connecting it to the existing graph — using the effective language count (§4.2) when witnesses are available, raw `wp_count` otherwise, and a fixed low score for nodes reachable only via typed WD edges. The scoring function is pluggable.

### 3.3 Edge filters

Filters applied at fetch time (pushed into SQL where possible):

- `min_consensus`: minimum wp_count / effective count for consensus edges.
- `props`: restrict typed edges to a property set. Named presets: `cg` (the `cg_rels` causal-graph set), `all`, or an explicit list.
- `edge_kinds`: any subset of `{consensus, typed}`.
- `direction`: `both` (default), `out`, `in`.

### 3.4 Graph merging

Consensus edges and typed edges between the same (src, dst) pair are kept as **distinct parallel edges**, not merged. The WP-not-WD condition — a consensus edge with no typed edge in either direction between the pair — is computed as a derived per-edge flag (`wp_not_wd: bool`) so the signature ALGAE query result is directly visible in the neighborhood view. The bidirectional check follows `queries/wp_not_wd.sql` semantics.

---

## 4. Witness Semantics

### 4.1 Witness display

When the backend supports witnesses, each consensus edge carries its language set. The UI exposes:

- Edge tooltip/panel listing witnessing editions (decoded via `ms_languages`).
- Filtering by witness language ("show only edges witnessed by `de`").
- Set operations across a selected edge pair (shared witnesses, symmetric difference) — useful when inspecting why two related consensus edges have different strengths.

### 4.2 Effective language count and clone families

Raw witness counts overweight bot-generated edition clusters (the Lsjbot cluster: `ceb`, `war`, `sv`, `vi`). microscope ships a **clone-family configuration**: a list of language groups, each contributing at most a configurable maximum (default 1) to the **effective count** of an edge.

- Effective count = |witnesses outside any family| + Σ over families min(|witnesses ∩ family|, cap).
- The default family list is a static config file with the Lsjbot cluster; it is expected to be replaced or augmented by endogenous weighting output from ALGAE's edition-weighting work when that lands. The config format should anticipate per-language scalar weights as a generalization (family caps are a special case).
- UI toggle between raw and effective counts; edge visual encoding (§5.1) uses effective count by default.

---

## 5. Views

### 5.1 Graph view

Standard node-link rendering with force-directed layout.

- **Nodes:** labeled with `best_label`; seed nodes visually distinguished; size optionally by degree or entity `wp_count`.
- **Consensus edges:** thickness/opacity by effective language count; `wp_not_wd` edges highlighted distinctly (this is the discovery signal).
- **Typed edges:** rendered directionally with property labels on hover; property-class coloring (causation, kinship, creation, succession, …) using the `cg_rels` category groupings.
- **Interactions:** click-to-expand (one more hop from a single node), node pinning, collapse/hide, edge-panel inspection, witness filtering.

### 5.2 Temporal view (CauseGraph-like)

Nodes are positioned along a horizontal time axis; the vertical dimension is layout-assigned to minimize edge crossings among concurrent entities. This view is the seed of CauseGraph rendering and should be built as a **separable module** (data-in, layout-out, no microscope-specific dependencies).

#### 5.2.1 Anchor date selection

Each entity may have many date claims. A **date policy** selects the anchor date used for positioning:

1. Prefer properties in `starts` (P571 inception, P569 birth, P580 start time, P577 publication, …) in a configurable priority order.
2. Else properties in `others` (P585 point in time, P1317 floruit).
3. Else properties in `ends` (positioning at the end date, visually flagged as end-anchored).
4. Else the entity is **undated**.

Nested date claims (non-null `source_property`) are never used as the entity's own anchor — they date a relationship, not the entity — but see §5.2.4.

Multiple values for the same property (e.g., conflicting P571 claims) are resolved by taking the highest-precision value; ties surface a warning marker on the node.

#### 5.2.2 Precision rendering

Wikidata precision runs from 0 (billions of years) to 14 (seconds). The time value alone is meaningless without its precision, and neighborhoods routinely mix precision-9 (year) people with precision-6 (millennium) archaeological entities.

- Each dated node renders as a **point plus an uncertainty extent**: the interval implied by its precision (a precision-7 "century" value spans the century). At most zoom levels most extents collapse to points; they become visible as the user zooms toward the node's native precision.
- The axis is zoomable across scales; tick generation is precision-aware (labels in Ga/Ma/ka for deep time, years/months/days elsewhere). Julian/Gregorian calendar-model handling follows the time value's `calendarmodel` where it matters (pre-1583 dates).
- Entities whose anchor precision is coarser than the current viewport span are rendered as spanning bands rather than points, so a "20th century" entity doesn't get a false-precision position among dated-to-the-day events.

#### 5.2.3 Undated nodes

Undated entities are common and must not vanish. Strategies, user-selectable:

- **Margin placement** (default): undated nodes in a docked side region, with edges into the timeline rendered in a muted style.
- **Constraint inference** (optional, later): infer a feasible interval from dated neighbors via directed edges whose properties imply temporal order (succession properties P155/P156, P1365/P1366; causation properties; `starts`/`ends` of related entities). Rendered as a wide band with an "inferred" marker. This is a bounded-effort feature — full temporal constraint propagation is CauseGraph territory.

Statements with properties in `likely_nonspecific` and no date are treated as generic claims and excluded from constraint inference.

#### 5.2.4 Secondary date events

Beyond the anchor, an entity's other date claims can be displayed as **event ticks** along its timeline row: end dates (rendering the entity as a lifespan bar when both start and end anchor exist), nested date qualifiers (e.g., P580 on P108 "employer" → tick labeled with the parent property and target), and additional dated claims. Toggleable per property class; default shows start+end (lifespan bars) only.

### 5.3 View continuity

Graph view and temporal view are two projections of one neighborhood state. Switching views preserves selection, filters, expansion state, and pinned nodes. Node identity persists (shared element keys) so the transition can animate, which materially helps users keep orientation.

---

## 6. Architecture

### 6.1 Components

```
algae-microscope/
├── server/            # Python (FastAPI): backend interface, Postgres + API-only impls,
│   │                  #   neighborhood expansion, caching
│   ├── backends/
│   ├── neighborhood/  # expansion, ranking, wp_not_wd derivation, effective counts
│   └── api/           # REST endpoints (§7)
├── web/               # TypeScript SPA: graph + temporal views, controls
│   └── temporal/      # separable temporal layout module (§5.2)
├── cli/               # headless queries: neighborhood → JSON/GraphML/DOT export
└── contract/          # SQL contract views + version, mirrored from algae-farmer
```

- **Server** is the only component that talks to data sources; the web app talks only to the server. This keeps API-only rate limiting, caching, and credentials in one place, and lets the CLI reuse everything.
- **CLI mode** covers the original microscope use case (quick terminal inspection of a QID's neighborhood) plus export for external tools (Gephi, `alignment_sheaf.py` input).

### 6.2 Neighborhood as a serializable object

The expanded neighborhood (nodes, parallel edges, witness data, dates, flags, expansion provenance) has a defined JSON schema and is the unit of: server→web transfer, CLI export, and permalink state. This schema is the natural input format for downstream sheaf analysis and future CauseGraph ingestion, so it is versioned and documented.

### 6.3 Caching

- Postgres backend: no extra caching initially (the DB is local and fast).
- API-only backend: mandatory on-disk cache of entity JSON keyed by (qid, revision), with a TTL-based revision check. Interactive re-expansion must not re-fetch unchanged entities.

---

## 7. Server API

```
GET  /api/capabilities
GET  /api/search?q=...                      # label → QID resolution
POST /api/neighborhood                      # {seeds, hops, budget, filters} → neighborhood JSON
POST /api/neighborhood/expand               # {neighborhood_id|state, node, hops:1} → delta
GET  /api/entity/{qid}                      # entity detail incl. all date claims
GET  /api/edge/{src}/{dst}                  # parallel edges + witnesses for a pair
```

Neighborhood responses include the full serialized object (§6.2); `expand` returns a delta against a client-held state to keep interactive expansion cheap.

---

## 8. Configuration

```toml
[backend]
mode = "postgres"            # or "api"
dsn  = "postgresql://..."    # postgres mode

[expansion]
default_hops = 1
max_hops = 3
default_budget = 100

[witnesses]
clone_families = [["ceb", "war", "sv", "vi"]]
family_cap = 1

[temporal]
anchor_priority = ["P571", "P569", "P580", "P577"]   # prepended to starts default order
undated = "margin"           # or "infer"

[api_backend]
cache_dir = "~/.cache/algae-microscope"
user_agent = "algae-microscope/0.1 (contact)"
```

---

## 9. Non-Goals (initial version)

1. **Live consensus computation in API-only mode** — see §2.3.
2. **Sheaf computation in the UI.** H⁰/H¹, Laplacian diagnostics, and obstruction-derived branch points stay in `alignment_sheaf.py` / CauseGraph. microscope's job is to export neighborhoods in a shape those tools can consume; rendering *precomputed* obstruction annotations on edges is a plausible later feature and the edge schema should tolerate an extensible annotation map.
3. **Editing.** No writes to ALGAE, no Wikidata edit submission. Surfacing `wp_not_wd` candidates for human review is in scope; pushing statements to Wikidata is not.
4. **Full temporal constraint solving** for undated nodes (§5.2.3's inference is bounded single-pass, not a solver).
5. **Multiverse branching visualization.** The temporal layout module should not preclude it (its data model keeps per-node event lists rather than a single scalar position), but branch rendering is CauseGraph's problem.

---

## 10. Key Design Decisions

1. **Separate repository.** Different stack and release cadence from algae-farmer; the API-only mode makes it independently useful; the temporal layout module is the first real CauseGraph rendering code and shouldn't be buried in a pipeline repo.
2. **Versioned read-only contract** instead of direct table access, so the ALGAE schema (currently mid-migration) can evolve behind stable views.
3. **Witness arrays as the design target**, `wp_count` as a degraded compatibility mode — inverting this would bake the lossy representation into a new codebase during the exact migration meant to eliminate it.
4. **Effective counts over raw counts** as the default visual encoding, with clone families as explicit, replaceable configuration anticipating endogenous edition weights.
5. **Honest API-only degradation.** Rather than approximating consensus badly, API-only mode shows only what it truly has, with capabilities-driven UI adaptation.
6. **Temporal layout as a separable module** with precision-aware rendering as a first-class requirement, since anchor selection + precision + undated handling is the hard problem and its solution is reusable by CauseGraph.
7. **Serializable neighborhood objects** as the universal interchange unit across web UI, CLI export, sheaf tooling, and eventual CauseGraph ingestion.
