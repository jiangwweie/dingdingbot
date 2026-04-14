# DEBT-3 架构评审请求 - API 依赖注入方案

> **评审日期**: 2026-04-03
> **申请人**: Team Coordinator
> **优先级**: P0 (阻塞测试验证)

---

## 📋 问题背景

### 当前问题

**订单链集成测试 fixture 失败**

**测试文件**: `tests/integration/test_order_chain_api.py` (19 个用例)

**问题现象**:
- API 端点 `get_order_tree` 内部创建 `OrderRepository()` 使用默认数据库路径 `data/v3_dev.db`
- 测试 fixture 创建临时数据库 (`:memory:`)，但 API 不使用它
- 导致测试无法验证数据库操作的正确性

**当前代码** (`src/interfaces/api.py:620-630`):
```python
@app.get("/api/v3/orders/tree")
async def get_order_tree(
    symbol: Optional[str] = None,
    parent_order_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """获取订单树形结构"""
    repository = OrderRepository()  # ❌ 使用默认数据库路径
    try:
        tree = await repository.get_order_tree(
            symbol=symbol,
            parent_order_id=parent_order_id,
            status=status,
            limit=limit
        )
        return {"tree": tree}
    finally:
        await repository.close()
```

**影响范围**:
- ❌ 阻塞订单链集成测试验证 (DEBT-3)
- ❌ 无法验证批量删除功能的数据库操作
- ❌ 无法验证订单树形查询的正确性

---

## 🎯 建议方案

### 方案 A: API 端点支持依赖注入 (推荐)

**核心思路**: 修改 API 端点使用全局依赖注入，与现有 `set_dependencies()` 机制保持一致。

**设计参考**: 已有成功案例 - 策略参数 API (`TEST-1` 已修复)

**成功案例** (`src/interfaces/api.py:set_dependencies`):
```python
# 已修复的策略参数 API
def set_dependencies(repository=None, account_getter=None):
    """设置全局依赖注入"""
    global _config_entry_repo, _account_getter
    _config_entry_repo = repository
    _account_getter = account_getter

# API 端点使用依赖注入
@app.get("/api/strategy/params")
async def get_strategy_params(profile: str = "default"):
    repository = _config_entry_repo or ConfigEntryRepository()  # ✅ 支持注入
    try:
        params = await repository.get_strategy_params(profile)
        return {"profile": profile, "params": params}
    finally:
        if not _config_entry_repo:  # 仅关闭非注入的实例
            await repository.close()
```

---

## 🔧 修改方案详细设计

### 1. 扩展 `set_dependencies()` 函数

**修改位置**: `src/interfaces/api.py:45-50`

**当前代码**:
```python
def set_dependencies(repository=None, account_getter=None):
    """设置全局依赖注入"""
    global _config_entry_repo, _account_getter
    _config_entry_repo = repository
    _account_getter = account_getter
```

**修改为**:
```python
def set_dependencies(
    config_entry_repo=None,
    order_repo=None,
    account_getter=None
):
    """设置全局依赖注入"""
    global _config_entry_repo, _order_repo, _account_getter
    _config_entry_repo = config_entry_repo
    _order_repo = order_repo
    _account_getter = account_getter
```

**影响分析**:
- ✅ 向后兼容：可选参数，不影响现有调用
- ✅ 统一管理：所有 Repository 依赖集中管理
- ⚠️ 需同步修改：所有使用 `repository` 参数名的调用改为 `config_entry_repo`

---

### 2. 修改订单链 API 端点

**修改位置**: `src/interfaces/api.py:620-630`

**当前代码**:
```python
@app.get("/api/v3/orders/tree")
async def get_order_tree(...):
    repository = OrderRepository()  # ❌ 硬编码
    try:
        tree = await repository.get_order_tree(...)
        return {"tree": tree}
    finally:
        await repository.close()
```

**修改为**:
```python
@app.get("/api/v3/orders/tree")
async def get_order_tree(...):
    repository = _order_repo or OrderRepository()  # ✅ 支持注入
    try:
        tree = await repository.get_order_tree(...)
        return {"tree": tree}
    finally:
        if not _order_repo:  # 仅关闭非注入实例
            await repository.close()
```

**影响分析**:
- ✅ 生产环境：`_order_repo` 为 None，使用默认 `OrderRepository()`
- ✅ 测试环境：测试 fixture 注入临时数据库 Repository
- ✅ 资源管理：注入实例不关闭，避免测试数据库提前关闭

---

### 3. 同步修改其他订单 API 端点

**涉及端点** (5 个):
| 端点 | 行号 | 说明 |
|------|------|------|
| `GET /api/v3/orders/tree` | 620-630 | 订单树查询 |
| `GET /api/v3/orders/{order_id}` | 640-650 | 订单详情 |
| `DELETE /api/v3/orders/{order_id}` | 660-670 | 单个删除 |
| `DELETE /api/v3/orders/batch` | 680-690 | 批量删除 |
| `GET /api/v3/orders/{order_id}/klines` | 700-710 | K 线数据 |

**修改模式** (统一模式):
```python
# 所有订单相关端点统一修改
repository = _order_repo or OrderRepository()
try:
    # 业务逻辑
    ...
finally:
    if not _order_repo:
        await repository.close()
```

---

### 4. 修改测试 fixture

**修改位置**: `tests/integration/test_order_chain_api.py:20-40`

**当前 fixture**:
```python
@pytest.fixture
async def order_repository():
    """创建临时数据库 Repository"""
    repo = OrderRepository(db_path=":memory:")
    yield repo
    await repo.close()

@pytest.fixture
def api_client(order_repository):
    """创建测试客户端"""
    # ❌ 无法注入到 API 端点
    client = TestClient(app)
    return client
```

**修改为**:
```python
@pytest.fixture
def api_client():
    """创建测试客户端并注入依赖"""
    # 创建临时数据库 Repository
    repo = OrderRepository(db_path=":memory:")

    # ✅ 注入到全局依赖
    set_dependencies(order_repo=repo)

    # 创建测试客户端
    client = TestClient(app)

    yield client

    # 清理
    repo.close()
    set_dependencies(order_repo=None)  # 重置依赖
```

---

## 📊 影响范围分析

### 1. 生产代码修改

| 文件 | 修改类型 | 风险等级 |
|------|----------|----------|
| `src/interfaces/api.py` | 扩展依赖注入 | 🟢 低风险 |
| - `set_dependencies()` | 参数扩展 | ✅ 向后兼容 |
| - 订单 API 端点 (5 个) | 使用注入 | ✅ 默认行为不变 |

**风险评估**:
- ✅ **向后兼容**: 默认行为与当前完全一致
- ✅ **生产安全**: `_order_repo` 为 None 时使用默认 Repository
- ✅ **测试友好**: 测试可注入临时数据库

---

### 2. 测试代码修改

| 文件 | 修改类型 | 风险等级 |
|------|----------|----------|
| `tests/integration/test_order_chain_api.py` | fixture 修改 | 🟢 低风险 |

**风险评估**:
- ✅ **测试隔离**: 每个测试使用独立临时数据库
- ✅ **资源管理**: fixture 自动清理依赖
- ✅ **并发安全**: 同步 TestClient + 同步 fixture

---

### 3. 依赖模块分析

**相关模块**:
| 模块 | 是否需要修改 | 说明 |
|------|--------------|------|
| `OrderRepository` | ❌ 无需修改 | 已支持自定义 db_path |
| `src/main.py` | ⚠️ 可能修改 | 启动时调用 `set_dependencies()` |
| `其他 API 端点` | ❌ 无需修改 | 仅影响订单相关端点 |

---

## 🎯 架构评审要点

请架构师重点评审以下方面：

### 1. 架构一致性 ✅
- ✅ 与现有 `set_dependencies()` 机制保持一致
- ✅ 与已修复的策略参数 API (`TEST-1`) 模式一致
- ⚠️ 需确认：是否需要统一所有 Repository 的注入机制？

### 2. Clean Architecture 合规性 ✅
- ✅ Interfaces 层依赖 Infrastructure 层 (符合规范)
- ✅ 通过依赖注入实现测试友好 (符合 DI 原则)
- ⚠️ 需确认：全局变量 `_order_repo` 是否符合架构规范？

### 3. 资源管理安全性 ✅
- ✅ 注入实例不提前关闭 (避免数据库连接丢失)
- ✅ 非注入实例正确关闭 (避免资源泄漏)
- ⚠️ 需确认：是否需要显式声明注入实例的生命周期？

### 4. 测试覆盖完整性 ✅
- ✅ 可验证数据库操作的正确性
- ✅ 可验证订单树形查询逻辑
- ✅ 可验证批量删除功能
- ⚠️ 需确认：是否需要补充 E2E 测试？

### 5. 边界情况处理 ✅
- ✅ `_order_repo=None` 默认行为
- ✅ `_order_repo` 异常处理
- ⚠️ 需确认：是否需要添加类型检查？

---

## 📋 需架构师决策的问题

### 问题 1: 全局变量命名规范
**当前命名**: `_order_repo`
**是否需要**: 统一命名规范（如 `_repository_order`）

### 问题 2: 依赖注入扩展策略
**当前策略**: 逐步扩展（仅订单相关）
**是否需要**: 一次性统一所有 Repository 注入机制

### 问题 3: 启动时依赖初始化
**当前状态**: `src/main.py` 未调用 `set_dependencies(order_repo=...)`
**是否需要**: 启动时显式初始化所有依赖

### 问题 4: 类型注解完整性
**当前状态**: `set_dependencies()` 参数缺少类型注解
**是否需要**: 补充完整类型注解
```python
def set_dependencies(
    config_entry_repo: Optional[ConfigEntryRepository] = None,
    order_repo: Optional[OrderRepository] = None,
    account_getter: Optional[Callable] = None
):
```

---

## 🚀 预期收益

### 测试验证收益
- ✅ 解除 DEBT-3 阻塞，可验证订单链功能
- ✅ 提高测试覆盖率：集成测试 19 个用例可执行
- ✅ 验证批量删除数据库操作正确性

### 架构改进收益
- ✅ 统一依赖注入机制，与现有 API 保持一致
- ✅ 提高测试友好性，支持临时数据库注入
- ✅ 资源管理更安全，避免提前关闭数据库

---

## 📅 评审时间线

| 阶段 | 预计时间 | 说明 |
|------|----------|------|
| 架构师评审 | 0.5h | 评审方案并提出修改建议 |
| 代码修改 | 1h | 根据评审意见修改代码 |
| 测试验证 | 0.5h | 运行 19 个测试用例验证 |
| **总计** | **2h** | - |

---

## 📎 附录

### A. 成功案例参考
- `TEST-1` 策略参数 API 修复: 同样使用依赖注入方案，测试从失败到 22/22 通过
- 评审文档: `docs/designs/strategy-params-api-review.md`

### B. 相关文档
- 原始任务计划: `docs/planning/task_plan.md#DEBT-3`
- 订单链契约文档: `docs/designs/order-chain-tree-contract.md`
- API 契约文档: `docs/arch/api-contract.md`

---

**请架构师评审并回复以下内容**:
1. ✅/⚠️ 方案是否通过评审
2. 需要修改的建议（如有）
3. 需补充的边界情况处理（如有）
4. 需补充的类型注解（如有）

**评审结果请发送至**: Team Coordinator