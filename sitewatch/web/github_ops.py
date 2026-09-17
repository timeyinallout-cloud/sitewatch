"""Thin GitHub Actions REST client: dispatch fleet-sweep/accept-baseline,
poll to completion, and download+extract report artifacts.

Deliberately never re-implements the crawl -- it stays inside GitHub
Actions' pinned Ubuntu/Chromium environment, the single source of truth
baselines can be trusted against (see the README's own warning: a baseline
accepted from any other environment shows false regressions on every
subsequent CI run). This module is the remote control, not a second
executor; `local_ops.py` is the (explicitly unverified) fallback for when
this one can't be reached.
"""
from __future__ import annotations

import io
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.github.com"
SWEEP_WORKFLOW = "fleet-sweep.yml"
ACCEPT_WORKFLOW = "accept-baseline.yml"
ARTIFACT_NAME = "sitewatch-report"


class GitHubOpsError(RuntimeError):
    """Raised on any GitHub API failure -- dispatch, poll, or download.
    Callers treat this as "remote path unavailable", not a crash."""


def _repo() -> str:
    repo = os.environ.get("SITEWATCH_GH_REPO", "")
    if not repo:
        raise GitHubOpsError("SITEWATCH_GH_REPO is not configured")
    return repo


def _headers() -> dict:
    token = os.environ.get("SITEWATCH_GH_TOKEN", "")
    if not token:
        raise GitHubOpsError("SITEWATCH_GH_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def dispatch(workflow: str, inputs: dict | None = None, *, ref: str = "main") -> datetime:
    """Trigger a workflow_dispatch run. Returns the dispatch time (UTC) --
    the dispatch call itself never returns a run id, so callers match the
    resulting run by creation time via find_run_after()."""
    url = f"{API}/repos/{_repo()}/actions/workflows/{workflow}/dispatches"
    dispatched_at = datetime.now(timezone.utc)
    try:
        resp = requests.post(url, headers=_headers(), json={"ref": ref, "inputs": inputs or {}},
                              timeout=15)
    except requests.RequestException as exc:
        raise GitHubOpsError(f"dispatch request failed: {exc}") from exc
    if resp.status_code != 204:
        raise GitHubOpsError(f"dispatch failed: HTTP {resp.status_code}: {resp.text[:300]}")
    return dispatched_at


def find_run_after(workflow: str, after: datetime, *, timeout: float = 30.0,
                    poll_interval: float = 2.0) -> int:
    """Poll the workflow's run list until one created at/after `after`
    appears. Raises GitHubOpsError if none shows up within `timeout`."""
    url = f"{API}/repos/{_repo()}/actions/workflows/{workflow}/runs"
    deadline = time.monotonic() + timeout
    while True:
        try:
            resp = requests.get(url, headers=_headers(),
                                 params={"event": "workflow_dispatch", "per_page": 5}, timeout=15)
        except requests.RequestException as exc:
            raise GitHubOpsError(f"run lookup failed: {exc}") from exc
        if resp.status_code == 200:
            for run in resp.json().get("workflow_runs", []):
                created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                if created >= after:
                    return run["id"]
        if time.monotonic() >= deadline:
            raise GitHubOpsError(f"no {workflow} run appeared within {timeout:.0f}s of dispatch")
        time.sleep(poll_interval)


@dataclass
class RunResult:
    run_id: int
    status: str                # "completed" or "timed_out"
    conclusion: str | None     # "success"/"failure"/None (only set when completed)
    html_url: str


def poll_run(run_id: int, *, timeout: float = 600.0, interval: float = 10.0) -> RunResult:
    """Poll a run until it reaches a terminal status or `timeout` elapses."""
    url = f"{API}/repos/{_repo()}/actions/runs/{run_id}"
    deadline = time.monotonic() + timeout
    last: dict = {}
    while True:
        try:
            resp = requests.get(url, headers=_headers(), timeout=15)
        except requests.RequestException as exc:
            raise GitHubOpsError(f"poll failed: {exc}") from exc
        if resp.status_code != 200:
            raise GitHubOpsError(f"poll failed: HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        last = data
        if data["status"] == "completed":
            return RunResult(run_id=run_id, status="completed",
                              conclusion=data["conclusion"], html_url=data["html_url"])
        if time.monotonic() >= deadline:
            return RunResult(run_id=run_id, status="timed_out", conclusion=None,
                              html_url=last.get("html_url", ""))
        time.sleep(interval)


def download_artifact(run_id: int, dest_dir: Path, *, name: str = ARTIFACT_NAME) -> Path:
    """Download and extract a run's named artifact into dest_dir."""
    list_url = f"{API}/repos/{_repo()}/actions/runs/{run_id}/artifacts"
    try:
        resp = requests.get(list_url, headers=_headers(), timeout=15)
    except requests.RequestException as exc:
        raise GitHubOpsError(f"listing artifacts failed: {exc}") from exc
    if resp.status_code != 200:
        raise GitHubOpsError(f"listing artifacts failed: HTTP {resp.status_code}")
    artifacts = resp.json().get("artifacts", [])
    match = next((a for a in artifacts if a["name"] == name), None)
    if match is None:
        raise GitHubOpsError(f"run {run_id} has no artifact named {name!r}")

    try:
        zip_resp = requests.get(match["archive_download_url"], headers=_headers(), timeout=60)
    except requests.RequestException as exc:
        raise GitHubOpsError(f"artifact download failed: {exc}") from exc
    if zip_resp.status_code != 200:
        raise GitHubOpsError(f"artifact download failed: HTTP {zip_resp.status_code}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            zf.extractall(dest_dir)
    except zipfile.BadZipFile as exc:
        raise GitHubOpsError(f"artifact for run {run_id} is not a valid zip: {exc}") from exc
    return dest_dir
