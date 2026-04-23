"""
Recovery Retry Policy - PG 恢复任务重试策略

职责：
1. 定义 recovery task 的 retry/backoff 策略参数
2. 提供计算 next_retry_at 的统一函数
3. 集中管理重试规则，避免硬编码散落

设计原则：
- 指数退避：延迟随重试次数增长
- 延迟上限：避免无限增长
- 可维护性：参数集中，易于调整
"""

from typing import Final

# ============================================
# Retry/Backoff 策略参数
# ============================================

MAX_RECOVERY_RETRY_COUNT: Final[int] = 3
"""最大重试次数"""

BASE_RECOVERY_RETRY_DELAY_SECONDS: Final[int] = 60
"""基础重试延迟（秒）"""

MAX_RECOVERY_RETRY_DELAY_SECONDS: Final[int] = 900
"""最大重试延迟（秒，15 分钟）"""


# ============================================
# 计算函数
# ============================================

def calculate_next_retry_at(now_ms: int, retry_count: int) -> int:
    """
    计算下次重试时间戳（指数退避）

    Args:
        now_ms: 当前时间戳（毫秒）
        retry_count: 当前重试次数

    Returns:
        int: 下次重试时间戳（毫秒）

    策略：
    - retry_count=0: 60s 后
    - retry_count=1: 120s 后
    - retry_count=2: 240s 后
    - retry_count>=3: 900s 后（上限）
    """
    # 指数退避：delay = base_delay * 2^retry_count
    delay_seconds = BASE_RECOVERY_RETRY_DELAY_SECONDS * (2 ** retry_count)

    # 上限截断
    delay_seconds = min(delay_seconds, MAX_RECOVERY_RETRY_DELAY_SECONDS)

    # 转换为毫秒时间戳
    return now_ms + (delay_seconds * 1000)


def should_retry(retry_count: int) -> bool:
    """
    判断是否应该继续重试

    Args:
        retry_count: 当前重试次数

    Returns:
        bool: True 表示可以继续重试，False 表示已达上限
    """
    return retry_count < MAX_RECOVERY_RETRY_COUNT
