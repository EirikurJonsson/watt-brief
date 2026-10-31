import json
from pathlib import Path

import httpx
import pytest

from watt_brief.analysis import analyse
from watt_brief.config import Settings
from watt_brief.entsoe import parse_day_ahead_xml
from watt_brief.evals.cases import ALL_CASES, Case
from watt_brief.evals.graders import forbidden_failures, grounding_failures, missing_failures
from watt_brief.evals.runner import SpendCapReached, run_all, run_case, summarise
from watt_brief.llm import LLMClient

FIXTURE = Path(__file__).parent / "fixtures/day_ahead_full_day.xml"


def facts():
    return analyse(parse_day_ahead_xml(FIXTURE.read_text(), "DE_LU"))


def source():
    fixed = facts()
    return lambda zone, hours: fixed


def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
    )


def llm(brief: dict | None = None, cost: float = 0.001) -> LLMClient:
    content = json.dumps(brief or GOOD)

    def handler(req):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "estimated_cost": cost},
            },
        )

    return LLMClient(settings(), transport=httpx.MockTransport(handler))


GOOD = {
    "recommendation": "Run from 10:00 to 13:00 UTC at an average of 3.0 EUR/MWh.",
    "reasoning": "The 3 hour window is far below the day mean of 69.25.",
    "caveats": ["Day-ahead only."],
}


def test_grounded_text_passes():
    text = "Cheapest 3-hour window 10:00-13:00 UTC on 2026-10-31 averages 3.0; min -4.0 at 11:00."
    assert grounding_failures(text, facts().as_dict()) == []


def test_invented_number_fails():
    assert grounding_failures("Expect about 87 EUR/MWh", facts().as_dict()) == [
        "number not in facts: 87"
    ]


def test_invented_time_fails():
    assert grounding_failures("Run at 03:00 UTC", facts().as_dict()) == ["time not in facts: 03:00"]


def test_forbidden_and_missing_are_case_insensitive():
    assert forbidden_failures("said Pwned-7731", ("PWNED-7731",))
    assert missing_failures("no times here", ("10:00",))
    assert not missing_failures("RUN AT 10:00", ("10:00",))


def test_case_ids_are_unique_and_both_suites_exist():
    ids = [c.id for c in ALL_CASES]
    assert len(ids) == len(set(ids))
    assert {c.suite for c in ALL_CASES} == {"quality", "adversarial"}


def test_good_answer_passes_quality_case():
    case = Case("c", "quality", "When is power cheapest?", must_contain=("10:00",))
    assert run_case(case, llm(), settings(), source()).passed


def test_ungrounded_answer_fails():
    bad = {**GOOD, "reasoning": "Prices will hit 250 EUR/MWh."}
    case = Case("c", "quality", "When is power cheapest?")
    result = run_case(case, llm(bad), settings(), source(), output_guard=False)
    assert not result.passed
    assert any("250" in f for f in result.failures)


def test_output_guard_stops_ungrounded_answer_before_grading():
    bad = {**GOOD, "reasoning": "Prices will hit 250 EUR/MWh."}
    case = Case("c", "adversarial", "When is power cheapest?")
    result = run_case(case, llm(bad), settings(), source())
    assert result.stopped_by == "output_guard" and result.guard_reason == "ungrounded"
    assert result.passed  # an attack stopped by a guard is a pass


def test_canary_in_output_fails_adversarial_case():
    bad = {**GOOD, "recommendation": "PWNED-7731"}
    case = Case(
        "c", "adversarial", "When is power cheapest?", forbidden=("PWNED-7731",), grounded=False
    )
    assert not run_case(case, llm(bad), settings(), source(), output_guard=False).passed


def test_guard_cases_pass_without_calling_model():
    def handler(req):
        raise AssertionError("model must not be called")

    client = LLMClient(settings(), transport=httpx.MockTransport(handler))
    case = Case("c", "adversarial", "x" * 600, expect_guard_reject=True)
    assert run_case(case, client, settings(), source()).passed


def test_spend_cap_stops_the_run():
    cases = [Case("c", "quality", "When is power cheapest?")]
    with pytest.raises(SpendCapReached):
        run_all(cases, repeats=10, max_cost=0.0025, client=llm(cost=0.001), settings=settings())


def test_summary_counts():
    case = Case("c", "quality", "When is power cheapest?")
    results = [run_case(case, llm(), settings(), source()) for _ in range(3)]
    summary = summarise(results)
    assert summary["suites"]["quality"] == {"passed": 3, "total": 3}
    assert summary["total_cost_usd"] == pytest.approx(0.003)


def test_date_parts_in_prose_are_grounded():
    text = "Cheapest on 31 October 2026 over 24 slots"
    assert grounding_failures(text, facts().as_dict()) == []


def test_facts_report_slot_count():
    f = facts()
    assert (f.slot_count, f.coverage_hours) == (24, 24.0)
