from __future__ import annotations

import argparse
from decimal import Decimal
import importlib
from types import SimpleNamespace
from types import ModuleType

import pytest

from scripts.trading_kernel import run_command_worker_once as command_cli
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
)
from src.trading_kernel.domain.capacity import ActionTimeFacts


class FakeCcxtExchange:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.closed = False
        self.ohlcv_symbols: list[str] = []

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object = None,
        limit: int | None = None,
    ) -> list[list[object]]:
        del timeframe, since, limit
        self.ohlcv_symbols.append(symbol)
        return [[1, "10", "11", "9", "10.5", "20"]]

    async def load_markets(self, reload: bool = False) -> dict[str, object]:
        assert reload is False
        return {}

    def market(self, symbol: str) -> dict[str, object]:
        assert symbol == "BTC/USDT:USDT"
        return {
            "info": {
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.001",
                        "minQty": "0.001",
                    },
                    {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ]
            }
        }

    async def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class FakeWorkerAdapter:
    def __init__(self) -> None:
        self.closed = False

    async def execute(self, request: object) -> object:
        del request
        raise AssertionError("worker stub must replace dispatch")

    async def read_action_time_facts(self, request: object) -> object:
        del request
        raise AssertionError("worker stub must replace fact collection")

    async def read_instrument_rules(self, request: object) -> object:
        del request
        raise AssertionError("worker stub must replace rule collection")

    async def close(self) -> None:
        self.closed = True


class FakeProbeAdapter:
    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal("5"),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_action_time_facts(
        self,
        request: ActionTimeFactsRequest,
    ) -> ActionTimeFacts:
        return ActionTimeFacts(
            signal_event_id=request.signal_event_id,
            runtime_scope_id=request.runtime_scope_id,
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            position_side=request.position_side,
            account_position_mode="independent_sides",
            best_bid_price=Decimal("99"),
            best_ask_price=Decimal("100"),
            account_equity=Decimal("1000"),
            available_margin=Decimal("900"),
            netting_domain_position_qty=Decimal("0"),
            netting_domain_open_order_count=0,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


def _set_valid_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "TRADING_KERNEL_ENVIRONMENT": "live",
        "TRADING_KERNEL_VENUE_ID": "binance-usdm",
        "TRADING_KERNEL_ACCOUNT_ID": "subaccount-main",
        "TRADING_KERNEL_ACCOUNT_POSITION_MODE": "independent_sides",
        "TRADING_KERNEL_API_KEY": "api-key-sensitive",
        "TRADING_KERNEL_API_SECRET": "api-secret-sensitive",
        "TRADING_KERNEL_TIMEOUT_SECONDS": "7.5",
        "TRADING_KERNEL_EXIT_TAKER_FEE_RATE": "0.0005",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _production_runtime() -> ModuleType:
    try:
        return importlib.import_module(
            "src.trading_kernel.infrastructure.production_runtime"
        )
    except ModuleNotFoundError:
        pytest.fail("production Binance runtime factory module is missing")


def test_factory_requires_exact_live_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_runtime_environment(monkeypatch)
    monkeypatch.setenv("TRADING_KERNEL_VENUE_ID", "wrong")
    production_runtime = _production_runtime()

    with pytest.raises(ValueError, match="venue identity"):
        production_runtime.build_binance_usdm_venue_adapter()


def test_settings_mask_credentials_and_require_independent_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_runtime_environment(monkeypatch)
    production_runtime = _production_runtime()

    settings = production_runtime.ProductionRuntimeSettings.from_environment()

    rendered = repr(settings)
    assert "api-key-sensitive" not in rendered
    assert "api-secret-sensitive" not in rendered
    assert settings.account_position_mode == "independent_sides"

    monkeypatch.setenv("TRADING_KERNEL_ACCOUNT_POSITION_MODE", "one_way")
    with pytest.raises(ValueError, match="position mode identity"):
        production_runtime.ProductionRuntimeSettings.from_environment()


@pytest.mark.asyncio
async def test_public_factory_uses_only_canonical_registry_symbols_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_runtime_environment(monkeypatch)
    production_runtime = _production_runtime()
    created: list[FakeCcxtExchange] = []

    def constructor(config: dict[str, object]) -> FakeCcxtExchange:
        exchange = FakeCcxtExchange(config)
        created.append(exchange)
        return exchange

    monkeypatch.setattr(production_runtime.ccxt_async, "binanceusdm", constructor)

    source = production_runtime.build_binance_usdm_market_source()
    candles = await source.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id="binance-usdm:OPUSDT:perpetual",
            timeframe="1h",
            limit=1,
            closed_at_ms=3_600_000,
        )
    )

    assert len(candles) == 1
    assert created[0].ohlcv_symbols == ["OP/USDT:USDT"]
    assert "apiKey" not in created[0].config
    assert "secret" not in created[0].config

    await source.close()
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_authenticated_factory_builds_exact_mapping_rules_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_runtime_environment(monkeypatch)
    production_runtime = _production_runtime()
    created: list[FakeCcxtExchange] = []

    def constructor(config: dict[str, object]) -> FakeCcxtExchange:
        exchange = FakeCcxtExchange(config)
        created.append(exchange)
        return exchange

    monkeypatch.setattr(production_runtime.ccxt_async, "binanceusdm", constructor)

    adapter = production_runtime.build_binance_usdm_venue_adapter()
    rules = await adapter.read_instrument_rules(
        InstrumentRulesRequest(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            observed_at_ms=1_000,
            valid_for_ms=5_000,
        )
    )

    assert created[0].config["apiKey"] == "api-key-sensitive"
    assert created[0].config["secret"] == "api-secret-sensitive"
    assert created[0].config["timeout"] == 7_500
    assert rules.quantity_step == Decimal("0.001")
    assert rules.price_tick == Decimal("0.1")
    assert rules.min_notional == Decimal("5")

    await adapter.close()
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_command_worker_closes_factory_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeWorkerAdapter()
    engine = FakeEngine()
    monkeypatch.setattr(command_cli, "_load_factory", lambda spec: lambda: adapter)
    monkeypatch.setattr(command_cli, "create_async_engine", lambda url: engine)

    async def run_worker(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return SimpleNamespace(model_dump=lambda **kwargs: {"status": "idle"})

    monkeypatch.setattr(command_cli, "run_entry_worker_once", run_worker)

    exit_code = await command_cli._run(
        argparse.Namespace(
            database_url="postgresql+asyncpg://kernel:test@localhost/kernel",
            venue_factory="module:factory",
            worker_role="entry",
            worker_id="entry-1",
            runtime_commit="commit-1",
            schema_revision="0001_initial",
            now_ms=1_000,
            lease_ms=30_000,
            timeout_seconds=10.0,
            action_fact_validity_ms=5_000,
            idle_poll_interval_ms=2_000,
        )
    )

    assert exit_code == 0
    assert adapter.closed is True
    assert engine.disposed is True


@pytest.mark.asyncio
async def test_readonly_probe_reports_only_bounded_identity_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_runtime_environment(monkeypatch)
    production_runtime = _production_runtime()
    try:
        probe_module = importlib.import_module(
            "scripts.trading_kernel.probe_production_runtime"
        )
    except ModuleNotFoundError:
        pytest.fail("readonly production runtime probe is missing")
    settings = production_runtime.ProductionRuntimeSettings.from_environment()

    result = await probe_module.probe_production_runtime(
        FakeProbeAdapter(),
        settings,
        now_ms=10_000,
        validity_ms=5_000,
    )

    assert result.instrument_rule_count == 6
    assert result.netting_domain_count == 12
    assert result.non_flat_domain_count == 0
    assert result.open_order_domain_count == 0
    assert result.account_position_mode == "independent_sides"
    rendered = result.model_dump_json()
    assert "api-key-sensitive" not in rendered
    assert "api-secret-sensitive" not in rendered
    assert "credential" not in rendered.lower()
