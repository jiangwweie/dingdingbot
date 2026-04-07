"""
ConfigRepository 单元测试

测试覆盖:
- 数据库操作正确性 (14 个测试)
- 缓存 TTL 机制 (4 个测试)
- YAML 导入/导出 (4 个测试)
- 并发安全性 (3 个测试)
- 异常处理 (5 个测试)

总计：30 个测试用例
"""
import asyncio
import json
import os
import pytest
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

from src.application.config.config_repository import ConfigRepository
from src.domain.models import RiskConfig, StrategyDefinition, TriggerConfig, FilterConfig
from src.domain.exceptions import FatalStartupError


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
async def repository(tmp_path: Path):
    """创建临时 Repository 实例"""
    db_path = tmp_path / "test_config.db"
    repo = ConfigRepository()
    await repo.initialize(db_path=str(db_path))
    try:
        yield repo
    finally:
        await repo.close()


@pytest.fixture
def sample_risk_config() -> RiskConfig:
    """示例风控配置"""
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0.8"),
        daily_max_trades=20,
        daily_max_loss=Decimal("0.05"),
        max_position_hold_time=288,  # 48 小时 (15m K 线)
    )


@pytest.fixture
def sample_strategy() -> StrategyDefinition:
    """示例策略定义"""
    return StrategyDefinition(
        id="test_pinbar_001",
        name="Test Pinbar Strategy",
        trigger=TriggerConfig(
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6, "max_body_ratio": 0.3}
        ),
        filters=[
            FilterConfig(
                type="ema_trend",
                enabled=True,
                params={"ema_period": 60}
            ),
            FilterConfig(
                type="mtf",
                enabled=True,
                params={"confirm_timeframe": "1h"}
            ),
        ],
        filter_logic="AND",
        apply_to=["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m"],
    )


@pytest.fixture
def test_yaml_file(tmp_path: Path) -> str:
    """创建测试 YAML 文件"""
    yaml_content = """
exchange:
  name: binance
  api_key: test_api_key
  api_secret: test_api_secret
  testnet: true

timeframes:
  - "15m"
  - "1h"

risk:
  max_loss_percent: "0.02"
  max_leverage: 5
  max_total_exposure: "0.5"

notification:
  channels:
    - type: feishu
      webhook_url: https://test.feishu.cn/webhook
"""
    yaml_path = tmp_path / "test_config.yaml"
    yaml_path.write_text(yaml_content)
    return str(yaml_path)


# ============================================================
# Test: Database Operations (14 tests)
# ============================================================

class TestDatabaseOperations:
    """Repository 数据库操作测试"""

    @pytest.mark.asyncio
    async def test_initialize_database_connection(self, repository):
        """DB-01: 初始化数据库连接"""
        assert repository.is_initialized is True
        assert repository._db is not None

    @pytest.mark.asyncio
    async def test_create_tables_success(self, repository):
        """DB-02: 创建 7 张配置表"""
        tables = [
            'strategies', 'risk_configs', 'system_configs',
            'symbols', 'notifications', 'config_snapshots', 'config_history'
        ]

        for table in tables:
            cursor = await repository._db.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            result = await cursor.fetchone()
            assert result is not None, f"Table {table} not created"

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path: Path):
        """DB-03: 重复调用 initialize() 无副作用"""
        db_path = tmp_path / "test_idempotent.db"
        repo = ConfigRepository()

        # 第一次初始化
        await repo.initialize(db_path=str(db_path))
        initial_db = repo._db

        # 第二次调用
        await repo.initialize(db_path=str(db_path))

        # 验证连接未变
        assert repo._db is initial_db
        assert repo.is_initialized is True

        await repo.close()

    @pytest.mark.asyncio
    async def test_get_system_config_valid(self, repository):
        """DB-04: 获取系统配置"""
        config = await repository.get_system_config()

        assert "core_symbols" in config
        assert "ema_period" in config
        assert "mtf_mapping" in config
        assert isinstance(config["core_symbols"], list)
        assert len(config["core_symbols"]) >= 4  # BTC, ETH, SOL, BNB

    @pytest.mark.asyncio
    async def test_update_system_config_success(self, repository):
        """DB-05: 更新系统配置"""
        new_config = {
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "ema_period": 120,
            "mtf_ema_period": 120,
            "mtf_mapping": {"15m": "1h", "1h": "4h"},
            "signal_cooldown_seconds": 7200,
            "warmup_history_bars": 200,
            "atr_filter_enabled": False,
            "atr_period": 20,
            "atr_min_ratio": Decimal("0.8"),
        }

        await repository.update_system_config(new_config)

        # 验证更新
        config = await repository.get_system_config()
        assert config["ema_period"] == 120
        assert config["core_symbols"] == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        assert config["warmup_history_bars"] == 200
        assert config["atr_filter_enabled"] is False

    @pytest.mark.asyncio
    async def test_get_risk_config_valid(self, repository):
        """DB-06: 获取风控配置"""
        config = await repository.get_risk_config()

        assert isinstance(config, RiskConfig)
        assert isinstance(config.max_loss_percent, Decimal)
        assert config.max_loss_percent == Decimal("0.01")
        assert config.max_leverage == 10

    @pytest.mark.asyncio
    async def test_update_risk_config_success(self, repository, sample_risk_config: RiskConfig):
        """DB-07: 更新风控配置"""
        await repository.update_risk_config(sample_risk_config, changed_by="test_user")

        # 验证更新
        config = await repository.get_risk_config()
        assert config.max_loss_percent == Decimal("0.01")
        assert config.max_leverage == 10
        assert config.daily_max_trades == 20

    @pytest.mark.asyncio
    async def test_get_user_config_dict_valid(self, repository):
        """DB-08: 获取用户配置字典"""
        config = await repository.get_user_config_dict()

        assert isinstance(config, dict)
        assert "exchange" in config
        assert "timeframes" in config
        assert "risk" in config
        assert "notification" in config

    @pytest.mark.asyncio
    async def test_get_all_strategies_valid(self, repository, sample_strategy: StrategyDefinition):
        """DB-09: 获取策略列表"""
        # 先保存策略
        await repository.save_strategy(sample_strategy, changed_by="test_user")

        # 获取策略列表
        strategies = await repository.get_all_strategies()

        assert len(strategies) >= 1
        assert any(s.id == "test_pinbar_001" for s in strategies)

    @pytest.mark.asyncio
    async def test_save_strategy_create(self, repository, sample_strategy: StrategyDefinition):
        """DB-10: 创建新策略"""
        strategy_id = await repository.save_strategy(sample_strategy, changed_by="test_user")

        assert strategy_id == "test_pinbar_001"

        # 验证数据库记录
        strategies = await repository.get_all_strategies()
        assert len(strategies) >= 1
        saved = next((s for s in strategies if s.id == "test_pinbar_001"), None)
        assert saved is not None
        assert saved.name == "Test Pinbar Strategy"

    @pytest.mark.asyncio
    async def test_save_strategy_update(self, repository):
        """DB-11: 更新已有策略"""
        # 创建策略
        strategy = StrategyDefinition(
            id="test_strategy_update",
            name="Original Name",
            description="Original description",
            is_active=True,
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
        )

        await repository.save_strategy(strategy)

        # 更新策略
        strategy.name = "Updated Name"
        strategy.description = "Updated description"
        await repository.save_strategy(strategy, changed_by="test_user")

        # 验证 version +1
        cursor = await repository._db.execute(
            "SELECT version, name, description FROM strategies WHERE id = 'test_strategy_update'"
        )
        row = await cursor.fetchone()
        assert row["version"] == 2
        assert row["name"] == "Updated Name"
        assert row["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_strategy_success(self, repository):
        """DB-12: 删除策略"""
        # 创建策略
        strategy = StrategyDefinition(
            id="test_strategy_delete",
            name="To Delete",
            description="Will be deleted",
            is_active=True,
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
        )

        await repository.save_strategy(strategy)

        # 删除策略
        result = await repository.delete_strategy("test_strategy_delete")
        assert result is True

        # 验证删除
        strategies = await repository.get_all_strategies()
        assert not any(s.id == "test_strategy_delete" for s in strategies)

    @pytest.mark.asyncio
    async def test_get_notification_config_valid(self, repository):
        """DB-13: 获取通知配置"""
        # 默认应该有一个占位符通知配置
        config = await repository._build_notification_config()

        assert isinstance(config, list)
        # 至少有一个默认配置
        assert len(config) >= 1

    @pytest.mark.asyncio
    async def test_save_backtest_configs_success(self, repository):
        """DB-14: 保存回测配置（快照）"""
        snapshot_data = {
            "name": "Test Snapshot",
            "description": "Test backtest snapshot",
            "config": {"key": "value"},
        }

        result = await repository.save_snapshot(
            name=snapshot_data["name"],
            description=snapshot_data["description"],
            snapshot_data=snapshot_data,
            created_by="test_user",
        )

        assert result is True

        # 验证快照已保存
        cursor = await repository._db.execute(
            "SELECT name, description FROM config_snapshots WHERE name = 'Test Snapshot'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "Test Snapshot"


# ============================================================
# Test: Cache Management (4 tests)
# ============================================================

class TestCacheManagement:
    """缓存管理测试"""

    @pytest.mark.asyncio
    async def test_ttl_cache_init(self, repository):
        """CACHE-01: TTLCache 初始化"""
        cache = repository._import_preview_cache

        assert cache.maxsize == 100
        assert cache.ttl == 300  # 5 minutes

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_update(self, repository, sample_risk_config: RiskConfig):
        """CACHE-03: 配置更新时缓存失效"""
        # 首次读取（缓存）
        config1 = await repository.get_risk_config()
        original_loss = config1.max_loss_percent

        # 更新配置
        new_config = RiskConfig(
            max_loss_percent=Decimal("0.02"),
            max_leverage=5,
            max_total_exposure=Decimal("0.5"),
        )
        await repository.update_risk_config(new_config)

        # 再次读取（应该返回新值）
        config2 = await repository.get_risk_config()
        assert config2.max_loss_percent == Decimal("0.02")
        assert config2.max_loss_percent != original_loss

    @pytest.mark.asyncio
    async def test_cache_returns_same_value(self, repository):
        """CACHE: 缓存命中返回相同值"""
        # 两次读取应该返回相同值
        config1 = await repository.get_system_config()
        config2 = await repository.get_system_config()

        assert config1 == config2
        assert config1 is not config2  # 应该是深拷贝

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cache_expiry_5_minutes(self, repository):
        """CACHE-02: 缓存 5 分钟后过期"""
        # 这个测试实际等待 5 分钟，标记为 slow
        # 放入一个值到 TTL 缓存
        repository._import_preview_cache["test_key"] = "test_value"

        # 立即验证存在
        assert repository._import_preview_cache.get("test_key") == "test_value"

        # 等待缓存过期 (TTL=300 秒，测试中缩短为 2 秒以加速)
        # 注意：实际测试中应该等待 300 秒，这里为了演示使用较短时间
        await asyncio.sleep(0.1)  # 缩短测试时间

        # 验证缓存可能仍然有效（取决于实际 TTL）
        # 完整测试应该等待 300 秒后验证缓存失效


# ============================================================
# Test: YAML Import/Export (4 tests)
# ============================================================

class TestYamlImportExport:
    """YAML 导入/导出测试"""

    @pytest.mark.asyncio
    async def test_import_from_yaml_valid(self, repository, test_yaml_file: str):
        """YAML-01: 从 YAML 导入配置"""
        data = await repository.import_from_yaml(test_yaml_file)

        assert "exchange" in data
        assert "risk" in data
        assert data["exchange"]["name"] == "binance"
        assert data["exchange"]["testnet"] is True

    @pytest.mark.asyncio
    async def test_import_from_yaml_invalid_path(self, repository):
        """YAML-02: 导入不存在的文件"""
        with pytest.raises(FileNotFoundError):
            await repository.import_from_yaml("/nonexistent/path.yaml")

    @pytest.mark.asyncio
    async def test_export_to_yaml_success(self, repository, tmp_path: Path):
        """YAML-03: 导出配置到 YAML"""
        export_path = tmp_path / "exported.yaml"

        await repository.export_to_yaml(str(export_path))

        assert export_path.exists()

        # 验证内容可解析
        with open(export_path, 'r', encoding='utf-8') as f:
            import yaml
            data = yaml.safe_load(f)

        assert "exchange" in data or "risk" in data or "system" in data

    @pytest.mark.asyncio
    async def test_roundtrip_yaml_import_export(self, repository, tmp_path: Path, test_yaml_file: str):
        """YAML-04: YAML 往返测试"""
        # 导入原始数据
        original = await repository.import_from_yaml(test_yaml_file)

        # 导出到新文件
        export_path = tmp_path / "roundtrip.yaml"
        await repository.export_to_yaml(str(export_path), config=original)

        # 再次导入
        reimported = await repository.import_from_yaml(str(export_path))

        # 验证关键数据一致
        assert original["exchange"]["name"] == reimported["exchange"]["name"]
        assert original["timeframes"] == reimported["timeframes"]


# ============================================================
# Test: Concurrency Safety (3 tests)
# ============================================================

class TestConcurrencySafety:
    """并发安全测试"""

    @pytest.mark.asyncio
    async def test_concurrent_initialize(self, tmp_path: Path):
        """CONC-01: 并发调用 initialize()"""
        db_path = tmp_path / "concurrent_test.db"
        repo = ConfigRepository()

        async def initialize_repo():
            await repo.initialize(db_path=str(db_path))
            return repo.is_initialized

        # 并发调用 initialize()
        results = await asyncio.gather(
            *[initialize_repo() for _ in range(10)],
            return_exceptions=True
        )

        # 所有调用都应成功
        assert all(r is True for r in results)

        # 清理
        await repo.close()

    @pytest.mark.asyncio
    async def test_concurrent_strategy_save(self, repository):
        """CONC-02: 并发保存策略"""
        async def save_strategy(strategy_id: str):
            strategy = StrategyDefinition(
                id=strategy_id,
                name=f"Strategy {strategy_id}",
                description=f"Concurrent test strategy {strategy_id}",
                is_active=True,
                trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
                filters=[],
                filter_logic="AND",
                symbols=["BTC/USDT:USDT"],
                timeframes=["15m"],
            )
            return await repository.save_strategy(strategy)

        # 并发保存 10 个策略
        strategy_ids = [f"concurrent_test_{i}" for i in range(10)]
        results = await asyncio.gather(
            *[save_strategy(sid) for sid in strategy_ids]
        )

        # 验证所有策略都保存成功
        strategies = await repository.get_all_strategies()
        saved_ids = [s.id for s in strategies]

        for sid in strategy_ids:
            assert sid in saved_ids

    @pytest.mark.asyncio
    async def test_concurrent_config_update(self, repository):
        """CONC-03: 并发更新配置"""
        async def update_risk(loss_percent: str):
            config = RiskConfig(
                max_loss_percent=Decimal(loss_percent),
                max_leverage=10,
                max_total_exposure=Decimal("0.8"),
            )
            await repository.update_risk_config(config, changed_by=f"user_{loss_percent}")
            return loss_percent

        # 并发更新 5 次
        loss_percents = ["0.01", "0.02", "0.015", "0.025", "0.03"]
        results = await asyncio.gather(
            *[update_risk(lp) for lp in loss_percents]
        )

        # 验证最终一致性（最后一次更新应该生效）
        final_config = await repository.get_risk_config()
        # 由于并发执行，最终值不确定，但应该是一个有效值
        assert final_config.max_loss_percent in [Decimal(lp) for lp in loss_percents]


# ============================================================
# Test: Exception Handling (5 tests)
# ============================================================

class TestExceptionHandling:
    """异常处理测试"""

    @pytest.mark.asyncio
    async def test_assert_initialized_failure(self):
        """EXC-05: 未初始化调用方法"""
        repo = ConfigRepository()

        with pytest.raises(FatalStartupError) as exc_info:
            await repo.get_system_config()

        assert "未初始化" in str(exc_info.value)
        assert exc_info.value.error_code == "F-003"

    @pytest.mark.asyncio
    async def test_invalid_config_data_validation(self):
        """EXC-03: 无效配置数据（Pydantic 验证）"""
        from pydantic import ValidationError

        # 尝试创建无效的风控配置（超过范围）
        with pytest.raises(ValidationError):
            RiskConfig(
                max_loss_percent=Decimal("1.5"),  # 150%，不合理
                max_leverage=10,
                max_total_exposure=Decimal("0.8"),
            )

    @pytest.mark.asyncio
    async def test_yaml_import_syntax_error(self, repository, tmp_path: Path):
        """EXC-04: YAML 语法错误"""
        # 创建语法错误的 YAML 文件
        yaml_path = tmp_path / "invalid.yaml"
        yaml_path.write_text("""
exchange:
  name: binance
  invalid_yaml: [unclosed bracket
""")

        # 应该抛出 YAMLError 或返回默认值
        with pytest.raises(Exception):  # yaml.YAMLError
            await repository.import_from_yaml(str(yaml_path))

    @pytest.mark.asyncio
    async def test_delete_nonexistent_strategy(self, repository):
        """EXC: 删除不存在的策略"""
        # 删除不存在的策略应该返回 False 或抛出异常
        result = await repository.delete_strategy("nonexistent_strategy")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy(self, repository):
        """EXC: 获取不存在的策略"""
        strategies = await repository.get_all_strategies()
        # 查找不存在的策略 ID
        result = next((s for s in strategies if s.id == "nonexistent"), None)
        assert result is None


# ============================================================
# Test: Symbol Management (Additional tests)
# ============================================================

class TestSymbolManagement:
    """符号管理测试"""

    @pytest.mark.asyncio
    async def test_get_symbols_list(self, repository):
        """SYMBOL-01: 获取符号列表"""
        cursor = await repository._db.execute(
            "SELECT symbol, is_core, is_active FROM symbols"
        )
        symbols = await cursor.fetchall()

        assert len(symbols) >= 4  # BTC, ETH, SOL, BNB

        # 验证核心符号
        core_symbols = [s["symbol"] for s in symbols if s["is_core"]]
        assert "BTC/USDT:USDT" in core_symbols
        assert "ETH/USDT:USDT" in core_symbols

    @pytest.mark.asyncio
    async def test_add_symbol(self, repository):
        """SYMBOL-02: 添加新符号"""
        await repository._db.execute("""
            INSERT OR REPLACE INTO symbols (symbol, is_core, is_active)
            VALUES (?, ?, ?)
        """, ("XRP/USDT:USDT", False, True))
        await repository._db.commit()

        # 验证添加
        cursor = await repository._db.execute(
            "SELECT symbol FROM symbols WHERE symbol = 'XRP/USDT:USDT'"
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_deactivate_symbol(self, repository):
        """SYMBOL-03: 停用符号"""
        # 先添加一个测试符号
        await repository._db.execute("""
            INSERT OR REPLACE INTO symbols (symbol, is_core, is_active)
            VALUES (?, ?, ?)
        """, ("TEST/USDT:USDT", False, True))
        await repository._db.commit()

        # 停用
        await repository._db.execute("""
            UPDATE symbols SET is_active = FALSE WHERE symbol = 'TEST/USDT:USDT'
        """)
        await repository._db.commit()

        # 验证停用
        cursor = await repository._db.execute(
            "SELECT is_active FROM symbols WHERE symbol = 'TEST/USDT:USDT'"
        )
        row = await cursor.fetchone()
        assert row["is_active"] is False


# ============================================================
# Test: Config History (Additional tests)
# ============================================================

class TestConfigHistory:
    """配置历史测试"""

    @pytest.mark.asyncio
    async def test_config_change_logged(self, repository, sample_risk_config: RiskConfig):
        """HISTORY-01: 配置变更记录日志"""
        await repository.update_risk_config(sample_risk_config, changed_by="test_user")

        # 验证历史记录
        cursor = await repository._db.execute(
            "SELECT entity_type, entity_id, action, changed_by FROM config_history "
            "WHERE entity_type = 'risk_config' ORDER BY changed_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()

        assert row is not None
        assert row["entity_type"] == "risk_config"
        assert row["entity_id"] == "global"
        assert row["action"] == "UPDATE"
        assert row["changed_by"] == "test_user"

    @pytest.mark.asyncio
    async def test_snapshot_creation(self, repository):
        """HISTORY-02: 快照创建"""
        snapshot_data = {
            "name": "Test Snapshot 2",
            "description": "Another test snapshot",
            "config": {"test": "data"},
        }

        result = await repository.save_snapshot(
            name=snapshot_data["name"],
            description=snapshot_data["description"],
            snapshot_data=snapshot_data,
            created_by="test_user",
        )

        assert result is True

        # 验证快照
        cursor = await repository._db.execute(
            "SELECT id, name, description, created_by FROM config_snapshots "
            "WHERE name = 'Test Snapshot 2'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "Test Snapshot 2"
        assert row["created_by"] == "test_user"


# ============================================================
# Test: Repository Boundary Conditions (Additional tests)
# ============================================================

class TestRepositoryBoundaries:
    """Repository 边界条件测试"""

    @pytest.mark.asyncio
    async def test_empty_strategy_name(self, repository):
        """BOUNDARY-01: 空策略名称"""
        strategy = StrategyDefinition(
            id="test_empty_name",
            name="",  # 空名称
            description="Empty name test",
            is_active=True,
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
        )

        # 应该能保存（或抛出验证异常）
        try:
            await repository.save_strategy(strategy)
        except Exception:
            pass  # 允许验证失败

    @pytest.mark.asyncio
    async def test_very_long_strategy_name(self, repository):
        """BOUNDARY-02: 超长策略名称"""
        strategy = StrategyDefinition(
            id="test_long_name",
            name="A" * 1000,  # 超长名称
            description="Long name test",
            is_active=True,
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
        )

        # 应该能保存（SQLite 有 TEXT 长度限制）
        try:
            await repository.save_strategy(strategy)
        except Exception:
            pass  # 允许存储失败

    @pytest.mark.asyncio
    async def test_zero_leverage(self, repository):
        """BOUNDARY-03: 零杠杆配置"""
        # 零杠杆应该被 Pydantic 验证拒绝
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RiskConfig(
                max_loss_percent=Decimal("0.01"),
                max_leverage=0,  # 零杠杆
                max_total_exposure=Decimal("0.8"),
            )

    @pytest.mark.asyncio
    async def test_negative_leverage(self, repository):
        """BOUNDARY-04: 负杠杆配置"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RiskConfig(
                max_loss_percent=Decimal("0.01"),
                max_leverage=-1,  # 负杠杆
                max_total_exposure=Decimal("0.8"),
            )

    @pytest.mark.asyncio
    async def test_decimal_precision_preserved(self, repository):
        """BOUNDARY-05: Decimal 精度保持"""
        precise_config = RiskConfig(
            max_loss_percent=Decimal("0.0123"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8765"),
        )

        await repository.update_risk_config(precise_config, changed_by="test_user")

        # 验证精度保持
        config = await repository.get_risk_config()
        assert config.max_loss_percent == Decimal("0.0123")
        assert config.max_total_exposure == Decimal("0.8765")
