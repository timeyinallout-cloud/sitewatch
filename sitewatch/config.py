from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Site:
    name: str
    base_url: str

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")


def load_sites(path: Path) -> list[Site]:
    data = tomllib.loads(Path(path).read_text())
    return [Site(name=s["name"], base_url=s["base_url"].rstrip("/")) for s in data.get("site", [])]
