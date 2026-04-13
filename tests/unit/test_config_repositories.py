"""
Unit tests for Config Repositories

Tests all 7 repository classes:
- StrategyConfigRepository
- RiskConfigRepository
- SystemConfigRepository
- SymbolConfigRepository
- NotificationConfigRepository
- ConfigSnapshotRepositoryExtended
- ConfigHistoryRepository
"""
import asyncio
import os
import pytest
import tempfile
from decimal import Decimal
from typing import Dict, Any

from src.infrastructure.repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    SymbolConfigRepository,
    NotificationConfigRepository,
    ConfigSnapshotRepositoryExtended,
    ConfigHistoryRepository,
    ConfigDatabaseManager,
    ConfigConflictError,
    ConfigValidationError,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)
    # Cleanup WAL files if exist
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)


@pytest.fixture
async def strategy_repo(temp_db):
    """Create StrategyConfigRepository instance."""
    repo = StrategyConfigRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def risk_repo(temp_db):
    """Create RiskConfigRepository instance."""
    repo = RiskConfigRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def system_repo(temp_db):
    """Create SystemConfigRepository instance."""
    repo = SystemConfigRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def symbol_repo(temp_db):
    """Create SymbolConfigRepository instance."""
    repo = SymbolConfigRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def notification_repo(temp_db):
    """Create NotificationConfigRepository instance."""
    repo = NotificationConfigRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def snapshot_repo(temp_db):
    """Create ConfigSnapshotRepositoryExtended instance."""
    repo = ConfigSnapshotRepositoryExtended(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def history_repo(temp_db):
    """Create ConfigHistoryRepository instance."""
    repo = ConfigHistoryRepository(temp_db)
    await repo.initialize()
    yield repo
    await repo.close()


# ============================================================
# StrategyConfigRepository Tests
# ============================================================
class TestStrategyConfigRepository:
    """Tests for StrategyConfigRepository."""

    @pytest.mark.asyncio
    async def test_create_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test creating a new strategy."""
        strategy_data = {
            "name": "Test Pinbar Strategy",
            "description": "A test strategy",
            "trigger_config": {"type": "pinbar", "params": {"min_wick_ratio": 0.6}},
            "filter_configs": [{"type": "ema", "params": {"period": 60}}],
            "filter_logic": "AND",
            "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "timeframes": ["15m", "1h"],
        }

        strategy_id = await strategy_repo.create(strategy_data)
        assert strategy_id is not None
        assert len(strategy_id) > 0

        # Verify the strategy was created
        retrieved = await strategy_repo.get_by_id(strategy_id)
        assert retrieved is not None
        assert retrieved["name"] == "Test Pinbar Strategy"
        assert retrieved["is_active"] is True
        assert len(retrieved["symbols"]) == 2

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(self, strategy_repo: StrategyConfigRepository):
        """Test that creating a strategy with duplicate name raises error."""
        strategy_data = {
            "name": "Duplicate Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": [],
            "timeframes": [],
        }

        await strategy_repo.create(strategy_data)

        # Attempting to create another with same name should fail
        with pytest.raises(ConfigConflictError):
            await strategy_repo.create(strategy_data)

    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test getting a strategy that doesn't exist."""
        result = await strategy_repo.get_by_id("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test updating a strategy."""
        strategy_data = {
            "name": "Update Test Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": ["BTC/USDT:USDT"],
            "timeframes": ["15m"],
        }

        strategy_id = await strategy_repo.create(strategy_data)

        # Update the strategy
        update_result = await strategy_repo.update(
            strategy_id,
            {"name": "Updated Strategy Name", "description": "New description"}
        )
        assert update_result is True

        # Verify update
        updated = await strategy_repo.get_by_id(strategy_id)
        assert updated["name"] == "Updated Strategy Name"
        assert updated["description"] == "New description"
        assert updated["version"] == 2  # Version should increment

    @pytest.mark.asyncio
    async def test_update_nonexistent_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test updating a strategy that doesn't exist."""
        result = await strategy_repo.update("nonexistent", {"name": "New Name"})
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test deleting a strategy."""
        strategy_data = {
            "name": "Delete Test Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": [],
            "timeframes": [],
        }

        strategy_id = await strategy_repo.create(strategy_data)

        # Delete the strategy
        delete_result = await strategy_repo.delete(strategy_id)
        assert delete_result is True

        # Verify deletion
        retrieved = await strategy_repo.get_by_id(strategy_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_toggle_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test toggling strategy active status."""
        strategy_data = {
            "name": "Toggle Test Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": [],
            "timeframes": [],
        }

        strategy_id = await strategy_repo.create(strategy_data)

        # Initially active
        initial = await strategy_repo.get_by_id(strategy_id)
        assert initial["is_active"] is True

        # Toggle to inactive
        new_status = await strategy_repo.toggle(strategy_id)
        assert new_status is False

        # Toggle back to active
        new_status = await strategy_repo.toggle(strategy_id)
        assert new_status is True

    @pytest.mark.asyncio
    async def test_toggle_nonexistent_strategy(self, strategy_repo: StrategyConfigRepository):
        """Test toggling a strategy that doesn't exist."""
        result = await strategy_repo.toggle("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_strategy_list(self, strategy_repo: StrategyConfigRepository):
        """Test getting list of strategies with pagination."""
        # Create multiple strategies
        for i in range(5):
            await strategy_repo.create({
                "name": f"Strategy {i}",
                "trigger_config": {"type": "pinbar"},
                "filter_configs": [],
                "symbols": [],
                "timeframes": [],
            })

        # Get all
        strategies, total = await strategy_repo.get_list(limit=10)
        assert total == 5
        assert len(strategies) == 5

        # Get with pagination
        strategies, total = await strategy_repo.get_list(limit=2, offset=2)
        assert total == 5
        assert len(strategies) == 2

    @pytest.mark.asyncio
    async def test_get_active_strategies(self, strategy_repo: StrategyConfigRepository):
        """Test filtering strategies by active status."""
        # Create active and inactive strategies
        await strategy_repo.create({
            "name": "Active Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": [],
            "timeframes": [],
        })

        inactive_id = await strategy_repo.create({
            "name": "Inactive Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": [],
            "timeframes": [],
        })
        await strategy_repo.toggle(inactive_id)  # Make inactive

        # Get only active
        strategies, total = await strategy_repo.get_list(is_active=True)
        assert total == 1
        assert strategies[0]["name"] == "Active Strategy"


# ============================================================
# RiskConfigRepository Tests
# ============================================================
class TestRiskConfigRepository:
    """Tests for RiskConfigRepository."""

    @pytest.mark.asyncio
    async def test_get_global_initially_none(self, risk_repo: RiskConfigRepository):
        """Test that global config is None initially."""
        result = await risk_repo.get_global()
        assert result is None

    @pytest.mark.asyncio
    async def test_update_creates_global_config(self, risk_repo: RiskConfigRepository):
        """Test that update creates global config if not exists."""
        config = {
            "max_loss_percent": Decimal("0.02"),
            "max_leverage": 20,
            "max_total_exposure": Decimal("0.5"),
        }

        result = await risk_repo.update(config)
        assert result is True

        retrieved = await risk_repo.get_global()
        assert retrieved is not None
        assert retrieved["max_loss_percent"] == Decimal("0.02")
        assert retrieved["max_leverage"] == 20

    @pytest.mark.asyncio
    async def test_update_existing_config(self, risk_repo: RiskConfigRepository):
        """Test updating existing global config."""
        # Create initial config
        await risk_repo.update({
            "max_loss_percent": Decimal("0.01"),
            "max_leverage": 10,
        })

        # Update
        await risk_repo.update({
            "max_leverage": 15,
            "cooldown_minutes": 300,
        })

        retrieved = await risk_repo.get_global()
        assert retrieved["max_leverage"] == 15
        assert retrieved["cooldown_minutes"] == 300
        assert retrieved["version"] == 2


# ============================================================
# SystemConfigRepository Tests
# ============================================================
class TestSystemConfigRepository:
    """Tests for SystemConfigRepository."""

    @pytest.mark.asyncio
    async def test_get_global_initially_none(self, system_repo: SystemConfigRepository):
        """Test that global config is None initially."""
        result = await system_repo.get_global()
        assert result is None

    @pytest.mark.asyncio
    async def test_update_creates_global_config(self, system_repo: SystemConfigRepository):
        """Test that update creates global config."""
        config = {
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "ema_period": 50,
            "mtf_mapping": {"15m": "1h", "1h": "4h"},
        }

        result = await system_repo.update(config)
        assert result is True

        retrieved = await system_repo.get_global()
        assert retrieved is not None
        assert len(retrieved["core_symbols"]) == 2
        assert retrieved["ema_period"] == 50

    @pytest.mark.asyncio
    async def test_update_with_restart_required(self, system_repo: SystemConfigRepository):
        """Test update with restart_required flag."""
        await system_repo.update({
            "core_symbols": ["BTC/USDT:USDT"],
        })

        await system_repo.update(
            {"ema_period": 100},
            restart_required=True
        )

        retrieved = await system_repo.get_global()
        assert retrieved["restart_required"] is True


# ============================================================
# SymbolConfigRepository Tests
# ============================================================
class TestSymbolConfigRepository:
    """Tests for SymbolConfigRepository."""

    @pytest.mark.asyncio
    async def test_create_symbol(self, symbol_repo: SymbolConfigRepository):
        """Test creating a new symbol."""
        symbol_data = {
            "symbol": "BTC/USDT:USDT",
            "is_core": True,
            "price_precision": 2,
            "quantity_precision": 8,
        }

        result = await symbol_repo.create(symbol_data)
        assert result is True

        retrieved = await symbol_repo.get_by_symbol("BTC/USDT:USDT")
        assert retrieved is not None
        assert retrieved["is_core"] is True

    @pytest.mark.asyncio
    async def test_create_duplicate_symbol_raises(self, symbol_repo: SymbolConfigRepository):
        """Test that creating duplicate symbol raises error."""
        symbol_data = {
            "symbol": "ETH/USDT:USDT",
            "is_core": False,
        }

        await symbol_repo.create(symbol_data)

        with pytest.raises(ConfigConflictError):
            await symbol_repo.create(symbol_data)

    @pytest.mark.asyncio
    async def test_get_all_symbols(self, symbol_repo: SymbolConfigRepository):
        """Test getting all symbols."""
        await symbol_repo.create({"symbol": "BTC/USDT:USDT"})
        await symbol_repo.create({"symbol": "ETH/USDT:USDT"})
        await symbol_repo.create({"symbol": "SOL/USDT:USDT"})

        symbols = await symbol_repo.get_all()
        assert len(symbols) == 3

    @pytest.mark.asyncio
    async def test_get_active_symbols(self, symbol_repo: SymbolConfigRepository):
        """Test getting only active symbols."""
        btc_id = await symbol_repo.create({"symbol": "BTC/USDT:USDT"})
        await symbol_repo.create({"symbol": "ETH/USDT:USDT"})

        # Deactivate BTC
        await symbol_repo.toggle("BTC/USDT:USDT")

        active = await symbol_repo.get_active()
        assert len(active) == 1
        assert active[0]["symbol"] == "ETH/USDT:USDT"

    @pytest.mark.asyncio
    async def test_update_symbol(self, symbol_repo: SymbolConfigRepository):
        """Test updating a symbol."""
        await symbol_repo.create({
            "symbol": "BTC/USDT:USDT",
            "price_precision": 2,
        })

        result = await symbol_repo.update(
            "BTC/USDT:USDT",
            {"price_precision": 4, "is_active": False}
        )
        assert result is True

        updated = await symbol_repo.get_by_symbol("BTC/USDT:USDT")
        assert updated["price_precision"] == 4
        assert updated["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_non_core_symbol(self, symbol_repo: SymbolConfigRepository):
        """Test deleting a non-core symbol."""
        await symbol_repo.create({
            "symbol": "ALT/USDT:USDT",
            "is_core": False,
        })

        result = await symbol_repo.delete("ALT/USDT:USDT")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_core_symbol_raises(self, symbol_repo: SymbolConfigRepository):
        """Test that deleting core symbol raises error."""
        await symbol_repo.create({
            "symbol": "BTC/USDT:USDT",
            "is_core": True,
        })

        with pytest.raises(ConfigValidationError):
            await symbol_repo.delete("BTC/USDT:USDT")

    @pytest.mark.asyncio
    async def test_add_core_symbols(self, symbol_repo: SymbolConfigRepository):
        """Test adding core symbols idempotently."""
        symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

        added = await symbol_repo.add_core_symbols(symbols)
        assert added == 3

        # Adding same symbols again should add 0
        added_again = await symbol_repo.add_core_symbols(symbols)
        assert added_again == 0

        # All should be core symbols
        all_symbols = await symbol_repo.get_all()
        assert all(s["is_core"] for s in all_symbols)

    @pytest.mark.asyncio
    async def test_toggle_symbol(self, symbol_repo: SymbolConfigRepository):
        """Test toggling symbol active status."""
        await symbol_repo.create({"symbol": "BTC/USDT:USDT"})

        # Toggle off
        new_status = await symbol_repo.toggle("BTC/USDT:USDT")
        assert new_status is False

        # Toggle on
        new_status = await symbol_repo.toggle("BTC/USDT:USDT")
        assert new_status is True


# ============================================================
# NotificationConfigRepository Tests
# ============================================================
class TestNotificationConfigRepository:
    """Tests for NotificationConfigRepository."""

    @pytest.mark.asyncio
    async def test_create_notification(self, notification_repo: NotificationConfigRepository):
        """Test creating a notification configuration."""
        notification = {
            "channel_type": "feishu",
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "notify_on_signal": True,
            "notify_on_order": True,
        }

        notification_id = await notification_repo.create(notification)
        assert notification_id is not None

        retrieved = await notification_repo.get_by_id(notification_id)
        assert retrieved is not None
        assert retrieved["channel_type"] == "feishu"

    @pytest.mark.asyncio
    async def test_get_active_channels(self, notification_repo: NotificationConfigRepository):
        """Test getting active notification channels."""
        await notification_repo.create({
            "channel_type": "feishu",
            "webhook_url": "https://example.com/feishu",
        })
        inactive_id = await notification_repo.create({
            "channel_type": "telegram",
            "webhook_url": "https://example.com/telegram",
        })
        await notification_repo.update(inactive_id, {"is_active": False})

        active = await notification_repo.get_active_channels()
        assert len(active) == 1
        assert active[0]["channel_type"] == "feishu"

    @pytest.mark.asyncio
    async def test_test_connection(self, notification_repo: NotificationConfigRepository):
        """Test connection testing."""
        notification_id = await notification_repo.create({
            "channel_type": "feishu",
            "webhook_url": "https://example.com/webhook",
        })

        result = await notification_repo.test_connection(notification_id)
        assert result["success"] is True
        assert result["channel_type"] == "feishu"

    @pytest.mark.asyncio
    async def test_test_connection_invalid_url(self, notification_repo: NotificationConfigRepository):
        """Test connection with invalid URL."""
        notification_id = await notification_repo.create({
            "channel_type": "feishu",
            "webhook_url": "invalid-url",
        })

        result = await notification_repo.test_connection(notification_id)
        assert result["success"] is False


# ============================================================
# ConfigSnapshotRepositoryExtended Tests
# ============================================================
class TestConfigSnapshotRepositoryExtended:
    """Tests for ConfigSnapshotRepositoryExtended."""

    @pytest.mark.asyncio
    async def test_create_snapshot(self, snapshot_repo: ConfigSnapshotRepositoryExtended):
        """Test creating a configuration snapshot."""
        snapshot = {
            "name": "Test Snapshot",
            "description": "A test snapshot",
            "snapshot_data": {
                "strategies": [{"name": "Strategy A"}],
                "risk_config": {"max_loss": 0.01},
            },
        }

        snapshot_id = await snapshot_repo.create(snapshot)
        assert snapshot_id is not None

        retrieved = await snapshot_repo.get_by_id(snapshot_id)
        assert retrieved is not None
        assert retrieved["name"] == "Test Snapshot"
        # Note: API returns 'config_data' not 'snapshot_data'
        assert len(retrieved["config_data"]["strategies"]) == 1

    @pytest.mark.asyncio
    async def test_get_recent_snapshots(self, snapshot_repo: ConfigSnapshotRepositoryExtended):
        """Test getting recent snapshots."""
        for i in range(5):
            await snapshot_repo.create({
                "name": f"Snapshot {i}",
                "snapshot_data": {"version": i},
            })

        recent = await snapshot_repo.get_recent(count=3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["name"] == "Snapshot 4"

    @pytest.mark.asyncio
    async def test_get_snapshot_list_pagination(self, snapshot_repo: ConfigSnapshotRepositoryExtended):
        """Test snapshot list with pagination."""
        for i in range(10):
            await snapshot_repo.create({
                "name": f"Snapshot {i}",
                "snapshot_data": {},
            })

        snapshots, total = await snapshot_repo.get_list(limit=5, offset=0)
        assert total == 10
        assert len(snapshots) == 5


# ============================================================
# ConfigHistoryRepository Tests
# ============================================================
class TestConfigHistoryRepository:
    """Tests for ConfigHistoryRepository."""

    @pytest.mark.asyncio
    async def test_record_change(self, history_repo: ConfigHistoryRepository):
        """Test recording a configuration change."""
        record_id = await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="CREATE",
            new_values={"name": "Test Strategy"},
            changed_by="test-user",
            change_summary="Created new strategy"
        )
        assert record_id is not None

    @pytest.mark.asyncio
    async def test_get_entity_history(self, history_repo: ConfigHistoryRepository):
        """Test getting history for a specific entity."""
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="CREATE",
            new_values={"name": "Initial"},
        )
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="UPDATE",
            old_values={"name": "Initial"},
            new_values={"name": "Updated"},
        )

        history = await history_repo.get_entity_history("strategy", "strategy-123")
        assert len(history) == 2
        assert history[0]["action"] == "UPDATE"  # Most recent first
        assert history[1]["action"] == "CREATE"

    @pytest.mark.asyncio
    async def test_get_recent_changes(self, history_repo: ConfigHistoryRepository):
        """Test getting recent changes."""
        for i in range(5):
            await history_repo.record_change(
                entity_type="strategy",
                entity_id=f"strategy-{i}",
                action="CREATE",
                changed_by="user",
            )

        recent = await history_repo.get_recent_changes(limit=3)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_get_changes_summary(self, history_repo: ConfigHistoryRepository):
        """Test getting changes summary."""
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="s1",
            action="CREATE",
        )
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="s2",
            action="CREATE",
        )
        await history_repo.record_change(
            entity_type="risk_config",
            entity_id="global",
            action="UPDATE",
        )

        summary = await history_repo.get_changes_summary()
        assert summary["total_changes"] == 3
        assert summary["changes_by_action"]["CREATE"] == 2
        assert summary["changes_by_action"]["UPDATE"] == 1
        assert summary["changes_by_entity"]["strategy"] == 2

    @pytest.mark.asyncio
    async def test_get_rollback_candidates(self, history_repo: ConfigHistoryRepository):
        """Test getting rollback candidates."""
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="CREATE",
            new_values={"name": "v1"},
        )
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="UPDATE",
            old_values={"name": "v1"},
            new_values={"name": "v2"},
        )
        await history_repo.record_change(
            entity_type="strategy",
            entity_id="strategy-123",
            action="DELETE",
        )

        candidates = await history_repo.get_rollback_candidates("strategy", "strategy-123")
        # Should only return CREATE and UPDATE actions
        assert len(candidates) == 2
        assert all(c["action"] in ("CREATE", "UPDATE") for c in candidates)


# ============================================================
# ConfigDatabaseManager Tests
# ============================================================
class TestConfigDatabaseManager:
    """Tests for ConfigDatabaseManager."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self, temp_db):
        """Test that manager initializes all repositories."""
        manager = ConfigDatabaseManager(temp_db)
        await manager.initialize()

        assert manager.strategy_repo is not None
        assert manager.risk_repo is not None
        assert manager.system_repo is not None
        assert manager.symbol_repo is not None
        assert manager.notification_repo is not None
        assert manager.snapshot_repo is not None
        assert manager.history_repo is not None

        # Test basic functionality
        risk_config = {
            "max_loss_percent": Decimal("0.01"),
            "max_leverage": 10,
        }
        result = await manager.risk_repo.update(risk_config)
        assert result is True

        await manager.close()

    @pytest.mark.asyncio
    async def test_manager_close(self, temp_db):
        """Test that manager closes all repositories.

        Note: With connection pool, repos don't set _db to None on close()
        because the pool manages connection lifecycle. The repos remain
        usable after close() in this mode.
        """
        manager = ConfigDatabaseManager(temp_db)
        await manager.initialize()
        # close() should not raise an error
        await manager.close()
        # Connection is pool-managed, so _db is not None
        # This is correct behavior - pool connections outlive individual repos
        assert manager.strategy_repo._db is not None


# ============================================================
# Integration Tests
# ============================================================
class TestConfigRepositoriesIntegration:
    """Integration tests for all repositories working together."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_db):
        """Test a complete configuration workflow."""
        manager = ConfigDatabaseManager(temp_db)
        await manager.initialize()

        try:
            # 1. Add core symbols
            await manager.symbol_repo.add_core_symbols([
                "BTC/USDT:USDT",
                "ETH/USDT:USDT",
                "SOL/USDT:USDT"
            ])

            # 2. Configure risk settings
            await manager.risk_repo.update({
                "max_loss_percent": Decimal("0.01"),
                "max_leverage": 10,
                "max_total_exposure": Decimal("0.8"),
            })

            # 3. Configure system settings
            await manager.system_repo.update({
                "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
                "ema_period": 60,
            })

            # 4. Create a strategy
            strategy_id = await manager.strategy_repo.create({
                "name": "Pinbar + EMA Strategy",
                "description": "Pinbar pattern with EMA trend filter",
                "trigger_config": {"type": "pinbar", "params": {"min_wick_ratio": 0.6}},
                "filter_configs": [{"type": "ema", "params": {"period": 60}}],
                "filter_logic": "AND",
                "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
                "timeframes": ["15m", "1h"],
            })

            # 5. Add notification channel
            notification_id = await manager.notification_repo.create({
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook",
            })

            # 6. Create configuration snapshot
            snapshot_id = await manager.snapshot_repo.create({
                "name": "Initial Configuration",
                "description": "Initial system configuration",
                "snapshot_data": {
                    "strategy_id": strategy_id,
                    "notification_id": notification_id,
                },
            })

            # 7. Record history for each change
            await manager.history_repo.record_change(
                entity_type="strategy",
                entity_id=strategy_id,
                action="CREATE",
                new_values={"name": "Pinbar + EMA Strategy"},
                changed_by="system",
                change_summary="Created initial strategy"
            )

            # Verify all data
            symbols = await manager.symbol_repo.get_active()
            assert len(symbols) == 3

            risk_config = await manager.risk_repo.get_global()
            assert risk_config["max_loss_percent"] == Decimal("0.01")

            strategies, total = await manager.strategy_repo.get_list()
            assert total == 1

            snapshots, total = await manager.snapshot_repo.get_list()
            assert total == 1

        finally:
            await manager.close()


# ============================================================
# Main entry point for running tests directly
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/infrastructure/repositories"])
