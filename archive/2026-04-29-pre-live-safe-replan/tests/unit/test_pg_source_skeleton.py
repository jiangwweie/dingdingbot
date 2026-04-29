"""
定向测试：执行主线 PG 真源闭环第一层骨架

覆盖:
A. RuntimePositionsReadModel: account_snapshot 缺失时回退到 position_repo.list_active()
B. api._get_order_repo: fallback 走 create_order_repository() + 依赖注入
C. OrderLifecycleService.register_created_order: 保存/状态机/容错
D. ENTRY filled callback: 首次触发 + 重复 FILLED 去重
E. ExecutionOrchestrator: _protect_filled_entry / _handle_entry_filled 防重
"""

from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
)


# ============================================================
# A. RuntimePositionsReadModel fallback to position_repo
# ============================================================


class TestRuntimePositionsFallback:
    """account_snapshot 缺失时，position_repo.list_active() 回退构造响应。"""

    @pytest.mark.asyncio
    async def test_fallback_single_position(self):
        """单条 PG position projection 正确映射到 ConsolePositionItem。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        repo = MagicMock()

        async def mock_list_active(*, limit=100, symbol=None):
            return [
                SimpleNamespace(
                    symbol="ETH/USDT:USDT",
                    direction="LONG",
                    current_qty=Decimal("0.5"),
                    entry_price=Decimal("3000"),
                    watermark_price=Decimal("3100"),
                    unrealized_pnl=Decimal("50"),
                    leverage=10,
                    updated_at=1710000000000,
                )
            ]

        repo.list_active = mock_list_active

        response = await read_model.build(account_snapshot=None, position_repo=repo)

        assert len(response.positions) == 1
        pos = response.positions[0]
        assert pos.symbol == "ETH/USDT:USDT"
        assert pos.direction == "LONG"
        assert pos.quantity == 0.5
        assert pos.entry_price == 3000.0
        assert pos.current_price == 3100.0  # watermark_price
        assert pos.unrealized_pnl == 50.0
        assert pos.leverage == 10
        assert pos.margin == 0.0  # PG fallback 不算 margin
        assert pos.exposure == 1500.0  # 0.5 * 3000
        assert pos.updated_at is not None

    @pytest.mark.asyncio
    async def test_fallback_multiple_positions(self):
        """多条 PG position projection 全部映射。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        repo = MagicMock()

        async def mock_list_active(*, limit=100, symbol=None):
            return [
                SimpleNamespace(
                    symbol="BTC/USDT:USDT",
                    direction="LONG",
                    current_qty=Decimal("0.1"),
                    entry_price=Decimal("64000"),
                    watermark_price=None,
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                    updated_at=1710000000000,
                ),
                SimpleNamespace(
                    symbol="SOL/USDT:USDT",
                    direction="SHORT",
                    current_qty=Decimal("2.0"),
                    entry_price=Decimal("150"),
                    watermark_price=Decimal("140"),
                    unrealized_pnl=Decimal("20"),
                    leverage=3,
                    updated_at=1710000001000,
                ),
            ]

        repo.list_active = mock_list_active

        response = await read_model.build(account_snapshot=None, position_repo=repo)

        assert len(response.positions) == 2
        assert response.positions[0].symbol == "BTC/USDT:USDT"
        assert response.positions[0].current_price == 64000.0  # watermark None → entry_price
        assert response.positions[1].symbol == "SOL/USDT:USDT"
        assert response.positions[1].direction == "SHORT"

    @pytest.mark.asyncio
    async def test_fallback_empty_list(self):
        """list_active 返回空列表时响应为空。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        repo = MagicMock()

        async def mock_list_active(*, limit=100, symbol=None):
            return []

        repo.list_active = mock_list_active

        response = await read_model.build(account_snapshot=None, position_repo=repo)

        assert len(response.positions) == 0

    @pytest.mark.asyncio
    async def test_fallback_repo_exception_returns_empty(self):
        """list_active 抛异常时回退为空列表而非报错。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        repo = MagicMock()
        repo.list_active = AsyncMock(side_effect=Exception("PG connection lost"))

        response = await read_model.build(account_snapshot=None, position_repo=repo)

        assert len(response.positions) == 0

    @pytest.mark.asyncio
    async def test_snapshot_present_skips_fallback(self):
        """account_snapshot 有数据时不走 position_repo fallback。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel
        from src.domain.models import PositionInfo

        read_model = RuntimePositionsReadModel()

        snapshot = MagicMock()
        snapshot.positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("0.1"),
                entry_price=Decimal("64000"),
                unrealized_pnl=Decimal("100"),
                leverage=5,
            )
        ]

        repo = MagicMock()
        repo.list_active = AsyncMock(side_effect=AssertionError("不应调用 list_active"))

        response = await read_model.build(account_snapshot=snapshot, position_repo=repo)

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "BTC/USDT:USDT"

    @pytest.mark.asyncio
    async def test_snapshot_empty_positions_triggers_fallback(self):
        """account_snapshot 存在但 positions 为空时，仍走 fallback。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        snapshot = MagicMock()
        snapshot.positions = []

        repo = MagicMock()

        async def mock_list_active(*, limit=100, symbol=None):
            return [
                SimpleNamespace(
                    symbol="ETH/USDT:USDT",
                    direction="LONG",
                    current_qty=Decimal("0.5"),
                    entry_price=Decimal("3000"),
                    watermark_price=Decimal("3100"),
                    unrealized_pnl=Decimal("50"),
                    leverage=10,
                    updated_at=1710000000000,
                )
            ]

        repo.list_active = mock_list_active

        response = await read_model.build(account_snapshot=snapshot, position_repo=repo)

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "ETH/USDT:USDT"

    @pytest.mark.asyncio
    async def test_no_repo_no_snapshot_returns_empty(self):
        """两者都缺失时返回空列表。"""
        from src.application.readmodels.runtime_positions import RuntimePositionsReadModel

        read_model = RuntimePositionsReadModel()

        response = await read_model.build(account_snapshot=None, position_repo=None)

        assert len(response.positions) == 0


# ============================================================
# B. api._get_order_repo fallback and injection
# ============================================================


class TestGetOrderRepoFallback:
    """_get_order_repo fallback 走 create_order_repository() + 依赖注入。"""

    def setup_method(self):
        from src.interfaces import api

        self._api = api
        self._original_order_repo = api._order_repo
        self._original_exchange_gateway = api._exchange_gateway
        self._original_audit_logger = api._audit_logger

        api._order_repo = None
        api._exchange_gateway = None
        api._audit_logger = None

    def teardown_method(self):
        self._api._order_repo = self._original_order_repo
        self._api._exchange_gateway = self._original_exchange_gateway
        self._api._audit_logger = self._original_audit_logger

    def test_fallback_calls_create_order_repository(self):
        """_order_repo 为 None 时走 create_order_repository()。"""
        repo = MagicMock()

        with patch("src.interfaces.api.create_order_repository", return_value=repo) as mock_create:
            resolved = self._api._get_order_repo()

        assert resolved is repo
        mock_create.assert_called_once_with()

    def test_injects_exchange_gateway_when_available(self):
        """repo 有 set_exchange_gateway 时注入 gateway。"""
        repo = MagicMock()
        repo.set_exchange_gateway = MagicMock()
        gateway = MagicMock()
        self._api._exchange_gateway = gateway

        with patch("src.interfaces.api.create_order_repository", return_value=repo):
            resolved = self._api._get_order_repo()

        repo.set_exchange_gateway.assert_called_once_with(gateway)

    def test_injects_audit_logger_when_available(self):
        """repo 有 set_audit_logger 时注入 audit_logger。"""
        repo = MagicMock()
        repo.set_audit_logger = MagicMock()
        audit_logger = MagicMock()
        self._api._audit_logger = audit_logger

        with patch("src.interfaces.api.create_order_repository", return_value=repo):
            resolved = self._api._get_order_repo()

        repo.set_audit_logger.assert_called_once_with(audit_logger)

    def test_no_injection_when_repo_lacks_methods(self):
        """repo 没有 set_exchange_gateway / set_audit_logger 时不报错。"""
        repo = MagicMock(spec=[])  # no methods
        gateway = MagicMock()
        audit_logger = MagicMock()
        self._api._exchange_gateway = gateway
        self._api._audit_logger = audit_logger

        with patch("src.interfaces.api.create_order_repository", return_value=repo):
            resolved = self._api._get_order_repo()

        assert resolved is repo

    def test_returns_existing_repo_when_set(self):
        """_order_repo 已设置时直接返回，不走 factory。"""
        existing_repo = MagicMock()
        self._api._order_repo = existing_repo

        with patch("src.interfaces.api.create_order_repository") as mock_create:
            resolved = self._api._get_order_repo()

        assert resolved is existing_repo
        mock_create.assert_not_called()

    def test_no_gateway_skips_injection(self):
        """_exchange_gateway 为 None 时跳过 gateway 注入。"""
        repo = MagicMock()
        repo.set_exchange_gateway = MagicMock()
        self._api._exchange_gateway = None
        self._api._audit_logger = MagicMock()
        repo.set_audit_logger = MagicMock()

        with patch("src.interfaces.api.create_order_repository", return_value=repo):
            resolved = self._api._get_order_repo()

        repo.set_exchange_gateway.assert_not_called()
        repo.set_audit_logger.assert_called()


# ============================================================
# C. OrderLifecycleService.register_created_order
# ============================================================


class TestRegisterCreatedOrder:
    """register_created_order: 保存订单、创建状态机、容错。"""

    @pytest.fixture
    async def service(self, tmp_path):
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.infrastructure.order_repository import OrderRepository

        db_path = str(tmp_path / "test_register.db")
        repo = OrderRepository(db_path=db_path)
        await repo.initialize()
        svc = OrderLifecycleService(repository=repo)
        await svc.start()
        yield svc
        await svc.stop()

    @pytest.mark.asyncio
    async def test_saves_order_and_sets_created_status(self, service):
        """register_created_order 保存订单并设置 CREATED 状态。"""
        order = Order(
            id="reg_test_001",
            signal_id="sig_reg_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("0.5"),
            filled_qty=Decimal("0"),
            price=Decimal("60000"),
            status=OrderStatus.OPEN,  # 传入任意状态，方法会强制 CREATED
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        result = await service.register_created_order(order)

        assert result.status == OrderStatus.CREATED
        assert result.id == "reg_test_001"

        # 验证持久化
        saved = await service.get_order("reg_test_001")
        assert saved is not None
        assert saved.status == OrderStatus.CREATED

    @pytest.mark.asyncio
    async def test_creates_state_machine(self, service):
        """register_created_order 为订单创建状态机。"""
        order = Order(
            id="reg_test_002",
            signal_id="sig_reg_002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal("0.3"),
            filled_qty=Decimal("0"),
            price=Decimal("3000"),
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        await service.register_created_order(order)

        sm = service.get_state_machine("reg_test_002")
        assert sm is not None
        assert sm.current_status == OrderStatus.CREATED

    @pytest.mark.asyncio
    async def test_no_audit_logger_does_not_error(self, tmp_path):
        """audit_logger 为 None 时不报错。"""
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.infrastructure.order_repository import OrderRepository

        db_path = str(tmp_path / "test_no_audit.db")
        repo = OrderRepository(db_path=db_path)
        await repo.initialize()
        svc = OrderLifecycleService(repository=repo, audit_logger=None)
        await svc.start()

        try:
            order = Order(
                id="reg_test_003",
                signal_id="sig_reg_003",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.LIMIT,
                order_role=OrderRole.TP2,
                requested_qty=Decimal("0.1"),
                filled_qty=Decimal("0"),
                price=Decimal("62000"),
                status=OrderStatus.OPEN,
                created_at=int(time.time() * 1000),
                updated_at=int(time.time() * 1000),
            )

            result = await svc.register_created_order(order)
            assert result.status == OrderStatus.CREATED
        finally:
            await svc.stop()

    @pytest.mark.asyncio
    async def test_no_notify_callback_does_not_error(self, tmp_path):
        """on_order_changed 回调未设置时不报错。"""
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.infrastructure.order_repository import OrderRepository

        db_path = str(tmp_path / "test_no_notify.db")
        repo = OrderRepository(db_path=db_path)
        await repo.initialize()
        svc = OrderLifecycleService(repository=repo)
        await svc.start()

        # 不设置任何回调
        assert svc._on_order_changed is None

        try:
            order = Order(
                id="reg_test_004",
                signal_id="sig_reg_004",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.LIMIT,
                order_role=OrderRole.SL,
                requested_qty=Decimal("0.2"),
                filled_qty=Decimal("0"),
                price=Decimal("58000"),
                status=OrderStatus.OPEN,
                created_at=int(time.time() * 1000),
                updated_at=int(time.time() * 1000),
            )

            result = await svc.register_created_order(order)
            assert result.status == OrderStatus.CREATED
        finally:
            await svc.stop()

    @pytest.mark.asyncio
    async def test_triggered_by_and_metadata_passed(self, service):
        """triggered_by 和 metadata 参数正确传递到审计日志。"""
        from src.application.order_audit_logger import OrderAuditEventType, OrderAuditTriggerSource

        audit_logger = AsyncMock()
        audit_logger.log = AsyncMock()
        service._audit_logger = audit_logger

        order = Order(
            id="reg_test_005",
            signal_id="sig_reg_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0"),
            price=Decimal("59000"),
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        await service.register_created_order(
            order,
            triggered_by=OrderAuditTriggerSource.EXCHANGE,
            metadata={"reason": "protection_order"},
        )

        # audit_logger.log 应被调用
        assert audit_logger.log.called


# ============================================================
# D. ENTRY filled callback: 首次触发 + 重复 FILLED 去重
# ============================================================


class TestEntryFilledCallback:
    """update_order_from_exchange: ENTRY 首次 FILLED 触发 callback，重复不触发。"""

    @pytest.fixture
    async def service(self, tmp_path):
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.infrastructure.order_repository import OrderRepository

        db_path = str(tmp_path / "test_entry_filled.db")
        repo = OrderRepository(db_path=db_path)
        await repo.initialize()
        svc = OrderLifecycleService(repository=repo)
        await svc.start()
        yield svc
        await svc.stop()

    @pytest.mark.asyncio
    async def test_entry_filled_triggers_callback(self, service):
        """ENTRY 首次变成 FILLED 时触发 entry_filled callback。"""
        callback_calls = []

        async def on_entry_filled(order):
            callback_calls.append(order.id)

        service.set_entry_filled_callback(on_entry_filled)

        # 创建 ENTRY 订单并推进到 OPEN
        from src.domain.models import OrderStrategy

        strategy = OrderStrategy(
            id="test_strat",
            name="Test",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_entry_filled_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("1.0"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[Decimal("1.5")],
        )
        await service.submit_order(order.id, exchange_order_id="ex_001")
        await service.confirm_order(order.id)

        # 模拟交易所推送 FILLED
        exchange_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="ex_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        await service.update_order_from_exchange(exchange_order)

        assert len(callback_calls) == 1
        assert callback_calls[0] == order.id

    @pytest.mark.asyncio
    async def test_duplicate_filled_does_not_retrigger_callback(self, service):
        """同一订单重复收到 FILLED 不应重复触发 callback。"""
        callback_calls = []

        async def on_entry_filled(order):
            callback_calls.append(order.id)

        service.set_entry_filled_callback(on_entry_filled)

        from src.domain.models import OrderStrategy

        strategy = OrderStrategy(
            id="test_strat",
            name="Test",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_entry_filled_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("1.0"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[Decimal("1.5")],
        )
        await service.submit_order(order.id, exchange_order_id="ex_002")
        await service.confirm_order(order.id)

        # 首次 FILLED
        exchange_order_1 = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="ex_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        await service.update_order_from_exchange(exchange_order_1)

        # 重复 FILLED（WebSocket 推送重复）
        exchange_order_2 = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="ex_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        await service.update_order_from_exchange(exchange_order_2)

        # callback 只触发一次
        assert len(callback_calls) == 1

    @pytest.mark.asyncio
    async def test_non_entry_filled_does_not_trigger(self, service):
        """非 ENTRY 角色（如 SL）FILLED 不触发 entry_filled callback。"""
        callback_calls = []

        async def on_entry_filled(order):
            callback_calls.append(order.id)

        service.set_entry_filled_callback(on_entry_filled)

        # 直接注册一个 SL 订单
        sl_order = Order(
            id="sl_order_001",
            signal_id="sig_sl_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            price=Decimal("60000"),
            status=OrderStatus.CREATED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        await service.register_created_order(sl_order)
        await service.submit_order(sl_order.id, exchange_order_id="ex_sl_001")
        await service.confirm_order(sl_order.id)

        # SL 订单 FILLED
        exchange_sl = Order(
            id=sl_order.id,
            signal_id=sl_order.signal_id,
            exchange_order_id="ex_sl_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("60000"),
            status=OrderStatus.FILLED,
            created_at=sl_order.created_at,
            updated_at=sl_order.updated_at,
        )
        await service.update_order_from_exchange(exchange_sl)

        # SL FILLED 不触发 entry_filled callback
        assert len(callback_calls) == 0

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_break_update(self, service):
        """entry_filled callback 抛异常不影响 update_order_from_exchange 主流程。"""
        async def failing_callback(order):
            raise RuntimeError("callback boom")

        service.set_entry_filled_callback(failing_callback)

        from src.domain.models import OrderStrategy

        strategy = OrderStrategy(
            id="test_strat",
            name="Test",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_entry_filled_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("1.0"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[Decimal("1.5")],
        )
        await service.submit_order(order.id, exchange_order_id="ex_003")
        await service.confirm_order(order.id)

        exchange_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="ex_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        # 不应抛异常
        result = await service.update_order_from_exchange(exchange_order)
        assert result.status == OrderStatus.FILLED


# ============================================================
# E. ExecutionOrchestrator: _protect_filled_entry / _handle_entry_filled 防重
# ============================================================


class TestOrchestratorEntryFilledDedup:
    """_protect_filled_entry / _handle_entry_filled 防重行为。"""

    @pytest.mark.asyncio
    async def test_has_existing_protection_orders_returns_true(self):
        """已有保护单时 _has_existing_protection_orders 返回 True。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_001",
            signal_id="sig_dedup_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        sl_order = Order(
            id="sl_001",
            signal_id="sig_dedup_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            parent_order_id="entry_001",
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, sl_order])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_existing_protection_orders_returns_false(self):
        """无保护单时 _has_existing_protection_orders 返回 False。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_002",
            signal_id="sig_dedup_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        assert result is False

    @pytest.mark.asyncio
    async def test_protect_filled_entry_skips_when_protection_exists(self):
        """已有保护单时 _protect_filled_entry 跳过挂载但仍投影仓位。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator
        from src.domain.execution_intent import ExecutionIntentStatus

        entry_order = Order(
            id="entry_003",
            signal_id="sig_dedup_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        sl_order = Order(
            id="sl_003",
            signal_id="sig_dedup_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            parent_order_id="entry_003",
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, sl_order])

        mock_project = AsyncMock()

        intent = MagicMock()
        intent.id = "intent_003"
        intent.strategy = MagicMock()

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle
        orchestrator._project_position_from_entry_order = mock_project

        await orchestrator._protect_filled_entry(
            intent=intent,
            entry_order=entry_order,
            strategy=intent.strategy,
        )

        # 不应挂载新保护单（没有调用 _mount_protection_orders）
        # 但应投影仓位
        mock_project.assert_called_once_with(entry_order)

    @pytest.mark.asyncio
    async def test_protect_filled_entry_no_strategy_skips(self):
        """strategy 为 None 时 _protect_filled_entry 直接返回。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_004",
            signal_id="sig_dedup_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_project = AsyncMock()

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._project_position_from_entry_order = mock_project

        intent = MagicMock()
        intent.id = "intent_004"

        await orchestrator._protect_filled_entry(
            intent=intent,
            entry_order=entry_order,
            strategy=None,
        )

        # strategy 为 None，不应投影也不应挂载
        mock_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_entry_filled_no_intent_skips(self):
        """_handle_entry_filled 找不到 intent 时跳过。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_005",
            signal_id="sig_dedup_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_load_intent = AsyncMock(return_value=None)
        mock_protect = AsyncMock()

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._load_intent_by_order_id = mock_load_intent
        orchestrator._protect_filled_entry = mock_protect

        await orchestrator._handle_entry_filled(entry_order)

        # 没有 intent，不应调用 _protect_filled_entry
        mock_protect.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_entry_filled_with_intent_calls_protect(self):
        """_handle_entry_filled 找到 intent 时调用 _protect_filled_entry。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_006",
            signal_id="sig_dedup_006",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        intent = MagicMock()
        intent.id = "intent_006"
        intent.strategy = MagicMock()

        mock_load_intent = AsyncMock(return_value=intent)
        mock_protect = AsyncMock()

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._load_intent_by_order_id = mock_load_intent
        orchestrator._protect_filled_entry = mock_protect

        await orchestrator._handle_entry_filled(entry_order)

        mock_protect.assert_called_once_with(
            intent=intent,
            entry_order=entry_order,
            strategy=intent.strategy,
        )

    @pytest.mark.asyncio
    async def test_has_existing_protection_orders_ignores_unrelated_orders(self):
        """_has_existing_protection_orders 只看 parent_order_id 匹配的保护单。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_007",
            signal_id="sig_dedup_007",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        # 另一个 ENTRY 的保护单，parent_order_id 不同
        unrelated_sl = Order(
            id="sl_other",
            signal_id="sig_dedup_007",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            parent_order_id="entry_other",
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, unrelated_sl])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        assert result is False  # unrelated_sl 的 parent_order_id 不匹配


# ============================================================
# F. _has_existing_protection_orders 兜底防重
# ============================================================


class TestHasExistingProtectionOrdersFallback:
    """_has_existing_protection_orders: parent_order_id 匹配 → True，
    parent_order_id 不匹配但 signal_id 下有 TP/SL → True（兜底防重），
    只有 ENTRY 没有 TP/SL → False。"""

    @pytest.mark.asyncio
    async def test_parent_order_id_match_returns_true(self):
        """parent_order_id 匹配时返回 True。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_parent_001",
            signal_id="sig_fallback_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        # SL 的 parent_order_id 匹配 entry
        sl_order = Order(
            id="sl_match_001",
            signal_id="sig_fallback_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            parent_order_id="entry_parent_001",
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, sl_order])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        assert result is True

    @pytest.mark.asyncio
    async def test_parent_order_id_mismatch_but_unbound_protection_returns_true(self):
        """parent_order_id 不匹配，但存在"未绑定 parent"的 TP/SL → 兜底返回 True（防重）。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_no_match_002",
            signal_id="sig_fallback_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        # TP1 未绑定 parent_order_id（对账重建/历史脏数据）
        tp1_order = Order(
            id="tp1_unbound_002",
            signal_id="sig_fallback_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal("0.5"),
            filled_qty=Decimal("0"),
            parent_order_id=None,  # 未绑定 → 兜底命中
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, tp1_order])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        # 兜底防重：未绑定 parent 的保护单 → True
        assert result is True

    @pytest.mark.asyncio
    async def test_parent_order_id_mismatch_bound_to_other_entry_returns_false(self):
        """parent_order_id 不匹配且已绑定到别的 ENTRY → False（不误判）。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_bound_004",
            signal_id="sig_fallback_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        # SL 已绑定到另一个 ENTRY（parent_order_id 不为空且不匹配当前 entry）
        sl_bound = Order(
            id="sl_bound_other_004",
            signal_id="sig_fallback_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            parent_order_id="entry_other_004",  # 绑定到别的 ENTRY，不为空
            status=OrderStatus.OPEN,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order, sl_bound])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        # parent_order_id 不匹配且不为空 → 不算兜底命中 → False
        assert result is False

    @pytest.mark.asyncio
    async def test_only_entry_no_protection_returns_false(self):
        """同 signal_id 下只有 ENTRY、没有保护单时返回 False。"""
        from src.application.execution_orchestrator import ExecutionOrchestrator

        entry_order = Order(
            id="entry_only_003",
            signal_id="sig_fallback_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            status=OrderStatus.FILLED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )

        mock_lifecycle = MagicMock()
        mock_lifecycle.get_orders_by_signal = AsyncMock(return_value=[entry_order])

        orchestrator = ExecutionOrchestrator.__new__(ExecutionOrchestrator)
        orchestrator._order_lifecycle = mock_lifecycle

        result = await orchestrator._has_existing_protection_orders(entry_order)
        assert result is False


# ============================================================
# G. EXIT filled callback: 首次触发 + 重复 FILLED 去重
# ============================================================


class TestExitFilledCallback:
    """update_order_from_exchange: EXIT (SL/TP) 首次 FILLED 触发 callback，重复不触发。"""

    @pytest.fixture
    async def service(self, tmp_path):
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.infrastructure.order_repository import OrderRepository

        db_path = str(tmp_path / "test_exit_filled.db")
        repo = OrderRepository(db_path=db_path)
        await repo.initialize()
        svc = OrderLifecycleService(repository=repo)
        await svc.start()
        yield svc
        await svc.stop()

    @pytest.mark.asyncio
    async def test_exit_filled_triggers_callback(self, service):
        """SL 首次变成 FILLED 时触发 exit_filled callback。"""
        callback_calls = []

        async def on_exit_filled(order):
            callback_calls.append(order.id)

        service.set_exit_filled_callback(on_exit_filled)

        sl_order = Order(
            id="sl_exit_001",
            signal_id="sig_exit_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            price=Decimal("60000"),
            status=OrderStatus.CREATED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        await service.register_created_order(sl_order)
        await service.submit_order(sl_order.id, exchange_order_id="ex_sl_001")
        await service.confirm_order(sl_order.id)

        exchange_order = Order(
            id=sl_order.id,
            signal_id=sl_order.signal_id,
            exchange_order_id="ex_sl_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("60000"),
            status=OrderStatus.FILLED,
            created_at=sl_order.created_at,
            updated_at=sl_order.updated_at,
        )

        await service.update_order_from_exchange(exchange_order)

        assert len(callback_calls) == 1
        assert callback_calls[0] == sl_order.id

    @pytest.mark.asyncio
    async def test_tp1_filled_triggers_callback(self, service):
        """TP1 首次变成 FILLED 时触发 exit_filled callback。"""
        callback_calls = []

        async def on_exit_filled(order):
            callback_calls.append(order.id)

        service.set_exit_filled_callback(on_exit_filled)

        tp1_order = Order(
            id="tp1_exit_002",
            signal_id="sig_exit_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal("0.5"),
            filled_qty=Decimal("0"),
            price=Decimal("66000"),
            status=OrderStatus.CREATED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        await service.register_created_order(tp1_order)
        await service.submit_order(tp1_order.id, exchange_order_id="ex_tp1_002")
        await service.confirm_order(tp1_order.id)

        exchange_order = Order(
            id=tp1_order.id,
            signal_id=tp1_order.signal_id,
            exchange_order_id="ex_tp1_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal("0.5"),
            filled_qty=Decimal("0.5"),
            average_exec_price=Decimal("66000"),
            status=OrderStatus.FILLED,
            created_at=tp1_order.created_at,
            updated_at=tp1_order.updated_at,
        )

        await service.update_order_from_exchange(exchange_order)

        assert len(callback_calls) == 1
        assert callback_calls[0] == tp1_order.id

    @pytest.mark.asyncio
    async def test_duplicate_filled_does_not_retrigger_exit_callback(self, service):
        """同一 SL 订单重复收到 FILLED 不应重复触发 exit_filled callback。"""
        callback_calls = []

        async def on_exit_filled(order):
            callback_calls.append(order.id)

        service.set_exit_filled_callback(on_exit_filled)

        sl_order = Order(
            id="sl_exit_003",
            signal_id="sig_exit_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            price=Decimal("60000"),
            status=OrderStatus.CREATED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        await service.register_created_order(sl_order)
        await service.submit_order(sl_order.id, exchange_order_id="ex_sl_003")
        await service.confirm_order(sl_order.id)

        # 首次 FILLED
        exchange_order_1 = Order(
            id=sl_order.id,
            signal_id=sl_order.signal_id,
            exchange_order_id="ex_sl_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("60000"),
            status=OrderStatus.FILLED,
            created_at=sl_order.created_at,
            updated_at=sl_order.updated_at,
        )
        await service.update_order_from_exchange(exchange_order_1)

        # 重复 FILLED
        exchange_order_2 = Order(
            id=sl_order.id,
            signal_id=sl_order.signal_id,
            exchange_order_id="ex_sl_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("60000"),
            status=OrderStatus.FILLED,
            created_at=sl_order.created_at,
            updated_at=sl_order.updated_at,
        )
        await service.update_order_from_exchange(exchange_order_2)

        assert len(callback_calls) == 1

    @pytest.mark.asyncio
    async def test_entry_filled_does_not_trigger_exit_callback(self, service):
        """ENTRY FILLED 不触发 exit_filled callback。"""
        exit_callback_calls = []

        async def on_exit_filled(order):
            exit_callback_calls.append(order.id)

        service.set_exit_filled_callback(on_exit_filled)

        from src.domain.models import OrderStrategy

        strategy = OrderStrategy(
            id="test_strat",
            name="Test",
            tp_levels=1,
            tp_ratios=[Decimal("1.0")],
            tp_targets=[Decimal("1.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_exit_not_entry_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal("1.0"),
            initial_sl_rr=Decimal("-1.0"),
            tp_targets=[Decimal("1.5")],
        )
        await service.submit_order(order.id, exchange_order_id="ex_entry_004")
        await service.confirm_order(order.id)

        exchange_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="ex_entry_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        await service.update_order_from_exchange(exchange_order)

        assert len(exit_callback_calls) == 0

    @pytest.mark.asyncio
    async def test_exit_callback_exception_does_not_break_update(self, service):
        """exit_filled callback 抛异常不影响 update_order_from_exchange 主流程。"""
        async def failing_callback(order):
            raise RuntimeError("exit callback boom")

        service.set_exit_filled_callback(failing_callback)

        sl_order = Order(
            id="sl_exit_exception_005",
            signal_id="sig_exit_exception_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0"),
            price=Decimal("60000"),
            status=OrderStatus.CREATED,
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        await service.register_created_order(sl_order)
        await service.submit_order(sl_order.id, exchange_order_id="ex_sl_exception_005")
        await service.confirm_order(sl_order.id)

        exchange_order = Order(
            id=sl_order.id,
            signal_id=sl_order.signal_id,
            exchange_order_id="ex_sl_exception_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("60000"),
            status=OrderStatus.FILLED,
            created_at=sl_order.created_at,
            updated_at=sl_order.updated_at,
        )

        # 不应抛异常，主流程正常完成
        result = await service.update_order_from_exchange(exchange_order)
        assert result.status == OrderStatus.FILLED
