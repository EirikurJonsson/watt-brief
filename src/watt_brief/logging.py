"""Structured JSON logs with request IDs. Secrets are redacted before they are written.

User text goes in as a field, never interpolated into the message.
"""

import contextvars
import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(securityToken=)[^&\s\"']+"),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    return rid


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        entry.update(getattr(record, "fields", {}))
        return redact(json.dumps(entry, default=str))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # httpx logs full request URLs, which can carry tokens.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(event, extra={"fields": fields})
