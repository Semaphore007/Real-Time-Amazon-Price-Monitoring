"""
Raw HTML storage for debugging failed or interesting scrape results.

Files are written to  ./raw_html/<spider>/<ASIN>_<timestamp>.html.gz
Compressed automatically to keep disk usage low.
"""
from __future__ import annotations

import gzip
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path("raw_html")


class RawHtmlStore:
    """
    Thread-safe gzip HTML writer.

    Usage::
        store = RawHtmlStore()
        store.save(response.text, asin="B0SKF6205", spider_name="product_detail")
    """

    def __init__(self, base_dir: str | Path = _DEFAULT_DIR) -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        html: str | bytes,
        *,
        asin: str,
        spider_name: str = "spider",
        url: str = "",
    ) -> Path:
        """
        Persist *html* to disk as gzip.

        Returns the path written, so callers can log it.
        """
        target_dir = self.base_dir / spider_name
        target_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{asin}_{ts}.html.gz"
        filepath = target_dir / filename

        raw = html.encode("utf-8", errors="replace") if isinstance(html, str) else html

        with gzip.open(filepath, "wb") as fh:
            fh.write(raw)
            if url:
                fh.write(f"\n<!-- url: {url} -->".encode())

        logger.debug("Saved raw HTML → %s (%d bytes compressed)", filepath, filepath.stat().st_size)
        return filepath

    def read(self, filepath: str | Path) -> str:
        """Decompress and return stored HTML as a string."""
        with gzip.open(filepath, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace")
