from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

# Below this, treat two screenshots as "the same page" (anti-aliasing jitter,
# a live odds price ticking over, a relative timestamp string) rather than a
# real visual regression worth flagging.
DIFF_THRESHOLD_PCT = 1.0


@dataclass
class DiffResult:
    is_new: bool
    changed_pct: float | None  # None when is_new
    diff_image_path: Path | None = None


def compare(baseline_path: Path | None, current_path: Path, diff_out_path: Path) -> DiffResult:
    if baseline_path is None or not baseline_path.exists():
        return DiffResult(is_new=True, changed_pct=None)

    baseline = Image.open(baseline_path).convert("RGB")
    current = Image.open(current_path).convert("RGB")

    # Pages legitimately grow/shrink (new content, a longer table). Pad the
    # shorter image rather than crop the taller one, so real added content
    # at the bottom shows up as a diff instead of being silently truncated.
    w = max(baseline.width, current.width)
    h = max(baseline.height, current.height)
    if baseline.size != (w, h):
        padded = Image.new("RGB", (w, h), "white")
        padded.paste(baseline, (0, 0))
        baseline = padded
    if current.size != (w, h):
        padded = Image.new("RGB", (w, h), "white")
        padded.paste(current, (0, 0))
        current = padded

    delta = ImageChops.difference(baseline, current)
    bbox = delta.getbbox()
    if bbox is None:
        return DiffResult(is_new=False, changed_pct=0.0)

    mask = delta.convert("L").point(lambda p: 255 if p > 25 else 0)
    changed_pixels = mask.histogram()[255]
    changed_pct = 100.0 * changed_pixels / (w * h)

    diff_path = None
    if changed_pct > DIFF_THRESHOLD_PCT:
        highlight = current.copy()
        red = Image.new("RGB", (w, h), (220, 40, 40))
        highlight.paste(red, (0, 0), mask)
        diff_out_path.parent.mkdir(parents=True, exist_ok=True)
        highlight.save(diff_out_path)
        diff_path = diff_out_path

    return DiffResult(is_new=False, changed_pct=changed_pct, diff_image_path=diff_path)
