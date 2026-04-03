# 架构评审报告：FastAPI lifespan Repository 初始化方案

**评审编号**: AR-20260403-001
**关联诊断报告**: DA-20260403-001
**评审时间**: 2026-04-03 15:20
**架构师**: Architect

---

## 📋 评审结论

**❌ 方案 A 暂不通过 - 存在 asyncio.Lock 事件循环冲突风险**

**建议修复路径**：
1. 先修复所有 Repository 的 `asyncio.Lock()` 创建逻辑（PR-1）
2. 再实施方案 A 的 lifespan 初始化（PR-2）

---

## 🔍 架构合规性分析

### ✅ Clean Architecture 合规性

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 依赖方向 | ✅ 正确 | interfaces 层初始化 infrastructure 层，符合外层依赖内层原则 |
| 层次边界 | ✅ 清晰 | lifespan 属于接口层，Repository 属于基础设施层 |
| 接口隔离 | ✅ 符合 | Repository 抽象良好，通过 `initialize()` 和 `close()` 管理生命周期 |

### ⚠️ 技术约束检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| asyncio.Lock 事件循环 | ❌ **冲突风险** | SignalRepository 和 ConfigEntryRepository 在 `__init__` 中创建 lock |
| 幂等性保证 | ⚠️ 需验证 | 需确保 `initialize()` 可多次调用（幂等性） |
| 资源泄漏预防 | ✅ 正确 | shutdown 阶段正确调用 `close()` |

---

## 🚨 关键问题分析

### 问题 1：asyncio.Lock 事件循环冲突（严重）

**代码位置**:
- `src/infrastructure/signal_repository.py:36`
- `src/infrastructure/config_entry_repository.py:36`

**问题代码**:
```python
class SignalRepository:
    def __init__(self, db_path: str = "data/v3_dev.db"):
        self._lock = asyncio.Lock()  # ❌ 在 __init__ 中创建 lock
```

**根因**:
- `asyncio.Lock()` 创建时绑定到当前事件循环
- uvicorn 启动时创建事件循环 A
- lifespan 在事件循环 A 中初始化 Repository，lock 绑定到循环 A
- 如果后续有其他事件循环（pytest-asyncio、热重载等），lock 无法跨循环使用
- 导致死锁或异常

**影响范围**:
- SignalRepository: 1 个 `asyncio.Lock`
- ConfigEntryRepository: 1 个 `asyncio.Lock`
- OrderRepository: ✅ 已修复（DEBT-5）

**复现路径**:
1. `uvicorn src.interfaces.api:app` 启动
2. lifespan 初始化 Repository（lock 绑定到事件循环 A）
3. 热重载触发（uvicorn --reload）
4. 新事件循环 B 创建
5. API 端点访问 Repository 时，尝试使用循环 A 的 lock → **死锁**

---

### 问题 2：initialize() 幂等性缺失

**代码位置**:
- `src/infrastructure/signal_repository.py:39-59`
- `src/infrastructure/config_entry_repository.py:38-68`

**问题代码**:
```python
async def initialize(self) -> None:
    """Initialize database connection and create tables."""
    # ❌ 未检查是否已初始化
    self._db = await aiosqlite.connect(self.db_path)
```

**风险**:
- 如果 lifespan 初始化后，API 端点再次调用 `initialize()`
- 会导致数据库连接泄漏

**对比 OrderRepository**:
```python
async def initialize(self) -> None:
    """Initialize database connection..."""
    # ✅ 幂等性检查
    if self._db is not None:
        return
    async with self._ensure_lock():
        ...
```

---

## 🎯 修复方案（两阶段）

### PR-1: 修复 Repository asyncio.Lock 问题（前置条件）

**修改范围**:
1. SignalRepository
2. ConfigEntryRepository

**修改内容**（参考 OrderRepository DEBT-5 修复）:

```python
# 文件：src/infrastructure/signal_repository.py
# 位置：第 27-48 行

# 修改前：
def __init__(self, db_path: str = "data/v3_dev.db"):
    self.db_path = db_path
    self._db: Optional[aiosqlite.Connection] = None
    self._lock = asyncio.Lock()  # ❌ 立即创建
    logger.info(f"数据库初始化完成：{db_path}")

# 修改后：
def __init__(self, db_path: str = "data/v3_dev.db"):
    self.db_path = db_path
    self._db: Optional[aiosqlite.Connection] = None
    self._lock: Optional[asyncio.Lock] = None  # ✅ 延迟创建
    logger.info(f"数据库初始化完成：{db_path}")

def _ensure_lock(self) -> asyncio.Lock:
    """Ensure lock is created for current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Lock()
    
    if self._lock is None:
        self._lock = asyncio.Lock()
    return self._lock

async def initialize(self) -> None:
    """Initialize database connection..."""
    # ✅ 幂等性检查
    if self._db is not None:
        return
    
    async with self._ensure_lock():
        # ... 原有初始化逻辑 ...

# 所有 async with self._lock: 改为 async with self._ensure_lock():
```

**工作量**: 1.5 小时
**优先级**: 🔴 P0（必须先完成）

---

### PR-2: 实施 lifespan 初始化（原方案 A）

**修改内容**:

```python
# 文件：src/interfaces/api.py
# 位置：第 284-295 行

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.
    Initialize repositories on startup, close on shutdown.
    """
    # Startup - 初始化所有 Repository
    from src.infrastructure.signal_repository import SignalRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    
    global _repository, _config_entry_repo
    
    try:
        # 初始化 SignalRepository（幂等）
        if _repository is None:
            _repository = SignalRepository()
            await _repository.initialize()
            logger.info("✅ SignalRepository initialized in lifespan")
        
        # 初始化 ConfigEntryRepository（幂等）
        if _config_entry_repo is None:
            _config_entry_repo = ConfigEntryRepository()
            await _config_entry_repo.initialize()
            logger.info("✅ ConfigEntryRepository initialized in lifespan")
        
        # OrderRepository 按需创建（DEBT-3 方案）
        
        yield
        
    finally:
        # Shutdown - 清理所有 Repository
        if _repository is not None:
            await _repository.close()
            logger.info("✅ SignalRepository closed")
        
        if _config_entry_repo is not None:
            await _config_entry_repo.close()
            logger.info("✅ ConfigEntryRepository closed")
```

**工作量**: 0.5 小时
**优先级**: 🔴 P0（PR-1 完成后）
**前置条件**: PR-1 必须完成

---

## 📊 Trade-off 分析

### 方案对比

| 方案 | 优点 | 缺点 | 风险 |
|------|------|------|------|
| **PR-1 + PR-2** | ✅ 彻底解决事件循环冲突<br>✅ 幂等性保证<br>✅ 符合架构原则 | ⚠️ 需要修改多个文件<br>⚠️ 工作量增加（2h） | 🟢 低风险 |
| **仅 PR-2** | ✅ 快速修复（0.5h） | ❌ 引入 asyncio.Lock 冲突<br>❌ 热重载会死锁 | 🔴 高风险 |
| **方案 B（main.py）** | ✅ 无需修改 Repository | ❌ 无法热重载<br>❌ 不符合开发习惯 | 🟡 中风险 |
| **方案 C（懒加载）** | ✅ 最小修改 | ❌ 仍有 lock 冲突<br>❌ 线程安全问题 | 🔴 高风险 |

---

## ✅ 架构评审决策

### 推荐方案：PR-1 + PR-2（两阶段修复）

**理由**:
1. **根本性解决**：先修复 Repository 的 asyncio.Lock 问题，再实施 lifespan 初始化
2. **架构一致性**：所有 Repository 统一使用 `_ensure_lock()` 模式
3. **幂等性保证**：避免重复初始化和资源泄漏
4. **风险可控**：分层修复，每步可验证

**实施顺序**:
```
1. PR-1: 修复 SignalRepository 和 ConfigEntryRepository（1.5h）
   ↓ 验证：运行单元测试，确认 asyncio.Lock 修复
2. PR-2: 实施 lifespan 初始化（0.5h）
   ↓ 验证：启动 uvicorn，测试所有 API 端点
3. 集成测试：热重载、并发访问、事件循环切换
```

**验证命令**:
```bash
# PR-1 验证
pytest tests/unit/test_signal_repository.py -v
pytest tests/unit/test_config_entry_repository.py -v

# PR-2 验证
curl http://localhost:8000/api/health
curl http://localhost:8000/api/signals/stats
curl http://localhost:8000/api/v3/orders/tree?days=7

# 热重载验证（修改任意代码文件，触发重载）
# 访问 API 确认不死锁
```

---

## 🚫 拒绝理由

### 为什么不能直接实施方案 A？

1. **asyncio.Lock 事件循环冲突**
   - SignalRepository 和 ConfigEntryRepository 的 lock 在 `__init__` 中创建
   - uvicorn --reload 会创建新事件循环，导致 lock 失效
   - 会引入比当前问题更严重的死锁问题

2. **initialize() 缺少幂等性**
   - 多次调用会导致数据库连接泄漏
   - 不符合资源管理最佳实践

3. **架构一致性**
   - OrderRepository 已使用 `_ensure_lock()` 模式（DEBT-5）
   - 其他 Repository 应保持一致

---

## 📌 后续建议

### 技术债清单

1. **统一 Repository 基类**（P2）
   - 创建 `BaseRepository` 提供 `_ensure_lock()` 和幂等性 `initialize()`
   - 所有 Repository 继承基类，避免重复代码

2. **启动健康检查**（P1）
   - 添加 `/api/health/detailed` 端点
   - 返回所有 Repository 初始化状态

3. **文档化启动模式**（P1）
   - README.md 说明两种启动模式（uvicorn vs main.py）
   - 开发环境使用 uvicorn --reload
   - 生产环境使用 main.py

---

## 📎 相关文档

- DEBT-5 修复记录: `docs/planning/progress.md` (2026-04-03 22:00)
- OrderRepository asyncio.Lock 修复: commit `31a4ed1`
- Clean Architecture 原则: `CLAUDE.md`

---

**评审状态**: ❌ 方案 A 暂不通过，需先完成 PR-1
**下一步**: Backend Developer 执行 PR-1，然后执行 PR-2

---

**架构师签名**: Architect
**评审时间**: 2026-04-03 15:20