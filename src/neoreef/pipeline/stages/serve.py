"""Local development server: threaded, CORS-enabled, with HTTP Range support.

CesiumJS fetches COGs with Range requests; the stdlib SimpleHTTPRequestHandler
ignores the header and would stream whole multi-GB files, and the plain
HTTPServer serves one request at a time. Both are fixed here.
"""

from __future__ import annotations

import logging
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024


def parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    """``bytes=a-b`` -> (start, end) inclusive, clamped to *size*; None if absent/invalid."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    start_s, end_s = m.groups()
    if start_s == "" and end_s == "":
        return None
    if start_s == "":                      # suffix range: last N bytes
        length = int(end_s)
        if length <= 0:
            return None
        return max(0, size - length), size - 1
    start = int(start_s)
    end = int(end_s) if end_s else size - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        return None
    return start, end


class RangeCORSHandler(SimpleHTTPRequestHandler):
    """Static files with CORS headers and single-range GET support."""

    _range: Optional[Tuple[int, int]] = None

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def send_head(self):
        self._range = None
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        header = self.headers.get("Range")
        if not header:
            return super().send_head()
        rng = parse_range(header, size)
        if rng is None:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        start, end = rng
        f = open(path, "rb")
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(os.fstat(f.fileno()).st_mtime))
        self.end_headers()
        self._range = (start, end)
        return f

    def copyfile(self, source, outputfile):
        if self._range is None:
            return super().copyfile(source, outputfile)
        start, end = self._range
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(CHUNK, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def log_message(self, fmt, *args):
        pass


def make_server(serve_dir: Path, port: int, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    handler = partial(RangeCORSHandler, directory=str(serve_dir))
    return ThreadingHTTPServer((host, port), handler)


def start_local_server(serve_dir: Path, port: int, log: logging.Logger) -> None:
    server = make_server(serve_dir, port)
    log.info(f"Local server started at http://0.0.0.0:{port}  (serving {serve_dir})")
    log.info(f"  LAN access: http://<your-ip>:{port}/")
    log.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")
    finally:
        server.server_close()
