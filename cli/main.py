"""`algae-microscope` CLI: neighborhood → terminal / JSON / GraphML / DOT.

Examples:
    algae-microscope Q42
    algae-microscope Q42 Q5 --hops 2 --budget 50 --min-consensus 5
    algae-microscope "Douglas Adams" --mode api --format json -o out.json
    algae-microscope contract          # print the ms_* contract SQL
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from server.backends import BackendError, EdgeFilters, make_backend
from server.config import load_config
from server.neighborhood import WitnessWeights, expand

from .export import FORMATS

QID_RE = re.compile(r"^Q\d+$")


def _print_contract() -> int:
    path = Path(__file__).resolve().parents[1] / "contract" / "ms_views_v1.sql"
    sys.stdout.write(path.read_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "contract":
        return _print_contract()

    parser = argparse.ArgumentParser(
        prog="algae-microscope",
        description="Explore a neighborhood of the ALGAE graph",
        epilog=__doc__.split("Examples:")[1] if "Examples:" in (__doc__ or "")
        else None,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("seeds", nargs="+",
                        help="seed QIDs or free-text labels")
    parser.add_argument("--hops", type=int, default=None)
    parser.add_argument("--budget", type=int, default=None,
                        help="max new nodes retained per hop")
    parser.add_argument("--min-consensus", type=int, default=0,
                        help="minimum wp_count for consensus edges")
    parser.add_argument("--props", default="all",
                        help="'cg', 'all', or comma-separated property list")
    parser.add_argument("--edge-kinds", default="consensus,typed",
                        help="subset of consensus,typed")
    parser.add_argument("--direction", choices=["both", "out", "in"],
                        default="both")
    parser.add_argument("--format", choices=sorted(FORMATS), default="text")
    parser.add_argument("-o", "--output", default=None,
                        help="write to file instead of stdout")
    parser.add_argument("--config", default=None, help="path to config.toml")
    parser.add_argument("--mode", choices=["postgres", "api"], default=None,
                        help="override backend mode")
    parser.add_argument("--dsn", default=None, help="override postgres DSN")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.mode:
        config.backend.mode = args.mode
    if args.dsn:
        config.backend.dsn = args.dsn

    props: str | list[str] = args.props
    if props not in ("cg", "all"):
        props = [p.strip() for p in props.split(",") if p.strip()]
    filters = EdgeFilters(
        min_consensus=args.min_consensus,
        props=props,
        edge_kinds={k.strip() for k in args.edge_kinds.split(",") if k.strip()},
        direction=args.direction)

    try:
        backend = make_backend(config)
    except BackendError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        seeds = []
        for seed in args.seeds:
            if QID_RE.match(seed):
                seeds.append(seed)
            else:
                hits = backend.search(seed, limit=1)
                if not hits:
                    print(f"error: no entity found for {seed!r}",
                          file=sys.stderr)
                    return 1
                print(f"resolved {seed!r} -> {hits[0].qid} "
                      f"({hits[0].label})", file=sys.stderr)
                seeds.append(hits[0].qid)

        hops = args.hops if args.hops is not None else config.expansion.default_hops
        hops = min(hops, config.expansion.max_hops)
        budget = (args.budget if args.budget is not None
                  else config.expansion.default_budget)

        neighborhood = expand(
            backend, seeds, hops=hops, budget=budget, filters=filters,
            weights=WitnessWeights.from_config(config),
            edge_limit=config.expansion.edge_limit)
    except BackendError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        backend.close()

    rendered = FORMATS[args.format](neighborhood)
    if args.output:
        Path(args.output).write_text(rendered)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
