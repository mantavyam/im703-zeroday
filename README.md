# im703-zeroday

GitHub Actions watcher that alerts you on **Discord**, **Gmail (with a calendar invite)** and **GitHub issues (@mention, so GitHub emails and pushes to your phone too)** when IRONMAN registration for a race you choose is announced, opens, changes price tier, or sells out. Then it stops by itself.

## How it works

Twice a day (10:47 and 22:47 IST) it checks two sources for each target in `targets.yaml`:

1. **Njuko API**, Ironman's registration system for the 2027 season:
   `https://front-api.njuko.com/edition/url/2027-ironman-703-goa`
   - `404`: edition not created yet
   - `DRAFT`: created, not open yet. Usually weeks before opening, often with the exact opening time.
   - `OPEN`: open. Every price tier comes with live `participantLimit` and `reservedCount`.
2. **ironman.com register page**, `<body class="registration-state--…">`: `open`, `opening_soon`, `sold_out`, `general_sold_out` or `closed`. It's a fallback, and the Register button link can reveal the Njuko slug early.

Each target moves through `waiting → announced → open → sold_out/closed`, and never goes backwards.

Every alert goes to all three channels, except the weekly check-in and stop/resume confirmations, which go only to Discord:

- **Discord:** a webhook message. Urgent alerts @mention you.
- **Gmail:** an email. Announced and opening-time emails also carry a `.ics` calendar invite.
- **GitHub:** one issue per race. Each alert is a comment ending in `cc @you`, so GitHub sends its own notification email and app push. The issue closes when the race is sold out or closed. The issue opens quietly (no @mention) when watching starts, so you can close it to stop alerts at any time. Watcher problems go to a separate "Watcher status" issue.

| Alert | When |
|---|---|
| Announced | Njuko edition appears (calendar invite if the time is known) |
| Opening time set/changed | Future opening time published or moved (invite updates the same calendar event) |
| Opens within a day | Before opening |
| **OPEN** | Registration open, with prices and slots left |
| Tier filling | Current tier ≥ `tier_alert_pct` full |
| Tier changed | Cheaper tier sold out, price went up |
| Sold out / closed | All tracked entry types gone. **Target done**, issue closed |
| Watcher problem | A source failed 2 runs in a row (~1 day) |
| Working again | A failing source recovered |
| Weekly check-in | Every 7 days, so you know it's alive (**Discord only**) |
| Stopped / resumed | You stopped or resumed a race (**Discord only**) |

The calendar invite has alarms 1 day, 1 hour and 10 minutes before opening. This covers the exact minute, even though checks run only every 12 hours.

When every active target is done, the workflow disables itself.

## Setup

1. **Create a GitHub repo and push this folder.**
   - **Public:** Actions minutes are free. Secrets stay encrypted, but `state/state.json` and `targets.yaml` are visible.
   - **Private:** fine too. Two runs a day use about 60 of the 2,000 free minutes a month.
2. **Discord webhook:** Server settings → Integrations → Webhooks → New Webhook → pick a channel → Copy URL.
   - Everyone in that channel sees the alerts. Only you are @mentioned, so friends who want phone pushes should set the channel's notifications to **All messages**.
3. **Your Discord user ID** (for @mention pings): User settings → Advanced → enable Developer Mode. Then right-click your name → Copy User ID.
4. **Gmail app password:**
   - Turn on 2-Step Verification on the Google account.
   - Go to https://myaccount.google.com/apppasswords and create one named "ironman watcher".
   - Copy the 16 characters.
5. **Repo secrets:** Settings → Secrets and variables → Actions → New repository secret.

   | Secret | Value |
   |---|---|
   | `DISCORD_WEBHOOK_URL` | webhook URL |
   | `DISCORD_USER_ID` | your numeric Discord ID |
   | `GMAIL_ADDRESS` | Gmail that sends the alerts |
   | `GMAIL_APP_PASSWORD` | the 16-char app password |
   | `SUBSCRIBER_LIST` | optional: friends who should also get the emails, comma-separated or one per line, e.g. `friend1@gmail.com, friend2@yahoo.com`. You (`GMAIL_ADDRESS`) always get a copy. Everyone is Bcc'd, so nobody sees the others' addresses. Unset = only you. |

6. **Allow the workflow to push state and write issues:** Settings → Actions → General → Workflow permissions → **Read and write**.
7. **GitHub mention target** (optional): issues @mention the repo owner by default. To mention someone else, add a repo *variable* (not a secret) `NOTIFY_GITHUB_USER` under Settings → Secrets and variables → Actions → Variables.
   - Check that GitHub emails you about mentions: https://github.com/settings/notifications → "Participating, @mentions and custom" → Email on.
   - Install the GitHub mobile app for push notifications.
8. **Test the alerts:**
   - Actions → **watch** → Run workflow → mode `test-notify`.
   - You should get a Discord ping, an email with a calendar invite for tomorrow, and a GitHub issue "TEST IRONMAN 70.3: registration watch" that mentions you and then closes. Delete the test calendar event afterwards.
9. **First real run:** Run workflow → mode `run`. After that it runs on schedule.

## Stop alerts (you registered, or changed your mind)

Pick whichever is easiest:

1. **Close the race's GitHub issue.** This works from the GitHub phone app.
   - Close as **Completed**: you registered 🎉
   - Close as **Not planned**: you changed your mind
   - The next run stops checking that race and sends a short Discord confirmation.
   - **Reopen the issue** to start watching again.
2. **Run the workflow by hand:** Actions → watch → Run workflow.
   - Mode `stop`, target `goa-2027`, reason `booked` or `not-interested`. This also closes the issue.
   - Mode `resume` undoes it.
3. **Edit `targets.yaml`:** set `active: false` for the race.

When every active race is stopped or sold out, the workflow turns itself off. To watch again after that, first re-enable it (Actions → watch → Enable workflow), then reopen the issue or run `resume`.

## Targets

Edit `targets.yaml`:

```yaml
- id: goa-2027
  name: IRONMAN 70.3 Goa 2027
  race_page: im703-goa          # ironman.com/races/<race_page>/register
  year: 2027
  race_months: [10, 11]         # sanity check on the race date
  watch_from: 2026-11-02
  active: true
  competitions: ["Individual Entry"]   # men's individual; women: "Individual Women Entry"
  tier_alert_pct: 80
  extra_slugs: []
```

- **Entry-type names** come from Njuko. Amdavad has `Individual Entry`, `Individual Women Entry`, `Relay Entry` and `Relay Women Entry`. Use `[]` to track all of them.
- **Watch a future edition:** add a new target, for example `goa-2028` with `year: 2028`. Then re-enable the workflow: Actions → watch → Enable workflow.
- **Unusual slugs:** most Njuko slugs are `{year}-ironman-703-{place}`, but a few differ (Oman is `muscat`). The watcher also reads the slug from the Register button. If you learn the slug some other way, add it to `extra_slugs`.

## Project layout

```
.github/workflows/watch.yml   schedule, manual modes (run / test-notify / stop / resume), state commit, self-disable
targets.yaml                  races to watch
state/state.json              watcher memory (phase, issue numbers, retry queue); committed by the workflow
watcher/sources.py            Njuko API + ironman.com page fetch/parse
watcher/engine.py             phases and alert rules
watcher/notify.py             Discord, Gmail (+ .ics), GitHub issues
watcher/ics.py                calendar invite
watcher/__main__.py           CLI and run loop
tests/                        tests + real saved pages/API responses (2026-11-02)
```

## Local use

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                          # tests use real saved pages/API responses
DRY_RUN=1 python -m watcher run    # live check, prints alerts instead of sending
python -m watcher status           # show saved state
python -m watcher stop goa-2027 --reason booked   # or not-interested
python -m watcher resume goa-2027
```

## Limits

- GitHub can delay scheduled runs, and in rare high-load periods it skips them. The calendar alarms are the backup for a known opening time.
- In about 20% of races checked, the Njuko edition appeared at or after opening, with no advance warning. In that case the alert comes at the next run, up to about 12 hours later.
- Njuko and Ironman can change their API or page at any time. If that breaks parsing, you get a "Watcher problem" alert instead of silence.
