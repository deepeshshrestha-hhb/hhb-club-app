"""
Claude AI text-assist service.

Powers the admin "Summarize / Rewrite / change tone" helpers on the event
summary editor. Entirely optional: when ``ANTHROPIC_API_KEY`` is not set (the
default locally and until configured on Render) the feature is simply disabled
and the summary field still works as a plain editable text box.

Kept deliberately small — one helper that takes the current draft plus an
instruction and returns the rewritten text. The anthropic SDK is imported lazily
so the app boots fine even if the package isn't installed.
"""
from config import Config

# Sensible, low-cost default — fast and more than capable for short paragraphs.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Preset instructions surfaced as one-click buttons in the editor. The free-form
# box lets admins type anything else.
PRESETS = {
    "summarize": "Summarize this into a concise, engaging overview paragraph.",
    "rewrite": "Rewrite this to read more clearly and smoothly, keeping the same facts.",
    "shorten": "Make this noticeably shorter while keeping the key points.",
    "expand": "Expand this into a fuller, more vivid overview, but stay truthful to the facts given.",
    "formal": "Rewrite this in a more formal, polished tone.",
    "fun": "Rewrite this in a more fun, upbeat and friendly tone.",
    "grammar": "Fix any spelling and grammar mistakes. Make no other changes.",
}

_SYSTEM_PROMPT = (
    "You are helping an admin write a short overview paragraph for a badminton "
    "club's event photo gallery (a tournament, picnic, or social event). "
    "Return ONLY the rewritten paragraph text — no preamble, no quotes, no "
    "markdown, no options. Keep it warm and readable, suitable for club members. "
    "Do not invent specific facts (scores, names, dates) that aren't in the draft."
)


def is_enabled() -> bool:
    """True when an Anthropic API key is configured."""
    return bool(getattr(Config, "ANTHROPIC_API_KEY", None))


def assist(instruction: str, draft: str, event_label: str = "") -> str:
    """Apply ``instruction`` to ``draft`` via Claude and return the new text.

    Raises RuntimeError when the feature is disabled or the SDK is unavailable,
    so the route can surface a clean error message.
    """
    if not is_enabled():
        raise RuntimeError("AI assist is not configured.")

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on deployment
        raise RuntimeError("The anthropic package is not installed.") from exc

    instruction = (instruction or "").strip()
    draft = (draft or "").strip()
    if not instruction:
        raise RuntimeError("No instruction provided.")

    context = f"Event: {event_label}\n\n" if event_label else ""
    if draft:
        user_content = (
            f"{context}Current draft:\n\"\"\"\n{draft}\n\"\"\"\n\n"
            f"Instruction: {instruction}"
        )
    else:
        user_content = (
            f"{context}There is no draft yet. Instruction: {instruction}\n\n"
            "Write a short, plausible overview paragraph the admin can then edit. "
            "Keep it generic — do not invent specific results, names or dates."
        )

    model = getattr(Config, "ANTHROPIC_MODEL", None) or DEFAULT_MODEL
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    result = "".join(parts).strip()
    if not result:
        raise RuntimeError("The AI returned an empty response.")
    return result
