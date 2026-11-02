"""Send every alert to Discord, Gmail and a GitHub issue.

Discord: webhook message, @mentions you on urgent alerts.
Gmail:   SMTP email; announced/opening-time alerts carry an .ics calendar invite.
GitHub:  one issue per race; each alert is a comment that @mentions you, so
         GitHub sends its own notification email + mobile push. The issue
         closes when the race is sold out/closed.

Environment variables (GitHub Actions secrets):
    DISCORD_WEBHOOK_URL   Discord channel webhook URL
    DISCORD_USER_ID       your Discord user ID, to @mention you on urgent alerts (optional)
    GMAIL_ADDRESS         Gmail account that sends the mail
    GMAIL_APP_PASSWORD    16-char Google app password for that account
    SUBSCRIBER_LIST       extra people to email, separated by commas, spaces or new lines.
                          GMAIL_ADDRESS always gets a copy. Everyone is Bcc'd,
                          so nobody sees the others' addresses. Empty = only you.
    GITHUB_TOKEN          set automatically in Actions (needs issues: write)
    GITHUB_REPOSITORY     set automatically in Actions (owner/repo)
    NOTIFY_GITHUB_USER    GitHub username to @mention (workflow defaults to repo owner)
    DRY_RUN=1             print alerts instead of sending
"""
from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

import requests

from .engine import Alert

COLORS = {"open": 0xE53935, "reminder": 0xE53935, "announced": 0xFB8C00,
          "open_time": 0xFB8C00, "tier_change": 0xFDD835, "tier_low": 0xFDD835,
          "sold_out": 0x757575, "closed": 0x757575, "error": 0x8E24AA,
          "heartbeat": 0x43A047, "test": 0x1E88E5}
GITHUB_API = "https://api.github.com"
CLOSES_ISSUE = {"sold_out", "closed", "test"}


_EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def parse_subscribers(raw: str) -> list[str]:
    """Split a SUBSCRIBER_LIST value into unique, valid addresses (case-insensitive)."""
    out, seen = [], set()
    for part in re.split(r"[\s,;]+", raw or ""):
        addr = part.strip().strip("<>")
        if not addr:
            continue
        if not _EMAIL_RE.match(addr):
            print(f"::warning::SUBSCRIBER_LIST: skipping invalid address {addr!r}")
            continue
        if addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def _plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*|`(.+?)`", lambda m: m.group(1) or m.group(2), text)


def _html(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)


class Notifier:
    def __init__(self, env: dict | None = None, issues: dict | None = None):
        env = dict(os.environ if env is None else env)
        self.dry = env.get("DRY_RUN") == "1"
        self.webhook = env.get("DISCORD_WEBHOOK_URL", "").strip()
        self.user_id = env.get("DISCORD_USER_ID", "").strip()
        self.gmail = env.get("GMAIL_ADDRESS", "").strip()
        self.gmail_pw = env.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
        # You (GMAIL_ADDRESS) always get a copy; SUBSCRIBER_LIST adds friends.
        self.recipients = parse_subscribers(
            f"{self.gmail} {env.get('SUBSCRIBER_LIST', '')}")
        self.gh_token = env.get("GITHUB_TOKEN", "").strip()
        self.gh_repo = env.get("GITHUB_REPOSITORY", "").strip()
        self.gh_user = env.get("NOTIFY_GITHUB_USER", "").strip().lstrip("@")
        # target id -> issue number; lives in state.json so comments reuse one issue
        self.issues = issues if issues is not None else {}
        self.log: list[str] = []

    def channels(self) -> list[str]:
        out = []
        if self.webhook:
            out.append("discord")
        if self.gmail and self.gmail_pw and self.recipients:
            out.append("gmail")
        if self.gh_token and self.gh_repo:
            out.append("github")
        return out

    def send(self, alert: Alert) -> bool:
        """Send to the alert's channels (default: all). True if at least one worked."""
        names = [c for c in self.channels()
                 if alert.channels is None or c in alert.channels]
        if self.dry:
            print(f"[DRY_RUN] {alert.kind} -> {alert.channels or 'all'}: {alert.title}")
            for line in alert.lines:
                print("    " + _plain(line))
            if alert.ics:
                print(f"    (+ .ics attachment, {len(alert.ics)} bytes)")
            return True
        if not names:  # e.g. Discord-only alert with no webhook set: nothing to retry
            self.log.append(f"skipped {alert.kind}: {alert.channels} not configured")
            return True
        senders = {"discord": self._discord, "gmail": self._gmail, "github": self._github}
        ok = False
        for name in names:
            ok |= self._try(name, senders[name], alert)
        return ok

    def _try(self, name, fn, alert) -> bool:
        try:
            fn(alert)
            self.log.append(f"{name}: sent {alert.kind}")
            return True
        except Exception as e:  # report, but never crash the run
            self.log.append(f"{name}: FAILED {alert.kind}: {type(e).__name__}: {e}")
            print(f"::warning::{name} failed for {alert.kind}: {type(e).__name__}")
            return False

    def _discord(self, alert: Alert) -> None:
        desc = "\n".join(alert.lines)
        if alert.url:
            desc += f"\n\n➡️ {alert.url}"
        payload = {
            "username": "IRONMAN watcher",
            "embeds": [{"title": alert.title[:256], "description": desc[:4000],
                        "url": alert.url, "color": COLORS.get(alert.kind, 0x607D8B)}],
            "allowed_mentions": {"parse": []},
        }
        if alert.urgent and self.user_id:
            payload["content"] = f"<@{self.user_id}>"
            payload["allowed_mentions"] = {"users": [self.user_id]}
        for attempt in range(3):
            r = requests.post(self.webhook, json=payload, timeout=20)
            if r.status_code == 429:  # rate limited
                time.sleep(min(float(r.json().get("retry_after", 2)), 10))
                continue
            r.raise_for_status()
            return
        raise RuntimeError("discord rate limited 3 times")

    def _gmail(self, alert: Alert) -> None:
        msg = EmailMessage()
        prefix = "🚨 " if alert.urgent else ""
        msg["Subject"] = prefix + alert.title
        msg["From"] = f"IRONMAN watcher <{self.gmail}>"
        # Visible "To" is the sender; everyone on the list is Bcc'd so
        # friends don't see each other's addresses (or reply-all).
        msg["To"] = self.gmail
        if alert.urgent:
            msg["X-Priority"] = "1"
            msg["Importance"] = "high"
        body = [_plain(line) for line in alert.lines]
        if alert.url:
            body += ["", f"Link: {alert.url}"]
        msg.set_content("\n".join(body) + "\n\n-- im703-zeroday watcher\n")
        html_lines = "".join(f"<p>{_html(line)}</p>" for line in alert.lines)
        if alert.url:
            html_lines += (f'<p><a href="{html.escape(alert.url)}" style="font-size:18px;'
                           f'font-weight:bold">➡️ Open registration page</a></p>')
        msg.add_alternative(f"<html><body>{html_lines}"
                            "<p style='color:#888'>im703-zeroday watcher</p></body></html>",
                            subtype="html")
        if alert.ics:
            # Inline calendar part lets Gmail show an "Add to calendar" card;
            # the attachment works in every other mail client.
            msg.add_alternative(alert.ics, subtype="calendar",
                                params={"method": "PUBLISH"})
            msg.add_attachment(alert.ics.encode(), maintype="text", subtype="calendar",
                               filename=f"{alert.target_id or 'ironman'}-registration.ics")
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=30) as s:
            s.login(self.gmail, self.gmail_pw)
            s.send_message(msg, from_addr=self.gmail, to_addrs=self.recipients)

    # ------------------------------------------------------------ GitHub issues

    def _gh(self, method: str, path: str, **payload) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.gh_token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        url = f"{GITHUB_API}/repos/{self.gh_repo}{path}"
        fn = {"GET": requests.get, "POST": requests.post, "PATCH": requests.patch}[method]
        kwargs = {"headers": headers, "timeout": 20}
        if payload:
            kwargs["json"] = payload
        return fn(url, **kwargs)

    def _new_issue(self, key: str, title: str, body: str) -> int:
        r = self._gh("POST", "/issues", title=title, body=body)
        r.raise_for_status()
        self.issues[key] = r.json()["number"]
        return self.issues[key]

    def ensure_issue(self, target_id: str, target_name: str) -> int | None:
        """Open the race's issue quietly (no @mention) so you can close it to stop alerts."""
        if "github" not in self.channels() or self.dry:
            return None
        if target_id in self.issues:
            return self.issues[target_id]
        try:
            return self._new_issue(target_id, issue_title(target_id, target_name),
                                   intro_body(target_name))
        except Exception as e:
            self.log.append(f"github: FAILED to open issue for {target_id}: {e}")
            return None

    def issue_info(self, target_id: str) -> dict | None:
        """Current issue state, or None if there's no issue / GitHub not set up."""
        number = self.issues.get(target_id)
        if number is None or "github" not in self.channels() or self.dry:
            return None
        try:
            r = self._gh("GET", f"/issues/{number}")
            if r.status_code in (404, 410):
                self.issues.pop(target_id, None)
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            self.log.append(f"github: FAILED to read issue #{number}: {e}")
            return None

    def set_issue_state(self, target_id: str, open_: bool, reason: str = "completed") -> bool:
        number = self.issues.get(target_id)
        if number is None or "github" not in self.channels() or self.dry:
            return False
        payload = {"state": "open"} if open_ else {"state": "closed", "state_reason": reason}
        try:
            self._gh("PATCH", f"/issues/{number}", **payload).raise_for_status()
            return True
        except Exception as e:
            self.log.append(f"github: FAILED to update issue #{number}: {e}")
            return False

    def _github(self, alert: Alert) -> None:
        key = alert.target_id or "_status"
        lines = [f"### {alert.title}", ""] + list(alert.lines)
        if alert.url:
            lines += ["", f"➡️ {alert.url}"]
        if alert.ics:
            lines += ["", "📅 Calendar invite (.ics) sent by email."]
        if self.gh_user:
            lines += ["", f"cc @{self.gh_user}"]
        body = "\n".join(lines)
        number = self.issues.get(key)
        if number is not None:
            r = self._gh("POST", f"/issues/{number}/comments", body=body)
            if r.status_code in (404, 410):  # issue deleted: open a new one
                number = None
            else:
                r.raise_for_status()
        if number is None:
            title = (issue_title(key, alert.target_name) if alert.target_id
                     else "Watcher status")
            if alert.target_id:
                body = intro_body(alert.target_name) + "\n\n---\n\n" + body
            number = self._new_issue(key, title, body)
        if alert.kind in CLOSES_ISSUE:
            self._gh("PATCH", f"/issues/{number}", state="closed",
                     state_reason="completed").raise_for_status()
            if alert.kind == "test":
                self.issues.pop(key, None)


def issue_title(target_id: str, target_name: str) -> str:
    return f"{target_name or target_id}: registration watch"


def intro_body(target_name: str) -> str:
    return (f"Watching **{target_name}** registration. Alerts appear here as comments.\n\n"
            "**Stop alerts for this race:**\n"
            "- Registered? Close this issue as **Completed** 🎉\n"
            "- Changed your mind? Close it as **Not planned**.\n\n"
            "Reopen the issue to resume watching. If every race is stopped, the "
            "workflow turns itself off; re-enable it first (Actions → watch).")
