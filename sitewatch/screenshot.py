from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1280, "height": 900}
NAV_TIMEOUT_MS = 20_000


def page_slug(url: str) -> str:
    """A stable, filesystem-safe name for a page URL, used to pair a
    screenshot with the same page across runs regardless of crawl order.
    Must fold in the query string -- pages like /?division=E0 differ only
    there, and collapsing them to the same file silently overwrites one
    page's screenshot with another's."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    base = "root" if path == "/" else _UNSAFE_CHARS.sub("-", path.strip("/"))
    if parsed.query:
        base = f"{base}--{_UNSAFE_CHARS.sub('-', parsed.query)}"
    # Long, ID-bearing, or heavily-parameterised URLs still need a unique,
    # short filename -- hash the full path+query in alongside a readable prefix.
    if len(base) > 80:
        digest = hashlib.sha1((path + "?" + parsed.query).encode()).hexdigest()[:8]
        base = base[:60] + "-" + digest
    return base


def capture(urls: list[str], out_dir: Path) -> dict[str, Path | None]:
    """Screenshots each URL (full page, desktop viewport). Returns a map of
    url -> saved PNG path, or None for a page that failed to render."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path | None] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) sitewatch/0.1 screenshot"
        ))
        page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        for url in urls:
            dest = out_dir / f"{page_slug(url)}.png"
            try:
                page.goto(url, wait_until="networkidle")
                page.screenshot(path=str(dest), full_page=True)
                results[url] = dest
            except Exception:
                results[url] = None
        browser.close()
    return results
