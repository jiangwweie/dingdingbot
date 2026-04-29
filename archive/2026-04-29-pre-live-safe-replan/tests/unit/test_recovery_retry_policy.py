"""
Recovery Retry Policy 单元测试

测试目标：
1. retry_count=0/1/2... 时，next_retry_at 递增
2. 延迟有上限，不无限增长
3. 达到最大重试次数后 should_retry 返回 False
4. 未达到最大次数时 should_retry 返回 True
"""
import pytest

from src.application.recovery_retry_policy import (
    calculate_next_retry_at,
    should_retry,
    MAX_RECOVERY_RETRY_COUNT,
    BASE_RECOVERY_RETRY_DELAY_SECONDS,
    MAX_RECOVERY_RETRY_DELAY_SECONDS,
)


def test_retry_delay_increases_with_retry_count():
    """
    测试延迟随重试次数递增

    场景：
    1. retry_count=0/1/2/3
    断言：
    - next_retry_at 递增
    """
    now_ms = 1000000

    # retry_count=0: 60s 后
    next_retry_0 = calculate_next_retry_at(now_ms, retry_count=0)

    # retry_count=1: 120s 后
    next_retry_1 = calculate_next_retry_at(now_ms, retry_count=1)

    # retry_count=2: 240s 后
    next_retry_2 = calculate_next_retry_at(now_ms, retry_count=2)

    # retry_count=3: 480s 后
    next_retry_3 = calculate_next_retry_at(now_ms, retry_count=3)

    # 验证递增
    assert next_retry_1 > next_retry_0
    assert next_retry_2 > next_retry_1
    assert next_retry_3 > next_retry_2

    # 验证具体延迟值
    assert next_retry_0 == now_ms + (60 * 1000)  # 60s
    assert next_retry_1 == now_ms + (120 * 1000)  # 120s
    assert next_retry_2 == now_ms + (240 * 1000)  # 240s
    assert next_retry_3 == now_ms + (480 * 1000)  # 480s


def test_retry_delay_has_upper_limit():
    """
    测试延迟有上限

    场景：
    1. retry_count 非常大（如 10）
    断言：
    - next_retry_at 不超过上限（900s）
    """
    now_ms = 1000000

    # retry_count=10: 理论上应该是 60 * 2^10 = 61440s，但应该被截断到 900s
    next_retry_10 = calculate_next_retry_at(now_ms, retry_count=10)

    # 验证上限
    expected_delay_ms = MAX_RECOVERY_RETRY_DELAY_SECONDS * 1000
    assert next_retry_10 == now_ms + expected_delay_ms

    # 验证不超过上限
    actual_delay_ms = next_retry_10 - now_ms
    assert actual_delay_ms <= expected_delay_ms


def test_should_retry_returns_true_when_below_max():
    """
    测试未达到最大次数时可以重试

    场景：
    1. retry_count=0/1/2
    断言：
    - should_retry 返回 True
    """
    assert should_retry(retry_count=0) is True
    assert should_retry(retry_count=1) is True
    assert should_retry(retry_count=2) is True


def test_should_retry_returns_false_when_at_max():
    """
    测试达到最大重试次数后不能重试

    场景：
    1. retry_count=3/4/5
    断言：
    - should_retry 返回 False
    """
    assert should_retry(retry_count=3) is False
    assert should_retry(retry_count=4) is False
    assert should_retry(retry_count=5) is False


def test_exponential_backoff_formula():
    """
    测试指数退避公式

    公式：delay = base_delay * 2^retry_count
    上限：max_delay
    """
    now_ms = 1000000

    # 验证公式（未达上限时）
    for retry_count in range(4):
        next_retry = calculate_next_retry_at(now_ms, retry_count)
        expected_delay_seconds = BASE_RECOVERY_RETRY_DELAY_SECONDS * (2 ** retry_count)
        expected_delay_ms = expected_delay_seconds * 1000

        # 如果未达上限
        if expected_delay_seconds <= MAX_RECOVERY_RETRY_DELAY_SECONDS:
            assert next_retry == now_ms + expected_delay_ms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
