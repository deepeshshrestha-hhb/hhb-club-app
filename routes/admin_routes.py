import hmac
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash
)

from config import Config
from services import r2_service
from services.spond_service import fetch_members_to_csv
from services.player_stats_service import invalidate_cache

admin_bp = Blueprint("admin", __name__)


def _credentials_configured():
    return bool(Config.ADMIN_USERNAME and Config.ADMIN_PASSWORD)


def _check_credentials(username, password):
    """Constant-time check against the configured admin credentials."""
    if not _credentials_configured():
        return False
    user_ok = hmac.compare_digest(username or "", Config.ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(password or "", Config.ADMIN_PASSWORD)
    return user_ok and pass_ok


def _safe_next(target):
    """Only allow same-site relative redirects (avoid open-redirect via ?next=)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _check_credentials(request.form.get("username"), request.form.get("password")):
            session["is_admin"] = True
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.admin_page"))
        flash("Invalid username or password.")
    return render_template("login.html")


@admin_bp.route("/admin/logout")
def logout():
    session.pop("is_admin", None)
    flash("Logged out.")
    return redirect(url_for("dashboard"))


@admin_bp.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")


@admin_bp.route("/admin/sync_spond", methods=["POST"])
@admin_required
def sync_spond_route():
    """Re-fetch the member list from Spond, rewrite the local CSV, and upload it
    to R2. Use after a player joins or leaves."""
    fetch_members_to_csv()
    invalidate_cache()
    flash("Spond member list refreshed.")
    return redirect(url_for("admin.admin_page"))


@admin_bp.route("/admin/refresh-data", methods=["POST"])
@admin_required
def refresh_data_route():
    """Re-download all data/ and tournaments/ files from R2. Use after uploading
    a new scoresheet directly to the bucket, to pick it up without a redeploy."""
    result = r2_service.download_all()
    invalidate_cache()
    if result.get("skipped"):
        flash("R2 is not configured; nothing to refresh.")
    else:
        flash(f"Refreshed {result.get('downloaded', 0)} file(s) from R2.")
    return redirect(url_for("admin.admin_page"))


@admin_bp.route("/admin/debug-files")
@admin_required
def debug_files():
    """Temporary diagnostic: report, for each tournament file as it exists on
    this server, its size/hash/zip-contents and openpyxl load result, plus the
    interpreter + openpyxl versions. Lets us compare the deployed bytes/lib
    against local. Remove once the deploy is verified healthy."""
    import sys
    import hashlib
    import zipfile
    import openpyxl
    from flask import Response
    from services.tournament_service import TOURNAMENTS_DIR

    lines = [
        f"python={sys.version.split()[0]}  openpyxl={openpyxl.__version__}",
        f"tournaments_dir={TOURNAMENTS_DIR}",
        "",
    ]
    for p in sorted(TOURNAMENTS_DIR.glob("*.xlsm")):
        size = p.stat().st_size
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        try:
            is_zip = zipfile.is_zipfile(p)
            names = zipfile.ZipFile(p).namelist() if is_zip else []
            has_ss = "xl/sharedStrings.xml" in names
            entries = len(names)
        except Exception as exc:  # noqa: BLE001
            is_zip, has_ss, entries = False, "?", f"ziperr: {exc}"
        try:
            openpyxl.load_workbook(p, data_only=True)
            load = "LOAD_OK"
        except Exception as exc:  # noqa: BLE001
            load = f"LOAD_FAIL {type(exc).__name__}: {exc}"
        lines.append(
            f"{p.name}\n  size={size} sha256={sha} zip={is_zip} "
            f"entries={entries} sharedStrings={has_ss}\n  {load}"
        )

    # Full entry dump for the file that fails first, to expose any
    # case/encoding difference in the zip member names on this server.
    target = TOURNAMENTS_DIR / "HHB Annual Doubles Classic - 2026.xlsm"
    lines.append("\n--- full namelist: Doubles 2026 ---")
    if target.exists():
        try:
            for n in zipfile.ZipFile(target).namelist():
                lines.append(f"  {n!r}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  ziperr: {exc}")
    else:
        lines.append("  (file missing)")

    return Response("\n".join(lines), mimetype="text/plain")
