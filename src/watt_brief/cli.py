"""Dev entry point: python -m watt_brief.cli --fixture tests/fixtures/day_ahead_full_day.xml "..."

--fixture reads a local XML file, so it works without an ENTSO-E token. Output from a fixture
is NOT real market data.
"""

import argparse
from pathlib import Path

from watt_brief.analysis import analyse
from watt_brief.brief import write_brief
from watt_brief.config import get_settings
from watt_brief.entsoe import parse_day_ahead_xml
from watt_brief.llm import LLMClient
from watt_brief.logging import configure_logging, new_request_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--zone", default="DE_LU")
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()

    configure_logging()
    new_request_id()
    settings = get_settings()
    series = parse_day_ahead_xml(args.fixture.read_text(), args.zone)
    facts = analyse(series)

    client = LLMClient(settings)
    try:
        brief, completion = write_brief(client, settings, args.question, facts)
    finally:
        client.close()

    print(f"\nRecommendation: {brief.recommendation}\n")
    print(f"Reasoning: {brief.reasoning}\n")
    for caveat in brief.caveats:
        print(f"- {caveat}")
    print(
        f"\n[{completion.input_tokens} in / {completion.output_tokens} out, "
        f"{completion.latency_ms} ms, cost {completion.cost_usd}]"
    )
    print("[source: FIXTURE, not real market data]")


if __name__ == "__main__":
    main()
