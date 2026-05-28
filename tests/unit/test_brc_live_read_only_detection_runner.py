from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.brc_live_read_only_detection_runner import (
    BrcLiveReadOnlyDetectionRunner,
    ExchangeGatewayReadOnlySnapshotProvider,
    LiveReadOnlyRunnerConfig,
    LiveReadOnlyRunnerError,
)
from src.application.execution_permission import ExecutionPermission


class _SnapshotProvider:
    def __init__(self, account_facts: dict | None = None, market_snapshot: dict | None = None):
        self.account_facts = account_facts or {
            "source": "exchange_live",
            "truth_level": "exchange_read",
            "freshness": "fresh",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        }
        self.market_snapshot = market_snapshot or {"symbol": "ETH/USDT:USDT", "mark_price": "3000"}

    async def read_account_facts(self) -> dict:
        return dict(self.account_facts)

    async def read_market_snapshot(self, *, symbol: str) -> dict:
        return {**self.market_snapshot, "symbol": symbol}


class _OperationService:
    def __init__(
        self,
        *,
        intent_decision: str = "allow",
        intent_final_permission: str = "intent_recording",
        unsafe_result: bool = False,
    ):
        self.intent_decision = intent_decision
        self.intent_final_permission = intent_final_permission
        self.unsafe_result = unsafe_result
        self.preflight_calls: list[dict] = []
        self.confirm_calls: list[dict] = []

    async def preflight(self, *, operation_type: str, requested_by: str, input_params: dict, source=None):
        self.preflight_calls.append(
            {
                "operation_type": operation_type,
                "requested_by": requested_by,
                "input_params": dict(input_params),
                "source": dict(source or {}),
            }
        )
        if operation_type == "evaluate_signal_from_admission_strategy":
            return SimpleNamespace(
                operation_id="op-signal",
                preflight_id="pf-signal",
                operation_type=operation_type,
                decision="allow",
                idempotency_key="idem-signal",
                after={"signal_evaluation_would_be_recorded": True},
                result_summary={},
            )
        return SimpleNamespace(
            operation_id="op-intent",
            preflight_id="pf-intent",
            operation_type=operation_type,
            decision=self.intent_decision,
            idempotency_key="idem-intent",
            after={
                "execution_permission_resolution": {
                    "final_permission": self.intent_final_permission,
                    "requested_permission": "intent_recording",
                }
            },
            result_summary={},
        )

    async def confirm(
        self,
        *,
        operation_id: str,
        preflight_id: str,
        confirmation_phrase: str,
        idempotency_key: str,
        confirmed_by=None,
    ):
        self.confirm_calls.append(
            {
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "confirmation_phrase": confirmation_phrase,
                "idempotency_key": idempotency_key,
                "confirmed_by": confirmed_by,
            }
        )
        if operation_id == "op-signal":
            return SimpleNamespace(
                status="executed",
                result_summary={
                    "signal_evaluated": True,
                    "signal_generated": True,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "auto_execution_enabled": False,
                },
            )
        return SimpleNamespace(
            status="executed",
            result_summary={
                "trial_trade_intent_created": True,
                "not_executed_reason": "observe_only",
                "execution_intent_created": self.unsafe_result,
                "order_created": False,
                "orders_placed": False,
                "auto_execution_enabled": False,
            },
        )


class _Gateway:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch_account_balance(self):
        self.calls.append("fetch_account_balance")
        return SimpleNamespace(
            total_balance="1000",
            available_balance="1000",
            unrealized_pnl="0",
            positions=[],
            timestamp=1770000000000,
        )

    async def fetch_positions(self, symbol=None):
        self.calls.append(f"fetch_positions:{symbol}")
        return []

    async def fetch_open_orders(self, symbol):
        self.calls.append(f"fetch_open_orders:{symbol}")
        return []

    async def fetch_ticker_price(self, symbol):
        self.calls.append(f"fetch_ticker_price:{symbol}")
        return "3000"

    async def create_order(self, *_args, **_kwargs):
        raise AssertionError("read-only snapshot provider must not create orders")

    async def cancel_order(self, *_args, **_kwargs):
        raise AssertionError("read-only snapshot provider must not cancel orders")


def _config(permission=ExecutionPermission.INTENT_RECORDING) -> LiveReadOnlyRunnerConfig:
    return LiveReadOnlyRunnerConfig(
        trading_env="live",
        brc_execution_permission_max=permission,
        campaign_id="brc-live-readonly",
        binding_id="bind-live-readonly",
        symbols=("ETH/USDT:USDT",),
        interval_seconds=0,
        max_iterations=1,
    )


def _runner(
    operation_service: _OperationService,
    snapshot_provider: _SnapshotProvider | None = None,
    *,
    audit_writable=True,
    runtime_safety: dict | None = None,
    recorder=None,
):
    async def _audit_writable():
        return audit_writable

    async def _runtime_safety():
        return dict(runtime_safety or {"current_runtime_state": "observe"})

    async def _sleep(_seconds: float):
        return None

    return BrcLiveReadOnlyDetectionRunner(
        operation_service=operation_service,
        snapshot_provider=snapshot_provider or _SnapshotProvider(),
        audit_writable=_audit_writable,
        runtime_safety_reader=_runtime_safety,
        iteration_recorder=recorder,
        sleep=_sleep,
        now_ms=lambda: 1770000000000,
    )


@pytest.mark.parametrize(
    "permission",
    [ExecutionPermission.ORDER_ALLOWED, ExecutionPermission.EXECUTION_INTENT_ALLOWED],
)
@pytest.mark.asyncio
async def test_live_read_only_runner_refuses_permissions_above_intent_recording(permission):
    runner = _runner(_OperationService())

    with pytest.raises(LiveReadOnlyRunnerError, match="BRC_EXECUTION_PERMISSION_MAX=intent_recording"):
        await runner.run_once(_config(permission))


@pytest.mark.parametrize(
    "permission",
    [ExecutionPermission.READ_ONLY, ExecutionPermission.SIGNAL_ONLY],
)
@pytest.mark.asyncio
async def test_live_read_only_runner_refuses_permissions_below_intent_recording(permission):
    runner = _runner(_OperationService())

    with pytest.raises(LiveReadOnlyRunnerError, match="BRC_EXECUTION_PERMISSION_MAX=intent_recording"):
        await runner.run_once(_config(permission))


@pytest.mark.asyncio
async def test_live_read_only_runner_refuses_non_live_trading_env():
    runner = _runner(_OperationService())
    config = _config()
    config = config.model_copy(update={"trading_env": "testnet"})

    with pytest.raises(LiveReadOnlyRunnerError, match="TRADING_ENV=live"):
        await runner.run_once(config)


@pytest.mark.asyncio
async def test_live_read_only_runner_skips_when_account_facts_unavailable():
    operations = _OperationService()
    runner = _runner(
        operations,
        _SnapshotProvider(account_facts={"source": "unavailable", "truth_level": "unavailable"}),
    )

    evidence = await runner.run_once(_config())

    assert evidence.status == "skipped"
    assert evidence.skipped_reason == "account facts unavailable"
    assert operations.preflight_calls == []
    assert operations.confirm_calls == []


@pytest.mark.asyncio
async def test_live_read_only_runner_respects_hard_lock():
    operations = _OperationService()
    runner = _runner(operations, runtime_safety={"hard_lock_active": True})

    evidence = await runner.run_once(_config())

    assert evidence.status == "skipped"
    assert evidence.skipped_reason == "hard lock active"
    assert operations.preflight_calls == []
    assert operations.confirm_calls == []


@pytest.mark.asyncio
async def test_live_read_only_runner_records_signal_and_trial_trade_intent_without_order():
    operations = _OperationService()
    recorded = []

    async def _record(evidence):
        recorded.append(evidence)

    runner = _runner(operations, recorder=_record)

    evidence = await runner.run_once(_config())

    assert evidence.status == "executed"
    assert evidence.not_executed_reason == "observe_only"
    assert evidence.execution_permission_resolution["final_permission"] == "intent_recording"
    assert [call["operation_type"] for call in operations.preflight_calls] == [
        "evaluate_signal_from_admission_strategy",
        "record_trial_trade_intent_from_signal_evaluation",
    ]
    assert [call["confirmation_phrase"] for call in operations.confirm_calls] == [
        "CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
        "CONFIRM_RECORD_TRIAL_TRADE_INTENT",
    ]
    assert evidence.signal_result["result_summary"]["execution_intent_created"] is False
    assert evidence.trial_trade_intent_result["result_summary"]["execution_intent_created"] is False
    assert evidence.trial_trade_intent_result["result_summary"]["order_created"] is False
    assert evidence.trial_trade_intent_result["result_summary"]["orders_placed"] is False
    assert recorded == [evidence]


@pytest.mark.asyncio
async def test_live_read_only_runner_skips_intent_when_permission_preflight_blocks():
    operations = _OperationService(intent_decision="block", intent_final_permission="signal_only")
    runner = _runner(operations)

    evidence = await runner.run_once(_config())

    assert evidence.status == "intent_skipped"
    assert evidence.execution_permission_resolution["final_permission"] == "signal_only"
    assert len(operations.confirm_calls) == 1
    assert operations.confirm_calls[0]["confirmation_phrase"] == "CONFIRM_EVALUATE_SIGNAL_NO_INTENT"


@pytest.mark.asyncio
async def test_live_read_only_runner_raises_if_adapter_returns_execution_artifact():
    operations = _OperationService(unsafe_result=True)
    runner = _runner(operations)

    with pytest.raises(LiveReadOnlyRunnerError, match="execution intent"):
        await runner.run_once(_config())


@pytest.mark.asyncio
async def test_exchange_gateway_read_only_snapshot_provider_uses_only_read_methods():
    gateway = _Gateway()
    provider = ExchangeGatewayReadOnlySnapshotProvider(
        gateway=gateway,
        symbols=("ETH/USDT:USDT",),
    )

    account_facts = await provider.read_account_facts()
    market_snapshot = await provider.read_market_snapshot(symbol="ETH/USDT:USDT")

    assert account_facts["source"] == "exchange_live"
    assert account_facts["unknown_unmanaged_counts"] == {"orders": 0, "positions": 0}
    assert market_snapshot["mark_price"] == "3000"
    assert gateway.calls == [
        "fetch_account_balance",
        "fetch_positions:None",
        "fetch_open_orders:ETH/USDT:USDT",
        "fetch_ticker_price:ETH/USDT:USDT",
    ]
