# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
    stats and HHB Score leaderboard, plus a **Club Analytics** tab (age
    demographics, longest-serving, most-active / inactive by signup hours)
  - **Weekly Score Upload** (`/weekly-scores`) — self-service Sunday doubles
    score entry (replacing WhatsApp), with live duplicate-row highlighting;
    admin opens/closes a transient weekly session and submits it straight into
    the League workbook
  - **Hours Played** — signup-derived activity (last 4 weeks / 6 months)
    computed from Spond RSVPs; surfaced via `/api/hours-played/*` JSON and on
    profile/analytics views (distinct from the tournament-based HHB Score)
  - **Photos** — club gallery (`/photos/gallery`), per-event photos linked from
    tournament pages, podium photos, and per-player profile photos
  - **Feedback** — site-wide modal (General + Feature Request); `/feedback`
  - **Admin** (`/admin`) — Spond Refresh, Refresh Signup Analytics, Refresh Data
    from R2, and photo management (club + podium), behind a single-user login

---

## Commands

- **Install deps:** `pip install -r requirements.txt` (Python 3.12; see
  `PYTHON_VERSION` in [render.yaml](render.yaml)).
- **Run locally:** `python app.py` → serves on `http://localhost:5000`.
  Locally the `R2_*` env vars are unset, so the app skips R2 and reads/writes
  your local `data/` + `tournaments/` files — nothing touches production.
- **Production server (Render):**
  `gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`.
  `app = create_app()` is exposed at module level for gunicorn.
- **Config:** copy `.env.example` → `.env` and fill in Spond creds (required for
  the live calendar/members), plus optional `R2_*` / `ADMIN_*` vars. `.env` is
  gitignored.
- **Tests / lint:** there is **no** test suite or linter configured. For
  data-format changes the real confirmation is the page rendering **on Render**
  (Linux), since some `.xlsm` quirks are hidden on Windows (see Known issues).
- **Flask dev server caveat:** prefer `--no-reload` and track the PID — stale
  background processes can silently accumulate on the same port on Windows (see
  Local Tooling Notes).

## Architecture Notes

Standard Flask blueprint layout. App factory `create_app()` in [app.py](app.py)
registers ten blueprints and, on startup, pulls the canonical data files from R2
into local `data/` + `tournaments/` via `r2_service.download_all()` (a no-op
locally when `R2_*` is unset). The Spond member CSV is **no longer** refreshed on
startup — it's fetched on demand via Admin → Spond Refresh. Top-level routes
`/` (dashboard), `/about`, and `/health` live directly in `app.py`.

```
app.py                  # create_app(); registers blueprints; /, /about, /health routes
config.py               # Config class; loads .env (SECRET_KEY, Spond creds, DATA_DIR, ADMIN_*)
routes/                 # Flask blueprints (thin; delegate to services)
  calendar_routes.py    # /calendar, /api/calendar
  tournament_routes.py  # /tournaments/* (doubles, championships, league)
  player_routes.py      # /players (+ Analytics tab), profile pages, add/edit/delete profile
  photos_routes.py      # /photos gallery + per-event photos + profile photo uploads;
                        #   event summary view/save + Claude AI assist endpoint (admin)
  hours_routes.py       # /api/hours-played/* JSON (most-active, inactive, per-player)
  admin_routes.py       # /admin, /admin/login, Spond Refresh, Refresh Signup Analytics,
                        #   Refresh Data from R2, club + podium photo mgmt; admin_required
  feedback_routes.py    # /feedback, /feedback/submit, /feedback/status, /feedback/delete (admin)
  weekly_score_routes.py # /weekly-scores + api/ (add/amend/delete) + admin/ (open/close/submit)
services/               # Business logic + data parsing (the heart of the app)
  spond_service.py      # Live Spond fetch: events (calendar) + members (CSV) + per-date confirmed
                        #   attendees (get_confirmed_attendees, for Weekly Score Upload); _parse_timestamp, LOCAL_TZ
  calendar_service.py   # Weekly sessions (via Spond) + annual events (Excel)
  excel_service.py      # load_excel/save_excel + load_workbook_normalized() (backslash-zip fix)
  tournament_service.py # Generic tournament CRUD + Doubles .xlsm parser
  championship_service.py
  league_service.py     # Also: get_league_roster/resolve_attendee_names + write_weekly_scores()
                        #   (writes Weekly Score Upload matches into the live season's .xlsm)
  weekly_score_service.py # Weekly Score Upload session (data/WeeklyScoreSession.json): open/close/
                        #   add/amend/delete/submit-to-database, duplicate-row detection
  player_service.py     # Reads hhb_members.csv, merges stats + signup hours, ranks players
  player_stats_service.py # Computes per-player tournament stats + HHB Score (cached)
  analytics_service.py  # Signup-hours pipeline (Spond RSVPs → CSV → per-player hours) +
                        #   club analytics + lazy weekly background auto-refresh
  profile_service.py    # name_to_slug() + player profile data (jinja `slugify` filter)
  photos_service.py     # Club + event photo CRUD (Photos.xlsx + static/images/photos/)
  podium_service.py     # Podium photos in static/images/podium/ (numbered _1, _2 …)
  feedback_service.py   # User feedback CRUD (Feedback.xlsx, General + Feature Request)
  event_summary_service.py # Per-event overview text (EventSummaries.xlsx, keyed by event_id)
  ai_service.py         # Optional Claude text-assist (summarize/rewrite/tone) for summaries
  r2_service.py         # Cloudflare R2 download-on-startup / upload-on-write/delete (no-op locally)
models/                 # Lightweight plain classes (Player, Match, etc.) — minimal use
templates/              # Jinja2 templates; base.html holds the navbar + feedback modal
static/                 # styles.css, css/, js/ (calendar.js, tournaments.js), images/ (+ photos/, podium/)
data/                   # Excel club data + hhb_members.csv, player_hours.csv,
                        #   signups_history.csv, signups_meta.json (all regenerated from Spond),
                        #   WeeklyScoreSession.json (transient - deleted on submit-to-database)
tournaments/            # Per-year tournament scoresheets (.xlsm) — source of truth
scripts/                # seed_r2.py (upload+verify), pull_r2.py (download-only snapshot)
```

**Key data-flow facts:**
- **Spond is the live source** for calendar sessions and the member list.
  `fetch_members_to_csv()` writes `data/hhb_members.csv` **on demand** (Admin →
  Spond Refresh), failing silently so the app still boots offline from the cached
  CSV. Calendar sessions are fetched **live per page load** (`get_weekly_sessions`),
  returning `[]` on failure so the page still renders.
- **Tournament results are parsed read-only from `.xlsm` files** in
  `tournaments/`. Each tournament type/era has its own parser because the Excel
  layouts differ year to year (see Decisions Log).
- **HHB Score** ([player_stats_service.py](services/player_stats_service.py))
  aggregates achievements across all three tournament types into one ranked
  leaderboard. Player name matching across tournaments uses lowercase first
  names + an `ALIASES` map for nicknames/spellings. Results are cached in-process.
- **Signup "Hours Played" is a separate pipeline** from HHB Score
  ([analytics_service.py](services/analytics_service.py)): Spond RSVPs
  (accepted attendees only) for the last ~6 months →
  `data/signups_history.csv` → aggregated per player into
  `data/player_hours.csv` (last 4 weeks / 6 months). It joins on **full name**
  (no first-name/alias ambiguity), so it's distinct from the tournament join.
  `player_service.get_all_players()` merges these hours into each player record.
  Refreshed via **Admin → Refresh Signup Analytics** *and* a throttled
  **background auto-refresh** kicked off on Players/Calendar page load when the
  data is older than 7 days (`maybe_refresh_async`); staleness is tracked in
  `data/signups_meta.json` by **content**, not file mtime, because the R2 pull
  resets mtimes on every cold start. `get_club_analytics()` builds the Players
  Analytics tab (age bands, longest-serving from profile "year joined",
  most-active/inactive) — pure computation over the already-merged list.
- **Photos** live as files under `static/images/photos/` (club/event, metadata
  in `data/Photos.xlsx`) and `static/images/podium/` (numbered variants, no
  metadata file), each mirrored to R2 and editable via the Admin photo pages.
- **Weekly Score Upload** ([weekly_score_service.py](services/weekly_score_service.py))
  replaces WhatsApp score submission for Sunday doubles. A single transient
  session (`data/WeeklyScoreSession.json`, R2-backed) tracks status
  (none/open/closed) + in-progress matches, each with a required **Court No.**
  (1-4, the club only has 4 courts) added 2026-09-07 for court-usage analytics
  — see `get_league()`'s existing `top_players_courts`. The player dropdown is
  populated from that Sunday's confirmed Spond attendees
  (`spond_service.get_confirmed_attendees`), resolved to the league's own
  player-name spelling (`league_service.resolve_attendee_names`, reusing
  `player_stats_service.ALIASES`). **Submit to Database**
  (`league_service.write_weekly_scores`) writes the matches straight into that
  season's League `.xlsm` (reusing pre-built blank rows for the date if the
  sheet has them, else appending new ones) and then recomputes and overwrites
  — as literal values, not formulas — every played row's Winner/Difference/Points
  and every roster player's Played/Won/Lost/Points/PF, for the **whole** sheet,
  not just the new rows. That's required because opening a workbook with
  openpyxl and saving it drops the cached result of *every* formula in the
  file (openpyxl never evaluates formulas) — see the docstring on
  `write_weekly_scores` before touching this. Session clears back to "none"
  once submitted, ready for next Sunday.
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
- **Pulling prod data locally (read-only snapshot):** to bring live photos,
  player profiles, feedback, etc. into your local env, copy `.env.r2.example`
  → `.env.r2`, fill in the four `R2_*` values (Render dashboard → hhb-club
  service → Environment), and run [scripts/pull_r2.py](scripts/pull_r2.py)
  (download-only counterpart to `seed_r2.py`; mirrors all synced prefixes
  down). `.env.r2` is a **dedicated** file, separate from `.env` — `config.py`
  only loads `.env`, so the main app never sees these credentials and stays
  local-only even if `.env.r2` is left filled in. There is only one bucket and
  it *is* production, but because the app can't read `.env.r2`, there's no
  cleanup step needed after pulling (unlike the old `.env`-based flow).
- **Admin:** single-user session login (`/admin/login`, `ADMIN_USERNAME` /
  `ADMIN_PASSWORD`). Buttons: **Spond Refresh** (members → CSV → R2),
  **Refresh Signup Analytics** (RSVPs → hours → R2), **Refresh Data from R2**,
  plus club + podium photo management. Members are no longer fetched on every
  startup.
- **Cloudflare fronts the domain via a Worker reverse proxy**, not plain DNS.
  As of 2026-08-01, Render's custom-domain edge IP (`216.24.57.1`) sits inside
  Cloudflare's own network, so a direct DNS-only *or* proxied record at the
  apex/`www` hits Cloudflare error 1000 ("DNS points to prohibited IP") —
  free-tier Cloudflare refuses to route to an origin that's itself inside
  Cloudflare's network ("orange-to-orange" is Enterprise-only). The fix:
  a small Worker, **`hhb-club-proxy`** (Cloudflare dashboard → Workers &
  Pages → hhb-club-proxy), does a plain `fetch()` reverse-proxy to
  `https://hhb-club.onrender.com` — a Worker's outbound fetch isn't subject to
  the DNS-level block. `hhbclub.co.uk` and `www.hhbclub.co.uk` are bound to it
  as Worker **Custom Domains** (dashboard-managed; no manual DNS A/CNAME
  records for those two hosts anymore — Cloudflare auto-manages them via the
  Worker binding). Free Workers plan (100k req/day) is far more than this
  site needs. The three unrelated Cloudflare Tunnel subdomains on this same
  zone (`family-tree`, `snapped`, `travel-diaries` — other side projects, not
  part of this app) are untouched. Render support has not yet been contacted
  to ask whether they can offer a non-Cloudflare-fronted IP; if they do, the
  Worker could be removed and DNS-only records restored.
- **Day-to-day change → deploy workflow:** see
  [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) (and the phone cheat-sheet
  `docs/dev-workflow.png`, rendered from `docs/dev-workflow.html` — edit the HTML
  and re-export if it changes). System diagram: `docs/architecture.png`.

---

## Current Status

**Working:**
- Dashboard, About, Calendar, Players, and all three tournament archives render.
- Live Spond integration for sessions + members (graceful offline fallback).
- Doubles parser handles modern 2-group/QF-SF-Final template plus bespoke
  one-off year formats: 2018 (single league + eliminator), 2019/2021
  (direct-to-semis), 2022 (Super 6/Super 3 + walkover).
- Championships and League parsers + HHB Score leaderboard.
- Club Analytics tab + signup "Hours Played" (Spond-RSVP derived) with weekly
  background auto-refresh and an admin force-refresh.
- Club/event/podium photo galleries + per-player profile photos (R2-backed).
- Per-event summary paragraph (admin-editable, shown above the gallery) with an
  optional Claude AI "Summarize / Rewrite / change tone" assist (needs
  `ANTHROPIC_API_KEY`; degrades to a plain text field when unset).
- League "Final Standings" table is sortable by Played / Won / Win %.
- Weekly Score Upload (`/weekly-scores`): self-service Sunday score entry with
  a Spond-attendance-driven player dropdown, duplicate-row highlighting, and
  admin open/close/submit-to-database controls that write straight into the
  live season's League workbook. Not yet used in production for a real Sunday
  — worth a close look at the first live submission (see the Suggested Build
  Approach's step 6 in the original spec: "test the full weekly cycle
  end-to-end for one Sunday before rolling out to players").

**In progress / partial:**
- `/api/calendar` still serves `ClubCalendar.xlsx` data, not live Spond — noted
  inline as a possible future switch to `get_weekly_sessions()`.
- `models/` classes are minimal and largely unused; logic lives in services.

**Known issues / gotchas:**
- **Weekly Score Upload rows lose their live Excel formulas.** Every row
  `write_weekly_scores()` touches gets correct Winner/Difference/Points/
  standings numbers, but as literal values, not formulas — hand-editing one of
  those rows' scores later in Excel won't auto-update its derived columns
  (copy the formula from an untouched row if that's ever needed). This is a
  deliberate trade-off: openpyxl can't evaluate formulas and there's no
  headless Excel/LibreOffice available on Render's Python buildpack, so
  writing scores from the web form means recomputing those columns in Python
  instead of leaving Excel to do it. See the docstring on
  `league_service.write_weekly_scores` for the full reasoning.
- **A brand-new league player must still be added to the season's roster
  block in Excel** (the `PLAYERS_IDS`/points-table names, same as before this
  feature) for their Weekly Score Upload results to count toward standings —
  `resolve_attendee_names()` falls back to their plain first name so the match
  itself still gets recorded, but Played/Won/Points won't include them until
  they're in the roster.
- `COMPLETED_2026_EVENTS` set in [calendar_service.py](services/calendar_service.py)
  is hand-maintained — update it as 2026 events pass.
- All three tournament archives (Doubles, Championships, League) auto-discover
  years by globbing the `tournaments/` folder for the matching filename — no
  per-year code change is needed. The catch is the **parser**: each targets a
  specific Excel layout, so a new scoresheet must follow the same template as the
  most recent working year, otherwise the year lists but renders empty (a parser
  fix, not config).
- `get_doubles_tournament` has a duplicated unreachable `return` block at the end
  (harmless dead code).
- **Backslash-separator `.xlsm` files:** some scoresheets were saved with `\`
  ZIP path separators (e.g. `xl\sharedStrings.xml`). Windows' `zipfile` hides
  this (maps `\`→`/`) so they load fine locally, but on **Linux/Render** openpyxl
  raises `KeyError: 'xl/sharedStrings.xml'`. Handled by
  `load_workbook_normalized()` in [excel_service.py](services/excel_service.py),
  which rebuilds the package with forward slashes on failure. New scoresheets
  with this quirk are auto-handled — no manual fix needed.
- **R2 seeding — always use the script:** [scripts/seed_r2.py](scripts/seed_r2.py)
  reads each file and verifies the round trip (re-uploads on a mismatch) before
  declaring it seeded; always seed via it rather than uploading ad hoc. (As of
  2026-09, the repo lives on a local external drive, `I:\All Repositories\
  hhb_club_app` — not OneDrive. The verify-and-retry logic stays as a general
  safety net, but the OneDrive "Files On-Demand" un-hydrated-placeholder failure
  mode this was originally written for no longer applies; don't diagnose a
  seeding issue as OneDrive-related.)
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
- **2026-06-28 — Feedback admin: delete + expanded statuses + public feature
  requests.** Admins can now delete any entry (General or Feature Request) via
  `/feedback/delete` (`delete_feedback`, `admin_required`), and feature-request
  statuses expanded to five: New, Accepted, Rejected, In Progress, Completed.
  Feature Requests are now visible to **everyone** (read-only, including their
  status) so members can see what's been raised and not duplicate it; the status
  dropdown and delete buttons render only for admins (`session.is_admin`) and the
  routes stay `admin_required`.
- **2026-06-28 — Added signup "Hours Played" analytics + photo galleries.**
  New `analytics_service.py` derives per-player hours from Spond RSVPs
  (`signups_history.csv` → `player_hours.csv`), kept **separate** from the
  member CSV (which is rewritten wholesale on Spond Refresh) and merged at read
  time. Deliberately a **distinct pipeline from HHB Score**: it joins on full
  name and measures attendance, not tournament achievement. Refresh is both
  admin-triggered and a throttled background auto-refresh on page load, with
  staleness judged from `signups_meta.json` content (mtimes are unreliable after
  R2 cold-start downloads). Also added `photos_service.py` (club/event photos,
  `Photos.xlsx`) and `podium_service.py` (podium images), both R2-backed, with
  Admin upload/delete pages and a new `hours_bp` blueprint exposing
  `/api/hours-played/*`. *Why:* members wanted activity/attendance insights
  separate from competitive results, plus a place for event photos — all reusing
  the existing Excel/CSV + R2 storage pattern rather than a database.
- **2026-06-28 — Sortable League standings + event summaries with Claude AI
  assist.** (1) The League year "Final Standings" table is now client-side
  sortable by **Played / Won / Win %** (clickable headers, toggle asc/desc);
  default stays the official league order (by Won), and the `#` column always
  shows each player's true league rank/medal regardless of sort. (2) New
  `event_summary_service.py` stores an admin-authored overview paragraph per
  event in `data/EventSummaries.xlsx` (keyed by the same `event_id` photos use,
  e.g. `league_2024`, `annual_picnic_2025`), shown to everyone at the top of the
  event photo gallery and editable inline by admins. The gallery page now also
  renders for admins (and when a summary exists) even with zero photos.
  (3) Optional `ai_service.py` adds Claude "Summarize / Rewrite / change tone"
  helpers in the admin editor via `POST /photos/event/<id>/summary/ai`; gated by
  `ANTHROPIC_API_KEY` (+ optional `ANTHROPIC_MODEL`, default Haiku 4.5) — when
  the key is unset the AI buttons are simply hidden and the field works as plain
  text. New dep: `anthropic`. *Why:* reuse the proven Excel + R2 pattern and the
  `admin_required` decorator; keep the AI strictly optional so prod can adopt it
  whenever a key is added, with no hard dependency for local/offline runs.
- **2026-07-02 — Moved `pull_r2.py` credentials into a dedicated `.env.r2`
  file.** `scripts/pull_r2.py` now calls `load_dotenv(".env.r2")` itself
  instead of relying on `R2_*` vars in the main `.env`. *Why:* the old flow
  required commenting the `R2_*` vars back out of `.env` after every pull, or
  the next `python app.py` would re-upload local writes to production R2 —
  an easy step to forget. Since `config.py` only loads `.env`, the main app
  now structurally cannot see R2 credentials that live in `.env.r2`, so a
  prod-data resync is a single `python scripts/pull_r2.py` with nothing to
  clean up afterward. Added `.env.r2.example` as the template (gitignore
  updated to track it, mirroring the existing `.env.example` exception).
- **2026-08-01 — Restored production after Render's edge moved behind
  Cloudflare; added `hhb-club-proxy` Worker.** The site had been running
  locally (with a since-stopped `cloudflared` tunnel for `hhbclub.co.uk`)
  while Render was temporarily unused. On repointing the domain back to
  Render, both the pre-existing DNS-only apex `A` record and a Proxied `www`
  CNAME started failing with Cloudflare error 1000 ("DNS points to prohibited
  IP") — confirmed via direct IP probe that Render's custom-domain IP
  (`216.24.57.1`) now resolves inside Cloudflare's own network (`Server:
  cloudflare`, `CF-RAY` present even unproxied), which Cloudflare disallows
  routing to from another zone on free/pro plans. Moving the zone off
  Cloudflare DNS was ruled out (domain registered via Cloudflare, and three
  other side-project subdomains depend on Cloudflare Tunnels on this same
  zone). Fix: added a Cloudflare Worker (`hhb-club-proxy`) that reverse-proxies
  via `fetch()` to `https://hhb-club.onrender.com` — outbound Worker fetches
  aren't subject to the DNS-level block — and bound it to `hhbclub.co.uk` +
  `www.hhbclub.co.uk` as Worker Custom Domains, removing the old manual
  A/CNAME records (Cloudflare now manages those two hosts' DNS itself via the
  Worker binding). See the Deployment section for details. *Why:* kept
  everything on Cloudflare (no registrar/nameserver migration, no risk to the
  other tunnel-based subdomains) while working around a platform-level
  interaction that didn't exist when the domain was first set up.
- **2026-07-02 — Claude merges its own PRs via `gh pr merge`, no manual
  checkpoint.** Previously the Git Workflow reserved the actual merge step for
  the user via the GitHub UI. Per explicit user instruction, that checkpoint is
  removed: after opening a PR, immediately run
  `gh pr merge <n> --merge --delete-branch` (merge commit, not squash/rebase,
  to match this repo's history) and sync local master. *Why:* the user wants
  the full branch → PR → merge → sync cycle to run end-to-end without waiting
  for a manual approval step on GitHub.
- **2026-09-07 — Added Weekly Score Upload** (`weekly_score_service.py`,
  `weekly_score_routes.py`, `templates/weekly_scores.html`,
  `static/js/weekly_scores.js`), replacing WhatsApp-based Sunday score
  submission per the feature spec. Session state is a single transient JSON
  file (`data/WeeklyScoreSession.json`, R2-backed), not a new Excel sheet —
  matches the existing lightweight-JSON pattern already used for
  `committee.json`/`about_content.json` rather than introducing a new service
  category. The player dropdown resolves that Sunday's live Spond attendance
  to the league's own player-name spelling (new
  `spond_service.get_confirmed_attendees` + `league_service.
  resolve_attendee_names`, reusing `player_stats_service.ALIASES` for
  nickname mapping) so submitted names line up with the sheet's existing
  standings formulas, falling back to the full club roster if Spond has
  nothing for that date. The bigger design problem was **submitting into the
  live `.xlsm`**: openpyxl can't evaluate formulas, and saving a workbook it
  opened drops the cached result of every formula in the file, not just ones
  it edits — confirmed by a round-trip test before writing any real code
  (`ws['C5']='Alice'; wb.save(...)` blanked every other formula cell in the
  sheet, old rows included). Since there's no headless Excel/LibreOffice on
  Render's Python buildpack, `league_service.write_weekly_scores()`
  recomputes Winner/Difference/Points per match row and Played/Won/Lost/
  Points/PF per roster player itself (replicating the sheet's own formulas,
  including its player-ID-as-prime-number trick for the parts that turned out
  to not actually matter downstream) and writes them as literal values, for
  the *whole* sheet on every submit — verified end-to-end against a copy of
  the real 2026 league workbook (`get_league()` reads back correct winners,
  diffs and standings with no Excel involved). *Why not LibreOffice
  headless?* `render.yaml` is a plain Python buildpack
  (`buildCommand: pip install -r requirements.txt`), so a system package
  isn't available without moving to a Docker-based Render service — too big
  an infra change for this feature alone.
- **2026-09-07 — Added required Court No. (1-4) to Weekly Score Upload.**
  Requested for court-usage analytics. A `court-select` dropdown at the top
  of both the entry form and the amend modal, and a `Court` column at the
  front of the results table. Validated server-side (`weekly_score_service.
  VALID_COURTS`, required - not optional, unlike everything else about the
  session which degrades gracefully) and written into the league sheet's
  existing `Court No.` column (K, only present on the 2026+ template -
  `write_weekly_scores` silently skips it for an older template rather than
  erroring) alongside the rest of the match on submit. *Why:* the club only
  has 4 physical courts, and Court No. already existed as an optional column
  in the 2026 sheet (see the 2026-06 court-rotation decision) - this feature
  is what actually starts populating it every week instead of leaving it
  blank, so `get_league()`'s existing `top_players_courts` analytics has real
  data to work with going forward.
- **2026-09-07 — Weekly Score Upload polish: caching fix, disabled-until-valid
  submit, Amend prefill fix, compact/winner-first table, success toast,
  unique-player validation.** Several rapid follow-ups from live use on the
  first real Sunday: (1) a stale-cache bug where the Court No. dropdown
  showed blank on the live site, root-caused to the Cloudflare Worker reverse
  proxy caching the old JS bundle at the edge - fixed generically with an
  `asset_version()` Jinja global that appends an mtime-based `?v=...` to the
  script tag. (2) Submit/Save buttons are disabled until every field
  (`form.checkValidity()`) is filled. (3) Amend was silently failing to
  pre-select players whose names had fallen off the live attendance list
  since submission - fixed by always adding the match's own four players as
  options first. (4) Results table made phone-portrait-friendly: merged
  Player 1+2 / 3+4 into single "Team" columns, shortened headers, and always
  shows the winning team first regardless of entry order (display-only - the
  underlying stored/written data is unchanged). (5) A Bootstrap toast now
  confirms a successful submit/amend (there was previously no visual cue).
  (6) The same player can no longer appear in both teams - validated both
  client-side (button disabled + an inline message explaining why) and
  server-side (`weekly_score_service._validate_match`, since a duplicate
  player had already gotten into the live 6-Sep session before this fix
  shipped - existing bad rows need manual deletion, this only stops new ones).
- **2026-09-08 — Type-ahead search for the four player fields on Weekly Score
  Upload.** Scrolling a plain `<select>` through ~20+ names was the
  complaint. Each player field is now a small vanilla-JS combobox
  (`initPlayerCombobox` in `weekly_scores.js`, `player_search_field` Jinja
  macro in `weekly_scores.html`): a text input filters and shows matches in a
  dropdown (click or arrow keys + Enter to pick), while the real `<select>`
  stays in the DOM - visually hidden via CSS clip, not the `hidden`
  attribute, since a `hidden` element is barred from constraint validation -
  and remains the single source of truth for value/`required`/FormData, so
  none of the existing validation, duplicate-player, or submit-gating code
  needed to change. Typing garbage that doesn't match a real name and
  clicking away reverts the visible text to the last valid selection (the
  underlying value never left that state anyway). *Why not a `<datalist>`?*
  It doesn't enforce picking an actual list entry, which would let a typo'd
  name slip into the league workbook unresolved.
- **2026-09-08 — Fixed inconsistent player names on Weekly Score Upload**
  (same person showing as e.g. "Tousif" in one match and "Mohammad Tousif"
  in another). Root cause: `weekly_score_service._player_options()` had two
  paths that disagreed - when Spond had confirmed attendees for the date it
  resolved to the league's short/nickname form via `resolve_attendee_names()`
  (e.g. "Tousif"), but whenever Spond had nothing for that date (unreachable,
  or nobody confirmed yet) it fell back to `player_service.get_player_names()`
  - full "First Last" names from the member CSV. Which path ran depended on
  Spond's state at the moment each dropdown loaded, so the *same* player
  could get submitted under either form across different matches. Fixed by
  falling back to `league_service.get_league_roster()` instead - already in
  the club's short form, so the fallback path now agrees with the
  Spond-resolved one; full names are only a last-resort fallback if a
  season has no roster at all yet. This fixes the dropdown for *new*
  submissions only - already-submitted rows using the old full-name form
  need a quick Amend (re-pick from the now-consistent dropdown) to match.
- **2026-09-08 — Fixed Amend silently swapping a player to an unrelated name
  after ~10s, added a match-count badge.** The 10s background poll
  (`fetchState` → `render` → `refreshFormOptions`) rebuilds *every*
  `.player-select` on the page each time it fires, including the ones inside
  an open Amend modal someone is actively editing - it only ever used the
  general attendance list (`state.players`), not the extra match-specific
  names (e.g. an older full-name value) merged in when that modal was
  opened. Losing that value mid-rebuild left the `<select>` with no option
  explicitly marked `selected`, and browsers resolve that by silently
  picking the first enabled option instead of falling back to the
  placeholder - which alphabetically was near-always the same name
  ("Altamash" in this club's roster), overwriting whatever the field
  actually held with no visual cue. Reproduced and confirmed fixed with a
  Playwright test that opens Amend, waits past the poll interval, and checks
  the field's value survived. Two-part fix in `weekly_scores.js`: (1)
  `refreshFormOptions()` now always keeps a select's current value in its
  own option list before rebuilding, regardless of whether it's in the
  general list; (2) `populatePlayerSelect()` decides up front whether the
  current value is restorable and marks exactly one option selected either
  way, so any future case where a value truly can't be restored falls back
  to the visible "Select player…" placeholder rather than silently landing
  on an arbitrary real name. Also added a match-count badge next to the
  "Scores" heading (`#matchCount`, updated in `renderTable()`).
- **2026-09-08 — Weekly Score Upload's player dropdown now reads past dates
  from the signup-history cache, not a live Spond query.** Live reports for
  the 6-Sep session: a player who didn't attend appeared in the dropdown
  (someone already in the league roster) and one who did attend was missing
  (not yet added to that roster) - the signature of the dropdown having
  fallen through to the roster-wide fallback for that date rather than
  actually reflecting who played. A live Spond query for an already-past
  date isn't something this app could verify as reliable (no way to test
  against real Spond servers from this dev environment) - it may simply
  return nothing for a past date, or something else may be off; either way,
  the dropdown ended up wrong. Since attendance for a date that's already
  happened is settled, `weekly_score_service._player_options()` now reads
  `data/signups_history.csv` (the existing per-player-hours RSVP cache -
  see `analytics_service.py`) for any date that's today or earlier, filtered
  to exactly that date's accepted RSVPs, and only falls back to a live
  Spond query if that cache has nothing yet for the date (e.g. too recent
  to have synced - prompt an **Admin → Refresh Signup Analytics** to force
  it). A genuinely future date (session opened ahead of time) still queries
  Spond live, since attendance for it is still changing. This also
  incidentally satisfies "don't keep polling Spond for a date that's already
  happened" - once the cache has that date, the 10s state-poll no longer
  makes any live Spond call for it, just a local CSV read.
- **2026-09-08 — `fetch_signups_history()` refuses to overwrite the cache
  with a suspiciously small fetch.** Live incident: an Admin → Refresh Signup
  Analytics click landed right after what looked like a transient Spond
  hiccup (the same hiccup that briefly emptied the Calendar's live session
  list) - `data/signups_history.csv` gets **fully overwritten** on every
  call with whatever that run's live Spond fetch returns, no exception
  needed, so a fetch that "succeeds" but comes back incomplete (Spond
  rate-limited/truncated rather than erroring outright) would silently wipe
  out real cached history - in this case seemingly losing 6-Sep's attendees,
  which then vanished from the Weekly Score Upload dropdown. Fixed by
  refusing the overwrite (logging instead, keeping the existing cache) when
  the new fetch has fewer than half the rows already cached, but only once
  the cache is non-trivial (>20 rows) so a genuinely small early-season
  dataset can still grow normally. There's no legitimate scenario where a
  real 6-month rolling history halves overnight, so this only ever blocks
  what looks like a bad fetch.
- **2026-09-08 — Fixed the real root cause of the recurring Weekly Score
  Upload dropdown flakiness: a non-atomic CSV write race, not a filtering or
  caching bug.** After two earlier fixes (the historical-cache lookup and the
  partial-overwrite guard, both above) the *exact same* symptom kept coming
  back - the wrong players in the 06-Sep dropdown, self-correcting minutes
  later with no admin action. That "self-correcting" pattern was the
  giveaway: `fetch_signups_history()` and `aggregate_hours()` both wrote
  their CSVs (`signups_history.csv`, `player_hours.csv`) via plain
  `open(path, "w")`, which truncates the file immediately and then streams
  rows out over however long the write takes. Render runs `gunicorn
  --workers 1 --threads 4`, so all requests share one process and
  filesystem; `analytics_service.maybe_refresh_async()` fires this same
  `refresh_now()` in a background thread on *every* stale Players/Calendar
  page load (admin's manual "Refresh Signup Analytics" button hits the same
  path). Any request landing on `/weekly-scores` while that background
  thread was mid-write - e.g. the admin refreshing on one tab while checking
  the dropdown on another - would read `signups_history.csv` while it was
  truncated or partially rewritten, silently dropping some of that Sunday's
  attendees until the write finished a moment later. Confirmed with a
  synthetic race test (slow writer thread + concurrent reader) that this
  reproduces exactly the "some players missing, others wrongly present,
  fine again shortly after" behaviour reported live. Fixed with a small
  `_atomic_write()` helper (write to a same-directory temp file, then
  `os.replace()`) used by both CSV writers, so a concurrent reader always
  sees either the complete old file or the complete new one, never a
  half-written one - re-ran the race test against the fix with zero partial
  reads. *Why this and not another `_historical_attendees()` tweak?* The
  prior two fixes were correct changes but were treating symptoms of a data
  source that was intermittently self-corrupting from a race, not a stale or
  wrongly-scoped source - no amount of query-logic fixing would have made
  a torn read complete.
- **2026-09-08 — Added an admin diagnostic view for the Weekly Score Upload
  player dropdown** (`weekly_score_service.debug_player_sources()`,
  `GET /weekly-scores/admin/debug-players?date=YYYY-MM-DD`, `admin_required`).
  The 06-Sep dropdown mismatch (wrong players showing/missing) reportedly
  recurred live even after the atomic-write fix above, which would have
  fully explained an intermittent version of the symptom but not one that
  persists after a fresh refresh. Rather than guess a fourth root cause
  blind (no live/production access from this dev environment - see the
  Spond credentials note), this returns every stage of the resolution chain
  as JSON for a given date: raw `signups_history.csv` rows for that date,
  historical-cache raw/resolved, live Spond raw/resolved, the league
  roster, and the final computed dropdown - so the actual broken stage can
  be read off real data instead of inferred. Verified locally against
  synthetic CSV rows that the pipeline itself correctly includes/excludes
  attendees by date when the source rows are correct.
- **2026-09-08 — Added a live per-court match count to Weekly Score Upload.**
  The club wants roughly equal matches across all 4 courts each Sunday, but
  there was no visibility into the split while scores were being entered -
  only after the fact by counting rows in the results table (Court 1 was
  reportedly lagging noticeably behind the others). Added a
  `renderCourtCounts()` badge row (`#courtCounts` in `weekly_scores.html`)
  above the Scores table, recomputed on every add/amend/delete and on the
  10s poll alongside the existing match-count badge; any court behind the
  busiest court gets a warning-coloured badge so an admin steering players
  onto quieter courts can see the imbalance at a glance. Verified in a real
  browser (Playwright) against a locally-seeded session with an
  intentionally uneven court split.
- **2026-09-08 — Found and fixed the true root cause of the recurring Weekly
  Score Upload dropdown mismatch: Refresh Signup Analytics was reporting
  false success.** The new `debug-players` diagnostic (above) showed
  `signups_history.csv` had nothing past 2026-09-02 despite several admin
  refresh clicks since - with no cached or live attendance for 06-Sep, the
  dropdown was silently falling back to the static league roster (every
  registered player, regardless of whether they actually played that
  Sunday), which is exactly why Deepesh (on the roster) kept showing and
  Ziad/Vivek (not yet added to the roster) kept being missing, deterministically,
  no matter how many times it was refreshed. Root cause:
  `fetch_signups_history()` returned `0` for both a real failure/guard-block
  *and* a legitimately-empty fetch, and `refresh_now()` called
  `_write_last_fetched()` unconditionally regardless - so a silently-failing
  (or partial-overwrite-guard-blocked, see the earlier 2026-09-08 entry)
  Spond fetch still got the cache stamped "fresh" every time. That both told
  the 7-day background auto-refresh there was nothing to do, and made every
  admin refresh click report a hollow success (`aggregate_hours()`'s nonzero
  player count, recomputed over the same stale cache, masked the fetch
  itself having done nothing). Fixed: `fetch_signups_history()` now returns
  `None` specifically for a failed/blocked fetch (distinct from a
  legitimate empty one); `refresh_now()` only stamps `last_fetched` on an
  actual success; the admin flash message and background-refresh log now
  say plainly when a refresh did **not** update the cache instead of
  reporting success regardless. Verified locally: a failing fetch leaves
  `signups_meta.json` unwritten and is reported as a failure; a mocked
  successful fetch writes it and reports the real row count. *Why this
  wasn't caught by the two earlier "transient" fixes:* those (correctly)
  hardened against a bad fetch corrupting good data, but neither one made a
  failing fetch stop pretending to have succeeded - the actual gap.
- **2026-09-08 — Found and fixed the actual root cause underneath the whole
  Weekly Score Upload dropdown saga: a Spond login rate-limit storm from
  zero request caching.** Live server logs (visible to the admin, not to
  Claude - this dev environment has no production access) showed
  `429 ... url='https://api.spond.com/core/v1/auth2/login'` even before
  manually clicking Refresh Signup Analytics. `spond_service.
  get_confirmed_attendees()` performed a brand-new Spond login on every
  single call, with no caching anywhere. It's called from
  `weekly_score_service._player_options()` on every
  `/weekly-scores/api/state` poll (10s interval, `weekly_scores.js`) -
  unconditionally for a future-dated still-open session, and, once the
  signup-history cache fell behind (see the refresh-false-success fix
  above), for a past date too on every single poll. From just one open
  browser tab that's hundreds of fresh Spond logins per hour - enough to
  trip Spond's own rate limiting, which in turn starved the legitimate
  signup-history refresh of the same login capacity, making the stale
  cache unable to ever recover on its own: a self-inflicted, self-sustaining
  loop the app had no way to break out of by itself. Fixed with a 120s
  in-process cache in `get_confirmed_attendees()`, keyed by date, caching a
  failed/empty result too (not just success) - retrying a rate-limited
  endpoint every 10s only prolongs the rate limit. Verified locally: 5
  rapid calls (simulating 5 poll cycles) now trigger 1 real Spond fetch
  instead of 5. *Why this wasn't caught by the earlier fixes today:* every
  prior fix (atomic write, false-success masking, the diagnostic view) was
  correct and necessary but treated the signup-history side; this is a
  wholly separate code path (`get_confirmed_attendees`, not
  `fetch_signups_history`) that only became visible once the false-success
  masking was removed and a real error started showing up in the logs -
  a case where fixing one bug's silence was what surfaced the next bug.
- **2026-09-08 — Live-verified the Weekly Score Upload dropdown fix chain end
  to end; saga closed.** Once Spond's own rate limit (from the login storm
  above) cleared, a real Refresh Signup Analytics succeeded (1364 signup
  rows, 47 players), and the `debug-players` diagnostic for 06-Sep then
  showed everything lined up: `signups_history.csv` has both real Eastwood
  9-10/10-11 events for that date with the actual 20 attendees, the
  historical-cache resolution and final dropdown both list Ziad and Vivek
  and correctly exclude Deepesh (who's only in the static league roster, not
  that Sunday's real attendance). Confirms all four fixes were needed and
  each was necessary but not sufficient alone: the atomic CSV write (no
  torn reads), the honest refresh-failure reporting (surfaced the real
  error instead of masking it), the Spond login-storm cache (let a refresh
  actually succeed instead of perpetually rate-limiting itself), and the
  historical-cache-first lookup from 2026-09-08 earlier (the original fix,
  correct all along but starved of real data by the other three bugs). No
  further action needed unless a new symptom appears.
- **2026-09-08 — Fixed a live incident: duplicate score submissions and
  site-wide slowness on Weekly Score Upload.** Reported live during active
  Sunday score entry: the same match appearing 4-5x, and unrelated pages
  (Dashboard included) running very slowly. Two compounding bugs: (1)
  `weekly_scores.js` never disabled the Submit/Save buttons while a request
  was in flight, so a slow response looked like nothing happened and a
  repeated tap fired another full POST, creating another identical match.
  (2) `weekly_score_service._save()` ran `r2_service.upload_file()`
  synchronously, inline in the request thread, on every single
  add/amend/delete/open/close - `upload_file()` retries up to 3x with
  exponential-backoff sleeps on any hiccup, and Render gives this app only 4
  threads total (`gunicorn --workers 1 --threads 4`), so a burst of the
  duplicate submissions from bug #1 - each blocking on its own R2 upload -
  was enough to starve every thread, hanging completely unrelated pages.
  Fixed: the submit/save buttons now disable synchronously the instant a
  request starts (restored via the existing gate functions in `.finally()`);
  the R2 upload now runs in a daemon background thread instead of blocking
  the request; `add_match()` also gained a server-side safety net that
  treats a resubmission of the exact same match (same 4 players + scores,
  regardless of team order) within 15 seconds as a duplicate tap/retry and
  returns the existing row instead of creating another one - covers cases
  the client-side lock can't (a genuine network retry, a second device).
  Verified: 5 rapid identical `add_match()` calls collapse into 1 stored
  match; `_save()` returns in ~1ms instead of blocking for a mocked 2s R2
  upload; an end-to-end Playwright test against a real browser + an
  artificially-slowed API route confirmed 4 rapid clicks on Submit produce
  exactly 1 match. The duplicate rows already created before this shipped
  were manually deleted by the admin and independently re-verified clean
  (15 matches, 0 flagged by the existing pink-highlight duplicate logic).
- **2026-09-08 — Added a lock around the Weekly Score Upload session's
  read-modify-write.** Raised by the admin while discussing whether the
  session even needs R2 for performance (it had already been made
  non-blocking, see the fix above) - the more relevant risk for several
  people entering scores at once turned out to be a completely separate bug:
  `_load()`/`_save()` had no locking, so two near-simultaneous submissions
  could both read the same "before" state, each append their own match, and
  the second write would silently overwrite the first with no error to
  anyone. Added a module-level `threading.Lock()` (`_session_lock`) that
  every function touching the session file now holds for its full
  read-modify-write cycle (`get_state`, `open_session`, `close_session`,
  `add_match`, `amend_match`, `delete_match`, and the read/unlink parts of
  `submit_to_database` - its slow `write_weekly_scores()` Excel call stays
  outside the lock so it doesn't block `get_state()` polls, safe because
  every mutating function requires status "open" and this session is
  already "closed" by then). `_load()`/`_save()` themselves stay lock-free
  since the lock isn't reentrant and callers already hold it. Verified the
  race was real, not hypothetical: reproduced the pre-fix unlocked pattern
  under 20 concurrent submissions with a realistic artificial write delay
  and it lost 19 of 20 matches; the same test against the locked version
  keeps all 20. Re-ran the existing duplicate-tap, amend, delete and close
  tests to confirm no regressions. *Why keep R2 rather than drop it for
  speed, as originally asked?* Render's filesystem is ephemeral and resets
  on every deploy, not just spin-down/wake - 3 hotfixes shipped today while
  this exact session was live, and without R2 each one would have wiped it;
  the R2 upload no longer blocks requests anyway, so dropping it wouldn't
  meaningfully improve performance further.
- **2026-09-08 — Added a per-player match filter (Total/Won/Lost badges) and
  switched Weekly Score Upload dates to DD-Mon-YYYY display.** (1) A
  dropdown above the Scores table lists everyone with a match on the board -
  the union of the current attendance list and every `p1`-`p4` actually
  recorded in `state.matches`, not just the attendance list alone, since
  testing surfaced that a player can have real matches without being in
  that list (the same class of gap Amend already guards against - see the
  earlier 2026-09-08 Amend-prefill fix). Selecting a name filters the table
  to their matches and shows Total/Won/Lost badges, computed client-side in
  `weekly_scores.js` (`computePlayerStats`) from data already on the page -
  a Sunday session averages ~8 matches per player over 2 hours, previously
  only checkable by scanning every row. (2) Dates now display as
  `06-Sep-2026` instead of `2026-09-06` everywhere on the page (Scores
  heading, admin Open/Closed banners, the "session opened for ..." flash
  message) via a new `format_display_date()` in `weekly_score_service.py`
  (registered as the `display_date` Jinja filter in `app.py`) and a
  matching JS `formatDisplayDate()` for the client-rendered poll path; the
  date-picker input and the hidden Reopen form field deliberately stay ISO
  since the browser/server still parse those as real form values. Verified
  in a real browser (Playwright): no raw ISO date string anywhere in the
  rendered page; a seeded session where a player is only in the match data
  (not the attendance list) is still filterable and shows correct
  Total/Won/Lost.
- **2026-09-08 — Fixed the player-filter Total/Won/Lost badges staying
  visible with stale numbers after switching back to "All players".** Root
  cause: `#playerFilterStats` had Bootstrap's `d-flex` class (`display: flex
  !important`) in its static markup at the same time the JS toggled the
  `hidden` attribute to show/hide it - the browser's built-in
  `[hidden]{display:none}` rule carries no `!important`, so Bootstrap's
  always won and the element never actually hid, regardless of the
  attribute; it just kept rendering whichever player's numbers were
  computed last. Fixed by only adding `d-flex`/`flex-wrap` via `classList`
  when a player is actually selected (removing them otherwise, so `hidden`
  works cleanly with nothing overriding it), plus explicitly resetting all
  three badge values to `"0"` when the filter is cleared as defense in
  depth. Verified with a real browser (Playwright) checking **actual
  computed style** (`getComputedStyle(...).display`), not just the `hidden`
  attribute - which is exactly what let this ship unnoticed the first time
  (the earlier test only checked `el.hidden`, true regardless of whether it
  visually did anything).

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
- [x] **Removed the dead `SUPPORTED_DOUBLES_YEARS` constant** — it was never read;
  years are discovered by filename glob. Done 2026-06-29.
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
gh pr merge <n> --merge --delete-branch        # 4. merge immediately via gh CLI
git checkout master && git pull                # 5. sync local master
```

**Claude merges every PR itself via `gh pr merge --merge --delete-branch`
right after opening it — do not wait for a manual GitHub UI merge as a
checkpoint.** Use `--merge` (not squash/rebase) to match this repo's
merge-commit convention (see recent history, e.g. "Merge pull request #27
from ..."). This applies every time, not just when explicitly asked per-PR.

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
