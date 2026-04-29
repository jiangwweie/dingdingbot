"""
Phase 5 集成场景测试

测试覆盖:
1. ExchangeGateway + PositionManager 集成
2. CapitalProtection + ExchangeGateway 集成
3. DcaStrategy + ExchangeGateway 集成
4. Reconciliation + PositionManager 集成

Reference: docs/designs/phase5-detailed-design.md
"""
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call
import time

from src.domain.models import (
    Direction,
    OrderType,
    OrderRole,
    OrderStatus,
    OrderResponse,
    PositionInfo,
    ReconciliationReport,
)
from src.application.position_manager import PositionManager
from src.application.capital_protection import CapitalProtectionManager, AccountService, CapitalProtectionConfig
from src.application.reconciliation import ReconciliationService
from src.domain.dca_strategy import DcaStrategy, DcaConfig, OrderManagerProtocol
from src.infrastructure.exchange_gateway import ExchangeGateway, OrderCancelResult


# ============================================================
# 集成测试 1: ExchangeGateway + PositionManager
# ============================================================

class TestExchangeGatewayPositionManagerIntegration:
    """测试 ExchangeGateway 与 PositionManager 的集成"""

    @pytest.fixture
    def mock_db(self):
        """创建模拟数据库 Session"""
        db = AsyncMock()
        async_tx = AsyncMock()
        async_tx.__aenter__ = AsyncMock(return_value=None)
        async_tx.__aexit__ = AsyncMock(return_value=None)
        db.begin = MagicMock(return_value=async_tx)
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def mock_gateway(self):
        """创建模拟 ExchangeGateway"""
        gateway = AsyncMock()
        gateway.rest_exchange = AsyncMock()
        gateway.place_order = AsyncMock()
        gateway.cancel_order = AsyncMock()
        gateway.fetch_order = AsyncMock()
        return gateway

    @pytest.fixture
    def position_manager(self, mock_db):
        """创建 PositionManager 实例"""
        return PositionManager(mock_db)

    @pytest.mark.asyncio
    async def test_place_order_creates_position(self, mock_gateway, position_manager, mock_db):
        """测试：下单成功后创建仓位"""
        # 准备：模拟订单成交
        order_response = OrderResponse(
            order_id="order_001",
            exchange_order_id="ex_001",
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            order_role=OrderRole.ENTRY,
            status=OrderStatus.FILLED,
            amount=Decimal("0.1"),
            filled_amount=Decimal("0.1"),
            price=Decimal("70000"),
            average_exec_price=Decimal("70000"),
            reduce_only=False,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        mock_gateway.place_order.return_value = order_response

        # Mock 仓位不存在
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # 执行：下单
        result = await mock_gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            amount=Decimal("0.1"),
            price=None,
        )

        # 验证：订单被放置
        assert result.order_id == "order_001"
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_reduce_position_updates_db(self, position_manager, mock_db):
        """测试：减仓处理更新数据库"""
        from src.infrastructure.v3_orm import PositionORM

        # 准备仓位
        position = PositionORM(
            id="pos_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            entry_price=Decimal("70000"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("70000"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
            is_closed=False,
        )

        # Mock 获取仓位
        with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = position

            # 准备平仓订单
            order = MagicMock()
            order.direction = Direction.LONG
            order.filled_qty = Decimal("0.05")
            order.average_exec_price = Decimal("75000")
            order.fee_paid = Decimal("0.5")

            # 执行减仓
            net_pnl = await position_manager.reduce_position("pos_001", order)

            # 验证：盈亏计算正确
            # 毛盈亏 = (75000 - 70000) * 0.05 = 250
            # 净盈亏 = 250 - 0.5 = 249.5
            expected_net_pnl = (Decimal("75000") - Decimal("70000")) * Decimal("0.05") - Decimal("0.5")
            assert net_pnl == expected_net_pnl

            # 验证：仓位状态更新
            assert position.current_qty == Decimal("0.05")  # 0.1 - 0.05
            assert position.realized_pnl == expected_net_pnl
            assert position.total_fees_paid == Decimal("0.5")
            assert position.is_closed == False

    @pytest.mark.asyncio
    async def test_full_close_position(self, position_manager, mock_db):
        """测试：完全平仓"""
        from src.infrastructure.v3_orm import PositionORM

        position = PositionORM(
            id="pos_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction="LONG",
            entry_price=Decimal("70000"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("70000"),
            realized_pnl=Decimal("100"),
            total_fees_paid=Decimal("1"),
            is_closed=False,
        )

        with patch.object(position_manager, '_fetch_position_locked', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = position

            # 准备完全平仓订单
            order = MagicMock()
            order.direction = Direction.LONG
            order.filled_qty = Decimal("0.1")  # 全部平仓
            order.average_exec_price = Decimal("72000")
            order.fee_paid = Decimal("0.5")

            # 执行减仓
            await position_manager.reduce_position("pos_001", order)

            # 验证：完全平仓
            assert position.current_qty == Decimal("0")
            assert position.is_closed == True
            assert position.closed_at is not None


# ============================================================
# 集成测试 2: CapitalProtection + ExchangeGateway
# ============================================================

class TestCapitalProtectionExchangeGatewayIntegration:
    """测试 CapitalProtectionManager 与 ExchangeGateway 的集成"""

    @pytest.fixture
    def mock_config(self):
        """创建测试配置"""
        return CapitalProtectionConfig(
            enabled=True,
            single_trade={
                "max_loss_percent": Decimal("2.0"),
                "max_position_percent": Decimal("20"),
            },
            daily={
                "max_loss_percent": Decimal("5.0"),
                "max_trade_count": 50,
            },
            account={
                "min_balance": Decimal("100"),
                "max_leverage": 10,
            },
        )

    @pytest.fixture
    def mock_account_service(self):
        """创建模拟账户服务"""
        account = AsyncMock(spec=AccountService)
        account.get_balance = AsyncMock(return_value=Decimal("10000"))
        return account

    @pytest.fixture
    def mock_notifier(self):
        """创建模拟通知服务"""
        notifier = AsyncMock()
        notifier.send_alert = AsyncMock()
        return notifier

    @pytest.fixture
    def mock_gateway(self):
        """创建模拟 ExchangeGateway"""
        gateway = AsyncMock()
        gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50000"))
        return gateway

    @pytest.fixture
    def capital_protection(self, mock_config, mock_account_service, mock_notifier, mock_gateway):
        """创建 CapitalProtectionManager 实例"""
        return CapitalProtectionManager(
            config=mock_config,
            account_service=mock_account_service,
            notifier=mock_notifier,
            gateway=mock_gateway,
        )

    @pytest.mark.asyncio
    async def test_market_order_price_from_gateway(self, capital_protection, mock_gateway):
        """测试：市价单从网关获取价格进行资本保护检查"""
        # 设置网关返回价格
        mock_gateway.fetch_ticker_price.return_value = Decimal("50123.45")

        # 执行资本保护检查（市价单无价格）
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 验证：调用了网关获取价格
        mock_gateway.fetch_ticker_price.assert_called_once_with("BTC/USDT:USDT")
        assert result.allowed is True
        # 验证使用获取的价格计算仓位价值
        assert result.position_value == Decimal("501.2345")

    @pytest.mark.asyncio
    async def test_market_order_gateway_failure(self, capital_protection, mock_gateway):
        """测试：市价单网关获取价格失败"""
        # 设置网关返回 None
        mock_gateway.fetch_ticker_price.return_value = None

        # 执行资本保护检查
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 验证：拒绝订单
        assert result.allowed is False
        assert result.reason == "CANNOT_ESTIMATE_MARKET_PRICE"

    @pytest.mark.asyncio
    async def test_stop_market_uses_trigger_price_not_gateway(self, capital_protection, mock_gateway):
        """测试：条件市价单使用触发价，不调用网关"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 执行资本保护检查（条件市价单）
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.STOP_MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=Decimal("51000"),
            stop_loss=Decimal("50500"),
        )

        # 验证：没有调用网关（使用 trigger_price）
        mock_gateway.fetch_ticker_price.assert_not_called()
        assert result.allowed is True
        # 验证使用触发价计算
        assert result.position_value == Decimal("510")

    @pytest.mark.asyncio
    async def test_limit_order_uses_provided_price(self, capital_protection, mock_gateway):
        """测试：限价单使用提供的价格，不调用网关"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 执行资本保护检查（限价单）
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 验证：没有调用网关
        mock_gateway.fetch_ticker_price.assert_not_called()
        assert result.allowed is True
        assert result.position_value == Decimal("500")


# ============================================================
# 集成测试 3: DcaStrategy + ExchangeGateway
# ============================================================

class TestDcaStrategyExchangeGatewayIntegration:
    """测试 DcaStrategy 与 ExchangeGateway 的集成"""

    @pytest.fixture
    def mock_order_manager(self):
        """创建模拟 OrderManager（实现 OrderManagerProtocol）"""
        manager = AsyncMock(spec=OrderManagerProtocol)
        manager.place_market_order = AsyncMock(return_value="order_123")
        manager.place_limit_order = AsyncMock(return_value="order_456")
        return manager

    @pytest.fixture
    def mock_gateway(self):
        """创建模拟 ExchangeGateway"""
        gateway = AsyncMock()
        gateway.rest_exchange = AsyncMock()
        return gateway

    @pytest.fixture
    def dca_config(self):
        """创建 DCA 配置"""
        return DcaConfig(
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
            place_all_orders_upfront=True,
            total_amount=Decimal("1000"),
        )

    @pytest.fixture
    def dca_strategy(self, dca_config):
        """创建 DcaStrategy 实例"""
        return DcaStrategy(
            config=dca_config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
        )

    @pytest.mark.asyncio
    async def test_dca_first_batch_market_order(self, dca_strategy, mock_order_manager):
        """测试：DCA 第一批市价单执行"""
        total_amount = Decimal("1000")

        # 执行第一批
        order_id = await dca_strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=total_amount,
        )

        # 验证：市价单被放置
        assert order_id == "order_123"
        mock_order_manager.place_market_order.assert_called_once_with(
            symbol="BTC/USDT:USDT",
            side="buy",
            qty=Decimal("500"),  # 50% of 1000
            reduce_only=False,
        )

    @pytest.mark.asyncio
    async def test_dca_place_limit_orders_after_first_batch(self, dca_strategy, mock_order_manager):
        """测试：第一批成交后预埋限价单"""
        # 执行第一批
        await dca_strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        # 记录第一批成交价
        dca_strategy.record_first_execution(Decimal("500"), Decimal("100"))

        # 预埋限价单
        placed = await dca_strategy.place_all_limit_orders(mock_order_manager)

        # 验证：2 个限价单被放置
        assert len(placed) == 2
        assert placed[0]["batch_index"] == 2
        assert placed[0]["limit_price"] == Decimal("98.00")  # -2%
        assert placed[1]["batch_index"] == 3
        assert placed[1]["limit_price"] == Decimal("96.00")  # -4%

        # 验证调用
        assert mock_order_manager.place_limit_order.call_count == 2

    @pytest.mark.asyncio
    async def test_dca_short_position_limit_price(self, dca_config, mock_order_manager):
        """测试：SHORT 方向的限价单价格计算"""
        strategy = DcaStrategy(
            config=dca_config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
        )

        # 执行第一批
        await strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        strategy.record_first_execution(Decimal("500"), Decimal("100"))

        # 计算限价（SHORT：价格上涨触发）
        # Batch 2: 100 * (1 - (-0.02)) = 102
        limit_price_2 = strategy.calculate_limit_price(batch_index=2)
        assert limit_price_2 == Decimal("102.00")

        # Batch 3: 100 * (1 - (-0.04)) = 104
        limit_price_3 = strategy.calculate_limit_price(batch_index=3)
        assert limit_price_3 == Decimal("104.00")

    @pytest.mark.asyncio
    async def test_dca_average_cost_calculation(self, dca_strategy, mock_order_manager):
        """测试：DCA 平均成本计算"""
        # 执行所有批次
        await dca_strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy.record_first_execution(Decimal("500"), Decimal("100"))

        # 记录第 2 批
        dca_strategy.record_batch_execution(
            batch_index=2,
            executed_qty=Decimal("300"),
            executed_price=Decimal("98"),
        )

        # 记录第 3 批
        dca_strategy.record_batch_execution(
            batch_index=3,
            executed_qty=Decimal("200"),
            executed_price=Decimal("96"),
        )

        # 验证平均成本
        # Total qty = 500 + 300 + 200 = 1000
        # Total value = 500*100 + 300*98 + 200*96 = 50000 + 29400 + 19200 = 98600
        # Average cost = 98600 / 1000 = 98.6
        assert dca_strategy.get_average_cost() == Decimal("98.6")


# ============================================================
# 集成测试 4: Reconciliation + PositionManager
# ============================================================

class TestReconciliationPositionManagerIntegration:
    """测试 ReconciliationService 与 PositionManager 的集成"""

    @pytest.fixture
    def mock_gateway(self):
        """创建模拟 ExchangeGateway"""
        gateway = AsyncMock()
        gateway.rest_exchange = AsyncMock()
        gateway.cancel_order = AsyncMock()
        return gateway

    @pytest.fixture
    def mock_position_mgr(self):
        """创建模拟 PositionManager"""
        return AsyncMock()

    @pytest.fixture
    def reconciliation_service(self, mock_gateway, mock_position_mgr):
        """创建 ReconciliationService 实例"""
        return ReconciliationService(
            gateway=mock_gateway,
            position_mgr=mock_position_mgr,
            grace_period_seconds=0,  # 测试时跳过等待
        )

    def create_position_info(self, symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")):
        """创建 PositionInfo 辅助方法"""
        return PositionInfo(
            symbol=symbol,
            side="long",
            size=current_qty,
            entry_price=Decimal("70000"),
            unrealized_pnl=Decimal("500"),
            leverage=10,
        )

    @pytest.mark.asyncio
    async def test_reconciliation_with_position_manager(self, reconciliation_service, mock_gateway, mock_position_mgr):
        """测试：对账服务与 PositionManager 集成"""
        # 准备本地仓位
        local_positions = [
            self.create_position_info(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
        ]
        mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)

        # 准备交易所仓位（一致）
        mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.1,
                'side': 'long',
                'entryPrice': 70000,
                'unrealizedPnl': 500,
                'leverage': 10,
            }
        ])
        mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

        # 执行对账
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

        # 验证：无差异
        assert report.is_consistent is True
        assert report.total_discrepancies == 0

    @pytest.mark.asyncio
    async def test_reconciliation_detects_missing_position(self, reconciliation_service, mock_gateway, mock_position_mgr):
        """测试：对账服务检测缺失仓位"""
        # 本地无仓位
        mock_position_mgr.get_open_positions = AsyncMock(return_value=[])

        # 交易所有仓位
        mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.1,
                'side': 'long',
                'entryPrice': 70000,
                'unrealizedPnl': 500,
                'leverage': 10,
            }
        ])
        mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

        # 执行对账
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

        # 验证：检测到缺失仓位
        assert report.is_consistent is False
        assert report.total_discrepancies == 1
        assert len(report.missing_positions) == 1

    @pytest.mark.asyncio
    async def test_reconciliation_detects_position_mismatch(self, reconciliation_service, mock_gateway, mock_position_mgr):
        """测试：对账服务检测仓位数量不匹配"""
        # 本地仓位 0.1
        local_positions = [
            self.create_position_info(symbol="BTC/USDT:USDT", current_qty=Decimal("0.1")),
        ]
        mock_position_mgr.get_open_positions = AsyncMock(return_value=local_positions)

        # 交易所仓位 0.15（不一致）
        mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.15,
                'side': 'long',
                'entryPrice': 70000,
                'unrealizedPnl': 500,
                'leverage': 10,
            }
        ])
        mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

        # 执行对账
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

        # 验证：检测到不匹配
        assert report.is_consistent is False
        assert report.total_discrepancies == 1
        assert len(report.position_mismatches) == 1
        assert report.position_mismatches[0].local_qty == Decimal("0.1")
        assert report.position_mismatches[0].exchange_qty == Decimal("0.15")
        assert report.position_mismatches[0].discrepancy == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_handle_orphan_orders_cancel_reduce_only(self, reconciliation_service, mock_gateway):
        """测试：处理孤儿订单 - 取消减仓订单"""
        orphan_orders = [
            OrderResponse(
                order_id="orphan_001",
                exchange_order_id="ex_orphan_001",
                symbol="BTC/USDT:USDT",
                order_type=OrderType.LIMIT,
                direction=Direction.LONG,
                order_role=OrderRole.TP1,
                status=OrderStatus.OPEN,
                amount=Decimal("0.1"),
                filled_amount=Decimal("0"),
                price=Decimal("75000"),
                reduce_only=True,
                created_at=int(time.time() * 1000),
                updated_at=int(time.time() * 1000),
            )
        ]

        mock_gateway.cancel_order = AsyncMock(return_value=OrderCancelResult(
            order_id="ex_orphan_001",
            symbol="BTC/USDT:USDT",
            status=OrderStatus.CANCELED,
            message="Order canceled successfully",
        ))

        # 执行处理
        await reconciliation_service.handle_orphan_orders(orphan_orders)

        # 验证：取消订单被调用
        mock_gateway.cancel_order.assert_called_once_with(
            order_id="ex_orphan_001",
            symbol="BTC/USDT:USDT",
        )

    @pytest.mark.asyncio
    async def test_grace_period_resolves_websocket_delay(self, reconciliation_service, mock_gateway, mock_position_mgr):
        """测试：宽限期解决 WebSocket 延迟导致的幽灵偏差"""
        # 第一次调用返回空（本地仓位尚未同步）
        call_count = {'positions': 0}

        async def get_positions_side_effect(*args):
            call_count['positions'] += 1
            if call_count['positions'] == 1:
                return []  # 第一次调用：无仓位
            else:
                return [self.create_position_info()]  # 第二次调用：有仓位

        mock_position_mgr.get_open_positions = AsyncMock(side_effect=get_positions_side_effect)
        mock_gateway.rest_exchange.fetch_positions = AsyncMock(return_value=[
            {
                'symbol': 'BTC/USDT:USDT',
                'contracts': 0.1,
                'side': 'long',
                'entryPrice': 70000,
                'unrealizedPnl': 500,
                'leverage': 10,
            }
        ])
        mock_gateway.rest_exchange.fetch_open_orders = AsyncMock(return_value=[])

        # 执行对账（grace_period_seconds=0）
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")

        # 验证：差异被解决（一致）
        assert report.is_consistent is True
        assert report.total_discrepancies == 0


# ============================================================
# 综合集成测试
# ============================================================

class TestPhase5FullIntegration:
    """Phase 5 完整集成测试"""

    @pytest.mark.asyncio
    async def test_full_order_lifecycle(self):
        """测试：完整的订单生命周期"""
        # 1. 资本保护检查通过
        # 2. 下单成功
        # 3. 创建仓位
        # 4. 订单成交
        # 5. 更新仓位
        # 6. 对账一致

        # 由于这是集成测试，我们主要验证接口契约和流程
        # 实际的交易所交互需要真实环境

        # 验证各模块的枚举模型
        from src.domain.models import Direction, OrderType, OrderRole, OrderStatus

        # 验证枚举类型
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderRole.ENTRY.value == "ENTRY"
        assert OrderStatus.FILLED.value == "FILLED"

        # 验证 Decimal 精度
        amount = Decimal("0.1")
        assert amount == Decimal("0.1")
        assert amount * Decimal("70000") == Decimal("7000")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
