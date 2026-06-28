"""
Pull a **read-only snapshot** of the production R2 bucket down to the local
data/, tournaments/, and static/images/ folders.

This is the download-only counterpart to ``scripts/seed_r2.py`` (which uploads
local files *to* R2). It only ever downloads: it calls
``r2_service.download_all()`` and never writes anything back to the bucket, so
running it cannot mutate production data.

Run from the project root with the R2_* env vars set (e.g. copied into your local
.env from the Render secrets):

    python scripts/pull_r2.py

It mirrors every object under the synced prefixes (data/, tournaments/,
static/images/photos/, static/images/podium/) into the same local paths the app
reads, including Feedback.xlsx, Photos.xlsx and all uploaded images.

IMPORTANT - keep the snapshot read-only:
There is only one R2 bucket and it IS production. This *script* is download-only
and safe, but the *app* is not: if you leave the R2_* vars set in your .env and
then start the app, anything it writes (a feedback submission, a photo upload, an
Admin refresh) is uploaded back to production R2. So once this pull finishes,
comment the R2_* vars back out of your .env before running the app locally - your
downloaded files then stay a frozen local snapshot and your local edits stay
local.
"""
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/pull_r2.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services import r2_service  # noqa: E402


def main():
    # Surface r2_service's per-file INFO logging when run as a standalone script
    # (app.py normally configures this, but it isn't imported here).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not r2_service.is_enabled():
        sys.exit(
            "R2_* env vars are not set in this shell. Set them (e.g. in your .env, "
            "copied from the Render secrets) and re-run."
        )

    result = r2_service.download_all()
    downloaded = result.get("downloaded", 0)
    failed = result.get("failed", 0)

    print(f"\nPulled {downloaded} file(s) from R2 ({failed} failed).")
    if failed:
        print("Some files failed to download - see the log lines above.")
    print(
        "\nRead-only reminder: comment the R2_* vars out of your .env before "
        "running the app locally, or the app will upload local changes back to "
        "production R2."
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
