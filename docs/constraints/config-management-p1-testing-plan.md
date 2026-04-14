# P1-8 并发测试补充计划

## 1. 测试目标

### 1.1 核心目标
- **验证 R9.3 竞态修复**: 确保配置初始化过程中的竞态条件已完全消除
- **建立重构安全网**: 为 P1-5/P1-6 重构提供并发安全保障
- **完善测试覆盖**: 补充当前测试套件缺失的并发场景

### 1.2 验收目标
| 目标 | 指标 | 验证方法 |
|------|------|----------|
| 并发测试通过率 | 100% | CI 流水线 |
| 竞态条件覆盖 | 所有已知场景 | 代码审查 + 测试矩阵 |
| 测试稳定性 | 无 flaky 测试 | 连续 10 次运行 |
| 执行时间 | < 2 分钟 | CI 计时 |

---

## 2. 测试用例设计

### 2.1 并发初始化测试

**测试文件**: `tests/concurrent/test_concurrent_init.py`

#### 测试场景 2.1.1: 多客户端同时触发首次加载
```python
@pytest.mark.asyncio
async def test_concurrent_first_load():
    """
    场景：50 个并发请求同时触发配置首次加载
    
    预期行为:
    - 仅一次实际文件读取
    - 所有请求获得相同配置数据
    - 无异常抛出
    
    验证方法:
    - mock 文件读取，计数调用次数
    - 比较所有返回配置的一致性
    """
```

#### 测试场景 2.1.2: 初始化期间的读取请求
```python
@pytest.mark.asyncio
async def test_read_during_initialization():
    """
    场景：配置初始化过程中，有读取请求到达
    
    预期行为:
    - 读取请求等待初始化完成
    - 返回正确的配置数据
    - 无死锁发生
    
    验证方法:
    - 使用 asyncio.Event 控制初始化时机
    - 设置超时断言检测死锁
    """
```

#### 测试场景 2.1.3: 初始化失败后的重试
```python
@pytest.mark.asyncio
async def test_initialization_retry():
    """
    场景：首次初始化失败，触发重试机制
    
    预期行为:
    - 重试不超过最大次数
    - 最终成功或抛出明确异常
    - 状态正确回滚
    
    验证方法:
    - mock 文件读取，控制失败/成功
    - 验证状态机转换
    """
```

### 2.2 锁序列化测试

**测试文件**: `tests/concurrent/test_lock_serialization.py`

#### 测试场景 2.2.1: 写操作互斥
```python
@pytest.mark.asyncio
async def test_write_exclusion():
    """
    场景：多个并发写操作
    
    预期行为:
    - 同一时间仅一个写操作执行
    - 写操作之间无数据竞争
    - 所有写操作最终生效
    
    验证方法:
    - 记录写操作开始/结束时间
    - 验证时间区间无重叠
    """
```

#### 测试场景 2.2.2: 读写分离
```python
@pytest.mark.asyncio
async def test_read_write_separation():
    """
    场景：读操作与写操作并发
    
    预期行为:
    - 读操作不被写操作阻塞 (读 - 读)
    - 写操作获得独占锁 (写 - 读/写互斥)
    - 读取的数据要么全旧要么全新 (无脏读)
    
    验证方法:
    - 使用 asyncio.Semaphore 模拟多读
    - 验证读取数据一致性
    """
```

#### 测试场景 2.2.3: 锁超时处理
```python
@pytest.mark.asyncio
async def test_lock_timeout():
    """
    场景：锁持有时间过长，触发超时
    
    预期行为:
    - 等待方在超时后抛出异常
    - 锁正确释放
    - 无死锁残留
    
    验证方法:
    - mock 长时间持有锁
    - 验证 TimeoutError 抛出
    """
```

### 2.3 事件循环安全测试

**测试文件**: `tests/concurrent/test_event_loop_safety.py`

#### 测试场景 2.3.1: 同步调用阻塞检测
```python
@pytest.mark.asyncio
async def test_no_blocking_sync_calls():
    """
    场景：异步上下文中调用同步阻塞方法
    
    预期行为:
    - 检测到阻塞调用时告警或失败
    - 事件循环不被阻塞
    
    验证方法:
    - 使用 asyncio.get_event_loop().run_in_executor 检测
    - 设置事件循环慢回调检测
    """
```

#### 测试场景 2.3.2: asyncio.to_thread 正确使用
```python
@pytest.mark.asyncio
async def test_asyncio_to_thread_usage():
    """
    场景：I/O 操作通过 to_thread 执行
    
    预期行为:
    - 文件 I/O 在独立线程执行
    - 事件循环不被阻塞
    - 异常正确传播
    
    验证方法:
    - 测量事件循环响应时间
    - 验证异常类型和堆栈
    """
```

#### 测试场景 2.3.3: 协程并发执行
```python
@pytest.mark.asyncio
async def test_concurrent_coroutines():
    """
    场景：多个协程并发执行
    
    预期行为:
    - 使用 asyncio.gather 正确等待
    - 异常正确传播和收集
    - 资源正确清理
    
    验证方法:
    - 验证 gather 返回值顺序
    - 验证异常组包含所有异常
    """
```

### 2.4 缓存并发测试

**测试文件**: `tests/concurrent/test_cache_concurrency.py`

#### 测试场景 2.4.1: 缓存更新与读取并发
```python
@pytest.mark.asyncio
async def test_cache_update_read_concurrent():
    """
    场景：缓存更新过程中有读取请求
    
    预期行为:
    - 读取要么获得旧缓存要么获得新缓存
    - 不会读取到部分更新的数据
    - 缓存一致性保证
    
    验证方法:
    - 原子更新缓存
    - 验证读取数据完整性
    """
```

#### 测试场景 2.4.2: 缓存失效并发处理
```python
@pytest.mark.asyncio
async def test_cache_invalidation_concurrent():
    """
    场景：多个请求同时触发缓存失效
    
    预期行为:
    - 仅一次实际失效操作
    - 其他请求等待失效完成
    - 无重复加载
    
    验证方法:
    - 计数实际加载次数
    - 验证最终缓存状态
    """
```

### 2.5 压力测试

**测试文件**: `tests/concurrent/test_stress.py`

#### 测试场景 2.5.1: 高并发负载
```python
@pytest.mark.asyncio
async def test_high_concurrency_load():
    """
    场景：100+ 并发请求持续 30 秒
    
    预期行为:
    - 无异常抛出
    - 响应时间在可接受范围
    - 内存使用稳定
    
    验证方法:
    - 使用 asyncio.Semaphore 控制并发数
    - 监控内存和响应时间
    """
```

---

## 3. 测试环境要求

### 3.1 pytest-asyncio 配置

**文件**: `pytest.ini` 或 `pyproject.toml`

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
filterwarnings =
    error::pytest.PytestUnraisableExceptionWarning
```

**文件**: `tests/conftest.py`

```python
import pytest
import asyncio

@pytest.fixture
def event_loop_policy():
    """使用默认事件循环策略"""
    return asyncio.DefaultEventLoopPolicy()

@pytest.fixture
async def cleanup_resources():
    """测试后清理资源"""
    yield
    # 清理全局状态
    await asyncio.sleep(0)  # 让出执行权
```

### 3.2 测试隔离策略

#### 全局状态隔离
```python
@pytest.fixture
async def isolated_config_manager():
    """
    为每个测试创建独立的 ConfigManager 实例
    避免全局状态污染
    """
    # 保存原始状态
    original = get_global_state()
    
    # 创建新实例
    cm = ConfigManager.new_instance()
    
    yield cm
    
    # 恢复原始状态
    restore_global_state(original)
```

#### 临时文件隔离
```python
@pytest.fixture
def temp_config_file(tmp_path):
    """
    为每个测试创建临时配置文件
    """
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text(DEFAULT_CONFIG)
    yield config_path
```

#### 时间隔离
```python
@pytest.fixture
def frozen_time():
    """
    冻结时间以消除时间相关的 flaky 测试
    """
    with freeze_time("2026-04-07 12:00:00") as frozen:
        yield frozen
```

### 3.3 并发测试工具

```python
# tests/concurrent/utils.py
import asyncio
import time
from contextlib import asynccontextmanager

@asynccontextmanager
async def measure_concurrency(tasks):
    """测量并发执行的性能指标"""
    start = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.perf_counter() - start
    
    yield {
        "duration": duration,
        "success": sum(1 for r in results if not isinstance(r, Exception)),
        "failures": [r for r in results if isinstance(r, Exception)],
    }

@asynccontextmanager
async def race_detector(timeout=5.0):
    """检测潜在的竞态条件"""
    import traceback
    
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if duration > timeout:
            pytest.fail(f"Potential race condition: operation took {duration}s")
```

---

## 4. 验收标准

### 4.1 测试通过率
- **要求**: 100% 通过率
- **验证**: CI 流水线连续 3 次成功

### 4.2 覆盖场景列表

| 场景分类 | 测试用例数 | 优先级 |
|----------|-----------|--------|
| 并发初始化 | 3 | P0 |
| 锁序列化 | 3 | P0 |
| 事件循环安全 | 3 | P1 |
| 缓存并发 | 2 | P1 |
| 压力测试 | 1 | P2 |
| **总计** | **12** | - |

### 4.3 性能指标

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 测试执行时间 | < 2 分钟 | CI 计时 |
| 并发吞吐量 | > 100 req/s | 压力测试 |
| P99 响应时间 | < 500ms | 压力测试 |
| 内存峰值 | < 100MB | 资源监控 |

### 4.4 稳定性要求

| 要求 | 验证方法 |
|------|----------|
| 无 flaky 测试 | 连续 10 次运行 100% 通过 |
| 无资源泄漏 | 测试前后内存对比 |
| 无死锁 | 所有测试在超时内完成 |

---

## 5. 实施步骤

### 步骤 1: 测试基础设施准备 (0.5h)
- [ ] 配置 pytest-asyncio
- [ ] 创建测试工具函数
- [ ] 设置测试隔离 fixture

### 步骤 2: 并发初始化测试 (1h)
- [ ] 实现 `test_concurrent_first_load`
- [ ] 实现 `test_read_during_initialization`
- [ ] 实现 `test_initialization_retry`

### 步骤 3: 锁序列化测试 (1h)
- [ ] 实现 `test_write_exclusion`
- [ ] 实现 `test_read_write_separation`
- [ ] 实现 `test_lock_timeout`

### 步骤 4: 事件循环安全测试 (0.5h)
- [ ] 实现 `test_no_blocking_sync_calls`
- [ ] 实现 `test_asyncio_to_thread_usage`
- [ ] 实现 `test_concurrent_coroutines`

### 步骤 5: 缓存并发测试 (0.5h)
- [ ] 实现 `test_cache_update_read_concurrent`
- [ ] 实现 `test_cache_invalidation_concurrent`

### 步骤 6: 压力测试 (0.5h)
- [ ] 实现 `test_high_concurrency_load`

### 步骤 7: 验证与优化 (1h)
- [ ] 运行全量测试套件
- [ ] 修复 flaky 测试
- [ ] 优化测试执行时间
- [ ] 更新测试文档

---

## 附录 A: 测试模板

```python
"""
并发测试模板 - 复制此模板创建新的并发测试
"""
import pytest
import asyncio
from typing import List

class TestConcurrencyTemplate:
    """并发测试模板类"""
    
    @pytest.fixture
    async def setup_test(self):
        """测试准备"""
        # 初始化测试数据
        pass
    
    @pytest.mark.asyncio
    async def test_concurrent_scenario(self, setup_test):
        """
        并发测试模板
        
        Arrange: 设置并发任务
        Act: 并发执行
        Assert: 验证结果
        """
        # Arrange
        num_tasks = 10
        tasks: List[asyncio.Task] = []
        
        # Act
        for i in range(num_tasks):
            task = asyncio.create_task(self.concurrent_operation(i))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Assert
        assert all(not isinstance(r, Exception) for r in results)
    
    async def concurrent_operation(self, task_id: int):
        """并发操作实现"""
        pass
```

---

## 附录 B: 参考资料

- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [Python asyncio 并发编程](https://docs.python.org/3/library/asyncio.html)
- [Testing Async Code](https://pytest-asyncio.readthedocs.io/en/latest/how-to-guides/index.html)

---

*文档版本: 1.0*
*创建日期: 2026-04-07*
*预计实施时间：5 小时*
