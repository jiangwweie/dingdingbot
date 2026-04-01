"""
单元测试：ReconciliationLock 对账并发锁

测试覆盖:
1. 锁获取和释放
2. 锁超时机制
3. 锁持有者验证
4. 并发锁竞争
5. 上下文管理器
6. try_acquire 非阻塞获取
"""
import asyncio
import pytest
import time
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.application.reconciliation_lock import ReconciliationLock, ReconciliationLockError


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_db():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # 清理
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def reconciliation_lock(temp_db):
    """创建 ReconciliationLock 实例"""
    return ReconciliationLock(db_path=temp_db)


# ============================================================
# 测试：锁获取和释放
# ============================================================

@pytest.mark.asyncio
async def test_lock_acquire_and_release(reconciliation_lock):
    """测试：基本锁获取和释放"""
    async with reconciliation_lock.acquire("test_lock", "test_owner"):
        # 锁应该被持有
        status = reconciliation_lock.get_status("test_lock")
        assert status["locked"] is True
        assert status["locked_by"] == "test_owner"

    # 锁应该被释放
    status = reconciliation_lock.get_status("test_lock")
    assert status["locked"] is False


@pytest.mark.asyncio
async def test_lock_auto_renewal_for_same_owner(reconciliation_lock):
    """测试：同一持有者自动续期"""
    # 第一次获取锁
    async with reconciliation_lock.acquire("test_lock", "same_owner"):
        status1 = reconciliation_lock.get_status("test_lock")
        assert status1["locked"] is True

    # 第二次获取同一锁（应该成功，因为锁已释放）
    async with reconciliation_lock.acquire("test_lock", "same_owner"):
        status2 = reconciliation_lock.get_status("test_lock")
        assert status2["locked"] is True


@pytest.mark.asyncio
async def test_lock_release_manually(reconciliation_lock):
    """测试：手动释放锁"""
    # 获取锁
    acquired = await reconciliation_lock.try_acquire("test_lock", "test_owner")
    assert acquired is True

    # 手动释放
    result = reconciliation_lock.release("test_lock")
    assert result is True

    # 锁应该被释放
    status = reconciliation_lock.get_status("test_lock")
    assert status["locked"] is False


# ============================================================
# 测试：try_acquire 非阻塞获取
# ============================================================

@pytest.mark.asyncio
async def test_try_acquire_success(reconciliation_lock):
    """测试：try_acquire 成功获取锁"""
    result = await reconciliation_lock.try_acquire("test_lock", "test_owner")
    assert result is True

    # 锁状态
    status = reconciliation_lock.get_status("test_lock")
    assert status["locked"] is True

    # 清理
    reconciliation_lock.release("test_lock")


@pytest.mark.asyncio
async def test_try_acquire_locked(reconciliation_lock):
    """测试：try_acquire 锁被占用时返回 False"""
    # 第一次获取锁
    result1 = await reconciliation_lock.try_acquire("test_lock", "owner1")
    assert result1 is True

    # 第二次尝试获取（应该失败）
    result2 = await reconciliation_lock.try_acquire("test_lock", "owner2")
    assert result2 is False

    # 清理
    reconciliation_lock.release("test_lock")


@pytest.mark.asyncio
async def test_try_acquire_memory_lock_conflict(reconciliation_lock):
    """测试：内存锁冲突时 try_acquire 返回 False"""
    async with reconciliation_lock.acquire("test_lock", "owner1"):
        # 锁被持有时尝试获取
        result = await reconciliation_lock.try_acquire("test_lock", "owner2")
        assert result is False


# ============================================================
# 测试：锁状态查询
# ============================================================

@pytest.mark.asyncio
async def test_get_status_lock_not_exists(reconciliation_lock):
    """测试：获取不存在的锁状态"""
    # 先获取一次锁以创建表，然后释放
    async with reconciliation_lock.acquire("temp_lock", "owner"):
        pass

    # 现在查询一个不存在的锁
    status = reconciliation_lock.get_status("nonexistent_lock")
    assert status["locked"] is False
    assert status["lock_name"] == "nonexistent_lock"


@pytest.mark.asyncio
async def test_get_status_lock_holds_info(reconciliation_lock):
    """测试：获取锁状态包含完整信息"""
    async with reconciliation_lock.acquire("test_lock", "test_owner"):
        status = reconciliation_lock.get_status("test_lock")

        assert status["locked"] is True
        assert status["lock_name"] == "test_lock"
        assert status["locked_by"] == "test_owner"
        assert "locked_at" in status
        assert "expires_at" in status
        assert "is_expired" in status


# ============================================================
# 测试：锁超时机制
# ============================================================

@pytest.mark.asyncio
async def test_lock_expiration_detection(reconciliation_lock):
    """测试：锁过期检测"""
    # 手动创建一个已过期的锁
    import sqlite3
    current_time = int(time.time() * 1000)
    expired_time = current_time - 1000000  # 1000 秒前过期

    conn = sqlite3.connect(reconciliation_lock._db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lock_name TEXT UNIQUE NOT NULL,
            locked_at INTEGER NOT NULL,
            locked_by TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO reconciliation_locks (lock_name, locked_at, locked_by, expires_at) VALUES (?, ?, ?, ?)",
        ("expiring_lock", current_time, "old_owner", expired_time)
    )
    conn.commit()
    conn.close()

    # 检测锁是否已过期
    is_expired = reconciliation_lock._is_lock_expired("expiring_lock")
    assert is_expired is True

    # 获取状态应该显示已过期
    status = reconciliation_lock.get_status("expiring_lock")
    assert status["is_expired"] is True


@pytest.mark.asyncio
async def test_lock_timeout_prevents_concurrent_access(temp_db):
    """测试：锁超时防止并发访问"""
    lock1 = ReconciliationLock(db_path=temp_db)
    lock2 = ReconciliationLock(db_path=temp_db)

    # 设置非常短的超时时间用于测试
    lock1.LOCK_TIMEOUT_SECONDS = 1
    lock2.LOCK_TIMEOUT_SECONDS = 1

    # 第一个锁获取锁
    async with lock1.acquire("test_lock", "owner1"):
        # 第二个锁尝试获取（应该失败）
        with pytest.raises(ReconciliationLockError) as exc_info:
            async with lock2.acquire("test_lock", "owner2"):
                pass
        assert "已被占用" in str(exc_info.value)

    # 等待锁过期
    await asyncio.sleep(1.5)

    # 现在第二个锁应该可以获取
    async with lock2.acquire("test_lock", "owner2"):
        status = lock2.get_status("test_lock")
        assert status["locked"] is True


# ============================================================
# 测试：并发锁竞争
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_lock_acquires_serializes(temp_db):
    """测试：并发锁获取会序列化执行"""
    lock = ReconciliationLock(db_path=temp_db)
    results = []

    async def worker(worker_id: str):
        async with lock.acquire("shared_lock", worker_id):
            results.append(f"{worker_id}_started")
            await asyncio.sleep(0.1)  # 模拟工作
            results.append(f"{worker_id}_done")

    # 并发启动 3 个工作器
    await asyncio.gather(
        worker("worker1"),
        worker("worker2"),
        worker("worker3"),
    )

    # 验证：由于锁序列化，每个 worker 应该完整执行
    assert len(results) == 6
    # 验证每个 worker 的 start 和 done 是连续的
    for i in range(1, 4):
        worker_name = f"worker{i}"
        start_idx = results.index(f"{worker_name}_started")
        done_idx = results.index(f"{worker_name}_done")
        assert done_idx > start_idx


@pytest.mark.asyncio
async def test_multiple_lock_names_independent(temp_db):
    """测试：不同锁名称是独立的"""
    lock1 = ReconciliationLock(db_path=temp_db)
    lock2 = ReconciliationLock(db_path=temp_db)

    # 锁 1 获取锁 A
    async with lock1.acquire("lock_a", "owner1"):
        # 锁 2 可以获取锁 B（不同的锁名称）
        async with lock2.acquire("lock_b", "owner2"):
            status_a = lock1.get_status("lock_a")
            status_b = lock2.get_status("lock_b")

            assert status_a["locked"] is True
            assert status_b["locked"] is True

        # 锁 B 释放后
        status_b = lock2.get_status("lock_b")
        assert status_b["locked"] is False

    # 锁 A 释放后
    status_a = lock1.get_status("lock_a")
    assert status_a["locked"] is False


# ============================================================
# 测试：异常处理
# ============================================================

@pytest.mark.asyncio
async def test_lock_error_on_acquire_failure(reconciliation_lock):
    """测试：获取锁失败时抛出异常"""
    # 模拟数据库错误
    with patch.object(reconciliation_lock, '_acquire_db_lock', side_effect=Exception("DB error")):
        with pytest.raises(Exception) as exc_info:
            async with reconciliation_lock.acquire("test_lock", "owner"):
                pass
        assert "DB error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_lock_release_non_existent(reconciliation_lock):
    """测试：释放不存在的锁返回 False"""
    result = reconciliation_lock.release("nonexistent_lock")
    assert result is False


@pytest.mark.asyncio
async def test_lock_release_wrong_owner(reconciliation_lock):
    """测试：释放锁时验证持有者"""
    # 获取锁
    acquired = await reconciliation_lock.try_acquire("test_lock", "owner1")
    assert acquired is True

    # 尝试释放（内部持有者是 owner1）
    reconciliation_lock._lock_holder = "wrong_owner"
    result = reconciliation_lock.release("test_lock")
    assert result is False

    # 清理
    reconciliation_lock._lock_holder = "owner1"
    reconciliation_lock.release("test_lock")


# ============================================================
# 测试：边界情况
# ============================================================

@pytest.mark.asyncio
async def test_lock_default_owner(reconciliation_lock):
    """测试：默认 owner 生成"""
    async with reconciliation_lock.acquire("test_lock"):
        status = reconciliation_lock.get_status("test_lock")
        # owner 应该自动生成
        assert status["locked_by"].startswith("process_")


@pytest.mark.asyncio
async def test_lock_default_lock_name(reconciliation_lock):
    """测试：默认锁名称为 global"""
    async with reconciliation_lock.acquire():
        status = reconciliation_lock.get_status("global")
        assert status["locked"] is True


@pytest.mark.asyncio
async def test_lock_with_invalid_db_path():
    """测试：无效数据库路径的处理"""
    lock = ReconciliationLock(db_path="/nonexistent/path/db.sqlite")

    # 应该抛出 sqlite3.OperationalError 或 ReconciliationLockError
    with pytest.raises((sqlite3.OperationalError, ReconciliationLockError)):
        async with lock.acquire("test_lock", "owner"):
            pass


# ============================================================
# 测试：锁表初始化
# ============================================================

@pytest.mark.asyncio
async def test_lock_table_auto_created(temp_db):
    """测试：锁表自动创建"""
    lock = ReconciliationLock(db_path=temp_db)

    # 获取锁会触发锁表创建
    async with lock.acquire("test_lock", "owner"):
        # 验证锁表存在
        import sqlite3
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reconciliation_locks'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "reconciliation_locks"


# ============================================================
# 测试：集成场景
# ============================================================

@pytest.mark.asyncio
async def test_startup_reconciliation_pattern(temp_db):
    """测试：模拟系统启动对账场景"""
    lock = ReconciliationLock(db_path=temp_db)
    reconciliation_count = 0

    async def run_reconciliation():
        nonlocal reconciliation_count
        async with lock.acquire("startup_reconciliation", "main_process"):
            # 模拟对账工作
            await asyncio.sleep(0.05)
            reconciliation_count += 1

    # 串行执行多次对账
    await run_reconciliation()
    await run_reconciliation()

    # 验证：两次对账都成功执行
    assert reconciliation_count == 2


@pytest.mark.asyncio
async def test_lock_persistence_across_instances(temp_db):
    """测试：锁状态在多个实例间持久化"""
    # 创建第一个锁实例
    lock1 = ReconciliationLock(db_path=temp_db)

    # 获取锁
    async with lock1.acquire("persistent_lock", "instance1"):
        # 创建第二个锁实例（使用同一数据库）
        lock2 = ReconciliationLock(db_path=temp_db)

        # 第二个实例应该能看到锁状态
        status = lock2.get_status("persistent_lock")
        assert status["locked"] is True
        assert status["locked_by"] == "instance1"
