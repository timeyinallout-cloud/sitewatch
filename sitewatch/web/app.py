"""sitewatch's interactive layer: a chat bot (see chat.py) that can trigger
a sweep or accept new baselines on demand, on top of the existing CLI +
GitHub Actions `fleet-sweep`/`accept-baseline` workflows this app remote-
controls rather than replaces. See sweep_ops.py for why the actual crawl
runs in GitHub Actions first and only falls back to this process's own
Chromium (local_ops.py) when GitHub can't be reached -- baselines must
never be trusted from, or accepted from, that local fallback path.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from . import chat, jobs, sentry_setup
from .deps import require_viewer, templates

sentry_setup.init()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    jobs.init_db()
    yield


app = FastAPI(title="sitewatch", lifespan=_lifespan)
app.include_router(chat.router)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    resp.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "base-uri 'self'; frame-ancestors 'none'"))
    return resp


def _known_sites() -> list[dict]:
    from sitewatch.config import load_sites

    from .local_ops import CONFIG_PATH
    try:
        return [{"name": s.name, "slug": s.slug} for s in load_sites(CONFIG_PATH)]
    except (OSError, ValueError):
        return []


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _viewer: str = Depends(require_viewer)):
    last = jobs.get_last_complete_sweep()
    detail = json.loads(last["detail"]) if last and last["detail"] else None
    return templates.TemplateResponse(request, "index.html", {
        "sites": _known_sites(),
        "last_sweep": last,
        "last_detail": detail,
    })


@app.get("/report/{job_id}")
def report(job_id: str, _viewer: str = Depends(require_viewer)):
    row = jobs.get_job(job_id)
    if row is None or row["status"] != "complete":
        raise HTTPException(status_code=404, detail="No completed report for that job")
    detail = json.loads(row["detail"]) if row["detail"] else {}
    report_path = detail.get("report_path")
    if not report_path or not Path(report_path).exists():
        raise HTTPException(status_code=404, detail="No report file for that job")
    return FileResponse(report_path, media_type="text/html")


@app.get("/report/{job_id}/{asset_path:path}")
def report_asset(job_id: str, asset_path: str, _viewer: str = Depends(require_viewer)):
    """Screenshots/diff images the report.html references by a path
    relative to itself -- served from the same directory, never above it."""
    row = jobs.get_job(job_id)
    if row is None or row["status"] != "complete":
        raise HTTPException(status_code=404, detail="No completed report for that job")
    detail = json.loads(row["detail"]) if row["detail"] else {}
    report_path = detail.get("report_path")
    if not report_path:
        raise HTTPException(status_code=404, detail="No report file for that job")
    base_dir = Path(report_path).parent.resolve()
    candidate = (base_dir / asset_path).resolve()
    if base_dir not in candidate.parents and candidate != base_dir:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="No such file")
    return FileResponse(candidate)


@app.get("/health")
def health():
    return {"status": "ok"}
