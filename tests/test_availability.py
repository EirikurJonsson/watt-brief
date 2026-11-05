"""Questions that limit the hours of use ("I can charge between 08:00 and 16:00")."""

import json
from pathlib import Path

import httpx
import pytest

from watt_brief.analysis import Availability, analyse
from watt_brief.config import Settings
from watt_brief.entsoe import parse_day_ahead_xml
from watt_brief.llm import LLMClient
from watt_brief.pipeline import run_pipeline
from watt_brief.planner import make_plan, stated_hours

FIXTURE = Path(__file__).parent / "fixtures/day_ahead_full_day.xml"
# DE_LU on 31 October 2026 is on winter time: local = UTC + 1. Cheapest 3 hours overall: 10 to 13 UTC.


def series():
    return parse_day_ahead_xml(FIXTURE.read_text(), "DE_LU")


def test_hours_are_local_time_and_the_window_is_found_inside_them():
    # 15:00 to midnight local is 14:00 to 23:00 UTC; the cheapest window overall is outside it
    facts = analyse(series(), availability=Availability(15, 24))
    assert facts.fits_availability is True
    assert facts.cheapest_window.start_utc >= "2026-10-31T14:00Z"
    assert facts.cheapest_window.end_utc <= "2026-10-31T23:00Z"
    assert facts.availability == {
        "local_from": "15:00",
        "local_to": "00:00",
        "utc_from": "14:00",
        "utc_to": "23:00",
    }


def test_a_window_that_suits_the_hours_is_chosen_when_it_is_also_the_cheapest():
    facts = analyse(series(), availability=Availability(8, 16))  # 07:00 to 15:00 UTC
    assert (facts.cheapest_window.start_utc, facts.cheapest_window.end_utc) == (
        "2026-10-31T10:00Z",
        "2026-10-31T13:00Z",
    )
    assert facts.availability and facts.availability["utc_from"] == "07:00"


def test_when_no_window_fits_the_hours_the_whole_day_is_used_and_said_so():
    facts = analyse(series(), availability=Availability(8, 10))  # two hours, window needs three
    assert facts.fits_availability is False
    assert facts.cheapest_window.start_utc == "2026-10-31T10:00Z"


def test_hours_that_wrap_past_midnight_mean_the_night():
    facts = analyse(series(), availability=Availability(22, 6))  # 21:00 to 05:00 UTC
    assert facts.fits_availability is True
    assert facts.cheapest_window.start_utc == "2026-10-31T00:00Z"  # 01:00 to 04:00 local


def test_no_hours_means_nothing_changes():
    facts = analyse(series())
    assert facts.availability is None and facts.fits_availability is None


@pytest.mark.parametrize(
    "question, expected",
    [
        ("jeg starter arbejdet kl0800 til 1600, hvornar skal jeg lade", {8, 16}),
        ("between 8 and 16", {8, 16}),
        ("8:00-16:00", {8, 16}),
        ("open 08.00 til 16.00", {8, 16}),
        ("from 22 to 6", {22, 6}),
        ("until midnight", set()),
    ],
)
def test_hours_a_question_states(question, expected):
    assert expected <= stated_hours(question)
    if not expected:
        assert stated_hours(question) == set()


def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="planner-m",
        model_analyst="analyst-m",
        model_critic="critic-m",
    )


def scripted(plan: dict, brief: dict | None = None):
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body["messages"][1]["content"])
        content = plan if body["model"] == "planner-m" else brief
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "estimated_cost": 0.0},
            },
        )

    return LLMClient(settings(), transport=httpx.MockTransport(handler)), seen


QUESTION = "I work from 8 to 16 in Germany, when in between should I charge my EV?"
PLAN = {
    "zone": "DE_LU",
    "window_hours": 3,
    "intent": "cheapest_window",
    "available_from": 8,
    "available_to": 16,
}


def test_the_planner_passes_hours_the_question_states():
    client, _ = scripted(PLAN)
    plan, _, fallback = make_plan(client, settings(), QUESTION)
    assert not fallback
    assert plan.availability == Availability(8, 16)


def test_hours_the_question_does_not_state_are_dropped():
    client, _ = scripted({**PLAN, "available_from": 1, "available_to": 5})
    plan, _, _ = make_plan(client, settings(), QUESTION)
    assert plan.availability is None


@pytest.mark.parametrize(
    "bad", [{"available_to": None}, {"available_from": 8, "available_to": 8}, {"available_to": 30}]
)
def test_malformed_hours_make_the_plan_unusable_so_the_default_is_used(bad):
    from watt_brief.planner import DEFAULT_PLAN

    client, _ = scripted({**PLAN, **bad})
    plan, _, fallback = make_plan(client, settings(), QUESTION)
    assert fallback and plan == DEFAULT_PLAN


def test_the_pipeline_gives_the_analyst_facts_inside_the_hours():
    brief = {
        "recommendation": "Charge from 10:00 to 13:00 UTC, inside your 08:00 to 16:00 local hours.",
        "reasoning": "Your hours are 07:00 to 15:00 UTC. The window averages 3.00 EUR/MWh.",
        "caveats": ["Day-ahead prices only."],
    }
    client, seen = scripted(PLAN, brief)
    series_ = series()

    def get(zone, hours, availability=None):
        return analyse(series_, window_hours=hours, availability=availability)

    result = run_pipeline(client, settings(), QUESTION, get, use_planner=True)
    assert result.facts.fits_availability is True
    assert '"local_from": "08:00"' in seen[1] and '"utc_from": "07:00"' in seen[1]
