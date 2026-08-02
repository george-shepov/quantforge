from app.metering import MeteringStore


def test_api_key_is_returned_once_and_authenticates(tmp_path):
    store = MeteringStore(str(tmp_path / "metering.sqlite3"))

    created = store.create_key(
        name="SDK test",
        plan="developer",
        monthly_quota=100,
        rate_limit_per_minute=10,
    )

    assert created["apiKey"].startswith("qf_live_")
    principal = store.authenticate(str(created["apiKey"]))
    assert principal is not None
    assert principal.key_id == created["id"]
    assert principal.monthly_quota == 100
    assert store.authenticate("qf_live_invalid") is None


def test_usage_is_recorded_and_summarized(tmp_path):
    store = MeteringStore(str(tmp_path / "metering.sqlite3"))
    created = store.create_key(
        name="Usage test",
        plan="pro",
        monthly_quota=3,
        rate_limit_per_minute=2,
    )
    principal = store.authenticate(str(created["apiKey"]))
    assert principal is not None

    store.record_usage(
        principal=principal,
        method="POST",
        path="/api/backtests/run",
        status_code=200,
        latency_ms=12.5,
    )

    summary = store.usage_summary(principal)
    assert summary["used"] == 1
    assert summary["remaining"] == 2
    assert summary["monthlyQuota"] == 3
    assert store.usage_last_minute(principal.key_id) == 1
