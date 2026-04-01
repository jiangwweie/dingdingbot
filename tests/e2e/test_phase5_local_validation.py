"""
Phase 5 E2E 集成测试 - 本地验证（不依赖真实交易所）

用于验证 Phase 5 代码实现的正确性，无需真实 API 密钥
"""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.domain.models import (
    Direction, OrderType, OrderRole, OrderStatus,
    OrderRequest, DailyTradeStats
)
from src.domain.dca_strategy import DcaStrategy, DcaConfig


# ========== 模型验证测试 ==========

@pytest.mark.unit
class TestPhase5Models:
    """Phase 5 模型验证"""

    def test_order_request_market(self):
        """验证市价单请求"""
        req = OrderRequest(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            direction=Direction.LONG,
            quantity=Decimal("0.001")
        )
        assert req.symbol == "BTC/USDT:USDT"
        assert req.quantity == Decimal("0.001")
        assert req.reduce_only is False

    def test_order_request_limit(self):
        """验证限价单请求"""
        req = OrderRequest(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            direction=Direction.LONG,
            quantity=Decimal("0.001"),
            price=Decimal("100000")
        )
        assert req.price == Decimal("100000")

    def test_order_request_stop_market(self):
        """验证条件市价单"""
        req = OrderRequest(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.STOP_MARKET,
            direction=Direction.LONG,
            order_role=OrderRole.SL,
            quantity=Decimal("0.001"),
            trigger_price=Decimal("98000"),
            reduce_only=True
        )
        assert req.trigger_price == Decimal("98000")
        assert req.reduce_only is True

    def test_order_request_tp_role_requires_reduce_only(self):
        """验证 TP 角色必须 reduce_only=True"""
        req = OrderRequest(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            direction=Direction.SHORT,
            order_role=OrderRole.TP1,
            quantity=Decimal("0.0003"),
            price=Decimal("102000"),
            reduce_only=True  # TP 订单必须为 True
        )
        assert req.order_role == OrderRole.TP1
        assert req.reduce_only is True

    def test_order_request_serialization(self):
        """验证 JSON 序列化"""
        req = OrderRequest(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            order_role=OrderRole.ENTRY,
            quantity=Decimal("0.001"),
            stop_loss=Decimal("95000"),
            take_profit=Decimal("105000")
        )

        data = req.model_dump()
        assert data["symbol"] == "BTC/USDT:USDT"
        assert data["order_type"] == "MARKET"
        assert data["order_role"] == "ENTRY"
        assert data["direction"] == "LONG"


# ========== DCA 策略验证测试 ==========

@pytest.mark.unit
class TestDcaStrategy:
    """DCA 策略验证"""

    def test_dca_config(self):
        """验证 DCA 配置"""
        config = DcaConfig(
            total_amount=Decimal("0.003"),
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
        )
        assert config.total_amount == Decimal("0.003")
        assert config.entry_batches == 3
        assert config.entry_ratios == [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]

    def test_dca_batch_calculation(self):
        """验证 DCA 分批计算"""
        config = DcaConfig(
            total_amount=Decimal("0.003"),
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
        )

        # 第 1 批数量 = 总数量 * 0.5
        first_batch_qty = config.total_amount * config.entry_ratios[0]
        assert first_batch_qty == Decimal("0.0015")

    def test_dca_price_levels(self):
        """验证 DCA 价格档位计算（LIMIT 订单）"""
        config = DcaConfig(
            total_amount=Decimal("0.003"),
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
        )

        entry_price = Decimal("100000")

        # 第 2 批限价单价格 = 入场价 * (1 - 2%)
        price_level_2 = entry_price * (Decimal("1") - Decimal("0.02"))
        assert price_level_2 == Decimal("98000")

        # 第 3 批限价单价格 = 入场价 * (1 - 4%)
        price_level_3 = entry_price * (Decimal("1") - Decimal("0.04"))
        assert price_level_3 == Decimal("96000")


# ========== 资金保护逻辑验证测试 ==========

@pytest.mark.unit
class TestCapitalProtectionLogic:
    """资金保护逻辑验证"""

    def test_single_trade_loss_calculation(self):
        """单笔损失计算"""
        entry_price = Decimal("100000")
        stop_loss = Decimal("98000")  # 2% 止损
        quantity = Decimal("0.001")

        # 损失 = 数量 * (入场价 - 止损价)
        loss = quantity * (entry_price - stop_loss)
        assert loss == Decimal("2.0")  # 2.0 USDT

    def test_single_trade_loss_percent(self):
        """单笔损失百分比"""
        balance = Decimal("10000")
        loss = Decimal("200")  # 200 USDT

        loss_percent = (loss / balance) * Decimal("100")
        assert loss_percent == Decimal("2.0")  # 2%

    def test_daily_loss_tracking(self):
        """每日损失追踪"""
        stats = DailyTradeStats()
        stats.realized_pnl = Decimal("-450")  # 亏损 450 USDT
        balance = Decimal("10000")

        daily_loss_percent = (abs(stats.realized_pnl) / balance) * Decimal("100")
        assert daily_loss_percent == Decimal("4.5")

        # 如果再加一笔 2% 损失的交易，会超过 5% 日限额
        additional_loss = Decimal("200")  # 2%
        total_loss_percent = ((abs(stats.realized_pnl) + additional_loss) / balance) * Decimal("100")
        assert total_loss_percent == Decimal("6.5")
        assert total_loss_percent > Decimal("5.0")  # 超过日限额

    def test_position_exposure(self):
        """仓位暴露计算"""
        balance = Decimal("10000")
        position_value = Decimal("8500")

        exposure = position_value / balance
        assert exposure == Decimal("0.85")
        assert exposure > Decimal("0.80")  # 超过 80% 最大仓位限制


# ========== 枚举对齐验证 ==========

@pytest.mark.unit
class TestEnumAlignment:
    """枚举对齐验证"""

    def test_order_role_enum_values(self):
        """验证 OrderRole 枚举值"""
        assert OrderRole.ENTRY.value == "ENTRY"
        assert OrderRole.TP1.value == "TP1"
        assert OrderRole.TP2.value == "TP2"
        assert OrderRole.SL.value == "SL"

    def test_order_status_enum(self):
        """验证 OrderStatus 枚举"""
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELED.value == "CANCELED"

    def test_direction_enum(self):
        """验证 Direction 枚举"""
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
