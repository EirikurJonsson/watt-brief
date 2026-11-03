"""The full flow: guard -> plan -> facts -> analyst -> critic -> (one revision).

Planner and critic are switchable so the evals can measure whether they earn their cost.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from watt_brief.analysis import PriceFacts
from watt_brief.brief import Brief, write_brief
from watt_brief.config import Settings
from watt_brief.critic import Review, review_brief
from watt_brief.errors import BriefError, GuardRejected
from watt_brief.guards import check_question
from watt_brief.llm import Completion, LLMClient
from watt_brief.logging import log
from watt_brief.planner import DEFAULT_PLAN, UNSPECIFIED, UNSUPPORTED, Plan, make_plan

logger = logging.getLogger(__name__)

DEFAULT_ZONE = "DE_LU"

# (zone, window_hours) -> facts. Raises NoDataError when the zone has no data.
FactsSource = Callable[[str, int], PriceFacts]


class NoDataError(BriefError):
    pass


@dataclass(frozen=True)
class Step:
    name: str
    model: str
    cost_usd: float
    latency_ms: int
    input_tokens: int
    output_tokens: int


@dataclass
class PipelineResult:
    brief: Brief
    facts: PriceFacts
    plan: Plan
    review: Review | None = None
    revised: bool = False
    steps: list[Step] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.steps)

    @property
    def latency_ms(self) -> int:
        return sum(s.latency_ms for s in self.steps)


def _step(name: str, model: str, c: Completion) -> Step:
    return Step(name, model, c.cost_usd or 0.0, c.latency_ms, c.input_tokens, c.output_tokens)


def run_pipeline(
    client: LLMClient,
    settings: Settings,
    question: str,
    get_facts: FactsSource,
    *,
    use_planner: bool = False,
    use_critic: bool = False,
    zone: str | None = None,
    input_guard: bool = True,
    output_guard: bool = True,
) -> PipelineResult:
    steps: list[Step] = []

    try:
        question = check_question(question) if input_guard else question.strip()
    except GuardRejected as exc:
        log(
            logger,
            "guard_rejected",
            stage=exc.stage,
            reason=exc.reason,
            question_chars=len(question),
        )
        raise
    if not question:
        raise BriefError("the question is empty")

    plan = DEFAULT_PLAN
    if use_planner:
        plan, planner_completion, _ = make_plan(client, settings, question)
        if planner_completion:
            steps.append(_step("planner", settings.model_planner, planner_completion))

    # A zone chosen in the selector wins over any country named in the question.
    if zone is None:
        if plan.zone == UNSUPPORTED:
            raise NoDataError("I only cover DE_LU, FR, NL, BE, AT and ES day-ahead prices for now.")
        zone = DEFAULT_ZONE if plan.zone == UNSPECIFIED else plan.zone
    facts = get_facts(zone, plan.window_hours)

    brief, completion = write_brief(
        client, settings, question, facts, input_guard=False, output_guard=output_guard
    )
    steps.append(_step("analyst", settings.model_analyst, completion))
    result = PipelineResult(brief=brief, facts=facts, plan=plan, steps=steps)

    if use_critic:
        review, critic_completion = review_brief(client, settings, question, facts, brief)
        if critic_completion:
            steps.append(_step("critic", settings.model_critic, critic_completion))
        result.review = review
        if review and not review.approved and review.issues:
            note = (
                "A reviewer found problems with your previous draft: "
                + "; ".join(review.issues)
                + ". Fix them using only values in FACTS."
            )
            try:
                revised, revision_completion = write_brief(
                    client,
                    settings,
                    question,
                    facts,
                    input_guard=False,
                    output_guard=output_guard,
                    note=note,
                )
            except BriefError as exc:
                # The first draft already passed the guards. Keep it.
                log(logger, "revision_failed", reason=type(exc).__name__)
            else:
                steps.append(_step("analyst_revision", settings.model_analyst, revision_completion))
                result.brief = revised
                result.revised = True

    log(
        logger,
        "pipeline_ok",
        zone=zone,
        planner=use_planner,
        critic=use_critic,
        revised=result.revised,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    return result
