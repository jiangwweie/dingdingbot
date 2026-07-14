from __future__ import annotations

from decimal import Decimal

from src.application.action_time import account_risk_reprojection as subject
from src.application.action_time import post_submit_reconciliation_tick as tick_subject
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


NOW_MS = 1_752_480_000_000


def test_lifecycle_reprojection_projects_exposure_then_budget(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(subject, "load_account_risk_policy_current", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(subject, "classify_account_exchange_truth", lambda *_args, **_kwargs: calls.append("classify") or type("C", (), {"blockers": ()})())
    monkeypatch.setattr(subject, "project_account_exposure_current", lambda *_args, **_kwargs: calls.append("exposure") or type("E", (), {"global_blockers": (), "semantic_event_count": 1})())
    monkeypatch.setattr(subject, "project_account_budget_current", lambda *_args, **_kwargs: calls.append("budget") or type("B", (), {"projection_version": 7, "first_blocker": None})())

    result = subject.reproject_account_risk_current(
        object(), snapshot=_snapshot(), runtime_profile_id="profile-1", now_ms=NOW_MS
    )

    assert result.status == "reprojected"
    assert result.projection_version == 7
    assert result.semantic_event_count == 1
    assert calls == ["classify", "exposure", "budget"]


def test_unknown_snapshot_blocks_reprojection_without_creating_capacity() -> None:
    result = subject.reproject_account_risk_current(
        object(),
        snapshot=_snapshot().model_copy(update={"snapshot_ready": False, "failure_code": "account_risk_snapshot_fetch_failed"}),
        runtime_profile_id="profile-1",
        now_ms=NOW_MS,
    )

    assert result.status == "blocked"
    assert result.first_blocker == "account_risk_snapshot_fetch_failed"


def test_only_lifecycle_semantic_change_triggers_account_reprojection() -> None:
    existing = {
        "status": "matched", "entry_state": "filled", "sl_state": "open",
        "tp1_state": "open", "position_state": "open", "first_blocker": None,
        "blockers": [],
    }
    assert tick_subject._tick_semantics_changed(existing, dict(existing)) is False
    assert tick_subject._tick_semantics_changed(
        existing, {**existing, "tp1_state": "filled"}
    ) is True
    assert tick_subject._tick_semantics_changed(
        existing, {**existing, "position_state": "flat"}
    ) is True


def _snapshot() -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id="snapshot-1",
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 60_000,
    )
