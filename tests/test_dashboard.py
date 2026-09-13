from pathlib import Path

from sitewatch.config import Site
from sitewatch.crawler import CrawlResult, LinkIssue, PageResult
from sitewatch.dashboard import render_dashboard
from sitewatch.history import HistoryRecord
from sitewatch.runner import SiteReport


def _clean_report():
    site = Site(name="Clean Site", base_url="https://clean.example.com")
    crawl = CrawlResult(site=site)
    crawl.pages = [PageResult(url="https://clean.example.com/", status=200, elapsed_seconds=0.2, is_html=True)]
    return SiteReport(site=site, crawl=crawl)


def _broken_report():
    site = Site(name="Broken Site", base_url="https://broken.example.com")
    crawl = CrawlResult(site=site)
    crawl.pages = [PageResult(url="https://broken.example.com/", status=200, elapsed_seconds=0.2, is_html=True)]
    crawl.issues = [LinkIssue(page_url="https://broken.example.com/",
                               target_url="https://broken.example.com/x", status=404, kind="link")]
    return SiteReport(site=site, crawl=crawl)


def test_dashboard_renders_all_sites(tmp_path):
    out = render_dashboard("run1", [_clean_report(), _broken_report()], [], tmp_path / "index.html")
    html = out.read_text()
    assert "Clean Site" in html
    assert "Broken Site" in html


def test_dashboard_shows_open_issue_count(tmp_path):
    out = render_dashboard("run1", [_broken_report()], [], tmp_path / "index.html")
    html = out.read_text()
    assert "1</div><div class=\"l\">open issue(s)</div>" in html


def test_dashboard_with_no_history_shows_first_run_message(tmp_path):
    out = render_dashboard("run1", [_clean_report()], [], tmp_path / "index.html")
    assert "First run" in out.read_text()


def test_dashboard_renders_trend_cells_from_history(tmp_path):
    history = [
        HistoryRecord(run_id="run0", timestamp="2026-01-01T00:00:00", site="clean-site",
                      pages=1, broken=0, slow=0, visual_regressions=0, render_failures=0),
    ]
    out = render_dashboard("run1", [_clean_report()], history, tmp_path / "index.html")
    html = out.read_text()
    assert 'class="trend-cell good"' in html


def test_dashboard_caps_trend_to_max_runs(tmp_path):
    history = [
        HistoryRecord(run_id=f"run{i}", timestamp=f"2026-01-{i:02d}T00:00:00", site="clean-site",
                      pages=1, broken=0, slow=0, visual_regressions=0, render_failures=0)
        for i in range(1, 31)
    ]
    out = render_dashboard("run31", [_clean_report()], history, tmp_path / "index.html")
    html = out.read_text()
    assert "Last 20 run(s)" in html
