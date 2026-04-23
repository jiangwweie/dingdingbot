#!/usr/bin/env python3
"""
Sim-0 runtime chain check.

This script validates the real runtime path instead of hand-wiring services:

main.run_application()
  -> ConfigManager / PG / repositories / gateway / startup reconciliation
  -> SignalPipeline
  -> real strategy + filters
  -> ExecutionOrchestrator
  -> testnet ENTRY / protection orders

Safety:
- Requires EXCHANGE_TESTNET=true.
- Requires CORE_EXECUTION_INTENT_BACKEND=postgres.
- Uses BTC/USDT:USDT only.
- Does not print secrets.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Keep the embedded API away from any manually running local backend.
os.environ.setdefault("BACKEND_PORT", "18080")


@dataclass
class Sim0CheckResult:
    started: bool = False
    effective_testnet: Optional[bool] = None
    effective_symbol_scope: Optional[List[str]] = None
    effective_timeframes: Optional[List[str]] = None
    ticker_price: Optional[str] = None
    before_intent_count: int = 0
    after_intent_count: int = 0
    new_intents: List[Dict[str, Any]] = None
    orders_by_signal: Dict[str, List[Dict[str, Any]]] = None
    active_recovery_tasks: List[Dict[str, Any]] = None
    breaker_symbols: List[str] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.new_intents is None:
            self.new_intents = []
        if self.orders_by_signal is None:
            self.orders_by_signal = {}
        if self.active_recovery_tasks is None:
            self.active_recovery_tasks = []
        if self.breaker_symbols is None:
            self.breaker_symbols = []


def _require_env() -> None:
    if os.getenv("EXCHANGE_TESTNET", "").lower() != "true":
        raise RuntimeError("EXCHANGE_TESTNET must be true for Sim-0")
    if os.getenv("CORE_EXECUTION_INTENT_BACKEND", "").lower() != "postgres":
        raise RuntimeError("CORE_EXECUTION_INTENT_BACKEND must be postgres for Sim-0")
    if not os.getenv("PG_DATABASE_URL"):
        raise RuntimeError("PG_DATABASE_URL is required for Sim-0")


def _sync_runtime_config_from_env() -> None:
    """Sync .env runtime config into the existing config DB compatibility layer."""
    db_path = Path(os.getenv("CONFIG_DB_PATH", str(ROOT / "data" / "v3_dev.db")))
    api_key = os.getenv("EXCHANGE_API_KEY", "")
    api_secret = os.getenv("EXCHANGE_API_SECRET", "")
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")

    if not api_key or not api_secret:
        raise RuntimeError("EXCHANGE_API_KEY / EXCHANGE_API_SECRET are required")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO exchange_configs (id, exchange_name, api_key, api_secret, testnet, updated_at)
            VALUES ('primary', ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              exchange_name=excluded.exchange_name,
              api_key=excluded.api_key,
              api_secret=excluded.api_secret,
              testnet=1,
              updated_at=CURRENT_TIMESTAMP,
              version=exchange_configs.version+1
            """,
            (os.getenv("EXCHANGE_NAME", "binance"), api_key, api_secret),
        )
        if webhook:
            cur.execute(
                """
                INSERT INTO notifications
                (id, channel_type, webhook_url, is_active, notify_on_signal, notify_on_order, notify_on_error, updated_at)
                VALUES ('default', 'feishu', ?, 1, 1, 1, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                  channel_type='feishu',
                  webhook_url=excluded.webhook_url,
                  is_active=1,
                  notify_on_signal=1,
                  notify_on_order=1,
                  notify_on_error=1,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (webhook,),
            )
        cur.execute(
            """
            UPDATE system_configs
            SET core_symbols=?, timeframes=?, asset_polling_enabled=1, updated_at=CURRENT_TIMESTAMP
            WHERE id='global'
            """,
            (json.dumps(["BTC/USDT:USDT"]), json.dumps(["15m", "1h"])),
        )
        conn.commit()
    finally:
        conn.close()


def _floor_to_hour_ms(ts_ms: int) -> int:
    return ts_ms - (ts_ms % (60 * 60 * 1000))


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _make_kline(symbol: str, timeframe: str, timestamp: int, open_: Decimal, high: Decimal, low: Decimal, close: Decimal):
    from src.domain.models import KlineData

    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=_q(open_),
        high=_q(high),
        low=_q(low),
        close=_q(close),
        volume=Decimal("1000"),
        is_closed=True,
    )


def _build_controlled_history(symbol: str, anchor_price: Decimal) -> tuple[List[Any], List[Any], Any]:
    """Create bullish 1h/15m history plus one bullish pinbar signal candle."""
    now_ms = int(time.time() * 1000)
    signal_ts = _floor_to_hour_ms(now_ms) + (60 * 60 * 1000)
    hour_ms = 60 * 60 * 1000
    m15_ms = 15 * 60 * 1000

    start_price = anchor_price * Decimal("0.92")
    end_price = anchor_price * Decimal("0.995")

    one_hour = []
    for i in range(80):
        ratio = Decimal(i) / Decimal("79")
        close = start_price + (end_price - start_price) * ratio
        open_ = close * Decimal("0.998")
        high = close * Decimal("1.004")
        low = close * Decimal("0.994")
        ts = signal_ts - (80 - i) * hour_ms
        one_hour.append(_make_kline(symbol, "1h", ts, open_, high, low, close))

    m15 = []
    for i in range(80):
        ratio = Decimal(i) / Decimal("79")
        close = start_price + (end_price - start_price) * ratio
        open_ = close * Decimal("0.998")
        high = close * Decimal("1.004")
        low = close * Decimal("0.994")
        ts = signal_ts - (80 - i + 1) * m15_ms
        m15.append(_make_kline(symbol, "15m", ts, open_, high, low, close))

    high = anchor_price * Decimal("1.001")
    close = anchor_price
    open_ = anchor_price * Decimal("0.999")
    low = anchor_price * Decimal("0.975")
    signal_kline = _make_kline(symbol, "15m", signal_ts, open_, high, low, close)
    return one_hour, m15, signal_kline


async def _wait_for_runtime(main_module: Any, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pipeline = main_module.get_signal_pipeline()
        gateway = getattr(main_module, "_exchange_gateway", None)
        orchestrator = getattr(main_module, "_execution_orchestrator", None)
        if pipeline is not None and gateway is not None and orchestrator is not None:
            # Phase 6 has completed once warmup history is present.
            if pipeline._kline_history:
                return
        await asyncio.sleep(1)
    raise TimeoutError("runtime did not become ready in time")


async def run_check() -> Sim0CheckResult:
    _require_env()
    _sync_runtime_config_from_env()

    # Import main only after .env has been loaded.
    import src.main as app_main
    from src.domain.models import AccountSnapshot

    result = Sim0CheckResult()
    started_at = int(time.time() * 1000)
    runtime_task = asyncio.create_task(app_main.run_application())
    result.started = True

    try:
        await _wait_for_runtime(app_main)

        pipeline = app_main.get_signal_pipeline()
        gateway = app_main._exchange_gateway
        orchestrator = app_main._execution_orchestrator
        order_repo = app_main._order_repo
        recovery_repo = app_main._execution_recovery_repo

        user_config = await pipeline._config_manager.get_user_config()
        result.effective_testnet = user_config.exchange.testnet
        result.effective_symbol_scope = pipeline._config_manager.get_core_config().core_symbols
        result.effective_timeframes = user_config.timeframes

        if not result.effective_testnet:
            raise RuntimeError("effective exchange config is not testnet")

        ticker = await gateway.fetch_ticker_price("BTC/USDT:USDT")
        if ticker is None:
            raise RuntimeError("cannot fetch BTC ticker from testnet")
        result.ticker_price = str(ticker)

        before_intents = await orchestrator.list_intents()
        result.before_intent_count = len(before_intents)

        # Use a small account snapshot to keep the testnet order notional modest.
        pipeline.update_account_snapshot(
            AccountSnapshot(
                total_balance=Decimal("100"),
                available_balance=Decimal("100"),
                unrealized_pnl=Decimal("0"),
                positions=[],
                timestamp=int(time.time() * 1000),
            )
        )

        one_hour, m15, signal_kline = _build_controlled_history("BTC/USDT:USDT", Decimal(str(ticker)))

        # Replace only the runtime signal history for the controlled check.
        pipeline._kline_history = {
            "BTC/USDT:USDT:1h": one_hour,
            "BTC/USDT:USDT:15m": m15,
        }
        pipeline._mtf_ema_indicators.clear()
        pipeline._signal_cooldown_cache.clear()
        pipeline._signal_cache.clear()
        pipeline._runner = pipeline._build_and_warmup_runner()

        await app_main.on_kline_received(signal_kline)
        await asyncio.sleep(12)

        after_intents = await orchestrator.list_intents()
        result.after_intent_count = len(after_intents)

        new_intents = [intent for intent in after_intents if intent.created_at >= started_at]
        for intent in new_intents:
            item = {
                "id": intent.id,
                "signal_id": intent.signal_id,
                "symbol": intent.signal.symbol if intent.signal else None,
                "status": str(intent.status),
                "order_id": intent.order_id,
                "exchange_order_id": intent.exchange_order_id,
                "failed_reason": intent.failed_reason,
                "blocked_reason": intent.blocked_reason,
            }
            result.new_intents.append(item)

            if intent.signal_id and hasattr(order_repo, "get_orders_by_signal"):
                try:
                    orders = await order_repo.get_orders_by_signal(intent.signal_id)
                    result.orders_by_signal[intent.signal_id] = [
                        {
                            "id": o.id,
                            "role": str(o.order_role),
                            "status": str(o.status),
                            "requested_qty": str(o.requested_qty),
                            "filled_qty": str(o.filled_qty),
                            "exchange_order_id": o.exchange_order_id,
                            "parent_order_id": o.parent_order_id,
                        }
                        for o in orders
                    ]
                except Exception as e:
                    result.orders_by_signal[intent.signal_id] = [{"error": str(e)}]

        if recovery_repo is not None:
            result.active_recovery_tasks = await recovery_repo.list_active()
        result.breaker_symbols = orchestrator.list_circuit_breaker_symbols()

        return result

    except Exception as e:
        result.error = str(e)
        return result
    finally:
        shutdown_event = getattr(app_main, "_shutdown_event", None)
        if shutdown_event is not None and not shutdown_event.is_set():
            shutdown_event.set()
        try:
            await asyncio.wait_for(runtime_task, timeout=30)
        except asyncio.TimeoutError:
            runtime_task.cancel()
            try:
                await runtime_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    result = asyncio.run(run_check())
    payload = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    sys.stdout.flush()
    if result.error:
        return 2
    if not result.new_intents:
        return 3
    if not any(item.get("exchange_order_id") for item in result.new_intents):
        return 4
    return 0


if __name__ == "__main__":
    # Some legacy aiosqlite workers in the main runtime are still non-daemon
    # after graceful shutdown. The validation has already closed the runtime;
    # exit hard so this one-shot smoke script does not hang forever.
    os._exit(main())
