"""In-process fallback sweep executor: runs the crawl directly on this
app's own Chromium when GitHub Actions can't be reached or dispatched.

Deliberately NOT a source of new baselines. A baseline accepted from any
environment other than the CI-pinned one produces false "regressions" on
every subsequent run -- confirmed the hard way once already (see the
[[sitewatch]] memory: a local sandbox run showed PrivacyScan at 8 "visual
regressions" that were pure font-rendering drift, gone entirely when the
same commit ran through GitHub Actions). Every result this module produces
carries `"origin": "local"`, and chat.py/app.py must never offer "accept"
on one -- only "confirm with a real sweep" (dispatching the GitHub path).
"""
from __future__ import annotations

import os
from pathlib import Path

from sitewatch.config import load_sites
from sitewatch.dashboard import render_dashboard
from sitewatch.history import append_run, load_history
from sitewatch.report import render
from sitewatch.runner import run_all

CONFIG_PATH = Path(os.environ.get("SITEWATCH_CONFIG", "sites.toml"))
REPORTS_DIR = Path(os.environ.get("SITEWATCH_REPORTS_DIR", "/data/reports"))
BASELINE_DIR = Path(os.environ.get("SITEWATCH_BASELINE_DIR", "/data/baselines"))
HISTORY_FILE = Path(os.environ.get("SITEWATCH_HISTORY_FILE", "/data/history.jsonl"))
DASHBOARD_OUT = Path(os.environ.get("SITEWATCH_DASHBOARD_OUT", "/data/index.html"))


class LocalRunError(RuntimeError):
    """Raised for a genuine failure (bad config, no matching site, a crawl
    exception) -- never for a normal "issues found" result, which is a
    successful run that simply has broken links or diffs to report."""


def run_local(site_slug: str | None = None) -> dict:
    sites = load_sites(CONFIG_PATH)
    if not sites:
        raise LocalRunError(f"no [[site]] entries found in {CONFIG_PATH}")

    if site_slug:
        sites = [s for s in sites if s.slug == site_slug]
        if not sites:
            raise LocalRunError(f"no configured site matches {site_slug!r}")

    run_dir, site_reports = run_all(sites, REPORTS_DIR, BASELINE_DIR)
    report_path = render(run_dir.name, site_reports, run_dir / "report.html")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "latest.html").write_text(report_path.read_text())

    append_run(HISTORY_FILE, run_dir.name, site_reports)
    render_dashboard(run_dir.name, site_reports, load_history(HISTORY_FILE), DASHBOARD_OUT)

    total_broken = sum(len(r.crawl.broken_links) + len(r.crawl.broken_assets) for r in site_reports)
    total_visual = sum(len(r.visual_regressions) for r in site_reports)
    total_failed = sum(len(r.render_failures) for r in site_reports)

    return {
        "origin": "local",
        "run_id": run_dir.name,
        "report_path": str(report_path),
        "broken": total_broken,
        "visual_regressions": total_visual,
        "render_failures": total_failed,
        "sites": [r.site.name for r in site_reports],
    }
