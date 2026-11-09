import pytest

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    _overview_freshness,
)


def classify(*, age=0, status="running", extra=(), ledger_age=86400000, contradictory=False):
    now = 1_800_000_000_000
    return _overview_freshness(
        authority={"venue_id": "binance-usdm", "account_id": "manual-account", "exposure_updated_at_ms": now-ledger_age},
        monitor_rows=[{"monitor_key": "account:binance-usdm:position-audit", "owner_status": status, "updated_at_ms": now-age}, *extra],
        now_ms=now, contradictory=contradictory,
    )


@pytest.mark.parametrize("age,expected", [(0,"fresh"),(120000,"fresh"),(120001,"stale"),(300000,"stale"),(300001,"unavailable"),(-1,"contradictory")])
def test_stable_exposure_uses_account_audit_cadence(age, expected):
    freshness, identity, at = classify(age=age)
    assert freshness.value == expected
    assert identity == "account:binance-usdm:manual-account"
    assert at == 1_800_000_000_000-age


def test_fresh_notification_cannot_hide_old_or_failed_audit():
    notification={"monitor_key":"notification:feishu","updated_at_ms":1_800_000_000_000,"owner_status":"running"}
    assert classify(age=300001, extra=(notification,))[0].value == "unavailable"
    assert classify(status="temporarily_unavailable", extra=(notification,))[0].value == "unavailable"
    assert classify(contradictory=True)[0].value == "contradictory"


def test_missing_audit_is_unavailable_even_with_fresh_ledger_and_other_monitor():
    now=1_800_000_000_000
    result=_overview_freshness(authority={"venue_id":"binance-usdm","account_id":"manual-account","exposure_updated_at_ms":now},
        monitor_rows=[{"monitor_key":"account:binance-usdm:bnb-fee-capability","updated_at_ms":now,"owner_status":"running"}],now_ms=now,contradictory=False)
    assert result[0].value == "unavailable"
