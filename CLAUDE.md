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
  player_routes.py      # /players (+ Analytics tab), profile pages, add/edit/delete profile,
                        #   /players/rankings (Club Rankings, admin-only until published)
  photos_routes.py      # /photos gallery + per-event photos + profile photo uploads;
                        #   event summary view/save + Claude AI assist endpoint (admin)
  hours_routes.py       # /api/hours-played/* JSON (most-active, inactive, per-player)
  admin_routes.py       # /admin, /admin/login, Spond Refresh, Refresh Signup Analytics,
                        #   Refresh Data from R2, club + podium photo mgmt; admin_required
  feedback_routes.py    # /feedback, /feedback/submit, /feedback/status, /feedback/delete (admin)
  weekly_score_routes.py # /weekly-scores + api/ (add/amend/delete) + admin/ (open/close/submit)
  rules_routes.py        # /rules (Club Rules - rotation, sitting out, pool play sections)
  sunday_pools_routes.py # /sunday-pools + /sunday-pools/generate (admin) - Sunday Pool Play
  vote_routes.py         # /vote + /vote/results + /vote/admin/toggle-* (admin) - Top 20 Player Vote
services/               # Business logic + data parsing (the heart of the app)
  spond_service.py      # Live Spond fetch: events (calendar) + members (CSV) + per-date confirmed
                        #   attendees (get_confirmed_attendees, for Weekly Score Upload, and
                        #   get_confirmed_attendees_for_hour, for Sunday Pool Play's 10-11 slot
                        #   only); _parse_timestamp, LOCAL_TZ
  calendar_service.py   # Weekly sessions (via Spond) + annual events (Excel)
  excel_service.py      # load_excel/save_excel + load_workbook_normalized() (backslash-zip fix)
  tournament_service.py # Generic tournament CRUD + Doubles .xlsm parser
  championship_service.py
  league_service.py     # Also: get_league_roster/resolve_attendee_names + write_weekly_scores()
                        #   (writes Weekly Score Upload matches into the live season's .xlsm)
  league_analytics_service.py # All-time cross-season League analytics (/tournaments/league/analytics):
                        #   leaderboards, pairs, records, rivalries, milestones; mtime-keyed cache
  weekly_score_service.py # Weekly Score Upload session (data/WeeklyScoreSession.json): open/close/
                        #   add/amend/delete/submit-to-database, duplicate-row detection
  player_service.py     # Reads hhb_members.csv, merges stats + signup hours, ranks players
  player_stats_service.py # Computes per-player tournament stats + HHB Score (cached)
  analytics_service.py  # Signup-hours pipeline (Spond RSVPs → CSV → per-player hours) +
                        #   club analytics + lazy weekly background auto-refresh
  profile_service.py    # name_to_slug() + player profile data (jinja `slugify` filter)
  club_rankings_service.py # Manually-curated Club Rankings (data/club_rankings.json): ordered
                        #   player list + visible_to_public flag + move_player() up/down +
                        #   add_player() (admin-inserts an unranked club member at a chosen position)
  club_rules_service.py # Club Rules page copy (data/club_rules_content.json): rotation,
                        #   sitting_out, pool_play sections (see about_content_service pattern)
  sunday_pools_service.py # Sunday Pool Play (data/sunday_pools.json): generate_pools() splits
                        #   a date's confirmed 10-11am Spond sign-ups into Pool A/B by the
                        #   current Club Rankings order and publishes to /sunday-pools
  vote_service.py       # Top 20 Player Vote (data/player_votes.json): member Top-10 ballots,
                        #   admin voting_open/results_published flags, compute_rankings()
                        #   (pure Borda-scoring function) - see Decisions Log for why JSON,
                        #   not the Excel workbook the original feature spec asked for
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
- Top 20 Player Vote (`/vote`, `/vote/results`): tap-to-rank Top 10 ballot
  from the current Club Rankings Top 20, admin-controlled `voting_open`/
  `results_published` flags via a card on `/admin`. Not yet linked from
  the nav — direct-URL-only until the admin is ready to announce it.

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
- **2026-09-09 — Updated 2026 League Rule 3 for Weekly Score Upload; dropped
  rules 5 and 8.** The score-reporting rules were still WhatsApp-based, now
  obsolete since `/weekly-scores` replaced that flow. Rule 3 rewritten and
  split into two (the admin's own suggestion, since the combined text was
  getting long): report scores via the Weekly Score Upload page (with a
  link), plus a new rule 4 for the Hall-connectivity fallback (note matches
  on your phone, upload once back online). Old rule 5 (a separate "League
  Scores HHB" WhatsApp group for reporting) removed outright; old rule 8
  (the WhatsApp message-format example, e.g. "Sengole/Vishal bt Purvaiz/
  Vasu 21/17 - (Court 3)") removed since the web form's own required fields
  make a free-text format unnecessary. Net 18 rules -> 17, renumbered
  sequentially in the `PointRules` sheet of `tournaments/HHB Annual Players
  League - 2026.xlsm` via a one-off openpyxl script (following this repo's
  established `load_workbook_normalized(..., keep_vba=True)` pattern from
  `league_service.py`, per the xlsx skill's guidance on editing `.xlsm`
  files) - every other rule's text and all other sheets (standings, match
  data, Dates, MatchRules) verified untouched via `get_league(2026)`
  afterward. Also wired the existing `linkify` Jinja filter (already used
  on the Charity page) into the Rules tab's rendering, since rule 3 now
  contains a URL for the first time - it was plain-escaped text before,
  so the weekly-scores link would otherwise have rendered as dead text.
  Verified in a real browser (Playwright): 17 rules render correctly, no
  leftover WhatsApp/format wording anywhere, rule 3's URL renders as a
  working `<a href>` link. *Important:* this only updated the **git-tracked
  copy** of the workbook - Render serves data from R2, not git, and this
  session has no R2 credentials, so the live site won't reflect this change
  until the admin runs `scripts/seed_r2.py` locally to push the updated
  file (same gap as the 2026-09-01 "Sync 2026 Players League scoresheet"
  precedent commit, where the live update went out via seed_r2.py first
  and the git sync followed after).
- **2026-09-10 — Fixed a real security gap: anyone could delete anyone's
  Weekly Score Upload match.** The "Del" button was shown to every visitor
  while a session was open, and the underlying route (`POST /weekly-scores/
  api/matches/<id>/delete`) had **no auth check at all** - hiding the
  button alone would have been cosmetic, since anyone could still call the
  API directly. Fixed both layers: `api_delete_match` now has
  `@admin_required` (matching the convention already used for open/close/
  submit), and `weekly_scores.js` only renders the Del button when
  `window.WEEKLY_SCORE_IS_ADMIN` is true (already injected into every page
  load, previously unused). "Edit" (amend) stays open to everyone,
  unrestricted, per the admin's explicit request - only Delete needed
  gating. Verified with a Flask test-client (unauthenticated delete
  redirected and the match confirmed still present afterward; amend still
  succeeds unauthenticated; an admin session deletes normally) and in a
  real browser via Playwright, using a signed session cookie (built from
  `app.session_interface`, since local dev has no `ADMIN_USERNAME`/
  `PASSWORD` configured to log in with) to simulate an admin: a non-admin
  visitor sees Edit but zero Delete buttons anywhere on the page; an admin
  sees Delete and can use it end-to-end through the real UI.
- **2026-09-10 — Weekly Score Upload: match numbers, League Rule 6
  highlighting, reordered columns/forms.** (1) Removed the "this court has
  fewer matches..." footer note under the results table - the admin didn't
  want text that could read as encouraging players to pick a court number
  to balance the count rather than reporting whichever court they actually
  played on; the per-court badge colouring itself is untouched, so the
  imbalance is still visible at a glance, just without the instructional
  framing. (2) Added a Rule 6 ("only ONE win with a specific partner on a
  given Sunday") enforcement aid: `weekly_score_service._winning_pair()`
  identifies the winning team regardless of which slot (Team 1/2) it was
  entered into, and `_annotate()` flags `is_repeat_winner` when that pair
  already won another match today - deliberately separate from
  `is_duplicate` (a literal same-match repeat) since two matches can share
  a winning pair while being genuinely different matches (different
  opponents/scores), so it gets its own light-blue row colour rather than
  being folded into the pink duplicate highlight (duplicate wins if a row
  is somehow both). (3) Added a stable `match_number` (1-based, chronological
  submission order, independent of the table's current newest-first display
  sort) as the new first column, so the admin can say "delete match 7"
  unambiguously regardless of how the table is sorted; `Ct` moved to the
  last data column, and the two score columns now sit adjacent in the
  middle (`Team 1 | Sc | Sc | Team 2`) since Team 1 is already
  green-highlighted as the winner. (4) Reordered the "Enter a Score" form
  and Amend modal fields to match: Court No., Team 1 Player 1/2, Score,
  Score, Team 2 Player 1/2. (5) Confirmed, no change needed:
  `submit_to_database()` already sorts matches ascending by `submitted_at`
  before writing, and `write_weekly_scores()` fills rows in that exact
  order, so matches already land in the league workbook in the same
  chronological order as `match_number`. Verified `_annotate()` directly
  against synthetic data (duplicate and repeat-winner flags computed
  independently and correctly) and end-to-end in a real browser
  (Playwright): new column order, correct row colours, removed footer text
  with the new Rule 6 legend in its place, retained court-badge colouring,
  matching field order in both forms.
- **2026-09-10 — Fixed League Table standings, Matches tab layout, and added
  League Rule 6 auto-strike-off, after the first real Weekly Score Upload
  submission (32 matches, 6-Sep) exposed all three.** (1) `get_league()`'s
  Final Standings rank/order (and now Played/Won/Lost/Points/PF too) had
  been read straight from a static Excel Rank/Name block that
  `write_weekly_scores()` deliberately never resorts (see its docstring) -
  correct the moment scores were hand-entered in rank order, but stale as
  soon as the automated Weekly Score Upload flow started writing real
  results: a 0-played player (Yogi) stayed near the top of the table, and a
  high-win player (Waqas, 8 wins) didn't rise, and no amount of client-side
  re-sorting in `league_detail.html` could fix it since that JS's "Won
  desc" default view just restores the (stale) server-rendered order.
  Fixed by computing every standings number in Python directly from the
  parsed `matches` list instead of trusting the sheet: Played/Won/Lost via
  simple counters, point-differential (NPD) computed from each match's
  score margin rather than the sheet's Points-Against column (a live SUMIF
  formula that reads back blank after any openpyxl save - the same
  cache-wipe issue documented on `write_weekly_scores`), then sorted by
  Wins -> NPD -> Win% -> name per League Rule 9 ("Rankings will be based on
  number of WINS, then NPD and then WIN %"); the sheet's Rank/Name block is
  now read only to source the season's player roster (so a 0-match player
  still appears, correctly last). (2) The "Matches" tab table reused the
  Calendar page's `.sticky-table-wrapper` CSS class verbatim, including a
  hardcoded 64px offset for a 2nd frozen column tuned for Calendar's narrow
  "Day" abbreviation - wrong for this table's "#" match-number column,
  which pushed the frozen "Date" column visually on top of "Team 1". Fixed
  with `#matchesTable`-scoped overrides: only "Date" freezes now (at the
  left edge), "#" scrolls normally instead of getting its own hardcoded
  offset, and the shared `nth-child(5)` rule (meant for Calendar's numeric
  "Confirmed" count) no longer force-squeezes this table's actual 5th
  column ("Team 2", a name) into a narrow centered/nowrap style. (3) League
  Rule 6 ("only ONE win with a specific partner on a given Sunday") had
  already been violated in the live 6-Sep submission before anyone caught
  it (Waqas/Nawaz and Santosh/Mansoor each won twice) - rather than require
  a manual Excel fix, `get_league()` now detects a winning pair's 2nd+ win
  on the same date automatically (a forward scan over `matches`, which are
  already in chronological submission order per `write_weekly_scores()`'s
  own docstring) and marks it `is_struck_off`: excluded from standings and
  *every* analytics calculation (pair records, court usage, score
  frequency, Overall Stats' per-week totals, etc. - built from a new
  `counted_matches` list with struck-off rows removed) while still shown in
  the Matches tab, greyed out with strikethrough and a "Struck off" badge,
  so the double-report stays visible without corrupting any numbers. (4)
  Separately, the Weekly Score Upload page's own pre-submission
  `repeat-winner-row` highlight (added earlier the same day) apparently
  didn't visually register during the live 6-Sep session despite the two
  known repeat pairs - re-verified `_annotate()`/`_winning_pair()` end to
  end against a synthetic repeat-winning-pair session and found the
  detection logic itself correct (confirmed the admin submitted all 32
  matches in one continuous open session, ruling out the one structural gap
  this feature has: it can only compare matches within the *current*
  session, so submitting to the database mid-Sunday and reopening for more
  entries would hide an earlier win from later detection - not what
  happened here). Best remaining explanation is that a plain pale-blue
  background alone was too subtle to notice live on a busy phone-sized
  table, so strengthened it regardless of root cause: added a blue left
  accent border plus an explicit "Repeat win" badge next to the winning
  team's name. Verified standings sort and strike-off logic against
  synthetic match data, and both the Matches tab CSS fix (against real 2024
  season data) and the strengthened repeat-winner highlight (against a
  synthetic session) visually via Playwright. *Why not also fix "Overall
  Stats: Total Players Playing not populated for 6-Sep"* (also raised the
  same day)? Traced to `_historical_players_playing()`'s dependency on
  `data/signups_history.csv`, verified correct against synthetic data - the
  live blank cells are most likely the same class of stale-cache issue
  already root-caused multiple times earlier this week (see the 2026-09-08
  entries), fixable via Admin → Refresh Signup Analytics, not a code bug
  this sandbox could confirm without production access; left as a follow-up
  if refreshing doesn't resolve it.
- **2026-09-10 — `styles.css` now cache-busted like `weekly_scores.js`; the
  previous day's Matches tab CSS fix had shipped but a real phone still
  showed the old broken layout.** Root cause: `base.html`'s stylesheet
  `<link>` used a fixed `/static/styles.css` URL with no versioning, so the
  Cloudflare Worker reverse proxy (or the phone's own browser cache) could
  keep serving pre-deploy bytes indefinitely - exactly the failure mode the
  `asset_version()` Jinja global was built for on 2026-09-07, but that fix
  was only ever applied to the `weekly_scores.js` script tag, never to
  `styles.css` itself, even though the stylesheet is loaded on every page
  and just as vulnerable. Added the same `?v={{ asset_version('styles.css')
  }}` to `base.html`'s `<link>`, closing the gap site-wide rather than
  per-page. Also tightened `#matchesTable`'s "#" column padding specifically
  (the shared mobile media query's touch-friendly padding bump left a
  disproportionately wide gap around a 1-2 digit match number). Verified
  `styles.css` now serves with a `?v=<mtime>` param, and the Matches tab
  layout visually via Playwright at a real phone viewport (412×915, 2.6x
  DPR) against real 2024 league data.
- **2026-09-10 — Hid 0-match players from Final Standings; hid "Top Pairs by
  Wins" until the season has 3+ Sundays of data.** (1) A player with 0
  counted matches (not yet played this season, or whose only appearance was
  a struck-off match) is now excluded from `get_league()`'s `standings`
  list entirely, not just filtered in the template - so the "#" rank stays
  a consecutive number among actual participants (no gaps from a filtered
  row), and the exclusion automatically applies everywhere else that reads
  `standings` too: `top_players_courts`, the champion/runner-up/third
  lookups, and HHB Score's per-season participation level in
  `player_stats_service.py` (a player shouldn't get a "participated" credit
  for a season they haven't actually played in yet). (2) The Analytics
  tab's "Top Pairs by Wins" card is now gated on `a.total_sundays >= 3` -
  with only 1-2 Sundays played, a pair's win/loss record is too small a
  sample to be meaningful, and (per the existing `pair_records` threshold)
  it wasn't showing much useful data that early anyway. Verified both
  against synthetic data and against real, complete 2024 season data (no
  regressions: all 25 standings entries have played > 0, 10 top pairs still
  show at 11 Sundays).
- **2026-09-10 — Shortened Matches tab dates to "6-Sep"; fixed Season End
  showing the last match's date instead of the real scheduled end.** (1)
  Each Matches tab row now shows a new `date_short` field ("6-Sep") instead
  of the shared `_fmt_date()` output ("06 Sep 2024") - a season never spans
  a year boundary, so the year was pure column width Team 1 needed on a
  32+-row phone-sized table; `_fmt_date()` itself is untouched since other
  tournament pages still use it. (2) `get_league()`'s season-dates block
  used actual match min/max dates whenever *any* matches existed rather
  than only once `is_complete` - exactly what the comment above the code
  already said was intended, just not what the code did - so the 2026
  season (only 6-Sep played so far) showed Season End as `6-Sep` instead
  of the real scheduled `22-Nov`; only correct once a season is actually
  over and the last match date and the true end coincide. Verified against
  synthetic in-progress-season data and confirmed no regression against
  real, complete 2024 season data.
- **2026-09-10 — Fixed Final Standings silently excluding players not yet in
  the season's roster block** (reported live: Ziad and Vivek had real
  6-Sep matches but were missing entirely from the table). `get_league()`'s
  standings loop only ever iterated the static Excel Rank/Name block (the
  roster an admin maintains by hand) - a brand-new player whose matches
  resolved to their plain first name via `resolve_attendee_names()`'s
  fallback (since they weren't in that roster yet) had their matches
  correctly recorded and counted toward their *opponents'* Played/Won/PD,
  but their own results never showed up until someone manually added them
  to the sheet - previously just a documented "Known issue," now fixed:
  standings cover the roster plus anyone who has actually played a counted
  match but isn't in it, so a new player can play their first Sunday before
  an admin gets to Excel and still show up correctly. Removed the
  now-stale Known-issues note. Verified against synthetic data, and
  confirmed this wasn't 2026-specific - re-running against the real,
  complete 2024 season surfaced the identical gap for "Sengole" (2 matches,
  1 win, previously silently excluded there too), now correctly included.
- **2026-09-10 — Added a League link to the Calendar page and an "Individual
  Weekly Stats" tab on the League page.** (1) The Calendar's Annual Events
  tab now shows an "IN PROGRESS » View Tournament" badge/link for the
  Annual Players League while its season is underway, mirroring the
  existing "COMPLETED » View Tournament/Championship" pattern for Doubles/
  Championships - but placed outside the `completed_2026` gate, since the
  League is deliberately never added to `COMPLETED_2026_EVENTS` until the
  season actually ends in Nov; also added a League branch *inside* that
  gate so it automatically switches to a COMPLETED link once an admin adds
  it there later. (2) New "Individual Weekly Stats" tab (next to Overall
  Stats): Played (P) and Won (W) per Sunday for every player who's played
  this season, alphabetical, one column pair per Sunday that appears as
  scores get submitted - a new `get_weekly_stats()` in `league_service.py`
  built from the same counted (non-struck-off) matches standings already
  uses. Verified `get_weekly_stats()` against real 2024 season data (11
  date columns, 26 players, correct per-week Played/Won matching the
  requested layout) and both features visually via Playwright.
- **2026-09-11 — Matches tab: taller table, no-wrap team names, "/" instead
  of "&".** (1) The scrollable wrapper's `max-height` went from `65vh` to
  `80vh` - only ~7 rows fit before scrolling on a phone. (2) Team 2 was
  wrapping onto two lines while Team 1 stayed on one - the 2026-09-10
  Calendar-CSS-reuse fix had force-set `white-space:normal` on Team 2 to
  stop it being squeezed like Calendar's numeric "Confirmed" column, but
  never revisited nowrap once that specific problem was fixed. Both team
  cells are now `nowrap`, consistent with each other. (3) Team pairs now
  display as `Vasu/Waqas` instead of `Vasu & Waqas`, saving width - only
  the display text changed; the winner bold-highlight comparison still
  checks against `m.winner` (an `" & "`-joined string from the sheet),
  untouched. Verified visually via Playwright at a real phone viewport
  against real 2024 season data: 18 rows now visible before scrolling
  (was ~7), both team columns confirmed `white-space: nowrap`.
- **2026-09-13 — Strengthened the Weekly Score Upload duplicate-row
  highlight** (reported live: matches 5/28 and 24/34 were genuine exact
  duplicates but showed no highlight). Verified `_duplicate_key()`/
  `_annotate()` against a synthetic exact-duplicate pair first - the
  detection logic itself is correct, it flags them fine. The actual gap:
  `.duplicate-row` still only had a plain pale pink background - the exact
  same "too subtle to notice on a busy phone-sized table" problem already
  found and fixed for `.repeat-winner-row` on 2026-09-10 (left accent
  border + explicit badge), just never applied to `.duplicate-row` since
  nobody had reported it as unnoticed until now. Same fix: a red left
  accent border plus an explicit "Duplicate" badge next to the winning
  team's name (still takes priority over "Repeat win" when both apply).
  Verified visually against the synthetic duplicate pair: both rows
  correctly flagged and now clearly visible, not just a faint tint.
- **2026-09-14 — Fixed Overall Stats silently stopping after Week 1 once any
  workbook save happens** (reported live: after submitting 13-Sep's scores,
  Overall Stats still only showed the 6-Sep row). Every row after the first
  in the "Overall Stats" sheet's Date column is a formula
  (`=<prev row>+7`, a straight weekly chain, off-weeks included) - only
  Week 1's date (row 4) is a literal value. Any openpyxl save anywhere in
  the workbook (a Weekly Score Upload submit included - exactly what
  13-Sep's own submission had just done) drops the cached result of every
  formula in the file, this column included (the same cache-wipe behind
  `write_weekly_scores`'s whole design - see its docstring), and
  `get_overall_stats()` was reading this column with `data_only=True` and
  breaking out of its per-week loop the moment a cell wasn't a real date -
  which is every row from week 2 onward once the cache is gone, so the
  loop silently stopped right after week 1 every time, not just for 6-Sep.
  Fixed by no longer trusting the cached formula value at all: a second
  raw (`data_only=False`) read tells "formula present, cache just stale"
  (still part of the table) apart from a genuinely empty cell (real end of
  the table), and each week's date is computed in Python from Week 1's
  literal date plus a 7-day-per-row offset, replicating what the formula
  chain would have produced. Verified against the local 2026 workbook
  (which already exhibits this exact cache-wiped state): now returns all
  10 scheduled weeks plus the 2 October break rows correctly dated,
  instead of stopping after week 1; confirmed no regression against the
  real, complete 2024 season (all 11 weeks unchanged). *Note:* this is a
  different bug from the still-open "Total Players Playing not populated
  for 6-Sep" item in the 2026-09-10 entry - that one is about Week 1's own
  player counts (likely a `signups_history.csv` cache gap) and is
  untouched by this fix, which was purely about later weeks never being
  reached at all.
- **2026-09-15 — League page: Matches tab date filter, one-click clear, and
  direct tab URLs.** Requested feedback: the Matches tab only had "Filter by
  player" and no quick way to reset it (had to reopen the dropdown and pick
  "All Players"), and there was no way to link straight to a specific tab
  (e.g. Matches or Analytics) instead of always landing on the default pane.
  Added a second "Filter by date" dropdown (populated from each match's own
  `date` field, deduplicated in sheet order) that ANDs with the existing
  player filter, plus a single "Clear Filters" button that resets both in one
  click (`weekly_scores.js`-style vanilla JS, no new dependency). For tab
  URLs, `tournament_routes.league_detail` now accepts an optional
  `/<tab>` path segment (`/tournaments/league/2026/Matches`,
  `/tournaments/league/2026/Analytics`, etc. - case-insensitive, with a couple
  of forgiving aliases like `overall-stats`/`overallstats`), mapped via a
  `LEAGUE_TAB_SLUGS` dict to the tab-pane id to activate server-side (falling
  back to the same default pane logic as before - Rules if the season hasn't
  started yet, else Final Standings - for an unknown/missing slug). Clicking
  a tab client-side also updates the address bar to match (`history.
  replaceState` on Bootstrap's `shown.bs.tab` event), so any tab reached by
  navigation is trivially linkable/bookmarkable without a page reload. Only
  applied to the League detail page (that's what was asked for) - the same
  pattern could be extended to Doubles/Championships detail pages if wanted.
  Verified in a real browser against the live 2026 season data: direct links
  to Matches, Analytics, Overall Stats, and the newer Weekly Stats tab all
  open correctly; date+player filters combine correctly (34/66 matches for a
  single Sunday, further narrowed to 7 for one player); Clear Filters resets
  both dropdowns in one click; no console errors.
- **2026-09-15 — Added a manually-curated "Club Rankings" page** (`/players/rankings`,
  `club_rankings_service.py`, `templates/club_rankings.html`), separate from
  the automated HHB Score leaderboard already on `/players`. The committee
  decided the automated ranking (weighted blend of League-last-3-years rank
  and HHB Score rank, explored earlier this session) wasn't accurate enough
  on its own, given how many active players lack recent League history - so
  this is a hand-ordered list instead, seeded from the committee's own
  34-player ranking. Storage follows the same pattern as `committee.json`/
  `charity_settings.json`: a gitignored `data/club_rankings.json`
  (`{"visible_to_public": bool, "players": [name, ...]}`, rank = list
  position + 1), created on first save and R2-backed; the initial 34-name
  order lives as a `DEFAULT_PLAYERS` constant in the service (same pattern
  `committee_service.DEFAULT_MEMBERS` uses), not committed as data. Gated
  **admin-only for now** via `visible_to_public` (defaults to `False`) - the
  route 404s for non-admins until an admin clicks "Make Public" (a small
  toggle button on the page itself); a "Club Rankings" link appears on
  `/players` for admins always, and for everyone once it's public. Admins get
  ↑/↓ buttons per row (`club_rankings_service.move_player()`, a simple
  adjacent-swap, POST + redirect - no drag-and-drop, matching what was
  asked for) instead of a raw text/JSON editor. The disclaimer text ("50%
  League last 3 years / 50% subjective committee review, reviewed twice a
  year - December around the Annual Dinner, June after the Annual Doubles
  Classic") is hardcoded verbatim as given, not admin-editable, since that
  wasn't requested. Verified in a real browser: anonymous request 404s while
  admin-only; toggling Make Public flips a fresh cookie-less `curl` request
  to 200; an ↑/↓ click swaps the two rows and persists (confirmed via the
  saved JSON); re-toggled back to admin-only afterwards, matching the
  requested starting state. *Note:* since local dev is R2-connected to the
  live bucket (see Local Tooling Notes), this session's verification clicks
  already wrote the seeded list to production R2 - harmless, since it left
  the file in exactly the intended state (original order, admin-only) and
  nothing serves that route in production yet until this deploys.
- **2026-09-15 — Removed the "How to Contribute" (bank details) section from
  the Nepal Flood Relief page.** The campaign is closed and already fully
  donated (see the "Update: Funds Donated" section), so the admin's personal
  bank account details displayed there were no longer relevant and asked to
  be removed. Dropped the whole card + its admin edit modal from
  `charity_nepal_flood_relief.html` (the standalone "Raised so far" card now
  centers alone in that row instead of sharing it), and removed
  `how_to_contribute` from `charity_service.py`'s `CONTENT_KEYS`/
  `DEFAULT_CONTENT` so it can't be re-added via the generic content-edit
  route. Also proactively scrubbed the real bank details (account number +
  sort code) out of the persisted `data/charity_content.json` **on production
  R2** (this session's local dev is R2-connected to the live bucket - see
  Local Tooling Notes) with a one-off script, rather than leaving them
  sitting unused in storage indefinitely. Verified in a real browser: no
  bank-details card or edit button anywhere on the page, no console errors,
  contributions table and the funds-donated/donation-proof section below it
  both unaffected.
- **2026-09-15/16 — Added Sunday Pool Play: a new Club Rules section, a
  published `/sunday-pools` page, and a Club Rankings "Add Player" admin
  tool.** Per a committee WhatsApp announcement, the 10-11am half of the
  Sunday session now splits into two pools by ability - Pool A (Courts 1-2)
  and Pool B (Courts 3-4) - while 9-10am stays unchanged open play. Three
  pieces:
  (1) **Club Rules**: new third accordion section "Sunday Pool Play Rules
  (10-11am)" (`club_rules_service.py` `SECTION_ORDER`/`SECTION_TITLES`/
  `DEFAULT_SECTIONS["pool_play"]`), written up from the committee's comms -
  explains the 9-10/10-11 split, how Pool A/B are formed, that the existing
  sitting-out rotation continues separately within each pool, a worked
  20-signups example table, and links to Club Rankings and `/sunday-pools`.
  (2) **`/sunday-pools`** (`sunday_pools_service.py`, `sunday_pools_routes.py`,
  `templates/sunday_pools.html`): an admin picks a date and clicks
  "Generate & Publish"; `generate_pools()` fetches that date's confirmed
  **10-11am-only** Spond sign-ups (a new `spond_service.
  get_confirmed_attendees_for_hour()`, since the existing
  `get_confirmed_attendees()` merges every event on a date - Weekly Score
  Upload wants that, Pool Play specifically doesn't), splits them by the
  current Club Rankings order (top half -> Pool A, bottom half -> Pool B,
  Pool A gets the extra player on an odd turnout, an unranked attendee
  defaults into Pool B), and publishes to `data/sunday_pools.json` (same
  R2-backed, gitignored pattern as `club_rankings.json`). The page itself is
  **public** (unlike Club Rankings) since players need to check it before
  Sunday - only the generate form is admin-gated. Historical-cache-first /
  live-Spond-fallback for the attendee fetch mirrors `weekly_score_service.
  _historical_attendees()`'s reasoning exactly (a whole day's worth of hard
  Spond-rate-limit lessons from the Weekly Score Upload saga - see the many
  2026-09-08 entries above), deliberately not re-derived from scratch.
  (3) **Club Rankings "Add Player"** (`club_rankings_service.add_player()`,
  `players.club_rankings_add` route): admin-only form on `/players/rankings`
  - a dropdown of club members not yet ranked (from `player_service.
  get_player_names()`, diffed against the current list) plus a 1-based
  position field; inserts the player there, shifting everyone at/below that
  position down one, reusing the existing move_player() up/down arrows for
  any further adjustment. *Why scoped to insert-only:* the user asked
  specifically for add-and-position, not removal - no delete function was
  built.
  Before building anything, the user asked to see a preview first (they were
  on a phone via remote control, so `localhost` links wouldn't reach them) -
  handled by publishing a static Artifact mock-up (reusing the site's actual
  `styles.css` tokens/Bootstrap classes, not a generic template) showing both
  the new Rules section and a `/sunday-pools` render with real generated data
  from a live test run. Verified in a real browser end-to-end after
  approval: `/rules?open=pool_play` opens directly on the new section;
  `/sunday-pools` generated real Pool A/B from actual 13-Sep-2026 sign-up
  data (20 players, one unranked attendee correctly flagged and defaulted
  into Pool B); anonymous `curl` confirms the generate form is admin-only
  while the pools themselves are public; Add Player correctly inserted a
  test player at #5 and shifted the rest down (then removed via a one-off
  script to restore the exact 34-player list, same as the two other
  production-R2 test-data notes above - nothing serves any of these routes
  live until this deploys).
- **2026-09-16 — Temporarily hid the Dashboard "View Club Rules" CTA and the
  Players page "Club Rankings" button** while the admin reviews the new
  Sunday Pool Play rule and the Club Rankings list with the committee live
  on the site. Both pages stay fully reachable by direct URL (`/rules`,
  `/players/rankings`) for anyone who knows/is given the link - only the
  promotional entry points are removed, via a commented-out block in
  `dashboard.html` / `players.html` (not a data flag, since this is a
  short-lived manual state the admin will ask to reverse once the committee
  is happy - a code change either way). *Note:* `players.html`'s
  `rankings_visible` route variable is now unused by the template but left
  wired in `player_routes.py`, since restoring the button later needs no
  route changes, only un-commenting the markup. Also confirmed (no code
  needed) that `/rules?open=pool_play` already gives Sunday Pool Play Rules
  the same direct-link support the other two Club Rules sections have -
  the `?open=<key>` mechanism was already generic across all sections.
- **2026-09-16 — Corrected the Sunday Pool Play rule's Sitting Out wording.**
  The original draft said each pool keeps its own arrival-order queue - the
  admin corrected this: there's only ever **one** queue (everyone signs the
  board in arrival order at 9am, same as before), since 20 players can't
  realistically split into two separate sign-in queues. The actual rule:
  work down that single queue as normal, but each round needs 2 sitting out
  from Pool A and 2 from Pool B specifically, not just the next 4 names -
  skip anyone from a pool that's already got its 2 for that round and keep
  going until both pools are covered, then mark X on the board as usual
  (`club_rules_service.py` `DEFAULT_SECTIONS["pool_play"]`). Added the
  admin's own worked example (four Pool A players due up in a row -> first
  two sit out, next two are skipped, continue to the next two Pool B
  players) verbatim, since it explains the mechanism more plainly than a
  further paragraph of prose would.
- **2026-09-15 — Added the Top 20 Player Vote** (`vote_service.py`,
  `vote_routes.py`, `templates/vote.html` + `vote_results.html`,
  `static/js/vote.js`), letting members vote their own Top 10 (ranked) from
  the club's current Top 20 (Club Rankings), identity confirmed via a name
  dropdown - no login. The feature spec that kicked this off asked for an
  Excel workbook (`player_votes.xlsx`), but that didn't fit this codebase's
  conventions: `Feedback.xlsx`, the closest Excel precedent, turned out to
  be append-only with no overwrite-by-submitter logic, and pandas
  round-tripping a row with 10 ranked-name columns plus admin flags would
  have been clunky. Storage is instead `data/player_votes.json`
  (gitignored, R2-backed), copying `weekly_score_service.py`'s pattern
  exactly: a `_vote_lock = threading.Lock()` around every read-modify-write
  cycle (Render's single-worker/4-thread setup), and a backgrounded R2
  upload so a burst of Sunday-night voting can't tie up request threads the
  way an inline upload once did for Weekly Score Upload (see the
  2026-09-08 duplicate-submission entries). A member's ballot is a dict
  keyed by their name, so resubmission is a plain overwrite - no separate
  lookup/delete-and-reinsert logic needed. The candidate list itself isn't
  hardcoded (the spec's own suggestion, if avoidable): `get_candidates()`
  reads the live Top 20 straight from `club_rankings_service.get_rankings()`,
  so it always matches `/players/rankings`. Scoring is a pure function,
  `compute_rankings()` (no file I/O, easy to test in isolation): Borda
  points (rank 1 = 10 ... rank 10 = 1, 0 if absent from a ballot), ties
  broken on the vector of #1-place votes, then #2-place, etc., then name -
  verified against a hand-computed example and against a real 10-vote test
  ballot in the browser before resetting the data file. The tap-to-rank UI
  (`vote.js`, vanilla JS matching `weekly_scores.js`'s conventions: a local
  `state`/`render()` loop, event delegation, disable-before-fetch) uses
  SortableJS (CDN, loaded only on `vote.html`) for drag-to-reorder within
  the picked Top 10 - the first drag-and-drop in this codebase; a plain
  tap-to-add/tap-to-remove flow handles everything else with no dependency.
  Per the spec's own confirmed decisions: results stay hidden from members
  behind a `results_published` admin flag (admins get an unpublished
  preview), voting can be closed behind a `voting_open` flag with no
  auto-close-by-date, and both toggle via a new "Player Vote" card on the
  existing `/admin` page (checkbox-auto-submit pattern copied from the
  Committee-visibility card) rather than a separate admin sub-page - the
  "X / Y voted" progress counter is always visible, even pre-publish,
  scoped to the full club roster like the spec asked. Verified end-to-end
  in a real browser: picked and drag-reordered a real Top 10, submitted,
  confirmed `data/player_votes.json` held the overwritten row on
  resubmission, exercised all four server-side validation failures (wrong
  count, unrecognised member, duplicate pick, non-candidate pick) directly
  against `submit_vote()`, toggled both admin flags and confirmed the
  public/admin-preview/published views all matched, then reset the vote
  data back to `{voting_open: true, results_published: false, votes: {}}`
  before finishing - since local dev here is R2-connected to the live
  bucket (see Local Tooling Notes), leaving real test data in `player_votes.json`
  would have been the same kind of stray-write the 2026-09-15 Club Rankings
  entry already flagged, even though nothing serves this route in
  production yet until this deploys. No nav link was added yet - matches
  the current state where Club Rankings/Rules promo buttons are
  deliberately hidden pending committee review (see the entry just above);
  `/vote` and `/vote/results` are direct-URL-only for now.
- **2026-09-15 — Club Rankings: non-admins now see only the Top 20, not the
  full ~35-player list; Player Vote candidates sorted alphabetically, not
  by rank.** Two follow-up requests after the two features above shipped:
  (1) `player_routes.club_rankings_page()` now slices `rankings` to the
  first 20 entries for anyone without `session.is_admin` - admins still see
  the full list (Adjust/Add-Player controls were already admin-gated, so
  this only changes what the ranked table itself shows). (2)
  `vote_service.get_candidates()` now returns the Top 20 sorted
  alphabetically (`sorted(..., key=str.casefold)`) instead of in rank
  order, per committee discussion that showing candidates in their existing
  Club Rankings order would visually bias how members pick their own Top
  10; `vote.html`'s "Top 20 Candidates" heading now says "(sorted
  alphabetically)" so it's explicit on the page. This candidate order
  change is safe everywhere else `get_candidates()` feeds into -
  `submit_vote()`'s validation is a membership check, and
  `compute_rankings()`'s final leaderboard order comes from vote points/
  tie-break, not candidate iteration order - verified both in the browser
  after a full dev-server restart (Python route/service changes need one;
  template-only edits don't).
- **2026-09-15 — Added PIN protection to the Player Vote, closing a real
  identity gap the admin caught by testing live: anyone could pick any
  member's name from the dropdown and see or overwrite their ballot.**
  A member's first submission now generates a 4-digit PIN
  (`vote_service._generate_pin()`, `secrets.randbelow`) shown to them
  exactly once in a persistent success alert; only its SHA-256 hash is
  ever stored (`pin_hash`, checked with `hmac.compare_digest`, matching
  the constant-time-compare pattern `admin_routes._check_credentials`
  already uses) - the plaintext PIN is never written anywhere, so there's
  no "forgot your PIN" recovery path other than an admin clearing the
  ballot outright. Picking a name that's already voted now shows a
  PIN-gate panel ("Vote already in for X. Enter your PIN to view or
  change it.") instead of silently prefilling their picks - the old
  `GET /vote/api/existing` endpoint (which returned a ballot's rankings to
  anyone who asked) is gone, replaced by `GET /vote/api/status` (boolean
  only, never the picks) and `POST /vote/api/verify` (returns the
  rankings only if the PIN matches). `submit_vote()` now takes an optional
  `pin` and requires+checks it whenever a ballot already exists for that
  member, reusing (not regenerating) the same `pin_hash` across edits so
  one PIN covers every future resubmission. Admins get a separate
  bypass: `/vote/results` now renders an admin-only "All Ballots" table
  (`vote_service.admin_get_all_votes()`) showing every member's picks with
  no PIN needed, plus a "Clear Vote" button per row
  (`vote_service.admin_clear_vote()`, `POST /vote/admin/clear-vote`) - the
  only way to recover from a forgotten PIN, since there's nothing to
  resend. Verified end-to-end in the browser: a fresh submission reveals
  the PIN once; the wrong PIN is rejected with the picker staying hidden;
  the right PIN unlocks and correctly prefills the exact stored order; an
  edited resubmission reuses the same `pin_hash` (confirmed via
  `verify_pin()` still matching the original PIN after the update) and
  shows a plain "Vote updated" with no PIN repeated; the admin ballot
  table and Clear Vote both worked against a real pre-PIN legacy ballot
  that the admin had left in production R2 from live-testing the original
  flaw (a vote with no `pin_hash` at all, so it was correctly permanently
  PIN-locked until cleared - expected, not a bug, since there was never a
  real PIN for it to check against). Test data reset to defaults
  afterward per the usual note about this session's local dev being
  R2-connected to the live bucket.
- **2026-09-15 — Vote page now scrolls to top on submit.** Reported live on
  mobile (where most voting happens): after tapping "Submit My Top 10" at
  the bottom of the page, the "Vote recorded"/PIN confirmation renders up
  near the "Voting as" card, off-screen below the fold from wherever the
  voter was scrolled to - looked like the submission silently did nothing.
  `vote.js`'s submit handler now calls `window.scrollTo({top:0, behavior:
  'smooth'})` right after showing either the PIN-reveal or "Vote updated"
  alert; `showError()` does the same for a failed submit, since it renders
  in the same spot and has the identical off-screen problem. Verified at a
  real 375×812 mobile viewport: picking 10 and submitting from fully
  scrolled-down auto-scrolls back to the top with the PIN confirmation
  immediately visible, no manual scroll needed.
- **2026-09-16 — Fixed Vote page copy that only made sense on desktop.**
  "Tap a name on the left to add it" / "Tap a candidate on the left to add
  them here" referred to the two-column desktop layout (candidates card
  beside the Top 10 card), meaningless once those columns stack vertically
  on mobile - reworded to "from the candidates list" / "from the list" in
  `vote.html`, which holds regardless of screen size.
- **2026-09-16 — Player Vote leaderboard now ties back to the existing
  Club Rankings order instead of alphabetically, for candidates the vote
  itself can't separate.** With 20 candidates and only 10 picks per
  ballot, it's expected that several candidates end up with zero votes (or
  tied points otherwise) - previously `compute_rankings()`'s final
  tie-break was the candidate's own name (A-Z), an arbitrary split with no
  connection to anything. Since this vote exists specifically to refine
  the committee's existing Top 20 order (see the 2026-09-15 Club Rankings
  entries), it's the fairer fallback for anyone still tied after points
  and the #1/#2/.../#10-place-vote-count vector: `compute_rankings()` now
  looks up each candidate's index in `get_rankings()["players"][:TOP_N]`
  (the *rank-ordered* Top 20, not `get_candidates()`'s alphabetical
  version used for the ballot UI - deliberately two different orderings
  of the same 20 names for two different purposes) and sorts ties by that
  index ascending, i.e. a better pre-existing committee position wins a
  tie. Verified with a synthetic vote set covering exactly 15 of the 20
  candidates (leaving 5 with genuinely zero points): the zero-point group
  came back in precisely their original Club Rankings order, not
  alphabetical - then cross-checked live against `/vote/results`' real
  data (10 candidates had points from an actual submitted ballot; the
  remaining 10 zero-point candidates rendered in exact committee order).
  *Note:* left the live ballot data untouched this session (unlike prior
  sessions' test-data resets) - its ranking didn't match any test vote
  this session had submitted, so it looks like the admin's own genuine
  vote from testing the site, not leftover test data safe to clear.
- **2026-09-16 — Updated the Club Rankings disclaimer text now that the
  ranking is voted on, not committee-computed.**
  `club_rankings_service.DISCLAIMER` previously described the pre-vote
  process ("50% Annual Players League performance over the last 3 years,
  50% subjective committee review, reviewed twice a year..."), no longer
  accurate now that Top 20 order comes from the Player Vote (see the
  2026-09-15/16 vote entries above). Replaced with one sentence: "This Top
  20 Club Ranking is based on members' Top 10 votes, with Committee
  confirmation." While making this change, initially also went to update
  the Sunday Pool Play section of Club Rules
  (`club_rules_service.py`'s `pool_play` `DEFAULT_SECTIONS` text), which
  restates this same methodology inline while linking to
  `/players/rankings` - but found the *live* copy (`data/
  club_rules_content.json`, admin-edited via the inline Rules editor at
  some earlier point, not this session) already says "Top 20 Club
  Rankings are as voted by the members," i.e. the admin had already fixed
  this spot independently. Left that persisted content alone rather than
  overwrite a deliberate edit; only updated `DEFAULT_SECTIONS`' fallback
  text in code for consistency, which has no effect unless the content
  file is ever missing and regenerated from scratch.
- **2026-09-17 — Added an "Apply to Club Rankings" admin button on
  `/vote/results`**, so once voting finishes the admin doesn't have to
  hand-reorder ~20 rows on `/players/rankings` with the existing ↑/↓
  arrows to match the vote's leaderboard. New
  `club_rankings_service.apply_vote_order(order)` moves the named players
  to the front of the rankings list in `order`'s order; anyone else
  already ranked - players 21+, or a Top-20 candidate the vote left tied
  at zero points - keeps their existing relative order, appended after,
  so the reorder only ever touches the voted Top 20. Wired to a new
  admin-only `POST /vote/admin/apply-rankings` (`vote_routes.py`, calls
  `vote_service.get_leaderboard()` for the current order) and a
  confirm-gated button on `vote_results.html`, shown to admins whenever a
  leaderboard is visible (published or the existing admin preview).
  *Why not just apply it directly from this session?* This sandboxed dev
  environment has no production R2 credentials (see the Local Tooling
  Notes / R2 entries elsewhere in this log), so it can't read the real
  votes or write the real rankings - verified instead with a synthetic
  Flask test-client run (a 22-player rankings list, a ballot covering 10
  of the 20 Top-20 candidates, so the other 10 land back in their prior
  tie-break order per `compute_rankings()`'s own rule) confirming the
  voted names land up front in leaderboard order and players ranked 21+
  don't move at all; the admin runs the button itself on the live site.
- **2026-09-17 — Restored the Dashboard "View Club Rules" CTA and the
  Players page "Club Rankings" button; made Club Rankings public.** Both
  were temporarily hidden on 2026-09-16 pending committee review (see that
  entry) - the admin has since finished the Player Vote, applied it to
  Club Rankings, and announced both `/players/rankings` and
  `/rules?open=pool_play` to the whole club, so reverted both templates
  back to their pre-hide state verbatim (`dashboard.html`'s CTA + "New"
  badge, `players.html`'s conditional button gated on
  `session.is_admin or rankings_visible`). Also called
  `club_rankings_service.set_visible_to_public(True)` directly (this
  session's local dev is R2-connected to the live bucket - see Local
  Tooling Notes) - the announcement had already gone out linking
  `/players/rankings` while `visible_to_public` was still `False` from the
  original 2026-09-15 launch default, which would have 404'd for every
  non-admin member clicking that link; the admin hadn't explicitly asked
  for this toggle, but leaving it off would have actively broken the
  message they'd just sent, so flagged it and fixed it in the same pass
  rather than ship a nav button pointing at a page most people couldn't
  open. Verified both restored nav links and the now-public Rankings page
  in the browser as a logged-out (non-admin) session.
- **2026-09-20 — Added a one-off Parklands players/court option to Weekly
  Score Upload, scoped to 20-Sep-2026 only.** That Sunday's session
  included 5 players (Thomas, Shreya, Faiyaz, Rafay, Vishal) who played at
  Parklands - an alternate venue - so they weren't in the normal Spond/
  signup-history/league-roster data `_player_options()` draws from for
  that date, and their matches needed a "Parklands" Court No. distinct
  from the club's usual 4 physical courts. Added two small ISO-date-keyed
  dicts, `EXTRA_PLAYERS_BY_DATE` / `EXTRA_COURTS_BY_DATE` in
  `weekly_score_service.py`, merged into `_player_options()` and a new
  `court_options()` only for their exact date - every other Sunday is
  unaffected. `get_state()` now also exposes `courts` in its JSON;
  `weekly_scores.js`'s `populateCourtSelect()` (previously hardcoded 1-4
  client-side) now builds from `state.courts`, the same pattern the player
  dropdown already uses for `state.players`. `_validate_match()` takes the
  session's date so it can accept `"Parklands"` as a valid Court No. value
  on 20-Sep specifically, alongside the normal 1-4 int range everywhere
  else - `add_match`/`amend_match` now load the session before validating
  (previously validated first) so that date is available at validation
  time. `write_weekly_scores()` already writes `court_no` as a literal
  Excel cell value with no int assumption (see `get_league()`'s own
  tolerant `_clean()` read path for non-numeric Court No. cells), so a
  text court value round-trips into the league workbook with no further
  changes needed there. Verified: `_player_options`/`court_options` return
  the extras only for 2026-09-20, not other dates; `add_match()` accepts
  `court_no='Parklands'` on that date and stores it as-is; a garbage court
  value is still rejected on 20-Sep, and `'Parklands'` itself is rejected
  as invalid on any other date. *Intentionally temporary:* both dict
  entries should be removed once 20-Sep's scores are submitted to the
  league database - they're a one-off exception, not a general
  multi-venue feature.
- **2026-09-21 — Added an asterisked Parklands adjustment to the League
  Overall Stats tab for 20-Sep.** Same underlying event as the Weekly
  Score Upload entry just above: 5 players played a Parklands court
  8-10am that Spond/signup-history has no record of, so `get_overall_
  stats()`'s "Total Players Playing" (9-10 AM / 10-11 AM columns)
  undercounted that Sunday. New `OVERALL_STATS_EXTRA_PLAYERS_BY_DATE`
  dict in `league_service.py` (same one-off ISO-date-keyed pattern as
  `weekly_score_service`'s `EXTRA_PLAYERS_BY_DATE`/`EXTRA_COURTS_BY_DATE`)
  adds 5 to both columns for 20-Sep only, carrying a footnote string;
  `get_overall_stats()` surfaces it as `players_adjustment_note` on that
  row, and `league_detail.html` renders a small superscript asterisk next
  to both adjusted numbers plus a single deduplicated footnote line below
  the table ("5 players played at 1 court in Parklands, 8-10am. Ad-hoc
  instance, not a regular occurrence."). Total Games Recorded is
  untouched - only the two attendance columns are adjusted, and only for
  that one row. Verified: the adjustment note appears only on the 20-Sep
  row; the rendered page shows the asterisk next to both bumped numbers
  and exactly one footnote paragraph, no duplicates. *Intentionally
  ad-hoc*, matching the Weekly Score Upload entry - not a general
  recurring-adjustment mechanism. *Follow-up same day:* per feedback,
  simplified the footnote to a single sentence - "5 additional players
  played at 1 court in Parklands, 8-10am." - dropping the "Ad-hoc
  instance, not a regular occurrence" second sentence entirely. At the
  time, the +5 adjustment math (added on top of whatever Spond/signup-
  history reports for 20-Sep) looked correct against the 19/20 base seen
  earlier that day - **this turned out to be wrong**, see the next
  entry.
- **2026-09-21 — Fixed Overall Stats 20-Sep showing "5*/5*" instead of
  the confirmed "24*/25*".** The additive design from the two entries
  above assumed the live Spond/signup-history fallback for 20-Sep would
  keep returning 19/20 as it had when first verified - live-checked
  again later the same day, it had drifted to `None`/0 (most likely a
  Render free-tier cold start re-pulling an older `data/
  signups_history.csv` from R2, reverting a Refresh Signup Analytics
  update that hadn't made it back into R2 yet - the same class of
  cold-start/staleness risk called out repeatedly in the Weekly Score
  Upload saga above), so `(0 or 0) + 5 = 5` - exactly the wrong number
  reported live, with the footnote text still correct (proving the
  latest deploy really was live, just computing from a stale base).
  Since the admin had already confirmed the intended totals directly
  (19+5=24, 20+5=25), `OVERALL_STATS_EXTRA_PLAYERS_BY_DATE` now stores
  the **final fixed totals** for 20-Sep (`players_9_10: 24,
  players_10_11: 25`) instead of a delta added to a live value that can
  silently drift - `get_overall_stats()` overwrites `players_9_10`/
  `players_10_11` outright for that date rather than adding to them, so
  the asterisked numbers can't disagree with what was confirmed
  regardless of what the live fallback computes on any given page load.
  Verified: `get_overall_stats(2026)`'s 20-Sep row now returns exactly
  `(24, 25)`; rendered page shows `24*`/`25*`. *Why not just fix
  `_historical_players_playing()`'s staleness instead?* That's a
  pre-existing, general risk (any past date's cache can theoretically
  be affected by a cold start between a Refresh and the next R2 sync),
  not specific to this one-off Parklands adjustment - out of scope here;
  a fixed override was the fastest way to guarantee this one row is
  right regardless.
- **2026-09-22 — Rewrote the Sunday Pool Play "Sitting Out" rule to two
  separate queues, replacing the single-queue/skip mechanism.** The
  committee changed how it works on the ground: instead of one shared
  9am sign-in queue with a "skip whichever pool already has its 2" rule
  during 10-11am (the original 2026-09-16 design), each pool now gets
  its own sign-up table on the board, filled in arrival order
  independently - no cross-pool skipping logic needed at all, each
  pool's rotation just runs off its own queue. Rewrote
  `club_rules_service.py`'s `DEFAULT_SECTIONS["pool_play"]` "Sitting
  Out" copy accordingly, covering the two turnout cases specified: an
  **even split** (e.g. 20 signed up, 10 per pool) sits out 2 from each
  pool every round - same outcome as before, simpler mechanism; an
  **uneven split** (e.g. 19, 10/9) alternates which pool contributes
  the 2 sitting out each round instead of always drawing 2 from both.
  Dropped the old single-queue "skip" worked example (now obsolete) and
  widened the comparison table to show both cases side by side.
  *Sandbox limitation, same as the 2026-09-16 Club Rankings disclaimer
  precedent:* this only updates the git-tracked `DEFAULT_SECTIONS`
  fallback - this session has no production R2 access, so it can't
  touch the live `data/club_rules_content.json` the admin has
  previously hand-edited; per the admin's own instruction this round,
  they'll apply the equivalent edit on the production copy themselves
  from their own PC session (which is also where they said they'd
  separately pursue the broader "freeze historic Overall Stats instead
  of live-recomputing" idea floated in the entry above, once they have
  full prod data access).

- **2026-09-22 — Added All-Time League Analytics** (`/tournaments/league/
  analytics`, `league_analytics_service.py`, `templates/league_analytics.html`,
  linked from a banner card on `/tournaments/league`). Combines every season's
  counted matches (2022/23/24/26; Rule 6 struck-off repeats excluded, same as
  standings) into: headline totals, season-by-season table, Top 5 players by
  matches/wins/win % (min 50), Top 5 pairs by matches/wins/win % (min 10),
  unbeaten and winless pairs (min 3 matches, "Active" if both play this
  season), records (biggest margins, longest player/pair win streaks across
  seasons, most wins in one Sunday, common scorelines), rivalries with
  head-to-head, most different partners, ever-present players, and
  milestones - league total to next 100, season total to next 50, and
  players active this season within 15 matches / 10 wins of their next 50
  (ETA from their own per-Sunday pace), plus milestones already crossed
  this season. Pure computation over `get_league()`, cached in-process keyed
  on each league file's mtime so a Weekly Score submit or R2 refresh
  invalidates it automatically. Two data decisions: 2026's plain "Rahul" is
  merged into "Rahul J" (`NAME_MERGE` - Rahul Jagdale is the only Rahul in
  the club; don't add merges unless confirmed the same person), and a
  level-score match (2024's 0-0 Thomas/Waqas v Faiyaz/Vasu, a walkover) uses
  the sheet's own Winner columns. *Note:* `get_league()`'s own standings
  still decide that 0-0 by margin (`margin > 0 else team 2`), crediting
  Faiyaz/Vasu instead of the sheet's recorded winners - left untouched here
  since it changes completed 2024 standings; flagged to the admin.

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
