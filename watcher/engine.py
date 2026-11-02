"""Turn one run's observations into phase changes and alerts.

Phases only move forward:
    waiting   -> Njuko edition not created yet
    announced -> edition exists (DRAFT, or OPEN with a future start time)
    open      -> registration open now
    sold_out  -> every tracked entry type has no paid slots left   (done)
    closed    -> registration end date passed                      (done)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .config import Target
from .ics import registration_event
from .sources import Edition, PageInfo

IST = ZoneInfo("Asia/Kolkata")
RANK = {"waiting": 0, "announced": 1, "open": 2, "sold_out": 3, "closed": 3}
DONE = {"sold_out", "closed"}
# Runs every 12 h; remind once when opening is within ~a day.
REMINDER_WINDOW = dt.timedelta(hours=26)


@dataclass
class Alert:
    kind: str
    title: str
    lines: list[str] = field(default_factory=list)
    url: str | None = None
    urgent: bool = False      # @mention on Discord
    ics: str | None = None    # calendar attachment (email)
    target_id: str = ""
    target_name: str = ""
    channels: list[str] | None = None  # None = every channel; e.g. ["discord"]


def fmt_time(t: dt.datetime | None) -> str:
    if t is None:
        return "unknown"
    return t.astimezone(IST).strftime("%a %d %b %Y, %H:%M IST")


def fmt_money(amount: int, currency: str) -> str:
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AUD": "A$"}.get(currency)
    return f"{sym}{amount:,}" if sym else f"{amount:,} {currency}"


def tier_lines(target: Target, ed: Edition) -> list[str]:
    out = []
    for c in ed.competitions:
        if not target.tracks(c.name):
            continue
        i = c.current_tier()
        if i is None:
            out.append(f"**{c.name}**: all paid tiers full")
            continue
        t = c.tiers[i]
        nxt = c.tiers[i + 1] if i + 1 < len(c.tiers) else None
        line = (f"**{c.name}**: tier {i + 1}/{len(c.tiers)} "
                f"{fmt_money(t.all_in, ed.currency)} all-in, "
                f"{t.remaining}/{t.limit} left ({t.pct}% full)")
        if nxt:
            line += f"; next tier {fmt_money(nxt.all_in, ed.currency)}"
        out.append(line)
    return out or ["(no tracked entry types found; check `competitions` in targets.yaml)"]


def tracked_all_full(target: Target, ed: Edition) -> bool:
    tracked = [c for c in ed.competitions if target.tracks(c.name) and c.tiers]
    return bool(tracked) and all(c.current_tier() is None for c in tracked)


def edition_matches(target: Target, ed: Edition) -> bool:
    if ed.year is not None:
        return ed.year == target.year
    return ed.slug.startswith(f"{target.year}-")


def month_warning(target: Target, ed: Edition | None) -> list[str]:
    if not ed or not ed.race_start or not target.race_months:
        return []
    m = ed.race_start.astimezone(IST).month
    if m in target.race_months:
        return []
    return [f"⚠️ Race date {fmt_time(ed.race_start)} is outside expected months "
            f"{target.race_months}. Double-check this is the right edition."]


def evaluate(target: Target, st: dict, ed: Edition | None, page: PageInfo | None,
             now: dt.datetime) -> list[Alert]:
    """Update target state `st` in place and return alerts to send."""
    alerts: list[Alert] = []
    prev = st.get("phase", "waiting")
    year_prefix = f"{target.year}-"
    page_confirmed = bool(page and any(s.startswith(year_prefix) for s in page.slugs))
    reg_url = ed.register_url if ed else target.page_url

    if ed:
        st["slug"] = ed.slug
        st["register_url"] = ed.register_url

    # ---- what phase does this run's data show?
    observed = "waiting"
    if ed:
        observed = "announced"
        if ed.status == "OPEN" and (ed.reg_start is None or now >= ed.reg_start):
            observed = "open"
        if observed == "open" and tracked_all_full(target, ed):
            observed = "sold_out"
        if ed.reg_end and now > ed.reg_end:
            observed = "closed"
    if page:
        if page.state == "opening_soon" and page_confirmed:
            observed = max(observed, "announced", key=RANK.get)
        if page.state == "open" and ed is None and page_confirmed:
            observed = max(observed, "open", key=RANK.get)
        # The page may still show last year's state, so only trust
        # sold-out/closed after we've seen this edition open.
        if RANK[max(prev, observed, key=RANK.get)] >= RANK["open"]:
            if page.state in ("sold_out", "general_sold_out"):
                observed = max(observed, "sold_out", key=RANK.get)
            elif page.state == "closed":
                observed = max(observed, "closed", key=RANK.get)
        # Page says open but we can't tie it to the target year: warn once.
        if (page.state == "open" and ed is None and not page_confirmed
                and prev == "waiting" and not st.get("unconfirmed_open_alerted")):
            st["unconfirmed_open_alerted"] = True
            alerts.append(Alert(
                kind="page_open_unconfirmed", urgent=True,
                title=f"{target.name}: Ironman page says registration OPEN (check now)",
                lines=["The register page switched to open, but no Njuko edition "
                       f"for {target.year} was found yet. It may be this edition.",
                       f"Page: {target.page_url}"],
                url=target.page_url))

    new = max(prev, observed, key=RANK.get)
    st["phase"] = new
    st["page_state"] = page.state if page else st.get("page_state")

    # ---- calendar invite for a known future opening time
    ics_alert_lines = []
    ics_text = None
    if ed and ed.reg_start and ed.reg_start > now and new == "announced":
        key = ed.reg_start.isoformat()
        if st.get("ics_for") != key:
            changed = st.get("ics_for") is not None
            st["ics_seq"] = st.get("ics_seq", -1) + 1
            st["ics_for"] = key
            ics_text = registration_event(target, ed, st["ics_seq"])
            ics_alert_lines.append(
                f"{'🔁 Opening time CHANGED' if changed else '📅 Opening time'}: "
                f"**{fmt_time(ed.reg_start)}**. Calendar invite attached in email.")

    # ---- phase transitions
    if new != prev and new == "announced":
        lines = []
        if ed:
            lines.append(f"Njuko edition `{ed.slug}` created (status {ed.status}).")
            lines.append(f"Race day: {fmt_time(ed.race_start)}")
            lines += ics_alert_lines or ["Opening time not published yet; "
                                         "you'll get another alert when it is."]
        else:
            lines.append(f"Ironman page links to a {target.year} registration: "
                         f"{', '.join(page.slugs if page else [])}")
        lines += month_warning(target, ed)
        alerts.append(Alert(kind="announced", urgent=True, ics=ics_text, url=reg_url,
                            title=f"{target.name}: registration ANNOUNCED", lines=lines))
        ics_text, ics_alert_lines = None, []

    if ics_text:  # opening time set/changed later
        alerts.append(Alert(kind="open_time", urgent=True, ics=ics_text, url=reg_url,
                            title=f"{target.name}: registration opens {fmt_time(ed.reg_start)}",
                            lines=ics_alert_lines + month_warning(target, ed)))

    # ---- "opens before the next run" reminder (calendar alarms are the backup)
    if (new == "announced" and ed and ed.reg_start and
            now < ed.reg_start <= now + REMINDER_WINDOW and
            st.get("reminded_for") != ed.reg_start.isoformat()):
        st["reminded_for"] = ed.reg_start.isoformat()
        left = ed.reg_start - now
        hours, mins = divmod(int(left.total_seconds() // 60), 60)
        when = f"{hours} h {mins} min" if hours else f"{mins} min"
        alerts.append(Alert(kind="reminder", urgent=True, url=reg_url,
                            title=f"{target.name}: registration opens in ~{when}",
                            lines=[f"Opens {fmt_time(ed.reg_start)}.",
                                   "Be logged in to your IRONMAN account and ready to pay."]))

    if RANK[new] >= RANK["open"] and RANK[prev] < RANK["open"] and new not in DONE:
        st["opened_at"] = st.get("opened_at") or now.isoformat()
        lines = ["🚨 Register now. Early-bird slots usually go within ~48 hours."]
        if ed:
            lines += tier_lines(target, ed)
        lines += month_warning(target, ed)
        alerts.append(Alert(kind="open", urgent=True, url=reg_url,
                            title=f"{target.name}: registration is OPEN", lines=lines))
        if ed:  # baseline so the first tier change is relative to opening
            for c in ed.competitions:
                if target.tracks(c.name):
                    st.setdefault("tiers", {})[c.name] = c.current_tier()
                    i = c.current_tier()
                    if i is not None and c.tiers[i].pct >= target.tier_alert_pct:
                        st.setdefault("tier_low", {})[c.name] = i

    # ---- tier tracking while open
    elif new == "open" and ed:
        tiers = st.setdefault("tiers", {})
        low = st.setdefault("tier_low", {})
        for c in ed.competitions:
            if not target.tracks(c.name):
                continue
            cur = c.current_tier()
            before = tiers.get(c.name, "unset")
            tiers[c.name] = cur
            if before != "unset" and cur != before:
                if cur is None:
                    msg = f"**{c.name}**: last paid tier just filled."
                else:
                    t = c.tiers[cur]
                    msg = (f"**{c.name}**: now tier {cur + 1}/{len(c.tiers)} at "
                           f"{fmt_money(t.all_in, ed.currency)} all-in ({t.remaining} left).")
                alerts.append(Alert(kind="tier_change", urgent=True, url=reg_url,
                                    title=f"{target.name}: price tier changed",
                                    lines=[msg]))
            if cur is not None and c.tiers[cur].pct >= target.tier_alert_pct \
                    and low.get(c.name) != cur:
                low[c.name] = cur
                t = c.tiers[cur]
                alerts.append(Alert(kind="tier_low", urgent=True, url=reg_url,
                                    title=f"{target.name}: current tier {t.pct}% full",
                                    lines=[f"**{c.name}**: only {t.remaining}/{t.limit} left at "
                                           f"{fmt_money(t.all_in, ed.currency)} before the "
                                           "price goes up."]))

    if new in DONE and prev not in DONE:
        st["done_at"] = now.isoformat()
        why = "sold out" if new == "sold_out" else "closed"
        alerts.append(Alert(kind=new, url=reg_url,
                            title=f"{target.name}: registration {why}. Watching stopped.",
                            lines=[f"All tracked entry types are {why}. "
                                   "This target is done and won't be checked again."]))

    for a in alerts:
        a.target_id = target.id
        a.target_name = target.name
    return alerts
