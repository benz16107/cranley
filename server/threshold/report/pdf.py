"""Print the report's HTML to PDF with headless Chrome, which is already on the server (no new dependency)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class Unavailable(RuntimeError):
    """No Chrome on this server, or it failed to print."""


def chrome() -> str:
    for c in (os.environ.get("THRESHOLD_CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if c and shutil.which(c):
            return shutil.which(c)
    raise Unavailable("No Chrome or Chromium on this server to print the PDF; open the HTML report and print it instead.")


def from_html(html: str, timeout: float = 90) -> bytes:
    with tempfile.TemporaryDirectory(prefix="threshold-report-") as d:
        src, out = Path(d) / "report.html", Path(d) / "report.pdf"
        src.write_text(html)
        # its own profile folder: a Chrome already running on this machine would otherwise take the job and exit at once
        cmd = [chrome(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={d}/profile", "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as e:
            raise Unavailable("Chrome took too long to print the report.") from e
        if not out.exists() or out.stat().st_size == 0:
            raise Unavailable(f"Chrome did not print the report (exit {p.returncode}).")
        return out.read_bytes()
