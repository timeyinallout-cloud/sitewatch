"""Tests for the GitHub Actions REST client, with `requests` mocked out --
none of these hit the network."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from sitewatch.web import github_ops


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("SITEWATCH_GH_REPO", "timeyinallout-cloud/sitewatch")
    monkeypatch.setenv("SITEWATCH_GH_TOKEN", "fake-token")


def _resp(status_code=200, json_data=None, content=b"", text=""):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.content = content
    m.text = text
    return m


class TestConfig:
    def test_dispatch_requires_repo(self, monkeypatch):
        monkeypatch.delenv("SITEWATCH_GH_REPO", raising=False)
        with pytest.raises(github_ops.GitHubOpsError, match="SITEWATCH_GH_REPO"):
            github_ops.dispatch("fleet-sweep.yml")

    def test_dispatch_requires_token(self, monkeypatch):
        monkeypatch.delenv("SITEWATCH_GH_TOKEN", raising=False)
        with pytest.raises(github_ops.GitHubOpsError, match="SITEWATCH_GH_TOKEN"):
            github_ops.dispatch("fleet-sweep.yml")


class TestDispatch:
    def test_success_returns_a_timestamp(self, monkeypatch):
        monkeypatch.setattr(github_ops.requests, "post", lambda *a, **kw: _resp(204))
        before = datetime.now(timezone.utc)
        result = github_ops.dispatch("fleet-sweep.yml", {"site": "matchscout"})
        assert before <= result <= datetime.now(timezone.utc)

    def test_non_204_raises(self, monkeypatch):
        monkeypatch.setattr(github_ops.requests, "post",
                             lambda *a, **kw: _resp(404, text="Not Found"))
        with pytest.raises(github_ops.GitHubOpsError, match="dispatch failed"):
            github_ops.dispatch("fleet-sweep.yml")

    def test_request_exception_raises_ops_error(self, monkeypatch):
        import requests as requests_module

        def boom(*a, **kw):
            raise requests_module.ConnectionError("no route to host")
        monkeypatch.setattr(github_ops.requests, "post", boom)
        with pytest.raises(github_ops.GitHubOpsError, match="dispatch request failed"):
            github_ops.dispatch("fleet-sweep.yml")


class TestFindRunAfter:
    def test_finds_a_matching_run(self, monkeypatch):
        after = datetime.now(timezone.utc)
        later = (after + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        monkeypatch.setattr(github_ops.requests, "get", lambda *a, **kw: _resp(
            200, {"workflow_runs": [{"id": 999, "created_at": later}]}))
        assert github_ops.find_run_after("fleet-sweep.yml", after, timeout=5, poll_interval=0.01) == 999

    def test_ignores_runs_created_before(self, monkeypatch):
        after = datetime.now(timezone.utc)
        earlier = (after - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        monkeypatch.setattr(github_ops.requests, "get", lambda *a, **kw: _resp(
            200, {"workflow_runs": [{"id": 111, "created_at": earlier}]}))
        with pytest.raises(github_ops.GitHubOpsError, match="no fleet-sweep.yml run appeared"):
            github_ops.find_run_after("fleet-sweep.yml", after, timeout=0.05, poll_interval=0.01)


class TestPollRun:
    def test_returns_immediately_when_already_completed(self, monkeypatch):
        monkeypatch.setattr(github_ops.requests, "get", lambda *a, **kw: _resp(
            200, {"status": "completed", "conclusion": "success", "html_url": "https://x/1"}))
        result = github_ops.poll_run(1, timeout=5, interval=0.01)
        assert result.status == "completed"
        assert result.conclusion == "success"

    def test_times_out_while_still_in_progress(self, monkeypatch):
        monkeypatch.setattr(github_ops.requests, "get", lambda *a, **kw: _resp(
            200, {"status": "in_progress", "conclusion": None, "html_url": "https://x/1"}))
        result = github_ops.poll_run(1, timeout=0.03, interval=0.01)
        assert result.status == "timed_out"
        assert result.conclusion is None

    def test_non_200_raises(self, monkeypatch):
        monkeypatch.setattr(github_ops.requests, "get", lambda *a, **kw: _resp(500, text="oops"))
        with pytest.raises(github_ops.GitHubOpsError, match="poll failed"):
            github_ops.poll_run(1, timeout=1, interval=0.01)


class TestDownloadArtifact:
    def _zip_bytes(self, files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_downloads_and_extracts(self, monkeypatch, tmp_path):
        zip_bytes = self._zip_bytes({"20260101T000000Z/summary.md": b"# hi"})

        def fake_get(url, **kw):
            if "artifacts" in url and "download" not in url:
                return _resp(200, {"artifacts": [
                    {"name": "sitewatch-report", "archive_download_url": "https://dl/1"}]})
            return _resp(200, content=zip_bytes)

        monkeypatch.setattr(github_ops.requests, "get", fake_get)
        dest = tmp_path / "out"
        github_ops.download_artifact(1, dest)
        assert (dest / "20260101T000000Z" / "summary.md").read_text() == "# hi"

    def test_missing_artifact_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(github_ops.requests, "get",
                             lambda *a, **kw: _resp(200, {"artifacts": []}))
        with pytest.raises(github_ops.GitHubOpsError, match="no artifact named"):
            github_ops.download_artifact(1, tmp_path / "out")

    def test_bad_zip_raises(self, monkeypatch, tmp_path):
        def fake_get(url, **kw):
            if "artifacts" in url and "download" not in url:
                return _resp(200, {"artifacts": [
                    {"name": "sitewatch-report", "archive_download_url": "https://dl/1"}]})
            return _resp(200, content=b"not a zip")
        monkeypatch.setattr(github_ops.requests, "get", fake_get)
        with pytest.raises(github_ops.GitHubOpsError, match="not a valid zip"):
            github_ops.download_artifact(1, tmp_path / "out")
