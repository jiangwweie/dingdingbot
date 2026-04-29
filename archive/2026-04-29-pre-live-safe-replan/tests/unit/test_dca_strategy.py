"""
Unit tests for DCA (Dollar-Cost Averaging) strategy.

Coverage:
- First batch market order execution
- Limit order price calculation (G-003)
- Pre-placing all limit orders upfront (G-003 fix)
- Average cost basis calculation
- Batch state tracking
- Boundary conditions

Test Count: 10+ tests
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from src.domain.dca_strategy import (
    DcaStrategy,
    DcaConfig,
    DcaState,
    DcaBatch,
    DcaBatchTrigger,
    OrderManagerProtocol,
)
from src.domain.models import Direction, OrderType


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_order_manager():
    """Create mock order manager."""
    manager = AsyncMock(spec=OrderManagerProtocol)
    manager.place_market_order = AsyncMock(return_value="order_123")
    manager.place_limit_order = AsyncMock(return_value="order_456")
    return manager


@pytest.fixture
def default_dca_config():
    """Create default DCA config."""
    return DcaConfig(
        entry_batches=3,
        entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
        place_all_orders_upfront=True,
        total_amount=Decimal("1000"),  # 1000 units total
    )


@pytest.fixture
def dca_strategy_long(default_dca_config):
    """Create DCA strategy for LONG position."""
    return DcaStrategy(
        config=default_dca_config,
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
    )


@pytest.fixture
def dca_strategy_short(default_dca_config):
    """Create DCA strategy for SHORT position."""
    return DcaStrategy(
        config=default_dca_config,
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.SHORT,
    )


# ============================================================
# Test 1: First batch market order execution
# ============================================================
class TestFirstBatchExecution:

    @pytest.mark.asyncio
    async def test_execute_first_batch_market_order(self, dca_strategy_long, mock_order_manager):
        """Test executing first batch as market order."""
        total_amount = Decimal("1000")

        # Execute first batch
        order_id = await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=total_amount,
        )

        # Verify order was placed
        assert order_id == "order_123"
        mock_order_manager.place_market_order.assert_called_once_with(
            symbol="BTC/USDT:USDT",
            side="buy",
            qty=Decimal("500"),  # 50% of 1000
            reduce_only=False,
        )

        # Verify batch was recorded
        assert len(dca_strategy_long.state.executed_batches) == 1
        batch = dca_strategy_long.state.executed_batches[0]
        assert batch.batch_index == 1
        assert batch.order_type == OrderType.MARKET.value
        assert batch.ratio == Decimal("0.5")
        assert batch.status == "placed"

    @pytest.mark.asyncio
    async def test_execute_first_batch_short_side(self, dca_strategy_short, mock_order_manager):
        """Test executing first batch for SHORT position."""
        total_amount = Decimal("1000")

        order_id = await dca_strategy_short.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=total_amount,
        )

        # Verify side is "sell" for SHORT
        mock_order_manager.place_market_order.assert_called_once_with(
            symbol="BTC/USDT:USDT",
            side="sell",
            qty=Decimal("500"),
            reduce_only=False,
        )

    @pytest.mark.asyncio
    async def test_record_first_execution(self, dca_strategy_long, mock_order_manager):
        """Test recording first batch execution."""
        # Execute first batch
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )

        # Record execution
        executed_qty = Decimal("500")
        executed_price = Decimal("100")
        dca_strategy_long.record_first_execution(executed_qty, executed_price)

        # Verify state updated
        assert dca_strategy_long.state.first_exec_price == Decimal("100")
        assert dca_strategy_long.state.total_executed_qty == Decimal("500")
        assert dca_strategy_long.state.total_executed_value == Decimal("50000")
        assert dca_strategy_long.state.average_cost == Decimal("100")

        # Verify batch status
        batch = dca_strategy_long.state.executed_batches[0]
        assert batch.executed_qty == Decimal("500")
        assert batch.executed_price == Decimal("100")
        assert batch.status == "filled"


# ============================================================
# Test 2: Limit order price calculation (G-003)
# ============================================================
class TestLimitPriceCalculation:

    @pytest.mark.asyncio
    async def test_calculate_limit_price_long(self, dca_strategy_long, mock_order_manager):
        """Test limit price calculation for LONG position."""
        # Setup first execution
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Calculate limit prices for batch 2 and 3
        # Batch 2: -2% drop → 100 * (1 - 0.02) = 98
        limit_price_2 = dca_strategy_long.calculate_limit_price(batch_index=2)
        assert limit_price_2 == Decimal("98.00")

        # Batch 3: -4% drop → 100 * (1 - 0.04) = 96
        limit_price_3 = dca_strategy_long.calculate_limit_price(batch_index=3)
        assert limit_price_3 == Decimal("96.00")

    @pytest.mark.asyncio
    async def test_calculate_limit_price_short(self, dca_strategy_short, mock_order_manager):
        """Test limit price calculation for SHORT position."""
        # Setup first execution
        await dca_strategy_short.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_short.record_first_execution(Decimal("500"), Decimal("100"))

        # Calculate limit prices for batch 2 and 3
        # SHORT: limit_price = first_exec_price * (1 - trigger_drop_percent/100)
        # Batch 2: -2% → 100 * (1 - (-0.02)) = 100 * 1.02 = 102
        limit_price_2 = dca_strategy_short.calculate_limit_price(batch_index=2)
        assert limit_price_2 == Decimal("102.00")

        # Batch 3: -4% → 100 * (1 - (-0.04)) = 100 * 1.04 = 104
        limit_price_3 = dca_strategy_short.calculate_limit_price(batch_index=3)
        assert limit_price_3 == Decimal("104.00")

    @pytest.mark.asyncio
    async def test_calculate_limit_price_without_first_exec(self, dca_strategy_long):
        """Test that limit price returns None without first execution."""
        limit_price = dca_strategy_long.calculate_limit_price(batch_index=2)
        assert limit_price is None

    @pytest.mark.asyncio
    async def test_calculate_limit_price_market_order_returns_none(self, dca_strategy_long, mock_order_manager):
        """Test that market order batch returns None for limit price."""
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Batch 1 is MARKET, should return None
        limit_price = dca_strategy_long.calculate_limit_price(batch_index=1)
        assert limit_price is None


# ============================================================
# Test 3: G-003 Pre-placing all limit orders
# ============================================================
class TestPrePlacingLimitOrders:

    @pytest.mark.asyncio
    async def test_place_all_limit_orders(self, dca_strategy_long, mock_order_manager):
        """Test G-003: Pre-place all limit orders after first batch filled."""
        # Setup first execution
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Place all limit orders
        placed = await dca_strategy_long.place_all_limit_orders(mock_order_manager)

        # Verify 2 orders were placed (batch 2 and 3)
        assert len(placed) == 2
        assert placed[0]["batch_index"] == 2
        assert placed[0]["limit_price"] == Decimal("98.00")
        assert placed[1]["batch_index"] == 3
        assert placed[1]["limit_price"] == Decimal("96.00")

        # Verify place_limit_order was called correctly
        assert mock_order_manager.place_limit_order.call_count == 2

        # Verify pending batches
        assert len(dca_strategy_long.state.pending_batches) == 2

    @pytest.mark.asyncio
    async def test_place_all_limit_orders_raises_without_first_exec(self, dca_strategy_long, mock_order_manager):
        """Test that placing limit orders without first execution raises error."""
        with pytest.raises(ValueError, match="必须先记录第一批成交价"):
            await dca_strategy_long.place_all_limit_orders(mock_order_manager)

    @pytest.mark.asyncio
    async def test_place_all_limit_orders_disabled(self, mock_order_manager):
        """Test that pre-placing can be disabled."""
        config = DcaConfig(
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
            place_all_orders_upfront=False,  # Disabled
            total_amount=Decimal("1000"),
        )
        strategy = DcaStrategy(
            config=config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
        )

        await strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        strategy.record_first_execution(Decimal("500"), Decimal("100"))

        placed = await strategy.place_all_limit_orders(mock_order_manager)

        # Should return empty list when disabled
        assert placed == []
        mock_order_manager.place_limit_order.assert_not_called()


# ============================================================
# Test 4: Average cost calculation
# ============================================================
class TestAverageCostCalculation:

    @pytest.mark.asyncio
    async def test_average_cost_after_all_batches(self, dca_strategy_long, mock_order_manager):
        """Test average cost calculation after all batches filled."""
        # Setup first execution
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Simulate batch 2 execution
        dca_strategy_long.record_batch_execution(
            batch_index=2,
            executed_qty=Decimal("300"),
            executed_price=Decimal("98"),
        )

        # Simulate batch 3 execution
        dca_strategy_long.record_batch_execution(
            batch_index=3,
            executed_qty=Decimal("200"),
            executed_price=Decimal("96"),
        )

        # Calculate average cost
        # Total qty = 500 + 300 + 200 = 1000
        # Total value = 500*100 + 300*98 + 200*96 = 50000 + 29400 + 19200 = 98600
        # Average cost = 98600 / 1000 = 98.6
        assert dca_strategy_long.state.total_executed_qty == Decimal("1000")
        assert dca_strategy_long.state.total_executed_value == Decimal("98600")
        assert dca_strategy_long.get_average_cost() == Decimal("98.6")

    @pytest.mark.asyncio
    async def test_average_cost_zero_qty(self, dca_strategy_long):
        """Test average cost returns 0 when no quantity executed."""
        assert dca_strategy_long.get_average_cost() == Decimal("0")


# ============================================================
# Test 5: Batch state tracking
# ============================================================
class TestBatchStateTracking:

    @pytest.mark.asyncio
    async def test_is_completed(self, dca_strategy_long, mock_order_manager):
        """Test completion status tracking."""
        # Initially not completed
        assert dca_strategy_long.is_completed() is False

        # Execute first batch
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Still not completed (only 1 of 3 batches)
        assert dca_strategy_long.is_completed() is False

        # Execute remaining batches
        dca_strategy_long.record_batch_execution(2, Decimal("300"), Decimal("98"))
        dca_strategy_long.record_batch_execution(3, Decimal("200"), Decimal("96"))

        # Now completed
        assert dca_strategy_long.is_completed() is True

    @pytest.mark.asyncio
    async def test_get_execution_summary(self, dca_strategy_long, mock_order_manager):
        """Test execution summary generation."""
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        summary = dca_strategy_long.get_execution_summary()

        assert summary["signal_id"] == "signal_001"
        assert summary["symbol"] == "BTC/USDT:USDT"
        assert summary["direction"] == "LONG"
        assert summary["total_batches"] == 3
        assert summary["executed_batches"] == 1
        assert summary["pending_batches"] == 0
        assert summary["total_executed_qty"] == "500"
        assert summary["total_executed_value"] == "50000"
        assert summary["average_cost"] == "100"
        assert summary["first_exec_price"] == "100"
        assert summary["is_completed"] is False


# ============================================================
# Test 6: Boundary conditions
# ============================================================
class TestBoundaryConditions:

    @pytest.mark.asyncio
    async def test_custom_batch_triggers(self, mock_order_manager):
        """Test with custom batch trigger configuration."""
        config = DcaConfig(
            entry_batches=3,
            entry_ratios=[Decimal("0.4"), Decimal("0.35"), Decimal("0.25")],
            place_all_orders_upfront=True,
            total_amount=Decimal("1000"),
            batch_triggers=[
                DcaBatchTrigger(batch_index=1, order_type=OrderType.MARKET, ratio=Decimal("0.4")),
                DcaBatchTrigger(batch_index=2, order_type=OrderType.LIMIT, ratio=Decimal("0.35"), trigger_drop_percent=Decimal("-1.5")),
                DcaBatchTrigger(batch_index=3, order_type=OrderType.LIMIT, ratio=Decimal("0.25"), trigger_drop_percent=Decimal("-3.0")),
            ],
        )
        strategy = DcaStrategy(
            config=config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
        )

        await strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        strategy.record_first_execution(Decimal("400"), Decimal("100"))

        # Verify custom limit prices
        # Batch 2: 100 * (1 - 0.015) = 98.5
        limit_price_2 = strategy.calculate_limit_price(batch_index=2)
        assert limit_price_2 == Decimal("98.50")

        # Batch 3: 100 * (1 - 0.03) = 97
        limit_price_3 = strategy.calculate_limit_price(batch_index=3)
        assert limit_price_3 == Decimal("97.00")

    def test_config_validation_invalid_ratios(self):
        """Test config validation rejects invalid ratios."""
        with pytest.raises(ValueError, match="总和必须为 1.0"):
            DcaConfig(
                entry_batches=3,
                entry_ratios=[Decimal("0.5"), Decimal("0.3")],  # Sum = 0.8, not 1.0
            )

    def test_config_validation_batch_count_mismatch(self):
        """Test config validation for batch count."""
        # Should not raise for valid count
        config = DcaConfig(entry_batches=3, entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")])
        assert config.entry_batches == 3

    def test_config_validation_invalid_batch_count(self):
        """Test config validation rejects invalid batch count."""
        # Pydantic validates ge=2 constraint before custom validator
        with pytest.raises(ValueError):  # Pydantic will raise ValueError for ge=2 constraint
            DcaConfig(entry_batches=1, entry_ratios=[Decimal("1.0")])

        with pytest.raises(ValueError):
            DcaConfig(entry_batches=6, entry_ratios=[Decimal("0.2")] * 6)

    def test_state_calculate_batch_qty(self, default_dca_config):
        """Test batch quantity calculation."""
        state = DcaState(
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_batches=3,
            entry_ratios=default_dca_config.entry_ratios,
            total_amount=Decimal("1000"),
        )

        assert state.calculate_batch_qty(Decimal("0.5")) == Decimal("500")
        assert state.calculate_batch_qty(Decimal("0.3")) == Decimal("300")
        assert state.calculate_batch_qty(Decimal("0.2")) == Decimal("200")

    @pytest.mark.asyncio
    async def test_record_batch_execution_moves_from_pending_to_executed(self, dca_strategy_long, mock_order_manager):
        """Test that recording execution moves batch from pending to executed."""
        # Setup
        await dca_strategy_long.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        dca_strategy_long.record_first_execution(Decimal("500"), Decimal("100"))

        # Place limit orders
        await dca_strategy_long.place_all_limit_orders(mock_order_manager)

        # Verify pending batches
        assert len(dca_strategy_long.state.pending_batches) == 2
        assert len(dca_strategy_long.state.executed_batches) == 1

        # Record batch 2 execution
        dca_strategy_long.record_batch_execution(
            batch_index=2,
            executed_qty=Decimal("300"),
            executed_price=Decimal("98"),
        )

        # Verify moved to executed
        assert len(dca_strategy_long.state.pending_batches) == 1
        assert len(dca_strategy_long.state.executed_batches) == 2

        batch_2 = next(b for b in dca_strategy_long.state.executed_batches if b.batch_index == 2)
        assert batch_2.executed_qty == Decimal("300")
        assert batch_2.executed_price == Decimal("98")
        assert batch_2.status == "filled"


# ============================================================
# Test 7: 5-batch configuration
# ============================================================
class TestFiveBatchConfiguration:

    @pytest.mark.asyncio
    async def test_five_batch_execution(self, mock_order_manager):
        """Test DCA with 5 batches."""
        config = DcaConfig(
            entry_batches=5,
            entry_ratios=[Decimal("0.3"), Decimal("0.25"), Decimal("0.2"), Decimal("0.15"), Decimal("0.1")],
            place_all_orders_upfront=True,
            total_amount=Decimal("1000"),
        )
        strategy = DcaStrategy(
            config=config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
        )

        # Execute first batch
        await strategy.execute_first_batch(
            order_manager=mock_order_manager,
            symbol="BTC/USDT:USDT",
            total_amount=Decimal("1000"),
        )
        strategy.record_first_execution(Decimal("300"), Decimal("100"))

        # Place all limit orders
        placed = await strategy.place_all_limit_orders(mock_order_manager)

        # Verify 4 limit orders placed (batches 2-5)
        assert len(placed) == 4

        # Verify limit prices
        # Batch 2: -2% → 98
        assert placed[0]["batch_index"] == 2
        assert placed[0]["limit_price"] == Decimal("98.00")

        # Batch 3: -4% → 96
        assert placed[1]["batch_index"] == 3
        assert placed[1]["limit_price"] == Decimal("96.00")

        # Batch 4: -6% → 94
        assert placed[2]["batch_index"] == 4
        assert placed[2]["limit_price"] == Decimal("94.00")

        # Batch 5: -8% → 92
        assert placed[3]["batch_index"] == 5
        assert placed[3]["limit_price"] == Decimal("92.00")


# ============================================================
# Test 8: Default batch triggers auto-generation
# ============================================================
class TestDefaultBatchTriggers:

    def test_default_triggers_generated(self, default_dca_config):
        """Test that default batch triggers are auto-generated."""
        strategy = DcaStrategy(
            config=default_dca_config,
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
        )

        # Verify triggers were generated
        assert len(strategy.config.batch_triggers) == 3

        # Batch 1: MARKET
        assert strategy.config.batch_triggers[0].order_type == OrderType.MARKET
        assert strategy.config.batch_triggers[0].ratio == Decimal("0.5")

        # Batch 2: LIMIT with -2% drop
        assert strategy.config.batch_triggers[1].order_type == OrderType.LIMIT
        assert strategy.config.batch_triggers[1].trigger_drop_percent == Decimal("-2.0")
        assert strategy.config.batch_triggers[1].ratio == Decimal("0.3")

        # Batch 3: LIMIT with -4% drop
        assert strategy.config.batch_triggers[2].order_type == OrderType.LIMIT
        assert strategy.config.batch_triggers[2].trigger_drop_percent == Decimal("-4.0")
        assert strategy.config.batch_triggers[2].ratio == Decimal("0.2")


# ============================================================
# Test 9: DcaState model tests
# ============================================================
class TestDcaStateModel:

    def test_average_cost_property(self):
        """Test average_cost property calculation."""
        state = DcaState(
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
            total_executed_qty=Decimal("1000"),
            total_executed_value=Decimal("98600"),
        )

        assert state.average_cost == Decimal("98.6")

    def test_average_cost_zero(self):
        """Test average_cost returns 0 when no executions."""
        state = DcaState(
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
        )

        assert state.average_cost == Decimal("0")

    def test_calculate_limit_price_method(self):
        """Test state's calculate_limit_price method."""
        state = DcaState(
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
            first_exec_price=Decimal("100"),
        )

        trigger = DcaBatchTrigger(
            batch_index=2,
            order_type=OrderType.LIMIT,
            ratio=Decimal("0.3"),
            trigger_drop_percent=Decimal("-2.0"),
        )

        limit_price = state.calculate_limit_price(batch_index=2, batch_trigger=trigger)
        assert limit_price == Decimal("98.00")


# ============================================================
# Test 10: DcaConfig validation tests
# ============================================================
class TestDcaConfigValidation:

    def test_valid_config(self):
        """Test valid config is accepted."""
        config = DcaConfig(
            entry_batches=3,
            entry_ratios=[Decimal("0.5"), Decimal("0.3"), Decimal("0.2")],
        )
        assert config.entry_batches == 3
        assert config.place_all_orders_upfront is True  # Default

    def test_min_batch_count(self):
        """Test minimum batch count (2)."""
        config = DcaConfig(
            entry_batches=2,
            entry_ratios=[Decimal("0.5"), Decimal("0.5")],
        )
        assert config.entry_batches == 2

    def test_max_batch_count(self):
        """Test maximum batch count (5)."""
        config = DcaConfig(
            entry_batches=5,
            entry_ratios=[Decimal("0.2")] * 5,
        )
        assert config.entry_batches == 5

    def test_invalid_ratio_zero(self):
        """Test that zero ratio is rejected in batch trigger."""
        # entry_ratios doesn't validate individual ratios, but DcaBatchTrigger does
        # Test with DcaBatchTrigger instead - Pydantic Field validation raises ValidationError
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="greater_than"):
            DcaBatchTrigger(
                batch_index=1,
                order_type=OrderType.MARKET,
                ratio=Decimal("0"),
            )

    def test_invalid_ratio_negative(self):
        """Test that negative ratio is rejected in batch trigger."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="greater_than"):
            DcaBatchTrigger(
                batch_index=1,
                order_type=OrderType.MARKET,
                ratio=Decimal("-0.1"),
            )
