from __future__ import annotations

from decimal import Decimal

from src.application.action_time import account_capacity_materialization as subject
from src.application.action_time.account_capacity_reservation import (
    AccountCapacityCandidate,
    AccountCapacityReservationResult,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


def test_snapshot_is_classified_projected_and_claimed_in_order(monkeypatch) -> None:
    calls: list[str] = []
    snapshot = _snapshot()
    candidate = _candidate()
    monkeypatch.setattr(subject, "lock_account_budget_current", lambda _conn, **_kwargs: calls.append("lock") or True, raising=False)
    monkeypatch.setattr(subject, "classify_account_exchange_truth", lambda _conn, *, snapshot: calls.append("classify") or type("C", (), {"blockers": ()})())
    monkeypatch.setattr(subject, "load_account_risk_policy_current", lambda _conn, **_kwargs: calls.append("policy") or object())
    monkeypatch.setattr(subject, "project_account_exposure_current", lambda _conn, **_kwargs: calls.append("exposure") or type("E", (), {"global_blockers": ()})())
    monkeypatch.setattr(subject, "project_account_budget_current", lambda _conn, **_kwargs: calls.append("budget") or type("B", (), {"projection_version": 7})())
    expected = AccountCapacityReservationResult(allowed=True, allocated_risk=Decimal("9"))
    monkeypatch.setattr(subject, "reserve_account_capacity_for_candidate", lambda _conn, **kwargs: calls.append(f"reserve:{kwargs['expected_projection_version']}") or expected)

    result = subject.materialize_account_capacity_from_snapshot(
        object(), snapshot=snapshot, runtime_profile_id="profile-1", candidate=candidate, now_ms=1_752_480_000_000
    )

    assert result == expected
    assert calls == ["classify", "lock", "policy", "exposure", "budget", "reserve:7"]


def test_exchange_classification_blocker_prevents_budget_and_claim(monkeypatch) -> None:
    monkeypatch.setattr(subject, "classify_account_exchange_truth", lambda _conn, *, snapshot: type("C", (), {"blockers": ("account_exchange_order_unknown_global_fail_closed",)})())
    result = subject.materialize_account_capacity_from_snapshot(object(), snapshot=_snapshot(), runtime_profile_id="profile-1", candidate=_candidate(), now_ms=1_752_480_000_000)
    assert result.allowed is False
    assert result.first_blocker == "account_exchange_order_unknown_global_fail_closed"


def test_snapshot_without_trade_permission_is_blocked_before_classification(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "classify_account_exchange_truth",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not classify")),
    )
    result = subject.materialize_account_capacity_from_snapshot(
        object(),
        snapshot=_snapshot().model_copy(update={"can_trade": False}),
        runtime_profile_id="profile-1",
        candidate=_candidate(),
        now_ms=1_752_480_000_000,
    )
    assert result.allowed is False
    assert result.first_blocker == "account_trade_permission_not_true"


def _snapshot() -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(snapshot_ready=True, account_id="account-1", exchange_id="binance_usdm", total_wallet_balance=Decimal("600"), available_balance=Decimal("500"), exchange_total_initial_margin=Decimal("100"), can_trade=True, position_mode="one_way", source_snapshot_id="snapshot-1", observed_at_ms=1_752_480_000_000, valid_until_ms=1_752_480_060_000)


def _candidate() -> AccountCapacityCandidate:
    return AccountCapacityCandidate(account_id="account-1", runtime_profile_id="profile-1", exchange_instrument_id="binance_usdm:SOLUSDT", risk_cluster_id="crypto_usd_beta", per_unit_stop_risk=Decimal("3"), entry_reference_price=Decimal("150"), min_qty=Decimal(".01"), qty_step=Decimal(".01"), min_notional=Decimal("5"), exchange_max_leverage=20)
