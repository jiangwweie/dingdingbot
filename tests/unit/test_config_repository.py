"""
Unit tests for ConfigRepository - SQLite persistence for configuration management.
"""
import pytest
import json
import tempfile
import os
from decimal import Decimal

from src.infrastructure.config_repository import ConfigRepository


class TestConfigRepository:
    """Test ConfigRepository CRUD operations."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance with temporary database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        yield repo

        # Cleanup
        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    # ==================== Strategy Config Tests ====================

    @pytest.mark.asyncio
    async def test_create_strategy(self, repository):
        """Test creating a new strategy configuration."""
        triggers = [{"type": "pinbar", "params": {"min_wick_ratio": 0.6}}]
        filters = [{"type": "ema", "period": 60}]
        apply_to = ["BTC/USDT:USDT:15m"]

        strategy_id = await repository.create_strategy(
            name="Test Strategy",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
            description="Test strategy for unit testing",
        )

        assert strategy_id is not None
        assert strategy_id > 0

        # Retrieve and verify
        strategy = await repository.get_strategy(strategy_id)
        assert strategy is not None
        assert strategy["name"] == "Test Strategy"
        assert strategy["description"] == "Test strategy for unit testing"
        assert strategy["triggers"] == triggers
        assert strategy["filters"] == filters
        assert strategy["apply_to"] == apply_to
        assert strategy["is_active"] == 0

    @pytest.mark.asyncio
    async def test_get_strategy_by_name(self, repository):
        """Test retrieving strategy by name."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        await repository.create_strategy(
            name="Unique Strategy",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        strategy = await repository.get_strategy_by_name("Unique Strategy")
        assert strategy is not None
        assert strategy["name"] == "Unique Strategy"

        # Non-existent strategy
        strategy = await repository.get_strategy_by_name("Non Existent")
        assert strategy is None

    @pytest.mark.asyncio
    async def test_activate_strategy(self, repository):
        """Test activating a strategy."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        # Create two strategies
        id1 = await repository.create_strategy(
            name="Strategy 1",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )
        id2 = await repository.create_strategy(
            name="Strategy 2",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        # Activate strategy 1
        await repository.activate_strategy(id1)

        # Strategy 1 should be active
        strategy1 = await repository.get_strategy(id1)
        assert strategy1["is_active"] == 1

        # Strategy 2 should be inactive (due to trigger constraint)
        strategy2 = await repository.get_strategy(id2)
        assert strategy2["is_active"] == 0

    @pytest.mark.asyncio
    async def test_update_strategy(self, repository):
        """Test updating a strategy configuration."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        strategy_id = await repository.create_strategy(
            name="Update Test",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        # Update the strategy
        new_triggers = [{"type": "engulfing", "params": {"min_body_ratio": 0.5}}]
        await repository.update_strategy(
            strategy_id=strategy_id,
            name="Updated Name",
            triggers=new_triggers,
            description="Updated description",
        )

        strategy = await repository.get_strategy(strategy_id)
        assert strategy["name"] == "Updated Name"
        assert strategy["description"] == "Updated description"
        assert strategy["triggers"] == new_triggers

    @pytest.mark.asyncio
    async def test_delete_strategy(self, repository):
        """Test deleting a strategy configuration."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        strategy_id = await repository.create_strategy(
            name="Delete Test",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        # Delete the strategy
        await repository.delete_strategy(strategy_id)

        # Verify deleted
        strategy = await repository.get_strategy(strategy_id)
        assert strategy is None

    @pytest.mark.asyncio
    async def test_list_strategies(self, repository):
        """Test listing strategies."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        # Create multiple strategies
        for i in range(3):
            await repository.create_strategy(
                name=f"Strategy {i}",
                triggers=triggers,
                filters=filters,
                apply_to=apply_to,
            )

        # List all strategies (default: only active)
        strategies = await repository.list_strategies()
        # Note: By default, list_strategies returns only active strategies
        # Since no strategy was activated, this returns 0
        assert len(strategies) == 0

        strategies = await repository.list_strategies(include_inactive=True)
        assert len(strategies) == 3

    @pytest.mark.asyncio
    async def test_get_active_strategy(self, repository):
        """Test retrieving the active strategy."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        # Create strategies and activate one
        id1 = await repository.create_strategy(
            name="Active Strategy",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )
        await repository.create_strategy(
            name="Inactive Strategy",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        await repository.activate_strategy(id1)

        active = await repository.get_active_strategy()
        assert active is not None
        assert active["name"] == "Active Strategy"

    # ==================== Risk Config Tests ====================

    @pytest.mark.asyncio
    async def test_get_risk_config(self, repository):
        """Test retrieving risk configuration."""
        risk = await repository.get_risk_config()
        assert risk is not None
        assert risk["id"] == 1
        assert risk["max_loss_percent"] == 1.0
        assert risk["max_leverage"] == 10
        assert risk["max_total_exposure"] == 0.8

    @pytest.mark.asyncio
    async def test_update_risk_config(self, repository):
        """Test updating risk configuration."""
        # Update risk config
        await repository.update_risk_config(
            max_loss_percent=2.0,
            max_leverage=20,
            max_total_exposure=0.9,
        )

        risk = await repository.get_risk_config()
        assert risk["max_loss_percent"] == 2.0
        assert risk["max_leverage"] == 20
        assert risk["max_total_exposure"] == 0.9

    @pytest.mark.asyncio
    async def test_update_risk_config_partial(self, repository):
        """Test partially updating risk configuration."""
        # Update only max_loss_percent
        await repository.update_risk_config(max_loss_percent=1.5)

        risk = await repository.get_risk_config()
        assert risk["max_loss_percent"] == 1.5
        assert risk["max_leverage"] == 10  # Unchanged
        assert risk["max_total_exposure"] == 0.8  # Unchanged

    # ==================== System Config Tests ====================

    @pytest.mark.asyncio
    async def test_get_system_config(self, repository):
        """Test retrieving system configuration."""
        system = await repository.get_system_config()
        assert system is not None
        assert system["id"] == 1
        assert system["history_bars"] == 100
        assert system["queue_batch_size"] == 10
        assert system["queue_flush_interval"] == 5.0

    @pytest.mark.asyncio
    async def test_update_system_config(self, repository):
        """Test updating system configuration."""
        # Update system config
        await repository.update_system_config(
            history_bars=200,
            queue_batch_size=20,
            queue_flush_interval=10.0,
        )

        system = await repository.get_system_config()
        assert system["history_bars"] == 200
        assert system["queue_batch_size"] == 20
        assert system["queue_flush_interval"] == 10.0

    @pytest.mark.asyncio
    async def test_update_system_config_partial(self, repository):
        """Test partially updating system configuration."""
        # Update only history_bars
        await repository.update_system_config(history_bars=150)

        system = await repository.get_system_config()
        assert system["history_bars"] == 150
        assert system["queue_batch_size"] == 10  # Unchanged
        assert system["queue_flush_interval"] == 5.0  # Unchanged

    # ==================== Symbol Config Tests ====================

    @pytest.mark.asyncio
    async def test_add_symbol(self, repository):
        """Test adding a new symbol configuration."""
        symbol_id = await repository.add_symbol(
            symbol="BTC/USDT:USDT",
            is_core=1,
            is_enabled=1,
        )

        assert symbol_id is not None
        assert symbol_id > 0

        # Retrieve and verify
        symbol = await repository.get_symbol("BTC/USDT:USDT")
        assert symbol is not None
        assert symbol["symbol"] == "BTC/USDT:USDT"
        assert symbol["is_core"] == 1
        assert symbol["is_enabled"] == 1

    @pytest.mark.asyncio
    async def test_get_symbol_by_id(self, repository):
        """Test retrieving symbol by ID."""
        symbol_id = await repository.add_symbol(
            symbol="ETH/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        symbol = await repository.get_symbol_by_id(symbol_id)
        assert symbol is not None
        assert symbol["id"] == symbol_id
        assert symbol["symbol"] == "ETH/USDT:USDT"

    @pytest.mark.asyncio
    async def test_update_symbol(self, repository):
        """Test updating a symbol configuration."""
        await repository.add_symbol(
            symbol="SOL/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        # Update the symbol
        await repository.update_symbol(
            symbol="SOL/USDT:USDT",
            is_core=1,
            is_enabled=0,
        )

        symbol = await repository.get_symbol("SOL/USDT:USDT")
        assert symbol["is_core"] == 1
        assert symbol["is_enabled"] == 0

    @pytest.mark.asyncio
    async def test_remove_symbol(self, repository):
        """Test removing a symbol configuration."""
        await repository.add_symbol(
            symbol="BNB/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        # Remove the symbol
        await repository.remove_symbol("BNB/USDT:USDT")

        # Verify removed
        symbol = await repository.get_symbol("BNB/USDT:USDT")
        assert symbol is None

    @pytest.mark.asyncio
    async def test_remove_symbol_by_id(self, repository):
        """Test removing a symbol configuration by ID."""
        symbol_id = await repository.add_symbol(
            symbol="XRP/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        # Remove by ID
        result = await repository.remove_symbol_by_id(symbol_id)
        assert result is True

        # Verify removed
        symbol = await repository.get_symbol_by_id(symbol_id)
        assert symbol is None

    @pytest.mark.asyncio
    async def test_cannot_remove_core_symbol(self, repository):
        """Test that core symbols cannot be removed."""
        await repository.add_symbol(
            symbol="BTC/USDT:USDT",
            is_core=1,
            is_enabled=1,
        )

        # Attempt to remove core symbol should raise error
        with pytest.raises(ValueError, match="核心币种不可删除"):
            await repository.remove_symbol("BTC/USDT:USDT")

        with pytest.raises(ValueError, match="核心币种不可删除"):
            await repository.remove_symbol_by_id(1)

    @pytest.mark.asyncio
    async def test_get_enabled_symbols(self, repository):
        """Test retrieving enabled symbols."""
        # Add symbols
        await repository.add_symbol("BTC/USDT:USDT", is_core=1, is_enabled=1)
        await repository.add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=1)
        await repository.add_symbol("SOL/USDT:USDT", is_core=0, is_enabled=0)

        enabled = await repository.get_enabled_symbols()
        assert "BTC/USDT:USDT" in enabled
        assert "ETH/USDT:USDT" in enabled
        assert "SOL/USDT:USDT" not in enabled

    @pytest.mark.asyncio
    async def test_list_symbols(self, repository):
        """Test listing all symbols."""
        await repository.add_symbol("BTC/USDT:USDT", is_core=1, is_enabled=1)
        await repository.add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=1)

        all_symbols = await repository.list_symbols()
        assert len(all_symbols) == 2

        enabled_only = await repository.list_symbols(enabled_only=True)
        assert len(enabled_only) == 2

        # Disable one symbol
        await repository.update_symbol("BTC/USDT:USDT", is_enabled=0)

        enabled_only = await repository.list_symbols(enabled_only=True)
        assert len(enabled_only) == 1

    @pytest.mark.asyncio
    async def test_delete_symbol(self, repository):
        """Test deleting a symbol by ID (API v1 method)."""
        symbol_id = await repository.add_symbol(
            symbol="DOGE/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        # Delete by ID
        result = await repository.delete_symbol(symbol_id)
        assert result is True

        # Verify deleted
        symbol = await repository.get_symbol_by_id(symbol_id)
        assert symbol is None

    # ==================== Notification Config Tests ====================

    @pytest.mark.asyncio
    async def test_add_notification(self, repository):
        """Test adding a new notification configuration."""
        notification_id = await repository.add_notification(
            channel="feishu",
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test123",
            is_enabled=1,
            description="Test notification",
        )

        assert notification_id is not None
        assert notification_id > 0

        # Retrieve and verify
        notification = await repository.get_notification(notification_id)
        assert notification is not None
        assert notification["channel"] == "feishu"
        assert notification["webhook_url"] == "https://open.feishu.cn/open-apis/bot/v2/hook/test123"
        assert notification["is_enabled"] == 1

    @pytest.mark.asyncio
    async def test_update_notification(self, repository):
        """Test updating a notification configuration."""
        notification_id = await repository.add_notification(
            channel="feishu",
            webhook_url="https://example.com/webhook",
            is_enabled=1,
        )

        # Update the notification
        await repository.update_notification(
            notification_id=notification_id,
            webhook_url="https://updated.com/webhook",
            is_enabled=0,
        )

        notification = await repository.get_notification(notification_id)
        assert notification["webhook_url"] == "https://updated.com/webhook"
        assert notification["is_enabled"] == 0

    @pytest.mark.asyncio
    async def test_delete_notification(self, repository):
        """Test deleting a notification configuration."""
        notification_id = await repository.add_notification(
            channel="telegram",
            webhook_url="https://telegram.com/webhook",
            is_enabled=1,
        )

        # Delete the notification
        await repository.delete_notification(notification_id)

        # Verify deleted
        notification = await repository.get_notification(notification_id)
        assert notification is None

    @pytest.mark.asyncio
    async def test_get_enabled_notifications(self, repository):
        """Test retrieving enabled notifications."""
        await repository.add_notification("feishu", "https://feishu.com/webhook", is_enabled=1)
        await repository.add_notification("wecom", "https://wecom.com/webhook", is_enabled=0)
        await repository.add_notification("telegram", "https://telegram.com/webhook", is_enabled=1)

        enabled = await repository.get_enabled_notifications()
        assert len(enabled) == 2

        channels = [n["channel"] for n in enabled]
        assert "feishu" in channels
        assert "telegram" in channels
        assert "wecom" not in channels

    @pytest.mark.asyncio
    async def test_list_notifications(self, repository):
        """Test listing all notifications."""
        await repository.add_notification("feishu", "https://feishu.com/webhook", is_enabled=1)
        await repository.add_notification("wecom", "https://wecom.com/webhook", is_enabled=0)

        all_notifications = await repository.list_notifications()
        assert len(all_notifications) == 2

        enabled_only = await repository.list_notifications(enabled_only=True)
        assert len(enabled_only) == 1

    @pytest.mark.asyncio
    async def test_get_notification_by_id(self, repository):
        """Test retrieving notification by ID (API v1 method)."""
        notification_id = await repository.add_notification(
            channel="feishu",
            webhook_url="https://example.com/webhook",
            is_enabled=1,
        )

        notification = await repository.get_notification_by_id(notification_id)
        assert notification is not None
        assert notification["id"] == notification_id
        assert notification["channel"] == "feishu"


class TestConfigSnapshots:
    """Test config snapshot repository methods."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_create_snapshot(self, repository):
        """Test creating a config snapshot."""
        config_json = {
            "risk": {"max_loss_percent": 1.0},
            "system": {"history_bars": 100},
        }

        snapshot_id = await repository.create_snapshot(
            name="Test Snapshot",
            config_json=config_json,
            description="Test snapshot for unit testing",
            created_by="test_user",
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

        # Retrieve and verify
        snapshot = await repository.get_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot["name"] == "Test Snapshot"
        assert snapshot["description"] == "Test snapshot for unit testing"
        assert snapshot["config_json"] == config_json

    @pytest.mark.asyncio
    async def test_get_snapshot_by_name(self, repository):
        """Test retrieving snapshot by name."""
        config_json = {"test": "data"}

        await repository.create_snapshot(
            name="Unique Snapshot",
            config_json=config_json,
        )

        snapshot = await repository.get_snapshot_by_name("Unique Snapshot")
        assert snapshot is not None
        assert snapshot["name"] == "Unique Snapshot"
        assert snapshot["config_json"] == config_json

        # Non-existent snapshot
        snapshot = await repository.get_snapshot_by_name("Non Existent")
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, repository):
        """Test deleting a snapshot."""
        config_json = {"test": "data"}

        snapshot_id = await repository.create_snapshot(
            name="Delete Test",
            config_json=config_json,
        )

        # Delete the snapshot
        await repository.delete_snapshot(snapshot_id)

        # Verify deleted
        snapshot = await repository.get_snapshot(snapshot_id)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_list_snapshots(self, repository):
        """Test listing snapshots with pagination."""
        config_json = {"test": "data"}

        # Create multiple snapshots
        for i in range(5):
            await repository.create_snapshot(
                name=f"Snapshot {i}",
                config_json={**config_json, "index": i},
            )

        # List all snapshots
        snapshots = await repository.list_snapshots(limit=50, offset=0)
        assert len(snapshots) == 5

        # List with pagination
        snapshots = await repository.list_snapshots(limit=2, offset=0)
        assert len(snapshots) == 2

        snapshots = await repository.list_snapshots(limit=2, offset=2)
        assert len(snapshots) == 2

    @pytest.mark.asyncio
    async def test_get_snapshot_count(self, repository):
        """Test getting snapshot count."""
        config_json = {"test": "data"}

        # Create 3 snapshots
        for i in range(3):
            await repository.create_snapshot(
                name=f"Count Test {i}",
                config_json=config_json,
            )

        count = await repository.get_snapshot_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_create_full_snapshot(self, repository):
        """Test creating a full configuration snapshot."""
        snapshot_id = await repository.create_full_snapshot(
            name="Full Config Snapshot",
            description="Complete configuration snapshot",
            created_by="admin",
        )

        assert snapshot_id is not None

        snapshot = await repository.get_snapshot(snapshot_id)
        assert snapshot is not None
        assert "strategy" in snapshot["config_json"]
        assert "risk" in snapshot["config_json"]
        assert "system" in snapshot["config_json"]
        assert "symbols" in snapshot["config_json"]
        assert "notifications" in snapshot["config_json"]


class TestConfigHistory:
    """Test config history repository methods."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_history_auto_recorded_on_strategy_create(self, repository):
        """Test that history is automatically recorded when creating a strategy."""
        triggers = [{"type": "pinbar", "params": {}}]
        filters = []
        apply_to = []

        await repository.create_strategy(
            name="History Test Strategy",
            triggers=triggers,
            filters=filters,
            apply_to=apply_to,
        )

        # History should be automatically recorded
        history = await repository.get_history(config_type="strategy", limit=10)
        assert len(history) > 0

        # Find the create action
        create_history = [h for h in history if h["action"] == "create"]
        assert len(create_history) > 0

    @pytest.mark.asyncio
    async def test_history_auto_recorded_on_risk_update(self, repository):
        """Test that history is automatically recorded when updating risk config."""
        # Update risk config
        await repository.update_risk_config(max_loss_percent=2.0)

        # History should be automatically recorded
        history = await repository.get_history(config_type="risk", limit=10)
        assert len(history) > 0

        # Find the update action
        update_history = [h for h in history if h["action"] == "update"]
        assert len(update_history) > 0

    @pytest.mark.asyncio
    async def test_get_history_by_id(self, repository):
        """Test retrieving history by ID."""
        # Create a strategy to generate history
        await repository.create_strategy(
            name="History ID Test",
            triggers=[{"type": "pinbar", "params": {}}],
            filters=[],
            apply_to=[],
        )

        # Get history
        history = await repository.get_history(config_type="strategy", limit=10)
        assert len(history) > 0

        # Retrieve by ID
        history_entry = await repository.get_history_by_id(history[0]["id"])
        assert history_entry is not None
        assert history_entry["id"] == history[0]["id"]

    @pytest.mark.asyncio
    async def test_get_history_count(self, repository):
        """Test getting history count."""
        # Create multiple strategies
        for i in range(3):
            await repository.create_strategy(
                name=f"History Count Test {i}",
                triggers=[{"type": "pinbar", "params": {}}],
                filters=[],
                apply_to=[],
            )

        count = await repository.get_history_count(config_type="strategy")
        assert count == 3  # 3 create actions

    @pytest.mark.asyncio
    async def test_history_filter_by_type(self, repository):
        """Test filtering history by config type."""
        # Create strategy
        await repository.create_strategy(
            name="Type Filter Test",
            triggers=[{"type": "pinbar", "params": {}}],
            filters=[],
            apply_to=[],
        )

        # Update risk config
        await repository.update_risk_config(max_loss_percent=2.0)

        # Filter by strategy
        strategy_history = await repository.get_history(config_type="strategy", limit=10)
        assert all(h["config_type"] == "strategy" for h in strategy_history)

        # Filter by risk
        risk_history = await repository.get_history(config_type="risk", limit=10)
        assert all(h["config_type"] == "risk" for h in risk_history)

    @pytest.mark.asyncio
    async def test_clear_old_history(self, repository):
        """Test clearing old history."""
        # Create some history entries
        await repository.create_strategy(
            name="Clear History Test",
            triggers=[{"type": "pinbar", "params": {}}],
            filters=[],
            apply_to=[],
        )

        initial_count = await repository.get_history_count()
        assert initial_count > 0

        # Clear history older than 30 days (should not clear recent entries)
        await repository.clear_old_history(keep_days=30)

        # Recent entries should still exist
        remaining_count = await repository.get_history_count()
        assert remaining_count == initial_count  # Recent entries preserved


class TestBulkOperations:
    """Test bulk repository operations."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_get_full_config(self, repository):
        """Test retrieving full configuration."""
        full_config = await repository.get_full_config()

        assert "strategy" in full_config
        assert "risk" in full_config
        assert "system" in full_config
        assert "symbols" in full_config
        assert "notifications" in full_config

        # Risk and system should have default values
        assert full_config["risk"]["max_loss_percent"] == 1.0
        assert full_config["system"]["history_bars"] == 100

    @pytest.mark.asyncio
    async def test_get_all_symbols(self, repository):
        """Test retrieving all symbol configurations."""
        await repository.add_symbol("BTC/USDT:USDT", is_core=1, is_enabled=1)
        await repository.add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=0)

        all_symbols = await repository.get_all_symbols()
        assert len(all_symbols) == 2

        # Both enabled and disabled should be included
        symbols_list = [s["symbol"] for s in all_symbols]
        assert "BTC/USDT:USDT" in symbols_list
        assert "ETH/USDT:USDT" in symbols_list

    @pytest.mark.asyncio
    async def test_get_all_notifications(self, repository):
        """Test retrieving all notification configurations."""
        await repository.add_notification("feishu", "https://feishu.com/webhook", is_enabled=1)
        await repository.add_notification("wecom", "https://wecom.com/webhook", is_enabled=0)

        all_notifications = await repository.get_all_notifications()
        assert len(all_notifications) == 2

        # Both enabled and disabled should be included
        channels = [n["channel"] for n in all_notifications]
        assert "feishu" in channels
        assert "wecom" in channels


class TestRepositoryInitialization:
    """Test repository initialization and edge cases."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_create_data_directory(self):
        """Test that data directory is created if not exists."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "subdir", "config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        # Directory should be created
        assert os.path.exists(os.path.dirname(db_path))

        await repo.close()
        os.remove(db_path)
        os.rmdir(os.path.dirname(db_path))
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_database_tables_created(self):
        """Test that all database tables are created on initialization."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        # Verify tables exist by querying them
        async with repo._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = await cursor.fetchall()
            table_names = [t["name"] for t in tables]

        expected_tables = [
            "strategy_configs",
            "risk_configs",
            "system_configs",
            "symbol_configs",
            "notification_configs",
            "config_snapshots",
            "config_history",
        ]

        for table in expected_tables:
            assert table in table_names

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_default_configs_initialized(self):
        """Test that default configs are initialized."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        # Risk config should have default values
        risk = await repo.get_risk_config()
        assert risk is not None
        assert risk["max_loss_percent"] == 1.0
        assert risk["max_leverage"] == 10

        # System config should have default values
        system = await repo.get_system_config()
        assert system is not None
        assert system["history_bars"] == 100
        assert system["queue_batch_size"] == 10

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_nonexistent_symbol_retrieval(self, repository):
        """Test retrieving a non-existent symbol returns None."""
        symbol = await repository.get_symbol("NON/EXISTENT:USDT")
        assert symbol is None

    @pytest.mark.asyncio
    async def test_nonexistent_notification_retrieval(self, repository):
        """Test retrieving a non-existent notification returns None."""
        notification = await repository.get_notification(999)
        assert notification is None

    @pytest.mark.asyncio
    async def test_nonexistent_strategy_retrieval(self, repository):
        """Test retrieving a non-existent strategy returns None."""
        strategy = await repository.get_strategy(999)
        assert strategy is None
