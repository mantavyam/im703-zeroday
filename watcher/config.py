"""Load watch targets from targets.yaml.

Works for any IRONMAN-brand race listed on ironman.com:
    https://www.ironman.com/races/<race_page>/register

The Njuko slug is guessed from the page name ("im703-goa" + 2027 ->
"2027-ironman-703-goa"). When a race uses a different slug or page, list
it under `aliases` and set `enabled: true`.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

# ironman.com page prefix -> Njuko slug prefix
BRANDS = {"im703": "ironman-703", "im": "ironman", "5150": "5150"}
RACE_PAGE_URL = "https://www.ironman.com/races/{name}/register"
DEFAULT_TIMEZONE = "Asia/Kolkata"

_RACE_NAME_RE = re.compile(r"/races/([a-z0-9][a-z0-9-]*)")
_URL_SLUG_RE = re.compile(r"^https?://[^/]+/([a-z0-9][a-z0-9-]*)")


def page_url(page: str) -> str:
    """'im703-goa' or a full URL -> URL to fetch."""
    page = page.strip()
    if page.startswith(("http://", "https://")):
        return page
    return RACE_PAGE_URL.format(name=page.strip("/"))


def page_name(page: str) -> str | None:
    """'im703-goa' or 'https://www.ironman.com/races/im703-goa/register' -> 'im703-goa'."""
    page = page.strip()
    if not page.startswith(("http://", "https://")):
        return page.strip("/") or None
    m = _RACE_NAME_RE.search(page)
    return m.group(1) if m else None


def default_slug(page: str, year: int) -> str | None:
    """Njuko slug most races use: im703-goa -> {year}-ironman-703-goa."""
    name = page_name(page)
    if not name:
        return None
    prefix, _, place = name.partition("-")
    core = f"{BRANDS[prefix]}-{place}" if prefix in BRANDS and place else name
    return f"{year}-{core}"


@dataclass
class Aliases:
    enabled: bool = False
    pages: list[str] = field(default_factory=list)  # extra ironman.com pages (name or URL)
    slugs: list[str] = field(default_factory=list)  # Njuko slugs, {year} patterns or Njuko URLs


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
    extra_slugs: list[str] = field(default_factory=list)  # older form of aliases.slugs
    timezone: str = DEFAULT_TIMEZONE
    aliases: Aliases = field(default_factory=Aliases)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def page_url(self) -> str:
        return page_url(self.race_page)

    def page_urls(self) -> list[str]:
        """Main page first, then alias pages (when aliases are enabled)."""
        urls = [self.page_url]
        if self.aliases.enabled:
            urls += [page_url(p) for p in self.aliases.pages]
        return list(dict.fromkeys(urls))

    def expand_slug(self, value: str) -> str | None:
        """'{year}-ironman-703-{place}', a plain slug, or a Njuko URL -> slug."""
        value = value.strip()
        if value.startswith(("http://", "https://")):
            m = _URL_SLUG_RE.match(value)
            return m.group(1) if m else None
        name = page_name(self.race_page) or ""
        place = name.partition("-")[2] or name
        return (value.replace("{year}", str(self.year))
                .replace("{place}", place).replace("{page}", name)) or None

    def slug_candidates(self) -> list[str]:
        """Njuko slugs to try, in order."""
        out = [default_slug(self.race_page, self.year)]
        if self.aliases.enabled:
            out += [default_slug(p, self.year) for p in self.aliases.pages]
            out += [self.expand_slug(s) for s in self.aliases.slugs]
        out += [self.expand_slug(s) for s in self.extra_slugs]
        return list(dict.fromkeys(s for s in out if s))

    def tracks(self, competition_name: str) -> bool:
        if not self.competitions:
            return True
        name = competition_name.strip().lower()
        return any(name == c.strip().lower() for c in self.competitions)

    def local_date(self, now: dt.datetime) -> dt.date:
        return now.astimezone(self.tz).date()

    def started(self, today: dt.date) -> bool:
        return self.watch_from is None or today >= self.watch_from


def _aliases(raw) -> Aliases:
    if not raw:
        return Aliases()
    if not isinstance(raw, dict):
        raise ValueError("aliases must be a mapping with enabled/pages/slugs")
    return Aliases(enabled=bool(raw.get("enabled", True)),
                   pages=[str(p) for p in raw.get("pages") or []],
                   slugs=[str(s) for s in raw.get("slugs") or []])


def load_targets(path: str | Path) -> list[Target]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    defaults = raw.get("defaults") or {}
    targets, seen = [], set()
    for item in raw.get("targets", []):
        t = {**defaults, **item}
        wf = t.get("watch_from")
        if isinstance(wf, str):
            wf = dt.date.fromisoformat(wf)
        tz = str(t.get("timezone") or DEFAULT_TIMEZONE)
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"{t.get('id')}: unknown timezone {tz!r} "
                             "(use a name like Europe/Berlin)") from e
        target = Target(
            id=str(t["id"]),
            name=str(t.get("name") or t["id"]),
            race_page=str(t["race_page"]),
            year=int(t["year"]),
            race_months=[int(m) for m in t.get("race_months") or []],
            watch_from=wf,
            active=bool(t.get("active", True)),
            competitions=list(t.get("competitions") or []),
            tier_alert_pct=int(t.get("tier_alert_pct", 80)),
            extra_slugs=list(t.get("extra_slugs") or []),
            timezone=tz,
            aliases=_aliases(t.get("aliases")),
        )
        if target.id in seen:
            raise ValueError(f"duplicate target id: {target.id}")
        seen.add(target.id)
        targets.append(target)
    return targets
