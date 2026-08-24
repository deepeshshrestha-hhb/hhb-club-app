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
    "rotation": "Sunday Doubles Player Rotation Rules",
    "sitting_out": "Sunday Doubles Player Sitting Out & Latecomer Rules",
}
SECTION_ORDER = ["rotation", "sitting_out"]

DEFAULT_SECTIONS = {
    "rotation": (
        "<p>After every match, players move up or down a court so "
        "that, over time, everyone ends up on a court that matches their performance on the day "
        "— keeping every game close and competitive.</p>"
        "<ol class=\"ps-3\">"
        "<li class=\"mb-2\"><strong>Winning Pair moves up one court, Losing Pair moves down "
        "one court</strong> — towards Court 1 and Court 4 respectively.</li>"
        "<li class=\"mb-2\"><strong>One exception at each end:</strong> on Court 1, the Winning "
        "Pair <em>stay put</em> — there's no court above to move up to. On Court 4, the Losing "
        "Pair <em>stay put</em> — there's no court below to move down to.</li>"
        "<li class=\"mb-0\"><strong>Split and re-pair for balance — before the game starts.</strong> "
        "Whenever new players arrive on a court, mix the four players so the two pairs are as "
        "evenly matched as possible, before play begins.</li>"
        "</ol>"
        "<div class=\"table-responsive mt-3\">"
        "<table class=\"table table-sm table-bordered align-middle mb-1 hhb-rules-table\">"
        "<thead class=\"table-light\"><tr><th>Court</th><th>Win</th><th>Don't win</th></tr></thead>"
        "<tbody>"
        "<tr><td><strong>1</strong></td>"
        "<td>Stay</td><td>&darr; Court 2</td></tr>"
        "<tr><td><strong>2</strong></td><td>&uarr; Court 1</td><td>&darr; Court 3</td></tr>"
        "<tr><td><strong>3</strong></td><td>&uarr; Court 2</td><td>&darr; Court 4</td></tr>"
        "<tr><td><strong>4</strong></td>"
        "<td>&uarr; Court 3</td><td>Stay</td></tr>"
        "</tbody></table>"
        "</div>"
        "<p class=\"text-muted small mb-0\">On arrival at any court, re-pair the four players "
        "for the most balanced game.</p>"
    ),
    "sitting_out": (
        "<p>4 courts run 9:00&ndash;11:00am &mdash; roughly 20 players sign up, so 16 play and 4 sit out "
        "at any time. Each game runs 11 minutes (stopwatch/buzzer) followed by a 2-minute break &mdash; "
        "about 4&ndash;5 games an hour.</p>"
        "<h6 class=\"fw-bold small text-uppercase text-muted mt-3 mb-2\">Sitting Out</h6>"
        "<ul class=\"ps-3 mb-2\">"
        "<li class=\"mb-1\"><strong>End of game:</strong> whoever's ahead when the buzzer sounds wins, "
        "game over. Level scores play one tie-break point.</li>"
        "<li class=\"mb-1\"><strong>Sign in:</strong> write your name on the board in arrival order "
        "&mdash; that's your place in the sit-out queue.</li>"
        "<li class=\"mb-1\"><strong>Board key:</strong> a number = a game you've played, an "
        "<strong>X</strong> = a game you sat out.</li>"
        "<li class=\"mb-1\"><strong>Only Court Wardens update the board.</strong> To keep it accurate, "
        "please don't mark yourself in or out — let a Warden do it, so there's no confusion.</li>"
        "<li class=\"mb-1\"><strong>Rotation:</strong> the most recent arrivals sit out first. Once "
        "everyone's had one turn, it starts again from the bottom. As soon as you sit out, you're back "
        "in for the very next game.</li>"
        "<li class=\"mb-0\"><strong>Want out early?</strong> Find someone in the sit-out queue, swap "
        "places with them directly, and let a Court Warden know.</li>"
        "</ul>"
        "<div class=\"table-responsive mt-2\">"
        "<table class=\"table table-sm table-bordered align-middle mb-1 hhb-rules-table\">"
        "<colgroup><col style=\"width:26%\"><col><col><col><col><col></colgroup>"
        "<thead class=\"table-light\"><tr><th>Group</th><th>G1</th><th>G2</th><th>G3</th><th>G4</th>"
        "<th>G5</th></tr></thead>"
        "<tbody>"
        "<tr><td>A (1&ndash;4)</td><td>1</td><td>2</td><td>3</td><td>4</td>"
        "<td class=\"text-danger fw-bold\">X</td></tr>"
        "<tr><td>B (5&ndash;8)</td><td>1</td><td>2</td><td>3</td><td class=\"text-danger fw-bold\">X</td>"
        "<td>4</td></tr>"
        "<tr><td>C (9&ndash;12)</td><td>1</td><td>2</td><td class=\"text-danger fw-bold\">X</td><td>3</td>"
        "<td>4</td></tr>"
        "<tr><td>D (13&ndash;16)</td><td>1</td><td class=\"text-danger fw-bold\">X</td><td>2</td><td>3</td>"
        "<td>4</td></tr>"
        "<tr><td>E (17&ndash;20)</td><td class=\"text-danger fw-bold\">X</td><td>1</td><td>2</td><td>3</td>"
        "<td>4</td></tr>"
        "</tbody></table>"
        "</div>"
        "<p class=\"text-muted small mb-2\">Example &mdash; all 20 players at 9am: each group of 4 sits "
        "out exactly once across 5 games.</p>"
        "<h6 class=\"fw-bold small text-uppercase text-muted mt-3 mb-2\">Latecomers</h6>"
        "<p class=\"text-muted small mb-2\">Games go to 21 points; the 11-minute clock roughly matches "
        "that, so these are checkpoints within the game, not arbitrary numbers.</p>"
        "<ul class=\"ps-3 mb-2\">"
        "<li class=\"mb-1\"><strong>Waiting for a court?</strong> Check the score on the active court "
        "nearest the board (usually Court 3 or 4). Either pair at 10+ (past halfway) &rarr; genuinely "
        "late, no X &mdash; but you're at the bottom of the queue, so you'll sit out next anyway. Both "
        "pairs under 10 &rarr; counts as sat out (X).</li>"
        "<li class=\"mb-0\"><strong>Got 4 to start a court?</strong> At the buzzer, either pair at 5+ "
        "&rarr; finish your game to 11, counts as played (everyone else waits ~2&ndash;3 min for you). "
        "Both pairs under 5 &rarr; stop there, neutral &mdash; no X, no number.</li>"
        "</ul>"
        "<p class=\"text-muted small mb-0\">Coming late never works in your favour &mdash; your name "
        "lands near the bottom of the list. But you won't be double-penalised if the timing genuinely "
        "wasn't in your control.</p>"
    ),
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
