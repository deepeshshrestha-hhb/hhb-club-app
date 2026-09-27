---
name: league-weekly-update
description: Write the weekly Annual Players League WhatsApp round-up after the admin submits a Sunday's Weekly Score Upload to the database. Use when the user says they've submitted this week's scores and wants the group update, or invokes /league-weekly-update (optionally with a date, e.g. 2026-09-27).
---

# League weekly WhatsApp round-up

The admin submits Sunday's scores from `/weekly-scores`, then asks for the
message to post to the club WhatsApp group. Your job: pull the facts, then
write the message in the house format below.

## 1. Get the facts (read-only)

```
python scripts/league_weekly_update.py [YYYY-MM-DD]
```

- No date means the latest Sunday with matches. Pass the date if the user names one.
- It downloads the League workbooks from **production R2** into a temp folder
  and never writes anything back. If it prints `"source": "local"`, R2 creds
  weren't found and the numbers come from the local `tournaments/` copy,
  which may be stale. Tell the user.
- If the date the user means isn't the latest `matches_by_week` entry, they
  probably haven't submitted yet. Say so and stop. Don't write about the
  previous week by mistake.
- Pipe stderr away (`2>$null`), because openpyxl prints harmless warnings.

All counts exclude Rule 6 struck-off matches (same as the website), so use
the script's numbers and don't recount raw rows.

## 2. Write the message

Keep the same shape every week. WhatsApp formatting uses `*bold*`, so no
Markdown headings. Give it to the user in one fenced code block so it copies
cleanly, and keep it phone-length.

```
🏸 *HHB Annual Players League <year> — Week <n> Round-Up (<dd-Mon>)*
<1–2 lines: matches today / players / courts, compared with previous weeks (matches_by_week); season total vs next season milestone>

*Final Standings — <short hook>*
🥇 *<#1>* — <W>W-<L>L (<pct>%), <movement + day record>
🥈 *<#2>* — ...
🥉 *<#3>* — ...
<optional 📈 big mover line (compare prev_rank vs rank); note if a top-3 player from last week didn't play>
<one line on the gap at the top>

*Performance of the day:* <perfect_days first (W-0, 3+ wins) = "a perfect 100% record"; otherwise the best day_records>
<optional: biggest win of the day (biggest_wins_today), deuce/1-point thrillers>
<welcomes: all_time_debuts = "making their League debut"; season_first_appearances not in debuts = "first appearance of the season">

🏆 *Milestones this week*
• <milestones_reached_today; players_at_or_above == 1 means "the first player ever to reach …">
• <any notable all_time_record_changes, e.g. a new most-wins-in-one-Sunday, or someone climbing the all-time top 5>

👀 *Coming up next week*
• <upcoming_milestones with to_go <= ~3, plus club_milestone / season_milestone if within reach>

Bring on Week <n+1>! 👀

📊 League Standings: <links.standings>
📈 All-Time Analytics: <links.analytics>
```

Rules:
- **Accuracy over flair.** Every number must come from the fact sheet. Don't
  claim "record-breaking" or "first ever" unless the data shows it
  (`busiest_sunday`, `players_at_or_above == 1`, `all_time_record_changes`).
- **No gendered pronouns.** Players' pronouns aren't recorded, so phrase
  around them ("Sandip brings up match #250", not "his 250th").
- Drop any section with nothing to say, except the standings and the two links.
- Use first names or nicknames exactly as the sheet spells them.
- After the code block, add short bullets for anything the admin should
  double-check, such as an odd data point, a name that looks like a
  duplicate spelling, or a struck-off match today (`struck_off_today`).
