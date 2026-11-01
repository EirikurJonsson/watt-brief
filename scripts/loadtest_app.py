"""App factory for the load test: the real service with settings read from the environment."""

from watt_brief.api import create_app
from watt_brief.config import Settings
from watt_brief.logging import configure_logging


def make_app():
    configure_logging()
    # _env_file=None: the test's settings come only from the environment it was started with,
    # never from a developer's real .env
    return create_app(Settings(_env_file=None))
