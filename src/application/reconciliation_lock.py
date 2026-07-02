"""
ReconciliationLock - 对账并发锁机制

P0-003: 完善重启对账流程

锁机制:
1. 数据库行锁：持久化锁状态，防止多进程/多实例并发
2. 内存锁 (asyncio.Lock): 防止同一进程内并发
3. 锁超时自动释放：防止死锁（默认 5 分钟）
"""
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from datetime import datetime
import sqlite3


class ReconciliationLockError(Exception):
    """对账锁异常"""
    pass


class ReconciliationLock:
    """
    对账并发锁

    使用场景:
    - 系统启动时对账
    - 定期自动对账
    - 手动触发对账

    锁机制:
    1. 数据库行锁：持久化锁状态，防止多进程/多实例并发
    2. 内存锁 (asyncio.Lock): 防止同一进程内并发
    3. 锁超时自动释放：防止死锁
    """

    # 锁超时时间（秒）- 防止死锁
    LOCK_TIMEOUT_SECONDS = 300  # 5 分钟

    def __init__(self, db_path: str):
        """
        初始化对账锁

        Args:
            db_path: SQLite 数据库文件路径
        """
        self._db_path = db_path
        self._memory_lock = asyncio.Lock()
        self._lock_holder: Optional[str] = None
        self._lock_acquired_at: Optional[float] = None

    def _init_lock_table(self, conn: sqlite3.Connection) -> None:
        """初始化锁表（如果不存在）"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lock_name TEXT UNIQUE NOT NULL,
                locked_at INTEGER NOT NULL,
                locked_by TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        conn.commit()

    def _get_lock_info(self, lock_name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """
        获取锁信息

        Args:
            lock_name: 锁名称
            conn: 可选的数据库连接（用于复用连接）

        Returns:
            锁信息字典，如果不存在则返回 None
        """
        should_close = False
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            should_close = True

        try:
            cursor = conn.execute(
                "SELECT lock_name, locked_at, locked_by, expires_at FROM reconciliation_locks WHERE lock_name = ?",
                (lock_name,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "lock_name": row[0],
                    "locked_at": row[1],
                    "locked_by": row[2],
                    "expires_at": row[3]
                }
            return None
        finally:
            if should_close:
                conn.close()

    def _acquire_db_lock(self, lock_name: str, owner: str) -> bool:
        """
        尝试获取数据库锁

        使用 INSERT OR REPLACE + 检查过期时间实现锁获取

        Args:
            lock_name: 锁名称
            owner: 锁持有者标识

        Returns:
            True 如果成功获取锁，False 如果锁已被占用
        """
        conn = sqlite3.connect(self._db_path)
        try:
            self._init_lock_table(conn)

            current_time = int(time.time() * 1000)  # 毫秒时间戳
            expires_at = current_time + (self.LOCK_TIMEOUT_SECONDS * 1000)

            # 检查现有锁
            existing = self._get_lock_info(lock_name, conn)

            if existing:
                # 锁已存在，检查是否过期
                if existing["expires_at"] > current_time:
                    # 锁未过期，检查是否是同一持有者
                    if existing["locked_by"] == owner:
                        # 同一持有者，续期锁
                        conn.execute(
                            "UPDATE reconciliation_locks SET locked_at = ?, expires_at = ? WHERE lock_name = ?",
                            (current_time, expires_at, lock_name)
                        )
                        conn.commit()
                        return True
                    else:
                        # 不同持有者，锁被占用
                        return False
                else:
                    # 锁已过期，可以抢占
                    conn.execute(
                        """INSERT OR REPLACE INTO reconciliation_locks
                           (id, lock_name, locked_at, locked_by, expires_at)
                           VALUES (
                               (SELECT id FROM reconciliation_locks WHERE lock_name = ?),
                               ?, ?, ?, ?
                           )""",
                        (lock_name, lock_name, current_time, owner, expires_at)
                    )
                    conn.commit()
                    return True
            else:
                # 锁不存在，直接获取
                conn.execute(
                    "INSERT INTO reconciliation_locks (lock_name, locked_at, locked_by, expires_at) VALUES (?, ?, ?, ?)",
                    (lock_name, current_time, owner, expires_at)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            raise ReconciliationLockError(f"数据库锁操作失败：{e}")
        finally:
            conn.close()

    def _release_db_lock(self, lock_name: str, owner: str) -> bool:
        """
        释放数据库锁

        Args:
            lock_name: 锁名称
            owner: 锁持有者标识

        Returns:
            True 如果成功释放，False 如果锁不是当前持有者
        """
        conn = sqlite3.connect(self._db_path)
        try:
            # 只有锁的持有者才能释放
            cursor = conn.execute(
                "SELECT locked_by FROM reconciliation_locks WHERE lock_name = ?",
                (lock_name,)
            )
            row = cursor.fetchone()

            if not row or row[0] != owner:
                return False

            conn.execute("DELETE FROM reconciliation_locks WHERE lock_name = ?", (lock_name,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            raise ReconciliationLockError(f"数据库锁释放失败：{e}")
        finally:
            conn.close()

    def _is_lock_expired(self, lock_name: str) -> bool:
        """
        检查锁是否已过期

        Args:
            lock_name: 锁名称

        Returns:
            True 如果锁已过期，False 否则
        """
        lock_info = self._get_lock_info(lock_name)
        if not lock_info:
            return False

        current_time = int(time.time() * 1000)
        return lock_info["expires_at"] < current_time

    @asynccontextmanager
    async def acquire(self, lock_name: str = "global", owner: Optional[str] = None):
        """
        获取锁的异步上下文管理器

        使用方式:
            async with lock.acquire("startup_reconciliation", "main_process"):
                await run_reconciliation()

        Args:
            lock_name: 锁名称（可用于不同目的锁）
            owner: 锁持有者标识（用于日志和调试）

        Raises:
            ReconciliationLockError: 获取锁失败
        """
        if owner is None:
            owner = f"process_{id(self)}_{datetime.now().isoformat()}"

        # 第一层：内存锁（防止同一进程内并发）
        acquired = await self._memory_lock.acquire()
        if not acquired:
            raise ReconciliationLockError("无法获取内存锁")

        try:
            # 第二层：数据库锁（防止多进程/多实例并发）
            if not self._acquire_db_lock(lock_name, owner):
                # 检查是否是死锁（自己持有的锁）
                lock_info = self._get_lock_info(lock_name)
                if lock_info and lock_info["locked_by"] == owner:
                    # 自己持有的锁，续期即可
                    self._lock_holder = owner
                    self._lock_acquired_at = time.time()
                    yield
                    return

                # 锁被其他进程持有
                raise ReconciliationLockError(
                    f"对账锁已被占用：lock_name={lock_name}, "
                    f"holder={lock_info['locked_by'] if lock_info else 'unknown'}"
                )

            self._lock_holder = owner
            self._lock_acquired_at = time.time()

            try:
                yield
            finally:
                # 释放锁
                self._release_db_lock(lock_name, owner)
                self._lock_holder = None
                self._lock_acquired_at = None
        finally:
            self._memory_lock.release()

    async def try_acquire(self, lock_name: str = "global", owner: Optional[str] = None) -> bool:
        """
        尝试获取锁（非阻塞）

        Args:
            lock_name: 锁名称
            owner: 锁持有者标识

        Returns:
            True 如果成功获取，False 如果锁已被占用
        """
        if owner is None:
            owner = f"process_{id(self)}_{datetime.now().isoformat()}"

        # 检查内存锁
        if self._memory_lock.locked():
            return False

        # 获取内存锁
        acquired = await self._memory_lock.acquire()
        if not acquired:
            return False

        # 获取数据库锁
        if not self._acquire_db_lock(lock_name, owner):
            self._memory_lock.release()
            return False

        self._lock_holder = owner
        self._lock_acquired_at = time.time()
        return True

    def release(self, lock_name: str = "global") -> bool:
        """
        手动释放锁

        Args:
            lock_name: 锁名称

        Returns:
            True 如果成功释放，False 如果锁不是当前持有者
        """
        if self._lock_holder:
            result = self._release_db_lock(lock_name, self._lock_holder)
            if result:
                self._lock_holder = None
                self._lock_acquired_at = None
                self._memory_lock.release()
            return result
        return False

    def get_status(self, lock_name: str = "global") -> Dict[str, Any]:
        """
        获取锁状态

        Args:
            lock_name: 锁名称

        Returns:
            锁状态字典
        """
        lock_info = self._get_lock_info(lock_name)

        if not lock_info:
            return {"locked": False, "lock_name": lock_name}

        current_time = int(time.time() * 1000)
        is_expired = lock_info["expires_at"] < current_time

        return {
            "locked": not is_expired,
            "lock_name": lock_name,
            "locked_by": lock_info["locked_by"],
            "locked_at": datetime.fromtimestamp(lock_info["locked_at"] / 1000).isoformat(),
            "expires_at": datetime.fromtimestamp(lock_info["expires_at"] / 1000).isoformat(),
            "is_expired": is_expired
        }
