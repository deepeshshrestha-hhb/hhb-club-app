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
  admin_routes.py       # /admin, /admin/sync_spond (placeholder); admin_required decorator
  feedback_routes.py    # /feedback, /feedback/submit, /feedback/status (admin)
services/               # Business logic + data parsing (the heart of the app)
  spond_service.py      # Live Spond fetch: events (calendar) + members (CSV)
  calendar_service.py   # Weekly sessions (via Spond) + annual events (Excel)
  excel_service.py      # Thin load_excel/save_excel helpers over data/
  tournament_service.py # Generic tournament CRUD + Doubles .xlsm parser
  championship_service.py
  league_service.py
  player_service.py     # Reads hhb_members.csv, merges stats, ranks players
  player_stats_service.py # Computes per-player stats + HHB Score (cached)
  feedback_service.py   # User feedback CRUD (Feedback.xlsx, General + Feature Request)
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
  vars: `SECRET_KEY`, `SPOND_USERNAME`, `SPOND_PASSWORD`, `SPOND_GROUP_ID`,
  `R2_*` (durable storage), `ADMIN_USERNAME`/`ADMIN_PASSWORD` (admin login).

---

## Deployment (Render + Cloudflare R2)

Live at **https://www.hhbclub.co.uk** (apex `hhbclub.co.uk` redirects to www),
also reachable at `hhb-club.onrender.com`. Hosted on **Render free tier**
(`gunicorn app:app --workers 1`, see [render.yaml](render.yaml)). GitHub repo
`deepeshshrestha-hhb/hhb-club-app` (private); Render auto-deploys on push to
`master`.

- **Durable storage:** Render's filesystem is ephemeral, so the canonical copies
  of `data/*` and `tournaments/*` live in a **Cloudflare R2** bucket
  (`hhb-club-data`). [r2_service.py](services/r2_service.py) downloads them on
  startup into the same local paths the parsers already use, and re-uploads any
  file the app writes (backing up the prior version under a `backups/` prefix
  first). All R2 code is a no-op locally when the `R2_*` env vars are unset.
- **Seeding / manual updates:** upload new `.xlsm` files to R2 under
  `tournaments/<exact filename>`, then **Admin → Refresh Data from R2** (or a
  redeploy) pulls them in. Use [scripts/seed_r2.py](scripts/seed_r2.py) to
  (re)seed with round-trip verification.
- **Admin:** single-user session login (`/admin/login`, `ADMIN_USERNAME` /
  `ADMIN_PASSWORD`). Buttons: **Spond Refresh** (members → CSV → R2) and
  **Refresh Data from R2**. Members are no longer fetched on every startup.
- **Cloudflare** now only provides DNS for the domain (A `@`→`216.24.57.1`,
  CNAME `www`→`hhb-club.onrender.com`, both DNS-only/grey-cloud). The old
  `cloudflared` tunnel has been deleted.
- **Day-to-day change → deploy workflow:** see
  [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) (and the phone cheat-sheet
  `docs/dev-workflow.png`). System diagram: `docs/architecture.png`.

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
- **Backslash-separator `.xlsm` files:** some scoresheets were saved with `\`
  ZIP path separators (e.g. `xl\sharedStrings.xml`). Windows' `zipfile` hides
  this (maps `\`→`/`) so they load fine locally, but on **Linux/Render** openpyxl
  raises `KeyError: 'xl/sharedStrings.xml'`. Handled by
  `load_workbook_normalized()` in [excel_service.py](services/excel_service.py),
  which rebuilds the package with forward slashes on failure. New scoresheets
  with this quirk are auto-handled — no manual fix needed.
- **R2 seeding & OneDrive:** the repo lives under OneDrive. Uploading files while
  they are un-hydrated "Files On-Demand" placeholders produced size-correct but
  byte-corrupt R2 objects. [scripts/seed_r2.py](scripts/seed_r2.py) reads each
  file (forcing hydration) and verifies the round trip; always seed via it.
- **Free-tier cold start:** the Render free instance spins down after ~15 min
  idle; the next request takes ~50s to wake (re-runs the R2 pull + first HHB
  Score computation, then caches). Expected, not a bug.

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
- **2026-06-24/25 — Deployed to Render free tier with Cloudflare R2 durable
  storage.** *Why:* stop depending on a local PC + `cloudflared` tunnel. Added
  R2 download-on-startup / upload-on-write, a single-user admin login, gunicorn,
  `render.yaml`, and production-safe app entry (`app = create_app()`, no
  `debug`). Members fetched on demand (Admin → Spond Refresh) instead of every
  startup. See the Deployment section.
- **2026-06-25 — App-side backups instead of R2 bucket versioning.** *Why:* R2
  exposes no S3-style versioning toggle, so `upload_file` copies the prior object
  to `backups/<key>.<timestamp>` before overwriting.
- **2026-06-25 — Tolerant workbook loader for backslash-`.xlsm` files.** *Why:*
  the Linux-only `sharedStrings` `KeyError`; see Known issues / gotchas.
- **2026-06-27 — Added a user feedback system** (`feedback_service.py`,
  `feedback_routes.py`, `templates/feedback.html`, site-wide modal + floating
  button in `base.html`). Two types: *General* (public) and *Feature Request*
  (admin-only). Submitters identify themselves by picking their name from the
  club player list (a `get_player_names()` dropdown injected site-wide via an
  `inject_feedback_players` context processor); "Non-Member" reveals an email
  field instead. Stored in `data/Feedback.xlsx` (cols incl. `Submitted By` +
  `User Email`) via the existing `load_excel`/`save_excel` + R2 pattern;
  gitignored as it can hold non-member emails (PII). `/feedback` shows General to
  everyone and adds a Feature Requests column with status controls for admins;
  status updates go through `admin_required`.
  *Why:* reuse the proven Excel+R2 storage and `admin_required` decorator rather
  than introduce a database for a low-volume feature.

---

## Next Steps / TODO

- [x] **Initialize git** — done 2026-06-23; first commit captures the current state.
- [x] **Replace the placeholder `/admin/sync_spond`** — now a real Spond Refresh
  (fetch members → CSV → R2), behind admin login. Done 2026-06-25.
- [x] **Deploy off the local PC** — live on Render + R2; tunnel removed. Done 2026-06-25.
- [ ] Decide whether `/api/calendar` should switch to live Spond data
  (currently Excel-backed).
- [ ] Remove the duplicated dead `return` block at the end of
  `get_doubles_tournament` in [tournament_service.py](services/tournament_service.py).
- [ ] Confirm/extend `SUPPORTED_DOUBLES_YEARS` as remaining years are validated.
- [ ] Keep `COMPLETED_2026_EVENTS` current as the season progresses.
- [ ] Optional: re-enable Cloudflare proxy (orange cloud) with SSL/TLS mode
  **Full (strict)** if you want CDN/WAF in front of Render.

---

## Git Workflow

**Always use feature branches — never commit directly to `master`.**

The full flow for every change:

```
git checkout -b feature/<short-description>   # 1. branch from master
# ... make changes, commit ...
git push -u origin feature/<short-description> # 2. push branch
gh pr create ...                               # 3. open PR (PowerShell, full gh path)
# merge on GitHub                              # 4. user merges via GitHub UI
git checkout master && git pull                # 5. sync local master
```

A `PreToolUse` hook in `.claude/settings.local.json` will fire a ⚠ warning
if a `git commit` or `git push` is attempted directly on `master` as a reminder.

---

## Local Tooling Notes

- **gh CLI** is installed at `C:\Program Files\GitHub CLI\gh.exe` but that
  directory is NOT on the PATH available to Claude's tool shell. Always invoke
  it with the full path:
  ```
  & "C:\Program Files\GitHub CLI\gh.exe" <command>
  ```
- **Flask dev server** — always start with `--no-reload` and track the PID.
  Multiple background processes can silently accumulate on the same port
  (Windows doesn't error), causing stale-code responses. Use
  `netstat -ano | grep ":<port> "` to verify only one LISTENING process exists
  before testing.

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
