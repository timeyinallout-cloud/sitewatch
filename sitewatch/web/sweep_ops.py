"""Orchestrates one "run a sweep" or "accept a baseline" request: try
GitHub Actions first, fall back to the in-process local crawl if GitHub
can't be reached, dispatched, or doesn't produce/finish a run in time.

See github_ops.py and local_ops.py's own docstrings for why the split
exists and what a "local" result is (and is not) good for. Accepting a
baseline always goes through GitHub Actions -- there is no local fallback
for accept, since accepting IS the operation that must never happen outside
the CI-pinned environment.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from . import github_ops, jobs, local_ops

# Downloaded GitHub Actions artifacts are persisted here (not a tempdir) so
# the dashboard/report viewer can serve them after this process restarts,
# same volume local_ops.py's own runs already live on.
GH_ARTIFACT_DIR = Path(os.environ.get("SITEWATCH_REPORTS_DIR", "/data/reports"))

log = logging.getLogger(__name__)

DISPATCH_FIND_TIMEOUT = 30.0   # how long to wait for the dispatched run to appear in the list
SWEEP_POLL_TIMEOUT = 600.0     # how long to wait for a sweep to finish (a real one: ~3 min)
ACCEPT_POLL_TIMEOUT = 180.0


def run_sweep_job(job_id: str, site_slug: str | None) -> None:
    jobs.start_job(job_id)
    try:
        result = _try_remote_sweep(site_slug)
        if result is None:
            result = local_ops.run_local(site_slug)
        summary = _summarize_sweep(result)
        jobs.finish_job(job_id, "complete", summary=summary, detail=result)
        jobs.update_message_for_job(job_id, summary, _actions_for_sweep(result))
    except local_ops.LocalRunError as exc:
        message = f"Sweep failed on both paths: {exc}"
        jobs.finish_job(job_id, "failed", error=message)
        jobs.update_message_for_job(job_id, message, None)
    except Exception as e:  # noqa: BLE001
        jobs.finish_job(job_id, "failed", error=str(e))
        jobs.update_message_for_job(job_id, f"Sweep failed: {e}", None)


def run_accept_job(job_id: str, run_id: str, site_slug: str | None) -> None:
    jobs.start_job(job_id)
    try:
        inputs = {"run_id": run_id}
        if site_slug:
            inputs["site"] = site_slug
        dispatched_at = github_ops.dispatch(github_ops.ACCEPT_WORKFLOW, inputs)
        gh_run_id = github_ops.find_run_after(
            github_ops.ACCEPT_WORKFLOW, dispatched_at, timeout=DISPATCH_FIND_TIMEOUT)
        result = github_ops.poll_run(gh_run_id, timeout=ACCEPT_POLL_TIMEOUT)

        if result.status == "timed_out":
            summary = (f"Accept dispatched (run {gh_run_id}) but hadn't finished after "
                       f"{ACCEPT_POLL_TIMEOUT:.0f}s — check {result.html_url or 'GitHub Actions'}.")
        elif result.conclusion == "success":
            summary = f"Accepted baselines from run {run_id}. ({result.html_url})"
        else:
            summary = (f"Accept run finished with conclusion={result.conclusion!r} — "
                       f"check {result.html_url}.")

        detail = {"origin": "github", "run_id": gh_run_id, "html_url": result.html_url,
                   "conclusion": result.conclusion, "source_run_id": run_id, "site": site_slug}
        jobs.finish_job(job_id, "complete", summary=summary, detail=detail)
        jobs.update_message_for_job(job_id, summary, [{"label": "View run on GitHub",
                                                          "url": result.html_url}] if result.html_url else None)
    except github_ops.GitHubOpsError as exc:
        message = (f"Couldn't accept via GitHub Actions: {exc}. Accepting only ever happens "
                   f"from the CI-pinned environment, so there is no local fallback for this — "
                   f"run `sitewatch accept` yourself once GitHub Actions is reachable.")
        jobs.finish_job(job_id, "failed", error=message)
        jobs.update_message_for_job(job_id, message, None)
    except Exception as e:  # noqa: BLE001
        jobs.finish_job(job_id, "failed", error=str(e))
        jobs.update_message_for_job(job_id, f"Accept failed: {e}", None)


def _try_remote_sweep(site_slug: str | None) -> dict | None:
    inputs = {"site": site_slug} if site_slug else {}
    try:
        dispatched_at = github_ops.dispatch(github_ops.SWEEP_WORKFLOW, inputs)
        run_id = github_ops.find_run_after(github_ops.SWEEP_WORKFLOW, dispatched_at,
                                            timeout=DISPATCH_FIND_TIMEOUT)
        result = github_ops.poll_run(run_id, timeout=SWEEP_POLL_TIMEOUT)
    except github_ops.GitHubOpsError as exc:
        log.warning("GitHub Actions path unavailable, falling back to local: %s", exc)
        return None

    if result.status == "timed_out":
        log.warning("GitHub Actions run %s did not finish within %.0fs, falling back to local",
                     result.run_id, SWEEP_POLL_TIMEOUT)
        return None

    # conclusion "failure" here just means --fail-on-issues found real
    # issues -- a normal, trustworthy result, not an infra problem. Only
    # missing artifacts mean the remote path genuinely didn't deliver.
    dest = GH_ARTIFACT_DIR / f"gh-{result.run_id}"
    try:
        github_ops.download_artifact(result.run_id, dest)
    except github_ops.GitHubOpsError as exc:
        log.warning("GitHub run %s completed but its artifact couldn't be fetched, "
                     "falling back to local: %s", result.run_id, exc)
        return None

    summary_path = next(dest.glob("*/summary.md"), None)
    report_path = next(dest.glob("*/report.html"), None)
    return {
        "origin": "github",
        "run_id": result.run_id,
        "html_url": result.html_url,
        "conclusion": result.conclusion,
        "artifact_dir": str(dest),
        "report_path": str(report_path) if report_path else None,
        "summary_md": summary_path.read_text() if summary_path else "",
    }


def _summarize_sweep(result: dict) -> str:
    if result["origin"] == "github":
        header = f"Sweep complete via GitHub Actions (run {result['run_id']})."
        body = result.get("summary_md", "").strip()
        return f"{header}\n\n{body}" if body else header
    return (
        f"Sweep complete (ran locally — GitHub Actions was unreachable). "
        f"{result['broken']} broken link(s)/asset(s), {result['visual_regressions']} visual "
        f"change(s) flagged, {result['render_failures']} render failure(s). Visual changes from "
        f"a local run are unverified against the real baseline environment — re-run "
        f"“run a sweep” once GitHub Actions is reachable before trusting or accepting them."
    )


def _actions_for_sweep(result: dict) -> list[dict] | None:
    if result["origin"] == "github":
        actions = [{"label": "View run on GitHub", "url": result["html_url"]}]
        actions.append({"action": "accept", "label": "Accept new baselines",
                         "run_id": str(result["run_id"])})
        return actions
    return [{"action": "sweep", "label": "Retry via GitHub Actions", "site": ""}]
