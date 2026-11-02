# Alert messages

Exact text of every alert, produced by running the real watcher code on example data. Every channel sends the same message: a bold title, the body and a `Link:` line. Markdown symbols (`**`, backticks) are shown as they are sent; Discord and GitHub render them, and the email removes them (its HTML copy shows them as bold/code).

**Example data:** IRONMAN 70.3 Goa 2027 (time zone Asia/Kolkata); Njuko entry appears 1 Mar 2027, opens Thu 22 Apr 2027 10:00 IST, race Sun 31 Oct 2027. Prices and slots are the real Amdavad 2027 numbers from 2 Nov 2026.

**What each channel adds:**

- **Discord:** plain text message from `IRONMAN watcher`, no embed and no link preview. Urgent alerts start with `<@your-id>`, which pings you.
- **Gmail:** subject = title. Sent to `GMAIL_ADDRESS`, Bcc to `SUBSCRIBER_LIST`; urgent alerts are marked high priority.
- **GitHub:** comment on the race's issue, ending with `cc @mantavyam` so GitHub emails and pushes you.

| Situation | Discord | Gmail | GitHub |
|---|---|---|---|
| <b>Announced (opening time known)</b><br><sub>Njuko creates the edition (DRAFT) and already shows a future opening time.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration announced\*\*<br>The 2027 edition is now listed on Njuko (\`2027-ironman-703-goa\`, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Registration opens: \*\*Thu 22 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration announced<br><br>The 2027 edition is now listed on Njuko (2027-ironman-703-goa, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Registration opens: Thu 22 Apr 2027, 10:00 IST. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>_(calendar invite attached)_ | \*\*IRONMAN 70.3 Goa 2027: registration announced\*\*<br>The 2027 edition is now listed on Njuko (\`2027-ironman-703-goa\`, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Registration opens: \*\*Thu 22 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Announced (opening time not published yet)</b><br><sub>Njuko edition appears, but its opening time is still a placeholder in the past.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration announced\*\*<br>The 2027 edition is now listed on Njuko (\`2027-ironman-703-goa\`, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Opening time not published yet. You will get another alert when it is.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration announced<br><br>The 2027 edition is now listed on Njuko (2027-ironman-703-goa, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Opening time not published yet. You will get another alert when it is.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: registration announced\*\*<br>The 2027 edition is now listed on Njuko (\`2027-ironman-703-goa\`, status DRAFT).<br>Race day: Sun 31 Oct 2027, 06:30 IST<br>Opening time not published yet. You will get another alert when it is.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Opening time published</b><br><sub>A later run finds a real future opening time for an already announced race.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration opens Thu 22 Apr 2027, 10:00 IST\*\*<br>Registration opens: \*\*Thu 22 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration opens Thu 22 Apr 2027, 10:00 IST<br><br>Registration opens: Thu 22 Apr 2027, 10:00 IST. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>_(calendar invite attached)_ | \*\*IRONMAN 70.3 Goa 2027: registration opens Thu 22 Apr 2027, 10:00 IST\*\*<br>Registration opens: \*\*Thu 22 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Opening time changed</b><br><sub>Ironman moves the opening time. The new calendar invite replaces the old event.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration opens Fri 23 Apr 2027, 10:00 IST\*\*<br>Opening time changed to: \*\*Fri 23 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration opens Fri 23 Apr 2027, 10:00 IST<br><br>Opening time changed to: Fri 23 Apr 2027, 10:00 IST. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>_(calendar invite attached)_ | \*\*IRONMAN 70.3 Goa 2027: registration opens Fri 23 Apr 2027, 10:00 IST\*\*<br>Opening time changed to: \*\*Fri 23 Apr 2027, 10:00 IST\*\*. A calendar invite is attached to the email.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Opens within a day</b><br><sub>A check runs less than 26 hours before the opening time.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration opens in about 23 h 13 min\*\*<br>Opens Thu 22 Apr 2027, 10:00 IST.<br>Be logged in to your IRONMAN account and ready to pay.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration opens in about 23 h 13 min<br><br>Opens Thu 22 Apr 2027, 10:00 IST.<br>Be logged in to your IRONMAN account and ready to pay.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: registration opens in about 23 h 13 min\*\*<br>Opens Thu 22 Apr 2027, 10:00 IST.<br>Be logged in to your IRONMAN account and ready to pay.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Registration OPEN</b><br><sub>The first check after registration opens.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: registration is open\*\*<br>Register now. Early-bird slots usually sell out within about 48 hours.<br>\*\*Individual Entry\*\*: tier 1/3 ₹42,900 all-in, 137/257 left (46% full); next tier ₹46,200<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration is open<br><br>Register now. Early-bird slots usually sell out within about 48 hours.<br>Individual Entry: tier 1/3 ₹42,900 all-in, 137/257 left (46% full); next tier ₹46,200<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: registration is open\*\*<br>Register now. Early-bird slots usually sell out within about 48 hours.<br>\*\*Individual Entry\*\*: tier 1/3 ₹42,900 all-in, 137/257 left (46% full); next tier ₹46,200<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Current tier filling up</b><br><sub>The current price tier reaches \`tier\_alert\_pct\` (80%) full.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: current price tier 89% full\*\*<br>\*\*Individual Entry\*\*: only 26/257 left at ₹42,900 before the price goes up.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: current price tier 89% full<br><br>Individual Entry: only 26/257 left at ₹42,900 before the price goes up.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: current price tier 89% full\*\*<br>\*\*Individual Entry\*\*: only 26/257 left at ₹42,900 before the price goes up.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Price tier changed</b><br><sub>The cheaper tier sold out, so the price went up.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: price tier changed\*\*<br>\*\*Individual Entry\*\*: now tier 2/3 at ₹46,200 all-in (358 left).<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: price tier changed<br><br>Individual Entry: now tier 2/3 at ₹46,200 all-in (358 left).<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: price tier changed\*\*<br>\*\*Individual Entry\*\*: now tier 2/3 at ₹46,200 all-in (358 left).<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam |
| <b>Sold out (watching stops)</b><br><sub>Every paid tier of the tracked entry types is full. The race is done and its issue closes.</sub> | \*\*IRONMAN 70.3 Goa 2027: registration sold out, watching stopped\*\*<br>All tracked entry types are sold out. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration sold out, watching stopped<br><br>All tracked entry types are sold out. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: registration sold out, watching stopped\*\*<br>All tracked entry types are sold out. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam<br><br>_(then closes the issue)_ |
| <b>Registration closed (watching stops)</b><br><sub>The registration end date passes before the race sells out.</sub> | \*\*IRONMAN 70.3 Goa 2027: registration closed, watching stopped\*\*<br>All tracked entry types are closed. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | Subject: IRONMAN 70.3 Goa 2027: registration closed, watching stopped<br><br>All tracked entry types are closed. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa | \*\*IRONMAN 70.3 Goa 2027: registration closed, watching stopped\*\*<br>All tracked entry types are closed. This race will not be checked again.<br><br>Link: https://in.ind1.ironman.com/2027-ironman-703-goa<br><br>cc @mantavyam<br><br>_(then closes the issue)_ |
| <b>Page says open, edition not confirmed</b><br><sub>ironman.com switches to open, but no Njuko edition for the target year is found.</sub> | &lt;@123456789012345678&gt;<br>\*\*IRONMAN 70.3 Goa 2027: Ironman page says registration is open\*\*<br>The register page switched to open, but no Njuko edition for 2027 was found yet. It may be this edition. Check the page now.<br><br>Link: https://www.ironman.com/races/im703-goa/register | Subject: IRONMAN 70.3 Goa 2027: Ironman page says registration is open<br><br>The register page switched to open, but no Njuko edition for 2027 was found yet. It may be this edition. Check the page now.<br><br>Link: https://www.ironman.com/races/im703-goa/register | \*\*IRONMAN 70.3 Goa 2027: Ironman page says registration is open\*\*<br>The register page switched to open, but no Njuko edition for 2027 was found yet. It may be this edition. Check the page now.<br><br>Link: https://www.ironman.com/races/im703-goa/register<br><br>cc @mantavyam |
| <b>Watcher problem</b><br><sub>A source fails 2 runs in a row (about a day).</sub> | &lt;@123456789012345678&gt;<br>\*\*Watcher problem: IRONMAN 70.3 Goa 2027 Ironman page\*\*<br>Failed 2 runs in a row.<br>Last error: \`ironman page: HTTP 403\`<br>The other source may still work. Check the Actions logs. The site layout or API may have changed. | Subject: Watcher problem: IRONMAN 70.3 Goa 2027 Ironman page<br><br>Failed 2 runs in a row.<br>Last error: ironman page: HTTP 403<br>The other source may still work. Check the Actions logs. The site layout or API may have changed. | _(on the "Watcher status" issue)_<br>\*\*Watcher problem: IRONMAN 70.3 Goa 2027 Ironman page\*\*<br>Failed 2 runs in a row.<br>Last error: \`ironman page: HTTP 403\`<br>The other source may still work. Check the Actions logs. The site layout or API may have changed.<br><br>cc @mantavyam |
| <b>Working again</b><br><sub>The failing source works again.</sub> | \*\*IRONMAN 70.3 Goa 2027 Ironman page working again\*\*<br>Checks are succeeding again. | Subject: IRONMAN 70.3 Goa 2027 Ironman page working again<br><br>Checks are succeeding again. | _(on the "Watcher status" issue)_<br>\*\*IRONMAN 70.3 Goa 2027 Ironman page working again\*\*<br>Checks are succeeding again.<br><br>cc @mantavyam |
| <b>Weekly check-in</b><br><sub>Every 7 days (example from March 2027).</sub> | \*\*Weekly check-in: watcher is running\*\*<br>\*\*IRONMAN 70.3 Goa 2027\*\*: announced, opens Thu 22 Apr 2027, 10:00 IST<br>\*\*IRONMAN 70.3 Amdavad 2028\*\*: starts watching 15 Feb 2027 | - | - |
| <b>Alerts stopped: registered</b><br><sub>You close the race issue as Completed, or run mode \`stop\` with reason \`booked\`.</sub> | \*\*IRONMAN 70.3 Goa 2027: alerts stopped (you registered)\*\*<br>No more alerts for this race.<br>To watch again: reopen its GitHub issue, or run the workflow with mode \`resume\`. | - | - |
| <b>Alerts stopped: not registering</b><br><sub>You close the race issue as Not planned, or run mode \`stop\` with reason \`not-interested\`.</sub> | \*\*IRONMAN 70.3 Goa 2027: alerts stopped (you are not registering)\*\*<br>No more alerts for this race.<br>To watch again: reopen its GitHub issue, or run the workflow with mode \`resume\`. | - | - |
| <b>Watching resumed</b><br><sub>You reopen the race issue, or run mode \`resume\`.</sub> | \*\*IRONMAN 70.3 Goa 2027: watching resumed\*\*<br>Alerts for this race are back on. | - | - |
| <b>Test alert</b><br><sub>Manual run with mode \`test-notify\`. Opens a test issue and closes it.</sub> | &lt;@123456789012345678&gt;<br>\*\*Test alert from im703-zeroday\*\*<br>If you can read this, alerts work on this channel.<br>The attached test calendar event is at Tue 03 Nov 2026, 22:00 IST. Delete it after checking.<br><br>Link: https://www.ironman.com/races/im703-goa/register | Subject: Test alert from im703-zeroday<br><br>If you can read this, alerts work on this channel.<br>The attached test calendar event is at Tue 03 Nov 2026, 22:00 IST. Delete it after checking.<br><br>Link: https://www.ironman.com/races/im703-goa/register<br><br>_(calendar invite attached)_ | _(opens a new issue; description below the table)_<br>\*\*Test alert from im703-zeroday\*\*<br>If you can read this, alerts work on this channel.<br>The attached test calendar event is at Tue 03 Nov 2026, 22:00 IST. Delete it after checking.<br><br>Link: https://www.ironman.com/races/im703-goa/register<br><br>cc @mantavyam<br><br>_(then closes the issue)_ |

## Race issue description

Opened quietly (no @mention) on the first check of a race. Title: **IRONMAN 70.3 Goa 2027: registration watch**

```markdown
Watching **IRONMAN 70.3 Goa 2027** registration. Alerts appear here as comments.

**Stop alerts for this race:**
- Registered? Close this issue as **Completed**.
- Changed your mind? Close it as **Not planned**.

Reopen the issue to resume watching. If every race is stopped, the workflow turns itself off. Re-enable it first (Actions, then watch).
```

## Calendar invite

Attached to the *Announced (opening time known)*, *Opening time published* and *Opening time changed* emails.

| Field | Value |
|---|---|
| Title | IRONMAN 70.3 Goa 2027 registration opens |
| When | Thu 22 Apr 2027, 10:00 to 10:30 IST |
| Reminders | 1 day, 1 hour and 10 minutes before: "IRONMAN 70.3 Goa 2027 registration opens tomorrow / in 1 hour / in 10 minutes" |
| Link | https://in.ind1.ironman.com/2027-ironman-703-goa |
| Notes | IRONMAN 70.3 Goa 2027 registration opens. Early-bird slots usually sell out within about 48 hours.<br>Register: https://in.ind1.ironman.com/2027-ironman-703-goa<br>Info: https://www.ironman.com/races/im703-goa/register |

<details><summary>Raw .ics file</summary>

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//im703-zeroday//registration watcher//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:goa-2027-registration-open@im703-zeroday
SEQUENCE:0
DTSTAMP:20270301T051700Z
DTSTART:20270422T043000Z
DTEND:20270422T050000Z
SUMMARY:IRONMAN 70.3 Goa 2027 registration opens
DESCRIPTION:IRONMAN 70.3 Goa 2027 registration opens. Early-bird slots usu
 ally sell out within about 48 hours.\nRegister: https://in.ind1.ironman.c
 om/2027-ironman-703-goa\nInfo: https://www.ironman.com/races/im703-goa/re
 gister
URL:https://in.ind1.ironman.com/2027-ironman-703-goa
STATUS:CONFIRMED
TRANSP:OPAQUE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:IRONMAN 70.3 Goa 2027 registration opens tomorrow
TRIGGER:-P1D
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:IRONMAN 70.3 Goa 2027 registration opens in 1 hour
TRIGGER:-PT1H
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:IRONMAN 70.3 Goa 2027 registration opens in 10 minutes
TRIGGER:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
```

</details>

