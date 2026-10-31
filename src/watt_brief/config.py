"""Settings from the environment. Secrets are SecretStr so they never print by accident."""

from functools import lru_cache
from typing import Literal

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

    # Service. "fixture" serves synthetic data and says so in every response.
    facts_source: Literal["fixture", "entsoe"] = "fixture"

    # Abuse controls.
    daily_spend_cap_usd: float = 1.0
    # Counted per call when the provider reports no cost, so the cap is never blind.
    fallback_cost_per_call_usd: float = 0.001
    spend_db_path: str = "data/spend.sqlite"
    kill_switch_file: str = "KILL_SWITCH"
    rate_limit_per_minute: int = 6
    rate_limit_per_day: int = 100
    max_concurrent_requests: int = 4
    # Only enable behind Cloudflare Tunnel with no open ports: the header is spoofable otherwise.
    trust_cf_connecting_ip: bool = False

    # /metrics is disabled (404) unless this is set.
    metrics_token: SecretStr | None = None
    alert_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
