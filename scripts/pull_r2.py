"""
Pull a **read-only snapshot** of the production R2 bucket down to the local
data/, tournaments/, and static/images/ folders.

This is the download-only counterpart to ``scripts/seed_r2.py`` (which uploads
local files *to* R2). It only ever downloads: it calls
``r2_service.download_all()`` and never writes anything back to the bucket, so
running it cannot mutate production data.

Run from the project root:

    python scripts/pull_r2.py

Credentials come from a dedicated ``.env.r2`` file in the project root (copy
``.env.r2.example`` to ``.env.r2`` and fill in the real values) - NOT from the
main ``.env``. It mirrors every object under the synced prefixes (data/,
tournaments/, static/images/photos/, static/images/podium/) into the same
local paths the app reads, including Feedback.xlsx, Photos.xlsx and all
uploaded images.

IMPORTANT - keep the snapshot read-only:
There is only one R2 bucket and it IS production. This *script* is download-only
and safe, but the *app* is not: if the app starts with R2_* vars set, anything
it writes (a feedback submission, a photo upload, an Admin refresh) is uploaded
back to production R2. Using ``.env.r2`` instead of ``.env`` means the main app
(``config.py`` only loads ``.env``) never sees these credentials, so a plain
``python app.py`` always stays local-only - no need to remember to comment
anything out.
"""
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/pull_r2.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load R2 credentials from the dedicated .env.r2 file (see .env.r2.example).
# Deliberately separate from .env, which config.py loads for the main app.
load_dotenv(PROJECT_ROOT / ".env.r2")

from services import r2_service  # noqa: E402


def main():
    # Surface r2_service's per-file INFO logging when run as a standalone script
    # (app.py normally configures this, but it isn't imported here).
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not r2_service.is_enabled():
        sys.exit(
            "R2_* env vars are not set. Copy .env.r2.example to .env.r2 and fill "
            "in the real values (from the Render dashboard's Environment tab), "
            "then re-run."
        )

    result = r2_service.download_all()
    downloaded = result.get("downloaded", 0)
    failed = result.get("failed", 0)

    print(f"\nPulled {downloaded} file(s) from R2 ({failed} failed).")
    if failed:
        print("Some files failed to download - see the log lines above.")
    print(
        "\nThese credentials live in .env.r2, not .env, so python app.py stays "
        "local-only - nothing to clean up."
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
