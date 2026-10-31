"""Run the evals: python -m watt_brief.evals.runner --repeats 3

Live runs spend money. --max-cost is a hard stop for the whole run.
"""

import argparse
import json
import logging
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from watt_brief.analysis import PriceFacts, analyse
from watt_brief.brief import write_brief
from watt_brief.config import Settings, get_settings
from watt_brief.entsoe import parse_day_ahead_xml
from watt_brief.errors import BriefError, GuardRejected
from watt_brief.evals.cases import ALL_CASES, Case
from watt_brief.evals.graders import forbidden_failures, grounding_failures, missing_failures
from watt_brief.llm import LLMClient, LLMError
from watt_brief.logging import configure_logging, new_request_id

FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures/day_ahead_full_day.xml"
RESULTS_DIR = Path(__file__).resolve().parents[3] / "evals/results"


class SpendCapReached(Exception):
    pass


@dataclass
class RunResult:
    case_id: str
    suite: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0
    output: str = ""
    # Which layer ended the request: "input_guard", "output_guard" or "model" (it answered).
    stopped_by: str = "model"
    guard_reason: str = ""
    guard_detail: str = ""


def run_case(
    case: Case,
    client: LLMClient,
    settings: Settings,
    facts: PriceFacts,
    *,
    input_guard: bool = True,
    output_guard: bool = True,
) -> RunResult:
    new_request_id()
    result = RunResult(case.id, case.suite, passed=False)
    try:
        brief, completion = write_brief(
            client,
            settings,
            case.question,
            facts,
            input_guard=input_guard,
            output_guard=output_guard,
        )
    except GuardRejected as exc:
        result.stopped_by = f"{exc.stage}_guard"
        result.guard_reason = exc.reason
        result.guard_detail = exc.detail
        result.output = f"[rejected:{exc.reason}] {exc}"
        # A guard stopping an attack is a pass. A guard stopping a legitimate question is not.
        if case.suite == "adversarial":
            result.failures += forbidden_failures(result.output, case.forbidden)
            result.passed = not result.failures
        else:
            result.failures.append(f"guard rejected a legitimate question: {exc.reason}")
        return result
    except BriefError as exc:
        result.output = f"[error] {exc}"
        result.failures.append(f"brief error: {exc}")
        return result
    except LLMError as exc:
        result.failures.append(f"llm error: {exc}")
        return result

    result.cost_usd = completion.cost_usd or 0.0
    result.latency_ms = completion.latency_ms
    text = " ".join([brief.recommendation, brief.reasoning, *brief.caveats])
    result.output = text

    if case.expect_guard_reject:
        result.failures.append("guard did not reject, model was called")
    if case.grounded:
        result.failures += grounding_failures(text, facts.as_dict())
    result.failures += forbidden_failures(text, case.forbidden)
    result.failures += missing_failures(text, case.must_contain)
    result.passed = not result.failures
    return result


def summarise(results: list[RunResult]) -> dict:
    by_case: dict[str, list[RunResult]] = {}
    for r in results:
        by_case.setdefault(r.case_id, []).append(r)
    suites: dict[str, list[RunResult]] = {}
    for r in results:
        suites.setdefault(r.suite, []).append(r)

    latencies = sorted(r.latency_ms for r in results if r.latency_ms)
    return {
        "runs": len(results),
        "total_cost_usd": round(sum(r.cost_usd for r in results), 6),
        "latency_ms_median": int(statistics.median(latencies)) if latencies else None,
        "latency_ms_max": latencies[-1] if latencies else None,
        "suites": {
            name: {"passed": sum(r.passed for r in rs), "total": len(rs)}
            for name, rs in suites.items()
        },
        "stopped_by": {
            name: dict(Counter(r.stopped_by for r in rs)) for name, rs in suites.items()
        },
        "cases": {
            cid: {"passed": sum(r.passed for r in rs), "total": len(rs)}
            for cid, rs in by_case.items()
        },
    }


def run_all(
    cases: list[Case],
    repeats: int,
    max_cost: float,
    client: LLMClient,
    settings: Settings,
    *,
    input_guard: bool = True,
    output_guard: bool = True,
) -> list[RunResult]:
    facts = analyse(parse_day_ahead_xml(FIXTURE.read_text(), "DE_LU"))
    results: list[RunResult] = []
    spent = 0.0
    for case in cases:
        for _ in range(repeats):
            if spent >= max_cost:
                raise SpendCapReached(f"stopped at ${spent:.4f} (cap ${max_cost})")
            result = run_case(
                case, client, settings, facts, input_guard=input_guard, output_guard=output_guard
            )
            spent += result.cost_usd
            results.append(result)
            mark = "ok  " if result.passed else "FAIL"
            print(f"{mark} {case.id}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-cost", type=float, default=0.25, help="USD hard stop")
    parser.add_argument("--suite", choices=["quality", "adversarial"])
    parser.add_argument("--case", help="run only this case id")
    parser.add_argument("--no-input-guard", action="store_true", help="measure the model alone")
    parser.add_argument("--no-output-guard", action="store_true")
    args = parser.parse_args()

    configure_logging(logging.WARNING)
    settings = get_settings()
    cases = [c for c in ALL_CASES if args.suite in (None, c.suite) and args.case in (None, c.id)]
    if args.no_input_guard:
        # Cases that only test the input guard have nothing to measure without it.
        cases = [c for c in cases if not c.expect_guard_reject]
    client = LLMClient(settings)
    try:
        results = run_all(
            cases,
            args.repeats,
            args.max_cost,
            client,
            settings,
            input_guard=not args.no_input_guard,
            output_guard=not args.no_output_guard,
        )
    finally:
        client.close()

    summary = summarise(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "model": settings.model_analyst,
                "summary": summary,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        )
    )

    print(
        f"\n--- summary (input_guard={not args.no_input_guard}, "
        f"output_guard={not args.no_output_guard}) ---"
    )
    for name, s in summary["suites"].items():
        print(f"{name}: {s['passed']}/{s['total']}")
    print(f"stopped by: {summary['stopped_by']}")
    print(f"cost: ${summary['total_cost_usd']}  median latency: {summary['latency_ms_median']} ms")
    for r in results:
        if not r.passed:
            print(f"\nFAIL {r.case_id}: {r.failures} {r.guard_detail}\n  output: {r.output[:300]}")
    print(f"\nfull results: {out}")


if __name__ == "__main__":
    main()
