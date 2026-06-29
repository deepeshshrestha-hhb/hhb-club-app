# HHB Club App — Development & Deploy Workflow

How to make a change and get it live on Render. See
[architecture.png](architecture.png) for the system diagram and the project
[CLAUDE.md](../CLAUDE.md) for deeper notes.

---

## Everyday workflow (code changes)

```bash
# 1. Start from up-to-date master and branch
git checkout master && git pull
git checkout -b my-change

# 2. Run locally and validate  ->  http://localhost:5000
python app.py

# 3. Commit on the branch
git add -p
git commit -m "Short, imperative summary of what changed"

# 4. Push and open a PR
git push -u origin my-change
#   then open the PR on GitHub (or: gh pr create)

# 5. Merge the PR into master
```

**Render auto-deploys when `master` changes** — so the deploy fires on the
**merge**, not on the branch push. Watch it in Render → your service → **Logs**;
the `R2 download complete: N file(s)` line confirms a healthy boot. The first
request after idle may take ~50s (free-tier cold start).

> Solo shortcut: you *can* commit straight to `master` and push to deploy, but
> the branch + PR flow gives you a reviewable diff and clean history.

### Running locally
- `python app.py` serves the dev server on `http://localhost:5000`.
- Locally the `R2_*` env vars are unset, so the app **skips R2 and reads your
  local `data/` + `tournaments/` files** — nothing touches production.
- `.env` supplies your Spond + (optional) `R2_*` / admin values locally. Never
  commit `.env`.

---

## Code vs. Data — two different paths

| You're changing… | How | Deploy needed? |
|---|---|---|
| **Code / templates** (`.py`, `.html`, CSS) | git → PR → merge to `master` | **Yes** (auto) |
| **A tournament `.xlsm`** | upload to **R2** under `tournaments/`, then **Admin → Refresh Data from R2** | **No** — picked up live |
| **Member list** | **Admin → Spond Refresh** | No |

The **R2 bucket (`hhb-club-data`) is the source of truth** for data; the app's
local disk is just a rebuildable cache. You rarely touch data files through git
anymore.

### Adding / updating tournament data
1. Put the file in R2 under `tournaments/` with the **exact** filename the
   parser expects, e.g. `tournaments/HHB Annual Doubles Classic - 2027.xlsm`.
   - Bulk/initial load: run `python scripts/seed_r2.py` (with `R2_*` vars set).
     It uploads **and round-trip-verifies** each file (OneDrive-safe).
2. **Admin → Refresh Data from R2** to pull it into the live app (no redeploy).
3. That's it — all three archives (Doubles, Championships, League) auto-discover
   years by globbing the `tournaments/` folder for the matching filename, so no
   code change is needed for a new year. Just confirm the page renders correctly
   (winner/runner-up populate): each parser targets a specific Excel layout, so a
   new file must follow the same template as the most recent working year. If the
   layout differs the year will list but show empty, which is a parser fix — not
   a config change.

---

## Remember
- **Local (Windows) ≠ Linux** for some `.xlsm` quirks (Windows hides the
  backslash-zip issue). The normalized loader handles it, but for data-format
  changes, the real confirmation is the page loading **on Render**.
- **Rollback:** Render → the service → **Manual Deploy → Roll back** to a
  previous deploy (instant), and/or `git revert <sha>` + push for the permanent
  fix.
- **Secrets** live in Render (Environment tab), never in the repo. Local secrets
  live in `.env` (gitignored).

### Optional: exercise the R2 path locally
Set the four `R2_*` vars in your shell before `python app.py`, and local behaves
like production (pulls from R2 on boot, uploads on write). Most of the time you
don't need this.
