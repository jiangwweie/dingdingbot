# P1-5 Provider 注册模式设计审查报告 (QA 视角)

> **审查日期**: 2026-04-07  
> **审查人**: QA Tester  
> **审查对象**: `docs/arch/P1-5-provider-registration-design.md`  
> **审查焦点**: 可测试性评估 + 测试策略设计

---

## 1. 执行摘要

### 1.1 总体评价

| 评估维度 | 评分 | 说明 |
|----------|------|------|
| **可测试性** | **A-** | Protocol 接口设计优良，少数并发场景需额外关注 |
| **覆盖率目标可行性** | **可行** | Provider 层>85% 可达，ConfigManager >80% 需_mock 辅助_ |
| **风险等级** | **中低** | 3 项 P2 风险，1 项 P1 风险（并发注册） |
| **设计修改建议** | **建议微调** | 增加 Provider 验证钩子，优化并发锁粒度 |

### 1.2 关键发现

**优势** ✅:
1. Protocol 接口定义清晰，4 个方法职责单一，易于 Mock
2. ProviderRegistry 职责聚焦，注册/获取/注销逻辑隔离
3. CachedProvider 基类设计优良，缓存逻辑可独立验证
4. ConfigManager 外观层委托模式，测试时可逐层隔离

**风险** ⚠️:
1. `ProviderRegistry` 懒加载存在竞态条件（多线程/多协程并发首次访问）
2. `CachedProvider` 缓存 TTL 依赖 `datetime.now()`，测试时需要时间模拟
3. 向后兼容别名方法 57 个调用方，存在遗漏测试风险

---

## 2. 可测试性详细评估

### 2.1 Provider Protocol 接口

**设计原文**:
```python
@runtime_checkable
class ConfigProvider(Protocol):
    async def get(self, key: Optional[str] = None) -> Any: ...
    async def update(self, key: str, value: Any) -> None: ...
    async def refresh(self) -> None: ...
    @property
    def cache_ttl(self) -> int: ...
```

| 评估项 | 评分 | 分析 |
|--------|------|------|
| **Mock 友好度** | A+ | 4 个方法签名简洁，无复杂依赖 |
| **类型推导** | A+ | Protocol + `@runtime_checkable` 支持运行时检查 |
| **依赖注入** | A | 接口无隐式依赖，易于替换 |

**测试建议**:
```python
# Mock Provider 实现示例
class MockConfigProvider:
    def __init__(self, initial_data: dict = None):
        self._data = initial_data or {}
        self._cache_ttl = 300
        self.get_call_count = 0
        self.update_call_count = 0
    
    async def get(self, key: Optional[str] = None) -> Any:
        self.get_call_count += 1
        return self._data if key is None else self._data.get(key)
    
    async def update(self, key: str, value: Any) -> None:
        self.update_call_count += 1
        self._data[key] = value
    
    async def refresh(self) -> None:
        pass
    
    @property
    def cache_ttl(self) -> int:
        return self._cache_ttl
```

---

### 2.2 ProviderRegistry 注册机制

**设计原文**:
```python
class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, ConfigProvider] = {}
        self._factory_funcs: Dict[str, Callable[[], ConfigProvider]] = {}
    
    def register(self, name: str, provider: ConfigProvider) -> None: ...
    def register_factory(self, name: str, factory: Callable[[], ConfigProvider]) -> None: ...
    def get_provider(self, name: str) -> ConfigProvider: ...
    def unregister(self, name: str) -> None: ...
```

| 评估项 | 评分 | 分析 |
|--------|------|------|
| **独立测试性** | A | 无外部依赖，可单元测试 |
| **懒加载验证** | B+ | 需要验证首次访问触发工厂函数 |
| **并发安全** | B- | 懒加载存在竞态条件（见风险章节） |

**测试建议**:
```python
class TestProviderRegistry:
    def test_register_and_get(self):
        registry = ProviderRegistry()
        provider = MockConfigProvider()
        registry.register('test', provider)
        assert registry.get_provider('test') is provider
    
    def test_lazy_loading(self):
        registry = ProviderRegistry()
        factory_called = False
        
        def factory():
            nonlocal factory_called
            factory_called = True
            return MockConfigProvider()
        
        registry.register_factory('lazy', factory)
        assert not factory_called  # 注册时不触发
        
        registry.get_provider('lazy')
        assert factory_called  # 首次访问触发
    
    def test_unregister(self):
        registry = ProviderRegistry()
        registry.register('test', MockConfigProvider())
        registry.unregister('test')
        with pytest.raises(KeyError):
            registry.get_provider('test')
```

---

### 2.3 CachedProvider 缓存逻辑

**设计原文**:
```python
class CachedProvider:
    CACHE_TTL_SECONDS = 300
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    def _get_cached(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        if datetime.now() > expires_at:
            del self._cache[key]
            return None
        return value
```

| 评估项 | 评分 | 分析 |
|--------|------|------|
| **缓存命中验证** | A | 逻辑简单，易于断言 |
| **TTL 过期验证** | B | 依赖 `datetime.now()`，需要时间模拟 |
| **缓存失效验证** | A+ | `_invalidate_cache` 方法清晰 |

**测试难点**: TTL 过期测试需要等待或模拟时间

**解决方案**:
```python
import time
from freezegun import freeze_time

class TestCachedProvider:
    @freeze_time("2026-04-07 10:00:00")
    def test_cache_expires(self):
        provider = TestProvider()
        provider._set_cached('key', 'value')
        
        # 5 分钟后，缓存应有效
        frozen_datetime = datetime(2026, 4, 7, 10, 5, 0)
        with freeze_time(frozen_datetime):
            assert provider._get_cached('key') == 'value'
        
        # 6 分钟后，缓存应过期
        frozen_datetime = datetime(2026, 4, 7, 10, 6, 1)
        with freeze_time(frozen_datetime):
            assert provider._get_cached('key') is None
    
    def test_cache_invalidation(self):
        provider = TestProvider()
        provider._set_cached('key', 'value')
        provider._invalidate_cache('key')
        assert provider._get_cached('key') is None
```

**推荐依赖**: `freezegun` 或 `time-machine` 库用于时间模拟

---

### 2.4 ConfigManager 外观层委托

**设计原文**:
```python
class ConfigManager:
    async def get_config(self, name: str, key: Optional[str] = None) -> Any:
        provider = self._registry.get_provider(name)
        return await provider.get(key)
    
    async def get_core_config(self) -> CoreConfig:
        """向后兼容别名"""
        return await self.get_config('core')
```

| 评估项 | 评分 | 分析 |
|--------|------|------|
| **委托逻辑验证** | A+ | 简单直接，易于 Mock 验证 |
| **别名方法测试** | B+ | 57 个调用方需要回归验证 |
| **异常传播** | A | 异常可正确抛出到调用方 |

**测试建议**:
```python
class TestConfigManagerDelegation:
    @pytest.fixture
    def manager_with_mock_providers(self):
        manager = ConfigManager()
        # 替换真实 Provider 为 Mock
        mock_core = MockConfigProvider({'core_symbols': ['BTC', 'ETH']})
        manager._registry.register('core', mock_core)
        return manager
    
    async def test_get_config_delegates_to_provider(self, manager_with_mock_providers):
        result = await manager_with_mock_providers.get_config('core')
        assert result == {'core_symbols': ['BTC', 'ETH']}
        assert manager_with_mock_providers._registry.get_provider('core').get_call_count == 1
    
    async def test_backward_compatible_alias(self, manager_with_mock_providers):
        # 别名方法应委托给新 API
        result = await manager_with_mock_providers.get_core_config()
        assert result == {'core_symbols': ['BTC', 'ETH']}
```

---

## 3. 测试覆盖率目标可行性评估

### 3.1 覆盖率要求 vs 实际可达

| 模块 | 设计要求 | QA 评估 | 达成策略 |
|------|----------|---------|----------|
| **Provider Protocol** | >90% | **可达 95%** | 接口简单，分支少 |
| **ProviderRegistry** | >95% | **可达 95%** | 需覆盖懒加载边界 |
| **CachedProvider** | >90% | **可达 90%** | TTL 边界需要时间模拟 |
| **ConfigManager** | >85% | **可达 85%** | 别名方法多，需回归测试 |

### 3.2 覆盖率难点分析

**难点 1: CachedProvider TTL 边界条件**
```python
# 需要测试的边界场景
- TTL=0（不缓存）
- TTL 刚好过期
- TTL 未过期
- 缓存键不存在
- 缓存被手动失效
```

**解决方案**: 使用 `freezegun` 模拟时间跳跃，避免真实等待

**难点 2: ProviderRegistry 懒加载并发场景**
```python
# 并发首次访问同一 Provider 的竞态条件
async def test_concurrent_lazy_loading():
    registry = ProviderRegistry()
    factory_call_count = 0
    
    def factory():
        nonlocal factory_call_count
        factory_call_count += 1
        return MockConfigProvider()
    
    registry.register_factory('lazy', factory)
    
    # 并发获取（可能触发多次工厂调用）
    await asyncio.gather(
        registry.get_provider('lazy'),
        registry.get_provider('lazy'),
        registry.get_provider('lazy'),
    )
    
    # 期望：只调用一次工厂函数
    # 风险：可能调用多次（竞态条件）
```

**建议**: 设计文档中应明确说明是否保证单例，或添加锁保护

**难点 3: ConfigManager 57 个别名调用方**
- 无法逐一测试每个调用方
- 建议：抽样测试 + 全量回归测试

---

## 4. 风险识别清单

### 4.1 P1 风险（高优先级）

| 风险 ID | 描述 | 影响 | 建议缓解措施 |
|---------|------|------|--------------|
| **R1** | ProviderRegistry 懒加载竞态条件 | 多协程并发首次访问可能创建多个实例 | 添加 `asyncio.Lock` 保护懒加载逻辑 |

**修复建议代码**:
```python
class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, ConfigProvider] = {}
        self._factory_funcs: Dict[str, Callable[[], ConfigProvider]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]
    
    async def get_provider(self, name: str) -> ConfigProvider:
        if name not in self._providers:
            if name in self._factory_funcs:
                async with self._get_lock(name):
                    # Double-check locking
                    if name not in self._providers:
                        provider = self._factory_funcs[name]()
                        self.register(name, provider)
            else:
                raise KeyError(f"Provider '{name}' not registered")
        return self._providers[name]
```

### 4.2 P2 风险（中优先级）

| 风险 ID | 描述 | 影响 | 建议缓解措施 |
|---------|------|------|--------------|
| **R2** | CachedProvider 依赖 `datetime.now()` | 测试难以验证 TTL 过期 | 引入可注入的时钟抽象 |
| **R3** | 向后兼容别名方法可能遗漏测试 | 57 个调用方无法全覆盖 | 回归测试 + 关键路径抽样 |
| **R4** | Provider 缓存失效可能数据不一致 | 更新后缓存未失效 | 在 `update()` 中自动失效缓存 |

**R2 修复建议**:
```python
from typing import Callable

class CachedProvider:
    def __init__(self, clock: Callable[[], datetime] = None):
        self._clock = clock or datetime.now
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    def _get_cached(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        if self._clock() > expires_at:  # 使用注入的时钟
            del self._cache[key])
            return None
        return value
```

### 4.3 P3 风险（低优先级）

| 风险 ID | 描述 | 影响 | 建议缓解措施 |
|---------|------|------|--------------|
| **R5** | ConfigManager 错误处理返回 None | 可能掩盖 Provider 异常 | 增加配置项控制降级行为 |
| **R6** | 扩展 Provider 未实现 Protocol 全部方法 | 运行时才报错 | 增加运行时验证钩子 |

---

## 5. 测试用例设计建议

### 5.1 测试分类总览

| 类别 | 测试数量 | 优先级 | 说明 |
|------|----------|--------|------|
| Provider 注册/注销 | 8 | P0 | 核心功能 |
| Provider 缓存 TTL | 10 | P0 | 关键逻辑 |
| 动态访问测试 | 8 | P1 | 统一 API 验证 |
| 向后兼容测试 | 6 | P1 | 别名方法验证 |
| 并发安全测试 | 6 | P1 | 竞态条件验证 |
| 扩展性验证 | 4 | P2 | 新增 Provider 场景 |
| **合计** | **42** | - | - |

---

### 5.2 Provider 注册/注销测试 (8 个)

```python
class TestProviderRegistration:
    """Provider 注册/注销测试"""
    
    def test_register_provider_success(self):
        """测试成功注册 Provider"""
    
    def test_register_provider_overwrite(self):
        """测试注册覆盖已存在的 Provider"""
    
    def test_get_provider_not_found(self):
        """测试获取不存在的 Provider 抛出 KeyError"""
    
    def test_register_factory_lazy_loading(self):
        """测试工厂函数懒加载"""
    
    def test_unregister_existing_provider(self):
        """测试注销已存在的 Provider"""
    
    def test_unregister_nonexistent_provider(self):
        """测试注销不存在的 Provider（应静默成功）"""
    
    def test_registered_names_property(self):
        """测试 registered_names 属性返回正确列表"""
    
    def test_register_then_get_multiple_providers(self):
        """测试注册多个 Provider 后正确获取"""
```

---

### 5.3 Provider 缓存 TTL 测试 (10 个)

```python
class TestCachedProvider:
    """CachedProvider 缓存 TTL 测试"""
    
    def test_cache_hit_within_ttl(self):
        """测试 TTL 内缓存命中"""
    
    def test_cache_miss_after_ttl(self):
        """测试 TTL 过期后缓存未命中"""
    
    def test_cache_miss_for_nonexistent_key(self):
        """测试不存在的键缓存未命中"""
    
    def test_set_cached_value(self):
        """测试设置缓存值"""
    
    def test_invalidate_specific_key(self):
        """测试使特定键缓存失效"""
    
    def test_invalidate_all_cache(self):
        """测试清空全部缓存"""
    
    def test_cache_ttl_zero_means_no_cache(self):
        """测试 TTL=0 表示不缓存"""
    
    def test_cache_exactly_at_ttl_boundary(self):
        """测试 TTL 边界时刻（刚好过期）"""
    
    def test_refresh_invalidates_cache(self):
        """测试 refresh() 方法使缓存失效"""
    
    def test_concurrent_cache_access(self):
        """测试并发缓存访问安全性"""
```

---

### 5.4 动态访问测试 (8 个)

```python
class TestConfigManagerDynamicAccess:
    """ConfigManager 动态访问测试"""
    
    async def test_get_config_all(self):
        """测试获取全部配置 get_config(name)"""
    
    async def test_get_config_specific_key(self):
        """测试获取特定配置项 get_config(name, key)"""
    
    async def test_update_config(self):
        """测试更新配置 update_config(name, key, value)"""
    
    async def test_get_config_unknown_provider(self):
        """测试获取未知 Provider 的配置（应抛出异常或返回 None）"""
    
    async def test_get_config_provider_returns_none(self):
        """测试 Provider 返回 None 的处理"""
    
    async def test_update_config_propagates_exception(self):
        """测试更新配置时 Provider 异常正确传播"""
    
    async def test_register_provider_extends_access(self):
        """测试注册新 Provider 后可动态访问"""
    
    async def test_get_config_type_verification(self):
        """测试返回值的类型验证"""
```

---

### 5.5 向后兼容测试 (6 个)

```python
class TestBackwardCompatibility:
    """向后兼容别名方法测试"""
    
    async def test_get_core_config_alias(self):
        """测试 get_core_config() 委托给 get_config('core')"""
    
    async def test_get_user_config_alias(self):
        """测试 get_user_config() 委托给 get_config('user')"""
    
    async def test_get_risk_config_alias(self):
        """测试 get_risk_config() 委托给 get_config('risk')"""
    
    async def test_update_risk_config_alias(self):
        """测试 update_risk_config() 委托给 update_config('risk', ...)"""
    
    def test_all_legacy_methods_exist(self):
        """测试所有遗留方法名仍存在"""
    
    def test_legacy_methods_return_types(self):
        """测试遗留方法返回类型正确"""
```

---

### 5.6 并发安全测试 (6 个)

```python
class TestConcurrencySafety:
    """并发安全测试"""
    
    async def test_concurrent_register_same_name(self):
        """测试并发注册同一名称的 Provider"""
    
    async def test_concurrent_get_provider_lazy_load(self):
        """测试并发获取懒加载 Provider（应只创建一次）"""
    
    async def test_concurrent_cache_read_write(self):
        """测试并发缓存读写"""
    
    async def test_concurrent_update_config(self):
        """测试并发更新同一配置项"""
    
    async def test_concurrent_register_and_get(self):
        """测试并发注册和获取操作"""
    
    async def test_async_lock_no_deadlock(self):
        """测试异步锁无死锁（10 并发压力测试）"""
```

---

### 5.7 扩展性验证测试 (4 个)

```python
class TestExtensibility:
    """扩展性验证测试"""
    
    async def test_add_custom_provider(self):
        """测试添加自定义 Provider"""
    
    async def test_custom_provider_with_different_ttl(self):
        """测试自定义 Provider 配置不同 TTL"""
    
    async def test_provider_composition(self):
        """测试 Provider 组合使用"""
    
    async def test_provider_decorator_pattern(self):
        """测试 Provider 装饰器模式（如 CachedProvider 包装其他 Provider）"""
```

---

## 6. 测试数据准备建议

### 6.1 Fixture Provider 实现

**建议创建**: `tests/fixtures/providers.py`

```python
import pytest
from typing import Any, Optional, Dict
from src.application.config.providers.base import CachedProvider


class MockConfigProvider:
    """通用 Mock Provider - 用于测试 ConfigManager"""
    
    def __init__(self, initial_data: Dict[str, Any] = None):
        self._data = initial_data or {}
        self._cache_ttl = 300
        self.get_call_count = 0
        self.update_call_count = 0
        self.refresh_call_count = 0
    
    async def get(self, key: Optional[str] = None) -> Any:
        self.get_call_count += 1
        return self._data if key is None else self._data.get(key)
    
    async def update(self, key: str, value: Any) -> None:
        self.update_call_count += 1
        self._data[key] = value
    
    async def refresh(self) -> None:
        self.refresh_call_count += 1
    
    @property
    def cache_ttl(self) -> int:
        return self._cache_ttl


class FaultyConfigProvider:
    """故障注入 Provider - 用于测试异常处理"""
    
    def __init__(self, raise_on_get: bool = False, raise_on_update: bool = False):
        self.raise_on_get = raise_on_get
        self.raise_on_update = raise_on_update
    
    async def get(self, key: Optional[str] = None) -> Any:
        if self.raise_on_get:
            raise RuntimeError("Simulated get error")
        return {}
    
    async def update(self, key: str, value: Any) -> None:
        if self.raise_on_update:
            raise RuntimeError("Simulated update error")
    
    async def refresh(self) -> None:
        pass
    
    @property
    def cache_ttl(self) -> int:
        return 300


class SlowConfigProvider(CachedProvider):
    """慢速 Provider - 用于测试超时/并发"""
    
    def __init__(self, delay_seconds: float = 0.1):
        super().__init__()
        self.delay_seconds = delay_seconds
    
    async def get(self, key: Optional[str] = None) -> Any:
        await asyncio.sleep(self.delay_seconds)
        return {'slow': 'data'}
    
    async def update(self, key: str, value: Any) -> None:
        await asyncio.sleep(self.delay_seconds)


@pytest.fixture
def mock_core_provider():
    return MockConfigProvider({
        'core_symbols': ['BTC', 'ETH', 'SOL'],
        'core_timeframes': ['15m', '1h', '4h']
    })


@pytest.fixture
def mock_user_provider():
    return MockConfigProvider({
        'api_key': 'test_key',
        'testnet': True
    })


@pytest.fixture
def faulty_provider():
    return FaultyConfigProvider(raise_on_get=True)


@pytest.fixture
def slow_provider():
    return SlowConfigProvider(delay_seconds=0.5)
```

---

### 6.2 Mock Repository 数据策略

**建议创建**: `tests/fixtures/config_data.py`

```python
import pytest
from decimal import Decimal
from typing import Dict, Any


@pytest.fixture
def sample_core_config() -> Dict[str, Any]:
    return {
        'core_symbols': ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
        'core_timeframes': ['15m', '1h', '4h', '1d'],
        'exchange': 'binance',
        'testnet': True,
    }


@pytest.fixture
def sample_user_config() -> Dict[str, Any]:
    return {
        'api_key': 'test_api_key_123456',
        'api_secret': 'test_api_secret_789012',
        'testnet': True,
        'notification_webhook': 'https://example.com/webhook',
    }


@pytest.fixture
def sample_risk_config() -> Dict[str, Any]:
    return {
        'max_loss_percent': Decimal('0.01'),  # 1%
        'max_leverage': 20,
        'default_leverage': 10,
        'cool_down_minutes': 30,
    }


@pytest.fixture
def sample_account_snapshot() -> Dict[str, Any]:
    return {
        'total_balance': Decimal('10000.00'),
        'available_balance': Decimal('8000.00'),
        'unrealized_pnl': Decimal('150.50'),
        'positions': [
            {
                'symbol': 'BTC/USDT:USDT',
                'side': 'LONG',
                'size': Decimal('0.5'),
                'entry_price': Decimal('65000.00'),
            }
        ],
    }
```

---

## 7. 设计修改建议

### 7.1 强烈建议采纳 (P0)

**建议 1**: 为 `ProviderRegistry.get_provider()` 添加并发保护

```python
# 修改前：存在竞态条件
def get_provider(self, name: str) -> ConfigProvider:
    if name not in self._providers:
        if name in self._factory_funcs:
            provider = self._factory_funcs[name]()
            self.register(name, provider)
        else:
            raise KeyError(f"Provider '{name}' not registered")
    return self._providers[name]

# 修改后：双重检查锁定
async def get_provider(self, name: str) -> ConfigProvider:
    if name not in self._providers:
        if name in self._factory_funcs:
            async with self._get_lock(name):
                if name not in self._providers:
                    provider = self._factory_funcs[name]()
                    self.register(name, provider)
        else:
            raise KeyError(f"Provider '{name}' not registered")
    return self._providers[name]
```

---

### 7.2 建议采纳 (P1)

**建议 2**: 为 `CachedProvider` 注入时钟抽象

```python
# 使 TTL 测试更可控
class CachedProvider:
    def __init__(self, clock: Callable[[], datetime] = None):
        self._clock = clock or datetime.now
```

**建议 3**: 在 `ConfigManager` 中添加 Provider 验证钩子

```python
def register_provider(self, name: str, provider: ConfigProvider) -> None:
    # 验证 Provider 是否实现 Protocol
    if not isinstance(provider, ConfigProvider):
        raise TypeError(f"Provider must implement ConfigProvider: {provider}")
    self._registry.register(name, provider)
```

---

### 7.3 可选采纳 (P2)

**建议 4**: 考虑 Provider 生命周期钩子

```python
class ConfigProvider(Protocol):
    async def on_register(self) -> None:
        """Provider 注册时回调"""
        ...
    
    async def on_unregister(self) -> None:
        """Provider 注销时回调"""
        ...
```

---

## 8. 测试文件结构建议

```
tests/
├── unit/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── test_provider_protocol.py       # Protocol 接口测试
│   │   ├── test_provider_registry.py       # Registry 注册测试
│   │   ├── test_cached_provider.py         # 缓存 Provider 测试
│   │   ├── test_config_manager.py          # ConfigManager 外观层测试
│   │   ├── test_config_manager_aliases.py  # 向后兼容别名测试
│   │   └── test_concurrency_safety.py      # 并发安全测试
│   │
│   └── ... (其他现有测试)
│
├── integration/
│   ├── config/
│   │   ├── test_provider_integration.py    # Provider 集成测试
│   │   └── test_config_e2e.py              # 配置端到端测试
│   │
│   └── ... (其他现有测试)
│
└── fixtures/
    ├── providers.py                        # Provider Fixture
    └── config_data.py                      # 配置数据 Fixture
```

---

## 9. 结论

### 9.1 可测试性评分：A-

**评分理由**:
- ✅ Protocol 接口设计优良，Mock 友好
- ✅ 职责分离清晰，可独立测试
- ⚠️ 并发场景需要额外关注
- ⚠️ TTL 缓存需要时间模拟工具

### 9.2 测试策略总结

| 策略 | 说明 |
|------|------|
| **分层测试** | Protocol → Registry → CachedProvider → ConfigManager |
| **Mock 辅助** | 使用 Mock Provider 隔离 ConfigManager 测试 |
| **时间模拟** | 使用 `freezegun` 测试 TTL 缓存 |
| **并发验证** | 使用 `asyncio.gather` 测试并发场景 |
| **回归保障** | 全量测试验证 57 个别名调用方 |

### 9.3 行动建议

**立即行动**:
1. [ ] 采纳建议 1：添加并发锁保护懒加载
2. [ ] 创建测试 Fixture（Mock Provider + 配置数据）
3. [ ] 安装 `freezegun` 或 `time-machine` 用于时间模拟

**开发前准备**:
1. [ ] 编写 42 个测试用例（按本设计）
2. [ ] 配置覆盖率检查（Provider 层>85%，ConfigManager>80%）
3. [ ] 准备回归测试计划

---

**审查结论**: 设计整体优良，建议**微调后实施**。主要风险（并发竞态）已有明确缓解方案，测试覆盖率目标可行。

---

*审查人：QA Tester*  
*审查日期：2026-04-07*  
*下次审查：代码实现完成后进行代码审查*
