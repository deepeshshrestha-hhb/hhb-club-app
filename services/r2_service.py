"""
Cloudflare R2 (S3-compatible) durable storage for the club's data files.

Render's free filesystem is ephemeral, so on each boot we pull the canonical
copies of every data file from R2 into the same local paths the services layer
already reads (``data/`` and ``tournaments/``). Whenever the app writes a data
file, we push that exact file back to R2 so the durable copy stays current.

The bucket mirrors the local tree under two prefixes:

    data/<filename>            e.g. data/Tournaments.xlsx
    tournaments/<filename>     e.g. "tournaments/HHB Annual Doubles Classic - 2026.xlsm"

Everything here is gated by the R2_* env vars: when they are absent (e.g. local
development), the helpers become no-ops and the app just uses whatever is on
local disk. So importing this module never changes local behavior unless R2 is
actually configured.

Previous-version safety: R2 does not expose S3-style bucket versioning, so
before overwriting an object the app server-side-copies the current version to
a timestamped ``backups/<key>.<UTC timestamp>`` key. Those backup objects live
outside the mirrored prefixes, so they are never pulled back to local disk. Add
an R2 Object Lifecycle Rule on the ``backups/`` prefix if you want them expired
automatically.

Required environment variables (set as Render secrets, never committed):
    R2_ACCESS_KEY_ID       R2 API token access key id
    R2_SECRET_ACCESS_KEY   R2 API token secret access key
    R2_BUCKET              bucket name
    R2_ENDPOINT_URL        https://<accountid>.r2.cloudflarestorage.com
"""
import os
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import Config

logger = logging.getLogger("r2")

# Local roots that mirror the bucket prefixes.
BASE_DIR = Path(Config.BASE_DIR)
SYNCED_DIRS = {
    "data": BASE_DIR / "data",
    "tournaments": BASE_DIR / "tournaments",
}

_REQUIRED_VARS = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_ENDPOINT_URL",
)

_client = None
_client_lock = threading.Lock()


def _env(name):
    val = os.environ.get(name)
    return val.strip() if val and val.strip() else None


def is_enabled():
    """True only when every R2_* variable is present. Otherwise all helpers no-op."""
    return all(_env(n) for n in _REQUIRED_VARS)


def get_client():
    """Lazily build (and cache) a boto3 S3 client pointed at R2."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import boto3
                from botocore.config import Config as BotoConfig

                _client = boto3.client(
                    "s3",
                    endpoint_url=_env("R2_ENDPOINT_URL"),
                    aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
                    aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
                    region_name="auto",
                    config=BotoConfig(
                        retries={"max_attempts": 3, "mode": "standard"},
                        s3={"addressing_style": "path"},
                    ),
                )
    return _client


def _key_to_local(key):
    """Map an R2 object key ('tournaments/Foo.xlsm') to its local Path.
    Returns None for keys outside the two mirrored prefixes."""
    parts = key.split("/", 1)
    if len(parts) != 2:
        return None
    prefix, rest = parts
    root = SYNCED_DIRS.get(prefix)
    if root is None or not rest:
        return None
    return root / rest


def _local_to_key(local_path):
    """Map a local Path back to its R2 key ('data/foo.xlsx').
    Returns None if the path is not under a synced directory."""
    local_path = Path(local_path).resolve()
    for prefix, root in SYNCED_DIRS.items():
        try:
            rel = local_path.relative_to(root.resolve())
        except ValueError:
            continue
        return f"{prefix}/{rel.as_posix()}"
    return None


def download_all():
    """Pull every object under the mirrored prefixes from R2 onto local disk.

    Safe to call on startup and on demand. Creates the local dirs even when a
    prefix is empty in the bucket. No-op (returns skipped=True) when R2 is not
    configured, so local dev is unaffected.
    """
    # Always make sure the local dirs exist, R2 or not.
    for root in SYNCED_DIRS.values():
        root.mkdir(parents=True, exist_ok=True)

    if not is_enabled():
        present = [n for n in _REQUIRED_VARS if _env(n)]
        logger.warning(
            "R2 not configured; skipping download (using local files). "
            "R2 vars present: %s of %s.", present, list(_REQUIRED_VARS),
        )
        return {"downloaded": 0, "skipped": True}

    client = get_client()
    bucket = _env("R2_BUCKET")
    logger.info("R2 download starting from bucket %r ...", bucket)
    downloaded, failed, names = 0, 0, []
    paginator = client.get_paginator("list_objects_v2")
    for prefix in SYNCED_DIRS:
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                key, size = obj["Key"], obj["Size"]
                if key.endswith("/"):
                    continue  # skip "folder" placeholder keys
                local = _key_to_local(key)
                if local is None:
                    continue
                local.parent.mkdir(parents=True, exist_ok=True)
                try:
                    client.download_file(bucket, key, str(local))
                    got = local.stat().st_size
                    if got != size:
                        failed += 1
                        logger.error(
                            "R2 download SIZE MISMATCH for %s: expected %d, got %d bytes "
                            "(file may be corrupt).", key, size, got,
                        )
                    else:
                        downloaded += 1
                        names.append(key)
                        logger.info("R2 downloaded %s (%d bytes).", key, got)
                except Exception as exc:  # noqa: BLE001 - log and keep going
                    failed += 1
                    logger.error("R2 download FAILED for %s: %s", key, exc)
    logger.info(
        "R2 download complete: %d ok, %d failed. Files: %s",
        downloaded, failed, ", ".join(names) or "none",
    )
    return {"downloaded": downloaded, "failed": failed, "skipped": False, "files": names}


def _backup_existing(client, bucket, key):
    """Server-side copy the current object (if any) to a timestamped backups/
    key, so the prior version is recoverable before we overwrite it. Best-effort:
    a backup failure is logged but does not block the upload."""
    try:
        client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return  # nothing there yet (first upload) - nothing to back up
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_key = f"backups/{key}.{ts}"
    try:
        client.copy_object(
            Bucket=bucket,
            Key=backup_key,
            CopySource={"Bucket": bucket, "Key": key},
        )
        logger.info("R2 backup: %s -> %s", key, backup_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("R2 backup of %s failed (continuing with upload): %s", key, exc)


def upload_file(local_path):
    """Push one local file back to R2 under its mirrored key, with retries.

    Before overwriting, the current object is backed up to a timestamped
    backups/ key. On persistent upload failure it logs an error and leaves the
    local file in place (the update is not lost locally) rather than raising.
    Returns True on success, False otherwise. No-op (returns False) when R2 is
    not configured.
    """
    if not is_enabled():
        return False

    local_path = Path(local_path)
    key = _local_to_key(local_path)
    if key is None:
        logger.warning("R2 upload skipped: %s is not under a synced directory.", local_path)
        return False
    if not local_path.exists():
        logger.warning("R2 upload skipped: %s does not exist.", local_path)
        return False

    client = get_client()
    bucket = _env("R2_BUCKET")
    _backup_existing(client, bucket, key)
    last_exc = None
    for attempt in range(1, 4):
        try:
            client.upload_file(str(local_path), bucket, key)
            logger.info("R2 upload ok: %s -> %s (attempt %d).", local_path.name, key, attempt)
            return True
        except Exception as exc:  # noqa: BLE001 - we want to retry on anything
            last_exc = exc
            logger.warning("R2 upload failed for %s (attempt %d/3): %s", key, attempt, exc)
            time.sleep(2 ** (attempt - 1))

    logger.error(
        "R2 upload FAILED after 3 attempts for %s: %s. Local file kept at %s; "
        "durable copy is now STALE until the next successful upload.",
        key, last_exc, local_path,
    )
    return False
