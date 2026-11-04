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

# Word stems for the languages of the markets we cover. They are matched against text that has
# been lower-cased and stripped of accents, so "Électricité" and "Wärmepumpe" match "electric"
# and "warmepumpe". The list is deliberately specific: a generic word such as "laden" (shop or
# charge) would let too much through.
_TOPIC_STEMS = (
    # English
    (
        r"electric|power|energy|price|prices|cost|tariff|cheap|expensive|kwh|mwh|\bkw\b|watt|grid|"
        r"charg|\bev\b|heat pump|boiler|battery|\bload\b|appliance|washing|dishwasher|negative|"
        r"spot|day-ahead|peak|off-peak|solar|wind|usage|consum|"
        r"dryer|laundry|oven|sauna|\bpool\b|heater|heating|air con|hvac|immersion|thermostat|hot water"
    ),
    # German
    (
        r"strom|energie|preis|tarif|gunstig|billig|warmepumpe|elektr|aufladen|waschmaschine|"
        r"spulmaschine|geschirrspuler|verbrauch|photovoltaik"
    ),
    # French (electricite and electrique already match "electric")
    (
        r"energie|prix|tarif|moins cher|plus cher|pompe a chaleur|recharg|lave-linge|"
        r"lave-vaisselle|consommation|panneaux solaires|heures creuses"
    ),
    # Spanish (electricidad and electrico already match "electric")
    (
        r"energia|precio|tarifa|bomba de calor|cargar|lavadora|lavavajillas|consumo|mas barat|"
        r"mas car[oa]|placas solares"
    ),
    # Dutch
    (
        r"stroom|elektr|energie|prijs|prijzen|tarief|goedkoop|duurst|warmtepomp|opladen|"
        r"wasmachine|vaatwasser|verbruik|zonnepanelen"
    ),
    # Danish (strom, from "strøm", is in the German list)
    (
        r"\bel-?(pris|bil|forbrug|regning|afgift|tarif|net)|\bpris(en|er|erne)?\b|"
        r"energi\b|billigst|dyrest|varmepumpe|oplad|vaskemaskine|opvaskemaskine|\btorretumbler|"
        r"forbrug|solcelle|elkedel|negative priser|spotpris"
    ),
)
_TOPIC = re.compile("|".join(_TOPIC_STEMS))

# A second way in, for appliances no keyword list will ever finish: a question that asks when to
# run, start, use or heat something is about timing a load. English, plus Danish for the Danish testers. It lets more
# unusual questions reach the model, which the output guard, rate limits and spend cap exist for.
_TIMING = re.compile(
    r"\b(when|what time|best time|which hour|what hour|best hour|cheapest time|"
    r"hvornar|bedste tidspunkt|hvilken tid|hvilket tidspunkt|billigste tid)\b"
)
_ACTION = re.compile(
    r"\b(run|start|turn on|switch on|turn up|use|charge|heat|cook|wash|boil|dry|do|"
    r"kore|kor|starte|taende|bruge|oplade|lade|varme|vaske|torre|koge|lave)\b"
)

_MARKUP = re.compile(
    r"[<>]|https?:|www\.|javascript:|"
    r"\b[a-z0-9-]+\.(?:com|org|net|io|example|info|biz|xyz|top|app|dev|ru|cn|tk|ly)\b",
    re.IGNORECASE,
)
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


def fold(text: str) -> str:
    """Lower-case and strip accents, so keyword stems match across the covered languages."""
    # \u00df, \u00f8 and \u00e6 do not decompose, so map them by hand (Strasse, Kobenhavn, Sjaelland).
    lowered = text.lower().replace("\u00df", "ss").replace("\u00f8", "o").replace("\u00e6", "ae")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def check_question(question: str) -> str:
    """Return the cleaned question, or raise GuardRejected. Never calls a model."""
    cleaned = normalize(question)
    if not cleaned:
        raise _reject("empty", "input")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise _reject("too_long", "input")
    if _DELIMITERS.search(cleaned):
        raise _reject("delimiter", "input")
    folded = fold(cleaned)
    if not (_TOPIC.search(folded) or (_TIMING.search(folded) and _ACTION.search(folded))):
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
