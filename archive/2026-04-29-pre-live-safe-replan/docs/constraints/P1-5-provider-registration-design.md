# P1-5 Day 5: Provider 注册模式架构设计

> **文档状态**: 已审查 - 待批准  
> **创建日期**: 2026-04-07  
> **修订日期**: 2026-04-07  
> **作者**: 系统架构师  
> **关联 ADR**: [ADR-20260407-001](./ADR-20260407-001-p1-implementation-strategy.md)  
> **预计工时**: 9 小时  
> **QA 审查**: [审查报告](../reviews/p1_5_provider_design_qa_review.md)  

---

## 0. 修订历史

| 版本 | 修订日期 | 修订内容 | 修订原因 |
|------|----------|----------|----------|
| v1.1 | 2026-04-07 | 修复 P0 竞态风险、P1 时钟抽象、P1 Protocol 验证 | QA 审查修复 |
| v1.0 | 2026-04-07 | 初始版本 | - |

**本次修订详情 **(v1.1)
:
- **P0 修复**: ProviderRegistry 添加 `asyncio.Lock` 并发保护，实现双重检查锁定模式
- **P1 修复 #1**: CachedProvider 注入时钟抽象 `ClockProtocol`，支持测试时模拟时间
- **P1 修复 #2**: ConfigManager.register_provider() 添加 Protocol 类型检查

---

## 1. 执行摘要

### 1.1 设计目标

实现**Provider 注册模式**，使配置管理具备高度可扩展性，满足用户核心需求：

> "后期增加 config（如新风控、系统参数），业务层直接通过 `manager.get_config('new_field')` 就可以，不用到处改代码"

### 1.2 核心技术方案

| 设计模式 | 应用场景 |
|----------|----------|
| **外观模式 (Facade)** | `ConfigManager` 作为统一入口，委托调用底层 Provider |
| **Provider 注册** | 动态注册配置提供者，支持零修改扩展 |
| **Protocol 接口** | 定义 Provider 契约，支持静态类型检查 |
| **类型别名** | 保留硬编码方法名，确保向后兼容 |

### 1.3 架构优势

```
┌─────────────────────────────────────────────────────────┐
│                    ConfigManager                        │
│  - get_config(name: str) -> Any    # 统一动态访问       │
│  - update_config(name, value)      # 统一更新           │
│  - get_core_config() -> CoreConfig # 向后兼容别名       │
│  - get_user_config() -> UserConfig # 向后兼容别名       │
│  - register_provider(name, provider)  # 注册新 Provider │
└────────────────────┬────────────────────────────────────┘
                     │ 委托调用
        ┌────────────┼────────────┬────────────────┐
        │            │            │                │
┌───────▼───────┐ ┌──▼────────┐ ┌─▼──────────────┐
│ CoreProvider  │ │UserProvider│ │RiskProvider    │
│ - get()       │ │- get()    │ │- get()         │
│ - update()    │ │- update() │ │- update()      │
│ - cache       │ │- cache    │ │- cache         │
└───────────────┘ └───────────┘ └────────────────┘
```

---

## 2. Provider 注册模式架构设计

### 2.1 ConfigProvider Protocol 接口定义

```python
from typing import Protocol, Any, Optional, TypeVar, runtime_checkable
from typing_extensions import overload

T = TypeVar('T')

@runtime_checkable
class ConfigProvider(Protocol):
    """
    配置提供者协议 - 所有 Provider 必须实现的接口
    
    职责:
    - 提供配置数据访问方法
    - 管理 Provider 级缓存
    - 支持配置更新通知
    """
    
    async def get(self, key: Optional[str] = None) -> Any:
        """
        获取配置数据
        
        Args:
            key: 配置键，None 表示获取全部配置
            
        Returns:
            配置值或配置字典
        """
        ...
    
    async def update(self, key: str, value: Any) -> None:
        """
        更新配置数据
        
        Args:
            key: 配置键
            value: 新值
        """
        ...
    
    async def refresh(self) -> None:
        """刷新缓存（从数据源重新加载）"""
        ...
    
    @property
    def cache_ttl(self) -> int:
        """缓存 TTL（秒），0 表示不缓存"""
        ...
```

### 2.2 Provider 注册机制设计

```python
from typing import Dict, Callable, Awaitable
import asyncio

class ProviderRegistry:
    """
    Provider 注册中心 - 管理所有配置提供者
    
    特性:
    - 动态注册/注销 Provider
    - 按需懒加载 Provider
    - 支持 Provider 装饰器
    - 并发安全（双重检查锁定）
    """
    
    def __init__(self):
        self._providers: Dict[str, ConfigProvider] = {}
        self._factory_funcs: Dict[str, Callable[[], ConfigProvider]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, name: str) -> asyncio.Lock:
        """获取或创建指定 Provider 的锁（懒加载）"""
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]
    
    def register(self, name: str, provider: ConfigProvider) -> None:
        """注册 Provider 实例"""
        self._providers[name] = provider
        logger.info(f"Provider '{name}' registered: {provider}")
    
    def register_factory(self, name: str, factory: Callable[[], ConfigProvider]) -> None:
        """注册 Provider 工厂函数（懒加载）"""
        self._factory_funcs[name] = factory
    
    async def get_provider(self, name: str) -> ConfigProvider:
        """
        获取 Provider 实例（并发安全 - 双重检查锁定）
        
        Args:
            name: Provider 名称
            
        Returns:
            ConfigProvider 实例
            
        Raises:
            KeyError: Provider 不存在
        """
        # 第一次检查（无锁，快速路径）
        if name not in self._providers:
            if name in self._factory_funcs:
                # 获取锁进行懒加载
                async with self._get_lock(name):
                    # 第二次检查（有锁，防止竞态条件）
                    if name not in self._providers:
                        # 懒加载：首次访问时创建
                        provider = self._factory_funcs[name]()
                        self.register(name, provider)
            else:
                raise KeyError(f"Provider '{name}' not registered")
        return self._providers[name]
    
    def unregister(self, name: str) -> None:
        """注销 Provider"""
        self._providers.pop(name, None)
        self._factory_funcs.pop(name, None)
    
    @property
    def registered_names(self) -> list[str]:
        """返回所有已注册的 Provider 名称"""
        return list(self._providers.keys()) + list(self._factory_funcs.keys())
```

### 2.3 动态访问方法（ConfigManager 外观层）

```python
class ConfigManager:
    """
    配置管理器 - 外观模式实现
    
    提供统一的配置访问入口，内部委托给对应的 Provider 处理
    """
    
    def __init__(self):
        self._registry = ProviderRegistry()
        self._register_builtin_providers()
    
    def _register_builtin_providers(self) -> None:
        """注册内置 Provider"""
        from .providers import (
            CoreConfigProvider,
            UserConfigProvider,
            RiskConfigProvider,
        )
        
        self._registry.register('core', CoreConfigProvider())
        self._registry.register('user', UserConfigProvider())
        self._registry.register('risk', RiskConfigProvider())
    
    def register_provider(self, name: str, provider: ConfigProvider) -> None:
        """
        外部 API: 注册新的配置提供者
        
        Usage:
            manager.register_provider('new_risk', NewRiskProvider())
        
        QA 审查修复 (P1 风险):
        - 添加 Protocol 类型检查，防止注册无效 Provider
        """
        # QA 审查修复：验证 Provider 是否实现 ConfigProvider Protocol
        if not isinstance(provider, ConfigProvider):
            raise TypeError(
                f"Provider must implement ConfigProvider protocol. "
                f"Got {type(provider).__name__} which is missing required methods: "
                f"get(), update(), refresh(), cache_ttl property"
            )
        self._registry.register(name, provider)
    
    async def get_config(self, name: str, key: Optional[str] = None) -> Any:
        """
        统一配置访问入口
        
        Usage:
            # 获取全部配置
            core = await manager.get_config('core')
            
            # 获取特定配置项
            symbols = await manager.get_config('core', 'core_symbols')
            
            # 新风控配置（注册后直接使用）
            new_risk = await manager.get_config('new_risk')
        """
        provider = self._registry.get_provider(name)
        return await provider.get(key)
    
    async def update_config(self, name: str, key: str, value: Any) -> None:
        """
        统一配置更新入口
        
        Usage:
            await manager.update_config('risk', 'max_leverage', 20)
        """
        provider = self._registry.get_provider(name)
        await provider.update(key, value)
```

### 2.4 缓存策略（Provider 级缓存）

**QA 审查修复**: 添加时钟抽象注入，解决测试时无法控制时间的问题

```python
from datetime import datetime, timedelta
from typing import Protocol, Optional, Dict, Any, Callable
from functools import wraps

# ========== 时钟抽象（QA 审查修复：P1 风险） ==========

class ClockProtocol(Protocol):
    """时钟协议接口 - 用于依赖注入，使 TTL 测试可控制"""
    
    def now(self) -> datetime:
        """返回当前时间"""
        ...


class SystemClock:
    """系统时钟实现 - 返回真实时间"""
    
    def now(self) -> datetime:
        return datetime.now()


class MockClock:
    """模拟时钟 - 用于测试时控制时间"""
    
    def __init__(self, fixed_time: datetime = None):
        """
        Args:
            fixed_time: 固定的模拟时间，None 表示使用当前时间
        """
        self._fixed_time = fixed_time or datetime.now()
    
    def now(self) -> datetime:
        return self._fixed_time
    
    def advance(self, seconds: int) -> None:
        """推进时间（用于测试 TTL 过期）"""
        from datetime import timedelta
        self._fixed_time += timedelta(seconds=seconds)


# ========== 缓存 Provider 基类 ==========

class CachedProvider:
    """
    带缓存的 Provider 基类
    
    提供 TTL 缓存机制，子类继承后自动获得缓存能力
    
    QA 审查修复:
    - 注入时钟依赖，解决测试时无法验证 TTL 过期逻辑的问题
    """
    
    CACHE_TTL_SECONDS = 300  # 5 分钟默认 TTL
    
    def __init__(self, clock: ClockProtocol = None):
        """
        Args:
            clock: 时钟实现，默认使用 SystemClock
                   测试时可注入 MockClock 控制时间
        """
        self._clock = clock or SystemClock()
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    @property
    def cache_ttl(self) -> int:
        return self.CACHE_TTL_SECONDS
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """获取缓存值，过期则返回 None"""
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        # QA 审查修复：使用注入的时钟而非硬编码 datetime.now()
        if self._clock.now() > expires_at:
            del self._cache[key]
            return None
        return value
    
    def _set_cached(self, key: str, value: Any) -> None:
        """设置缓存值"""
        # QA 审查修复：使用注入的时钟计算过期时间
        expires_at = self._clock.now() + timedelta(seconds=self.cache_ttl)
        self._cache[key] = (value, expires_at)
    
    def _invalidate_cache(self, key: Optional[str] = None) -> None:
        """
        使缓存失效
        
        Args:
            key: 指定键，None 表示清空全部缓存
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)
```

**测试用法示例**:
```python
# 测试 TTL 过期场景
def test_cache_expires():
    from datetime import datetime
    
    # 注入 MockClock，固定在 10:00:00
    mock_clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
    provider = TestProvider(clock=mock_clock)
    
    # 设置缓存
    provider._set_cached('key', 'value')
    
    # 5 分钟后，缓存应有效
    mock_clock.advance(300)  # 10:05:00
    assert provider._get_cached('key') == 'value'
    
    # 再过 1 分钟，缓存应过期（TTL=300 秒）
    mock_clock.advance(61)  # 10:06:01
    assert provider._get_cached('key') is None
```

---

## 3. 模块化文件结构

### 3.1 目录结构

```
src/application/config/providers/
├── __init__.py                    # Provider Protocol + Registry 导出
├── base.py                        # 抽象基类 (CachedProvider)
├── core_config_provider.py        # 核心配置 Provider
├── user_config_provider.py        # 用户配置 Provider
├── risk_config_provider.py        # 风控配置 Provider
└── [新增 Provider 零修改]          # 如 new_risk_config_provider.py

src/application/config/
├── __init__.py                    # 包导出
├── config_manager.py              # 外观层 (统一入口)
├── models.py                      # 配置数据模型 (TypedDict)
└── providers/                     # Provider 模块
```

### 3.2 各文件职责

| 文件 | 职责 | 预计行数 |
|------|------|----------|
| `__init__.py` | Protocol 接口 + Registry 导出 | ~30 |
| `base.py` | 缓存基类 + 通用工具 | ~80 |
| `core_config_provider.py` | 核心配置数据访问 | ~100 |
| `user_config_provider.py` | 用户配置数据访问 | ~120 |
| `risk_config_provider.py` | 风控配置数据访问 | ~100 |
| `config_manager.py` | 外观层 + 注册 API | ~150 |
| `models.py` | TypedDict 类型定义 | ~100 |

### 3.3 新增 Provider 零修改示例

**场景**: 新增 `ExchangeConfig` 配置类别

**仅需 3 步**:

```python
# Step 1: 创建 Provider 文件 src/application/config/providers/exchange_config_provider.py
from .base import CachedProvider
from src.domain.models import ExchangeConfig

class ExchangeConfigProvider(CachedProvider):
    async def get(self, key: Optional[str] = None):
        # 实现数据访问逻辑
        ...
    
    async def update(self, key: str, value: Any):
        # 实现数据更新逻辑
        ...

# Step 2: 在初始化时注册
from src.application.config import ConfigManager
from .providers.exchange_config_provider import ExchangeConfigProvider

manager = ConfigManager()
manager.register_provider('exchange', ExchangeConfigProvider())

# Step 3: 业务层直接使用
exchange_config = await manager.get_config('exchange')
api_key = await manager.get_config('exchange', 'api_key')
```

**对比**: 硬编码方式需要修改 `ConfigManager` 类，添加 `get_exchange_config()` 方法，并更新所有调用方。

---

## 4. 类型安全保障

### 4.1 TypedDict 定义配置类型映射

```python
from typing import TypedDict, Literal, Union, overload

# 配置名称到类型的映射
class ConfigTypes(TypedDict, total=False):
    """配置类型映射表 - 用于静态类型推导"""
    core: CoreConfig
    user: UserConfig
    risk: RiskConfig
    # 可扩展更多类型

# 类型别名用于 IDE 提示
ConfigName = Literal['core', 'user', 'risk']
ConfigValue = Union[CoreConfig, UserConfig, RiskConfig]
```

### 4.2 @overload 装饰器保障 IDE 提示

```python
from typing import overload, Literal

class ConfigManager:
    @overload
    async def get_config(self, name: Literal['core'], key: None = None) -> CoreConfig: ...
    @overload
    async def get_config(self, name: Literal['user'], key: None = None) -> UserConfig: ...
    @overload
    async def get_config(self, name: Literal['risk'], key: None = None) -> RiskConfig: ...
    @overload
    async def get_config(self, name: str, key: None = None) -> Any: ...
    
    @overload
    async def get_config(self, name: Literal['core'], key: Literal['core_symbols']) -> list[str]: ...
    @overload
    async def get_config(self, name: Literal['core'], key: str) -> Any: ...
    
    async def get_config(self, name: str, key: Optional[str] = None) -> Any:
        """实际实现"""
        ...
```

### 4.3 Protocol 类型检查策略

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ConfigProvider(Protocol):
    """运行时可检查的 Protocol"""
    
    async def get(self, key: Optional[str] = None) -> Any: ...
    async def update(self, key: str, value: Any) -> None: ...
    async def refresh(self) -> None: ...
    @property
    def cache_ttl(self) -> int: ...

# 使用场景
def validate_provider(provider: object) -> ConfigProvider:
    """验证对象是否实现了 ConfigProvider 协议"""
    if not isinstance(provider, ConfigProvider):
        raise TypeError(f"Provider must implement ConfigProtocol: {provider}")
    return provider
```

---

## 5. 向后兼容设计

### 5.1 硬编码方法保留为别名

```python
class ConfigManager:
    # ========== 新统一 API ==========
    async def get_config(self, name: str, key: Optional[str] = None) -> Any:
        """统一动态访问入口"""
        ...
    
    async def update_config(self, name: str, key: str, value: Any) -> None:
        """统一更新入口"""
        ...
    
    # ========== 向后兼容别名 ==========
    
    async def get_core_config(self) -> CoreConfig:
        """向后兼容: 委托给 get_config('core')"""
        return await self.get_config('core')
    
    async def get_user_config(self) -> UserConfig:
        """向后兼容: 委托给 get_config('user')"""
        return await self.get_config('user')
    
    async def get_risk_config(self) -> RiskConfig:
        """向后兼容: 委托给 get_config('risk')"""
        return await self.get_config('risk')
    
    async def update_risk_config(self, config: RiskConfig, changed_by: str = "user") -> None:
        """向后兼容: 委托给 update_config('risk', 'global', config)"""
        await self.update_config('risk', 'global', config)
```

### 5.2 ConfigManager 外观层委托

```
调用方                     ConfigManager (外观层)                 Provider (实现层)
                                                                     
get_core_config()  ────►  get_config('core')  ──────────────►  CoreProvider.get()
                          ↓ (委托)
get_user_config()  ────►  get_config('user')  ──────────────►  UserProvider.get()
                          ↓ (委托)
update_risk_config() ───►  update_config('risk', ...) ──────► RiskProvider.update()
```

### 5.3 57 个调用方零破坏验证

| 调用方类别 | 文件数 | 兼容性保证 |
|------------|--------|------------|
| 核心模块 | 5 | 保留所有原有公共 API |
| 测试文件 | ~15 | 原有测试无需修改 |
| 其他模块 | ~37 | import 语句无需调整 |

**验证方法**:
```bash
# 运行全量测试确保零破坏
pytest tests/ -xvs --tb=short
```

---

## 6. 扩展性验证场景

### 6.1 示例：新增 `NewRiskConfig` 仅需 3 步

**需求**: 增加一套独立的风控配置 `new_risk`，支持不同的风控策略

#### 6.1.1 实现步骤

```python
# Step 1: 创建 Provider 实现
# 文件：src/application/config/providers/new_risk_config_provider.py

from typing import Any, Optional, Dict
from .base import CachedProvider
from decimal import Decimal

class NewRiskConfigProvider(CachedProvider):
    """
    新风控配置 Provider
    
    支持独立于原有风控配置的新规则集
    """
    
    CACHE_TTL_SECONDS = 60  # 1 分钟缓存
    
    def __init__(self, db_connection=None):
        super().__init__()
        self._db = db_connection
    
    async def get(self, key: Optional[str] = None) -> Any:
        """获取新风控配置"""
        cache_key = key or '__all__'
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        # 从数据库加载
        config = await self._load_from_db()
        
        if key:
            result = config.get(key)
        else:
            result = config
        
        self._set_cached(cache_key, result)
        return result
    
    async def update(self, key: str, value: Any) -> None:
        """更新新风控配置"""
        await self._save_to_db(key, value)
        self._invalidate_cache(key)
    
    async def _load_from_db(self) -> Dict[str, Any]:
        """从数据库加载配置（示例实现）"""
        return {
            'max_daily_loss': Decimal('0.02'),
            'max_single_trade_loss': Decimal('0.005'),
            'cool_down_minutes': 30,
        }
    
    async def _save_to_db(self, key: str, value: Any) -> None:
        """保存到数据库（示例实现）"""
        # 实际实现需要数据库操作
        pass


# Step 2: 注册 Provider
# 文件：src/application/config_manager.py 或 初始化代码

from .providers.new_risk_config_provider import NewRiskConfigProvider

# 在 ConfigManager 初始化时注册
def _register_builtin_providers(self):
    # ... 原有注册代码 ...
    self._registry.register('new_risk', NewRiskConfigProvider(self._db))


# Step 3: 业务层直接使用
# 文件：任何需要新风控配置的业务代码

# 无需修改任何已有代码，直接使用新配置
new_risk_config = await manager.get_config('new_risk')
max_loss = await manager.get_config('new_risk', 'max_daily_loss')
```

#### 6.1.2 扩展成本对比

| 方案 | 修改文件数 | 修改代码行数 | 调用方迁移 |
|------|------------|--------------|------------|
| **Provider 注册模式** | 2 (新建 Provider + 注册) | ~80 行 | 零迁移 |
| **硬编码模式** | 3+ (ConfigManager + 调用方 + 测试) | ~150+ 行 | 需更新所有调用方 |

---

## 7. 技术要点详解

### 7.1 线程安全与并发控制

```python
import asyncio
from threading import RLock

class ThreadSafeProviderRegistry:
    """线程安全的 Provider 注册表"""
    
    def __init__(self):
        self._providers: Dict[str, ConfigProvider] = {}
        self._lock = RLock()
        self._async_lock: Optional[asyncio.Lock] = None
    
    def _get_async_lock(self) -> asyncio.Lock:
        """懒加载异步锁"""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock
    
    async def register_async(self, name: str, provider: ConfigProvider) -> None:
        """异步注册（线程安全）"""
        async with self._get_async_lock():
            self._providers[name] = provider
    
    def get_provider(self, name: str) -> ConfigProvider:
        """同步获取（线程安全）"""
        with self._lock:
            return self._providers[name]
```

### 7.2 懒加载机制

```python
class LazyProviderWrapper:
    """
    Provider 懒加载包装器
    
    首次访问时才实际创建 Provider 实例
    """
    
    def __init__(self, factory: Callable[[], ConfigProvider]):
        self._factory = factory
        self._instance: Optional[ConfigProvider] = None
        self._lock = threading.Lock()
    
    @property
    def instance(self) -> ConfigProvider:
        """懒加载实例"""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance
    
    def __getattr__(self, name):
        return getattr(self.instance, name)
```

### 7.3 错误处理与降级

```python
class ConfigManager:
    async def get_config(self, name: str, key: Optional[str] = None) -> Any:
        """带错误处理的配置访问"""
        try:
            provider = self._registry.get_provider(name)
            return await provider.get(key)
        except KeyError:
            # Provider 不存在
            logger.warning(f"Provider '{name}' not found, returning None")
            return None
        except Exception as e:
            # Provider 内部错误
            logger.error(f"Provider '{name}' error: {e}")
            # 可配置降级策略：返回缓存、默认值、或抛出异常
            return self._get_default_config(name, key)
```

---

## 8. 实施任务分解

### 8.1 总体计划

```
Day 5-1: Provider 框架实现 (4h)
Day 5-2: 迁移现有配置类型 (2h)
Day 5-3: Provider 层测试 (2h)
Day 5-4: 向后兼容验证 (1h)
```

### 8.2 Day 5-1: Provider 框架实现 (4h)

| 任务 | 描述 | 工时 |
|------|------|------|
| **T1**: 创建 Provider Protocol | 定义 ConfigProvider 接口 + ProviderRegistry | 1h |
| **T2**: 实现 CachedProvider 基类 | TTL 缓存机制 + 线程安全 | 1h |
| **T3**: 实现 ConfigManager 外观层 | 统一 API + 注册方法 | 1h |
| **T4**: 编写框架层测试 | 验证注册机制 + 缓存机制 | 1h |

**验收标准**:
- [ ] Protocol 接口定义完整
- [ ] 可以注册和获取 Provider
- [ ] 缓存 TTL 机制工作正常
- [ ] 测试覆盖率 > 85%

### 8.3 Day 5-2: 迁移现有配置类型 (2h)

| 任务 | 描述 | 工时 |
|------|------|------|
| **T1**: 实现 CoreConfigProvider | 从 config_manager.py 迁移核心配置逻辑 | 0.5h |
| **T2**: 实现 UserConfigProvider | 迁移用户配置逻辑 | 0.5h |
| **T3**: 实现 RiskConfigProvider | 迁移风控配置逻辑 | 0.5h |
| **T4**: 保留向后兼容别名 | 在 ConfigManager 添加委托方法 | 0.5h |

**验收标准**:
- [ ] 3 个内置 Provider 实现完成
- [ ] 原有 API 调用正常
- [ ] 无破坏性变更

### 8.4 Day 5-3: Provider 层单元测试 (2h)

| 任务 | 描述 | 工时 |
|------|------|------|
| **T1**: CoreProvider 测试 | 验证核心配置访问 | 0.5h |
| **T2**: UserProvider 测试 | 验证用户配置访问 | 0.5h |
| **T3**: RiskProvider 测试 | 验证风控配置访问 | 0.5h |
| **T4**: Registry 测试 | 验证注册/注销机制 | 0.5h |

**验收标准**:
- [ ] 所有 Provider 测试通过
- [ ] 边界条件测试覆盖
- [ ] 异常场景测试覆盖

### 8.5 Day 5-4: 向后兼容验证 (1h)

| 任务 | 描述 | 工时 |
|------|------|------|
| **T1**: 57 个调用方扫描 | 确认所有调用方兼容 | 0.5h |
| **T2**: 全量测试运行 | 确保零破坏 | 0.5h |

**验收标准**:
- [ ] 全量测试通过率 100%
- [ ] 无破坏性变更

---

## 9. 架构图

### 9.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        业务层 (Business Layer)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ signal_      │  │ api.py       │  │ main.py      │          │
│  │ pipeline.py  │  │              │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                    ┌───────▼────────┐
                    │  ConfigManager │  ← 外观层 (Facade)
                    │  - get_config() │
                    │  - update_config()
                    │  - register_provider()
                    └───────┬─────────┘
                            │ 委托
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼────────┐  ┌───────▼────────┐
│ Provider       │  │ Provider      │  │ Provider       │
│ Registry       │  │ Registry      │  │ Registry       │
│ (注册中心)      │  │ (注册中心)     │  │ (注册中心)      │
└───────┬────────┘  └──────┬────────┘  └───────┬────────┘
        │                  │                   │
   ┌────┴────┐        ┌───┴────┐         ┌────┴────┐
   │ Core    │        │ User   │         │ Risk    │
   │ Provider│        │ Provider│        │ Provider│
   └────┬────┘        └───┬────┘         └────┬────┘
        │                 │                   │
   ┌────▼─────────────────▼───────────────────▼────┐
   │          Data Access Layer                     │
   │  - SQLite (aiosqlite)                          │
   │  - YAML Fallback                               │
   └────────────────────────────────────────────────┘
```

### 9.2 扩展流程

```
新增配置类别 (如 NewRiskConfig)
         │
         ▼
┌────────────────────────┐
│ 1. 实现 NewRiskProvider │
│    - 继承 CachedProvider│
│    - 实现 get() 方法    │
│    - 实现 update() 方法 │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ 2. 注册 Provider        │
│    manager.register_   │
│    provider('new_risk',│
│              NewRiskProvider())
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ 3. 直接使用             │
│    manager.get_config( │
│      'new_risk')       │
└────────────────────────┘
```

---

## 10. 验收标准

### 10.1 功能验收

| 验收项 | 验证方法 | 状态 |
|--------|----------|------|
| Provider Protocol 定义 | 静态类型检查通过 | ⬜ |
| Provider 注册机制 | 注册后可以正确访问 | ⬜ |
| 缓存 TTL 机制 | 过期后自动刷新 | ⬜ |
| 向后兼容性 | 57 个调用方零破坏 | ⬜ |
| 扩展性验证 | 新增 Provider 仅需 3 步 | ⬜ |

### 10.2 测试覆盖验收

| 模块 | 行覆盖 | 分支覆盖 | 状态 |
|------|--------|----------|------|
| Provider Protocol | > 90% | > 85% | ⬜ |
| ProviderRegistry | > 95% | > 90% | ⬜ |
| CachedProvider | > 90% | > 85% | ⬜ |
| ConfigManager (外观层) | > 85% | > 80% | ⬜ |

### 10.3 性能验收

| 指标 | 基线 | 目标 | 测量方法 |
|------|------|------|----------|
| 配置访问延迟 | P95 < 50ms | P95 < 50ms | 性能测试 |
| 缓存命中率 | > 80% | > 85% | 监控统计 |

---

## 11. 附录

### 11.1 相关文件清单

| 文件 | 操作类型 | 说明 |
|------|----------|------|
| `src/application/config/providers/__init__.py` | 新增 | Provider Protocol 导出 |
| `src/application/config/providers/base.py` | 新增 | 缓存基类 |
| `src/application/config/providers/core_config_provider.py` | 新增 | 核心配置 Provider |
| `src/application/config/providers/user_config_provider.py` | 新增 | 用户配置 Provider |
| `src/application/config/providers/risk_config_provider.py` | 新增 | 风控配置 Provider |
| `src/application/config_manager.py` | 修改 | 添加外观层委托方法 |

### 11.2 决策记录

| 决策项 | 确认选择 | 理由 |
|--------|----------|------|
| **设计模式** | 外观模式 + Provider 注册 | 用户偏好，扩展性最佳 |
| **类型安全** | Protocol + TypedDict + @overload | 保障 IDE 提示 + 静态检查 |
| **向后兼容** | 保留硬编码方法为别名 | 57 个调用方零破坏 |
| **缓存策略** | Provider 级 TTL 缓存 | 各 Provider 可独立配置 |

---

*文档版本：1.1*  
*创建日期: 2026-04-07*  
*最后更新：2026-04-07 (v1.1 - QA 审查修复)*  
*QA 审查：[审查报告](../reviews/p1_5_provider_design_qa_review.md)*
