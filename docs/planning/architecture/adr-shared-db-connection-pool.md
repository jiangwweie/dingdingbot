# 架构设计方案：共享 DB 连接池统一改造

> **日期**: 2026-04-13
> **状态**: 实施中

---

## 方案选择：方案 A（最小侵入）

每个 Repository 的 `initialize()` 内部，将 `aiosqlite.connect()` 替换为 `pool.get_connection()`。不改初始化顺序、不改依赖注入接口、不改 `main.py` Phase 9 的调用方式。

**理由**：
1. **零时序风险** — `main.py` Phase 9 和 `api.py lifespan` 的调用顺序完全不变
2. **渐进式** — 可以逐个文件改造，每改一个文件都能独立验证
3. **今天的修复不受影响** — lifespan 补充初始化、set_dependencies 扩容等今日提交完全隔离

---

## 需要改造的文件清单（13 个文件，~20 处连接点）

| # | 文件 | DB 路径 | 连接点数 | 改动内容 |
|---|------|---------|---------|---------|
| 1 | `signal_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 2 | `order_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 3 | `backtest_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 4 | `reconciliation_repository.py` | reconciliation.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 5 | `config_snapshot_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 6 | `config_entry_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 7 | `config_profile_repository.py` | v3_dev.db | 1 | 替换 connect + PRAGMA 委托给池 |
| 8-14 | `config_repositories.py` 中 7 个类 | v3_dev.db | 7 | 替换 connect + PRAGMA 委托给池 |
| 15 | `strategy_optimizer.py` | optimization_history.db | 1 | 替换 connect + PRAGMA 委托给池 |

**不在改造范围**：`historical_data_repository.py` 使用 SQLAlchemy `create_async_engine`，有独立连接池机制。

---

## 具体改动

### 1. connection_pool.py 新增 busy_timeout

在第 86 行 `cache_size` 后添加：
```python
await conn.execute("PRAGMA busy_timeout=10000")  # 10s retry on locked
```

### 2. 每个 Repository 的 initialize() 改动模板

**改前**（6 行）：
```python
if self._owns_connection and self._db is None:
    self._db = await aiosqlite.connect(self.db_path)
    self._db.row_factory = aiosqlite.Row
    await self._db.execute("PRAGMA journal_mode=WAL")
    await self._db.execute("PRAGMA synchronous=NORMAL")
    await self._db.execute("PRAGMA wal_autocheckpoint=1000")
    await self._db.execute("PRAGMA cache_size=-64000")
```

**改后**（3 行）：
```python
if self._owns_connection and self._db is None:
    from src.infrastructure.connection_pool import get_connection as pool_get_connection
    self._db = await pool_get_connection(self.db_path)
    # PRAGMA 已在连接池中统一设置，此处无需重复执行
```

### 3. close() 方法不需要改

`close()` 检查 `_owns_connection` 标志，池化连接的 `_owns_connection=False`，所以不会关闭池连接。

---

## 测试用例设计

### T1: 连接共享验证
- 同一 db_path 的多个 Repository 获取同一连接实例
- 不同 db_path 获取不同连接实例

### T2: 并发写入无 locked
- 多个 Repository 同时写入同一数据库
- 验证 busy_timeout 生效，无 "database is locked" 异常

### T3: 双模式初始化回归
- `main.py` 嵌入模式（lifespan="off"）：Phase 9 逐个初始化 → 应正常
- `api.py` lifespan 模式：lifespan startup → 应正常
- 两种模式下 `/api/v1/config/*` 端点均返回 200

### T4: PRAGMA 验证
- 验证 WAL 模式已启用
- 验证 busy_timeout=10000 已设置
- 验证 synchronous=NORMAL 已设置

### T5: Shutdown 清理
- `close_all_connections()` 正确关闭所有连接
- Repository.close() 不会关闭池化连接

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 池化连接被多个 Repo 同时写入导致 locked | 低 | `busy_timeout=10000` 自动重试 + 各 Repo 已有 asyncio.Lock |
| 连接池在错误事件循环中创建 | 低 | connection_pool 已用延迟 Lock 模式解决 |
| shutdown 时连接未正确清理 | 低 | 连接池有 `close_all()`，应用 shutdown 时调用 |
| 注入连接的 Repo 行为异常 | 低 | 现有测试已覆盖注入模式 |
