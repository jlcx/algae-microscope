# algae-microscope

Interactive explorer for neighborhoods of the ALGAE graph: multi-seed,
multi-hop expansion with a force-directed **graph view** and a
CauseGraph-like **temporal view** that lays entities out along a time axis
from Wikidata date claims. Read-only with respect to ALGAE; also runs in a
degraded **API-only mode** against live Wikidata with no local database.

See `SPEC.md` for the full design. Layout:

```
server/     Python: backend seam (Postgres | API-only), neighborhood
            expansion, witness math, FastAPI endpoints
web/        TypeScript SPA (no runtime deps): graph + temporal views
web/src/temporal/   separable temporal layout module (anchor policy,
                    precision-aware axis, lanes, constraint inference)
cli/        headless neighborhood → text / JSON / GraphML / DOT
contract/   ms_* SQL contract views (v1), mirrored from algae-farmer
tests/      pytest suite (fake backend, parsing, endpoints, exporters)
```

## Setup

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'          # or '.[postgres,server]' for a lean install
```

### Postgres mode

Apply the query contract to the ALGAE database once (creates read-only
`ms_*` views plus `ms_meta` with the contract version):

```sh
algae-microscope contract | psql -d algae
```

For interactive label search, the base table needs a supporting index
(optional — search fails fast with this hint when absent):

```sql
CREATE INDEX idx_wd_entities_label ON wd_entities (best_label text_pattern_ops);
```

### Configuration

Copy `config.example.toml` to `config.toml` (auto-loaded from the working
directory, `$ALGAE_MICROSCOPE_CONFIG`, or `--config`). Backend mode/DSN,
expansion defaults, witness clone families, temporal anchor priority, and
API-cache settings live there.

## CLI

```sh
algae-microscope Q42                                  # terminal view
algae-microscope Q42 Q5 --hops 2 --budget 50 --min-consensus 5
algae-microscope "Douglas Adams" --mode api           # no database needed
algae-microscope Q42 --format graphml -o q42.graphml  # Gephi export
algae-microscope Q42 --format json -o q42.json        # sheaf-tool input
```

Consensus edges print with raw and effective witness counts and a
`** WP-not-WD **` marker on pairs heavily linked across Wikipedias with no
Wikidata statement (the signature ALGAE signal).

## Server + web UI

```sh
(cd web && npm install && npm run build)   # once; server mounts web/dist
algae-microscope-server --mode postgres    # http://127.0.0.1:8321
```

For web development: `algae-microscope-server` in one shell,
`cd web && npm run dev` in another (Vite proxies `/api`).

API surface (§7): `GET /api/capabilities`, `GET /api/search?q=`,
`POST /api/neighborhood`, `POST /api/neighborhood/expand`,
`GET /api/entity/{qid}`, `GET /api/edge/{src}/{dst}`, plus
`GET /api/config` and `GET /api/witness_ops` for the UI.

## Tests

```sh
.venv/bin/pytest                 # Python: 43 tests, no network/database
cd web && npm test               # temporal module unit tests + typecheck
```

## Performance expectations (Postgres mode)

Hop-1 expansions answer in a couple of seconds. Hop-2+ through hub entities
(countries, years) currently costs minutes: ordering a hub's ~10⁶ consensus
edges by strength scans them all. The contract file lists composite
`(src, wp_count DESC)` / `(dst, wp_count DESC)` indexes that would fix this;
until then, keep hub-heavy expansions to `--props cg` and higher
`--min-consensus`, or expand single nodes interactively.

## Notes

- API-only mode shows **Wikidata structure and dates only** — no
  cross-language consensus or witnesses (computing those live is a
  non-goal). Entity JSON is cached in `~/.cache/algae-microscope` keyed by
  revision; requests are rate-limited with a proper User-Agent.
- Property constants (`cg_rels`, date property classes, inverses) are
  vendored from algae-farmer commit `f1833232` — see
  `server/constants.py` for the re-vendoring note.
- The serialized neighborhood JSON (`schema_version: 1`) is the interchange
  unit across the web UI, CLI export, sheaf tooling, and future CauseGraph
  ingestion.
