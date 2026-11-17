#!/usr/bin/env python3
"""Compatibility shim: the pipeline now lives in ``src/neoreef/pipeline``.

    python cesium_pipeline.py --config config/cesium_config.json --stage all

is equivalent to ``neoreef-pipeline ...`` after ``pip install -e .``.
This file will be removed once all docs and scripts use the new entry point.
"""

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from neoreef.pipeline.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
