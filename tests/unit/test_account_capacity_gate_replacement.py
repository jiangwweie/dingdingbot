from __future__ import annotations

from decimal import Decimal

from src.application.action_time import promotion_action_time_lane as subject
from src.domain.account_risk import AccountRiskPolicy
from src.infrastructure.binance_usdm_account_risk_snapshot import FullAccountRiskSnapshot


def test_active_account_capacity_replaces_only_legacy_flat_position_blockers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(subject, "load_account_risk_policy_current", lambda *_args, **_kwargs: _policy())

    bundle, blocker = subject._prepare_active_capacity_bundle(
        object(), bundle=_bundle(base_safe=True), snapshot=_snapshot()
    )

    assert blocker is None
    assert bundle.blockers == ("public_fact_not_satisfied",)


def test_active_account_capacity_requires_non_position_account_safety(
    monkeypatch,
) -> None:
    monkeypatch.setattr(subject, "load_account_risk_policy_current", lambda *_args, **_kwargs: _policy())

    _bundle_after, blocker = subject._prepare_active_capacity_bundle(
        object(), bundle=_bundle(base_safe=False), snapshot=_snapshot()
    )

    assert blocker == "account_capacity_base_fact_not_safe"


def _bundle(*, base_safe: bool) -> subject.CandidateBundle:
    return subject.CandidateBundle(
        candidate={"strategy_group_id": "SOR-001", "symbol": "SOLUSDT", "side": "long"},
        runtime_scope={"runtime_profile_id": "profile-1"},
        policy={}, event_binding={}, event_spec={}, signal={}, readiness={},
        public_fact={}, action_time_fact={},
        account_safe_fact={"fact_values": {"account_capacity_base_safe": base_safe}},
        account_mode_fact={}, coverage={}, owner_policy_version="owner-policy-1",
        account_id="account-1",
        blockers=(
            "account_safe_fact_not_satisfied",
            "account_safe_fact_not_fresh",
            "account_safe_fact_not_true",
            "open_orders_not_clear",
            "active_position_or_open_order_conflict",
            "public_fact_not_satisfied",
        ),
    )


def _policy() -> AccountRiskPolicy:
    return AccountRiskPolicy(
        risk_policy_version="account-policy-1",
        planned_stop_risk_fraction=Decimal("0.025"),
        max_concurrent_positions=2,
        max_portfolio_open_risk_fraction=Decimal("0.06"),
        max_cluster_open_risk_fraction=Decimal("0.04"),
        max_portfolio_initial_margin_fraction=Decimal("0.90"),
        max_leverage=10,
        max_new_action_time_lanes=1,
        automatic_downsize_enabled=True,
        unknown_exposure_policy="global_fail_closed",
        activation_state="active",
    )


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
        observed_at_ms=1_752_480_000_000,
        valid_until_ms=1_752_480_060_000,
    )
