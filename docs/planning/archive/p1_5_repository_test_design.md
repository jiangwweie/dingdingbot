# P1-5 Repository 层测试用例设计

> **文档状态**: 待执行  
> **创建日期**: 2026-04-07  
> **作者**: Backend Developer  
> **适用对象**: QA Tester  
> **关联实现**: `src/application/config/config_repository.py`  

---

## 1. 测试目标

验证 ConfigRepository 层的以下方面：

- **数据库操作正确性**: 7 张配置表的 CRUD 操作
- **缓存 TTL 机制**: 5 分钟过期、配置更新时失效
- **YAML 导入/导出**: 解析、序列化、精度保持
- **并发安全性**: asyncio.Lock 保护下的并发写入
- **异常处理**: 数据库连接失败、数据验证失败等场景

---

## 2. 测试环境准备

### 2.1 测试数据库

```python
# 使用内存数据库或临时文件
import tempfile
import os

# 方式 1: 临时文件数据库
test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
test_db_path = Path(test_db_path)

# 方式 2: 内存数据库（更快，但无法测试 WAL 模式）
test_db_path = ":memory:"
```

### 2.2 测试 Fixture

```python
import pytest
import asyncio
from pathlib import Path
from src.application.config.config_repository import ConfigRepository

@pytest.fixture
async def repo():
    """Create a test repository with temporary database."""
    repo = ConfigRepository()
    test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
    
    try:
        await repo.initialize(db_path=test_db_path)
        yield repo
    finally:
        await repo.close()
        os.close(test_db_fd)
        os.unlink(test_db_path)

@pytest.fixture
def test_yaml_path():
    """Path to test YAML file."""
    return Path(__file__).parent / "fixtures" / "test_config.yaml"
```

### 2.3 测试数据准备

**test_config.yaml** (测试 YAML 文件):
```yaml
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
```

---

## 3. 测试用例清单

### 3.1 数据库操作测试 (14 个)

| 用例 ID | 测试方法 | 测试内容 | 预期结果 |
|--------|---------|---------|---------|
| DB-01 | `test_initialize_database_connection` | 初始化数据库连接 | 连接成功，`is_initialized=True` |
| DB-02 | `test_create_tables_success` | 创建 7 张配置表 | 所有表存在，schema 正确 |
| DB-03 | `test_initialize_idempotent` | 重复调用 initialize() | 无副作用，第二次调用直接返回 |
| DB-04 | `test_get_system_config_valid` | 获取系统配置 | 返回包含 core_symbols 等字段的字典 |
| DB-05 | `test_update_system_config_success` | 更新系统配置 | 数据库记录更新，缓存失效 |
| DB-06 | `test_get_risk_config_valid` | 获取风控配置 | 返回 RiskConfig 对象，Decimal 精度正确 |
| DB-07 | `test_update_risk_config_success` | 更新风控配置 | 数据库记录更新，缓存更新 |
| DB-08 | `test_get_user_config_dict_valid` | 获取用户配置字典 | 包含 exchange、risk、notification 等 |
| DB-09 | `test_get_all_strategies_valid` | 获取策略列表 | 返回 StrategyDefinition 列表 |
| DB-10 | `test_save_strategy_create` | 创建新策略 | 返回策略 ID，数据库有记录 |
| DB-11 | `test_save_strategy_update` | 更新已有策略 | version 字段 +1 |
| DB-12 | `test_delete_strategy_success` | 删除策略 | 返回 True，数据库记录消失 |
| DB-13 | `test_get_notification_config_valid` | 获取通知配置 | 返回 NotificationConfig |
| DB-14 | `test_save_backtest_configs_success` | 保存回测配置 | 返回保存项数量 |

### 3.2 缓存管理测试 (4 个)

| 用例 ID | 测试方法 | 测试内容 | 预期结果 |
|--------|---------|---------|---------|
| CACHE-01 | `test_ttl_cache_init` | TTLCache 初始化 | maxsize=100, ttl=300 |
| CACHE-02 | `test_cache_expiry_5_minutes` | 缓存 5 分钟后过期 | 5 分钟后读取返回新数据 |
| CACHE-03 | `test_cache_invalidation_on_update` | 配置更新时缓存失效 | update 后立即读取返回新值 |
| CACHE-04 | `test_cache_hit_performance` | 缓存命中性能 | 命中时间 < 1ms |

### 3.3 YAML 导入/导出测试 (4 个)

| 用例 ID | 测试方法 | 测试内容 | 预期结果 |
|--------|---------|---------|---------|
| YAML-01 | `test_import_from_yaml_valid` | 从 YAML 导入配置 | 返回配置字典，数据正确 |
| YAML-02 | `test_import_from_yaml_invalid_path` | 导入不存在的文件 | 抛出 FileNotFoundError |
| YAML-03 | `test_export_to_yaml_success` | 导出配置到 YAML | 文件存在，内容可解析 |
| YAML-04 | `test_roundtrip_yaml_import_export` | YAML 往返测试 | 导出后再导入，数据一致 |

### 3.4 并发安全测试 (3 个)

| 用例 ID | 测试方法 | 测试内容 | 预期结果 |
|--------|---------|---------|---------|
| CONC-01 | `test_concurrent_initialize` | 并发调用 initialize() | 仅一次初始化成功，其他等待 |
| CONC-02 | `test_concurrent_strategy_save` | 并发保存策略 | 无数据损坏，所有策略保存成功 |
| CONC-03 | `test_concurrent_config_update` | 并发更新配置 | 无竞态条件，最终一致性 |

### 3.5 异常处理测试 (5 个)

| 用例 ID | 测试方法 | 测试内容 | 预期结果 |
|--------|---------|---------|---------|
| EXC-01 | `test_database_connection_failure` | 数据库连接失败 | 抛出异常，错误信息清晰 |
| EXC-02 | `test_table_creation_failure` | 表创建失败 | 抛出异常，回滚事务 |
| EXC-03 | `test_invalid_config_data` | 无效配置数据 | 抛出 ValidationError |
| EXC-04 | `test_yaml_import_syntax_error` | YAML 语法错误 | 抛出 YAMLError 或使用默认配置 |
| EXC-05 | `test_assert_initialized_failure` | 未初始化调用方法 | 抛出 FatalStartupError |

---

## 4. 测试代码示例

### 4.1 数据库操作测试示例

```python
import pytest
from decimal import Decimal
from src.application.config.config_repository import ConfigRepository
from src.domain.models import RiskConfig

class TestDatabaseOperations:
    
    @pytest.mark.asyncio
    async def test_initialize_database_connection(self, repo):
        """DB-01: 初始化数据库连接"""
        assert repo.is_initialized is True
        assert repo._db is not None
    
    @pytest.mark.asyncio
    async def test_create_tables_success(self, repo):
        """DB-02: 创建 7 张配置表"""
        tables = [
            'strategies', 'risk_configs', 'system_configs',
            'symbols', 'notifications', 'config_snapshots', 'config_history'
        ]
        
        for table in tables:
            cursor = await repo._db.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            result = await cursor.fetchone()
            assert result is not None, f"Table {table} not created"
    
    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, repo):
        """DB-03: 重复调用 initialize() 无副作用"""
        initial_db = repo._db
        await repo.initialize()  # 第二次调用
        assert repo._db is initial_db  # 连接未变
    
    @pytest.mark.asyncio
    async def test_get_system_config_valid(self, repo):
        """DB-04: 获取系统配置"""
        config = await repo.get_system_config()
        
        assert "core_symbols" in config
        assert "ema_period" in config
        assert "mtf_mapping" in config
        assert isinstance(config["core_symbols"], list)
    
    @pytest.mark.asyncio
    async def test_update_system_config_success(self, repo):
        """DB-05: 更新系统配置"""
        new_config = {
            "core_symbols": ["BTC/USDT:USDT"],
            "ema_period": 120,
            "mtf_ema_period": 120,
            "mtf_mapping": {"15m": "1h"},
            "signal_cooldown_seconds": 7200,
        }
        
        await repo.update_system_config(new_config)
        
        # 验证更新
        config = await repo.get_system_config()
        assert config["ema_period"] == 120
        assert config["core_symbols"] == ["BTC/USDT:USDT"]
    
    @pytest.mark.asyncio
    async def test_get_risk_config_valid(self, repo):
        """DB-06: 获取风控配置"""
        config = await repo.get_risk_config()
        
        assert isinstance(config, RiskConfig)
        assert isinstance(config.max_loss_percent, Decimal)
        assert config.max_loss_percent == Decimal("0.01")
        assert config.max_leverage == 10
    
    @pytest.mark.asyncio
    async def test_update_risk_config_success(self, repo):
        """DB-07: 更新风控配置"""
        new_config = RiskConfig(
            max_loss_percent=Decimal("0.02"),
            max_leverage=5,
            max_total_exposure=Decimal("0.5"),
        )
        
        await repo.update_risk_config(new_config, changed_by="test_user")
        
        # 验证更新
        config = await repo.get_risk_config()
        assert config.max_loss_percent == Decimal("0.02")
        assert config.max_leverage == 5
    
    @pytest.mark.asyncio
    async def test_save_strategy_create(self, repo):
        """DB-10: 创建新策略"""
        from src.domain.models import StrategyDefinition, TriggerConfig
        
        strategy = StrategyDefinition(
            id="test_strategy_1",
            name="Test Pinbar",
            trigger=TriggerConfig(
                type="pinbar",
                enabled=True,
                params={"min_wick_ratio": 0.6}
            ),
            filters=[],
            filter_logic="AND",
        )
        
        strategy_id = await repo.save_strategy(strategy, changed_by="test_user")
        
        assert strategy_id == "test_strategy_1"
        
        # 验证数据库记录
        strategies = await repo.get_all_strategies()
        assert len(strategies) >= 1
        assert any(s.id == "test_strategy_1" for s in strategies)
    
    @pytest.mark.asyncio
    async def test_save_strategy_update(self, repo):
        """DB-11: 更新已有策略"""
        from src.domain.models import StrategyDefinition, TriggerConfig
        
        # 创建策略
        strategy = StrategyDefinition(
            id="test_strategy_update",
            name="Original Name",
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
        )
        
        await repo.save_strategy(strategy)
        
        # 更新策略
        strategy.name = "Updated Name"
        await repo.save_strategy(strategy)
        
        # 验证 version +1
        cursor = await repo._db.execute(
            "SELECT version FROM strategies WHERE id = 'test_strategy_update'"
        )
        row = await cursor.fetchone()
        assert row["version"] == 2
    
    @pytest.mark.asyncio
    async def test_delete_strategy_success(self, repo):
        """DB-12: 删除策略"""
        from src.domain.models import StrategyDefinition, TriggerConfig
        
        # 创建策略
        strategy = StrategyDefinition(
            id="test_strategy_delete",
            name="To Delete",
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
            filter_logic="AND",
        )
        
        await repo.save_strategy(strategy)
        
        # 删除策略
        result = await repo.delete_strategy("test_strategy_delete")
        assert result is True
        
        # 验证删除
        strategies = await repo.get_all_strategies()
        assert not any(s.id == "test_strategy_delete" for s in strategies)
```

### 4.2 缓存管理测试示例

```python
import pytest
import asyncio
import time
from src.application.config.config_repository import ConfigRepository

class TestCacheManagement:
    
    @pytest.mark.asyncio
    async def test_ttl_cache_init(self, repo):
        """CACHE-01: TTLCache 初始化"""
        cache = repo.get_import_preview_cache()
        
        assert cache.maxsize == 100
        assert cache.ttl == 300  # 5 minutes
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_on_update(self, repo):
        """CACHE-03: 配置更新时缓存失效"""
        # 首次读取（缓存）
        config1 = await repo.get_risk_config()
        
        # 更新配置
        new_config = RiskConfig(
            max_loss_percent=Decimal("0.02"),
            max_leverage=5,
            max_total_exposure=Decimal("0.5"),
        )
        await repo.update_risk_config(new_config)
        
        # 再次读取（应该返回新值）
        config2 = await repo.get_risk_config()
        assert config2.max_loss_percent == Decimal("0.02")
```

### 4.3 YAML 导入/导出测试示例

```python
import pytest
import tempfile
import os
from pathlib import Path
from decimal import Decimal

class TestYamlImportExport:
    
    @pytest.mark.asyncio
    async def test_import_from_yaml_valid(self, repo, test_yaml_path):
        """YAML-01: 从 YAML 导入配置"""
        data = await repo.import_from_yaml(str(test_yaml_path))
        
        assert "exchange" in data
        assert "risk" in data
        assert data["exchange"]["name"] == "binance"
    
    @pytest.mark.asyncio
    async def test_import_from_yaml_invalid_path(self, repo):
        """YAML-02: 导入不存在的文件"""
        with pytest.raises(FileNotFoundError):
            await repo.import_from_yaml("/nonexistent/path.yaml")
    
    @pytest.mark.asyncio
    async def test_export_to_yaml_success(self, repo, tmp_path):
        """YAML-03: 导出配置到 YAML"""
        export_path = tmp_path / "exported.yaml"
        
        await repo.export_to_yaml(str(export_path))
        
        assert export_path.exists()
        
        # 验证内容可解析
        with open(export_path, 'r') as f:
            import yaml
            data = yaml.safe_load(f)
        
        assert "exchange" in data
        assert "risk" in data
    
    @pytest.mark.asyncio
    async def test_roundtrip_yaml_import_export(self, repo, tmp_path, test_yaml_path):
        """YAML-04: YAML 往返测试"""
        # 导入原始数据
        original = await repo.import_from_yaml(str(test_yaml_path))
        
        # 导出到新文件
        export_path = tmp_path / "roundtrip.yaml"
        await repo.export_to_yaml(str(export_path), config=original)
        
        # 再次导入
        reimported = await repo.import_from_yaml(str(export_path))
        
        # 验证数据一致（忽略 Decimal 精度差异）
        assert original["exchange"]["name"] == reimported["exchange"]["name"]
        assert original["timeframes"] == reimported["timeframes"]
```

### 4.4 并发安全测试示例

```python
import pytest
import asyncio

class TestConcurrencySafety:
    
    @pytest.mark.asyncio
    async def test_concurrent_initialize(self):
        """CONC-01: 并发调用 initialize()"""
        repo = ConfigRepository()
        test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
        
        async def initialize_repo():
            await repo.initialize(db_path=test_db_path)
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
        os.close(test_db_fd)
        os.unlink(test_db_path)
    
    @pytest.mark.asyncio
    async def test_concurrent_strategy_save(self, repo):
        """CONC-02: 并发保存策略"""
        from src.domain.models import StrategyDefinition, TriggerConfig
        
        async def save_strategy(strategy_id):
            strategy = StrategyDefinition(
                id=strategy_id,
                name=f"Strategy {strategy_id}",
                trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
                filters=[],
                filter_logic="AND",
            )
            return await repo.save_strategy(strategy)
        
        # 并发保存 10 个策略
        strategy_ids = [f"concurrent_test_{i}" for i in range(10)]
        results = await asyncio.gather(
            *[save_strategy(sid) for sid in strategy_ids]
        )
        
        # 验证所有策略都保存成功
        strategies = await repo.get_all_strategies()
        saved_ids = [s.id for s in strategies]
        
        for sid in strategy_ids:
            assert sid in saved_ids
```

### 4.5 异常处理测试示例

```python
import pytest
from src.application.config.config_repository import ConfigRepository
from src.domain.exceptions import FatalStartupError

class TestExceptionHandling:
    
    @pytest.mark.asyncio
    async def test_assert_initialized_failure(self):
        """EXC-05: 未初始化调用方法"""
        repo = ConfigRepository()
        
        with pytest.raises(FatalStartupError) as exc_info:
            await repo.get_system_config()
        
        assert "未初始化" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_invalid_config_data(self, repo):
        """EXC-03: 无效配置数据"""
        from pydantic import ValidationError
        
        # 尝试保存无效的风控配置
        invalid_config = RiskConfig(
            max_loss_percent=Decimal("1.5"),  # 超过 1，应该失败
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        
        # 验证器应该拒绝
        with pytest.raises(ValidationError):
            # 注意：这里测试的是 Pydantic 验证，不是 Repository
            RiskConfig.model_validate(invalid_config.model_dump())
```

---

## 5. 测试执行计划

### 5.1 测试文件结构

```
tests/unit/config/
├── __init__.py
├── conftest.py                  # 共享 fixture
├── test_config_repository.py    # Repository 层主测试文件
├── fixtures/
│   └── test_config.yaml         # 测试 YAML 文件
└── integration/
    └── test_repository_concurrent.py  # 并发测试
```

### 5.2 测试执行命令

```bash
# 运行所有 Repository 层测试
pytest tests/unit/config/test_config_repository.py -v

# 运行覆盖率
pytest tests/unit/config/test_config_repository.py --cov=src/application/config/config_repository --cov-report=html

# 运行并发测试
pytest tests/unit/config/integration/test_repository_concurrent.py -v

# 运行特定测试类
pytest tests/unit/config/test_config_repository.py::TestDatabaseOperations -v
```

### 5.3 测试覆盖目标

| 模块 | 行覆盖 | 分支覆盖 | 关键场景 |
|------|--------|----------|----------|
| ConfigRepository | > 85% | > 80% | I/O 异常、SQL 错误、缓存失效 |

---

## 6. 测试数据清理

测试结束后应清理临时文件：

```python
@pytest.fixture(autouse=True)
def cleanup_test_files(tmp_path):
    """自动清理测试文件"""
    yield
    # 清理逻辑（如有需要）
```

---

## 7. 参考文档

- **实现文件**: `src/application/config/config_repository.py`
- **影响分析报告**: `docs/arch/P1-5-config-manager-refactor-impact-analysis.md`
- **Parser 层测试**: `tests/unit/config/test_config_parser.py`

---

*文档版本: 1.0*  
*创建日期: 2026-04-07*
