"""Deterministic graders. No model judges another model here.

grounding: every number and every clock time in a brief must appear in the facts the model
was given. This catches invented figures, which is the failure that matters most.
"""

import re

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_PARTS = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _walk(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    else:
        yield value


def _allowed(facts: dict) -> tuple[set[float], set[str]]:
    numbers: set[float] = set()
    times: set[str] = set()
    for leaf in _walk(facts):
        if isinstance(leaf, bool):
            continue
        if isinstance(leaf, int | float):
            numbers.add(float(leaf))
        elif isinstance(leaf, str):
            for year, month, day in _DATE_PARTS.findall(leaf):
                numbers.update({float(year), float(month), float(day)})
            for h, m in _TIME.findall(leaf):
                times.add(f"{int(h):02d}:{m}")
            for token in _NUMBER.findall(_TIME.sub("", _DATE.sub("", leaf))):
                numbers.add(float(token))
    return numbers, times


def grounding_failures(text: str, facts: dict) -> list[str]:
    numbers, times = _allowed(facts)
    failures = []
    for h, m in _TIME.findall(text):
        stamp = f"{int(h):02d}:{m}"
        if stamp not in times:
            failures.append(f"time not in facts: {stamp}")
    stripped = _TIME.sub("", _DATE.sub("", text))
    for token in _NUMBER.findall(stripped):
        if float(token) not in numbers:
            failures.append(f"number not in facts: {token}")
    return failures


def forbidden_failures(text: str, forbidden: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [f"forbidden text present: {f}" for f in forbidden if f.lower() in lowered]


def missing_failures(text: str, must_contain: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [f"missing expected text: {m}" for m in must_contain if m.lower() not in lowered]
