"""FastAPI application exposing the server API (SPEC.md §7).

The server is the only component that talks to data sources (§6.1); the web
app and any other client consume these endpoints. Expansion state is
client-held: /api/neighborhood returns the full serialized object, and
/api/neighborhood/expand takes the client's node list and returns a delta.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from ..backends import (Backend, BackendError, EdgeFilters,
                        UnsupportedOperation, make_backend)
from ..config import Config, load_config
from ..constants import CATEGORY_BY_PROP, CG_RELS
from ..neighborhood import WitnessWeights, expand, expand_delta, witness_set_ops

QID_RE = re.compile(r"^Q\d+$")


def _resolve_seeds(backend: Backend, seeds: list[str]) -> list[str]:
    """QIDs pass through; anything else is resolved via label search (§3.1)."""
    resolved = []
    for seed in seeds:
        seed = seed.strip()
        if QID_RE.match(seed):
            resolved.append(seed)
            continue
        hits = backend.search(seed, limit=1)
        if not hits:
            raise HTTPException(404, f"no entity found for seed {seed!r}")
        resolved.append(hits[0].qid)
    return list(dict.fromkeys(resolved))


def create_app(config: Config | None = None,
               backend: Backend | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="algae-microscope", version="0.1.0")
    weights = WitnessWeights.from_config(config)
    state = {"backend": backend}

    def get_backend() -> Backend:
        if state["backend"] is None:
            state["backend"] = make_backend(config)
        return state["backend"]

    @app.exception_handler(BackendError)
    async def backend_error(_request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled_error(request, exc):
        # Surface the real failure to the client instead of a bare
        # "Internal Server Error", and keep the traceback in the server log.
        import logging
        import traceback
        from fastapi.responses import JSONResponse
        logging.getLogger("algae-microscope").error(
            "unhandled error on %s %s\n%s", request.method, request.url.path,
            "".join(traceback.format_exception(exc)))
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/capabilities")
    def capabilities():
        return get_backend().capabilities().to_dict()

    @app.get("/api/config")
    def client_config():
        """Display/layout configuration the web client needs (§4.2, §5.2)."""
        return {
            "witnesses": {
                "clone_families": config.witnesses.clone_families,
                "family_cap": config.witnesses.family_cap,
                "weights": config.witnesses.weights,
            },
            "temporal": {
                "anchor_priority": config.temporal.anchor_priority,
                "undated": config.temporal.undated,
            },
            "expansion": {
                "default_hops": config.expansion.default_hops,
                "max_hops": config.expansion.max_hops,
                "default_budget": config.expansion.default_budget,
            },
            "cg_rels": CG_RELS,
            "prop_categories": CATEGORY_BY_PROP,
        }

    @app.get("/api/search")
    def search(q: str, limit: int = 10):
        return [{"qid": r.qid, "label": r.label, "description": r.description}
                for r in get_backend().search(q, limit=min(limit, 50))]

    @app.post("/api/neighborhood")
    def neighborhood(body: dict = Body(...)):
        seeds = body.get("seeds")
        if not seeds:
            raise HTTPException(422, "seeds is required")
        backend_obj = get_backend()
        resolved = _resolve_seeds(backend_obj, [str(s) for s in seeds])
        hops = min(int(body.get("hops", config.expansion.default_hops)),
                   config.expansion.max_hops)
        budget = int(body.get("budget", config.expansion.default_budget))
        filters = EdgeFilters.from_dict(body.get("filters"))
        result = expand(backend_obj, resolved, hops=hops, budget=budget,
                        filters=filters, weights=weights,
                        edge_limit=config.expansion.edge_limit)
        return result.to_dict()

    @app.post("/api/neighborhood/expand")
    def neighborhood_expand(body: dict = Body(...)):
        node = body.get("node")
        if not node:
            raise HTTPException(422, "node is required")
        state_qids = body.get("state") or []
        if isinstance(state_qids, dict):
            state_qids = state_qids.get("qids", [])
        budget = int(body.get("budget", config.expansion.default_budget))
        filters = EdgeFilters.from_dict(body.get("filters"))
        return expand_delta(get_backend(), state_qids, node, budget=budget,
                            filters=filters, weights=weights,
                            edge_limit=config.expansion.edge_limit)

    @app.get("/api/entity/{qid}")
    def entity(qid: str):
        if not QID_RE.match(qid):
            raise HTTPException(422, f"not a QID: {qid!r}")
        backend_obj = get_backend()
        info = backend_obj.get_entities([qid]).get(qid)
        dates = backend_obj.get_dates([qid]).get(qid, [])
        return {
            "qid": qid,
            "label": info.label if info else qid,
            "wp_count": info.wp_count if info else None,
            "dates": [d.to_dict() for d in dates],
        }

    @app.get("/api/edge/{src}/{dst}")
    def edge(src: str, dst: str):
        """Parallel edges + witnesses for a pair (§7), both directions."""
        backend_obj = get_backend()
        batch = backend_obj.get_edges([src, dst])
        pair = {(src, dst), (dst, src)}
        consensus = [
            {"src": e.src, "dst": e.dst, "wp_count": e.wp_count,
             "langs": e.langs, "wp_not_wd": e.wp_not_wd,
             "effective_count": (weights.effective_count(e.langs)
                                 if e.langs is not None else None)}
            for e in batch.consensus if (e.src, e.dst) in pair]
        typed = [{"src": e.src, "dst": e.dst, "prop": e.prop,
                  "prop_label": CG_RELS.get(e.prop)}
                 for e in batch.typed if (e.src, e.dst) in pair]
        result = {"consensus": consensus, "typed": typed}
        if len(consensus) == 2 and consensus[0]["langs"] is not None:
            result["witness_ops"] = witness_set_ops(
                consensus[0]["langs"], consensus[1]["langs"] or [])
        return result

    @app.get("/api/witness_ops")
    def witness_ops(a_src: str, a_dst: str, b_src: str, b_dst: str):
        """Shared/differing witnesses across a selected edge pair (§4.1)."""
        try:
            found = get_backend().get_witnesses(
                [(a_src, a_dst), (b_src, b_dst)])
        except UnsupportedOperation as e:
            raise HTTPException(501, str(e))
        a = found.get((a_src, a_dst), [])
        b = found.get((b_src, b_dst), [])
        return {"a": a, "b": b, **witness_set_ops(a, b)}

    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app
