# -*- coding: utf-8 -*-
"""Entry point for Metashape Pro:  metashape.exe -r scripts/metashape_batch.py

Equivalent to running the root ``Batch_metashape.py`` (which holds the USER
CONFIG block); this shim just makes the repo layout explicit for the
``scripts/`` convention.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT / "src", REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from neoreef.common.logging import restore_std_streams  # noqa: E402

restore_std_streams()

from Batch_metashape import main  # noqa: E402  (user config + run)

if __name__ == "__main__":
    sys.exit(main())
