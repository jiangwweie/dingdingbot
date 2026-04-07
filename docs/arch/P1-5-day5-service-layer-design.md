# P1-5 Day 5: ConfigService 服务层架构设计文档

> **文档状态**: 待评审  
> **创建日期**: 2026-04-07  
> **作者**: 系统架构师  
> **关联 ADR**: [ADR-20260407-001](./ADR-20260407-001-p1-implementation-strategy.md)  
> **前置依赖**: [P1-5 Parser 层](./P1-5-parser-layer-design.md), [P1-5 Repository 层](./P1-5-repository-layer-design.md)

---

## 1. 执行摘要

### 1.1 设计目标

本文档定义 P1-5 ConfigManager 重构的 **Day 5 阶段**——ConfigService 服务层的架构设计与实现规范。

**核心职责**:
- 配置验证与合并（业务逻辑）
- 观察者模式（热重载通知）
- 配置版本管理
- 策略管理（业务规则）
- 风控配置更新（含快照）

**设计原则**:
- **无 I/O**: Service 层不直接执行文件/数据库操作，委托 Repository 层
- **纯业务逻辑**: 仅处理内存中的数据验证、合并、转换
- **依赖倒置**: 通过接口依赖 Repository 和 Parser

### 1.2 三层架构定位

```
┌─────────────────────────────────────────┐
│         Application Layer               │
│  ┌─────────────────────────────────┐    │
│  │      ConfigService              │    │
│  │  - 业务逻辑 (验证、合并、转换)   │    │
│  │  - 无文件操作，纯内存处理       │    │
│  │  - 依赖 ConfigRepository        │    │
│  │  - 预计：~300 行                 │    │
│  └─────────────┬───────────────────┘    │
└────────────────┼────────────────────────┘
                 │ 委托调用
┌────────────────▼────────────────────────┐
│         ConfigRepository                │
│  - 文件 I/O 操作                         │
│  - 数据库操作 (SQL)                      │
│  - 缓存管理 (含 TTL)                    │
│  └─────────────┬───────────────────────┘
└────────────────┼────────────────────────┘
                 │ 委托调用
┌────────────────▼────────────────────────┐
│           ConfigParser                  │
│  - YAML/JSON 解析                       │
│  - Decimal 精度处理                     │
│  - 模式验证                            │
└─────────────────────────────────────────┘
```

### 1.3 与 Repository 层的职责边界

| 职责域 | ConfigService | ConfigRepository |
|--------|---------------|------------------|
| **配置验证** | ✅ Pydantic 模型验证 | ❌ |
| **配置合并** | ✅ 多源配置合并逻辑 | ❌ |
| **业务规则** | ✅ 配置变更业务规则 | ❌ |
| **观察者通知** | ✅ 热重载通知机制 | ❌ |
| **版本号管理** | ✅ 版本号递增 | ❌ |
| **数据库连接** | ❌ | ✅ 连接管理 |
| **SQL 操作** | ❌ | ✅ CRUD 封装 |
| **缓存管理** | ❌ | ✅ TTL 缓存 |
| **文件 I/O** | ❌ | ✅ YAML 读写 |
| **锁机制** | ❌ | ✅ asyncio.Lock |

---

## 2. ConfigService 类设计

### 2.1 类结构

```python
class ConfigService:
    """
    配置服务 - 负责业务逻辑层
    
    Responsibilities:
    - 配置验证与合并
    - 热重载通知（观察者模式）
    - 配置版本管理
    - 策略管理（业务规则）
    - 风控配置更新（含快照）
    
    Architecture:
        ConfigService → ConfigRepository → ConfigParser
    """
```

### 2.2 依赖注入

```python
def __init__(
    self,
    repository: ConfigRepository,
    parser: ConfigParser,
    snapshot_service: Optional["ConfigSnapshotService"] = None,
    config_entry_repo: Optional["ConfigEntryRepository"] = None,
    config_profile_repo: Optional["ConfigProfileRepository"] = None,
):
    """
    初始化 ConfigService.
    
    Args:
        repository: ConfigRepository 实例（必需）
        parser: ConfigParser 实例（必需）
        snapshot_service: ConfigSnapshotService 实例（可选，用于自动快照）
        config_entry_repo: ConfigEntryRepository 实例（可选，用于 KV 配置）
        config_profile_repo: ConfigProfileRepository 实例（可选，用于 Profile 管理）
    """
```

### 2.3 内部状态

```python
# 依赖项
self._repository: ConfigRepository
self._parser: ConfigParser
self._snapshot_service: Optional[ConfigSnapshotService]
self._config_entry_repo: Optional[ConfigEntryRepository]
self._config_profile_repo: Optional[ConfigProfileRepository]

# 观察者模式
self._observers: Set[Callable[[], Awaitable[None]]]

# 配置版本
self._config_version: int

# 日志
self._logger: logging.Logger
```

---

## 3. 接口契约定义

### 3.1 生命周期管理

#### 3.1.1 initialize

```python
async def initialize(self) -> None:
    """
    初始化服务（加载默认配置）。
    
    前置条件:
        - Repository 已初始化
    
    后置条件:
        - 默认配置加载完成
        - 配置版本号初始化为 0
    
    异常:
        - DependencyNotReadyError: Repository 未初始化
    """
```

#### 3.1.2 assert_initialized

```python
def assert_initialized(self) -> None:
    """
    断言服务已初始化。
    
    异常:
        - DependencyNotReadyError: 服务未初始化
    """
```

### 3.2 Core Config 操作

#### 3.2.1 get_core_config

```python
def get_core_config(self) -> CoreConfig:
    """
    获取核心配置（同步，缓存命中）。
    
    返回:
        CoreConfig 配置副本（深拷贝）
    
    异常:
        - DependencyNotReadyError: 服务未初始化
    
    性能特征:
        - O(1) 时间复杂度
        - 返回内存缓存，无 I/O
    """
```

#### 3.2.2 get_core_config_async

```python
async def get_core_config_async(self) -> CoreConfig:
    """
    异步获取核心配置（可能触发数据库加载）。
    
    返回:
        CoreConfig 配置副本（深拷贝）
    
    异常:
        - DependencyNotReadyError: 服务未初始化
    """
```

### 3.3 User Config 操作

#### 3.3.1 get_user_config

```python
async def get_user_config(self) -> UserConfig:
    """
    获取用户配置（含合并逻辑）。
    
    合并顺序:
        1. 加载 YAML 基础配置
        2. 从 Repository 加载系统配置
        3. 从 Repository 加载风控配置
        4. 从 Repository 加载策略列表
        5. 从 Repository 加载通知配置
        6. 合并为完整 UserConfig
    
    返回:
        UserConfig 配置副本（深拷贝）
    
    异常:
        - ValidationError: 配置验证失败时返回默认配置（降级）
    """
```

#### 3.3.2 get_user_config_sync

```python
def get_user_config_sync(self) -> UserConfig:
    """
    同步获取用户配置（降级模式，仅 YAML）。
    
    使用场景:
        - 异步上下文不可用时
        - 日志初始化等早期阶段
    
    返回:
        UserConfig 配置副本（深拷贝）
    """
```

#### 3.3.3 update_user_config

```python
async def update_user_config(
    self,
    config_data: Dict[str, Any],
    auto_snapshot: bool = True,
    snapshot_description: str = "",
    changed_by: str = "user"
) -> UserConfig:
    """
    更新用户配置。
    
    Args:
        config_data: 新配置数据字典
        auto_snapshot: 是否创建自动快照（默认 True）
        snapshot_description: 快照描述（可选）
        changed_by: 变更操作人标识
    
    处理流程:
        1. 验证 config_data 格式
        2. 创建自动快照（如启用）
        3. 委托 Repository 保存配置
        4. 递增配置版本号
        5. 通知观察者
    
    返回:
        更新后的 UserConfig
    
    异常:
        - ValidationError: 配置验证失败
        - RuntimeError: Repository 异常
    """
```

### 3.4 Risk Config 操作

#### 3.4.1 update_risk_config

```python
async def update_risk_config(
    self,
    config: RiskConfig,
    changed_by: str = "user"
) -> None:
    """
    更新风控配置。
    
    Args:
        config: 新 RiskConfig
        changed_by: 变更操作人标识
    
    处理流程:
        1. 验证 RiskConfig 有效性
        2. 创建自动快照（如 snapshot_service 可用）
        3. 委托 Repository 保存到数据库
        4. 记录配置历史
        5. 递增配置版本号
        6. 通知观察者
    
    异常:
        - ValidationError: 配置验证失败
        - FatalStartupError: Repository 未初始化
    """
```

### 3.5 Strategy 管理

#### 3.5.1 save_strategy

```python
async def save_strategy(
    self,
    strategy: StrategyDefinition,
    changed_by: str = "user"
) -> str:
    """
    保存策略（创建或更新）。
    
    Args:
        strategy: StrategyDefinition
        changed_by: 变更操作人标识
    
    处理流程:
        1. 验证策略 ID（如为空则生成 UUID）
        2. 验证 TriggerConfig 和 FilterConfigs
        3. 委托 Repository 保存到数据库
        4. 记录配置历史
        5. 递增配置版本号
        6. 通知观察者
    
    返回:
        策略 ID
    
    异常:
        - ValidationError: 策略验证失败
    """
```

#### 3.5.2 delete_strategy

```python
async def delete_strategy(
    self,
    strategy_id: str,
    changed_by: str = "user"
) -> bool:
    """
    删除策略。
    
    Args:
        strategy_id: 策略 ID
        changed_by: 变更操作人标识
    
    返回:
        True: 删除成功
        False: 策略不存在
    
    处理流程:
        1. 委托 Repository 删除
        2. 记录配置历史
        3. 递增配置版本号
        4. 通知观察者
    """
```

#### 3.5.3 get_all_strategies

```python
async def get_all_strategies(self) -> List[StrategyDefinition]:
    """
    获取所有活跃策略。
    
    返回:
        StrategyDefinition 列表
    
    异常:
        - DependencyNotReadyError: 服务未初始化
    """
```

### 3.6 观察者模式

#### 3.6.1 add_observer

```python
def add_observer(
    self,
    callback: Callable[[], Awaitable[None]]
) -> None:
    """
    添加观察者回调。
    
    Args:
        callback: 异步回调函数，无参数
    
    使用场景:
        - SignalPipeline 重新配置
        - 热重载通知
    """
```

#### 3.6.2 remove_observer

```python
def remove_observer(
    self,
    callback: Callable[[], Awaitable[None]]
) -> None:
    """
    移除观察者回调。
    
    Args:
        callback: 之前添加的回调函数
    """
```

### 3.7 版本管理

#### 3.7.1 get_config_version

```python
def get_config_version(self) -> int:
    """
    获取当前配置版本号。
    
    返回:
        配置版本号（从 0 开始递增）
    
    使用场景:
        - 观察者检测配置是否已更新
        - 缓存失效判断
    """
```

### 3.8 依赖注入

#### 3.8.1 set_snapshot_service

```python
def set_snapshot_service(
    self,
    snapshot_service: "ConfigSnapshotService"
) -> None:
    """
    注入快照服务（用于自动快照）。
    
    Args:
        snapshot_service: ConfigSnapshotService 实例
    """
```

#### 3.8.2 set_config_entry_repository

```python
def set_config_entry_repository(
    self,
    repo: "ConfigEntryRepository"
) -> None:
    """
    注入 KV 配置仓库。
    
    Args:
        repo: ConfigEntryRepository 实例
    """
```

#### 3.8.3 set_config_profile_repository

```python
def set_config_profile_repository(
    self,
    repo: "ConfigProfileRepository"
) -> None:
    """
    注入 Profile 管理仓库。
    
    Args:
        repo: ConfigProfileRepository 实例
    """
```

---

## 4. 关键技术设计

### 4.1 观察者模式的异步通知机制

#### 4.1.1 设计要点

```python
async def _notify_observers(self) -> None:
    """
    通知所有观察者（配置变更时调用）。
    
    设计要点:
    1. 配置版本号先递增，再通知观察者
    2. 使用 asyncio.gather 并发调用所有观察者
    3. 捕获异常，防止单个观察者失败影响其他观察者
    4. 记录失败观察者的日志
    """
    if not self._observers:
        return
    
    # 递增版本号
    self._config_version += 1
    self._logger.debug(f"Configuration version updated to {self._config_version}")
    
    # 并发通知所有观察者
    results = await asyncio.gather(
        *[self._safe_observer_call(cb) for cb in self._observers],
        return_exceptions=True
    )
    
    # 记录失败的观察者
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            self._logger.error(f"Observer {i} failed: {result}")
```

#### 4.1.2 安全回调封装

```python
async def _safe_observer_call(
    self,
    callback: Callable[[], Awaitable[None]]
) -> Any:
    """
    安全调用观察者回调，捕获所有异常。
    
    Args:
        callback: 观察者回调函数
    
    返回:
        回调执行结果
    
    异常:
        所有异常被捕获并记录日志
    """
    try:
        return await callback()
    except Exception as e:
        self._logger.error(f"Observer callback raised: {e}")
        raise  # 重新抛出以便 _notify_observers 记录
```

#### 4.1.3 观察者注册示例

```python
# SignalPipeline 注册观察者
async def reload_signal_pipeline():
    """重新加载信号管道配置"""
    config = config_service.get_core_config()
    await signal_pipeline.reconfigure(config.signal_pipeline)

config_service.add_observer(reload_signal_pipeline)
```

### 4.2 ConfigManager 适配层的委托策略

#### 4.2.1 适配器模式

ConfigManager 保留为向后兼容的适配层，所有方法委托给 Service/Repository/Parser：

```python
class ConfigManager:
    """向后兼容的适配层"""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        config_dir: Optional[str] = None,
    ):
        # 初始化三层架构
        self._parser = ConfigParser()
        self._repository = ConfigRepository()
        self._service = ConfigService(
            repository=self._repository,
            parser=self._parser,
        )
        
        # 保存路径供 Repository 使用
        self._db_path = db_path
        self._config_dir = config_dir
    
    async def initialize_from_db(self) -> None:
        """委托给 Repository.initialize()"""
        await self._repository.initialize(
            db_path=self._db_path,
            config_dir=self._config_dir
        )
        await self._service.initialize()
    
    def get_core_config(self) -> CoreConfig:
        """委托给 Service.get_core_config()"""
        return self._service.get_core_config()
    
    async def get_user_config(self) -> UserConfig:
        """委托给 Service.get_user_config()"""
        return await self._service.get_user_config()
    
    async def update_risk_config(
        self,
        config: RiskConfig,
        changed_by: str = "user"
    ) -> None:
        """委托给 Service.update_risk_config()"""
        await self._service.update_risk_config(config, changed_by)
    
    # ... 其他委托方法
```

#### 4.2.2 委托方法清单

| ConfigManager 方法 | 委托目标 |
|-------------------|----------|
| `initialize_from_db()` | `Repository.initialize()` + `Service.initialize()` |
| `get_core_config()` | `Service.get_core_config()` |
| `get_core_config_async()` | `Service.get_core_config_async()` |
| `get_user_config()` | `Service.get_user_config()` |
| `get_user_config_sync()` | `Service.get_user_config_sync()` |
| `update_risk_config()` | `Service.update_risk_config()` |
| `save_strategy()` | `Service.save_strategy()` |
| `delete_strategy()` | `Service.delete_strategy()` |
| `add_observer()` | `Service.add_observer()` |
| `remove_observer()` | `Service.remove_observer()` |
| `get_config_version()` | `Service.get_config_version()` |
| `set_snapshot_service()` | `Service.set_snapshot_service()` |
| `import_from_yaml()` | `Repository.import_from_yaml()` |
| `export_to_yaml()` | `Repository.export_to_yaml()` |
| `get_backtest_configs()` | `Service` 或 `Repository`（取决于实现） |
| `save_backtest_configs()` | `Service` 或 `Repository`（取决于实现） |

### 4.3 错误处理策略

#### 4.3.1 异常分类

```python
from src.domain.exceptions import (
    FatalStartupError,      # 致命错误，系统无法启动
    DependencyNotReadyError, # 依赖未就绪
)

# Pydantic 验证异常
from pydantic import ValidationError
```

#### 4.3.2 错误处理矩阵

| 场景 | 异常类型 | 处理策略 |
|------|----------|----------|
| Repository 未初始化 | `DependencyNotReadyError` | 抛出，调用方处理 |
| 配置验证失败 | `ValidationError` | 降级到默认配置 |
| 数据库操作失败 | `aiosqlite.Error` | Repository 捕获，抛出业务异常 |
| YAML 解析失败 | `yaml.YAMLError` | Parser 捕获，返回默认配置 |
| 观察者回调失败 | `Exception` | 记录日志，继续通知其他观察者 |
| 快照服务失败 | `Exception` | 记录警告，继续配置更新 |

#### 4.3.3 错误处理示例

```python
async def get_user_config(self) -> UserConfig:
    """获取用户配置，验证失败时降级"""
    try:
        # 构建配置字典
        config_dict = await self._repository.get_user_config_dict()
        
        # 验证并返回
        return self._parser.parse_user_config(config_dict)
    
    except ValidationError as e:
        self._logger.error(f"UserConfig 验证失败，使用默认配置：{e}")
        return self._parser.create_default_user_config()
    
    except Exception as e:
        self._logger.error(f"获取用户配置失败：{e}")
        raise DependencyNotReadyError(f"无法获取用户配置：{e}", "F-003")
```

### 4.4 并发安全考虑

#### 4.4.1 锁策略

- **Repository 层持有所有锁**: `asyncio.Lock` 用于数据库操作和缓存更新
- **Service 层无锁**: 业务逻辑为纯内存操作，无并发竞争
- **ConfigManager 适配层无锁**: 委托调用由下层保证线程安全

#### 4.4.2 配置版本一致性

```python
async def _notify_observers(self) -> None:
    """
    配置版本递增与通知的原子性保证。
    
    注意：版本号递增在 Repository 层锁内完成，
    观察者通知在锁外并发执行。
    """
    # Repository 层保证原子性
    async with self._repository._ensure_lock():
        # 数据库更新
        await self._repository.update_risk_config(config)
        # 版本号递增
        self._config_version += 1
    
    # 锁外通知观察者（避免长持有锁）
    await self._notify_observers()
```

#### 4.4.3 深拷贝返回

```python
def get_core_config(self) -> CoreConfig:
    """返回配置副本，防止外部修改影响内部状态"""
    cached_config = self._repository.get_cached_config()
    return copy.deepcopy(cached_config)  # 深拷贝
```

---

## 5. 数据流图

### 5.1 配置加载流程

```
┌─────────────────────────────────────────────────────────────┐
│                    get_user_config()                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Service 层：验证初始化状态                              │
│     assert_initialized()                                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Repository 层：构建配置字典                             │
│     get_user_config_dict()                                  │
│  ├── _load_user_config_from_yaml()  ← Parser               │
│  ├── _load_system_config()         ← DB                    │
│  ├── _load_risk_config()           ← DB                    │
│  ├── _load_strategies_from_db()    ← DB                    │
│  └── _build_notification_config()  ← DB                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Parser 层：验证并返回 Pydantic 模型                       │
│     parse_user_config(config_dict)                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Service 层：返回深拷贝                                  │
│     return copy.deepcopy(config)                            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 配置更新流程

```
┌─────────────────────────────────────────────────────────────┐
│  update_risk_config(config, changed_by)                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Service 层：验证配置有效性                              │
│     (Pydantic 模型已验证)                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Service 层：创建自动快照（可选）                        │
│     if self._snapshot_service:                              │
│         await snapshot_service.create_auto_snapshot()       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Repository 层：保存数据库（锁内操作）                   │
│     async with self._ensure_lock():                         │
│         await self._db.execute("UPDATE risk_configs ...")   │
│         await self._log_config_change(...)                  │
│         self._risk_config_cache = config                    │
│         self._config_version += 1                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Service 层：通知观察者                                  │
│     await self._notify_observers()                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 验收标准

### 6.1 功能验收

| 验收项 | 验证方法 | 状态 |
|--------|----------|------|
| Service 层无 I/O 操作 | 代码审查确认无文件/数据库操作 | ⬜ |
| 委托调用正确性 | 单元测试验证方法调用链 | ⬜ |
| 观察者模式正确性 | 测试热重载通知场景 | ⬜ |
| 配置版本号递增 | 测试每次更新后版本号 +1 | ⬜ |
| 配置验证降级 | 测试无效配置返回默认值 | ⬜ |
| 深拷贝返回 | 测试外部修改不影响内部缓存 | ⬜ |

### 6.2 测试覆盖验收

| 测试类别 | 测试用例数 | 覆盖目标 |
|----------|------------|----------|
| 生命周期测试 | 3-5 | 初始化、断言、并发初始化 |
| Core Config 测试 | 5-8 | 同步/异步获取、缓存命中 |
| User Config 测试 | 8-12 | 获取、更新、验证、合并 |
| Risk Config 测试 | 5-8 | 更新、快照、通知 |
| Strategy 测试 | 8-12 | CRUD、验证、通知 |
| 观察者模式测试 | 5-8 | 添加、移除、通知、异常处理 |
| 版本管理测试 | 3-5 | 版本号递增、一致性 |

### 6.3 性能验收

| 指标 | 基线 | 目标 | 测量方法 |
|------|------|------|----------|
| get_core_config() | < 1ms | < 1ms | 单元测试基准 |
| get_user_config() | < 10ms | < 10ms | 集成测试 |
| update_risk_config() | < 50ms | < 50ms | 集成测试（含快照） |
| 观察者通知延迟 | < 100ms | < 100ms | 并发测试 |

---

## 7. 实施计划

### 7.1 任务清单

- [ ] 创建 `src/application/config/config_service.py`
- [ ] 实现 ConfigService 类核心逻辑
- [ ] 实现观察者模式
- [ ] 实现配置版本管理
- [ ] 实现策略管理方法
- [ ] 实现风控配置更新方法
- [ ] 精简 ConfigManager 为适配层
- [ ] 编写 Service 层单元测试
- [ ] 编写集成测试（热重载场景）
- [ ] 更新调用方测试（import 调整）

### 7.2 文件操作清单

| 文件路径 | 操作类型 | 预计行数 |
|----------|----------|----------|
| `src/application/config/config_service.py` | 新增 | ~300 |
| `src/application/config_manager.py` | 修改（精简） | ~200 (从 1600 行精简) |
| `tests/unit/test_config_service.py` | 新增 | ~200 |
| `tests/integration/test_config_service_integration.py` | 新增 | ~150 |

### 7.3 里程碑

| 里程碑 | 预计完成时间 | 验收标准 |
|--------|--------------|----------|
| M1: ConfigService 核心实现 | Day 5 上午 | 代码审查通过 |
| M2: 适配层精简完成 | Day 5 下午 | 向后兼容验证通过 |
| M3: 单元测试完成 | Day 5 下午 | 测试覆盖率 > 90% |
| M4: 集成测试完成 | Day 5 晚上 | 热重载场景验证通过 |

---

## 8. 风险与缓解

### 8.1 高风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **适配层遗漏方法** | 中 | 高 | 使用 grep 识别所有 Public API，逐一对比 |
| **观察者并发问题** | 中 | 中 | 使用 asyncio.gather + return_exceptions |
| **配置版本不一致** | 低 | 高 | 版本号递增在 Repository 锁内完成 |

### 8.2 中风险点

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **测试覆盖率不足** | 高 | 中 | 提前编写测试用例设计文档 |
| **依赖注入遗漏** | 中 | 中 | 使用类型检查工具验证 |

---

## 9. 附录

### 9.1 ConfigService 完整接口清单

```python
class ConfigService:
    # ========== Lifecycle ==========
    async def initialize(self) -> None
    def assert_initialized(self) -> None
    
    # ========== Core Config ==========
    def get_core_config(self) -> CoreConfig
    async def get_core_config_async(self) -> CoreConfig
    
    # ========== User Config ==========
    async def get_user_config(self) -> UserConfig
    def get_user_config_sync(self) -> UserConfig
    async def update_user_config(...) -> UserConfig
    
    # ========== Risk Config ==========
    async def update_risk_config(...) -> None
    
    # ========== Strategy Management ==========
    async def save_strategy(...) -> str
    async def delete_strategy(...) -> bool
    async def get_all_strategies(...) -> List[StrategyDefinition]
    
    # ========== Hot Reload ==========
    def add_observer(...) -> None
    def remove_observer(...) -> None
    
    # ========== Version Management ==========
    def get_config_version(self) -> int
    
    # ========== Dependency Injection ==========
    def set_snapshot_service(...) -> None
    def set_config_entry_repository(...) -> None
    def set_config_profile_repository(...) -> None
```

### 9.2 参考文件

- [P1-5 影响分析报告](./P1-5-config-manager-refactor-impact-analysis.md)
- [ConfigParser 实现](../../src/application/config/config_parser.py)
- [ConfigRepository 实现](../../src/application/config/config_repository.py)
- [ConfigManager 原始实现](../../src/application/config_manager.py)

---

*文档版本：1.0*  
*创建日期：2026-04-07*  
*最后更新：2026-04-07*
