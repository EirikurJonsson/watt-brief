"""Errors a caller can show to a user. Messages never echo the user's input."""


class BriefError(Exception):
    """The brief could not be produced. The message is safe to show a user."""


class GuardRejected(BriefError):
    """A guard stopped the request. `reason` is a stable code for logs and metrics;
    `stage` is "input" or "output". `detail` is for logs and evals only, never shown to a
    user, and is set only when it cannot contain the user's text."""

    def __init__(self, reason: str, stage: str, message: str, detail: str = ""):
        super().__init__(message)
        self.reason = reason
        self.stage = stage
        self.detail = detail
