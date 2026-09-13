from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sitewatch.runner import SiteReport


@dataclass
class HistoryRecord:
    run_id: str
    timestamp: str
    site: str
    pages: int
    broken: int
    slow: int
    visual_regressions: int
    render_failures: int

    @property
    def issue_count(self) -> int:
        return self.broken + self.slow + self.visual_regressions + self.render_failures


def append_run(history_path: Path, run_id: str, site_reports: list[SiteReport]) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as f:
        for r in site_reports:
            record = HistoryRecord(
                run_id=run_id,
                timestamp=timestamp,
                site=r.site.slug,
                pages=len(r.crawl.pages),
                broken=len(r.crawl.broken_links) + len(r.crawl.broken_assets),
                slow=len(r.crawl.slow_pages),
                visual_regressions=len(r.visual_regressions),
                render_failures=len(r.render_failures),
            )
            f.write(json.dumps(asdict(record)) + "\n")


def load_history(history_path: Path) -> list[HistoryRecord]:
    if not history_path.exists():
        return []
    records = []
    for line in history_path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(HistoryRecord(**json.loads(line)))
    return records


def history_by_site(records: list[HistoryRecord]) -> dict[str, list[HistoryRecord]]:
    by_site: dict[str, list[HistoryRecord]] = {}
    for r in records:
        by_site.setdefault(r.site, []).append(r)
    for site_records in by_site.values():
        site_records.sort(key=lambda r: r.timestamp)
    return by_site
