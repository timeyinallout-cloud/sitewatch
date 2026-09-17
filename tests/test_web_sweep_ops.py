"""Tests for the remote-first/local-fallback orchestration, with
github_ops and local_ops fully mocked -- these test sweep_ops.py's own
decision logic (when does it fall back, what does it write to the job),
not either executor."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sitewatch.web import github_ops, jobs, local_ops, sweep_ops


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    jobs.init_db(p)
    monkeypatch.setattr(jobs, "DEFAULT_DB_PATH", p)
    return p


def _run_result(status="completed", conclusion="success", html_url="https://x/1", run_id=42):
    return github_ops.RunResult(run_id=run_id, status=status, conclusion=conclusion, html_url=html_url)


class TestRunSweepJob:
    def test_remote_success_marks_job_complete_with_github_origin(self, db, monkeypatch, tmp_path):
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 42)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run", lambda *a, **kw: _run_result())

        run_dir = tmp_path / "gh-42" / "20260101T000000Z"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.md").write_text("### sitewatch\n- ok")
        (run_dir / "report.html").write_text("<html></html>")
        monkeypatch.setattr(sweep_ops.github_ops, "download_artifact",
                             lambda run_id, dest, **kw: dest)
        monkeypatch.setattr(sweep_ops, "GH_ARTIFACT_DIR", tmp_path)

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)

        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "GitHub Actions" in row["summary"]

    def test_dispatch_failure_falls_back_to_local(self, db, monkeypatch):
        def boom(*a, **kw):
            raise github_ops.GitHubOpsError("network unreachable")
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", boom)
        monkeypatch.setattr(sweep_ops.local_ops, "run_local", lambda site_slug: {
            "origin": "local", "run_id": "local1", "report_path": "/tmp/x.html",
            "broken": 0, "visual_regressions": 0, "render_failures": 0, "sites": ["MatchScout"],
        })

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)

        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "locally" in row["summary"]
        assert "unverified" in row["summary"]

    def test_run_that_never_finishes_falls_back_to_local(self, db, monkeypatch):
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 42)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run",
                             lambda *a, **kw: _run_result(status="timed_out", conclusion=None))
        monkeypatch.setattr(sweep_ops.local_ops, "run_local", lambda site_slug: {
            "origin": "local", "run_id": "local1", "report_path": "/tmp/x.html",
            "broken": 0, "visual_regressions": 0, "render_failures": 0, "sites": [],
        })

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)
        assert jobs.get_job(job_id)["status"] == "complete"

    def test_missing_artifact_falls_back_to_local(self, db, monkeypatch):
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 42)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run", lambda *a, **kw: _run_result())

        def boom(*a, **kw):
            raise github_ops.GitHubOpsError("artifact expired")
        monkeypatch.setattr(sweep_ops.github_ops, "download_artifact", boom)
        monkeypatch.setattr(sweep_ops.local_ops, "run_local", lambda site_slug: {
            "origin": "local", "run_id": "local1", "report_path": "/tmp/x.html",
            "broken": 0, "visual_regressions": 0, "render_failures": 0, "sites": [],
        })

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)
        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "locally" in row["summary"]

    def test_failure_conclusion_with_a_real_artifact_is_not_a_fallback_trigger(self, db, monkeypatch, tmp_path):
        """--fail-on-issues means real issues were found -- a normal,
        trustworthy result, not an infra failure that should fall back."""
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 42)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run",
                             lambda *a, **kw: _run_result(conclusion="failure"))

        run_dir = tmp_path / "20260101T000000Z"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.md").write_text("1 broken link")
        (run_dir / "report.html").write_text("<html></html>")
        monkeypatch.setattr(sweep_ops.github_ops, "download_artifact",
                             lambda run_id, dest, **kw: dest)
        monkeypatch.setattr(sweep_ops, "GH_ARTIFACT_DIR", tmp_path)

        local_called = []
        monkeypatch.setattr(sweep_ops.local_ops, "run_local", lambda site_slug: local_called.append(1))

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)

        assert local_called == []  # local fallback never invoked
        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "GitHub Actions" in row["summary"]

    def test_both_paths_failing_marks_job_failed(self, db, monkeypatch):
        def boom(*a, **kw):
            raise github_ops.GitHubOpsError("unreachable")
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", boom)
        monkeypatch.setattr(sweep_ops.local_ops, "run_local",
                             lambda site_slug: (_ for _ in ()).throw(
                                 local_ops.LocalRunError("no chromium available")))

        job_id = jobs.create_job("sweep", "all", "button")
        sweep_ops.run_sweep_job(job_id, None)
        row = jobs.get_job(job_id)
        assert row["status"] == "failed"
        assert "both paths" in row["error"]


class TestRunAcceptJob:
    def test_success(self, db, monkeypatch):
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 99)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run", lambda *a, **kw: _run_result(run_id=99))

        job_id = jobs.create_job("accept", "accept:42:all", "button")
        sweep_ops.run_accept_job(job_id, "42", None)
        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "Accepted" in row["summary"]

    def test_no_local_fallback_for_accept(self, db, monkeypatch):
        """Accept must never fall back locally -- accepting IS the operation
        that can only ever be trusted from the CI-pinned environment."""
        def boom(*a, **kw):
            raise github_ops.GitHubOpsError("unreachable")
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", boom)
        local_called = []
        monkeypatch.setattr(sweep_ops.local_ops, "run_local", lambda *a, **kw: local_called.append(1))

        job_id = jobs.create_job("accept", "accept:42:all", "button")
        sweep_ops.run_accept_job(job_id, "42", None)

        assert local_called == []
        row = jobs.get_job(job_id)
        assert row["status"] == "failed"
        assert "no local fallback" in row["error"]

    def test_failed_conclusion_is_reported_not_treated_as_success(self, db, monkeypatch):
        monkeypatch.setattr(sweep_ops.github_ops, "dispatch", lambda *a, **kw: datetime.now(timezone.utc))
        monkeypatch.setattr(sweep_ops.github_ops, "find_run_after", lambda *a, **kw: 99)
        monkeypatch.setattr(sweep_ops.github_ops, "poll_run",
                             lambda *a, **kw: _run_result(run_id=99, conclusion="failure"))

        job_id = jobs.create_job("accept", "accept:42:all", "button")
        sweep_ops.run_accept_job(job_id, "42", None)
        row = jobs.get_job(job_id)
        assert row["status"] == "complete"
        assert "conclusion='failure'" in row["summary"]
