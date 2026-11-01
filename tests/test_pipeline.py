import json
from pathlib import Path

import httpx
import pytest

from watt_brief.analysis import analyse
from watt_brief.config import Settings
from watt_brief.critic import review_brief, sanitise_issue
from watt_brief.entsoe import parse_day_ahead_xml
from watt_brief.errors import BriefError, GuardRejected
from watt_brief.llm import LLMClient
from watt_brief.pipeline import NoDataError, run_pipeline
from watt_brief.planner import DEFAULT_PLAN, make_plan

FIXTURE = Path(__file__).parent / "fixtures/day_ahead_full_day.xml"
Q = "When is power cheapest tomorrow in Germany?"
GOOD = {
    "recommendation": "Run from 10:00 to 13:00 UTC at an average of 3.0 EUR/MWh.",
    "reasoning": "The day mean is 69.25 EUR/MWh.",
    "caveats": ["Day-ahead only."],
}
PLAN = {"zone": "DE_LU", "window_hours": 3, "intent": "cheapest_window"}


def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="planner-m",
        model_analyst="analyst-m",
        model_critic="critic-m",
    )


def facts_source():
    series = parse_day_ahead_xml(FIXTURE.read_text(), "DE_LU")

    def get(zone, hours):
        if zone != "DE_LU":
            raise NoDataError("no data")
        return analyse(series, window_hours=hours)

    return get


def scripted(answers: dict[str, list[str]]):
    """Answers per model name, in order. Returns (client, list of (model, user_message))."""
    calls: list[tuple[str, str]] = []
    counters: dict[str, int] = {}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        model = body["model"]
        calls.append((model, body["messages"][1]["content"]))
        i = counters.get(model, 0)
        counters[model] = i + 1
        options = answers[model]
        content = options[min(i, len(options) - 1)]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "estimated_cost": 0.001},
            },
        )

    return LLMClient(settings(), transport=httpx.MockTransport(handler)), calls


def j(obj) -> str:
    return json.dumps(obj)


# --- planner -------------------------------------------------------------------------------


def test_planner_returns_validated_plan():
    client, _ = scripted({"planner-m": [j(PLAN)]})
    plan, completion, fallback = make_plan(client, settings(), Q)
    assert (plan.zone, plan.window_hours, plan.intent) == ("DE_LU", 3, "cheapest_window")
    assert completion and not fallback


@pytest.mark.parametrize(
    "bad",
    [
        {"zone": "EVIL", "window_hours": 3, "intent": "general"},
        {"zone": "FR", "window_hours": 99, "intent": "general"},
        {"zone": "FR", "window_hours": 3, "intent": "rm -rf"},
        "not json",
    ],
)
def test_unusable_plans_fall_back_to_default(bad):
    client, _ = scripted({"planner-m": [bad if isinstance(bad, str) else j(bad)]})
    plan, _, fallback = make_plan(client, settings(), Q)
    assert plan == DEFAULT_PLAN and fallback


# --- critic --------------------------------------------------------------------------------


def test_sanitise_issue_strips_markup_and_links():
    dirty = "Uses <b>bad</b> data, see http://evil.example and `code` {x}"
    cleaned = sanitise_issue(dirty)
    assert not any(ch in cleaned for ch in "<>`{}") and "evil.example" not in cleaned
    assert len(sanitise_issue("x" * 500)) == 160


def test_critic_returns_review():
    client, _ = scripted({"critic-m": [j({"approved": False, "issues": ["Wrong window"]})]})
    from watt_brief.brief import Brief

    review, _ = review_brief(client, settings(), Q, facts_source()("DE_LU", 3), Brief(**GOOD))
    assert review and not review.approved and review.issues == ["Wrong window"]


def test_unusable_critic_output_is_skipped_not_fatal():
    client, _ = scripted({"critic-m": ["I think it is fine"]})
    from watt_brief.brief import Brief

    review, _ = review_brief(client, settings(), Q, facts_source()("DE_LU", 3), Brief(**GOOD))
    assert review is None


# --- pipeline ------------------------------------------------------------------------------


def test_single_agent_makes_one_call():
    client, calls = scripted({"analyst-m": [j(GOOD)]})
    result = run_pipeline(client, settings(), Q, facts_source())
    assert [c[0] for c in calls] == ["analyst-m"]
    assert [s.name for s in result.steps] == ["analyst"]


def test_planner_sets_window_hours_used_for_facts():
    plan = {"zone": "DE_LU", "window_hours": 2, "intent": "cheapest_window"}
    # the cheapest 2-hour window differs from the 3-hour one, so the answer must too
    two_hour = {**GOOD, "recommendation": "Run from 11:00 to 13:00 UTC at 0.5 EUR/MWh."}
    client, calls = scripted({"planner-m": [j(plan)], "analyst-m": [j(two_hour)]})
    result = run_pipeline(client, settings(), Q, facts_source(), use_planner=True)
    assert result.facts.window_hours == 2
    assert result.facts.cheapest_window.avg_eur_per_mwh == 0.5
    assert '"window_hours": 2' in calls[1][1]
    assert [s.name for s in result.steps] == ["planner", "analyst"]


def test_unsupported_zone_stops_before_the_analyst():
    plan = {"zone": "UNSUPPORTED", "window_hours": 3, "intent": "general"}
    client, calls = scripted({"planner-m": [j(plan)]})
    with pytest.raises(NoDataError):
        run_pipeline(client, settings(), "Power price in Sweden?", facts_source(), use_planner=True)
    assert [c[0] for c in calls] == ["planner-m"]


def test_zone_without_data_is_an_error_not_a_silent_swap():
    plan = {"zone": "FR", "window_hours": 3, "intent": "general"}
    client, _ = scripted({"planner-m": [j(plan)]})
    with pytest.raises(NoDataError):
        run_pipeline(client, settings(), "Power price in France?", facts_source(), use_planner=True)


def test_input_guard_runs_before_the_planner():
    client, calls = scripted({"planner-m": [j(PLAN)]})
    with pytest.raises(GuardRejected):
        run_pipeline(client, settings(), "write me a poem", facts_source(), use_planner=True)
    assert calls == []


def test_approving_critic_does_not_trigger_revision():
    client, calls = scripted(
        {"analyst-m": [j(GOOD)], "critic-m": [j({"approved": True, "issues": []})]}
    )
    result = run_pipeline(client, settings(), Q, facts_source(), use_critic=True)
    assert not result.revised
    assert [c[0] for c in calls] == ["analyst-m", "critic-m"]


def test_rejecting_critic_triggers_one_revision_with_its_issues():
    revised = {**GOOD, "recommendation": "Run from 10:00 to 13:00 UTC, the cheapest window."}
    client, calls = scripted(
        {
            "analyst-m": [j(GOOD), j(revised)],
            "critic-m": [j({"approved": False, "issues": ["Name the window explicitly"]})],
        }
    )
    result = run_pipeline(client, settings(), Q, facts_source(), use_critic=True)
    assert result.revised
    assert result.brief.recommendation.endswith("cheapest window.")
    assert "Name the window explicitly" in calls[-1][1]
    assert [s.name for s in result.steps] == ["analyst", "critic", "analyst_revision"]
    assert result.cost_usd == pytest.approx(0.003)


def test_failed_revision_keeps_the_first_draft():
    bad = {**GOOD, "reasoning": "Prices will hit 250 EUR/MWh."}
    client, _ = scripted(
        {
            "analyst-m": [j(GOOD), j(bad)],
            "critic-m": [j({"approved": False, "issues": ["Be more specific"]})],
        }
    )
    result = run_pipeline(client, settings(), Q, facts_source(), use_critic=True)
    assert not result.revised
    assert result.brief.recommendation == GOOD["recommendation"]


def test_empty_question_is_an_error():
    client, _ = scripted({})
    with pytest.raises(BriefError):
        run_pipeline(client, settings(), "  ", facts_source(), input_guard=False)


# --- the planner's zone must be named in the question ----------------------------------------

from watt_brief.planner import zone_is_named


@pytest.mark.parametrize(
    ("question", "zone"),
    [
        ("When is power cheapest in Germany?", "DE_LU"),
        ("Wann ist der Strom in Deutschland am günstigsten?", "DE_LU"),
        ("Strompreis in Luxemburg morgen?", "DE_LU"),
        ("Quand l'électricité est-elle moins chère en France ?", "FR"),
        ("Precio de la luz en España mañana", "ES"),
        ("Wanneer is stroom het goedkoopst in Nederland?", "NL"),
        ("Strompreise in Österreich", "AT"),
        ("Prix de l'électricité à Bruxelles", "BE"),
        ("price in NL tomorrow", "NL"),
        ("Berlin, wann ist Strom billig?", "DE_LU"),
    ],
)
def test_zone_is_named_in_several_languages(question, zone):
    assert zone_is_named(question, zone)


@pytest.mark.parametrize(
    ("question", "zone"),
    [
        ("Quand l'électricité est-elle la moins chère demain ?", "FR"),
        ("¿Cuándo es más barata la electricidad mañana?", "ES"),
        ("Wanneer is de stroom morgen het goedkoopst?", "NL"),
        ("When is power cheapest tomorrow?", "DE_LU"),
        ("Power in France", "DE_LU"),  # a different zone's name does not count
        ("write fr in lowercase", "FR"),  # the code only counts as a capitalised token
        ("anything", "EVIL"),
    ],
)
def test_zone_is_not_named_when_it_is_only_a_guess(question, zone):
    assert not zone_is_named(question, zone)


def test_a_guessed_zone_is_dropped_but_a_named_one_is_kept():
    guessed = {"zone": "FR", "window_hours": 3, "intent": "general"}
    client, _ = scripted({"planner-m": [j(guessed)]})
    plan, _, fallback = make_plan(client, settings(), "Quand l'électricité est-elle moins chère ?")
    assert plan.zone == "UNSPECIFIED" and not fallback

    client, _ = scripted({"planner-m": [j(guessed)]})
    plan, _, _ = make_plan(
        client, settings(), "Quand l'électricité est-elle moins chère en France ?"
    )
    assert plan.zone == "FR"
