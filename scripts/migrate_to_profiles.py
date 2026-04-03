#!/usr/bin/env python3
"""
配置 Profile 管理 - 数据库迁移脚本

功能:
1. 创建 config_profiles 表
2. 扩展 config_entries_v2 表添加 profile_name 字段
3. 将现有配置归属到 default Profile

使用方法:
    python scripts/migrate_to_profiles.py

注意事项:
- 迁移前会自动备份数据库
- 迁移失败会自动回滚
- 迁移后可运行 rollback 回滚
"""
import asyncio
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("data/v3_dev.db")
BACKUP_DIR = Path("data/backups")


def get_timestamp() -> str:
    """获取时间戳字符串用于备份文件名"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_database() -> Optional[Path]:
    """
    备份数据库文件

    Returns:
        备份文件路径，如果失败返回 None
    """
    if not DB_PATH.exists():
        print(f"⚠️  数据库文件不存在：{DB_PATH}")
        return None

    # 创建备份目录
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # 生成备份文件名
    timestamp = get_timestamp()
    backup_path = BACKUP_DIR / f"v3_dev_backup_{timestamp}.db"

    try:
        # 复制数据库文件
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ 数据库已备份：{backup_path}")

        # 同时备份 WAL 和 SHM 文件（如果存在）
        for ext in ["-wal", "-shm"]:
            wal_file = DB_PATH.with_suffix(DB_PATH.suffix + ext)
            if wal_file.exists():
                shutil.copy2(wal_file, backup_path.with_suffix(DB_PATH.suffix + ext))

        return backup_path
    except Exception as e:
        print(f"❌ 备份失败：{e}")
        return None


def rollback_database(backup_path: Path) -> bool:
    """
    从备份恢复数据库

    Args:
        backup_path: 备份文件路径

    Returns:
        是否成功
    """
    if not backup_path.exists():
        print(f"❌ 备份文件不存在：{backup_path}")
        return False

    try:
        shutil.copy2(backup_path, DB_PATH)
        print(f"✅ 数据库已恢复到备份：{backup_path}")
        return True
    except Exception as e:
        print(f"❌ 恢复失败：{e}")
        return False


async def migrate_config_entries_add_profile_name(conn: sqlite3.Connection) -> bool:
    """
    扩展 config_entries_v2 表，添加 profile_name 字段

    Returns:
        是否成功
    """
    cursor = conn.cursor()

    try:
        # 检查字段是否已存在
        cursor.execute("""
            PRAGMA table_info(config_entries_v2)
        """)
        columns = [row[1] for row in cursor.fetchall()]

        if "profile_name" in columns:
            print("ℹ️  config_entries_v2.profile_name 字段已存在，跳过")
            return True

        # 添加 profile_name 字段，默认值为 'default'
        cursor.execute("""
            ALTER TABLE config_entries_v2
            ADD COLUMN profile_name TEXT NOT NULL DEFAULT 'default'
        """)

        print("✅ config_entries_v2 表已添加 profile_name 字段")

        # 创建索引
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_config_profile_key
            ON config_entries_v2(profile_name, config_key)
        """)

        print("✅ 已创建索引 idx_config_profile_key")

        conn.commit()
        return True

    except Exception as e:
        print(f"❌ 迁移 config_entries_v2 失败：{e}")
        conn.rollback()
        return False


async def create_config_profiles_table(conn: sqlite3.Connection) -> bool:
    """
    创建 config_profiles 表

    Returns:
        是否成功
    """
    cursor = conn.cursor()

    try:
        # 检查表是否已存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='config_profiles'
        """)

        if cursor.fetchone():
            print("ℹ️  config_profiles 表已存在，跳过")
            return True

        # 创建 config_profiles 表
        cursor.execute("""
            CREATE TABLE config_profiles (
                name            TEXT PRIMARY KEY,
                description     TEXT,
                is_active       BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                created_from    TEXT
            )
        """)

        print("✅ config_profiles 表已创建")

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_profiles_active
            ON config_profiles(is_active)
        """)

        # 插入 default Profile
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR IGNORE INTO config_profiles
            (name, description, is_active, created_at, updated_at, created_from)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("default", "默认配置档案", True, now, now, "system"))

        print("✅ default Profile 已创建")

        conn.commit()
        return True

    except Exception as e:
        print(f"❌ 创建 config_profiles 表失败：{e}")
        conn.rollback()
        return False


async def verify_migration(conn: sqlite3.Connection) -> bool:
    """
    验证迁移结果

    Returns:
        是否验证通过
    """
    cursor = conn.cursor()

    # 验证 config_profiles 表
    cursor.execute("SELECT COUNT(*) FROM config_profiles")
    profile_count = cursor.fetchone()[0]
    print(f"📊 config_profiles 表记录数：{profile_count}")

    # 验证 default Profile 存在
    cursor.execute("SELECT name, is_active FROM config_profiles WHERE name='default'")
    default = cursor.fetchone()
    if default:
        print(f"✅ default Profile 存在，激活状态：{default[1]}")
    else:
        print("❌ default Profile 不存在")
        return False

    # 验证 config_entries_v2 的 profile_name 字段
    cursor.execute("""
        SELECT COUNT(DISTINCT profile_name) FROM config_entries_v2
    """)
    profile_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM config_entries_v2 WHERE profile_name='default'")
    default_config_count = cursor.fetchone()[0]
    print(f"📊 config_entries_v2 表记录数：{default_config_count} (归属 default)")

    return True


async def main():
    """主函数"""
    print("=" * 60)
    print("配置 Profile 管理 - 数据库迁移脚本")
    print("=" * 60)
    print()

    # 备份数据库
    print("📦 步骤 1/4: 备份数据库...")
    backup_path = backup_database()
    if backup_path is None and DB_PATH.exists():
        print("❌ 备份失败，中止迁移")
        return False
    print()

    # 连接数据库
    print("📦 步骤 2/4: 连接数据库...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        return False
    print()

    # 执行迁移
    print("📦 步骤 3/4: 执行迁移...")
    print("-" * 60)

    success = True

    # 1. 创建 config_profiles 表
    if not await create_config_profiles_table(conn):
        success = False

    # 2. 扩展 config_entries_v2 表
    if not await migrate_config_entries_add_profile_name(conn):
        success = False

    print("-" * 60)
    print()

    if not success:
        print("❌ 迁移失败，尝试回滚...")
        if backup_path:
            rollback_database(backup_path)
        conn.close()
        return False

    # 验证迁移
    print("📦 步骤 4/4: 验证迁移...")
    print("-" * 60)
    if not await verify_migration(conn):
        print("❌ 验证失败")
        conn.close()
        return False
    print("-" * 60)
    print()

    conn.close()

    print("=" * 60)
    print("✅ 迁移成功完成!")
    print("=" * 60)
    print()
    print("下一步:")
    print("1. 运行测试验证功能正常")
    print("2. 如有问题，可从备份恢复:")
    print(f"   python scripts/rollback_profiles.py {backup_path}")
    print()

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
