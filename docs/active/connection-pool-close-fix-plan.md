# Connection Pool Shared Connection Premature Close -- Fix Plan

> **Created**: 2026-04-14
> **Severity**: P1 (silent data corruption risk, breaks sequential backtests)
> **Scope**: All repositories using `pool_get_connection`

---

## Root Cause

`ConnectionPool.get_connection(db_path)` returns a **shared** connection instance per db_path. All 13+ repositories that call `pool_get_connection` receive the same `aiosqlite.Connection` object when using the same database.

The `_owns_connection` flag is set in `__init__`:
```python
self._owns_connection = connection is None  # True when no connection injected
```

When `_owns_connection=True` and `initialize()` runs, the repo calls `pool_get_connection()` to get a connection. But this connection is **shared by the pool**, not owned by any single repo.

When any repo's `close()` is called with `_owns_connection=True`, it executes `await self._db.close()` -- destroying the shared connection for **all** other repos referencing it.

**Bug manifestation**: `api.py` backtest endpoints close `backtest_repository` then `order_repository` sequentially in a finally block. The first `close()` kills the shared connection, causing the second repo (and any subsequent DB operations) to fail with `ValueError("no active connection")`.

---

## Fix Principle

**Rule**: No repository should ever call `await self._db.close()` on a connection obtained from the pool. The pool is the sole owner; only `ConnectionPool.close_all()` should close connections.

**Fix pattern**: Change `close()` to only commit (if needed) and clear the local reference (`self._db = None`) -- **never** call `await self._db.close()`.

---

## Before / After Fix Pattern

### Pattern A: Simple close (most repos)

**Before:**
```python
async def close(self) -> None:
    """Close database connection (only if self-owned)."""
    if self._db and self._owns_connection:
        await self._db.close()
        self._db = None
```

**After:**
```python
async def close(self) -> None:
    """Clear local connection reference (pool-managed connections are never closed by repos)."""
    if self._db:
        self._db = None
```

### Pattern B: Close with commit (order_repository, reconciliation_repository)

**Before:**
```python
async def close(self) -> None:
    """Close database connection (only if self-owned)"""
    if self._db and self._owns_connection:
        async with self._ensure_lock():
            await self._db.commit()
            await self._db.close()
            self._db = None
            logger.info("订单仓库连接已关闭")
            self._db = None            # <-- duplicate line
            logger.info("订单仓库连接已关闭")  # <-- duplicate log
```

**After:**
```python
async def close(self) -> None:
    """Clear local connection reference (pool-managed connections are never closed by repos)."""
    if self._db:
        async with self._ensure_lock():
            await self._db.commit()
            self._db = None
            logger.info("订单仓库本地引用已清除")
```

### Pattern C: signal_repository (simple, no commit needed)

**Before:**
```python
async def close(self) -> None:
    """Close database connection (only if self-owned)."""
    if self._db and self._owns_connection:
        await self._db.close()
```

**After:**
```python
async def close(self) -> None:
    """Clear local connection reference (pool-managed connections are never closed by repos)."""
    self._db = None
```

---

## Files to Modify

### 1. `src/infrastructure/signal_repository.py` (line ~1228)
- Pattern C (simple)

### 2. `src/infrastructure/order_repository.py` (line ~184)
- Pattern B (with commit)
- **Also fixes**: duplicate `self._db = None` + duplicate `logger.info` (lines 190-193)

### 3. `src/infrastructure/backtest_repository.py` (line ~128)
- Pattern A

### 4. `src/infrastructure/config_snapshot_repository.py` (line ~100)
- Pattern A

### 5. `src/infrastructure/config_entry_repository.py` (line ~139)
- Pattern A

### 6. `src/infrastructure/config_profile_repository.py` (line ~122)
- Pattern A
- **Also fixes**: missing `pool_get_connection` import at line ~98
  - Add: `from src.infrastructure.connection_pool import get_connection as pool_get_connection`

### 7. `src/infrastructure/reconciliation_repository.py` (line ~168)
- Pattern B (with commit)

### 8. `src/infrastructure/repositories/config_repositories.py` -- 7 classes
All follow Pattern A. Lines:
- `StrategyConfigRepository.close()` ~line 109
- `RiskConfigRepository.close()` ~line 408
- `SystemConfigRepository.close()` ~line 575
- `SymbolConfigRepository.close()` ~line 731
- `NotificationConfigRepository.close()` ~line 1013
- `ConfigHistoryRepository.close()` ~line 1303

### 9. `src/application/strategy_optimizer.py` -- `_OptimizationHistoryRepository.close()` (line ~865)
- Pattern A

---

## Additional Cleanup

- `_owns_connection` field can be **removed** from all repos after this fix (it no longer affects behavior). This is optional and can be a follow-up cleanup.
- The `connection` parameter in `__init__` should be kept for backward compatibility with connection injection.

---

## Test Strategy

### Test 1: Shared connection survives first repo close
```python
async def test_close_one_repo_doesnt_break_another():
    """Closing one repo should not affect another repo sharing the same connection."""
    # Pool should still have the connection after both repos are "closed"
    repo1 = SignalRepository(db_path=":memory:")
    repo2 = OrderRepository(db_path=":memory:")
    await repo1.initialize()
    await repo2.initialize()

    # Both share the same pool connection
    assert repo1._db is repo2._db

    await repo1.close()

    # repo2 should still be able to use the connection
    await repo2._db.execute("SELECT 1")  # should NOT raise ValueError
```

### Test 2: Sequential backtest runs
```python
async def test_backtest_runs_twice_without_connection_error():
    """Backtest endpoint should work correctly on consecutive calls."""
    # Simulate the api.py finally block pattern
    backtest_repo = BacktestRepository(db_path=":memory:")
    order_repo = OrderRepository(db_path=":memory:")
    await backtest_repo.initialize()
    await order_repo.initialize()

    # First close (this was the bug -- it killed the shared connection)
    await backtest_repo.close()

    # Second close should not fail (order_repo still has valid reference)
    await order_repo.close()

    # Pool connection should still be alive
    pool_conn = await get_connection(":memory:")
    await pool_conn.execute("SELECT 1")  # should NOT raise ValueError
```

### Test 3: Pool cleanup still works
```python
async def test_pool_close_all_still_works():
    """ConnectionPool.close_all() should properly close all connections."""
    repo = SignalRepository(db_path=":memory:")
    await repo.initialize()
    await repo.close()  # clears local ref only

    # Pool should still have the connection
    pool = ConnectionPool.get_instance()
    assert ":memory:" in pool._connections

    # close_all should work
    await close_all_connections()
    assert len(pool._connections) == 0
```

### Test 4: Injected connection not affected
```python
async def test_injected_connection_not_closed():
    """A repo with an injected connection should not close it on repo.close()."""
    conn = await get_connection(":memory:")
    repo = SignalRepository(db_path=":memory:", connection=conn)
    await repo.initialize()
    await repo.close()

    # The injected connection should still be usable
    await conn.execute("SELECT 1")  # should NOT raise ValueError
```

---

## Parallel Work

All file modifications are **independent** -- each repo's `close()` method can be changed in parallel. No cross-file dependencies.

### Suggested parallel groups:
- **Group A**: `signal_repository.py`, `order_repository.py`, `backtest_repository.py`
- **Group B**: `config_snapshot_repository.py`, `config_entry_repository.py`, `config_profile_repository.py`, `reconciliation_repository.py`
- **Group C**: `repositories/config_repositories.py` (all 7 close methods in one file)
- **Group D**: `strategy_optimizer.py`

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Memory leak (connections never closed) | Low | Pool's `close_all()` is still called at application shutdown |
| Uncommitted data loss | Low | Repos with pending transactions should commit before clearing ref (Pattern B) |
| `_owns_connection` field becomes dead code | Certain | Can be cleaned up in a follow-up PR |
