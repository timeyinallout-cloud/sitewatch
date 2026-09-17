"""Covers only the --site filter added to `sitewatch run` -- the rest of
cli.py has no existing test file to extend, and backfilling that is out of
scope for this change."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from sitewatch import cli


@pytest.fixture(autouse=True)
def _stubbed(monkeypatch, tmp_path):
    sites = [SimpleNamespace(name="MatchScout", slug="matchscout"),
             SimpleNamespace(name="PrivacyScan", slug="privacyscan")]
    monkeypatch.setattr(cli, "load_sites", lambda path: sites)

    captured = {}

    def fake_run_all(sites_arg, reports_root, baseline_dir, max_pages=60, max_depth=4):
        captured["sites"] = sites_arg
        run_dir = tmp_path / "20260101T000000Z"
        run_dir.mkdir()
        return run_dir, []

    def fake_render(run_id, reports, out_path):
        out_path.write_text("<html></html>")
        return out_path

    monkeypatch.setattr(cli, "run_all", fake_run_all)
    monkeypatch.setattr(cli, "render", fake_render)
    monkeypatch.setattr(cli, "append_run", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "load_history", lambda path: [])
    monkeypatch.setattr(cli, "render_dashboard", lambda *a, **kw: tmp_path / "index.html")
    return captured


def test_no_site_filter_runs_everything(_stubbed, tmp_path):
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--reports-dir", str(tmp_path), "--baseline-dir", str(tmp_path)])
    (tmp_path / "index.html").touch()
    rc = cli._cmd_run(args)
    assert rc == 0
    assert [s.slug for s in _stubbed["sites"]] == ["matchscout", "privacyscan"]


def test_site_filter_limits_to_one_site(_stubbed, tmp_path):
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--site", "privacyscan",
                               "--reports-dir", str(tmp_path), "--baseline-dir", str(tmp_path)])
    (tmp_path / "index.html").touch()
    rc = cli._cmd_run(args)
    assert rc == 0
    assert [s.slug for s in _stubbed["sites"]] == ["privacyscan"]


def test_unknown_site_filter_fails_cleanly(_stubbed, tmp_path):
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--site", "nonexistent",
                               "--reports-dir", str(tmp_path), "--baseline-dir", str(tmp_path)])
    rc = cli._cmd_run(args)
    assert rc == 1
