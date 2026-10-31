from watt_brief.alerts import AlertManager, evaluate

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
        post=lambda url, text: sent.append(text),
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
