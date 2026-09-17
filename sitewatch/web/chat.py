"""Chat routes -- the bot interface. Reuses deps.require_viewer (same HTTP
Basic credential as the dashboard); no new auth layer for a single-user tool.

Job `kind` is always 'sweep' or 'accept' at creation time -- which actual
path a sweep took (GitHub Actions vs the local fallback) is decided inside
sweep_ops.run_sweep_job and only known once the job finishes, recorded in
its `detail.origin`, never guessed here.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import intent, jobs, sweep_ops
from .deps import require_viewer, templates

router = APIRouter()


def _row_to_message(row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "text": row["text"],
        "job_id": row["job_id"],
        "actions": json.loads(row["actions_json"]) if row["actions_json"] else None,
    }


def _row_to_job(row) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "kind": row["kind"],
        "target": row["target"],
        "summary": row["summary"],
        "detail": json.loads(row["detail"]) if row["detail"] else None,
        "error": row["error"],
    }


def _known_site_slugs() -> set[str]:
    from sitewatch.config import load_sites

    from .local_ops import CONFIG_PATH
    return {s.slug for s in load_sites(CONFIG_PATH)}


def _start_sweep(site_slug: str | None, source: str, background: BackgroundTasks) -> dict:
    target = site_slug or "all"
    if site_slug and site_slug not in _known_site_slugs():
        jobs.add_message("bot", f"“{site_slug}” isn't a configured site.")
        return {"started": False}
    try:
        job_id = jobs.create_job("sweep", target, source)
    except jobs.TargetBusyError as e:
        jobs.add_message(
            "bot", f"A sweep is already running for {target} (job {e.existing_job_id[:8]}) — "
                   f"wait for it to finish before starting another.")
        return {"started": False}
    jobs.add_message("bot", f"Running a sweep ({target})…", job_id=job_id)
    background.add_task(sweep_ops.run_sweep_job, job_id, site_slug)
    return {"started": True, "job_id": job_id}


def _start_accept(run_id: str, site_slug: str | None, source: str, background: BackgroundTasks) -> dict:
    target = f"accept:{run_id}:{site_slug or 'all'}"
    try:
        job_id = jobs.create_job("accept", target, source)
    except jobs.TargetBusyError as e:
        jobs.add_message("bot", f"Already accepting from run {run_id} (job {e.existing_job_id[:8]}).")
        return {"started": False}
    jobs.add_message("bot", f"Accepting baselines from run {run_id}…", job_id=job_id)
    background.add_task(sweep_ops.run_accept_job, job_id, run_id, site_slug)
    return {"started": True, "job_id": job_id}


def _status_text() -> str:
    row = jobs.get_last_complete_sweep()
    if row is None:
        return "No sweep has run yet. Try “run a sweep”."
    return f"Last sweep finished {row['finished_at']} UTC: {row['summary']}"


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, _viewer: str = Depends(require_viewer)):
    rows = jobs.list_messages()
    return templates.TemplateResponse(request, "chat.html", {
        "messages": [_row_to_message(r) for r in rows],
    })


@router.post("/chat/action")
async def chat_action(request: Request, background: BackgroundTasks,
                       _viewer: str = Depends(require_viewer)):
    body = await request.json()
    action = body.get("action")
    if action == "sweep":
        site = (body.get("site") or "").strip() or None
        jobs.add_message("user", f"[sweep] {site or 'all sites'}")
        return _start_sweep(site, "button", background)
    if action == "accept":
        run_id = (body.get("run_id") or "").strip()
        site = (body.get("site") or "").strip() or None
        if not run_id:
            raise HTTPException(status_code=400, detail="Missing run_id")
        jobs.add_message("user", f"[accept] run {run_id}" + (f" for {site}" if site else ""))
        return _start_accept(run_id, site, "button", background)
    raise HTTPException(status_code=400, detail="Unknown action")


@router.post("/chat/send")
async def chat_send(request: Request, background: BackgroundTasks,
                     _viewer: str = Depends(require_viewer)):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message")
    jobs.add_message("user", text)

    parsed = intent.parse(text)
    if parsed is None:
        jobs.add_message("bot", "Try “run a sweep”, “sweep matchscout”, "
                                  "“accept <run id>”, “status”, or use a button.")
        return {"started": False}

    if parsed["action"] == "sweep":
        return _start_sweep(parsed["site"], "typed", background)
    if parsed["action"] == "accept":
        return _start_accept(parsed["run_id"], parsed["site"], "typed", background)
    if parsed["action"] == "status":
        jobs.add_message("bot", _status_text())
        return {"started": False}
    raise HTTPException(status_code=400, detail="Unknown action")  # pragma: no cover - intent is closed


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _viewer: str = Depends(require_viewer)):
    row = jobs.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such job")
    return JSONResponse(_row_to_job(row), headers={"Cache-Control": "no-store"})
