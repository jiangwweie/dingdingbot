from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.readmodels import runtime_strategy_signal_input as signal_builder
from src.application.runtime_lane_identity_service import RuntimeLaneIdentityResolution
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeLaneEventEvaluationResult,
    RuntimeLaneEventEvaluationStatus,
    RuntimeStrategySignalEvaluationStatus,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from src.interfaces import api as api_module
from src.interfaces import api_trading_console as trading_api


def _identity(*, timeframe: str = "15m") -> RuntimeLaneIdentity:
    return RuntimeLaneIdentity(
        candidate_scope_id="scope:SOR-001:ETHUSDT:long",
        candidate_scope_event_binding_id="binding:SOR-001:ETHUSDT:long:SOR-LONG",
        runtime_scope_binding_id="runtime_scope:SOR-001:ETHUSDT:long",
        runtime_instance_id="runtime-sor-eth-long",
        runtime_profile_id="runtime-profile:pilot",
        policy_current_id="policy:SOR-001:ETHUSDT:long",
        strategy_group_id="SOR-001",
        strategy_group_version_id="sgv:SOR-001:v2",
        symbol="ETHUSDT",
        asset_class="crypto_perpetual",
        side="long",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        event_spec_version="v2",
        event_id="SOR-LONG",
        timeframe=timeframe,
        time_authority="trigger_candle_close_time_ms",
    )


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_instance_id="runtime-sor-eth-long",
        trial_binding_id="trial:sor:eth:long",
        strategy_family_id="SOR-001",
        strategy_family_version_id="SOR-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        status=SimpleNamespace(value="active"),
        execution_enabled=False,
        shadow_mode=True,
        carrier_id=None,
        boundary=SimpleNamespace(
            attempts_used=0,
            budget_reserved=0,
            max_notional_per_attempt=None,
            total_budget=None,
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=None,
            max_attempts=1,
            max_active_positions=1,
            requires_protection=True,
            requires_review=True,
            attempts_remaining=1,
            budget_remaining=None,
        ),
        policy_snapshot=SimpleNamespace(playbook_id=None),
        review_requirement=SimpleNamespace(value="required"),
    )


class _RuntimeService:
    async def get_runtime(self, runtime_instance_id: str):
        assert runtime_instance_id == "runtime-sor-eth-long"
        return _runtime()


class _OwnerFlowService:
    async def owner_action_flow(self, **_kwargs):
        return SimpleNamespace(
            data={
                "owner_action_flow": {
                    "next_attempt_gate": {
                        "status": "clear_for_preflight",
                        "next_attempt_allowed_by_lifecycle": True,
                        "blockers": [],
                        "warnings": [],
                    },
                    "just_in_time_lifecycle_audit": {"can_execute_live": False},
                },
                "post_action_state": {},
            }
        )


class _Candle:
    def __init__(self, close_time_ms: int) -> None:
        self.open_time_ms = close_time_ms - 900_000
        self.close_time_ms = close_time_ms
        self.open = "100"
        self.high = "101"
        self.low = "99"
        self.close = "100"
        self.volume = "10"


class _MarketSource:
    source_id = "unit_read_only"
    source_type = "unit_read_only_market"

    def __init__(self) -> None:
        self.timeframes: list[str] = []

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int):
        assert symbol == "ETH/USDT:USDT"
        assert limit > 0
        self.timeframes.append(timeframe)
        return [_Candle(1_780_000_000_000 + index * 900_000) for index in range(8)]


class _EventScopedEvaluator:
    def evaluate_for_runtime_lane(self, signal_input, *, lane_identity, freshness_window_ms):
        assert signal_input.primary_timeframe == "15m"
        assert lane_identity == _identity()
        assert freshness_window_ms == 900_000
        return RuntimeLaneEventEvaluationResult(
            lane_identity=lane_identity,
            status=RuntimeLaneEventEvaluationStatus.COMPUTED_NOT_SATISFIED,
            signal=None,
            blockers=[],
            reason_codes=["computed_not_satisfied", "event_side_not_satisfied"],
            raw_evaluation_status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
            evaluator_id="GenericEvaluator",
            can_materialize_live_signal_event=False,
        )


@pytest.mark.asyncio
async def test_observation_api_uses_lane_timeframe_and_projects_opposite_pattern_as_waiting(
    monkeypatch,
) -> None:
    source = _MarketSource()

    async def resolve_lane(*, runtime):
        assert runtime.runtime_instance_id == "runtime-sor-eth-long"
        return RuntimeLaneIdentityResolution(
            identity=_identity(),
            evaluator_version_id="SOR-001-v0",
            freshness_window_ms=900_000,
        )

    async def no_comparative_snapshot(**_kwargs):
        return None

    monkeypatch.setattr(api_module, "_strategy_runtime_service", _RuntimeService(), raising=False)
    monkeypatch.setattr(trading_api, "_service", lambda **_kwargs: _OwnerFlowService())
    monkeypatch.setattr(trading_api, "_resolve_runtime_lane_resolution", resolve_lane)
    monkeypatch.setattr(
        signal_builder,
        "market_source",
        lambda _args: source,
    )
    monkeypatch.setattr(
        signal_builder,
        "load_runtime_comparative_strength_snapshot",
        no_comparative_snapshot,
    )
    monkeypatch.setattr(
        __import__("src.application.runtime_strategy_signal_evaluation_service", fromlist=["x"]),
        "RuntimeStrategySignalEvaluationService",
        _EventScopedEvaluator,
    )

    payload = await trading_api._runtime_next_attempt_observation_cycle_payload(
        runtime_instance_id="runtime-sor-eth-long",
        request=trading_api.RuntimeNextAttemptObservationCycleRequest(
            include_exchange=False,
        ),
    )

    assert source.timeframes == ["15m", "4h"]
    assert payload["status"] == "waiting_for_opportunity"
    assert payload["blockers"] == []
    assert payload["signal_artifact"]["lane_identity"] == _identity().model_dump()
    assert payload["signal_artifact"]["can_materialize_live_signal_event"] is False
    assert payload["signal_artifact"]["evaluation_result"]["signal"] is None
    assert "short" not in str(payload["signal_artifact"])
