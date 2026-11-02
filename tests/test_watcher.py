import datetime as dt
import json
from pathlib import Path

import pytest

from watcher import __main__ as runner
from watcher import notify, sources
from watcher.config import Target, load_targets
from watcher.engine import evaluate
from watcher.ics import registration_event

FX = Path(__file__).parent / "fixtures"
UTC = dt.timezone.utc


def page(name):
    return sources.parse_page((FX / name).read_text(encoding="utf-8"))


def raw_amdavad():
    return json.loads((FX / "njuko_amdavad_open.json").read_text())


def goa_edition(status="DRAFT", reg_start="2027-04-22T04:30:00.000Z", reserved=None):
    """Amdavad's real JSON reshaped into a pretend Goa 2027 edition."""
    d = raw_amdavad()
    d["url"] = "2027-ironman-703-goa"
    d["status"] = status
    d["startDate"] = "2027-10-31T01:00:00.000Z"  # race 31 Oct 2027
    for c in d["competitions"]:
        c["startDateRegistrations"] = reg_start
        c["endDateRegistrations"] = "2027-10-30T00:00:00.000Z"
        if reserved is not None:
            for p in c["prices"]:
                if p["enabled"]:
                    p["reservedCount"] = reserved(p)
    return sources.parse_edition(d)


def goa():
    return Target(id="goa-2027", name="IRONMAN 70.3 Goa 2027", race_page="im703-goa",
                  year=2027, race_months=[10, 11], competitions=["Individual Entry"])


T0 = dt.datetime(2026, 11, 3, 5, 17, tzinfo=UTC)


# ------------------------------------------------------------------ sources


def test_page_states_from_real_pages():
    assert page("page_goa_opening_soon.html").state == "opening_soon"
    assert page("page_goa_opening_soon.html").slugs == []
    am = page("page_amdavad_open.html")
    assert am.state == "open" and am.slugs == ["2027-ironman-703-amdavad"]
    mi = page("page_michigan_soon_with_link.html")
    assert mi.state == "opening_soon" and "2027-ironman-703-michigan" in mi.slugs
    assert page("page_alghero_sold_out.html").state == "sold_out"


def test_page_without_state_is_an_error():
    with pytest.raises(sources.SourceError):
        sources.parse_page("<html><body class='x'>hi</body></html>")


def test_parse_real_amdavad_edition():
    ed = sources.parse_edition(raw_amdavad())
    assert ed.status == "OPEN" and ed.year == 2027 and ed.currency == "INR"
    assert ed.reg_start == dt.datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
    assert ed.register_url == "https://in.ind1.ironman.com/2027-ironman-703-amdavad"
    ind = next(c for c in ed.competitions if c.name == "Individual Entry")
    assert [t.all_in for t in ind.tiers] == [42900, 46200, 49500]  # complimentary dropped
    assert ind.current_tier() == 0 and ind.tiers[0].remaining == 3


def test_parse_real_draft_edition():
    d = json.loads((FX / "njuko_belgrade_draft.json").read_text())
    assert sources.parse_edition(d).status == "DRAFT"


def test_slug_candidates():
    assert goa().slug_candidates() == ["2027-ironman-703-goa"]
    t = Target(id="x", name="x", race_page="im-new-zealand", year=2028, extra_slugs=["a"])
    assert t.slug_candidates() == ["2028-ironman-new-zealand", "a"]


def test_targets_yaml_loads():
    ts = load_targets(Path(__file__).parent.parent / "targets.yaml")
    g = next(t for t in ts if t.id == "goa-2027")
    assert g.active and g.year == 2027 and g.watch_from == dt.date(2026, 11, 2)


# ------------------------------------------------------------------ engine lifecycle


def test_full_lifecycle():
    t, st = goa(), {"phase": "waiting"}
    soon = page("page_goa_opening_soon.html")

    # 1. nothing on Njuko yet
    assert evaluate(t, st, None, soon, T0) == [] and st["phase"] == "waiting"

    # 2. DRAFT edition appears with a future opening time -> announced + ics
    a = evaluate(t, st, goa_edition(), soon, T0)
    assert [x.kind for x in a] == ["announced"]
    assert a[0].ics and "DTSTART:20270422T043000Z" in a[0].ics and st["ics_seq"] == 0

    # 3. same data again -> silent
    assert evaluate(t, st, goa_edition(), soon, T0 + dt.timedelta(days=1)) == []

    # 4. opening time moved -> new invite, same UID, higher SEQUENCE
    a = evaluate(t, st, goa_edition(reg_start="2027-04-23T04:30:00.000Z"), soon, T0)
    assert [x.kind for x in a] == ["open_time"] and "SEQUENCE:1" in a[0].ics

    # 5. the day before -> reminder
    day_before = dt.datetime(2027, 4, 22, 5, 17, tzinfo=UTC)
    a = evaluate(t, st, goa_edition(reg_start="2027-04-23T04:30:00.000Z"), soon, day_before)
    assert [x.kind for x in a] == ["reminder"] and "23 h" in a[0].title

    # 6. opens -> urgent open alert with prices
    opened = dt.datetime(2027, 4, 23, 5, 17, tzinfo=UTC)
    ed = goa_edition("OPEN", "2027-04-23T04:30:00.000Z", reserved=lambda p: 10)
    a = evaluate(t, st, ed, soon, opened)
    assert [x.kind for x in a] == ["open"] and a[0].urgent
    assert any("₹42,900" in line for line in a[0].lines)

    # 7. early bird 90% full -> tier_low (Discord only)
    ed = goa_edition("OPEN", "2027-04-23T04:30:00.000Z",
                     reserved=lambda p: int(p["participantLimit"] * 0.9) if p["order"] == 0 else 0)
    a = evaluate(t, st, ed, soon, opened)
    assert [x.kind for x in a] == ["tier_low"] and a[0].urgent

    # 8. early bird fills -> tier_change to tier 2 price
    ed = goa_edition("OPEN", "2027-04-23T04:30:00.000Z",
                     reserved=lambda p: p["participantLimit"] if p["order"] == 0 else 0)
    a = evaluate(t, st, ed, soon, opened)
    assert [x.kind for x in a] == ["tier_change"] and "₹46,200" in a[0].lines[0]

    # 9. everything full -> sold_out, done
    ed = goa_edition("OPEN", "2027-04-23T04:30:00.000Z", reserved=lambda p: p["participantLimit"])
    a = evaluate(t, st, ed, soon, opened)
    assert [x.kind for x in a] == ["sold_out"] and st["phase"] == "sold_out"


def test_stale_sold_out_page_is_ignored_before_open():
    t, st = goa(), {"phase": "waiting"}
    assert evaluate(t, st, None, page("page_alghero_sold_out.html"), T0) == []
    assert st["phase"] == "waiting"


def test_page_open_without_edition_warns_once():
    t, st = goa(), {"phase": "waiting"}
    open_page = sources.PageInfo(state="open", slugs=[])
    assert [x.kind for x in evaluate(t, st, None, open_page, T0)] == ["page_open_unconfirmed"]
    assert evaluate(t, st, None, open_page, T0) == []


def test_page_open_with_target_year_link_counts_as_open():
    t, st = goa(), {"phase": "waiting"}
    p = sources.PageInfo(state="open", slugs=["2027-ironman-703-goa"])
    assert [x.kind for x in evaluate(t, st, None, p, T0)] == ["open"]


def test_no_warning_opening_goes_straight_to_open():
    t, st = goa(), {"phase": "waiting"}
    ed = goa_edition("OPEN", "2026-11-01T04:30:00.000Z", reserved=lambda p: 0)
    assert [x.kind for x in evaluate(t, st, ed, None, T0)] == ["open"]


def test_activated_after_sell_out_sends_no_register_now():
    t, st = goa(), {"phase": "waiting"}
    ed = goa_edition("OPEN", "2026-11-01T04:30:00.000Z", reserved=lambda p: p["participantLimit"])
    assert [x.kind for x in evaluate(t, st, ed, None, T0)] == ["sold_out"]


def test_wrong_month_is_flagged():
    t = goa()
    t.race_months = [3]
    a = evaluate(t, {"phase": "waiting"}, goa_edition(), None, T0)
    assert any("outside expected months" in line for line in a[0].lines)


# ------------------------------------------------------------------ ics + notify


def test_ics_is_valid_shape():
    text = registration_event(goa(), goa_edition(), 2, now=T0)
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and text.endswith("END:VCALENDAR\r\n")
    assert all(len(line.encode()) <= 75 for line in lines)
    assert "SEQUENCE:2" in text and text.count("BEGIN:VALARM") == 3


def test_gmail_message_has_calendar(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, m, from_addr=None, to_addrs=None): sent["msg"] = m

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    n = notify.Notifier({"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "abcd efgh"})
    alert = evaluate(goa(), {"phase": "waiting"}, goa_edition(), None, T0)[0]
    assert n.send(alert)
    msg = sent["msg"]
    assert sent["login"] == ("me@gmail.com", "abcdefgh")
    types = [p.get_content_type() for p in msg.walk()]
    assert types.count("text/calendar") == 2  # inline part + .ics attachment
    assert any(p.get_filename() == "goa-2027-registration.ics" for p in msg.walk())


def test_discord_mentions_only_on_urgent(monkeypatch):
    posts = []

    class R:
        status_code = 204
        def raise_for_status(self): pass

    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: posts.append(json) or R())
    n = notify.Notifier({"DISCORD_WEBHOOK_URL": "https://x", "DISCORD_USER_ID": "42"})
    alerts = evaluate(goa(), {"phase": "waiting"}, goa_edition(), None, T0)
    assert n.send(alerts[0])
    assert posts[0]["content"] == "<@42>" and posts[0]["allowed_mentions"] == {"users": ["42"]}


# ------------------------------------------------------------------ runner


def test_run_end_to_end(tmp_path, monkeypatch):
    (tmp_path / "targets.yaml").write_text(
        "targets:\n  - id: goa-2027\n    name: Goa\n    race_page: im703-goa\n"
        "    year: 2027\n    race_months: [10, 11]\n    competitions: ['Individual Entry']\n")
    monkeypatch.setattr(runner, "TARGETS", tmp_path / "targets.yaml")
    monkeypatch.setattr(runner, "STATE", tmp_path / "state.json")
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("DRY_RUN", "1")

    world = {"page": page("page_goa_opening_soon.html"), "ed": None, "tried": []}
    monkeypatch.setattr(sources, "fetch_page", lambda s, url: world["page"])

    def fake_edition(s, slug):
        world["tried"].append(slug)
        return world["ed"] if slug == "2027-ironman-703-goa" else None

    monkeypatch.setattr(sources, "fetch_edition", fake_edition)

    runner.run(T0)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["targets"]["goa-2027"]["phase"] == "waiting"
    assert "2027-ironman-703-goa" in world["tried"]
    assert "all_done=false" in out.read_text()

    world["ed"] = goa_edition("OPEN", "2026-11-01T04:30:00.000Z",
                              reserved=lambda p: p["participantLimit"])
    runner.run(T0 + dt.timedelta(days=1))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["targets"]["goa-2027"]["phase"] == "sold_out"
    assert "all_done=true" in out.read_text()

    # Done targets aren't fetched again.
    world["tried"].clear()
    runner.run(T0 + dt.timedelta(days=2))
    assert world["tried"] == []


def test_failures_alert_after_two_runs_then_recover(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "TARGETS", Path(__file__).parent.parent / "targets.yaml")
    monkeypatch.setattr(runner, "STATE", tmp_path / "state.json")
    monkeypatch.setenv("DRY_RUN", "1")
    sent = []
    orig = notify.Notifier.send
    monkeypatch.setattr(notify.Notifier, "send", lambda self, a: sent.append(a.kind) or orig(self, a))

    def boom(s, url):
        raise sources.SourceError("layout changed")

    monkeypatch.setattr(sources, "fetch_page", boom)
    monkeypatch.setattr(sources, "fetch_edition", lambda s, slug: None)
    runner.run(T0)
    assert "error" not in sent
    runner.run(T0 + dt.timedelta(days=1))
    assert sent.count("error") == 1
    monkeypatch.setattr(sources, "fetch_page", lambda s, url: page("page_goa_opening_soon.html"))
    sent.clear()
    runner.run(T0 + dt.timedelta(days=2))
    assert sent == ["heartbeat"]  # "working again"


class FakeResp:
    def __init__(self, code=201, data=None):
        self.status_code, self._data = code, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_github_issue_per_race_with_mention_then_closed(monkeypatch):
    calls = []

    def post(url, headers, timeout, json):
        calls.append(("POST", url, json))
        return FakeResp(201, {"number": 7})

    def patch(url, headers, timeout, json):
        calls.append(("PATCH", url, json))
        return FakeResp(200)

    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setattr(notify.requests, "patch", patch)
    issues = {}
    n = notify.Notifier({"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "me/repo",
                         "NOTIFY_GITHUB_USER": "@me"}, issues=issues)
    t, st = goa(), {"phase": "waiting"}

    n.send(evaluate(t, st, goa_edition(), None, T0)[0])          # announced -> new issue
    assert calls[0][1] == "https://api.github.com/repos/me/repo/issues"
    assert calls[0][2]["title"] == "IRONMAN 70.3 Goa 2027: registration watch"
    assert "cc @me" in calls[0][2]["body"] and issues == {"goa-2027": 7}

    st["phase"] = "open"
    full = goa_edition("OPEN", "2026-11-01T04:30:00.000Z", reserved=lambda p: p["participantLimit"])
    n.send(evaluate(t, st, full, None, T0)[0])                     # sold out -> comment + close
    assert calls[1][1].endswith("/issues/7/comments")
    assert calls[2] == ("PATCH", "https://api.github.com/repos/me/repo/issues/7",
                        {"state": "closed", "state_reason": "completed"})


def test_github_recreates_deleted_issue(monkeypatch):
    urls = []

    def post(url, headers, timeout, json):
        urls.append(url)
        return FakeResp(404) if url.endswith("/comments") else FakeResp(201, {"number": 9})

    monkeypatch.setattr(notify.requests, "post", post)
    issues = {"goa-2027": 3}
    n = notify.Notifier({"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "me/repo"}, issues=issues)
    assert n.send(evaluate(goa(), {"phase": "waiting"}, goa_edition(), None, T0)[0])
    assert urls[-1].endswith("/issues") and issues["goa-2027"] == 9


def test_every_alert_goes_to_every_channel(monkeypatch):
    sent = []
    n = notify.Notifier({"DISCORD_WEBHOOK_URL": "x", "GMAIL_ADDRESS": "a@gmail.com",
                         "GMAIL_APP_PASSWORD": "p", "GITHUB_TOKEN": "t",
                         "GITHUB_REPOSITORY": "me/repo"})
    for ch in ("_discord", "_gmail", "_github"):
        monkeypatch.setattr(n, ch, lambda a, ch=ch: sent.append((ch, a.kind)))
    t, st = goa(), {"phase": "open", "tiers": {"Individual Entry": 0}}
    ed = goa_edition("OPEN", "2026-11-01T04:30:00.000Z",
                     reserved=lambda p: int(p["participantLimit"] * 0.9) if p["order"] == 0 else 0)
    alert = evaluate(t, st, ed, None, T0)[0]
    assert alert.kind == "tier_low" and n.send(alert)
    assert sorted(sent) == [("_discord", "tier_low"), ("_github", "tier_low"), ("_gmail", "tier_low")]


# ------------------------------------------------------------------ stop / resume


class FakeGitHub:
    """Tiny in-memory stand-in for the GitHub issues API."""

    def __init__(self):
        self.issues, self.comments = {}, []

    def __call__(self, _notifier, method, path, **payload):
        import re
        if method == "POST" and path == "/issues":
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "state": "open", "title": payload["title"],
                              "body": payload["body"], "closed_by": None, "state_reason": None}
            return FakeResp(201, {"number": n})
        m = re.match(r"/issues/(\d+)(/comments)?$", path)
        n = int(m.group(1))
        if m.group(2):
            self.comments.append((n, payload["body"]))
            return FakeResp(201)
        if method == "GET":
            return FakeResp(200, self.issues[n])
        self.issues[n].update(state=payload["state"], state_reason=payload.get("state_reason"),
                              closed_by={"login": "github-actions[bot]"}
                              if payload["state"] == "closed" else None)
        return FakeResp(200)

    def user_closes(self, n, reason):
        self.issues[n].update(state="closed", state_reason=reason, closed_by={"login": "me"})

    def user_reopens(self, n):
        self.issues[n].update(state="open", state_reason="reopened", closed_by=None)


@pytest.fixture
def gh_world(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "TARGETS", Path(__file__).parent.parent / "targets.yaml")
    monkeypatch.setattr(runner, "STATE", tmp_path / "state.json")
    for k in ("DRY_RUN", "DISCORD_WEBHOOK_URL", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    gh = FakeGitHub()
    monkeypatch.setattr(notify.Notifier, "_gh",
                        lambda self, method, path, **kw: gh(self, method, path, **kw))
    fetched = []
    monkeypatch.setattr(sources, "fetch_page",
                        lambda s, url: fetched.append(url) or page("page_goa_opening_soon.html"))
    monkeypatch.setattr(sources, "fetch_edition", lambda s, slug: None)
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return gh, fetched, out


def test_issue_opened_quietly_at_start(gh_world):
    gh, _, _ = gh_world
    runner.run(T0)
    assert gh.issues[1]["title"] == "IRONMAN 70.3 Goa 2027: registration watch"
    assert "Close this issue as **Completed**" in gh.issues[1]["body"]
    assert "cc @" not in gh.issues[1]["body"]       # no mention, no email spam
    assert gh.comments == []                         # weekly check-in is Discord-only


def test_close_issue_stops_and_reopen_resumes(gh_world):
    gh, fetched, out = gh_world
    runner.run(T0)
    gh.user_closes(1, "completed")
    fetched.clear()
    runner.run(T0 + dt.timedelta(hours=12))
    state = json.loads(runner.STATE.read_text())
    assert state["targets"]["goa-2027"]["stopped"]["reason"] == "booked"
    assert fetched == []                             # no more checks for this race
    assert "all_done=true" in out.read_text()        # only active race -> workflow turns off

    gh.user_reopens(1)
    runner.run(T0 + dt.timedelta(hours=24))
    state = json.loads(runner.STATE.read_text())
    assert "stopped" not in state["targets"]["goa-2027"] and fetched


def test_close_as_not_planned_means_not_interested(gh_world):
    gh, _, _ = gh_world
    runner.run(T0)
    gh.user_closes(1, "not_planned")
    runner.run(T0 + dt.timedelta(hours=12))
    state = json.loads(runner.STATE.read_text())
    assert state["targets"]["goa-2027"]["stopped"]["reason"] == "not-interested"


def test_bot_closing_issue_does_not_stop(gh_world):
    gh, _, _ = gh_world
    runner.run(T0)
    gh.issues[1].update(state="closed", closed_by={"login": "github-actions[bot]"})
    runner.run(T0 + dt.timedelta(hours=12))
    assert "stopped" not in json.loads(runner.STATE.read_text())["targets"]["goa-2027"]


def test_stop_and_resume_commands(gh_world):
    gh, fetched, _ = gh_world
    runner.run(T0)
    assert runner.main(["stop", "goa-2027", "--reason", "not-interested"]) == 0
    assert gh.issues[1]["state"] == "closed" and gh.issues[1]["state_reason"] == "not_planned"
    fetched.clear()
    runner.run(T0 + dt.timedelta(hours=12))
    assert fetched == []
    assert runner.main(["resume", "goa-2027"]) == 0
    assert gh.issues[1]["state"] == "open"
    runner.run(T0 + dt.timedelta(hours=24))
    assert fetched


def test_unknown_target_is_rejected(gh_world):
    with pytest.raises(SystemExit):
        runner.main(["stop", "nope-2030"])


def test_discord_only_alert_skips_other_channels(monkeypatch):
    sent = []
    n = notify.Notifier({"DISCORD_WEBHOOK_URL": "x", "GMAIL_ADDRESS": "a@gmail.com",
                         "GMAIL_APP_PASSWORD": "p", "GITHUB_TOKEN": "t",
                         "GITHUB_REPOSITORY": "me/repo"})
    for ch in ("_discord", "_gmail", "_github"):
        monkeypatch.setattr(n, ch, lambda a, ch=ch: sent.append(ch))
    from watcher.engine import Alert
    assert n.send(Alert(kind="heartbeat", title="hb", channels=["discord"]))
    assert sent == ["_discord"]
    # No Discord configured -> nothing to send, and not queued for retry.
    n2 = notify.Notifier({"GMAIL_ADDRESS": "a@gmail.com", "GMAIL_APP_PASSWORD": "p"})
    assert n2.send(Alert(kind="heartbeat", title="hb", channels=["discord"]))


def test_subscriber_list_parsing():
    assert notify.parse_subscribers("a@x.com, B@y.org;\n c@z.in  a@X.com bad-address") == \
        ["a@x.com", "B@y.org", "c@z.in"]
    assert notify.parse_subscribers("") == []


def test_email_goes_to_me_plus_friends_as_bcc(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, u, p): pass
        def send_message(self, m, from_addr=None, to_addrs=None):
            sent.update(msg=m, to=to_addrs)

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    alert = evaluate(goa(), {"phase": "waiting"}, goa_edition(), None, T0)[0]

    n = notify.Notifier({"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "p",
                         "SUBSCRIBER_LIST": "f1@gmail.com,\nf2@yahoo.com, me@gmail.com"})
    assert n.send(alert)
    assert sent["to"] == ["me@gmail.com", "f1@gmail.com", "f2@yahoo.com"]
    assert sent["msg"]["To"] == "me@gmail.com"          # friends not visible in headers
    assert "f1@gmail.com" not in str(sent["msg"])

    n = notify.Notifier({"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "p"})
    assert n.send(alert) and sent["to"] == ["me@gmail.com"]   # empty list -> just me
