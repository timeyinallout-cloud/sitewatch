from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sitewatch.config import Site
from sitewatch.crawler import CrawlResult, crawl
from sitewatch.diff import DiffResult, compare
from sitewatch.screenshot import capture, page_slug


@dataclass
class PageDiff:
    url: str
    slug: str
    result: DiffResult
    current_path: Path | None
    baseline_path: Path | None


@dataclass
class SiteReport:
    site: Site
    crawl: CrawlResult
    page_diffs: list[PageDiff] = field(default_factory=list)
    render_failures: list[str] = field(default_factory=list)

    @property
    def visual_regressions(self) -> list[PageDiff]:
        return [d for d in self.page_diffs
                if not d.result.is_new and d.result.diff_image_path is not None]

    @property
    def new_pages(self) -> list[PageDiff]:
        return [d for d in self.page_diffs if d.result.is_new]


def run_site(site: Site, run_dir: Path, baseline_dir: Path,
             max_pages: int = 60, max_depth: int = 4) -> SiteReport:
    crawl_result = crawl(site, max_pages=max_pages, max_depth=max_depth)
    html_urls = [p.url for p in crawl_result.pages if p.is_html and isinstance(p.status, int) and p.status < 400]

    site_run_dir = run_dir / site.slug
    site_baseline_dir = baseline_dir / site.slug
    shots = capture(html_urls, site_run_dir)

    report = SiteReport(site=site, crawl=crawl_result)
    for url, current_path in shots.items():
        if current_path is None:
            report.render_failures.append(url)
            continue
        slug = page_slug(url)
        baseline_path = site_baseline_dir / f"{slug}.png"
        diff_path = site_run_dir / f"{slug}.diff.png"
        result = compare(baseline_path if baseline_path.exists() else None, current_path, diff_path)
        report.page_diffs.append(PageDiff(
            url=url, slug=slug, result=result,
            current_path=current_path,
            baseline_path=baseline_path if baseline_path.exists() else None,
        ))
    return report


def run_all(sites: list[Site], reports_root: Path, baseline_dir: Path,
            max_pages: int = 60, max_depth: int = 4) -> tuple[Path, list[SiteReport]]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = reports_root / run_id
    reports = [run_site(site, run_dir, baseline_dir, max_pages=max_pages, max_depth=max_depth)
               for site in sites]
    return run_dir, reports


def accept_baseline(run_dir: Path, baseline_dir: Path, site_slug: str | None = None) -> int:
    """Copy this run's screenshots into the baseline dir, making the current
    state the new "known good". Scope to one site, or all sites in the run
    if `site_slug` is None. Returns the number of images accepted."""
    import shutil

    count = 0
    site_dirs = [d for d in run_dir.iterdir() if d.is_dir()] if run_dir.exists() else []
    for site_dir in site_dirs:
        if site_slug is not None and site_dir.name != site_slug:
            continue
        dest = baseline_dir / site_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        for png in site_dir.glob("*.png"):
            if png.name.endswith(".diff.png"):
                continue
            shutil.copy2(png, dest / png.name)
            count += 1
    return count
