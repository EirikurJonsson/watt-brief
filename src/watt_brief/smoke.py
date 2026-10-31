"""One live call to confirm the key and model work: python -m watt_brief.smoke"""

from watt_brief.config import get_settings
from watt_brief.llm import LLMClient
from watt_brief.logging import configure_logging, new_request_id


def main() -> None:
    configure_logging()
    new_request_id()
    settings = get_settings()
    client = LLMClient(settings)
    try:
        result = client.complete(
            step="smoke",
            model=settings.model_analyst,
            system="You are a terse assistant.",
            user="Reply with the single word: ready",
        )
    finally:
        client.close()
    print(f"reply: {result.text.strip()!r}")


if __name__ == "__main__":
    main()
