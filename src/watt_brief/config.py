"""Settings from the environment. Secrets are SecretStr so they never print by accident."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str
    llm_api_key: SecretStr
    model_planner: str
    model_analyst: str
    model_critic: str

    # Optional until the data client exists.
    entsoe_api_token: SecretStr | None = None

    # Used only when the provider does not report a cost itself. Never guessed.
    price_input_per_mtok_usd: float | None = None
    price_output_per_mtok_usd: float | None = None

    # Chosen by the evals, see docs/adr/003-planner-yes-critic-not-yet.md.
    use_planner: bool = True
    use_critic: bool = False

    llm_timeout_seconds: float = 60.0
    max_output_tokens: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
