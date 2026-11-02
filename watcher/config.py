"""Load watch targets from targets.yaml."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Target:
    id: str
    name: str
    race_page: str
    year: int
    race_months: list[int] = field(default_factory=list)
    watch_from: dt.date | None = None
    active: bool = True
    competitions: list[str] = field(default_factory=list)
    tier_alert_pct: int = 80
    extra_slugs: list[str] = field(default_factory=list)

    @property
    def page_url(self) -> str:
        return f"https://www.ironman.com/races/{self.race_page}/register"

    def slug_candidates(self) -> list[str]:
        """Njuko slugs to try. Most races use {year}-ironman-703-{place}."""
        page = self.race_page
        if page.startswith("im703-"):
            core = "ironman-703-" + page[len("im703-"):]
        elif page.startswith("im-"):
            core = "ironman-" + page[len("im-"):]
        else:
            core = page
        out = [f"{self.year}-{core}", *self.extra_slugs]
        return list(dict.fromkeys(out))  # dedupe, keep order

    def tracks(self, competition_name: str) -> bool:
        if not self.competitions:
            return True
        name = competition_name.strip().lower()
        return any(name == c.strip().lower() for c in self.competitions)

    def started(self, today: dt.date) -> bool:
        return self.watch_from is None or today >= self.watch_from


def load_targets(path: str | Path) -> list[Target]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    targets = []
    seen = set()
    for t in raw.get("targets", []):
        wf = t.get("watch_from")
        if isinstance(wf, str):
            wf = dt.date.fromisoformat(wf)
        target = Target(
            id=str(t["id"]),
            name=str(t.get("name") or t["id"]),
            race_page=str(t["race_page"]),
            year=int(t["year"]),
            race_months=[int(m) for m in t.get("race_months", [])],
            watch_from=wf,
            active=bool(t.get("active", True)),
            competitions=list(t.get("competitions", [])),
            tier_alert_pct=int(t.get("tier_alert_pct", 80)),
            extra_slugs=list(t.get("extra_slugs", [])),
        )
        if target.id in seen:
            raise ValueError(f"duplicate target id: {target.id}")
        seen.add(target.id)
        targets.append(target)
    return targets
