"""Entry point.

    python -m watcher run                      normal check
    python -m watcher test-notify              test alert to every channel
    python -m watcher status                   print saved state
    python -m watcher stop goa-2027 --reason booked|not-interested
    python -m watcher resume goa-2027
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import sources
from .config import Target, load_targets
from .engine import DONE, Alert, edition_matches, evaluate, fmt_time
from .ics import registration_event
from .notify import Notifier

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "targets.yaml"
STATE = ROOT / "state" / "state.json"
FAIL_ALERT_AFTER = 2          # consecutive failed runs (~1 day at 2 runs/day) before "monitor broken"
HEARTBEAT_EVERY = dt.timedelta(days=7)
OUTBOX_MAX = 50


def load_state(path: Path | None = None) -> dict:
    path = path or STATE
    if path.exists() and path.read_text().strip():
        return json.loads(path.read_text())
    return {}


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def github_output(**kv) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def step_summary(text: str) -> None:
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a") as f:
            f.write(text + "\n")
    print(text)


def track_health(state: dict, key: str, label: str, err: Exception | None,
                 now: dt.datetime) -> list[Alert]:
    h = state.setdefault("health", {}).setdefault(key, {"fails": 0, "alerted": False})
    if err is None:
        recovered = h["alerted"]
        h.update(fails=0, alerted=False, last_error=None)
        if recovered:
            return [Alert(kind="heartbeat", title=f"{label} working again",
                          lines=["Checks are succeeding again."])]
        return []
    h["fails"] += 1
    h["last_error"] = str(err)[:300]
    if h["fails"] >= FAIL_ALERT_AFTER and not h["alerted"]:
        h["alerted"] = True
        return [Alert(kind="error", urgent=True,
                      title=f"Watcher problem: {label}",
                      lines=[f"Failed {h['fails']} runs in a row.",
                             f"Last error: `{h['last_error']}`",
                             "The other source may still work. Check the Actions logs. "
                             "The site layout or API may have changed."])]
    return []


def active_targets(targets: list[Target], state: dict, now: dt.datetime) -> list[Target]:
    tst = state.get("targets", {})
    return [t for t in targets
            if t.active and t.started(t.local_date(now))
            and tst.get(t.id, {}).get("phase") not in DONE
            and not tst.get(t.id, {}).get("stopped")]


STOP_REASONS = {"booked": "you registered", "not-interested": "you are not registering"}


def stopped_alert(t: Target, reason: str) -> Alert:
    return Alert(kind="stopped", channels=["discord"], target_id=t.id, target_name=t.name,
                 title=f"{t.name}: alerts stopped ({STOP_REASONS.get(reason, reason)})",
                 lines=["No more alerts for this race.",
                        "To watch again: reopen its GitHub issue, or run the workflow "
                        "with mode `resume`."])


def resumed_alert(t: Target) -> Alert:
    return Alert(kind="resumed", channels=["discord"], target_id=t.id, target_name=t.name,
                 title=f"{t.name}: watching resumed",
                 lines=["Alerts for this race are back on."])


def apply_issue_controls(t: Target, st: dict, notifier: Notifier,
                         now: dt.datetime) -> list[Alert]:
    """You close the race's issue -> stop. You reopen it -> resume."""
    if st.get("phase") in DONE:
        return []
    info = notifier.issue_info(t.id)
    if not info:
        return []
    stopped = st.get("stopped")
    if info.get("state") == "closed" and not stopped:
        closer = (info.get("closed_by") or {}).get("login", "")
        if closer.endswith("[bot]"):
            return []  # closed by the watcher itself, not by you
        reason = "booked" if info.get("state_reason") == "completed" else "not-interested"
        st["stopped"] = {"reason": reason, "at": now.isoformat(), "via": "issue",
                         "issue_closed": True}
        return [stopped_alert(t, reason)]
    if info.get("state") == "open" and stopped and stopped.get("issue_closed"):
        st.pop("stopped")
        return [resumed_alert(t)]
    return []


def run(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    targets = load_targets(TARGETS)  # module globals so tests can point elsewhere
    state = load_state()
    state.setdefault("version", 1)
    tstates = state.setdefault("targets", {})
    notifier = Notifier(issues=state.setdefault("github_issues", {}))
    sess = sources.session()
    alerts: list[Alert] = []

    # Your stop/resume actions on the race issues come first.
    for t in targets:
        if t.active and t.started(t.local_date(now)):
            st = tstates.setdefault(t.id, {"phase": "waiting", "activated_at": now.isoformat()})
            alerts += apply_issue_controls(t, st, notifier, now)

    for t in active_targets(targets, state, now):
        st = tstates.setdefault(t.id, {"phase": "waiting", "activated_at": now.isoformat()})
        notifier.ensure_issue(t.id, t.name)

        # Main page decides the state; alias pages only add Njuko links.
        pages, page_err = [], None
        for i, url in enumerate(t.page_urls()):
            try:
                pages.append(sources.fetch_page(sess, url, require_state=(i == 0)))
            except sources.SourceError as e:
                if i == 0:
                    page_err = e
                else:
                    print(f"[{t.id}] alias page failed: {url}: {e}")
        page = sources.merge_pages(pages)

        slugs = [st.get("slug")] if st.get("slug") else []
        slugs += t.slug_candidates()
        if page:
            slugs += [s for s in page.slugs if s.startswith(f"{t.year}-")]
        slugs = list(dict.fromkeys(slugs))

        ed, nj_err = None, None
        for slug in slugs:
            try:
                e = sources.fetch_edition(sess, slug)
            except sources.SourceError as x:
                nj_err = x
                continue
            if e and edition_matches(t, e):
                ed = e
                break

        alerts += track_health(state, f"{t.id}:page", f"{t.name} Ironman page", page_err, now)
        alerts += track_health(state, f"{t.id}:njuko", f"{t.name} Njuko API", nj_err, now)
        alerts += evaluate(t, st, ed, page, now)
        print(f"[{t.id}] phase={st['phase']} page={page.state if page else 'ERR'} "
              f"edition={(ed.slug + ':' + ed.status) if ed else 'none'} "
              f"tried={slugs}")

    # Weekly "still alive" message. Also changes state.json, and that commit
    # keeps GitHub from turning off the schedule after 60 quiet days.
    last_hb = state.get("last_heartbeat")
    if not last_hb or now - dt.datetime.fromisoformat(last_hb) >= HEARTBEAT_EVERY:
        state["last_heartbeat"] = now.isoformat()
        lines = []
        for t in targets:
            if not t.active:
                continue
            st = tstates.get(t.id, {})
            if not t.started(t.local_date(now)):
                lines.append(f"**{t.name}**: starts watching {t.watch_from:%d %b %Y}")
                continue
            line = f"**{t.name}**: {st.get('phase', 'not started')}"
            if st.get("stopped"):
                line += f" (stopped: {STOP_REASONS.get(st['stopped']['reason'], '')})"
            elif st.get("ics_for"):
                line += f", opens {fmt_time(dt.datetime.fromisoformat(st['ics_for']), t.tz)}"
            lines.append(line)
        alerts.append(Alert(kind="heartbeat", channels=["discord"],
                            title="Weekly check-in: watcher is running",
                            lines=lines or ["No active targets."]))

    # Send: queued failures from earlier runs first, then new alerts.
    queue = [Alert(**a) for a in state.get("outbox", [])] + alerts
    failed = [a for a in queue if not notifier.send(a)]
    state["outbox"] = [dataclasses.asdict(a) for a in failed][-OUTBOX_MAX:]
    if failed and not notifier.channels():
        print("::warning::No notification channels configured (set secrets).")

    save_state(state)

    remaining = active_targets(targets, state, now)
    pending = [t for t in targets if t.active and not t.started(t.local_date(now))]
    all_done = not remaining and not pending
    github_output(all_done=str(all_done).lower(), alerts=len(alerts))

    summary = [f"### Watcher run {now:%Y-%m-%d %H:%M} UTC", ""]
    for t in targets:
        st = tstates.get(t.id, {})
        status_word = "stopped" if st.get("stopped") else ("active" if t.active else "inactive")
        summary.append(f"- **{t.name}** ({status_word}): "
                       f"phase `{st.get('phase', '-')}`, page `{st.get('page_state', '-')}`, "
                       f"slug `{st.get('slug', '-')}`")
    summary += ["", f"Alerts this run: {len(alerts)}; queued for retry: {len(failed)}"]
    summary += [f"- {line}" for line in notifier.log]
    if all_done:
        summary.append("\nAll active targets are done. The workflow will be disabled.")
    step_summary("\n".join(summary))
    return 0


def test_notify() -> int:
    n = Notifier()
    print("Configured channels:", n.channels() or "NONE")
    now = dt.datetime.now(dt.timezone.utc)
    t = Target(id="test", name="TEST IRONMAN 70.3", race_page="im703-goa", year=2027)
    ed = sources.Edition(slug="2027-ironman-703-goa", status="DRAFT", year=2027, name="test",
                         currency="INR", race_start=None,
                         reg_start=(now + dt.timedelta(days=1)).replace(second=0, microsecond=0),
                         reg_end=None, created=now,
                         register_url="https://in.njuko.com/2027-ironman-703-goa")
    alert = Alert(kind="test", urgent=True, target_id="test", target_name=t.name, url=t.page_url,
                  title="Test alert from im703-zeroday",
                  lines=["If you can read this, alerts work on this channel.",
                         f"The attached test calendar event is at {fmt_time(ed.reg_start, t.tz)}. "
                         "Delete it after checking."],
                  ics=registration_event(t, ed, 0))
    ok = n.send(alert)
    for line in n.log:
        print(line)
    return 0 if ok and n.channels() else 1


def status() -> int:
    print(json.dumps(load_state(), indent=2, ensure_ascii=False))
    return 0


def _find_target(target_id: str) -> Target:
    targets = load_targets(TARGETS)
    for t in targets:
        if t.id == target_id:
            return t
    raise SystemExit(f"unknown target {target_id!r}; known: {[t.id for t in targets]}")


def stop(target_id: str, reason: str, now: dt.datetime | None = None) -> int:
    """Stop alerts for one race (you registered, or changed your mind)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    t = _find_target(target_id)
    state = load_state()
    st = state.setdefault("targets", {}).setdefault(t.id, {"phase": "waiting"})
    if st.get("stopped"):
        print(f"{t.id} is already stopped.")
        return 0
    notifier = Notifier(issues=state.setdefault("github_issues", {}))
    closed = notifier.set_issue_state(
        t.id, open_=False, reason="completed" if reason == "booked" else "not_planned")
    st["stopped"] = {"reason": reason, "at": now.isoformat(), "via": "command",
                     "issue_closed": closed}
    notifier.send(stopped_alert(t, reason))
    save_state(state)
    print(f"Stopped {t.id} ({reason}).", *notifier.log, sep="\n")
    return 0


def resume(target_id: str) -> int:
    t = _find_target(target_id)
    state = load_state()
    st = state.setdefault("targets", {}).setdefault(t.id, {"phase": "waiting"})
    if st.get("phase") in DONE:
        print(f"{t.id} is {st['phase']}; nothing to resume.")
        return 1
    if not st.pop("stopped", None):
        print(f"{t.id} wasn't stopped.")
        return 0
    notifier = Notifier(issues=state.setdefault("github_issues", {}))
    notifier.set_issue_state(t.id, open_=True)
    notifier.send(resumed_alert(t))
    save_state(state)
    print(f"Resumed {t.id}.", *notifier.log, sep="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="watcher")
    p.add_argument("mode", nargs="?", default="run",
                   choices=["run", "test-notify", "status", "stop", "resume"])
    p.add_argument("target", nargs="?", help="target id for stop/resume, e.g. goa-2027")
    p.add_argument("--reason", choices=sorted(STOP_REASONS), default="booked",
                   help="why you're stopping (stop only)")
    args = p.parse_args(argv)
    if args.mode in ("stop", "resume"):
        if not args.target:
            p.error(f"{args.mode} needs a target id, e.g. goa-2027")
        return stop(args.target, args.reason) if args.mode == "stop" else resume(args.target)
    return {"run": run, "test-notify": test_notify, "status": status}[args.mode]()


if __name__ == "__main__":
    sys.exit(main())
