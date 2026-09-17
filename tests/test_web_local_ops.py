"""Tests for the in-process fallback runner, with sitewatch's own crawl/
report/history/dashboard functions mocked out -- these test local_ops.py's
own wiring and summary math, not the crawler itself (covered elsewhere)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sitewatch.web import local_ops


def _fake_site_report(broken=0, visual=0, failed=0, name="MatchScout"):
    return SimpleNamespace(
        site=SimpleNamespace(name=name, slug=name.lower()),
        crawl=SimpleNamespace(broken_links=["x"] * broken, broken_assets=[]),
        visual_regressions=["y"] * visual,
        render_failures=["z"] * failed,
    )


@pytest.fixture(autouse=True)
def _paths(tmp_path, monkeypatch):
    monkeypatch.setattr(local_ops, "CONFIG_PATH", tmp_path / "sites.toml")
    monkeypatch.setattr(local_ops, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(local_ops, "BASELINE_DIR", tmp_path / "baselines")
    monkeypatch.setattr(local_ops, "HISTORY_FILE", tmp_path / "history.jsonl")
    monkeypatch.setattr(local_ops, "DASHBOARD_OUT", tmp_path / "index.html")


def test_raises_when_no_sites_configured(monkeypatch):
    monkeypatch.setattr(local_ops, "load_sites", lambda path: [])
    with pytest.raises(local_ops.LocalRunError, match="no \\[\\[site\\]\\]"):
        local_ops.run_local()


def test_raises_when_site_slug_unknown(monkeypatch):
    monkeypatch.setattr(local_ops, "load_sites",
                         lambda path: [SimpleNamespace(name="MatchScout", slug="matchscout")])
    with pytest.raises(local_ops.LocalRunError, match="no configured site matches"):
        local_ops.run_local("nonexistent")


def test_successful_run_reports_totals(tmp_path, monkeypatch):
    reports = [_fake_site_report(broken=2, visual=1), _fake_site_report(broken=0, visual=0, name="Other")]
    run_dir = tmp_path / "reports" / "20260101T000000Z"

    monkeypatch.setattr(local_ops, "load_sites",
                         lambda path: [SimpleNamespace(name="MatchScout", slug="matchscout")])
    monkeypatch.setattr(local_ops, "run_all", lambda sites, reports_root, baseline_dir: (run_dir, reports))

    def fake_render(run_id, sites, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("<html></html>")
        return out_path
    monkeypatch.setattr(local_ops, "render", fake_render)
    monkeypatch.setattr(local_ops, "append_run", lambda *a, **kw: None)
    monkeypatch.setattr(local_ops, "load_history", lambda path: [])
    monkeypatch.setattr(local_ops, "render_dashboard", lambda *a, **kw: None)

    result = local_ops.run_local()

    assert result["origin"] == "local"
    assert result["run_id"] == "20260101T000000Z"
    assert result["broken"] == 2
    assert result["visual_regressions"] == 1
    assert result["render_failures"] == 0
    assert result["sites"] == ["MatchScout", "Other"]
    assert Path(result["report_path"]).exists()
    assert (tmp_path / "reports" / "latest.html").exists()


def test_site_filter_only_runs_matching_site(monkeypatch, tmp_path):
    all_sites = [SimpleNamespace(name="MatchScout", slug="matchscout"),
                 SimpleNamespace(name="PrivacyScan", slug="privacyscan")]
    monkeypatch.setattr(local_ops, "load_sites", lambda path: all_sites)

    captured = {}
    def fake_run_all(sites, reports_root, baseline_dir):
        captured["sites"] = sites
        return tmp_path / "reports" / "run1", [_fake_site_report(name="MatchScout")]
    monkeypatch.setattr(local_ops, "run_all", fake_run_all)

    def fake_render(run_id, sites, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("<html></html>")
        return out_path
    monkeypatch.setattr(local_ops, "render", fake_render)
    monkeypatch.setattr(local_ops, "append_run", lambda *a, **kw: None)
    monkeypatch.setattr(local_ops, "load_history", lambda path: [])
    monkeypatch.setattr(local_ops, "render_dashboard", lambda *a, **kw: None)

    local_ops.run_local("matchscout")
    assert [s.slug for s in captured["sites"]] == ["matchscout"]
