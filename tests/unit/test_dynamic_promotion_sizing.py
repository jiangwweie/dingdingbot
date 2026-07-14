from decimal import Decimal

from src.application.action_time.promotion_action_time_lane import (
    CandidateBundle,
    _sizing_risk_decision_result,
)


NOW_MS = 1_000_000


def test_promotion_sizing_uses_dynamic_account_policy_and_lowest_leverage() -> None:
    bundle = CandidateBundle(
        candidate={
            "strategy_group_id": "CPM-RO-001",
            "symbol": "TESTUSDT",
            "side": "long",
        },
        runtime_scope={},
        policy={
            "planned_stop_risk_fraction": Decimal("0.03"),
            "max_initial_margin_utilization": Decimal("0.90"),
            "max_leverage": 10,
        },
        event_binding={},
        event_spec={
            "event_spec_id": "event:1",
            "protection_ref_type": "protective_stop",
        },
        signal={},
        readiness={},
        public_fact={},
        action_time_fact={
            "fact_snapshot_id": "action-time-fact-1",
            "valid_until_ms": NOW_MS + 30_000,
            "fact_values": {
                "protective_stop": "99.5",
                "execution_pricing": {
                    "side": "long",
                    "entry_reference_price": "100",
                    "entry_reference_kind": "best_ask",
                    "mark_price": "100",
                    "bid_price": "99.99",
                    "ask_price": "100",
                    "min_qty": "0.001",
                    "qty_step": "0.001",
                    "min_notional": "5",
                    "source_fact_snapshot_id": "public-fact-1",
                    "observed_at_ms": NOW_MS - 1_000,
                    "valid_until_ms": NOW_MS + 30_000,
                },
            },
        },
        account_safe_fact={
            "fact_snapshot_id": "account-fact-1",
            "observed_at_ms": NOW_MS - 1_000,
            "valid_until_ms": NOW_MS + 30_000,
            "fact_values": {
                "total_wallet_balance": "100",
                "available_balance": "100",
                "exchange_max_leverage_by_symbol": {"TESTUSDT": 100},
            },
        },
        account_mode_fact={},
        coverage={},
        owner_policy_version="owner-risk-policy-v2",
        account_id="owner-subaccount-runtime-v0",
        blockers=(),
    )

    decision, blockers = _sizing_risk_decision_result(bundle, now_ms=NOW_MS)

    assert blockers == []
    assert decision is not None
    assert decision.intended_qty == Decimal("6")
    assert decision.selected_leverage == 7
    assert decision.planned_stop_risk == Decimal("3.0")


def test_promotion_sizing_blocks_without_exchange_leverage_bracket() -> None:
    bundle = CandidateBundle(
        candidate={
            "strategy_group_id": "CPM-RO-001",
            "symbol": "TESTUSDT",
            "side": "long",
        },
        runtime_scope={},
        policy={
            "planned_stop_risk_fraction": "0.03",
            "max_initial_margin_utilization": "0.90",
            "max_leverage": 10,
        },
        event_binding={},
        event_spec={"event_spec_id": "event:1", "protection_ref_type": "stop"},
        signal={},
        readiness={},
        public_fact={},
        action_time_fact={
            "fact_snapshot_id": "action-time-fact-1",
            "valid_until_ms": NOW_MS + 30_000,
            "fact_values": {
                "stop": "99.5",
                "execution_pricing": {
                    "side": "long",
                    "entry_reference_price": "100",
                    "entry_reference_kind": "best_ask",
                    "mark_price": "100",
                    "bid_price": "99.99",
                    "ask_price": "100",
                    "min_qty": "0.001",
                    "qty_step": "0.001",
                    "min_notional": "5",
                    "source_fact_snapshot_id": "public-fact-1",
                    "observed_at_ms": NOW_MS - 1_000,
                    "valid_until_ms": NOW_MS + 30_000,
                },
            },
        },
        account_safe_fact={
            "fact_snapshot_id": "account-fact-1",
            "observed_at_ms": NOW_MS - 1_000,
            "valid_until_ms": NOW_MS + 30_000,
            "fact_values": {
                "total_wallet_balance": "100",
                "available_balance": "100",
            },
        },
        account_mode_fact={},
        coverage={},
        owner_policy_version="owner-risk-policy-v2",
        account_id="owner-subaccount-runtime-v0",
        blockers=(),
    )

    decision, blockers = _sizing_risk_decision_result(bundle, now_ms=NOW_MS)

    assert decision is None
    assert blockers == ["exchange_leverage_bracket_missing_or_invalid"]
