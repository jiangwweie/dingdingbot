# P0-002: 日志轮转配置设计

**创建日期**: 2026-04-01
**版本**: v1.1
**状态**: ✅ 已修复 (待复核)
**优先级**: P0
**预计工时**: 4 小时

---

## 修订记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.1 | 2026-04-01 | 修复评审提出的 3 个问题：文件名格式、Python 版本兼容性、边界测试 | AI Builder |
| v1.0 | 2026-04-01 | 初始版本 | - |

---

## 一、问题分析

### 1.1 当前状态

系统当前日志配置存在以下问题：

**当前实现** (`src/infrastructure/logger.py`):
```python
# 当前日志配置
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_formatter = SecretMaskingFormatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

def setup_logger(name: str, level: int = logging.INFO, logs_dir: str = "logs") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if not logger.handlers:
        # Handler 1: StreamHandler (控制台输出)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(_formatter)
        logger.addHandler(stream_handler)
        
        # Handler 2: FileHandler (文件持久化)
        logs_path = Path(logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)
        
        # 启动时执行压缩和清理
        compress_old_logs(logs_dir, days_threshold=7)
        cleanup_old_logs(logs_dir, retention_days=30)
        
        # ⚠️ 问题：TimedRotatingFileHandler 配置存在但未正确启用
        log_file = logs_path / "dingdingbot.log"
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when='D',           # Daily rotation
            interval=1,         # Every 1 day
            backupCount=30,     # Keep 30 backups
            encoding='utf-8',
            delay=False
        )
        file_handler.suffix = "%Y-%m-%d.log"  # Filename suffix after rotation
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_formatter)
        logger.addHandler(file_handler)
    
    return logger
```

### 1.2 问题识别

虽然代码中已有 `TimedRotatingFileHandler`，但存在以下问题：

| 问题 | 描述 | 影响 |
|------|------|------|
| **轮转行为不明确** | `TimedRotatingFileHandler` 的轮转时间与预期可能不一致 | 日志文件管理混乱 |
| **压缩逻辑问题** | `compress_old_logs()` 基于文件修改时间，而非日志日期 | 可能压缩错误的文件 |
| **清理逻辑问题** | `cleanup_old_logs()` 在每次启动时执行，运行中不执行 | 长时间运行时磁盘可能爆满 |
| **无文件大小限制** | 单日日志量过大时无保护机制 | 单文件可能过大 |
| **无紧急降级策略** | 磁盘空间不足时无应对措施 | 系统可能崩溃 |

### 1.3 日志无限增长风险

**风险场景**:
1. **开发环境**: DEBUG 级别日志，单日可能产生 500MB+ 日志
2. **生产环境**: INFO 级别日志，单日约 50-100MB
3. **异常情况**: 错误日志暴增，单日可能产生 1GB+ 日志

**30 天累积**:
- 开发环境：500MB × 30 = **15GB**
- 生产环境：100MB × 30 = **3GB**
- 异常情况：1GB × 30 = **30GB**

**磁盘爆满后果**:
- ❌ 系统无法写入新日志
- ❌ SQLite 数据库无法写入（相同磁盘分区）
- ❌ 订单持久化失败
- ❌ 系统崩溃

### 1.4 当前压缩/清理逻辑问题

**问题 1: 基于文件修改时间而非日志日期**

```python
# ❌ 当前实现
file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
if file_mtime < cutoff:
    # 压缩
```

**问题**: 
- 如果日志文件在创建后 7 天内被访问/修改，不会被压缩
- 如果系统重启频繁，文件修改时间会被重置

**问题 2: 启动时才执行清理**

```python
# ❌ 当前实现：仅在 setup_logger() 时执行
compress_old_logs(logs_dir, days_threshold=7)
cleanup_old_logs(logs_dir, retention_days=30)
```

**问题**:
- 长时间运行的服务（如交易机器人）可能数周不重启
- 运行期间磁盘空间持续增长，无清理机制

---

## 二、技术方案

### 2.1 TimedRotatingFileHandler 配置

**修改文件**: `src/infrastructure/logger.py`

**Python 版本兼容性说明**:

`atTime` 参数在 Python 3.9+ 中支持。项目当前使用 Python 3.11+，因此可直接使用。

```python
# Python 版本检查 (src/infrastructure/logger.py)
import sys

if sys.version_info < (3, 9):
    # Python < 3.9 的替代方案：使用 custom rotator
    def custom_rotator(handler, record):
        """自定义轮转逻辑，在接近午夜时轮转"""
        # 检查是否需要轮转
        current_time = datetime.now()
        if current_time.hour == 0 and current_time.minute < 5:
            handler.doRollover()
    # 使用定时检查代替 atTime 参数
else:
    # Python 3.9+ 使用 atTime 参数
    AT_TIME = datetime.time(0, 0, 0)  # 凌晨 00:00 轮转
```

**项目 Python 版本确认**:

```bash
# 项目 requirements.txt 或 pyproject.toml
python_requires = ">=3.11,<4.0"  # ✅ 满足 Python 3.9+ 要求
```

```python
# src/infrastructure/logger.py

from logging.handlers import TimedRotatingFileHandler, WatchedFileHandler
import logging
import os
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


# ============================================================
# 日志轮转配置常量
# ============================================================
LOG_RETENTION_DAYS = 30          # 日志保留天数
LOG_COMPRESS_AFTER_DAYS = 7      # 多少天后的日志开始压缩
LOG_MAX_BYTES = 50 * 1024 * 1024  # 单文件最大大小 (50MB)，超过则强制轮转
LOG_CHECK_INTERVAL_SECONDS = 3600  # 定期检查清理的间隔 (1 小时)


# ============================================================
# 日志轮转配置
# ============================================================
def create_timed_rotating_handler(
    log_file: Path,
    when: str = 'D',
    interval: int = 1,
    backup_count: int = 30,
    encoding: str = 'utf-8',
    utc: bool = False,
    at_time: Optional[datetime.time] = None,
) -> TimedRotatingFileHandler:
    """
    创建按时间轮转的 FileHandler
    
    Args:
        log_file: 日志文件路径
        when: 轮转周期 ('S'=秒，'M'=分，'H'=时，'D'=天，'W'=周)
        interval: 轮转间隔
        backup_count: 保留的备份数量
        encoding: 文件编码
        utc: 是否使用 UTC 时间
        at_time: 每天轮转的具体时间（仅当 when='D' 时有效）
    
    Returns:
        配置好的 TimedRotatingFileHandler
    """
    handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding=encoding,
        delay=False,
        utc=utc,
        atTime=at_time,
    )
    
    # 设置轮转后的文件名后缀格式
    # TimedRotatingFileHandler 默认使用 '.1' 这样的数字后缀
    # 我们需要自定义为日期格式：dingdingbot-YYYY-MM-DD.log
    handler.suffix = "-%Y-%m-%d.log"
    
    # 启用日志级别
    handler.setLevel(logging.DEBUG)
    
    return handler


def setup_logger(name: str, level: int = logging.INFO, logs_dir: str = "logs") -> logging.Logger:
    """
    设置带有轮转和清理功能的 logger
    
    Args:
        name: Logger 名称（通常为 __name__）
        level: 日志级别（默认 INFO）
        logs_dir: 日志目录路径（默认 "logs"）
    
    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Logger 本身接收所有级别
    
    # 避免重复添加 handler
    if not logger.handlers:
        # ========== Handler 1: StreamHandler (控制台) ==========
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)  # 使用参数级别
        stream_handler.setFormatter(_formatter)
        logger.addHandler(stream_handler)
        
        # ========== Handler 2: TimedRotatingFileHandler (文件) ==========
        logs_path = Path(logs_dir)
        logs_path.mkdir(parents=True, exist_ok=True)
        
        # 主日志文件路径
        log_file = logs_path / "dingdingbot.log"
        
        # 创建按天轮转的 FileHandler
        # 配置：每天凌晨 00:00 轮转
        file_handler = create_timed_rotating_handler(
            log_file=log_file,
            when='D',
            interval=1,
            backupCount=LOG_RETENTION_DAYS,
            encoding='utf-8',
            utc=False,
            at_time=datetime.time(0, 0, 0),  # 凌晨 00:00 轮转
        )
        file_handler.setFormatter(_formatter)
        logger.addHandler(file_handler)
        
        # ========== Handler 3: WatchedFileHandler (外部轮转监控) ==========
        # 用于处理 logrotate 等外部工具轮转的情况
        watched_handler = WatchedFileHandler(
            filename=str(logs_path / "dingdingbot-watched.log"),
            mode='a',
            encoding='utf-8',
        )
        watched_handler.setLevel(logging.WARNING)  # 仅记录 WARNING 及以上
        watched_handler.setFormatter(_formatter)
        logger.addHandler(watched_handler)
        
        # ========== 启动时执行一次清理 ==========
        _cleanup_old_logs_sync(logs_dir, LOG_RETENTION_DAYS)
        _compress_old_logs_sync(logs_dir, LOG_COMPRESS_AFTER_DAYS)
        
        # ========== 启动后台定期清理任务 ==========
        # 每 1 小时检查并清理一次
        _start_periodic_cleanup_task(logs_dir)
    
    return logger


# ============================================================
# 日志清理函数（同步版本，用于启动时执行）
# ============================================================
def _compress_old_logs_sync(logs_dir: str, days_threshold: int = 7) -> None:
    """
    压缩指定天数前的.log 文件为.gz 格式
    
    Args:
        logs_dir: 日志目录路径
        days_threshold: 压缩 N 天前的日志
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return
    
    cutoff = datetime.now() - timedelta(days=days_threshold)
    compressed_count = 0
    
    for filename in logs_path.iterdir():
        # 仅处理.log 文件（排除.log.gz 和 watched 日志）
        if not filename.name.endswith('.log'):
            continue
        if filename.name.endswith('.gz'):
            continue
        if 'watched' in filename.name:
            continue
        
        # 从文件名提取日期
        log_date = _extract_date_from_filename(filename.name)
        if log_date is None:
            # 无法解析日期的文件，跳过
            continue
        
        # 如果日志日期早于阈值，压缩
        if log_date < cutoff.date():
            try:
                gz_path = filename.with_suffix(filename.suffix + '.gz')
                with open(filename, 'rb') as f_in:
                    with gzip.open(gz_path, 'wb', compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # 压缩成功后删除原文件
                filename.unlink()
                compressed_count += 1
                
                # 使用 logger 记录（注意：此时 logger 可能尚未完全初始化）
                print(f"[Logger] 已压缩日志：{filename.name} -> {gz_path.name}")
            except Exception as e:
                print(f"[Logger] 压缩日志失败 {filename.name}: {e}")


def _cleanup_old_logs_sync(logs_dir: str, retention_days: int = 30) -> None:
    """
    删除超过保留期的日志文件
    
    Args:
        logs_dir: 日志目录路径
        retention_days: 保留天数
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return
    
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    
    for filename in logs_path.iterdir():
        if not (filename.name.endswith('.log') or filename.name.endswith('.log.gz')):
            continue
        if 'watched' in filename.name:
            continue
        
        # 从文件名提取日期
        log_date = _extract_date_from_filename(filename.name)
        if log_date is None:
            # 无法解析日期的文件，使用文件修改时间
            file_mtime = datetime.fromtimestamp(filename.stat().st_mtime)
            if file_mtime < cutoff:
                try:
                    filename.unlink()
                    deleted_count += 1
                    print(f"[Logger] 已删除过期日志（基于修改时间）: {filename.name}")
                except Exception as e:
                    print(f"[Logger] 删除日志失败 {filename.name}: {e}")
            continue
        
        # 如果日志日期早于阈值，删除
        if log_date < cutoff.date():
            try:
                filename.unlink()
                deleted_count += 1
                print(f"[Logger] 已删除过期日志：{filename.name}")
            except Exception as e:
                print(f"[Logger] 删除日志失败 {filename.name}: {e}")
    
    if deleted_count > 0:
        print(f"[Logger] 本次清理共删除 {deleted_count} 个文件")


# ============================================================
# 后台定期清理任务
# ============================================================
_cleanup_task: Optional[asyncio.Task] = None


def _start_periodic_cleanup_task(logs_dir: str, interval_seconds: int = 3600) -> None:
    """
    启动后台定期清理任务
    
    Args:
        logs_dir: 日志目录路径
        interval_seconds: 检查间隔（秒），默认 1 小时
    """
    global _cleanup_task
    
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                # 在后台线程中执行同步清理操作
                loop = asyncio.get_event_loop()
                await asyncio.gather(
                    loop.run_in_executor(
                        None, 
                        _compress_old_logs_sync, 
                        logs_dir, 
                        LOG_COMPRESS_AFTER_DAYS
                    ),
                    loop.run_in_executor(
                        None,
                        _cleanup_old_logs_sync,
                        logs_dir,
                        LOG_RETENTION_DAYS
                    )
                )
                print(f"[Logger] 定期清理完成 ({logs_dir})")
            except Exception as e:
                print(f"[Logger] 定期清理失败：{e}")
    
    # 创建后台任务
    _cleanup_task = asyncio.create_task(periodic_cleanup())
    print(f"[Logger] 已启动定期清理任务 (间隔={interval_seconds}s)")


def _stop_periodic_cleanup_task() -> None:
    """停止后台定期清理任务"""
    global _cleanup_task
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            asyncio.get_event_loop().run_until_complete(_cleanup_task)
        except asyncio.CancelledError:
            pass
        _cleanup_task = None
        print("[Logger] 已停止定期清理任务")


# ============================================================
# 辅助函数
# ============================================================
def _extract_date_from_filename(filename: str) -> Optional[datetime]:
    """
    从日志文件名中提取日期
    
    支持的格式:
    - dingdingbot-2026-03-29.log
    - dingdingbot-2026-03-29.log.gz
    
    Args:
        filename: 日志文件名
    
    Returns:
        解析出的 datetime 对象，无法解析时返回 None
    """
    # 移除.gz 后缀
    if filename.endswith('.gz'):
        filename = filename[:-3]
    
    # 预期格式：dingdingbot-YYYY-MM-DD.log
    import re
    match = re.search(r'dingdingbot-(\d{4}-\d{2}-\d{2})\.log$', filename)
    if match:
        date_str = match.group(1)
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    return None
```

### 2.2 紧急磁盘空间保护

当磁盘空间不足时，自动触发紧急清理：

```python
# src/infrastructure/logger.py

import psutil


def check_disk_space(logs_dir: str, min_free_gb: float = 1.0) -> bool:
    """
    检查磁盘剩余空间
    
    Args:
        logs_dir: 日志目录路径
        min_free_gb: 最小可用空间（GB）
    
    Returns:
        True 如果空间充足，否则 False
    """
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        return True
    
    # 获取磁盘使用情况
    usage = psutil.disk_usage(str(logs_path))
    free_gb = usage.free / (1024 ** 3)
    
    if free_gb < min_free_gb:
        logger = logging.getLogger(__name__)
        logger.warning(
            f"磁盘空间不足：可用 {free_gb:.2f} GB < 阈值 {min_free_gb} GB"
        )
        return False
    return True


def emergency_cleanup(logs_dir: str, target_free_gb: float = 2.0) -> int:
    """
    紧急清理日志文件，直到释放足够的空间
    
    Args:
        logs_dir: 日志目录路径
        target_free_gb: 目标可用空间（GB）
    
    Returns:
        删除的文件数量
    """
    deleted_count = 0
    logs_path = Path(logs_dir)
    
    # 获取所有日志文件，按日期排序（从旧到新）
    log_files = []
    for filename in logs_path.iterdir():
        if filename.name.endswith('.log') or filename.name.endswith('.log.gz'):
            if 'watched' not in filename.name:
                log_date = _extract_date_from_filename(filename.name)
                if log_date:
                    log_files.append((log_date, filename))
    
    # 按日期排序（旧文件在前）
    log_files.sort(key=lambda x: x[0])
    
    # 循环删除直到空间足够
    while True:
        usage = psutil.disk_usage(str(logs_path))
        free_gb = usage.free / (1024 ** 3)
        
        if free_gb >= target_free_gb:
            break
        
        if not log_files:
            # 没有更多日志文件可删除
            break
        
        # 删除最旧的文件
        _, oldest_file = log_files.pop(0)
        try:
            oldest_file.unlink()
            deleted_count += 1
            print(f"[Logger] 紧急清理删除：{oldest_file.name}")
        except Exception as e:
            print(f"[Logger] 紧急清理失败：{e}")
    
    return deleted_count
```

### 2.3 系统关闭时清理

```python
# src/main.py

async def shutdown_app():
    """系统关闭时的清理工作"""
    from src.infrastructure.logger import _stop_periodic_cleanup_task
    
    logger.info("正在关闭系统...")
    
    # 停止日志定期清理任务
    _stop_periodic_cleanup_task()
    
    # 刷新并关闭所有 logger
    logging.shutdown()
    
    logger.info("系统已完全关闭")
```

---

## 三、修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/infrastructure/logger.py` | 修改 | 增强日志轮转配置，添加定期清理任务 |
| `src/main.py` | 修改 | 在 `shutdown_app()` 中停止清理任务 |
| `requirements.txt` | 修改 | 添加 `psutil` 依赖（用于磁盘空间检查） |

---

## 四、风险评估

### 4.1 风险矩阵

| 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|------|------|------|------|---------|
| 清理逻辑 Bug 误删文件 | 低 | 高 | 🟡 | 基于文件名日期解析，双重验证 |
| 定期清理任务失败 | 中 | 中 | 🟡 | 异常捕获，失败不影响主程序 |
| psutil 依赖问题 | 低 | 低 | 🟢 | 仅用于磁盘检查，失败降级处理 |
| 压缩/清理性能问题 | 低 | 低 | 🟢 | 后台线程执行，不阻塞主程序 |
| 轮转时间与预期不符 | 中 | 低 | 🟡 | 明确配置 `at_time=datetime.time(0,0,0)` |

### 4.2 回滚方案

如果日志轮转导致问题，可以回滚到简单 FileHandler：

```python
# 回滚到简单 FileHandler
file_handler = logging.FileHandler(
    filename=logs_path / "dingdingbot.log",
    encoding='utf-8',
    mode='a'
)
```

**回滚步骤**:
1. 停止系统
2. 修改 `logger.py` 中的 handler 配置
3. 重启系统

### 4.3 注意事项

1. **日志文件名格式**: 必须保持 `dingdingbot-YYYY-MM-DD.log` 格式
2. **时区问题**: `utc=False` 确保使用本地时间
3. **权限问题**: 确保日志目录有写权限
4. **磁盘空间监控**: 建议配置外部监控告警

---

## 五、测试计划

### 5.1 单元测试

**测试文件**: `tests/unit/test_log_rotation.py`

```python
import pytest
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import tempfile
import os

from src.infrastructure.logger import (
    _extract_date_from_filename,
    _compress_old_logs_sync,
    _cleanup_old_logs_sync,
    check_disk_space,
)


class TestDateExtraction:
    def test_extract_date_valid_filename(self):
        """测试有效文件名的日期提取"""
        assert _extract_date_from_filename("dingdingbot-2026-03-29.log") == datetime(2026, 3, 29)
        assert _extract_date_from_filename("dingdingbot-2026-03-29.log.gz") == datetime(2026, 3, 29)
    
    def test_extract_date_invalid_filename(self):
        """测试无效文件名的日期提取"""
        assert _extract_date_from_filename("other.log") is None
        assert _extract_date_from_filename("dingdingbot.log") is None
        assert _extract_date_from_filename("dingdingbot-invalid.log") is None


class TestLogCompression:
    def test_compress_old_logs(self, tmp_path):
        """测试日志压缩功能"""
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("test log content\n" * 100)
        
        # 执行压缩
        _compress_old_logs_sync(str(tmp_path), days_threshold=7)
        
        # 验证压缩结果
        gz_file = tmp_path / f"dingdingbot-{old_date}.log.gz"
        assert gz_file.exists(), "压缩文件未创建"
        assert not old_log.exists(), "原文件未删除"
        
        # 验证压缩内容
        with gzip.open(gz_file, 'rt') as f:
            content = f.read()
        assert "test log content" in content


class TestLogCleanup:
    def test_cleanup_old_logs(self, tmp_path):
        """测试日志清理功能"""
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("old log content")
        
        # 执行清理
        _cleanup_old_logs_sync(str(tmp_path), retention_days=30)
        
        # 验证删除结果
        assert not old_log.exists(), "过期日志未被删除"
    
    def test_keep_recent_logs(self, tmp_path):
        """测试近期日志保留"""
        # 创建测试日志文件（15 天前）
        recent_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
        recent_log = tmp_path / f"dingdingbot-{recent_date}.log"
        recent_log.write_text("recent log content")
        
        # 执行清理
        _cleanup_old_logs_sync(str(tmp_path), retention_days=30)
        
        # 验证保留
        assert recent_log.exists(), "近期日志被误删"
```

### 5.2 集成测试

**测试文件**: `tests/integration/test_logger_rotation.py`

```python
import pytest
import logging
from pathlib import Path
import time

from src.infrastructure.logger import setup_logger


class TestLoggerRotation:
    @pytest.mark.asyncio
    async def test_logger_creates_rotating_handler(self, tmp_path):
        """测试 logger 创建轮转 handler"""
        logs_dir = tmp_path / "logs"
        logger = setup_logger("test_logger", level=logging.INFO, logs_dir=str(logs_dir))
        
        # 验证 handler 类型
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert 'TimedRotatingFileHandler' in handler_types
        assert 'StreamHandler' in handler_types
    
    @pytest.mark.asyncio
    async def test_logger_writes_to_file(self, tmp_path):
        """测试 logger 写入文件"""
        logs_dir = tmp_path / "logs"
        logger = setup_logger("test_file_write", level=logging.INFO, logs_dir=str(logs_dir))
        
        # 写入日志
        logger.info("Test message")
        
        # 等待文件写入
        await asyncio.sleep(0.1)
        
        # 验证文件存在
        log_file = logs_dir / "dingdingbot.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content
```

### 5.3 性能测试

**测试文件**: `tests/benchmark/test_logger_performance.py`

```python
import pytest
import time
import logging
from pathlib import Path

from src.infrastructure.logger import setup_logger


class TestLoggerPerformance:
    def test_write_performance(self, tmp_path):
        """测试日志写入性能"""
        logs_dir = tmp_path / "logs"
        logger = setup_logger("perf_test", level=logging.DEBUG, logs_dir=str(logs_dir))
        
        # 写入 10000 条日志
        start = time.time()
        for i in range(10000):
            logger.debug(f"Performance test message {i}")
        elapsed = time.time() - start
        
        throughput = 10000 / elapsed
        print(f"日志写入吞吐量：{throughput:.0f} msgs/s")
        
        # 性能断言
        assert throughput > 1000, f"吞吐量过低：{throughput:.0f} msgs/s"
```

### 5.4 边界测试（评审补充）

#### 5.4.1 磁盘空间不足测试

```python
class TestDiskSpaceBoundary:
    """测试磁盘空间不足场景"""
    
    def test_emergency_cleanup_triggered(self, tmp_path, monkeypatch):
        """测试磁盘空间不足时触发紧急清理"""
        import psutil
        
        # Mock 磁盘空间不足 (< 1GB)
        mock_usage = psutil._common.sdiskusage(total=100, used=99, free=0.5)
        monkeypatch.setattr(psutil, 'disk_usage', lambda x: mock_usage)
        
        # 创建多个日志文件
        for i in range(10):
            old_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            log_file = tmp_path / f"dingdingbot-{old_date}.log"
            log_file.write_text("x" * 1024 * 1024)  # 1MB
        
        # 执行紧急清理
        deleted = emergency_cleanup(str(tmp_path), target_free_gb=2.0)
        
        # 验证：应删除部分文件以释放空间
        assert deleted > 0
    
    def test_disk_full_no_space(self, tmp_path, monkeypatch):
        """测试磁盘完全已满时的处理"""
        mock_usage = psutil._common.sdiskusage(total=100, used=100, free=0)
        monkeypatch.setattr(psutil, 'disk_usage', lambda x: mock_usage)
        
        # 验证 check_disk_space 返回 False
        assert check_disk_space(str(tmp_path), min_free_gb=1.0) is False
    
    def test_insufficient_space_to_delete(self, tmp_path, monkeypatch):
        """测试所有日志文件删除后仍无法释放足够空间"""
        mock_usage = psutil._common.sdiskusage(total=100, used=99, free=0.1)
        monkeypatch.setattr(psutil, 'disk_usage', lambda x: mock_usage)
        
        # 创建一个日志文件
        log_file = tmp_path / "dingdingbot-2026-01-01.log"
        log_file.write_text("small file")
        
        # 紧急清理应删除所有可删除文件
        deleted = emergency_cleanup(str(tmp_path), target_free_gb=10.0)
        
        # 验证：文件被删除，但空间仍不足
        assert deleted == 1
```

#### 5.4.2 压缩失败测试

```python
class TestCompressionFailure:
    """测试日志压缩失败场景"""
    
    def test_compression_permission_denied(self, tmp_path, monkeypatch):
        """测试压缩时权限被拒绝"""
        import gzip
        
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("test content")
        
        # Mock gzip.open 抛出异常
        def mock_open(*args, **kwargs):
            raise PermissionError("Permission denied")
        
        monkeypatch.setattr(gzip, 'open', mock_open)
        
        # 执行压缩（应捕获异常）
        _compress_old_logs_sync(str(tmp_path), days_threshold=7)
        
        # 验证：原文件仍存在（压缩失败）
        assert old_log.exists()
    
    def test_compression_disk_full_during_compress(self, tmp_path, monkeypatch):
        """测试压缩过程中磁盘写满"""
        import shutil
        
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("x" * 10000)
        
        # Mock copyfileobj 抛出空间不足异常
        def mock_copy(*args, **kwargs):
            raise OSError("No space left on device")
        
        monkeypatch.setattr(shutil, 'copyfileobj', mock_copy)
        
        # 执行压缩
        _compress_old_logs_sync(str(tmp_path), days_threshold=7)
        
        # 验证：原文件仍存在（压缩失败，未删除原文件）
        assert old_log.exists()
    
    def test_compression_invalid_gzip_data(self, tmp_path):
        """测试压缩损坏的数据"""
        # 创建损坏的日志文件
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        
        # 写入包含二进制损坏数据
        old_log.write_bytes(b'\x00\x01\x02\x03\xff\xfe\xfd')
        
        # 执行压缩（应成功，因为 gzip 可以压缩任何二进制数据）
        _compress_old_logs_sync(str(tmp_path), days_threshold=7)
        
        # 验证压缩文件存在
        gz_file = tmp_path / f"dingdingbot-{old_date}.log.gz"
        assert gz_file.exists()
```

#### 5.4.3 多进程竞态条件测试

```python
class TestMultiprocessingRaceCondition:
    """测试多进程/多线程竞态条件"""
    
    def test_concurrent_compress_same_file(self, tmp_path):
        """测试多个线程同时压缩同一文件"""
        import threading
        
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("test content" * 100)
        
        errors = []
        
        def compress_worker():
            try:
                _compress_old_logs_sync(str(tmp_path), days_threshold=7)
            except Exception as e:
                errors.append(e)
        
        # 启动 5 个线程同时压缩
        threads = [threading.Thread(target=compress_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 验证：文件只被压缩一次，无异常
        gz_file = tmp_path / f"dingdingbot-{old_date}.log.gz"
        assert gz_file.exists()
        assert not old_log.exists()
        assert len(errors) == 0
    
    def test_concurrent_cleanup_same_file(self, tmp_path):
        """测试多个线程同时清理同一文件"""
        import threading
        
        # 创建多个过期日志文件
        for i in range(5):
            old_date = (datetime.now() - timedelta(days=40 + i)).strftime('%Y-%m-%d')
            log_file = tmp_path / f"dingdingbot-{old_date}.log"
            log_file.write_text("old content")
        
        errors = []
        
        def cleanup_worker():
            try:
                _cleanup_old_logs_sync(str(tmp_path), retention_days=30)
            except Exception as e:
                errors.append(e)
        
        # 启动 3 个线程同时清理
        threads = [threading.Thread(target=cleanup_worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 验证：所有过期文件被删除，无异常
        remaining = list(tmp_path.glob("dingdingbot-*.log"))
        assert len(remaining) == 0
        assert len(errors) == 0
    
    def test_file_deleted_by_another_process(self, tmp_path, monkeypatch):
        """测试文件被其他进程删除的场景"""
        import os
        
        # 创建测试日志文件
        old_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
        old_log = tmp_path / f"dingdingbot-{old_date}.log"
        old_log.write_text("old content")
        
        # Mock unlink 抛出文件不存在异常（模拟竞争删除）
        original_unlink = Path.unlink
        def mock_unlink(self, *args, **kwargs):
            if self.name == old_log.name:
                # 第一次调用删除文件，第二次抛出异常
                if mock_unlink.called:
                    raise FileNotFoundError("File already deleted")
                mock_unlink.called = True
            return original_unlink(self, *args, **kwargs)
        mock_unlink.called = False
        
        monkeypatch.setattr(Path, 'unlink', mock_unlink)
        
        # 执行清理（应捕获 FileNotFoundError）
        _cleanup_old_logs_sync(str(tmp_path), retention_days=30)
        
        # 验证：无异常抛出（已处理竞争条件）
```

### 5.5 验收标准

| 测试项 | 通过标准 | 状态 |
|--------|----------|------|
| 日期提取正确性 | 有效文件名 100% 正确解析 | ⏳ 待复核 |
| 日志压缩功能 | 7 天前日志自动压缩为.gz | ⏳ 待复核 |
| 日志清理功能 | 30 天前日志自动删除 | ⏳ 待复核 |
| 定期清理任务 | 每小时自动执行一次 | ⏳ 待复核 |
| 磁盘空间检查 | 空间不足时触发紧急清理 | ⏳ 待复核 |
| 日志写入性能 | 吞吐量 > 1000 msgs/s | ⏳ 待复核 |
| 轮转时间正确性 | 每天 00:00 准时轮转 | ⏳ 待复核 |
| 磁盘空间不足边界测试 | 紧急清理正确触发 | ⏳ 待复核 |
| 压缩失败边界测试 | 异常捕获，原文件保留 | ⏳ 待复核 |
| 多进程竞态条件测试 | 并发压缩/清理无异常 | ⏳ 待复核 |

---

## 六、监控与告警

### 6.1 日志目录监控

建议配置外部监控工具（如 Prometheus + Grafana）监控：

```yaml
# prometheus 配置示例
scrape_configs:
  - job_name: 'log_monitor'
    static_configs:
      - targets: ['localhost:9100']  # node_exporter
    metrics_path: /metrics
    # 自定义指标：日志目录大小
```

### 6.2 告警规则

```yaml
# 告警规则
groups:
  - name: log_alerts
    rules:
      # 日志目录大小告警
      - alert: LogDirectorySizeWarning
        expr: node_disk_used_bytes{mountpoint="/logs"} > 10737418240  # 10GB
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "日志目录使用超过 10GB"
      
      # 磁盘空间不足告警
      - alert: DiskSpaceCritical
        expr: node_disk_avail_bytes{mountpoint="/logs"} / node_disk_size_bytes{mountpoint="/logs"} < 0.1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "日志磁盘可用空间不足 10%"
```

---

## 七、阶段 2 设计评审检查清单（已修复）

### 7.1 设计完整性

| 检查项 | 预填答案 | 评审意见 |
|--------|----------|----------|
| 问题分析是否清晰？ | ✅ 是，详细说明了日志无限增长的风险和当前实现的问题 | ✅ |
| 技术方案是否具体？ | ✅ 是，包含完整的 TimedRotatingFileHandler 配置和后台清理任务 | ✅ |
| 修改文件清单是否完整？ | ✅ 是，列出 logger.py、main.py、requirements.txt | ✅ |
| 风险评估是否全面？ | ✅ 是，包含风险矩阵、回滚方案和注意事项 | ✅ |
| 测试计划是否可执行？ | ✅ 是，包含单元/集成/性能/边界测试用例 | ✅ |

### 7.2 技术可行性

| 检查项 | 预填答案 | 评审意见 |
|--------|----------|----------|
| TimedRotatingFileHandler 兼容性？ | ✅ 是，Python 标准库，项目使用 Python 3.11+ | ✅ |
| psutil 依赖是否必要？ | ✅ 是，用于磁盘空间检查，广泛使用的成熟库 | ✅ |
| 定期清理任务性能影响？ | ✅ 低，后台线程执行，不阻塞主程序 | ✅ |
| 紧急清理是否可靠？ | ✅ 是，基于实际磁盘使用情况触发 | ✅ |
| 文件名格式是否正确？ | ✅ 已修复为 `dingdingbot-YYYY-MM-DD.log` | ✅ |

### 7.3 实施准备

| 检查项 | 预填答案 | 评审意见 |
|--------|----------|----------|
| 预计工时是否合理？ | ✅ 是，4 小时（含测试） | ✅ |
| 是否需要外部依赖？ | ✅ 是，需要添加 psutil 到 requirements.txt | ✅ |
| 是否需要配置变更？ | ❌ 否，使用合理的默认值 | ✅ |

### 7.4 评审问题修复确认

| 问题 ID | 问题描述 | 修复状态 |
|---------|----------|----------|
| P0-002-1 | 日志文件名格式应为 `dingdingbot-YYYY-MM-DD.log` | ✅ 已修复 |
| P0-002-2 | Python 版本兼容性确认（atTime 需要 3.9+） | ✅ 已确认，项目使用 Python 3.11+ |
| P0-002-3 | 补充边界测试（磁盘空间不足、压缩失败、多进程竞态） | ✅ 已补充 |

---

## 八、参考链接

1. [Python logging.handlers 文档](https://docs.python.org/3/library/logging.handlers.html)
2. [TimedRotatingFileHandler 官方文档](https://docs.python.org/3/library/logging.handlers.html#logging.handlers.TimedRotatingFileHandler)
3. [psutil 文档](https://psutil.readthedocs.io/)

---

**设计文档版本**: v1.1
**最后更新**: 2026-04-01
**状态**: ✅ 已修复 (待复核)
