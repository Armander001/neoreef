"""Logger factories for the two runtimes.

``make_cli_logger``        stdlib ``logging`` with console + file handlers (pipeline).
``make_metashape_logger``  a plain ``log(msg)`` callable that fans out to the
                           Metashape console, stdout and a file handle, and never
                           raises (Metashape sessions can have closed stdio).

The Metashape console printer is *injected* so this module stays importable
without the ``Metashape`` package.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Optional, TextIO

LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def make_cli_logger(log_path: Path, name: str = "neoreef") -> logging.Logger:
    """Console (INFO+) and file (DEBUG+) logger. Idempotent per *name*."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fmt = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


def make_metashape_logger(log_handle: Optional[TextIO] = None,
                          console_print: Optional[Callable[[str], None]] = None
                          ) -> Callable[[str], None]:
    """Return ``log(msg)`` that writes to the Metashape console, stdout and a file.

    Each sink is wrapped in its own try/except so a closed stream never aborts
    a batch. Pass ``console_print=Metashape.app.console.print`` from the
    batch script.
    """
    def log(msg) -> None:
        msg = str(msg)
        if console_print is not None:
            try:
                console_print(msg)
            except Exception:
                pass
        try:
            print(msg)
        except Exception:
            pass
        if log_handle is not None:
            try:
                log_handle.write(msg + "\n")
                log_handle.flush()
            except Exception:
                pass
    return log


def restore_std_streams() -> None:
    """Re-attach stdout/stderr if a Metashape session closed them."""
    try:
        if sys.stdout is None or getattr(sys.stdout, "closed", False):
            sys.stdout = sys.__stdout__
        if sys.stderr is None or getattr(sys.stderr, "closed", False):
            sys.stderr = sys.__stderr__
    except Exception:
        pass
