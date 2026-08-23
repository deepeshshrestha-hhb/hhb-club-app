"""
Club Rules page editable copy: data/club_rules_content.json

Stores the admin-editable body HTML for the Club Rules page's two
collapsible sections (mirrors the About Us page's about_content_service.py
pattern). Content is authored as small HTML snippets (paragraphs, lists,
a table) rather than plain pre-line text, since these sections need bold
emphasis and a table that plain text can't represent. The admin textarea is
gated behind admin_required, so trusting the stored HTML (rendered with
Jinja's `| safe`) is safe — the same trust boundary the rest of the site's
admin-only edit forms already rely on.
"""
import json
from pathlib import Path

from config import Config
from services import r2_service

CLUB_RULES_CONTENT_PATH = Path(Config.DATA_DIR) / "club_rules_content.json"

SECTION_TITLES = {
    "rotation": "Doubles Player Rotation Rules",
    "sitting_out": "Doubles Player Sitting Out & Latecomer Rules",
}
SECTION_ORDER = ["rotation", "sitting_out"]

DEFAULT_SECTIONS = {
    "rotation": (
        "<p>Court 1 is where the best games happen. Court 4 is the Improvers Court, where "
        "players build up their game. After every match, players move up or down a court so "
        "that, over time, everyone ends up on a court that matches their ability — keeping "
        "every game close and competitive.</p>"
        "<ol class=\"ps-3\">"
        "<li class=\"mb-2\"><strong>Winning Pair moves up one court. Non-Winning Pair moves "
        "down one court.</strong> After every game, the Winning Pair move up towards Court 1, "
        "and the Non-Winning Pair move down towards Court 4 (Improvers Court).</li>"
        "<li class=\"mb-2\"><strong>One exception at each end:</strong> on Court 1, the Winning "
        "Pair <em>stay put</em> — there's no court above to move up to. On Court 4 (Improvers "
        "Court), the Non-Winning Pair <em>stay put</em> — there's no court below to move down "
        "to.</li>"
        "<li class=\"mb-2\"><strong>Split and re-pair for balance — before the game starts.</strong> "
        "Whenever new players arrive on a court, mix the four players so the two pairs are as "
        "evenly matched as possible, before play begins.</li>"
        "<li class=\"mb-0\"><strong>Stuck? Ask a Court Warden.</strong> Rukhsar, Jalal, Thomas, "
        "Deepesh, Sandip, or Altamash.</li>"
        "</ol>"
        "<div class=\"table-responsive mt-3\">"
        "<table class=\"table table-sm table-bordered align-middle mb-1\">"
        "<thead class=\"table-light\"><tr><th>Court</th><th>If pair wins</th><th>If pair doesn't win</th></tr></thead>"
        "<tbody>"
        "<tr><td><strong>1</strong> <span class=\"text-muted small\">Top Court</span></td>"
        "<td>Stay on Court 1</td><td>Move down to Court 2</td></tr>"
        "<tr><td><strong>2</strong></td><td>Move up to Court 1</td><td>Move down to Court 3</td></tr>"
        "<tr><td><strong>3</strong></td><td>Move up to Court 2</td><td>Move down to Court 4</td></tr>"
        "<tr><td><strong>4</strong> <span class=\"text-muted small\">Improvers Court</span></td>"
        "<td>Move up to Court 3</td><td>Stay on Court 4</td></tr>"
        "</tbody></table>"
        "</div>"
        "<p class=\"text-muted small mb-0\">On arrival at any court, re-pair the four players "
        "for the most balanced game.</p>"
    ),
    "sitting_out": "<p class=\"text-muted mb-0\">Coming soon.</p>",
}


def _load() -> dict:
    if not CLUB_RULES_CONTENT_PATH.exists():
        return dict(DEFAULT_SECTIONS)
    try:
        with open(CLUB_RULES_CONTENT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SECTIONS)
    for key, default_val in DEFAULT_SECTIONS.items():
        data.setdefault(key, default_val)
    return data


def _save(data: dict):
    CLUB_RULES_CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLUB_RULES_CONTENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    r2_service.upload_file(CLUB_RULES_CONTENT_PATH)


def get_rules_content() -> dict:
    return _load()


def update_section(key: str, html: str) -> bool:
    """Update one section's body HTML. Returns False for an unknown key."""
    if key not in SECTION_ORDER:
        return False
    data = _load()
    data[key] = html.strip()
    _save(data)
    return True
