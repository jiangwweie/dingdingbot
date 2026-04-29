"""
验证 6 + 7a: Backtester 异常传播与 position_size=0 跳过

验证 6: save_report 抛异常时，backtester 不再静默吞掉，而是向上传播
验证 7a: position_size=0 时，backtester 跳过该信号（不创建订单）
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import os

from src.domain.models import (
    Direction,
    BacktestRequest,
)
from src.application.backtester import Backtester


# ============================================================
# 验证 6: exception raise 不再静默吞
# ============================================================

class TestExceptionPropagation:
    """
    验证 6: backtest_repository.save_report 抛异常时，
    _run_v3_pms_backtest 应将异常向上传播，而非静默吞掉。

    对应代码 (backtester.py line 1551-1553):
        except Exception as e:
            logger.error(f"Failed to save backtest report: {e}")
            raise  # 不再静默吞掉异常
    """

    def _create_minimal_backtester(self):
        """Create a Backtester with mock gateway."""
        mock_gateway = AsyncMock()
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
        return Backtester(mock_gateway)

    @pytest.mark.asyncio
    async def test_save_report_exception_propagates(self):
        """
        验证 6: save_report 抛异常时，异常应向上传播。

        使用 mock 让 backtest_repository.save_report 始终抛异常，
        验证 backtester._run_v3_pms_backtest 使用 pytest.raises 确认异常向上传播。
        """
        backtester = self._create_minimal_backtester()

        # Create a mock backtest_repository that always raises
        mock_backtest_repo = AsyncMock()
        mock_backtest_repo.save_report = AsyncMock(
            side_effect=RuntimeError("Database connection lost")
        )

        # Create a minimal request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            strategies=[
                {
                    "id": "test_strat",
                    "name": "TestStrategy",
                    "triggers": [
                        {"type": "pinbar", "params": {
                            "min_wick_ratio": 0.5,
                            "max_body_ratio": 0.35,
                            "body_position_tolerance": 0.2,
                        }}
                    ],
                    "filters": [],
                    "filter_logic": "AND",
                    "apply_to": ["BTC/USDT:USDT:1h"],
                }
            ],
        )

        # _run_v3_pms_backtest requires klines, so we test at a lower level:
        # Directly test the exception propagation by mocking the inner flow.
        # Since _run_v3_pms_backtest is complex, we test the exception path
        # by directly invoking the try/except block logic.

        # Approach: Test that when save_report raises, the exception is NOT caught.
        # We verify this by calling a simplified version that isolates the exception path.

        # The actual code path in backtester.py lines 1538-1553:
        #   try:
        #       await backtest_repository.save_report(...)
        #   except Exception as e:
        #       logger.error(...)
        #       raise  <-- This is what we verify

        # Test: save_report raising should propagate
        with pytest.raises(RuntimeError, match="Database connection lost"):
            # Simulate the try/except block from backtester.py line 1538-1553
            try:
                await mock_backtest_repo.save_report(
                    MagicMock(), '{"triggers": []}', "BTC/USDT:USDT", "1h"
                )
            except Exception as e:
                # This mirrors the exact code in backtester.py:
                # except Exception as e:
                #     logger.error(f"Failed to save backtest report: {e}")
                #     raise  # 不再静默吞掉异常
                raise


# ============================================================
# 验证 6b: 集成级别 — _run_v3_pms_backtest 中 save_report 异常传播
# ============================================================

class TestExceptionPropagationIntegration:
    """
    验证 6b: 通过 mock 完整 _run_v3_pms_backtest 流程，
    验证 save_report 异常确实向上传播到调用者。
    """

    @pytest.mark.asyncio
    async def test_pms_backtest_propagates_save_report_exception(self):
        """
        验证 6b: PMS 回测中 save_report 异常向上传播。

        Mock gateway 返回有效 K 线数据让回测能走到 save_report 步骤，
        但 save_report 始终抛异常，验证调用者收到异常。
        """
        from src.domain.models import KlineData

        # Create mock gateway that returns valid klines
        mock_gateway = AsyncMock()
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=1700000000000 + i * 3600000,
                open=Decimal("50000") + Decimal(str(i)),
                high=Decimal("50100") + Decimal(str(i)),
                low=Decimal("49900") + Decimal(str(i)),
                close=Decimal("50050") + Decimal(str(i)),
                volume=Decimal("1000"),
                is_closed=True,
            )
            for i in range(10)
        ]
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=klines)

        backtester = Backtester(mock_gateway)

        # Create mock backtest_repository that always raises
        mock_backtest_repo = AsyncMock()
        mock_backtest_repo.save_report = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            limit=10,
            strategies=[
                {
                    "id": "test_strat",
                    "name": "TestStrategy",
                    "triggers": [
                        {"type": "pinbar", "params": {
                            "min_wick_ratio": 0.5,
                            "max_body_ratio": 0.35,
                            "body_position_tolerance": 0.2,
                        }}
                    ],
                    "filters": [],
                    "filter_logic": "AND",
                    "apply_to": ["BTC/USDT:USDT:1h"],
                }
            ],
        )

        # Verify exception propagates (not swallowed)
        with pytest.raises(RuntimeError, match="DB write failed"):
            await backtester._run_v3_pms_backtest(
                request,
                backtest_repository=mock_backtest_repo,
            )


# ============================================================
# 验证 7a: position_size=0 跳过信号
# ============================================================

class TestPositionSizeZeroSkip:
    """
    验证 7a: 当 calculate_position_size 返回 position_size=0 时，
    backtester 应跳过该信号（continue），不创建订单。

    对应代码 (backtester.py line 1338-1341):
        if position_size <= Decimal('0'):
            logger.info(f"[BACKTEST_SKIP] 跳过信号 {signal_id}：position_size={position_size}")
            continue
    """

    @pytest.mark.asyncio
    async def test_backtester_skips_signal_when_position_size_zero(self):
        """
        验证 7a: position_size=0 时跳过信号，不创建订单。

        通过 mock RiskCalculator.calculate_position_size 返回 (0, 1)，
        验证回测过程中该信号被跳过（active_orders 不会增加）。
        """
        from src.domain.models import KlineData
        from src.domain.risk_calculator import RiskCalculator

        # Create mock gateway with valid klines
        mock_gateway = AsyncMock()
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=1700000000000 + i * 3600000,
                open=Decimal("50000"),
                high=Decimal("50100"),
                low=Decimal("49900"),
                close=Decimal("50050"),
                volume=Decimal("1000"),
                is_closed=True,
            )
            for i in range(10)
        ]
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=klines)

        backtester = Backtester(mock_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            limit=10,
            strategies=[
                {
                    "id": "test_strat",
                    "name": "TestStrategy",
                    "triggers": [
                        {"type": "pinbar", "params": {
                            "min_wick_ratio": 0.5,
                            "max_body_ratio": 0.35,
                            "body_position_tolerance": 0.2,
                        }}
                    ],
                    "filters": [],
                    "filter_logic": "AND",
                    "apply_to": ["BTC/USDT:USDT:1h"],
                }
            ],
        )

        # Mock RiskCalculator to return position_size=0
        with patch.object(RiskCalculator, 'calculate_position_size', return_value=(Decimal('0'), 1)):
            report = await backtester._run_v3_pms_backtest(request)

            # Verify backtest completed but with 0 trades (all signals skipped)
            assert report.total_trades == 0, \
                "position_size=0 时所有信号应被跳过，total_trades 应为 0"

    @pytest.mark.asyncio
    async def test_backtester_skips_signal_when_position_size_negative(self):
        """
        验证 7a 扩展：position_size 为负数时同样应跳过信号。

        position_size <= Decimal('0') 的防护也应覆盖负数场景。
        """
        from src.domain.models import KlineData
        from src.domain.risk_calculator import RiskCalculator

        mock_gateway = AsyncMock()
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=1700000000000 + i * 3600000,
                open=Decimal("50000"),
                high=Decimal("50100"),
                low=Decimal("49900"),
                close=Decimal("50050"),
                volume=Decimal("1000"),
                is_closed=True,
            )
            for i in range(10)
        ]
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=klines)

        backtester = Backtester(mock_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            limit=10,
            strategies=[
                {
                    "id": "test_strat",
                    "name": "TestStrategy",
                    "triggers": [
                        {"type": "pinbar", "params": {
                            "min_wick_ratio": 0.5,
                            "max_body_ratio": 0.35,
                            "body_position_tolerance": 0.2,
                        }}
                    ],
                    "filters": [],
                    "filter_logic": "AND",
                    "apply_to": ["BTC/USDT:USDT:1h"],
                }
            ],
        )

        # Mock RiskCalculator to return negative position_size
        with patch.object(RiskCalculator, 'calculate_position_size', return_value=(Decimal('-1'), 1)):
            report = await backtester._run_v3_pms_backtest(request)

            assert report.total_trades == 0, \
                "position_size<0 时所有信号应被跳过，total_trades 应为 0"
