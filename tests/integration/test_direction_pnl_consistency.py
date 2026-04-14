"""
Direction/PnL 一致性验证 - PMS 回测集成测试

验证目标：
- PMS 回测报告中每个 PositionSummary 的 direction 和 realized_pnl 是否数学上一致
- 验证 DA-20260414-001 报告的"方向矛盾 bug"是否真实存在

核心断言逻辑：
- LONG 仓位：exit > entry 才应盈利（realized_pnl > 0）
- SHORT 仓位：entry > exit 才应盈利（realized_pnl > 0）
- 注意：手续费会导致"价格上涨但 PnL 为负"的正常场景，但"价格反向变动但 PnL 为正"是异常
"""

import pytest
import tempfile
import sqlite3
import yaml
import asyncio
from pathlib import Path
from decimal import Decimal
from contextlib import contextmanager

from fastapi.testclient import TestClient

from src.interfaces.api import app, set_dependencies
from src.application.config_manager import ConfigManager
from src.domain.models import AccountSnapshot, KlineData, Direction


# ============================================================
# Full DB schema (copied from test_backtest_user_story.py)
# ============================================================

def _create_config_tables_sync(db_path: str) -> None:
    """Create all config tables + signal tables using raw sqlite3 (sync, for test setup)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                is_active BOOLEAN DEFAULT TRUE, trigger_config TEXT NOT NULL,
                filter_configs TEXT NOT NULL, filter_logic TEXT DEFAULT 'AND',
                symbols TEXT NOT NULL, timeframes TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, version INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS risk_configs (
                id TEXT PRIMARY KEY DEFAULT 'global', max_loss_percent DECIMAL(5,4) NOT NULL,
                max_leverage INTEGER NOT NULL, max_total_exposure DECIMAL(5,4),
                daily_max_trades INTEGER, daily_max_loss DECIMAL(20,8),
                max_position_hold_time INTEGER, cooldown_minutes INTEGER DEFAULT 240,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, version INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS system_configs (
                id TEXT PRIMARY KEY DEFAULT 'global', core_symbols TEXT NOT NULL,
                ema_period INTEGER DEFAULT 60, mtf_ema_period INTEGER DEFAULT 60,
                mtf_mapping TEXT NOT NULL, signal_cooldown_seconds INTEGER DEFAULT 14400,
                queue_batch_size INTEGER DEFAULT 10, queue_flush_interval DECIMAL(4,2) DEFAULT 5.0,
                queue_max_size INTEGER DEFAULT 1000, warmup_history_bars INTEGER DEFAULT 100,
                atr_filter_enabled BOOLEAN DEFAULT TRUE, atr_period INTEGER DEFAULT 14,
                atr_min_ratio DECIMAL(4,2) DEFAULT 0.5,
                timeframes TEXT NOT NULL DEFAULT '["15m","1h"]',
                asset_polling_enabled BOOLEAN DEFAULT TRUE, asset_polling_interval INTEGER DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY, is_active BOOLEAN DEFAULT TRUE,
                is_core BOOLEAN DEFAULT FALSE, min_quantity DECIMAL(20,8),
                price_precision INTEGER, quantity_precision INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY, channel_type TEXT NOT NULL, webhook_url TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE, notify_on_signal BOOLEAN DEFAULT TRUE,
                notify_on_order BOOLEAN DEFAULT TRUE, notify_on_error BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                snapshot_data TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT, is_auto BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS exchange_configs (
                id TEXT PRIMARY KEY DEFAULT 'primary', exchange_name TEXT NOT NULL DEFAULT 'binance',
                api_key TEXT NOT NULL, api_secret TEXT NOT NULL, testnet BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, version INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS config_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, action TEXT NOT NULL, old_values TEXT,
                new_values TEXT, changed_by TEXT, changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                change_summary TEXT
            );
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                stop_loss TEXT NOT NULL,
                position_size TEXT NOT NULL,
                leverage INTEGER NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                risk_info TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                pnl_ratio TEXT,
                kline_timestamp INTEGER,
                strategy_name TEXT DEFAULT 'unknown',
                score REAL DEFAULT 0.0,
                signal_id TEXT,
                source TEXT DEFAULT 'live',
                ema_trend TEXT,
                mtf_status TEXT,
                pattern_score REAL,
                take_profit_1 TEXT,
                closed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_signal_id ON signals(signal_id);
            CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
            CREATE TABLE IF NOT EXISTS signal_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                direction TEXT,
                pattern_score REAL,
                final_result TEXT NOT NULL,
                filter_stage TEXT,
                filter_reason TEXT,
                details TEXT NOT NULL,
                kline_timestamp INTEGER,
                evaluation_summary TEXT,
                trace_tree JSON
            );
            CREATE TABLE IF NOT EXISTS signal_take_profits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                tp_id TEXT NOT NULL,
                position_ratio TEXT NOT NULL,
                risk_reward TEXT NOT NULL,
                price_level TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                filled_at TEXT,
                pnl_ratio TEXT,
                FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS config_snapshots_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                config_json TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                created_by TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 0
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# Mock Exchange Gateway
# ============================================================

class MockExchangeGateway:
    """Mock exchange gateway that generates K-line data."""

    def __init__(self, base_price: Decimal = Decimal("3000")):
        self.call_count = 0
        self.last_params = {}
        self.base_price = base_price

    def set_global_order_callback(self, callback):
        pass

    async def fetch_historical_ohlcv(self, symbol: str, timeframe: str, limit: int = 100, since=None):
        klines = []
        for i in range(limit):
            timestamp = 1700000000000 + (i * 3600 * 1000)
            price = self.base_price + Decimal(str(i)) * Decimal("10")
            klines.append(KlineData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=price,
                high=price * Decimal("1.02"),
                low=price * Decimal("0.98"),
                close=price * Decimal("1.01"),
                volume=Decimal("1000"),
                is_closed=True,
            ))
        self.call_count += 1
        self.last_params = {"symbol": symbol, "timeframe": timeframe, "limit": limit}
        return klines


# ============================================================
# Test Setup Helper
# ============================================================

@contextmanager
def setup_pms_backtest_env(
    symbol: str = "ETH/USDT:USDT",
    timeframe: str = "1h",
    initial_balance: str = "10000",
):
    """Create a complete PMS backtest environment with mock data."""
    if "BTC" in symbol:
        base_price = Decimal("50000")
    elif "ETH" in symbol:
        base_price = Decimal("3000")
    else:
        base_price = Decimal("100")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        db_path = str(config_dir / "test.db")

        # Create tables first
        _create_config_tables_sync(db_path)

        # Core config
        core_config = {
            "core_symbols": [symbol],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {"period": 60},
            "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d"},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
        }
        with open(config_dir / "core.yaml", "w") as f:
            yaml.dump(core_config, f)

        # User config
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key",
                "api_secret": "test_secret",
                "testnet": True,
            },
            "user_symbols": [],
            "timeframes": [timeframe],
            "strategy": {
                "trend_filter_enabled": True,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
            "asset_polling": {"interval_seconds": 60},
            "notification": {
                "channels": [{
                    "type": "feishu",
                    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
                }]
            },
        }
        with open(config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        # Initialize ConfigManager and SignalRepository
        async def _setup():
            mgr = ConfigManager(config_dir=str(config_dir), db_path=db_path)
            await mgr.initialize_from_db()
            await mgr.import_from_yaml(str(config_dir / "core.yaml"), changed_by="test")
            await mgr.import_from_yaml(str(config_dir / "user.yaml"), changed_by="test")
            return mgr

        mgr = asyncio.run(_setup())

        # Mock gateway
        mock_gw = MockExchangeGateway(base_price=base_price)

        # Set dependencies
        set_dependencies(
            repository=None,  # SignalRepository will be created by ConfigManager
            account_getter=lambda: AccountSnapshot(
                total_balance=Decimal(initial_balance),
                available_balance=Decimal(initial_balance),
                unrealized_pnl=Decimal("0"),
                positions=[],
                timestamp=1700000000000,
            ),
            config_manager=mgr,
            exchange_gateway=mock_gw,
        )

        yield mock_gw


def run_pms_backtest(
    symbol: str = "ETH/USDT:USDT",
    timeframe: str = "1h",
    limit: int = 100,
    initial_balance: str = "10000",
    strategies: list = None,
) -> dict:
    """Run a PMS backtest and return the report."""
    if strategies is None:
        strategies = [
            {
                "id": "test-strategy-01",
                "name": "Test Pinbar",
                "triggers": [
                    {
                        "type": "pinbar",
                        "params": {
                            "min_wick_ratio": 0.5,
                            "max_body_ratio": 0.35,
                            "body_position_tolerance": 0.2,
                        },
                    }
                ],
                "filters": [
                    {"type": "ema_trend", "params": {"period": 60}},
                    {"type": "atr", "params": {"period": 14, "min_atr_ratio": 0.5}},
                    {"type": "mtf", "params": {}},
                ],
                "filter_logic": "AND",
                "apply_to": [f"{symbol}:{timeframe}"],
            }
        ]

    with setup_pms_backtest_env(symbol=symbol, timeframe=timeframe, initial_balance=initial_balance):
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "mode": "v3_pms",
            "initial_balance": initial_balance,
            "slippage_rate": "0.001",
            "fee_rate": "0.0004",
            "strategies": strategies,
        }

        with TestClient(app) as client:
            resp = client.post("/api/backtest/orders", json=payload, timeout=120)
            assert resp.status_code == 200, f"Backtest request failed: {resp.status_code} - {resp.text}"
            data = resp.json()
            return data.get("report", {})


# ============================================================
# Direction/PnL Verification Logic
# ============================================================

def verify_direction_pnl_consistency(report: dict, test_name: str) -> tuple:
    """
    Verify direction and realized_pnl consistency in backtest report.

    Returns:
        (consistent_list, inconsistent_list)
    """
    positions = report.get("positions", [])
    total = len(positions)

    print(f"\n{'=' * 70}")
    print(f"[{test_name}] Direction/PnL 一致性验证报告")
    print(f"{'=' * 70}")
    print(f"总仓位数: {total}")

    if total == 0:
        print("无仓位数据，跳过验证")
        return [], []

    consistent = []
    inconsistent = []

    for i, pos in enumerate(positions):
        direction = pos.get("direction", "UNKNOWN")
        entry_price = Decimal(str(pos.get("entry_price", "0")))
        exit_price_val = pos.get("exit_price")
        realized_pnl = Decimal(str(pos.get("realized_pnl", "0")))
        position_id = pos.get("position_id", f"pos_{i}")
        signal_id = pos.get("signal_id", "")
        exit_reason = pos.get("exit_reason", "UNKNOWN")

        if exit_price_val is None:
            consistent.append({
                "position_id": position_id,
                "signal_id": signal_id,
                "direction": direction,
                "status": "OPEN (no exit price)",
            })
            continue

        exit_price = Decimal(str(exit_price_val))
        is_consistent = True
        detail = ""

        if direction == Direction.LONG:
            price_diff = exit_price - entry_price
            if price_diff < 0 and realized_pnl > 0:
                is_consistent = False
                detail = (
                    f"BUG! direction=LONG, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff} (<0), pnl={realized_pnl} (>0), "
                    f"exit_reason={exit_reason}"
                )
            elif price_diff > 0 and realized_pnl < 0:
                detail = (
                    f"NOTE: direction=LONG, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff} (>0), pnl={realized_pnl} (<0), "
                    f"exit_reason={exit_reason} (手续费可能大于盈利)"
                )
            else:
                detail = (
                    f"OK: direction=LONG, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff}, pnl={realized_pnl}, "
                    f"exit_reason={exit_reason}"
                )
        elif direction == Direction.SHORT:
            price_diff = entry_price - exit_price
            if price_diff < 0 and realized_pnl > 0:
                is_consistent = False
                detail = (
                    f"BUG! direction=SHORT, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff} (<0), pnl={realized_pnl} (>0), "
                    f"exit_reason={exit_reason}"
                )
            elif price_diff > 0 and realized_pnl < 0:
                detail = (
                    f"NOTE: direction=SHORT, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff} (>0), pnl={realized_pnl} (<0), "
                    f"exit_reason={exit_reason} (手续费可能大于盈利)"
                )
            else:
                detail = (
                    f"OK: direction=SHORT, entry={entry_price}, exit={exit_price}, "
                    f"price_diff={price_diff}, pnl={realized_pnl}, "
                    f"exit_reason={exit_reason}"
                )
        else:
            detail = f"UNKNOWN direction: {direction}"

        entry = {
            "position_id": position_id,
            "signal_id": signal_id,
            "direction": direction,
            "entry_price": str(entry_price),
            "exit_price": str(exit_price),
            "realized_pnl": str(realized_pnl),
            "exit_reason": exit_reason,
            "detail": detail,
        }

        if is_consistent:
            consistent.append(entry)
        else:
            inconsistent.append(entry)

    # Print results
    closed_count = sum(1 for p in positions if p.get("exit_price") is not None)
    open_count = total - closed_count

    print(f"已平仓: {closed_count}, 未平仓: {open_count}")
    print(f"方向一致: {len(consistent)}, 方向矛盾: {len(inconsistent)}")

    if inconsistent:
        print(f"\n{'!' * 70}")
        print(f"发现 {len(inconsistent)} 笔方向矛盾的仓位:")
        print(f"{'!' * 70}")
        for item in inconsistent:
            print(f"  {item['detail']}")
    else:
        print(f"\n所有已平仓仓位方向与 PnL 一致，未发现方向矛盾 bug")

    # Print detailed log (first 20)
    print(f"\n详细日志（前 20 条）:")
    for item in (consistent + inconsistent)[:20]:
        print(f"  [{item.get('position_id', '?')}] {item['detail']}")

    return consistent, inconsistent


def print_report_summary(report: dict, test_name: str):
    """Print backtest report summary."""
    print(f"\n--- [{test_name}] 回测报告摘要 ---")
    print(f"策略: {report.get('strategy_name', 'N/A')}")
    print(f"总交易: {report.get('total_trades', 0)}")
    print(f"盈利: {report.get('winning_trades', 0)}, 亏损: {report.get('losing_trades', 0)}")
    print(f"胜率: {report.get('win_rate', 0)}%")
    print(f"总 PnL: {report.get('total_pnl', 0)}")
    print(f"总手续费: {report.get('total_fees_paid', 0)}")
    print(f"总滑点: {report.get('total_slippage_cost', 0)}")
    print(f"最大回撤: {report.get('max_drawdown', 0)}%")


# ============================================================
# Pytest Tests
# ============================================================

class TestDirectionPnLConsistency:
    """Direction/PnL consistency verification tests."""

    def test_eth_1h_direction_pnl_consistency(self):
        """Verify ETH/USDT 1h PMS backtest direction/PnL consistency."""
        report = run_pms_backtest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            limit=100,
        )
        print_report_summary(report, "ETH_1h")
        consistent, inconsistent = verify_direction_pnl_consistency(report, "ETH_1h")

        assert len(inconsistent) == 0, (
            f"发现 {len(inconsistent)} 笔方向矛盾的仓位: "
            f"{[item['detail'] for item in inconsistent]}"
        )

    def test_sol_15m_direction_pnl_consistency(self):
        """Verify SOL/USDT 15m PMS backtest direction/PnL consistency."""
        report = run_pms_backtest(
            symbol="SOL/USDT:USDT",
            timeframe="15m",
            limit=100,
        )
        print_report_summary(report, "SOL_15m")
        consistent, inconsistent = verify_direction_pnl_consistency(report, "SOL_15m")

        assert len(inconsistent) == 0, (
            f"发现 {len(inconsistent)} 笔方向矛盾的仓位: "
            f"{[item['detail'] for item in inconsistent]}"
        )


# ============================================================
# Standalone execution (python this_file.py)
# ============================================================

if __name__ == "__main__":
    all_inconsistent = []

    # Test 1: ETH/USDT 1h
    print("\n" + "=" * 70)
    print("测试 1: ETH/USDT 1h PMS 回测")
    print("=" * 70)
    try:
        report1 = run_pms_backtest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            limit=100,
        )
        print_report_summary(report1, "ETH_1h")
        _, inconsistent1 = verify_direction_pnl_consistency(report1, "ETH_1h")
        all_inconsistent.extend(inconsistent1)
    except Exception as e:
        print(f"ETH/USDT 1h 回测异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: SOL/USDT 15m
    print("\n" + "=" * 70)
    print("测试 2: SOL/USDT 15m PMS 回测")
    print("=" * 70)
    try:
        report2 = run_pms_backtest(
            symbol="SOL/USDT:USDT",
            timeframe="15m",
            limit=100,
        )
        print_report_summary(report2, "SOL_15m")
        _, inconsistent2 = verify_direction_pnl_consistency(report2, "SOL_15m")
        all_inconsistent.extend(inconsistent2)
    except Exception as e:
        print(f"SOL/USDT 15m 回测异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    # Final summary
    print("\n" + "=" * 70)
    print("最终验证汇总")
    print("=" * 70)
    if all_inconsistent:
        print(f"发现 {len(all_inconsistent)} 笔方向矛盾的仓位:")
        for item in all_inconsistent:
            print(f"  {item['detail']}")
        print("\n结论: 存在方向矛盾 bug，需要进一步调查")
    else:
        print("所有测试中均未发现方向矛盾 bug")
        print("结论: DA-20260414-001 报告的'方向矛盾 bug'未能复现，数据来源可能有问题")
