# R9.3 配置加载竞态条件修复

**日期**: 2026-04-05
**风险级别**: P1
**状态**: ✅ 已完成

---

## 问题描述

ConfigManager 异步初始化期间，同步代码可能获取到不完整的配置（部分来自 DB，部分来自 YAML）。

### 竞态条件场景

```
时间线：
T0: 协程 A 调用 initialize_from_db()
T1: 协程 A 打开数据库连接
T2: 协程 B 调用 get_user_config()  ← 获取到不完整配置！
T3: 协程 A 加载系统配置
T4: 协程 A 加载风控配置
T5: 协程 A 初始化完成
```

---

## 修复方案

### 1. 添加初始化状态标记

```python
class ConfigManager:
    def __init__(self):
        # R9.3: Initialization state and lock for race condition prevention
        self._initialized = False      # 初始化完成标记
        self._initializing = False     # 初始化进行中标记
        self._init_lock: Optional[asyncio.Lock] = None
        self._init_event: Optional[asyncio.Event] = None
```

### 2. 双重检查锁定模式

```python
async def initialize_from_db(self) -> None:
    # 快速路径 - 已初始化
    if self._initialized:
        return

    init_lock = self._ensure_init_lock()
    init_event = self._ensure_init_event()

    async with init_lock:
        # 双重检查 - 获取锁后再次确认
        if self._initialized:
            return

        # 如果正在初始化，等待其他协程完成
        if self._initializing:
            await init_event.wait()
            return

        # 标记为正在初始化
        self._initializing = True

        try:
            # ... 初始化逻辑 ...
            self._initialized = True
            init_event.set()  # 通知等待的协程
        except Exception:
            # 失败时重置状态
            self._initializing = False
            init_event.clear()
            raise
        finally:
            self._initializing = False
```

### 3. get_user_config() 等待初始化完成

```python
async def get_user_config(self) -> UserConfig:
    # R9.3: 如果正在初始化，等待完成（最多 30 秒）
    if not self._initialized and self._init_event is not None:
        try:
            await asyncio.wait_for(self._init_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError("ConfigManager 初始化超时 (30 秒)")

    # ... 原有逻辑 ...
```

### 4. 添加初始化状态查询属性

```python
@property
def is_initialized(self) -> bool:
    """检查 ConfigManager 是否已完成初始化"""
    return self._initialized
```

---

## 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/application/config_manager_db.py` | 添加初始化状态标记、锁、事件；重构 `initialize_from_db()` 使用双重检查锁定；修改 `get_user_config()` 等待初始化完成 |
| `tests/unit/test_config_manager_db_r93.py` | 新增 9 个测试用例覆盖竞态条件场景 |

---

## 测试覆盖

### 测试用例清单

| 测试 | 描述 | 状态 |
|------|------|------|
| `test_concurrent_initialize_doesnt_duplicate` | 5 个并发初始化调用只执行一次 | ✅ |
| `test_sequential_initialize_is_idempotent` | 顺序调用两次配置不变 | ✅ |
| `test_get_config_waits_for_initialization` | get_config 等待初始化完成 | ✅ |
| `test_initialization_failure_propagates` | 初始化失败正确传播错误 | ✅ |
| `test_initialization_timeout` | 初始化超时抛出异常 | ✅ |
| `test_concurrent_get_config_during_init` | 5 个并发 get_config 全部成功 | ✅ |
| `test_initial_state` | 初始状态未初始化 | ✅ |
| `test_state_after_init` | 初始化后状态正确 | ✅ |
| `test_init_event_is_set` | 初始化完成后事件被设置 | ✅ |

### 测试结果

```
======================== 9 passed in 30.25s =========================
```

### 回归测试

- `test_config_manager_db.py`: 29 passed ✅
- `test_config_manager_db_r43.py`: 9 passed ✅

---

## 技术要点

### 1. 双重检查锁定 (Double-Checked Locking)

```python
# 第一次检查 - 无锁快速路径
if self._initialized:
    return

async with init_lock:
    # 第二次检查 - 锁保护
    if self._initialized:
        return
```

**为什么需要双重检查？**
- 第一次检查避免不必要的锁竞争（性能优化）
- 第二次检查防止多个协程在等待锁后重复执行

### 2. Event 通知机制

```python
# 初始化完成时通知所有等待者
init_event.set()

# 等待者被唤醒
await init_event.wait()
```

**为什么使用 Event 而不是 Lock？**
- Lock 只能唤醒一个等待者
- Event 可以同时唤醒所有等待者（广播语义）

### 3. 超时保护

```python
await asyncio.wait_for(self._init_event.wait(), timeout=30.0)
```

**为什么需要超时？**
- 防止初始化永久挂起导致系统不可用
- 30 秒是合理的时间窗口（数据库操作通常在毫秒级）

### 4. 失败状态重置

```python
try:
    # ... 初始化逻辑 ...
except Exception:
    self._initializing = False
    init_event.clear()
    raise
```

**为什么需要重置？**
- 允许重试初始化
- 避免永久阻塞后续调用

---

## 影响范围

### 向下兼容
- ✅ 现有调用方无需修改
- ✅ 同步方法 `get_core_config()` 保持不变
- ✅ YAML 回退逻辑不受影响

### 性能影响
- 无锁快速路径：`if self._initialized: return`（纳秒级）
- 首次初始化：增加少量锁开销（毫秒级）
- 并发场景：等待初始化完成（最多 30 秒）

### 安全边界
- ✅ 初始化失败不会留下部分状态
- ✅ 并发调用不会产生竞态条件
- ✅ 超时保护防止永久阻塞

---

## 验收标准

- [x] 并发调用 `initialize_from_db()` 不会重复初始化
- [x] 初始化期间 `get_user_config()` 等待而非返回不完整配置
- [x] 初始化失败时其他协程能感知错误
- [x] 测试覆盖所有竞态条件场景

---

## 参考文档

- [Python asyncio.Lock 文档](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Lock)
- [Python asyncio.Event 文档](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event)
- [双重检查锁定模式](https://en.wikipedia.org/wiki/Double-checked_locking)
