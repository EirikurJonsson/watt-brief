"""Settings from the environment. Secrets are SecretStr so they never print by accident."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
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

    # Per attempt. Transient failures are retried within the total budget below.
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_budget_seconds: float = 40.0
    max_output_tokens: int = 1000

    # Where to listen. Localhost by default; the container sets 0.0.0.0 and is only ever
    # reachable through the Docker network that cloudflared shares.
    serve_host: str = "127.0.0.1"
    serve_port: int = 8000

    # Service. "fixture" serves synthetic data and says so in every response.
    facts_source: Literal["fixture", "entsoe"] = "fixture"

    # Abuse controls.
    daily_spend_cap_usd: float = 1.0
    # Counted per call when the provider reports no cost, so the cap is never blind.
    fallback_cost_per_call_usd: float = 0.001
    spend_db_path: str = "data/spend.sqlite"
    history_db_path: str = "data/history.sqlite"
    kill_switch_file: str = "KILL_SWITCH"
    rate_limit_per_minute: int = 6
    rate_limit_per_day: int = 100
    max_concurrent_requests: int = 4
    # Only enable behind Cloudflare Tunnel with no open ports: the header is spoofable otherwise.
    trust_cf_connecting_ip: bool = False

    # /metrics is disabled (404) unless this is set.
    metrics_token: SecretStr | None = None
    alert_webhook_url: str | None = None
    # "ntfy" sends plain text with Title/Priority/Tags headers, as ntfy expects.
    alert_webhook_format: Literal["json", "ntfy"] = "json"

    @field_validator("entsoe_api_token", "metrics_token", "alert_webhook_url", mode="before")
    @classmethod
    def _blank_means_unset(cls, value):
        """A blank line in .env must mean "not set". An empty metrics token would otherwise
        match a request that sends no credentials at all."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
