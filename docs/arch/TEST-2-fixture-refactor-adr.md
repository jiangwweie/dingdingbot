# TEST-2 集成测试 Fixture 重构 ADR

**决策编号**: TEST-2-ADR-001
**决策日期**: 2026-04-03
**决策状态**: 已批准
**决策者**: Architect (架构师)
**实施者**: QA Tester (质量保障专家)

---

## 1. 决策背景和问题陈述

### 问题现象
`tests/integration/test_order_chain_api.py` 集成测试多次执行失败，测试运行时卡住不动，无法完成测试验证。

### 根因分析

**完整根因链**：
```
ASGITransport(app=app)
    ↓ 触发 FastAPI lifespan startup
lifespan() 初始化全局 Repository
    ↓ SignalRepository/ConfigEntryRepository.initialize()
Repository._ensure_lock() 创建 asyncio.Lock
    ↓ Lock 绑定到 lifespan 的事件循环
pytest-asyncio 在另一个事件循环运行测试
    ↓ 测试调用 Repository 方法
尝试获取 Lock (跨事件循环)
    ↓ asyncio.Lock 死锁 → 测试卡住
```

**对比验证**：

| 文件 | 测试客户端 | lifespan | Lock 事件循环 | 测试事件循环 | 结果 |
|------|-----------|----------|--------------|-------------|------|
| `test_strategy_params_api.py` | `TestClient` (同步) | 不触发 | pytest 主循环 | pytest 主循环 | ✅ 22/22 通过 |
| `test_order_chain_api.py` | `httpx.AsyncClient + ASGITransport` | 触发 | ASGITransport 循环 | pytest-asyncio 循环 | ❌ 死锁 |

### 影响评估
- **测试覆盖率**：集成测试无法运行，订单管理 API 完整流程无法验证
- **技术债累积**：任务长期挂着待办，阻塞后续 DEBT-1 和 DEBT-2 任务
- **开发效率**：每次运行测试都需要手动中断，浪费开发时间

---

## 2. 决策内容

**决策**: 采用方案 A（改用 TestClient 同步测试），避免 lifespan 事件循环冲突。

**核心修改**：
1. 将 `async def client(order_repo)` fixture 改为同步 `def client(order_repo)`
2. 使用 `TestClient(app)` 替代 `httpx.AsyncClient + ASGITransport(app)`
3. 手动初始化 SignalRepository、ConfigEntryRepository，避免依赖 lifespan 自动初始化
4. 移除测试方法的 `async def` 和 `@pytest.mark.asyncio` 装饰器

---

## 3. 理由和权衡分析

### 方案对比

#### 方案 A: 改用 TestClient（同步） ⭐⭐⭐⭐⭐（最终选择）

**优点**：
- ✅ **根本解决**：TestClient 不触发 lifespan，彻底避免事件循环冲突
- ✅ **已有验证**：`test_strategy_params_api.py` 22/22 通过证明可行
- ✅ **简单稳定**：FastAPI 官方推荐方式，维护成本低
- ✅ **最小改动**：仅修改 fixture，无需改动应用代码

**缺点**：
- ⚠️ 异步断言需要手动处理（可通过 `asyncio.run()` 解决）
- ⚠️ 无法测试 WebSocket 等纯异步场景（本测试不涉及）

**风险**：**低** - 已有成功案例，实现路径清晰

#### 方案 B: 禁用 lifespan 事件（已拒绝）

**优点**：
- ✅ 保留异步测试能力
- ✅ 避免 lifespan 冲突

**缺点**：
- ❌ **路由复制复杂**：FastAPI router 复制不完整，可能遗漏中间件/异常处理器
- ❌ **维护成本高**：每次 app 结构变化需同步更新测试
- ❌ **隐蔽风险**：可能引入与生产环境不一致的行为

**风险**：**中高** - 路由复制可能导致测试与生产环境行为不一致

**拒绝理由**：测试环境与生产环境行为不一致，维护成本高。

#### 方案 C: 统一事件循环管理（已拒绝）

**风险**：**高** - 框架层配置可能影响整个测试套件

**拒绝理由**：实现复杂度高，可能影响其他集成测试，投入产出比不合理。

### 选择方案 A 的理由

1. **根本解决**：彻底切断 lifespan → asyncio.Lock → 事件循环冲突链
2. **已验证可行**：`test_strategy_params_api.py` 22/22 通过是直接证据
3. **最小改动**：仅修改 fixture，约 20 行代码
4. **官方推荐**：FastAPI 文档明确推荐 TestClient 用于集成测试
5. **实施时间短**：预计 20 分钟完成（fixture 修改 + 验证）

---

## 4. 实施方案

### 修改文件清单

**主要修改文件**：
- `/Users/jiangwei/Documents/final/tests/integration/test_order_chain_api.py` (fixture 和测试方法签名)

**修改范围**：约 20 行代码（fixture 定义 + 测试方法签名）

### 具体修改步骤

#### 步骤 1: 修改 client fixture（第 60-75 行）

**修改前**：
```python
@pytest.fixture
async def client(order_repo):
    """创建异步 HTTP 客户端 - 使用已存在的 Repository

    使用依赖注入方式，避免重复创建 Repository
    """
    # 注入依赖
    set_dependencies(order_repo=order_repo)

    try:
        # 使用 httpx.AsyncClient 进行异步 HTTP 请求
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client
    finally:
        # 重置依赖注入
        set_dependencies(order_repo=None)
```

**修改后**：
```python
@pytest.fixture
def client(order_repo):
    """创建同步 HTTP 测试客户端 - 避免 lifespan 事件循环冲突

    使用 TestClient 避免 ASGITransport 触发 lifespan，
    手动初始化其他 Repository 防止 503 错误
    """
    import asyncio
    from fastapi.testclient import TestClient
    from src.infrastructure.signal_repository import SignalRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository

    # 注入预初始化的 OrderRepository
    set_dependencies(order_repo=order_repo)

    # 手动初始化 SignalRepository（避免 lifespan 自动初始化）
    signal_repo = SignalRepository()
    asyncio.run(signal_repo.initialize())
    set_dependencies(repository=signal_repo)

    # 手动初始化 ConfigEntryRepository
    config_repo = ConfigEntryRepository()
    asyncio.run(config_repo.initialize())
    set_dependencies(config_entry_repo=config_repo)

    try:
        # 使用 TestClient（不触发 lifespan）
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # 重置依赖注入
        set_dependencies(order_repo=None, repository=None, config_entry_repo=None)
```

#### 步骤 2: 移除向后兼容的 fixture（第 78-81 行）

**删除代码**：
```python
@pytest.fixture
async def order_repository(order_repo):
    """向后兼容的 fixture - 返回 Repository 实例"""
    return order_repo
```

**理由**：不再需要向后兼容，所有测试直接使用 `order_repo` fixture。

#### 步骤 3: 调整测试方法签名

**修改规则**：
- 移除所有测试方法的 `async def`，改为 `def`
- 移除所有 `@pytest.mark.asyncio` 装饰器
- 异步断言使用 `asyncio.run()` 包装（如有必要）

**示例修改**：

**修改前**：
```python
@pytest.mark.asyncio
async def test_get_order_tree_full_data(self, client, order_repository, setup_test_order_tree):
    """集成测试：获取完整订单树数据"""
    # 调用 API
    response = await client.get("/api/v3/orders/tree?days=7")
    ...
```

**修改后**：
```python
def test_get_order_tree_full_data(self, client, order_repository, setup_test_order_tree):
    """集成测试：获取完整订单树数据"""
    # 调用 API（同步）
    response = client.get("/api/v3/orders/tree?days=7")
    ...
```

**注意**：`setup_test_order_tree` fixture 仍保持异步，因为需要调用异步 Repository 方法。

#### 步骤 4: 运行验证

```bash
# 执行测试
pytest tests/integration/test_order_chain_api.py -v

# 预期结果
# - 所有测试通过（约 20+ 测试用例）
# - 无卡住现象
# - 响应时间正常（< 1s）
```

---

## 5. 影响范围评估

### 代码改动影响

| 影域 | 影响评估 |
|------|---------|
| **修改文件范围** | 仅 `test_order_chain_api.py`（约 20 行） |
| **生产代码** | **无影响** - 仅测试代码修改 |
| **其他集成测试** | **无影响** - 各测试文件 fixture 独立 |
| **测试覆盖率** | **保持不变** - 同步 TestClient 可覆盖相同断言 |

### 向下兼容性

| 兼容性维度 | 评估 |
|-----------|------|
| **API 行为** | ✅ 100% 兼容 - TestClient 与 AsyncClient HTTP 行为一致 |
| **测试断言** | ✅ 100% 兼容 - 同步/异步断言结果一致 |
| **测试数据** | ✅ 100% 兼容 - fixture 数据准备逻辑不变 |

### 风险控制

| 风险项 | 风控措施 |
|-------|---------|
| **Repository 初始化顺序** | 手动初始化 SignalRepository、ConfigEntryRepository 防止 503 错误 |
| **依赖注入清理** | finally 块确保依赖重置，避免影响其他测试 |
| **测试隔离性** | 临时数据库确保测试数据隔离，不影响其他测试 |

---

## 6. 实施时间估算

| 步骤 | 预计时间 |
|------|----------|
| fixture 修改 | 10 分钟 |
| 测试方法签名调整 | 5 分钟 |
| 运行验证 | 5 分钟 |
| **总计** | **20 分钟** |

---

## 7. 后续任务解除

完成 TEST-2 后，解除以下阻塞任务：
- DEBT-1: 创建 order_audit_logs 表（预计 1.5h）
- DEBT-2: 集成交易所 API 到批量删除（预计 2h，依赖 DEBT-1）

---

## 8. 参考资料

- FastAPI Testing Documentation: https://fastapi.tiangolo.com/tutorial/testing/
- pytest-asyncio Documentation: https://pytest-asyncio.readthedocs.io/
- `test_strategy_params_api.py` 成功案例（第 103-141 行）
- DEBT-6/DEBT-7 技术决策记录（`docs/reviews/AR-20260403-001-lifespan-init-review.md`）

---

*ADR 编写者: Architect (架构师)*
*ADR 审批者: 用户*
*ADR 实施者: QA Tester (质量保障专家)*
*ADR 创建时间: 2026-04-03*