import pytest
from pydantic import ValidationError

from watt_brief.config import Settings


def test_missing_required_settings_fail_loudly(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "MODEL_PLANNER", "MODEL_ANALYST", "MODEL_CRITIC"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_does_not_print():
    s = Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-supersecret",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
    )
    assert "sk-supersecret" not in repr(s)
    assert "sk-supersecret" not in str(s)
