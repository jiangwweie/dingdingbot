# P1-5: ConfigManager 职责拆分影响分析报告

> **文档状态**: 待评审  
> **创建日期**: 2026-04-07  
> **作者**: 系统架构师  
> **关联 ADR**: [ADR-20260407-001](./ADR-20260407-001-p1-implementation-strategy.md)  
> **预计工时**: 16 小时  

---

## 1. 执行摘要

### 1.1 问题陈述

当前 `ConfigManager` 类 (`src/application/config_manager.py`) 承担过多职责，违反单一职责原则 (SRP)：

| 职责域 | 代码行数 | 复杂度 |
|--------|----------|--------|
| 数据库连接管理 | ~150 行 | 中 |
| 表结构创建 | ~100 行 | 低 |
| 默认配置初始化 | ~200 行 | 中 |
| 系统配置加载/缓存 | ~100 行 | 低 |
| 风控配置加载/更新 | ~150 行 | 中 |
| 用户配置构建 | ~200 行 | 高 |
| 策略 CRUD 操作 | ~150 行 | 高 |
| 通知配置构建 | ~50 行 | 低 |
| 配置历史日志 | ~50 行 | 低 |
| 观察者模式 (热重载) | ~100 行 | 中 |
| 快照服务注入 | ~50 行 | 低 |
| 回测配置 KV 操作 | ~150 行 | 高 |
| YAML 导入/导出 | ~100 行 | 中 |
| **总计** | **~1600 行** | **高** |

### 1.2 重构目标

采用**三层架构模式**拆分 ConfigManager：

```
┌─────────────────────────────────────────┐
│           ConfigService                 │
│  - 业务逻辑 (验证、合并、转换)           │
│  - 无文件操作，纯内存处理               │
│  - 依赖 ConfigRepository 获取数据       │
│  - 预计：~300 行                         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         ConfigRepository                │
│  - 文件 I/O 操作                         │
│  - 数据库操作 (SQL)                      │
│  - 缓存管理 (含 TTL)                    │
│  - 依赖 ConfigParser 解析数据           │
│  - 预计：~600 行                         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│           ConfigParser                  │
│  - YAML/JSON 解析                       │
│  - Decimal 精度处理                     │
│  - 模式验证                            │
│  - 预计：~200 行                         │
└─────────────────────────────────────────┘
```

### 1.3 影响范围总览

| 影响维度 | 评估 |
|----------|------|
| **直接修改文件** | 1 个 (config_manager.py) |
| **新增文件** | 6-8 个 (Service/Repository/Parser + 测试) |
| **调用方迁移** | 57 个文件 (import 语句) |
| **测试文件调整** | ~15 个测试文件 |
| **数据库表变更** | 无 (向后兼容) |
| **API 变更** | 无 (保持公共接口稳定) |
| **破坏性变更** | 低 (通过适配层过渡) |

---

## 2. 现有架构分析

### 2.1 ConfigManager 职责地图

```python
class ConfigManager:
    # ================================
    # 职责 1: 基础设施管理
    # ================================
    - db_path, config_dir
    - _db (aiosqlite.Connection)
    - _lock, _init_lock, _config_lock
    - _initialized, _initializing, _init_event
    
    # ================================
    # 职责 2: 数据访问层 (Repository)
    # ================================
    - _create_tables()           # 创建数据库表
    - _initialize_default_configs()  # 初始化默认配置
    - _validate_and_apply_default_configs()
    - _is_empty_config()
    - _apply_hardcoded_defaults()
    - _load_system_config()      # 从 DB 加载系统配置
    - _load_risk_config()        # 从 DB 加载风控配置
    - _load_strategies_from_db() # 从 DB 加载策略
    - _build_notification_config() # 从 DB 构建通知配置
    - update_risk_config()       # 更新风控配置到 DB
    - save_strategy()            # 保存策略到 DB
    - delete_strategy()          # 从 DB 删除策略
    - _log_config_change()       # 记录配置历史
    - get_backtest_configs()     # 获取回测配置
    - save_backtest_configs()    # 保存回测配置
    - import_from_yaml()         # 从 YAML 导入
    - export_to_yaml()           # 导出到 YAML
    
    # ================================
    # 职责 3: 业务逻辑层 (Service)
    # ================================
    - get_core_config()          # 获取核心配置 (含缓存)
    - get_core_config_async()
    - get_user_config()          # 获取用户配置 (含合并)
    - get_user_config_sync()
    - _build_user_config_dict()  # 构建用户配置字典
    - _create_default_user_config()
    - reload_all_configs_from_db()
    - update_user_config()       # 更新用户配置 (含验证)
    - update_risk_config()       # 更新风控配置 (含快照)
    
    # ================================
    # 职责 4: 解析层 (Parser)
    # ================================
    - _load_core_config_from_yaml()  # YAML 解析
    - _load_user_config_from_yaml()
    
    # ================================
    # 职责 5: 辅助功能
    # ================================
    - add_observer()             # 观察者模式
    - remove_observer()
    - _notify_observers()
    - _safe_observer_call()
    - set_snapshot_service()     # 依赖注入
    - set_config_entry_repository()
    - set_config_profile_repository()
    - get_config_version()       # 版本号管理
    - assert_initialized()       # 初始化检查
    - is_initialized()
    - close()                    # 资源清理
```

### 2.2 依赖方分析

通过 `grep -r "from.*config_manager import|import.*ConfigManager"` 识别出 **57 个调用方文件**：

#### 2.2.1 核心模块 (高优先级)

| 文件 | 使用方式 | 依赖方法 | 风险等级 |
|------|----------|----------|----------|
| `src/main.py` | 启动入口 | `initialize_from_db()`, `get_core_config()`, `get_user_config()` | 🔴 高 |
| `src/interfaces/api.py` | API 端点 | `get_user_config()`, `update_user_config()`, `get_backtest_configs()` 等 20+ 处 | 🔴 高 |
| `src/application/signal_pipeline.py` | 信号管道 | `get_core_config()`, `get_user_config_sync()`, `add_observer()` | 🔴 高 |
| `src/application/backtester.py` | 回测引擎 | 隔离配置，不直接依赖 | 🟢 低 |
| `src/application/config_snapshot_service.py` | 快照服务 | 被 ConfigManager 注入 | 🟡 中 |

#### 2.2.2 测试文件 (中优先级)

| 文件类别 | 文件数量 | 主要测试内容 |
|----------|----------|--------------|
| 单元测试 | ~8 个 | `test_config_manager*.py` |
| 集成测试 | ~5 个 | `test_config_*.py`, `test_hot_reload.py` |
| 并发测试 | ~5 个 | `test_concurrent_*.py` |
| E2E 测试 | ~5 个 | `test_phase5_*.py`, `test_api_*.py` |

#### 2.2.3 其他模块

| 文件 | 使用方式 | 风险等级 |
|------|----------|----------|
| `src/infrastructure/repositories/*.py` | Repository 层 | 🟢 低 |
| `tests/backtest.py` | 回测脚本 | 🟢 低 |
| `scripts/*.py` | 工具脚本 | 🟢 低 |

### 2.3 数据库表依赖

ConfigManager 操作 7 张核心配置表：

| 表名 | 操作方法 | 是否需要迁移 |
|------|----------|--------------|
| `strategies` | CRUD | 否 |
| `risk_configs` | CRUD | 否 |
| `system_configs` | CRUD | 否 |
| `symbols` | Read | 否 |
| `notifications` | Read | 否 |
| `config_snapshots` | Read (通过服务) | 否 |
| `config_history` | Write | 否 |

**结论**: 数据库表结构无需调整，重构仅涉及应用层代码。

---

## 3. 改造范围清单

### 3.1 文件操作清单

#### 新增文件 (6-8 个)

| 文件路径 | 职责 | 预计行数 |
|----------|------|----------|
| `src/application/config/__init__.py` | 包初始化 | ~20 |
| `src/application/config/config_service.py` | 服务层 | ~300 |
| `src/application/config/config_repository.py` | 仓库层 | ~600 |
| `src/application/config/config_parser.py` | 解析层 | ~200 |
| `src/application/config/models.py` | 数据模型 | ~150 |
| `tests/unit/test_config_service.py` | 服务层测试 | ~200 |
| `tests/unit/test_config_repository.py` | 仓库层测试 | ~250 |
| `tests/unit/test_config_parser.py` | 解析层测试 | ~150 |

#### 修改文件 (1 个核心 + 57 个调用方)

| 文件 | 修改类型 | 预计改动行数 |
|------|----------|--------------|
| `src/application/config_manager.py` | 保留适配层 | ~200 (精简至原 15%) |
| `src/main.py` | import 调整 | ~10 |
| `src/interfaces/api.py` | import 调整 | ~10 |
| `src/application/signal_pipeline.py` | import 调整 | ~10 |
| 测试文件 (~15 个) | import 调整 + mock 更新 | ~5-20/文件 |

### 3.2 代码行数影响

| 类别 | 重构前 | 重构后 | 净增 |
|------|--------|--------|------|
| 生产代码 | ~1600 行 | ~1270 行 (拆分到 4 文件) | +~470 行 |
| 测试代码 | ~500 行 | ~800 行 (新增专项测试) | +~300 行 |
| **总计** | **~2100 行** | **~2070 行** | **+~770 行** |

---

## 4. 接口契约设计

### 4.1 ConfigParser (解析层)

```python
class ConfigParser:
    """
    配置解析器 - 负责 YAML/JSON 解析与序列化
    
    职责:
    - YAML ↔ Dict 转换
    - Decimal 精度保持
    - Pydantic 模型验证
    """
    
    # ========== Public API ==========
    
    def parse_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """解析 YAML 文件为字典"""
        ...
    
    def dump_to_yaml(self, data: Dict[str, Any]) -> str:
        """序列化为 YAML 字符串"""
        ...
    
    def parse_core_config(self, data: Dict[str, Any]) -> CoreConfig:
        """解析核心配置"""
        ...
    
    def parse_user_config(self, data: Dict[str, Any]) -> UserConfig:
        """解析用户配置"""
        ...
    
    def parse_risk_config(self, data: Dict[str, Any]) -> RiskConfig:
        """解析风控配置"""
        ...
    
    # ========== Internal Methods ==========
    
    def _decimal_representer(self, dumper, data) -> yaml.Node:
        """Decimal YAML 表示器 (精度保持)"""
        ...
    
    def _decimal_constructor(self, loader, node) -> Decimal:
        """Decimal YAML 构造器"""
        ...
```

### 4.2 ConfigRepository (仓库层)

```python
class ConfigRepository:
    """
    配置仓库 - 负责数据持久化
    
    职责:
    - 数据库连接管理
    - SQL 操作封装
    - 缓存管理 (含 TTL)
    - 文件 I/O
    """
    
    # ========== Lifecycle ==========
    
    async def initialize(self, db_path: str) -> None:
        """初始化数据库连接"""
        ...
    
    async def close(self) -> None:
        """关闭数据库连接"""
        ...
    
    # ========== System Config ==========
    
    async def get_system_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        ...
    
    async def update_system_config(self, config: Dict[str, Any]) -> None:
        """更新系统配置"""
        ...
    
    # ========== Risk Config ==========
    
    async def get_risk_config(self) -> RiskConfig:
        """获取风控配置"""
        ...
    
    async def update_risk_config(self, config: RiskConfig) -> None:
        """更新风控配置"""
        ...
    
    # ========== User Config ==========
    
    async def get_user_config_dict(self) -> Dict[str, Any]:
        """获取用户配置字典 (含合并)"""
        ...
    
    # ========== Strategy CRUD ==========
    
    async def get_all_strategies(self) -> List[StrategyDefinition]:
        """获取所有活跃策略"""
        ...
    
    async def save_strategy(self, strategy: StrategyDefinition) -> str:
        """保存策略 (创建或更新)"""
        ...
    
    async def delete_strategy(self, strategy_id: str) -> bool:
        """删除策略"""
        ...
    
    # ========== Notification Config ==========
    
    async def get_notification_config(self) -> NotificationConfig:
        """获取通知配置"""
        ...
    
    # ========== Backtest Config (KV) ==========
    
    async def get_backtest_configs(self, profile_name: Optional[str] = None) -> Dict[str, Any]:
        """获取回测配置"""
        ...
    
    async def save_backtest_configs(self, configs: Dict[str, Any]) -> int:
        """保存回测配置"""
        ...
    
    # ========== YAML Import/Export ==========
    
    async def import_from_yaml(self, yaml_path: str) -> Dict[str, Any]:
        """从 YAML 导入配置"""
        ...
    
    async def export_to_yaml(self, yaml_path: str, config: Dict[str, Any]) -> None:
        """导出配置到 YAML"""
        ...
    
    # ========== Internal Methods ==========
    
    async def _create_tables(self) -> None:
        """创建数据库表"""
        ...
    
    async def _load_system_config(self) -> Dict[str, Any]:
        """从 DB 加载系统配置"""
        ...
    
    async def _load_risk_config(self) -> RiskConfig:
        """从 DB 加载风控配置"""
        ...
```

### 4.3 ConfigService (服务层)

```python
class ConfigService:
    """
    配置服务 - 负责业务逻辑
    
    职责:
    - 配置验证与合并
    - 热重载通知
    - 配置版本管理
    - 观察者模式
    """
    
    # ========== Lifecycle ==========
    
    async def initialize(self) -> None:
        """初始化服务 (加载默认配置)"""
        ...
    
    def assert_initialized(self) -> None:
        """断言已初始化"""
        ...
    
    # ========== Core Config ==========
    
    def get_core_config(self) -> CoreConfig:
        """获取核心配置 (缓存命中)"""
        ...
    
    async def get_core_config_async(self) -> CoreConfig:
        """异步获取核心配置"""
        ...
    
    # ========== User Config ==========
    
    async def get_user_config(self) -> UserConfig:
        """获取用户配置"""
        ...
    
    def get_user_config_sync(self) -> UserConfig:
        """同步获取用户配置 (降级)"""
        ...
    
    async def update_user_config(
        self,
        config_data: Dict[str, Any],
        auto_snapshot: bool = True,
        snapshot_description: str = "",
        changed_by: str = "user"
    ) -> UserConfig:
        """更新用户配置"""
        ...
    
    # ========== Risk Config ==========
    
    async def update_risk_config(
        self,
        config: RiskConfig,
        changed_by: str = "user"
    ) -> None:
        """更新风控配置"""
        ...
    
    # ========== Strategy Management ==========
    
    async def save_strategy(
        self,
        strategy: StrategyDefinition,
        changed_by: str = "user"
    ) -> str:
        """保存策略"""
        ...
    
    async def delete_strategy(
        self,
        strategy_id: str,
        changed_by: str = "user"
    ) -> bool:
        """删除策略"""
        ...
    
    # ========== Hot Reload ==========
    
    def add_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """添加观察者"""
        ...
    
    def remove_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """移除观察者"""
        ...
    
    # ========== Version Management ==========
    
    def get_config_version(self) -> int:
        """获取配置版本号"""
        ...
    
    # ========== Dependency Injection ==========
    
    def set_snapshot_service(self, snapshot_service: "ConfigSnapshotService") -> None:
        """注入快照服务"""
        ...
    
    def set_config_entry_repository(self, repo: "ConfigEntryRepository") -> None:
        """注入 KV 仓库"""
        ...
```

### 4.4 ConfigManager (适配层 - 保留向后兼容)

```python
class ConfigManager:
    """
    配置管理器 - 向后兼容的适配层
    
    职责:
    - 委托调用 Service/Repository/Parser
    - 保持原有公共 API 不变
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        config_dir: Optional[str] = None,
    ):
        self._service = ConfigService(...)
        self._repository = ConfigRepository(...)
        self._parser = ConfigParser(...)
    
    # ========== 委托方法 (保持 API 兼容) ==========
    
    async def initialize_from_db(self) -> None:
        return await self._service.initialize()
    
    def get_core_config(self) -> CoreConfig:
        return self._service.get_core_config()
    
    async def get_user_config(self) -> UserConfig:
        return await self._service.get_user_config()
    
    async def update_risk_config(self, config: RiskConfig, changed_by: str = "user") -> None:
        return await self._service.update_risk_config(config, changed_by)
    
    # ... 其他委托方法
```

---

## 5. 风险评估

### 5.1 高风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **接口破坏导致调用方故障** | 中 | 高 | 保留 ConfigManager 适配层，保持公共 API 向后兼容 |
| **数据丢失/损坏** | 低 | 高 | 完整测试覆盖 + 快照回滚机制 |
| **并发竞态条件** | 中 | 中 | 保留现有的 asyncio.Lock 机制，增加并发测试 |
| **缓存不一致** | 中 | 中 | 明确缓存失效策略，统一刷新机制 |

### 5.2 中风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **测试用例大量失败** | 高 | 中 | 提前识别依赖，批量更新 mock |
| **循环依赖引入** | 低 | 中 | 预先绘制依赖图，使用依赖注入容器 |
| **性能回退** | 低 | 中 | 性能基准测试，关键路径监控 |

### 5.3 低风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **数据库迁移问题** | 无 | - | 数据库表结构无需变更 |
| **配置文件格式变更** | 无 | - | YAML 格式保持兼容 |

### 5.4 破坏性变更评估

| 变更类型 | 是否破坏 | 说明 |
|----------|----------|------|
| 公共 API 变更 | ❌ 否 | ConfigManager 适配层保持兼容 |
| 数据库表变更 | ❌ 否 | 无表结构变更 |
| 配置文件变更 | ❌ 否 | YAML 格式保持不变 |
| 测试接口变更 | ✅ 是 | 测试代码需更新 mock 对象 |

---

## 6. 数据迁移需求

### 6.1 数据库迁移

**结论**: 无需数据库迁移。

- 现有 7 张配置表保持不变
- SQL 操作逻辑仅内部重构
- 数据格式完全兼容

### 6.2 配置文件迁移

**结论**: 无需配置文件迁移。

- YAML 文件格式保持不变
- 解析逻辑向下兼容

### 6.3 代码迁移

需要进行以下代码迁移：

| 迁移内容 | 源位置 | 目标位置 |
|----------|--------|----------|
| YAML 解析逻辑 | `config_manager.py` | `config_parser.py` |
| 数据库操作 | `config_manager.py` | `config_repository.py` |
| 业务逻辑 | `config_manager.py` | `config_service.py` |
| 缓存管理 | `config_manager.py` | `config_repository.py` |

---

## 7. 测试覆盖需求

### 7.1 新增测试文件

| 测试文件 | 测试内容 | 预计用例数 |
|----------|----------|------------|
| `test_config_parser.py` | YAML 解析、Decimal 精度、模式验证 | 15-20 |
| `test_config_repository.py` | DB 操作、缓存、I/O 异常处理 | 25-30 |
| `test_config_service.py` | 业务逻辑、验证、合并、观察者 | 20-25 |

### 7.2 需要更新的测试文件

| 测试文件 | 需要更新的内容 |
|----------|----------------|
| `test_config_manager.py` | mock 对象更新、import 调整 |
| `test_config_manager_db.py` | repository 层测试迁移 |
| `test_config_manager_db_r93.py` | 并发初始化测试 |
| `test_config_snapshot_service.py` | 服务依赖注入更新 |
| `test_hot_reload.py` | 观察者模式测试 |
| `test_concurrent_*.py` (5 个) | 并发原语更新 |

### 7.3 测试覆盖目标

| 模块 | 行覆盖 | 分支覆盖 | 关键场景 |
|------|--------|----------|----------|
| ConfigParser | > 95% | > 90% | 精度处理、边界值、异常解析 |
| ConfigRepository | > 85% | > 80% | I/O 异常、SQL 错误、缓存失效 |
| ConfigService | > 90% | > 85% | 业务逻辑全覆盖、验证失败场景 |
| ConfigManager (适配层) | > 80% | > 75% | 委托调用正确性 |

---

## 8. 建议实施步骤

### 8.1 阶段划分

```
Week 2 (P1-5 核心重构):
├── Day 1-2: 接口定义 + Parser 层
├── Day 3-4: Repository 层
├── Day 5:   Service 层 + 适配层
└── Day 6:   测试更新 + 回归验证

Week 3 (P1-6 + P1-3):
├── Day 7-8: P1-6 依赖注入 (基于新架构)
├── Day 9:   P1-3 权限增强
└── Day 10:  回归测试 + 文档更新
```

### 8.2 详细实施步骤

#### 阶段 1: 接口定义 + Parser 层 (Day 1-2, 4h)

**任务清单**:
- [ ] 创建 `src/application/config/` 包目录
- [ ] 定义数据模型 (`models.py`)
- [ ] 实现 `ConfigParser` 类
- [ ] 迁移 YAML 解析逻辑
- [ ] 实现 Decimal 精度保持 (复用 P1-1 修复)
- [ ] 编写 Parser 层单元测试

**验收标准**:
- Parser 层测试通过率 100%
- 精度验证测试通过

#### 阶段 2: Repository 层 (Day 3-4, 8h)

**任务清单**:
- [ ] 实现 `ConfigRepository` 类
- [ ] 迁移数据库操作逻辑
- [ ] 迁移缓存管理逻辑
- [ ] 实现 TTL 缓存机制 (P1-2)
- [ ] 迁移 YAML 导入/导出逻辑
- [ ] 编写 Repository 层单元测试

**验收标准**:
- Repository 层测试通过率 100%
- DB 操作正确性验证通过
- 缓存 TTL 机制验证通过

#### 阶段 3: Service 层 + 适配层 (Day 5, 4h)

**任务清单**:
- [ ] 实现 `ConfigService` 类
- [ ] 迁移业务逻辑 (验证、合并、观察者)
- [ ] 迁移配置版本管理
- [ ] 保留 `ConfigManager` 适配层
- [ ] 实现委托方法
- [ ] 编写 Service 层单元测试

**验收标准**:
- Service 层测试通过率 100%
- 适配层兼容性验证通过

#### 阶段 4: 测试更新 + 回归验证 (Day 6, 4h)

**任务清单**:
- [ ] 更新现有测试文件 (import 调整)
- [ ] 更新 mock 对象
- [ ] 运行全量测试套件
- [ ] 性能基准对比
- [ ] 文档更新 (API 文档、架构文档)

**验收标准**:
- 全量测试通过率 100%
- 无性能回退
- 文档完整更新

### 8.3 里程碑

| 里程碑 | 预计完成时间 | 验收标准 |
|--------|--------------|----------|
| M1: Parser 层完成 | Day 2 结束 | Parser 测试 100% 通过 |
| M2: Repository 层完成 | Day 4 结束 | Repository 测试 100% 通过 |
| M3: Service 层完成 | Day 5 结束 | Service 测试 100% 通过 |
| M4: 适配层完成 | Day 5 结束 | 向后兼容验证通过 |
| M5: 全量回归通过 | Day 6 结束 | 全量测试 100% 通过 |

---

## 9. 验收标准

### 9.1 功能验收

| 验收项 | 验证方法 | 状态 |
|--------|----------|------|
| 三层架构实现 | 代码审查确认分层 | ⬜ |
| 依赖关系验证 | 静态分析工具检查 | ⬜ |
| 接口一致性测试 | 对比重构前后 API | ⬜ |
| 向后兼容性 | 现有调用方无需修改 | ⬜ |

### 9.2 性能验收

| 指标 | 基线 | 目标 | 测量方法 |
|------|------|------|----------|
| 配置加载延迟 | P95 < 100ms | P95 < 100ms | 性能测试 |
| 内存使用 | < 50MB | < 50MB | 压力测试 |
| 测试执行时间 | < 5 min | < 5 min | CI 流水线 |

### 9.3 测试覆盖验收

| 模块 | 行覆盖 | 分支覆盖 | 状态 |
|------|--------|----------|------|
| ConfigParser | > 95% | > 90% | ⬜ |
| ConfigRepository | > 85% | > 80% | ⬜ |
| ConfigService | > 90% | > 85% | ⬜ |
| ConfigManager | > 80% | > 75% | ⬜ |

### 9.4 文档验收

- [ ] API 文档更新
- [ ] 架构决策记录 (本文件)
- [ ] 迁移指南 (如有破坏性变更)
- [ ] 测试文档

---

## 10. 附录

### 10.1 相关文件清单

| 文件 | 操作类型 |
|------|----------|
| `docs/arch/ADR-20260407-001-p1-implementation-strategy.md` | 参考 |
| `docs/arch/config-management-p1-implementation-strategy.md` | 参考 |
| `docs/arch/config-management-p0p1-fix-design.md` | 参考 |
| `src/application/config_manager.py` | 重构目标 |
| `src/interfaces/api.py` | 调用方 |
| `src/main.py` | 调用方 |
| `src/application/signal_pipeline.py` | 调用方 |

### 10.3 决策记录

**用户决策确认** (2026-04-07):

| 决策项 | 确认选择 | 理由 |
|--------|----------|------|
| **ConfigManager 处理策略** | ✅ 保留适配层 | 57 个调用方无需修改，降低破坏性 |
| **重构实施策略** | ✅ 一次性重构 | 职责高度耦合，分步迁移成本更高 |
| **实施时间安排** | ✅ 按 6 天分阶段 | Day 1-2 Parser, Day 3-4 Repository, Day 5 Service, Day 6 测试 |

**决策依据**:
- 架构师推荐方案均采纳
- Week 1 并发测试（P1-8）已建立安全网
- 向后兼容优先原则

**下一步行动**:
- 启动 P1-5 实施准备
- 团队任务分配
- 开发环境准备

---

*文档版本: 1.0*  
*创建日期: 2026-04-07*  
*最后更新: 2026-04-07*
