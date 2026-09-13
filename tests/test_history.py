import json

from sitewatch.config import Site
from sitewatch.crawler import CrawlResult, PageResult
from sitewatch.history import append_run, history_by_site, load_history
from sitewatch.runner import SiteReport


def _report(slug_name="Test Site", pages=5):
    site = Site(name=slug_name, base_url="https://example.com")
    crawl = CrawlResult(site=site)
    crawl.pages = [
        PageResult(url=f"https://example.com/{i}", status=200, elapsed_seconds=0.2, is_html=True)
        for i in range(pages)
    ]
    return SiteReport(site=site, crawl=crawl)


def test_append_creates_one_line_per_site(tmp_path):
    path = tmp_path / "history.jsonl"
    append_run(path, "run1", [_report("A"), _report("B")])
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["site"] == "a"


def test_append_is_additive_across_runs(tmp_path):
    path = tmp_path / "history.jsonl"
    append_run(path, "run1", [_report("A")])
    append_run(path, "run2", [_report("A")])
    records = load_history(path)
    assert [r.run_id for r in records] == ["run1", "run2"]


def test_load_history_on_missing_file_is_empty(tmp_path):
    assert load_history(tmp_path / "nope.jsonl") == []


def test_history_by_site_groups_and_sorts(tmp_path):
    path = tmp_path / "history.jsonl"
    append_run(path, "run1", [_report("A"), _report("B")])
    append_run(path, "run2", [_report("A"), _report("B")])
    grouped = history_by_site(load_history(path))
    assert set(grouped.keys()) == {"a", "b"}
    assert [r.run_id for r in grouped["a"]] == ["run1", "run2"]


def test_issue_count_sums_all_categories(tmp_path):
    path = tmp_path / "history.jsonl"
    append_run(path, "run1", [_report("A")])
    record = load_history(path)[0]
    assert record.issue_count == record.broken + record.slow + record.visual_regressions + record.render_failures
