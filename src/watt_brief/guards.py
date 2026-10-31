"""Input and output guards. Cheap, deterministic, and no model involved.

These are heuristics, not proof. The topic check is a keyword allowlist: it stops obvious
off-topic and attack traffic before it costs a model call, and it will sometimes reject a
legitimate question phrased without any energy word. See docs/adr/002-layered-guards.md.
"""

import re
import unicodedata

from watt_brief.errors import GuardRejected
from watt_brief.grounding import grounding_failures

MAX_QUESTION_CHARS = 500

# Fragments of the system prompt that must never be echoed back.
LEAK_FRAGMENTS = ("untrusted user", "do not comply", "exactly these keys", "reply with one json")

_DELIMITERS = re.compile(r"<\s*/?\s*(question|facts)\s*>", re.IGNORECASE)

_TOPIC = re.compile(
    r"electric|power|energy|price|prices|cost|tariff|cheap|expensive|kwh|mwh|\bkw\b|watt|grid|"
    r"charg|\bev\b|heat pump|boiler|battery|\bload\b|appliance|washing|dishwasher|negative|"
    r"spot|day-ahead|peak|off-peak|solar|wind|usage|consum",
    re.IGNORECASE,
)

_MARKUP = re.compile(r"[<>]|https?:|www\.|javascript:", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z0-9_\-.]{4,}")

MESSAGES = {
    "empty": "Ask a question about European day-ahead electricity prices.",
    "too_long": f"Keep the question under {MAX_QUESTION_CHARS} characters.",
    "delimiter": "That question contains text I can't accept.",
    "off_topic": "I only answer questions about electricity prices and when to use power.",
    "unsafe_output": "I couldn't produce a safe answer. Try rephrasing the question.",
}


def normalize(text: str) -> str:
    """NFKC, drop control and zero-width characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"} or ch in "\n\t "
    )
    return re.sub(r"\s+", " ", text).strip()


def check_question(question: str) -> str:
    """Return the cleaned question, or raise GuardRejected. Never calls a model."""
    cleaned = normalize(question)
    if not cleaned:
        raise _reject("empty", "input")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise _reject("too_long", "input")
    if _DELIMITERS.search(cleaned):
        raise _reject("delimiter", "input")
    if not _TOPIC.search(cleaned):
        raise _reject("off_topic", "input")
    return cleaned


def _echo_tokens(question: str, facts_text: str) -> list[str]:
    """Attacker-style tokens: codes like PWNED-7731 or MEOWCANARY that are not in the facts."""
    found = []
    for token in _TOKEN.findall(question):
        has_letter = any(c.isalpha() for c in token)
        looks_like_code = any(c.isdigit() for c in token) or token.isupper()
        if has_letter and looks_like_code and token.lower() not in facts_text:
            found.append(token)
    return found


def check_output(text: str, question: str, facts: dict) -> None:
    """Raise GuardRejected if the brief leaks, echoes, carries markup, or invents a figure."""
    lowered = text.lower()
    if any(fragment in lowered for fragment in LEAK_FRAGMENTS):
        raise _reject("prompt_leak", "output")
    if _MARKUP.search(text):
        raise _reject("markup", "output")
    facts_text = str(facts).lower()
    if any(token.lower() in lowered for token in _echo_tokens(question, facts_text)):
        raise _reject("echo", "output")
    failures = grounding_failures(text, facts)
    if failures:
        # Only numbers and clock times from the model's own output, so safe to log.
        raise _reject("ungrounded", "output", detail="; ".join(failures))


def _reject(reason: str, stage: str, detail: str = "") -> GuardRejected:
    key = reason if reason in MESSAGES else "unsafe_output"
    return GuardRejected(reason, stage, MESSAGES[key], detail)
