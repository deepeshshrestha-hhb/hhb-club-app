# HHB Club App — Project Memory

> Persistent working notes for this repo. Keep it concise (bullets, not essays).
> **Update this file at the end of every session** or after any meaningful chunk
> of work: reflect what changed, what was decided, and what's next.

---

## Project Overview

- **What it is:** A Flask web app for the HHB badminton club. It surfaces the
  club's session calendar, an archive of annual tournaments (with full
  results/brackets), a player directory, and an all-time player leaderboard
  ("HHB Score").
- **Tech stack:**
  - Python 3 + **Flask 3.0** (server-rendered Jinja2 templates, no SPA)
  - **Bootstrap 5.3** (via CDN) for styling + custom `static/styles.css`
  - **pandas / openpyxl** for reading Excel data files
  - **spond** library for live integration with the club's Spond group
  - **python-dotenv** for config/secrets
- **Key features:**
  - **Dashboard** (`/`) and **About** (`/about`) — static landing pages
  - **Calendar** (`/calendar`) — live upcoming sessions pulled from Spond +
    recurring annual events from an Excel sheet
  - **Annual Tournaments** (`/tournaments/annual`) hub, split into three archives:
    - **Doubles** (Annual Doubles Classic, 2018–2026)
    - **Championships** (Annual Championships, pools A & B)
    - **League** (Annual Players League)
  - **Players** (`/players`) — directory synced from Spond + computed all-time
    stats and HHB Score leaderboard
  - **Admin** (`/admin`) — placeholder Spond-sync button

---

## Architecture Notes

Standard Flask blueprint layout. App factory in [app.py](app.py) registers four
blueprints and refreshes the Spond member CSV on startup.

```
app.py                  # create_app(); registers blueprints; / and /about routes
config.py               # Config class; loads .env (SECRET_KEY, Spond creds, DATA_DIR)
routes/                 # Flask blueprints (thin; delegate to services)
  calendar_routes.py    # /calendar, /api/calendar
  tournament_routes.py  # /tournaments/* (doubles, championships, league)
  player_routes.py      # /players
  admin_routes.py       # /admin, /admin/sync_spond (placeholder)
services/               # Business logic + data parsing (the heart of the app)
  spond_service.py      # Live Spond fetch: events (calendar) + members (CSV)
  calendar_service.py   # Weekly sessions (via Spond) + annual events (Excel)
  excel_service.py      # Thin load_excel/save_excel helpers over data/
  tournament_service.py # Generic tournament CRUD + Doubles .xlsm parser
  championship_service.py
  league_service.py
  player_service.py     # Reads hhb_members.csv, merges stats, ranks players
  player_stats_service.py # Computes per-player stats + HHB Score (cached)
models/                 # Lightweight plain classes (Player, Match, etc.) — minimal use
templates/              # Jinja2 templates; base.html holds the navbar
static/                 # styles.css, css/, js/ (calendar.js, tournaments.js), images/
data/                   # Excel club data + hhb_members.csv (regenerated from Spond)
tournaments/            # Per-year tournament scoresheets (.xlsm) — source of truth
```

**Key data-flow facts:**
- **Spond is the live source** for calendar sessions and the member list.
  `fetch_members_to_csv()` runs on every app startup and writes
  `data/hhb_members.csv`; it fails silently so the app still boots offline (uses
  the cached CSV). Calendar sessions are fetched **live per page load**
  (`get_weekly_sessions`), returning `[]` on failure so the page still renders.
- **Tournament results are parsed read-only from `.xlsm` files** in
  `tournaments/`. Each tournament type/era has its own parser because the Excel
  layouts differ year to year (see Decisions Log).
- **HHB Score** ([player_stats_service.py](services/player_stats_service.py))
  aggregates achievements across all three tournament types into one ranked
  leaderboard. Player name matching across tournaments uses lowercase first
  names + an `ALIASES` map for nicknames/spellings. Results are cached in-process.
- Secrets live only in `.env` (gitignored). `.env.example` documents required
  vars: `SECRET_KEY`, `SPOND_USERNAME`, `SPOND_PASSWORD`, `SPOND_GROUP_ID`.

---

## Current Status

**Working:**
- Dashboard, About, Calendar, Players, and all three tournament archives render.
- Live Spond integration for sessions + members (graceful offline fallback).
- Doubles parser handles modern 2-group/QF-SF-Final template plus bespoke
  one-off year formats: 2018 (single league + eliminator), 2019/2021
  (direct-to-semis), 2022 (Super 6/Super 3 + walkover).
- Championships and League parsers + HHB Score leaderboard.

**In progress / partial:**
- `/admin/sync_spond` is a **placeholder** (live-fetch mode means there's
  nothing to pre-sync). Returns a placeholder string.
- `/api/calendar` still serves `ClubCalendar.xlsx` data, not live Spond — noted
  inline as a possible future switch to `get_weekly_sessions()`.
- `models/` classes are minimal and largely unused; logic lives in services.

**Known issues / gotchas:**
- `COMPLETED_2026_EVENTS` set in [calendar_service.py](services/calendar_service.py)
  is hand-maintained — update it as 2026 events pass.
- `SUPPORTED_DOUBLES_YEARS` in [tournament_service.py](services/tournament_service.py)
  must be extended manually as more years are confirmed to fit a parser.
- `get_doubles_tournament` has a duplicated unreachable `return` block at the end
  (harmless dead code).

---

## Decisions Log

- **2026-06-23** — Created this CLAUDE.md as the project memory file (initial
  pass documenting the codebase as found).
- **2026-06-23** — Initialized git and made the first commit of the existing
  codebase. Added `.gitattributes` (`* text=auto` + explicit binary types) to
  normalize line endings and silence Windows CRLF warnings.
- **2026-06-23** — Stopped versioning `data/hhb_members.csv` (gitignored + removed
  from tracking). *Why:* it contains member PII (emails, DOBs) and is regenerated
  from Spond on every app startup, so it's a cache, not source.
- **Spond live-fetch over pre-sync** — Calendar and member data are pulled live
  rather than synced into a local store; the Admin "Sync Spond" button is kept
  only for backwards compatibility. *Why:* avoids stale data and a sync job;
  member CSV is the one cached artifact, refreshed on startup.
- **Fail-silent Spond calls** — startup member fetch and per-page session fetch
  both swallow errors and fall back (cached CSV / empty list). *Why:* the app
  must boot and render even when Spond is unreachable or creds are missing.
- **One parser per tournament era** — rather than a single generic Excel parser,
  each year/format has dedicated handling (modern template, 2018, 2019/2021,
  2022). *Why:* the club's scoresheet layouts changed substantially over the
  years; a single parser would be brittle.
- **First-name + ALIASES matching for HHB Score** — tournament sheets record
  first names only, so cross-tournament player identity is resolved by lowercase
  first name plus a small alias map. *Why:* simplest reliable join given the
  source data; documented nicknames are the only edge cases.
- **Secrets in `.env`, never committed** — `.gitignore` excludes `.env*`
  (except `.env.example`).

---

## Next Steps / TODO

- [x] **Initialize git** — done 2026-06-23; first commit captures the current state.
- [ ] Decide whether `/api/calendar` should switch to live Spond data
  (currently Excel-backed).
- [ ] Replace or remove the placeholder `/admin/sync_spond` behavior.
- [ ] Remove the duplicated dead `return` block at the end of
  `get_doubles_tournament` in [tournament_service.py](services/tournament_service.py).
- [ ] Confirm/extend `SUPPORTED_DOUBLES_YEARS` as remaining years are validated.
- [ ] Keep `COMPLETED_2026_EVENTS` current as the season progresses.

---

## Commit Message Convention

Once git is initialized, write commit messages that read as a working history —
**what changed and why**, not just "update":

- Use a short imperative summary line (≤72 chars), e.g.
  `Add 2022 Super 6 knockout parser for doubles archive`.
- Add a body when the *why* isn't obvious from the summary: the problem being
  solved, the approach, and any tradeoff or follow-up.
- One logical change per commit; avoid bundling unrelated edits.
- Bad: `update`, `fix stuff`, `wip`. Good: `Fix HHB Score double-counting
  championship pool results` / `Switch calendar to live Spond fetch with offline
  fallback`.
