"""Shared auth dependencies, importable by both app.py and chat.py without
either importing the other. Same shape as Foreman/Fleetboard's deps.py.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_basic = HTTPBasic(auto_error=False)


def _dev_mode() -> bool:
    return os.environ.get("SITEWATCH_DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def require_write_key(key: str | None = Depends(_api_key_header)) -> str:
    """A scheduler's credential -- triggering a run, not viewing one."""
    valid_keys = {k for k in os.environ.get("SITEWATCH_WRITE_KEYS", "").split(",") if k}
    if not valid_keys:
        if _dev_mode():
            return "dev"
        raise HTTPException(status_code=503, detail="Service is not configured")
    if key not in valid_keys:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")
    return key


def require_viewer(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> str:
    """A human looking at the dashboard/chat in a browser."""
    user = os.environ.get("SITEWATCH_USER", "")
    password = os.environ.get("SITEWATCH_PASS", "")
    unauthorized = HTTPException(status_code=401, detail="Invalid credentials",
                                  headers={"WWW-Authenticate": "Basic"})
    if not (user and password):
        if _dev_mode():
            return "dev"
        raise HTTPException(status_code=503, detail="Service is not configured")
    if credentials is None:
        raise unauthorized
    ok_user = secrets.compare_digest(credentials.username, user)
    ok_pass = secrets.compare_digest(credentials.password, password)
    if not (ok_user and ok_pass):
        raise unauthorized
    return credentials.username
