"""Build an .ics calendar event for the registration opening time."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Target
    from .sources import Edition


def _ts(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _esc(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets are folded with CRLF + space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > 74:
            out.append(cur.decode())
            cur = b" " + b
        else:
            cur += b
    out.append(cur.decode())
    return "\r\n".join(out)


def registration_event(target: "Target", ed: "Edition", sequence: int,
                       now: dt.datetime | None = None) -> str:
    """One event at the opening time, with reminders 1 day, 1 hour and 10 min before.

    The UID stays the same per target, so a later invite with a higher
    SEQUENCE updates the same calendar event instead of adding a new one.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    start = ed.reg_start
    end = start + dt.timedelta(minutes=30)
    desc = (f"{target.name} registration opens. Early-bird slots usually sell out "
            f"within ~48 hours.\nRegister: {ed.register_url}\nInfo: {target.page_url}")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//im703-zeroday//registration watcher//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{target.id}-registration-open@im703-zeroday",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{_ts(now)}",
        f"DTSTART:{_ts(start)}",
        f"DTEND:{_ts(end)}",
        f"SUMMARY:{_esc('🏊🚴🏃 ' + target.name + ' registration opens')}",
        f"DESCRIPTION:{_esc(desc)}",
        f"URL:{ed.register_url}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]
    for trigger, label in (("-P1D", "tomorrow"), ("-PT1H", "in 1 hour"),
                           ("-PT10M", "in 10 minutes")):
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                  f"DESCRIPTION:{_esc(target.name + ' registration opens ' + label)}",
                  f"TRIGGER:{trigger}", "END:VALARM"]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
