"""Property-based tests: the parser and the guards must survive input nobody planned for.

The ENTSO-E response and the user's question are both untrusted. Example tests cover the shapes we
have seen; these let Hypothesis look for the ones we have not.
"""

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from watt_brief.entsoe import EntsoeError, parse_day_ahead_xml
from watt_brief.errors import GuardRejected
from watt_brief.guards import check_output, check_question

VALID = (Path(__file__).parent / "fixtures/day_ahead_full_day.xml").read_text()
FACTS = {"zone": "DE_LU", "cheapest_window": {"start": "02:00", "end": "05:00", "avg": 10.5}}

# A short fixed budget keeps CI quick and the run reproducible enough to debug.
quick = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def parses_or_refuses(xml: str) -> None:
    try:
        series = parse_day_ahead_xml(xml, "DE_LU")
    except EntsoeError:
        return  # a clean refusal is the correct answer to bad input
    assert series.points
    starts = [p.start for p in series.points]
    assert starts == sorted(starts)


@quick
@given(st.text())
def test_arbitrary_text_is_never_an_unhandled_error(text):
    parses_or_refuses(text)


@quick
@given(st.integers(0, len(VALID) - 1), st.integers(1, 400), st.text(max_size=40))
def test_a_valid_response_with_a_piece_replaced_is_parsed_or_refused(at, width, junk):
    parses_or_refuses(VALID[:at] + junk + VALID[at + width :])


@quick
@given(st.integers(0, len(VALID)))
def test_a_truncated_response_is_parsed_or_refused(cut):
    parses_or_refuses(VALID[:cut])


@quick
@given(
    st.sampled_from(["position", "price.amount", "resolution", "start", "end"]),
    st.text(max_size=30),
)
def test_any_field_holding_garbage_is_parsed_or_refused(tag, value):
    import re

    broken = re.sub(
        rf"(<{re.escape(tag)}>)[^<]*(</{re.escape(tag)}>)", rf"\g<1>{re.escape(value)}\g<2>", VALID
    )
    parses_or_refuses(broken.replace("\\", ""))


def test_entity_expansion_bombs_are_refused():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        "<x>&b;&b;&b;&b;</x>"
    )
    try:
        parse_day_ahead_xml(bomb, "DE_LU")
    except EntsoeError:
        return
    raise AssertionError("an XML with entity definitions must be refused")


@quick
@given(st.text(max_size=600))
def test_the_question_guard_only_ever_accepts_or_rejects(question):
    try:
        check_question(question)
    except GuardRejected:
        pass


@quick
@given(st.text(max_size=600), st.text(max_size=100))
def test_the_output_guard_only_ever_accepts_or_rejects(text, question):
    try:
        check_output(text, question, FACTS)
    except GuardRejected:
        pass
