from __future__ import annotations

import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Site:
    name: str
    base_url: str
    # URL path+query glob patterns (fnmatch syntax) excluded from screenshot/
    # visual-regression comparison -- still crawled and link/asset-checked
    # like any other page. For pages whose content is expected to change
    # every run (live fixtures, live odds, a homepage built from the day's
    # data), pixel-diffing them is pure noise: a "regression" every single
    # day is not a signal of anything broken, and drowns out real ones.
    visual_exclude: tuple[str, ...] = ()
    # External hostnames whose broken-link/asset findings never fail CI
    # (--fail-on-issues), for third-party domains we don't control and have
    # confirmed are just occasionally flaky rather than a real break on our
    # side -- e.g. gamblingtherapy.org, linked from responsible-gambling
    # compliance pages, seen returning a real timeout on 2026-09-19 and a
    # real 502 on 2026-09-21 across two different sites. Findings on these
    # hosts still show up in the report/dashboard as usual (this doesn't
    # hide the issue, just stops re-litigating the same non-actionable
    # third-party outage as a fresh CI failure every time it recurs) --
    # only the pass/fail exit code ignores them.
    link_ignore_hosts: tuple[str, ...] = ()

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")

    def excludes_visual(self, url: str) -> bool:
        """Whether `url` matches one of this site's `visual_exclude` glob
        patterns, checked against both the bare path and path+query (so a
        pattern of "/" excludes the homepage without also needing to
        enumerate every query-string variant of it, while "/?division=*"
        can still target only the parameterised ones)."""
        if not self.visual_exclude:
            return False
        parsed = urlparse(url)
        path = parsed.path or "/"
        with_query = f"{path}?{parsed.query}" if parsed.query else path
        return any(fnmatch(path, pat) or fnmatch(with_query, pat) for pat in self.visual_exclude)

    def ignores_link_host(self, url: str) -> bool:
        """Whether `url`'s hostname is in this site's `link_ignore_hosts`."""
        if not self.link_ignore_hosts:
            return False
        return urlparse(url).hostname in self.link_ignore_hosts


def load_sites(path: Path) -> list[Site]:
    data = tomllib.loads(Path(path).read_text())
    return [
        Site(
            name=s["name"], base_url=s["base_url"].rstrip("/"),
            visual_exclude=tuple(s.get("visual_exclude", ())),
            link_ignore_hosts=tuple(s.get("link_ignore_hosts", ())),
        )
        for s in data.get("site", [])
    ]
