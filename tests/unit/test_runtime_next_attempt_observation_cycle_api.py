from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from scripts import build_runtime_strategy_signal_input_artifact
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.interfaces import api_trading_console


NOW_MS = 1781000000000


def _candle(index: int, open_: str, high: str, low: str, close: str) -> SimpleNamespace:
    return SimpleNamespace(
        open_time_ms=NOW_MS - (30 - index) * 3_600_000,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def _btpc_1h() -> list[SimpleNamespace]:
    return [
        _candle(0, "110", "111", "108", "109"),
        _candle(1, "109", "110", "107", "108"),
        _candle(2, "108", "109", "106", "107"),
        _candle(3, "107", "108", "105", "106"),
        _candle(4, "106", "107", "104", "105"),
        _candle(5, "105", "106", "103", "104"),
        _candle(6, "104", "105", "102", "103"),
        _candle(7, "103", "104", "101", "102"),
        _candle(8, "102", "104", "100", "103"),
        _candle(9, "103", "105", "101", "104"),
        _candle(10, "104", "106", "102", "105"),
        _candle(11, "105", "106", "100", "101"),
        _candle(12, "101", "102", "99", "100"),
        _candle(13, "100", "101", "95", "96"),
    ]


def _down_context_4h() -> list[SimpleNamespace]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _runtime(
    *,
    family_id: str = "BTPC-001",
    version_id: str = "BTPC-001-v0",
    side: str = "short",
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-api-1",
        trial_binding_id="trial-api-1",
        admission_decision_id="admission-api-1",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        carrier_id=f"{family_id}-runtime",
        symbol="AVAX/USDT:USDT",
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=Decimal("0.10"),
            total_budget=Decimal("6"),
            max_notional_per_attempt=Decimal("8"),
            max_active_positions=1,
            allowed_symbols=["AVAX/USDT:USDT"],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _clear_flow_response() -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "post_action_state": {
                "next_attempt_gate": {
                    "status": "clear_for_preflight",
                    "gate": "clear_for_next_preflight",
                    "next_attempt_allowed_by_lifecycle": True,
                    "blockers": [],
                    "warnings": [],
                }
            },
            "owner_action_flow": {
                "just_in_time_lifecycle_audit": {
                    "can_continue_to_authorization": True,
                    "can_execute_live": False,
                }
            },
        }
    )


def _blocked_flow_response() -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "post_action_state": {
                "next_attempt_gate": {
                    "status": "blocked",
                    "gate": "closed_trade_review_required",
                    "next_attempt_allowed_by_lifecycle": False,
                    "blockers": [{"id": "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED"}],
                    "required_next_step": "record_closed_trade_review",
                }
            },
            "owner_action_flow": {
                "just_in_time_lifecycle_audit": {
                    "can_continue_to_authorization": False,
                    "can_execute_live": False,
                }
            },
        }
    )


class _RuntimeService:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        assert runtime_instance_id == self.runtime.runtime_instance_id
        return self.runtime


class _OwnerFlowService:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def owner_action_flow(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _Source:
    source_id = "unit_market_source"
    source_type = "unit_read_only"

    def latest_closed_candles(self, *, symbol, timeframe, limit):
        return _down_context_4h() if timeframe == "4h" else _btpc_1h()


def _patch_runtime_and_owner_flow(monkeypatch, *, runtime, owner_flow_service):
    async def runtime_service():
        return _RuntimeService(runtime)

    monkeypatch.setattr(
        api_trading_console,
        "_strategy_runtime_service",
        runtime_service,
    )
    monkeypatch.setattr(
        api_trading_console,
        "_service",
        lambda *, include_exchange=False: owner_flow_service,
    )


@pytest.mark.asyncio
async def test_next_attempt_observation_api_blocks_before_signal_when_gate_blocks(
    monkeypatch,
):
    runtime = _runtime()
    owner_flow_service = _OwnerFlowService(_blocked_flow_response())
    _patch_runtime_and_owner_flow(
        monkeypatch,
        runtime=runtime,
        owner_flow_service=owner_flow_service,
    )
    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_market_source",
        lambda args: pytest.fail("signal market source must not run when gate blocks"),
    )

    payload = await api_trading_console._runtime_next_attempt_observation_cycle_payload(
        runtime_instance_id=runtime.runtime_instance_id,
        request=api_trading_console.RuntimeNextAttemptObservationCycleRequest(
            source="sample",
        ),
    )

    assert payload["status"] == "blocked"
    assert payload["blocked_stage"] == "next_attempt_gate"
    assert "operator_command_plan" not in payload
    assert payload["observation_cycle_plan"]["creates_execution_intent"] is False
    assert payload["safety_invariants"]["exchange_write_called"] is False


@pytest.mark.asyncio
async def test_next_attempt_observation_api_waits_for_observe_only_signal(monkeypatch):
    runtime = _runtime(family_id="RMR-001", version_id="RMR-001-v0", side="long")
    owner_flow_service = _OwnerFlowService(_clear_flow_response())
    _patch_runtime_and_owner_flow(
        monkeypatch,
        runtime=runtime,
        owner_flow_service=owner_flow_service,
    )
    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_market_source",
        lambda args: _Source(),
    )

    payload = await api_trading_console._runtime_next_attempt_observation_cycle_payload(
        runtime_instance_id=runtime.runtime_instance_id,
        request=api_trading_console.RuntimeNextAttemptObservationCycleRequest(
            source="sample",
        ),
    )

    assert payload["status"] == "waiting_for_signal"
    assert payload["blocked_stage"] == "strategy_signal"
    assert payload["signal_artifact"]["status"] == "observe_only"
    assert "operator_command_plan" not in payload
    assert payload["observation_cycle_plan"]["next_step"] == (
        "observe_only_or_wait_for_next_closed_bar"
    )
    assert payload["observation_cycle_plan"]["creates_shadow_candidate"] is False
    assert payload["safety_invariants"]["execution_intent_created"] is False


@pytest.mark.asyncio
async def test_next_attempt_observation_api_waits_without_entry_signal(
    monkeypatch,
):
    runtime = _runtime()
    owner_flow_service = _OwnerFlowService(_clear_flow_response())
    _patch_runtime_and_owner_flow(
        monkeypatch,
        runtime=runtime,
        owner_flow_service=owner_flow_service,
    )
    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_market_source",
        lambda args: _Source(),
    )

    payload = await api_trading_console._runtime_next_attempt_observation_cycle_payload(
        runtime_instance_id=runtime.runtime_instance_id,
        request=api_trading_console.RuntimeNextAttemptObservationCycleRequest(
            source="sample",
        ),
    )

    assert payload["status"] == "waiting_for_signal"
    assert payload["signal_artifact"]["status"] == "observe_only"
    assert "operator_command_plan" not in payload
    assert payload["observation_cycle_plan"]["next_step"] == (
        "observe_only_or_wait_for_next_closed_bar"
    )
    assert payload["observation_cycle_plan"]["creates_shadow_candidate"] is False
    assert payload["observation_cycle_plan"]["creates_execution_intent"] is False
    assert payload["safety_invariants"]["order_created"] is False
    assert payload["safety_invariants"]["order_lifecycle_called"] is False


@pytest.mark.asyncio
async def test_next_attempt_observation_api_rejects_prepare_records_flag():
    with pytest.raises(HTTPException) as exc:
        await api_trading_console.runtime_next_attempt_observation_cycle(
            "runtime-api-1",
            api_trading_console.RuntimeNextAttemptObservationCycleRequest(
                allow_prepare_records=True,
            ),
        )

    assert exc.value.status_code == 400
    assert "non-executing" in exc.value.detail
