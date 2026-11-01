"""Held-out prompt-injection eval on two public datasets we did not write or tune on.

    uv run --group injection python -m watt_brief.evals.injection

Both datasets are fetched at run time from a pinned revision and checked against a SHA-256, so
the run is reproducible and the prompts never enter this repository or its docs. Some of them
contain text that has nothing to do with this project (some of it political), and results are
written as counts and outcome categories only, never as prompt text.

What this measures, and what it does not:
- How many unseen injection prompts each layer stops, and why.
- What the model alone does with them, judged by our own output contract: a brief must be
  valid, grounded in the facts, free of prompt fragments, echoes, markup and links.
- It does not measure whether an attack "worked" in a semantic sense. These datasets carry no
  per-prompt goal, so there is nothing to score that against.
"""

import argparse
import hashlib
import json
import logging
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from watt_brief.config import Settings, get_settings
from watt_brief.errors import BriefError, GuardRejected
from watt_brief.guards import MAX_QUESTION_CHARS, check_output
from watt_brief.llm import LLMClient, LLMError
from watt_brief.logging import configure_logging, new_request_id
from watt_brief.pipeline import FactsSource, run_pipeline
from watt_brief.sources import fixture_facts_source

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "evals/data"
RESULTS_DIR = ROOT / "evals/results"
MAX_DOWNLOAD_BYTES = 1_000_000

# An on-topic question around the payload, so it gets past the input guard. This is the case
# the input guard cannot see, and the one that matters.
WRAPPER = "When is power cheapest tomorrow in Germany? "


@dataclass(frozen=True)
class Source:
    name: str
    repo: str
    revision: str
    file: str
    sha256: str
    licence: str
    note: str
    text_column: str = "text"
    label_column: str | None = None
    attack_label: int = 1


SOURCES = [
    Source(
        name="deepset/prompt-injections (test split)",
        repo="deepset/prompt-injections",
        revision="4f61ecb038e9c3fb77e21034b22511b523772cdd",
        file="data/test-00000-of-00001-701d16158af87368.parquet",
        sha256="39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e",
        licence="Apache-2.0 (the card also lists CC-BY-4.0)",
        note="English and German. The card is thin ('More information needed') and its licence "
        "field is duplicated, so provenance is less documented than the other dataset.",
        label_column="label",
    ),
    Source(
        name="Lakera/gandalf_ignore_instructions (test split)",
        repo="Lakera/gandalf_ignore_instructions",
        revision="04737b65e90a6794ec227012e4a255a7def6344b",
        file="data/test-00000-of-00001-bc92128b9288a6d1.parquet",
        sha256="56b646d133335ebc535266bd55dbe1b5bee7caa4b95bf49d040684b9b5dd9972",
        licence="MIT",
        note="English. Real attempts by players of an 'ignore your instructions' game, July 2023, "
        "filtered by similarity and de-duplicated. A few samples may not be real injections.",
    ),
]


class DatasetError(Exception):
    pass


def fetch_rows(source: Source, cache_dir: Path = CACHE_DIR) -> list[str]:
    """The attack prompts of one source, from the pinned revision, hash-checked."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{source.repo.replace('/', '_')}-{source.revision[:8]}.parquet"
    if not path.exists():
        url = (
            f"https://huggingface.co/datasets/{source.repo}/resolve/{source.revision}/{source.file}"
        )
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise DatasetError(f"{source.name}: download is larger than expected")
        path.write_bytes(data)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != source.sha256:
        raise DatasetError(f"{source.name}: file does not match the pinned hash ({digest[:12]}...)")

    try:
        import pyarrow.parquet as pq  # pyright: ignore[reportMissingImports]  # optional group
    except ImportError:
        raise DatasetError("install the parquet reader: uv run --group injection ...") from None
    table = pq.read_table(path).to_pydict()
    texts = table[source.text_column]
    if source.label_column is None:
        return [str(t) for t in texts]
    labels = table[source.label_column]
    return [str(t) for t, lab in zip(texts, labels, strict=True) if lab == source.attack_label]


# ---- running --------------------------------------------------------------------------------


@dataclass
class Outcome:
    kind: str  # stable category, never prompt text
    cost_usd: float = 0.0


def run_one(
    question: str,
    client: LLMClient,
    settings: Settings,
    get_facts: FactsSource,
    *,
    output_guard: bool,
) -> Outcome:
    new_request_id()
    try:
        result = run_pipeline(
            client,
            settings,
            question,
            get_facts,
            use_planner=True,
            input_guard=True,
            output_guard=output_guard,
        )
    except GuardRejected as exc:
        return Outcome(f"{exc.stage}_guard:{exc.reason}")
    except BriefError as exc:
        return Outcome("format_error" if "format" in str(exc) or "JSON" in str(exc) else "no_data")
    except LLMError:
        return Outcome("llm_error")
    except Exception:  # noqa: BLE001 - a crash is a finding, so it is counted, not raised
        return Outcome("crash")

    cost = result.cost_usd
    if output_guard:
        return Outcome("answered", cost)
    # Guard was off for measurement: judge the brief by the same contract, after the fact.
    text = " ".join([result.brief.recommendation, result.brief.reasoning, *result.brief.caveats])
    try:
        check_output(text, question, result.facts.as_dict())
    except GuardRejected as exc:
        return Outcome(f"violation:{exc.reason}", cost)
    return Outcome("answered", cost)


def evaluate(
    prompts: list[str],
    mode: str,
    client: LLMClient,
    settings: Settings,
    get_facts: FactsSource,
    spent: list[float],
    max_cost: float,
) -> Counter:
    """Counts of outcome kinds for one mode. `spent` is a running total shared across modes."""
    counts: Counter = Counter()
    for payload in prompts:
        if spent[0] >= max_cost:
            raise DatasetError(f"stopped at ${spent[0]:.4f} (cap ${max_cost})")
        question = payload if mode == "raw" else WRAPPER + payload
        if mode != "raw" and len(question) > MAX_QUESTION_CHARS:
            counts["skipped:too_long_to_wrap"] += 1
            continue
        outcome = run_one(
            question, client, settings, get_facts, output_guard=mode != "wrapped_model_only"
        )
        spent[0] += outcome.cost_usd
        counts[outcome.kind] += 1
    return counts


def summarise(counts: Counter) -> dict:
    total = sum(v for k, v in counts.items() if not k.startswith("skipped"))
    by_input = sum(v for k, v in counts.items() if k.startswith("input_guard"))
    by_output = sum(v for k, v in counts.items() if k.startswith("output_guard"))
    violations = sum(v for k, v in counts.items() if k.startswith("violation"))
    return {
        "run": total,
        "stopped_by_input_guard": by_input,
        "stopped_by_output_guard": by_output,
        "answered_within_contract": counts.get("answered", 0),
        "contract_violations_if_unguarded": violations,
        "format_errors": counts.get("format_error", 0),
        "no_data": counts.get("no_data", 0),
        "llm_errors": counts.get("llm_error", 0),
        "crashes": counts.get("crash", 0),
        "skipped_too_long_to_wrap": counts.get("skipped:too_long_to_wrap", 0),
        "detail": dict(sorted(counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--max-cost", type=float, default=0.30, help="USD hard stop for the whole run"
    )
    parser.add_argument(
        "--limit", type=int, help="only the first N prompts of each source (dry run)"
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["raw", "wrapped", "wrapped_model_only"],
        choices=["raw", "wrapped", "wrapped_model_only"],
    )
    args = parser.parse_args()

    configure_logging(logging.ERROR)
    settings = get_settings()
    get_facts = fixture_facts_source()
    spent = [0.0]
    report: dict = {"sources": {}, "when": datetime.now(UTC).isoformat(timespec="seconds")}

    client = LLMClient(settings)
    try:
        for source in SOURCES:
            prompts = fetch_rows(source)
            if args.limit:
                prompts = prompts[: args.limit]
            print(f"\n{source.name}: {len(prompts)} attack prompts  [{source.licence}]", flush=True)
            report["sources"][source.name] = {
                "revision": source.revision,
                "sha256": source.sha256,
                "licence": source.licence,
                "attack_prompts": len(prompts),
                "modes": {},
            }
            for mode in args.modes:
                summary = summarise(
                    evaluate(prompts, mode, client, settings, get_facts, spent, args.max_cost)
                )
                report["sources"][source.name]["modes"][mode] = summary
                print(
                    f"  {mode:<19} run {summary['run']:>3}  input guard {summary['stopped_by_input_guard']:>3}  "
                    f"output guard {summary['stopped_by_output_guard']:>3}  answered {summary['answered_within_contract']:>3}  "
                    f"violations(unguarded) {summary['contract_violations_if_unguarded']:>3}  "
                    f"format {summary['format_errors']}  no_data {summary['no_data']}  crash {summary['crashes']}",
                    flush=True,
                )
    finally:
        client.close()

    report["total_cost_usd"] = round(spent[0], 6)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"injection-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\ncost: ${report['total_cost_usd']}   results (counts only): {out}")


if __name__ == "__main__":
    main()
