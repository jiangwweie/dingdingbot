from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.action_time.full_chain_simulation_harness import (
    ACTIVE_EXIT_EVENT_SPECS,
    ExitPolicyCertificationCase,
    classify_tp1_execution_observation,
    run_ticket_exit_policy_certification,
)


@pytest.mark.parametrize(
    ("strategy_group_id", "event_spec_id", "side", "timeframe"),
    ACTIVE_EXIT_EVENT_SPECS,
)
def test_six_event_specs_share_the_ticket_bound_exit_policy_core(
    strategy_group_id,
    event_spec_id,
    side,
    timeframe,
):
    instrument = "ETHUSDT" if strategy_group_id != "MPG-001" else "SOLUSDT"
    entry = Decimal("100")
    stop = Decimal("95") if side == "long" else Decimal("105")

    result = run_ticket_exit_policy_certification(
        ExitPolicyCertificationCase(
            strategy_group_id=strategy_group_id,
            strategy_version=f"{strategy_group_id}-v0",
            event_spec_id=event_spec_id,
            event_spec_version=f"{event_spec_id}-v1",
            side=side,
            timeframe=timeframe,
            exchange_instrument_id=instrument,
            entry_avg_fill_price=entry,
            initial_stop_price=stop,
            entry_filled_qty=Decimal("2"),
            minimum_price_tick=Decimal("0.1"),
            entry_fee_quote=Decimal("0.08"),
            certified_exit_taker_fee_rate=Decimal("0.0005"),
            slippage_buffer_quote=Decimal("0.06"),
            requested_leverage=Decimal("10"),
            applied_leverage=Decimal("10"),
            exchange_readback_leverage=Decimal("10"),
        )
    )

    assert result["schema"] == "brc.ticket_exit_policy_certification.v1"
    assert result["policy_snapshot"]["strategy_group_id"] == strategy_group_id
    assert result["policy_snapshot"]["event_spec_id"] == event_spec_id
    assert result["policy_snapshot"]["side"] == side
    assert len(result["policy_snapshot"]["payload_hash"]) == 64
    assert len(result["execution_snapshot"]["payload_hash"]) == 64
    assert result["execution_snapshot"]["actual_r_per_unit"] == "5"
    assert result["tp1_order_contract"] == {
        "order_type": "LIMIT",
        "time_in_force": "GTC",
        "market_fallback_allowed": False,
        "reward_basis": "actual_entry_r",
    }
    assert result["tp1_states"]["unfilled"]["decision"] == "noop"
    assert result["tp1_states"]["partial"] == {
        "decision": "resize_existing_protection",
        "cumulative_filled_qty": "0.5",
        "remaining_position_qty": "1.5",
        "runner_qty": "1",
    }
    assert result["tp1_states"]["complete"]["decision"] == "move_runner_stop"
    assert result["tp1_states"]["complete"]["remaining_position_qty"] == "1"
    assert result["structural_evaluation"]["decision"] == "move_runner_stop"
    assert result["invalidation_evaluation"]["decision"] == "close_runner"
    assert result["time_stop_evaluation"]["decision"] == "close_runner"
    assert result["replacement_contract"]["place_new_before_cancel_prior"] is True
    assert result["replacement_contract"]["next_generation"] == 2
    assert result["terminal_reconciliation"]["remaining_position_qty"] == "0"
    assert result["terminal_reconciliation"]["settlement_state"] == "settled"
    assert result["leverage_truth"] == {
        "requested": "10",
        "applied": "10",
        "exchange_readback": "10",
        "status": "verified",
    }
    assert result["live_outcome_shape"]["evidence_kind"] == "rehearsal_only"
    assert result["authority_boundary"] == {
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_gateway": False,
        "calls_exchange_write": False,
        "grants_live_submit_authority": False,
        "requires_upstream_authorized_ticket": True,
        "uses_repo_json_or_md_authority": False,
    }


def test_short_certification_rounds_tp1_and_floor_in_the_safe_direction():
    result = run_ticket_exit_policy_certification(
        ExitPolicyCertificationCase(
            strategy_group_id="SOR-001",
            strategy_version="SOR-001-v0",
            event_spec_id="SOR-SHORT",
            event_spec_version="SOR-SHORT-v1",
            side="short",
            timeframe="15m",
            exchange_instrument_id="BTCUSDT",
            entry_avg_fill_price=Decimal("100.03"),
            initial_stop_price=Decimal("105.07"),
            entry_filled_qty=Decimal("1"),
            minimum_price_tick=Decimal("0.1"),
            entry_fee_quote=Decimal("0.04"),
            certified_exit_taker_fee_rate=Decimal("0.0005"),
            slippage_buffer_quote=Decimal("0.03"),
            requested_leverage=Decimal("10"),
            applied_leverage=Decimal("10"),
            exchange_readback_leverage=Decimal("10"),
        )
    )

    assert result["execution_snapshot"]["resolved_tp1_price"] == "94.9"
    assert Decimal(result["immediate_runner_floor"]) < Decimal("100.03")


@pytest.mark.parametrize(
    ("style", "exchange_status", "liquidity_role", "passive_supported", "expected"),
    [
        ("limit_gtc", "filled", "maker", True, "valid_maker_fill"),
        ("limit_gtc", "filled", "taker", True, "valid_taker_fill"),
        ("passive_limit_gtx", "rejected", None, True, "passive_rejected"),
        ("passive_limit_gtx", "filled", "taker", True, "contradictory_taker_fill"),
        ("passive_limit_gtx", "open", None, False, "venue_passive_limit_absent"),
    ],
)
def test_tp1_execution_observation_is_conservative_and_exact(
    style,
    exchange_status,
    liquidity_role,
    passive_supported,
    expected,
):
    result = classify_tp1_execution_observation(
        execution_style=style,
        exchange_status=exchange_status,
        liquidity_role=liquidity_role,
        fee_quote=Decimal("0.02") if exchange_status == "filled" else None,
        venue_passive_limit_supported=passive_supported,
    )

    assert result["status"] == expected
    assert result["market_fallback_allowed"] is False


def test_tp1_fill_without_fee_truth_and_leverage_readback_mismatch_fail_closed():
    assert classify_tp1_execution_observation(
        execution_style="limit_gtc",
        exchange_status="filled",
        liquidity_role="maker",
        fee_quote=None,
        venue_passive_limit_supported=True,
    )["status"] == "fill_fee_truth_missing"

    case = ExitPolicyCertificationCase(
        strategy_group_id="MI-001",
        strategy_version="MI-001-v0",
        event_spec_id="MI-LONG",
        event_spec_version="MI-LONG-v1",
        side="long",
        timeframe="1h",
        exchange_instrument_id="ETHUSDT",
        entry_avg_fill_price=Decimal("100"),
        initial_stop_price=Decimal("95"),
        entry_filled_qty=Decimal("1"),
        minimum_price_tick=Decimal("0.1"),
        entry_fee_quote=Decimal("0.04"),
        certified_exit_taker_fee_rate=Decimal("0.0005"),
        slippage_buffer_quote=Decimal("0.03"),
        requested_leverage=Decimal("10"),
        applied_leverage=Decimal("10"),
        exchange_readback_leverage=Decimal("2"),
    )

    with pytest.raises(ValueError, match="leverage_readback_mismatch"):
        run_ticket_exit_policy_certification(case)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("entry_filled_qty", Decimal("0"), "entry_filled_qty_invalid"),
        ("entry_fee_quote", Decimal("-0.01"), "entry_fee_quote_invalid"),
        ("minimum_price_tick", Decimal("0"), "minimum_price_tick_invalid"),
    ],
)
def test_missing_or_invalid_execution_truth_is_rejected(field, value, reason):
    values = dict(
        strategy_group_id="CPM-RO-001",
        strategy_version="CPM-RO-001-v0",
        event_spec_id="CPM-LONG",
        event_spec_version="CPM-LONG-v1",
        side="long",
        timeframe="1h",
        exchange_instrument_id="ETHUSDT",
        entry_avg_fill_price=Decimal("100"),
        initial_stop_price=Decimal("95"),
        entry_filled_qty=Decimal("1"),
        minimum_price_tick=Decimal("0.1"),
        entry_fee_quote=Decimal("0.04"),
        certified_exit_taker_fee_rate=Decimal("0.0005"),
        slippage_buffer_quote=Decimal("0.03"),
        requested_leverage=Decimal("10"),
        applied_leverage=Decimal("10"),
        exchange_readback_leverage=Decimal("10"),
    )
    values[field] = value

    with pytest.raises(ValueError, match=reason):
        run_ticket_exit_policy_certification(ExitPolicyCertificationCase(**values))
