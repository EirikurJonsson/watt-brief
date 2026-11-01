import httpx

from watt_brief.alerts import Alert, AlertManager, evaluate, webhook_request

OK = ["ok"] * 30


def names(alerts):
    return {a.name for a in alerts}


def test_quiet_when_all_is_well():
    assert evaluate(0.1, 1.0, OK, False, 0) == []


def test_spend_warning_then_critical():
    assert names(evaluate(0.8, 1.0, OK, False, 0)) == {"spend_high"}
    assert names(evaluate(1.0, 1.0, OK, False, 0)) == {"spend_cap"}


def test_kill_switch_and_bans():
    assert names(evaluate(0, 1.0, OK, True, 2)) == {"kill_switch", "bans_active"}


def test_error_spike_needs_enough_requests():
    assert evaluate(0, 1.0, ["error"] * 5, False, 0) == []
    assert names(evaluate(0, 1.0, ["error"] * 10 + ["ok"] * 20, False, 0)) == {"error_spike"}


def test_abuse_pattern_counts_rejections_and_rate_limits():
    mixed = ["rejected"] * 12 + ["rate_limited"] * 8 + ["ok"] * 10
    assert names(evaluate(0, 1.0, mixed, False, 0)) == {"abuse_pattern"}


def test_manager_notifies_once_per_cooldown():
    clock = {"t": 0.0}
    sent: list[str] = []
    manager = AlertManager(
        webhook_url="https://hook.example/x",
        clock=lambda: clock["t"],
        post=lambda url, alert, fmt: sent.append(alert.message),
    )
    assert len(manager.check(0.9, 1.0, False, 0)) == 1
    assert manager.check(0.9, 1.0, False, 0) == []
    clock["t"] += 1801
    assert len(manager.check(0.9, 1.0, False, 0)) == 1
    assert len(sent) == 2 and "90%" in sent[0]


def test_manager_without_webhook_only_logs():
    manager = AlertManager(post=lambda *_: (_ for _ in ()).throw(AssertionError("no post")))
    assert len(manager.check(1.0, 1.0, False, 0)) == 1


def test_critical_alerts_log_at_error_and_warnings_at_warning(caplog):
    import logging

    manager = AlertManager()
    with caplog.at_level(logging.INFO):
        manager.check(0.9, 1.0, False, 0)  # warning
        manager.check(1.0, 1.0, False, 0)  # critical
    levels = {r.levelname for r in caplog.records if r.message == "alert"}
    assert levels == {"WARNING", "ERROR"}


CRITICAL = Alert("spend_cap", "critical", "Daily spend cap reached: $1.0000.")
WARNING = Alert("spend_high", "warning", "Daily spend at 80% of the cap.")


def test_json_format_keeps_the_text_body():
    request = webhook_request(WARNING, "json")
    assert request == {"json": {"text": "[watt-brief warning] Daily spend at 80% of the cap."}}


def test_ntfy_format_is_plain_text_with_priority_by_severity():
    critical = webhook_request(CRITICAL, "ntfy")
    warning = webhook_request(WARNING, "ntfy")
    assert critical["content"] == CRITICAL.message.encode()
    assert critical["headers"] == {
        "Title": "watt-brief: spend_cap",
        "Priority": "high",
        "Tags": "rotating_light",
    }
    assert warning["headers"]["Priority"] == "default"
    assert warning["headers"]["Tags"] == "warning"


def test_ntfy_request_goes_out_as_text_and_a_failing_server_does_not_raise(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(500)

    real_post = httpx.post
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    )
    AlertManager._post_webhook("https://ntfy.example/topic", CRITICAL, "ntfy")
    monkeypatch.setattr(httpx, "post", real_post)
    (req,) = seen
    assert req.content == CRITICAL.message.encode()
    assert req.headers["priority"] == "high"
    assert req.headers["title"] == "watt-brief: spend_cap"


def test_a_network_failure_in_the_notifier_is_swallowed(monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    AlertManager._post_webhook("https://ntfy.example/secret-topic", CRITICAL, "ntfy")
