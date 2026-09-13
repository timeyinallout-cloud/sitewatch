from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sitewatch.config import Site

USER_AGENT = "sitewatch/0.1 (+https://github.com/timeyinallout-cloud/sitewatch)"
REQUEST_TIMEOUT = 15
SLOW_PAGE_SECONDS = 2.0
# Non-HTML links we still status-check but never crawl into or screenshot.
_SKIP_EXTENSIONS = (
    ".pdf", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".css", ".js", ".json", ".xml", ".zip", ".woff", ".woff2", ".txt",
)
# <link> covers many non-fetchable hints (preconnect, dns-prefetch,
# canonical, alternate...) -- only these rels actually load a resource.
_FETCHABLE_LINK_RELS = {"stylesheet", "icon", "shortcut icon", "apple-touch-icon", "manifest", "preload"}


@dataclass
class LinkIssue:
    page_url: str
    target_url: str
    status: int | str  # int status code, or a string like "timeout" / "error: ..."
    kind: str  # "link" or "asset"


@dataclass
class PageResult:
    url: str
    status: int | str
    elapsed_seconds: float
    is_html: bool
    title: str = ""


@dataclass
class CrawlResult:
    site: Site
    pages: list[PageResult] = field(default_factory=list)
    issues: list[LinkIssue] = field(default_factory=list)

    @property
    def slow_pages(self) -> list[PageResult]:
        return [p for p in self.pages if isinstance(p.elapsed_seconds, float)
                and p.elapsed_seconds > SLOW_PAGE_SECONDS]

    @property
    def broken_links(self) -> list[LinkIssue]:
        return [i for i in self.issues if i.kind == "link"]

    @property
    def broken_assets(self) -> list[LinkIssue]:
        return [i for i in self.issues if i.kind == "asset"]


def _same_host(a: str, b: str) -> bool:
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def _is_crawlable_html_link(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not path.endswith(_SKIP_EXTENSIONS)


def crawl(site: Site, max_pages: int = 60, max_depth: int = 4,
          _checked_asset_cache: set[str] | None = None) -> CrawlResult:
    """BFS same-host crawl from the site's homepage. Records every page's
    status/timing, and separately status-checks (but doesn't recurse into)
    every embedded asset and off-host link it finds -- that's how a broken
    CDN reference or a dead outbound link gets caught without needing a
    browser."""
    result = CrawlResult(site=site)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    seen: set[str] = set()
    checked_assets = _checked_asset_cache if _checked_asset_cache is not None else set()
    queue: deque[tuple[str, int]] = deque([(site.base_url + "/", 0)])
    seen.add(site.base_url + "/")

    while queue and len(result.pages) < max_pages:
        url, depth = queue.popleft()
        start = time.monotonic()
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            elapsed = time.monotonic() - start
            status = resp.status_code
        except requests.RequestException as exc:
            elapsed = time.monotonic() - start
            result.pages.append(PageResult(url=url, status=f"error: {exc.__class__.__name__}",
                                            elapsed_seconds=elapsed, is_html=False))
            continue

        content_type = resp.headers.get("content-type", "")
        is_html = "text/html" in content_type
        title = ""
        if is_html:
            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        result.pages.append(PageResult(url=url, status=status, elapsed_seconds=elapsed,
                                        is_html=is_html, title=title))

        if status >= 400:
            result.issues.append(LinkIssue(page_url=url, target_url=url, status=status, kind="link"))

        if not is_html or depth >= max_depth:
            continue

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            target = urljoin(url, href)
            if urlparse(target).scheme not in ("http", "https"):
                continue
            if _same_host(target, site.base_url):
                clean = target.split("#")[0]
                if clean in seen:
                    continue
                if _is_crawlable_html_link(clean):
                    seen.add(clean)
                    queue.append((clean, depth + 1))
                else:
                    # Same-host but not a page we'll crawl/screenshot (a PDF,
                    # a direct asset link, etc.) -- still confirm it resolves.
                    seen.add(clean)
                    _check_external(session, url, clean, checked_assets, result)
            else:
                _check_external(session, url, target, checked_assets, result)

        for tag in soup.find_all(["img", "script"]):
            src = tag.get("src")
            if not src:
                continue
            target = urljoin(url, src)
            if urlparse(target).scheme not in ("http", "https"):
                continue
            _check_asset(session, url, target, checked_assets, result)

        for tag in soup.find_all("link", href=True):
            rel = " ".join(tag.get("rel", [])).lower()
            if rel not in _FETCHABLE_LINK_RELS:
                continue
            target = urljoin(url, tag["href"])
            if urlparse(target).scheme not in ("http", "https"):
                continue
            _check_asset(session, url, target, checked_assets, result)

    return result


# Sites we don't control often WAF-block or rate-limit an identifiable bot
# UA (Cloudflare etc.) even though the link works fine for a real visitor --
# that's noise, not a real break. External checks masquerade as a browser
# and get a longer timeout + a GET retry on ANY failure (not just 4xx)
# before being flagged, to keep the report free of that false-positive class.
EXTERNAL_TIMEOUT = 20
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _check_status(session, target: str, *, external: bool) -> int | str:
    timeout = EXTERNAL_TIMEOUT if external else REQUEST_TIMEOUT
    headers = {"User-Agent": _BROWSER_UA} if external else None
    try:
        resp = session.head(target, timeout=timeout, allow_redirects=True, headers=headers)
        if resp.status_code < 400 and resp.status_code != 405:
            return resp.status_code
    except requests.RequestException:
        pass
    # HEAD failed, was rejected (405), or came back 4xx/5xx -- confirm with a
    # real GET before trusting that verdict.
    try:
        resp = session.get(target, timeout=timeout, allow_redirects=True, stream=True, headers=headers)
        resp.close()
        return resp.status_code
    except requests.RequestException as exc:
        return f"error: {exc.__class__.__name__}"


def _check_asset(session, page_url: str, target: str, cache: set[str], result: CrawlResult) -> None:
    if target in cache:
        return
    cache.add(target)
    status = _check_status(session, target, external=not _same_host(target, page_url))
    if isinstance(status, str) or status >= 400:
        result.issues.append(LinkIssue(page_url=page_url, target_url=target, status=status, kind="asset"))


def _check_external(session, page_url: str, target: str, cache: set[str], result: CrawlResult) -> None:
    if target in cache:
        return
    cache.add(target)
    status = _check_status(session, target, external=True)
    if isinstance(status, str) or status >= 400:
        result.issues.append(LinkIssue(page_url=page_url, target_url=target, status=status, kind="link"))
