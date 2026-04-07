# P1-8 并发测试补充 - 任务计划

**创建日期**: 2026-04-07  
**执行人**: QA Tester  
**状态**: 进行中  

---

## 任务目标

- 验证 R9.3 竞态修复的正确性（双重检查锁 + asyncio.Lock）
- 为后续 P1-5/P1-6 重构建立并发安全网
- 补充 12 个并发测试用例

---

## 测试文件结构

```
tests/concurrent/
├── __init__.py                 # 包初始化
├── conftest.py                 # 共享 fixtures
├── test_concurrent_init.py     # 并发初始化测试（3 个用例）
├── test_lock_serialization.py  # 锁序列化测试（3 个用例）
├── test_event_loop_safety.py   # 事件循环安全测试（2 个用例）
├── test_cache_concurrency.py   # 缓存并发测试（2 个用例）
└── test_stress.py              # 压力测试（2 个用例）
```

---

## 测试用例清单（12 个）

### 1. 并发初始化测试 (test_concurrent_init.py)

| 编号 | 测试名称 | 目标 | 状态 |
|------|----------|------|------|
| 1.1 | `test_concurrent_first_load` | 多客户端同时触发首次加载 | ☐ |
| 1.2 | `test_read_during_initialization` | 初始化期间的读取请求 | ☐ |
| 1.3 | `test_initialization_failure_recovery` | 初始化失败后的重试 | ☐ |

### 2. 锁序列化测试 (test_lock_serialization.py)

| 编号 | 测试名称 | 目标 | 状态 |
|------|----------|------|------|
| 2.1 | `test_write_exclusion` | 写操作互斥 | ☐ |
| 2.2 | `test_read_write_separation` | 读写分离 | ☐ |
| 2.3 | `test_lock_timeout` | 锁超时处理 | ☐ |

### 3. 事件循环安全测试 (test_event_loop_safety.py)

| 编号 | 测试名称 | 目标 | 状态 |
|------|----------|------|------|
| 3.1 | `test_no_blocking_sync_calls` | 同步调用阻塞检测 | ☐ |
| 3.2 | `test_asyncio_to_thread_usage` | asyncio.to_thread 正确使用 | ☐ |

### 4. 缓存并发测试 (test_cache_concurrency.py)

| 编号 | 测试名称 | 目标 | 状态 |
|------|----------|------|------|
| 4.1 | `test_cache_update_read_concurrent` | 缓存更新与读取并发 | ☐ |
| 4.2 | `test_cache_invalidation_concurrent` | 缓存失效并发处理 | ☐ |

### 5. 压力测试 (test_stress.py)

| 编号 | 测试名称 | 目标 | 状态 |
|------|----------|------|------|
| 5.1 | `test_high_concurrency_load` | 高并发负载 | ☐ |

---

## 实施步骤

### 步骤 1: 测试基础设施准备 (0.5h)
- [x] 创建测试目录
- [ ] 配置 pytest-asyncio fixtures
- [ ] 创建测试工具函数

### 步骤 2: 并发初始化测试 (1h)
- [ ] 实现 `test_concurrent_first_load`
- [ ] 实现 `test_read_during_initialization`
- [ ] 实现 `test_initialization_failure_recovery`

### 步骤 3: 锁序列化测试 (1h)
- [ ] 实现 `test_write_exclusion`
- [ ] 实现 `test_read_write_separation`
- [ ] 实现 `test_lock_timeout`

### 步骤 4: 事件循环安全测试 (0.5h)
- [ ] 实现 `test_no_blocking_sync_calls`
- [ ] 实现 `test_asyncio_to_thread_usage`

### 步骤 5: 缓存并发测试 (0.5h)
- [ ] 实现 `test_cache_update_read_concurrent`
- [ ] 实现 `test_cache_invalidation_concurrent`

### 步骤 6: 压力测试 (0.5h)
- [ ] 实现 `test_high_concurrency_load`

### 步骤 7: 验证与优化 (1h)
- [ ] 运行全量测试套件
- [ ] 修复 flaky 测试
- [ ] 优化测试执行时间
- [ ] 生成测试报告

---

## 验收标准

| 标准 | 目标值 | 验证方法 |
|------|--------|----------|
| 测试通过率 | 100% | CI 流水线 |
| 测试执行时间 | < 2 分钟 | pytest 计时 |
| 稳定性 | 连续 10 次运行无 flaky | 重复执行 |
| 覆盖率 | 覆盖所有 R9.3 代码路径 | coverage report |

---

## 技术要点

### R9.3 竞态修复机制

```python
# ConfigManager 使用双重检查锁模式
async def initialize_from_db(self):
    # Fast path
    if self._initialized:
        return
    
    # R9.3: Get lock and event
    init_lock = self._ensure_init_lock()
    init_event = self._ensure_init_event()
    
    async with init_lock:
        # Double-check
        if self._initialized:
            return
        
        # If already initializing, wait
        if self._initializing:
            await init_event.wait()
            return
        
        # Mark as initializing
        self._initializing = True
        try:
            # ... initialization logic ...
            self._initialized = True
            init_event.set()
        except Exception:
            self._initializing = False
            init_event.clear()
            raise
```

### 测试关键点

1. **事件循环安全**: `_ensure_init_lock()` 必须为当前事件循环创建锁
2. **双重检查**: 锁内外的两次检查都必须测试到
3. **并发等待**: `_initializing=True` 期间的并发请求应该等待
4. **失败恢复**: 初始化失败后状态必须正确回滚

---

**最后更新**: 2026-04-07
