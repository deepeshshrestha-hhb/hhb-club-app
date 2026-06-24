"""
Seed / refresh the R2 bucket from the local data/ and tournaments/ files, then
**verify each upload by downloading it back and opening it**. Re-uploads up to a
few times if the round-trip copy is bad.

This exists because a plain upload can silently store a size-correct but
byte-corrupted object (e.g. if the local source was read before a OneDrive
"Files On-Demand" placeholder finished hydrating). The size check in
r2_service.download_all cannot catch that; opening the workbook can.

Run from the project root with the R2_* env vars set:

    python scripts/seed_r2.py
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl

# Allow running as `python scripts/seed_r2.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services import r2_service  # noqa: E402


def verify_spreadsheet(path):
    """Return None if the workbook opens cleanly, else a short error string."""
    try:
        if not zipfile.is_zipfile(path):
            return "not a zip/OOXML file"
        names = zipfile.ZipFile(path).namelist()
        if "[Content_Types].xml" not in names:
            return "missing [Content_Types].xml (corrupt package)"
        openpyxl.load_workbook(path, data_only=True)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def main():
    if not r2_service.is_enabled():
        sys.exit("R2_* env vars are not set in this shell. Set them and re-run.")

    client = r2_service.get_client()
    bucket = os.environ["R2_BUCKET"]

    files = (
        sorted(Path("data").glob("*.xlsx"))
        + sorted(Path("data").glob("*.csv"))
        + sorted(Path("tournaments").glob("*.xlsm"))
    )
    if not files:
        sys.exit("No data/ or tournaments/ files found. Run from the project root.")

    ok = bad = 0
    for f in files:
        is_sheet = f.suffix.lower() in (".xlsx", ".xlsm")

        # 1) Make sure the LOCAL source is readable first (this also forces
        #    OneDrive to fully hydrate the file before we upload it).
        if is_sheet:
            err = verify_spreadsheet(f)
            if err:
                print(f"SKIP  local source unreadable: {f}  ->  {err}")
                bad += 1
                continue

        key = r2_service._local_to_key(f)

        # 2) Upload, then download the stored object back and re-verify it.
        verified, attempt = False, 0
        while attempt < 3 and not verified:
            attempt += 1
            r2_service.upload_file(f)
            tmp_path = tempfile.mktemp(suffix=f.suffix)
            try:
                client.download_file(bucket, key, tmp_path)
                r2_size, local_size = os.path.getsize(tmp_path), f.stat().st_size
                if r2_size != local_size:
                    err = f"size {r2_size} != local {local_size}"
                elif is_sheet:
                    err = verify_spreadsheet(tmp_path)
                else:
                    err = None
                if err is None:
                    verified = True
                else:
                    print(f"  attempt {attempt}: {key} round-trip BAD -> {err}; re-uploading")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        if verified:
            ok += 1
            print(f"OK    {key}  ({f.stat().st_size} bytes)")
        else:
            bad += 1
            print(f"BAD   {key}  - still corrupt in R2 after {attempt} attempts")

    print(f"\nDone: {ok} ok, {bad} bad.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
