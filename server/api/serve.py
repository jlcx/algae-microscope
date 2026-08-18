"""`algae-microscope-server` entry point."""

from __future__ import annotations

import argparse

from ..config import load_config
from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the algae-microscope server")
    parser.add_argument("--config", default=None, help="path to config.toml")
    parser.add_argument("--mode", choices=["postgres", "api"], default=None,
                        help="override backend mode")
    parser.add_argument("--dsn", default=None, help="override postgres DSN")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8321)
    args = parser.parse_args()

    config = load_config(args.config)
    if args.mode:
        config.backend.mode = args.mode
    if args.dsn:
        config.backend.dsn = args.dsn

    import uvicorn
    uvicorn.run(create_app(config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
