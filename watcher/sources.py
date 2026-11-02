"""Fetch and parse the two data sources.

1. Njuko front API (Ironman's 2027-season registration platform):
   GET https://front-api.njuko.com/edition/url/<slug>
   404 = edition not created yet. Otherwise JSON with status (DRAFT/OPEN),
   registration start time and every price tier with slot counts.

2. ironman.com register page: <body class="registration-state--X"> where X is
   open | opening_soon | sold_out | general_sold_out | closed, plus the
   "Register" button link, which can reveal the Njuko slug early.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import requests

NJUKO_API = "https://front-api.njuko.com/edition/url/{slug}"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 im703-zeroday-watcher"
)
PAGE_STATES = {"open", "opening_soon", "sold_out", "general_sold_out", "closed"}

_STATE_RE = re.compile(r"registration-state--([a-z_]+)")
# Njuko registration links: in.njuko.com/<slug> or white-label in.<region>.ironman.com/<slug>
_REG_LINK_RE = re.compile(
    r"https?://in\.(?:[a-z0-9-]+\.)?(?:njuko\.com|ironman\.com)/([a-z0-9][a-z0-9-]+)"
)


class SourceError(Exception):
    """Fetch or parse failed in a way that needs attention."""


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------- Njuko


@dataclass
class Tier:
    order: int
    base: int
    all_in: int
    limit: int
    reserved: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.reserved, 0)

    @property
    def full(self) -> bool:
        return self.reserved >= self.limit

    @property
    def pct(self) -> int:
        return int(self.reserved * 100 / self.limit) if self.limit else 100


@dataclass
class Competition:
    name: str
    tiers: list[Tier]  # paid tiers only, in price order

    def current_tier(self) -> int | None:
        """Index of the cheapest tier with free slots, None if all full."""
        for i, t in enumerate(self.tiers):
            if not t.full:
                return i
        return None


@dataclass
class Edition:
    slug: str
    status: str  # DRAFT | OPEN | ...
    year: int | None
    name: str
    currency: str
    race_start: dt.datetime | None
    reg_start: dt.datetime | None
    reg_end: dt.datetime | None
    created: dt.datetime | None
    register_url: str
    competitions: list[Competition] = field(default_factory=list)


def parse_edition(data: dict) -> Edition:
    meta = {m.get("key"): m.get("value") for m in data.get("metaData") or []}
    year = meta.get("im_event_year")
    comps: list[Competition] = []
    starts, ends = [], []
    for c in data.get("competitions") or []:
        if c.get("hideOnFront"):
            continue
        name = c.get("reportName") or (c.get("name") or [{}])[0].get("translation", "?")
        tiers = []
        for p in sorted(c.get("prices") or [], key=lambda p: p.get("order", 0)):
            pmeta = {m.get("key"): m.get("value") for m in p.get("metaData") or []}
            if not p.get("enabled") or not p.get("value"):
                continue  # disabled or free (complimentary) tier
            if str(pmeta.get("im_price_type", "")).upper() == "COMPLIMENTARY":
                continue
            limit = p.get("participantLimit")
            if limit is None:
                continue
            tiers.append(
                Tier(
                    order=int(p.get("order", 0)),
                    base=int(p["value"]),
                    all_in=int(pmeta.get("all_in_price") or p["value"]),
                    limit=int(limit),
                    reserved=int(p.get("reservedCount") or 0),
                )
            )
        comps.append(Competition(name=name, tiers=tiers))
        if s := parse_ts(c.get("startDateRegistrations")):
            starts.append(s)
        if e := parse_ts(c.get("endDateRegistrations")):
            ends.append(e)
    domain = data.get("domain") or "njuko.com"
    slug = data.get("url", "")
    return Edition(
        slug=slug,
        status=str(data.get("status", "")).upper(),
        year=int(year) if year and str(year).isdigit() else None,
        name=data.get("reportName") or slug,
        currency=data.get("currency") or "",
        race_start=parse_ts(data.get("startDate")),
        reg_start=min(starts) if starts else None,
        reg_end=max(ends) if ends else None,
        created=parse_ts(data.get("created_at")),
        register_url=f"https://in.{domain}/{slug}",
        competitions=comps,
    )


def fetch_edition(s: requests.Session, slug: str) -> Edition | None:
    """Return the edition, or None if it doesn't exist yet (404)."""
    url = NJUKO_API.format(slug=slug)
    try:
        r = s.get(url, headers={"Accept": "application/json",
                                "Origin": "https://in.njuko.com"}, timeout=30)
    except requests.RequestException as e:
        raise SourceError(f"njuko {slug}: {e}") from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise SourceError(f"njuko {slug}: HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise SourceError(f"njuko {slug}: not JSON") from e
    if not isinstance(data, dict) or "competitions" not in data:
        raise SourceError(f"njuko {slug}: unexpected JSON shape")
    return parse_edition(data)


# ---------------------------------------------------------------- Ironman page


@dataclass
class PageInfo:
    state: str | None  # None for alias pages that don't carry a registration state
    slugs: list[str]   # Njuko slugs linked from the page


def parse_page(html: str, require_state: bool = True) -> PageInfo:
    """Read the registration state and Njuko links from an ironman.com page.

    Alias pages (e.g. a race overview page) may have no state; pass
    require_state=False to only collect their Njuko links.
    """
    body = re.search(r"<body[^>]*>", html)
    m = _STATE_RE.search(body.group(0)) if body else None
    slugs = list(dict.fromkeys(_REG_LINK_RE.findall(html)))
    if not m:
        if require_state:
            raise SourceError("ironman page: no registration-state class on <body>")
        return PageInfo(state=None, slugs=slugs)
    state = m.group(1)
    if state not in PAGE_STATES:
        raise SourceError(f"ironman page: unknown state {state!r}")
    return PageInfo(state=state, slugs=slugs)


def merge_pages(pages: list[PageInfo]) -> PageInfo | None:
    """Main page decides the state (first page with one); links come from all pages."""
    if not pages:
        return None
    state = next((p.state for p in pages if p.state), None)
    slugs = list(dict.fromkeys(s for p in pages for s in p.slugs))
    return PageInfo(state=state, slugs=slugs)


def fetch_page(s: requests.Session, url: str, require_state: bool = True) -> PageInfo:
    """Fetch the register page.

    ironman.com sits behind Cloudflare, which answers HTTP 403 to plain
    Python/curl requests from GitHub's data-center IPs. curl_cffi sends the
    same TLS fingerprint as a real browser and gets through (verified on a
    GitHub runner 2026-11-02). Plain requests stays as a fallback.
    """
    try:
        from curl_cffi import requests as browser
    except ImportError:
        browser = None
    status, text, err = None, "", None
    if browser is not None:
        try:
            r = browser.get(url, impersonate="chrome", timeout=40)
            status, text = r.status_code, r.text
        except Exception as e:
            err = e
    if status != 200:
        try:
            r = s.get(url, timeout=40)
            status, text = r.status_code, r.text
        except requests.RequestException as e:
            raise SourceError(f"ironman page: {err or e}") from e
    if status != 200:
        raise SourceError(f"ironman page: HTTP {status}")
    return parse_page(text, require_state=require_state)
