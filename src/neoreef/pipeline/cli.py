"""``neoreef-pipeline`` command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from neoreef import __version__
from neoreef.common.logging import make_cli_logger
from . import stages
from .config import ConfigError, load_config
from .context import PipelineContext, resolve_viewers_dir
from .state import clear_records, load_records, save_records
from .stages.serve import start_local_server

DEFAULT_CONFIG = "config/cesium_config.json"
LOG_FILENAME = "cesium_pipeline.log"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neoreef-pipeline",
        description="NeoReef Cesium Pipeline: prepare geospatial data for CesiumJS",
    )
    p.add_argument("--config", default=DEFAULT_CONFIG, help=f"Path to cesium_config.json (default: {DEFAULT_CONFIG})")
    p.add_argument("--stage", default="all", choices=["all", *stages.ORDER, "serve"],
                   help="Pipeline stage to run (default: all)")
    p.add_argument("--port", type=int, default=None, help="Override LOCAL_SERVER_PORT from config")
    p.add_argument("--rescan", action="store_true",
                   help="Discard .state/records.json before running (forces a fresh scan)")
    p.add_argument("--viewers-dir", default=None, help="Directory with the viewer pages to copy")
    p.add_argument("--version", action="version", version=f"neoreef {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if args.viewers_dir:
        cfg.viewers_dir = Path(args.viewers_dir)

    out_dir = cfg.cesium_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    log = make_cli_logger(out_dir / LOG_FILENAME, name="neoreef.pipeline")
    log.info("=" * 60)
    log.info(f"NeoReef Cesium Pipeline v{__version__}  -  stage: {args.stage}")
    log.info(f"Config: {args.config}")
    log.info("=" * 60)
    for w in cfg.warnings:
        log.warning(w)

    ctx = PipelineContext(cfg=cfg, log=log, out_dir=out_dir,
                          viewers_dir=resolve_viewers_dir(cfg),
                          port=args.port or cfg.local_server_port)

    if args.rescan:
        clear_records(out_dir)
        log.info("State cleared (--rescan)")
    rs = load_records(out_dir, log)

    for name in stages.expand(args.stage):
        try:
            rs = stages.STAGES[name](ctx, rs)
        except Exception as e:
            log.error(f"Stage {name!r} failed: {e}", exc_info=True)
            if not cfg.continue_on_error:
                save_records(out_dir, rs)
                return 1
        save_records(out_dir, rs)

    if args.stage == "serve":
        log.info("--- Stage: local HTTP server ---")
        start_local_server(out_dir, ctx.port, log)

    log.info("Pipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
