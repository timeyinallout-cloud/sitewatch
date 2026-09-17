"""Free text -> a small, closed set of chat commands.

Regex only, no LLM fallback -- unlike Fleetboard's intent.py, sitewatch's
whole command surface is "run a sweep [for a site]", "accept a run [for a
site]", and "status". That's small enough that adding an AI-key dependency
just to parse it would be solving a problem that doesn't exist; the regexes
below plus the chat's buttons already cover every real phrasing.
"""
from __future__ import annotations

import re

_SWEEP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:run\s+)?(?:a\s+)?sweep"
    r"(?:\s+(?:for|on)\s+(\S+)|\s+(\S+))?\s*\.?\s*$", re.I)
_CHECK_RE = re.compile(r"^\s*check\s+(everything|\S+)\s*\.?\s*$", re.I)
_ACCEPT_RE = re.compile(r"^\s*accept(?:\s+(?:run\s+)?(\S+))?(?:\s+for\s+(\S+))?\s*\.?\s*$", re.I)
_STATUS_RE = re.compile(r"^\s*status\s*\??\s*$", re.I)


def parse(text: str) -> dict | None:
    """Returns a command dict, or None if the text doesn't match anything
    this bot understands (the caller shows a hint, it never guesses)."""
    m = _SWEEP_RE.match(text)
    if m:
        return {"action": "sweep", "site": m.group(1) or m.group(2)}

    m = _CHECK_RE.match(text)
    if m:
        site = None if m.group(1).lower() == "everything" else m.group(1)
        return {"action": "sweep", "site": site}

    m = _ACCEPT_RE.match(text)
    if m and m.group(1):
        return {"action": "accept", "run_id": m.group(1), "site": m.group(2)}

    if _STATUS_RE.match(text):
        return {"action": "status"}

    return None
