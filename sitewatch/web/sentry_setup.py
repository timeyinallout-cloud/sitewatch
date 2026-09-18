"""Error tracking via Sentry -- a no-op unless SENTRY_DSN is set, so this is
safe to import unconditionally from app.py without gating every deployment
on having an account. Same pattern as Foreman's sentry_setup.py -- see that
app's memory for why this was added.
"""
from __future__ import annotations

import os


def init() -> None:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.0,
        environment=os.environ.get("FLY_APP_NAME", "sitewatch-bot"),
    )
