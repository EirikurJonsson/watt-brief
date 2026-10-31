"""Deterministic graders. No model judges another model here."""

from watt_brief.grounding import grounding_failures

__all__ = ["forbidden_failures", "grounding_failures", "missing_failures"]


def forbidden_failures(text: str, forbidden: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [f"forbidden text present: {f}" for f in forbidden if f.lower() in lowered]


def missing_failures(text: str, must_contain: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [f"missing expected text: {m}" for m in must_contain if m.lower() not in lowered]
