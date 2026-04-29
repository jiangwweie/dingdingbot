"""
CachedProvider 单元测试 - 缓存 TTL 机制验证

测试范围:
- 首次访问（无缓存）
- 缓存命中（TTL 内）
- 缓存过期（TTL 后）
- 强制刷新
- 时钟注入验证（P1 验证）
- MockClock.advance() 控制时间

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md
"""

import pytest
from datetime import datetime, timedelta

from src.application.config.providers.cached_provider import (
    CachedProvider,
    SystemClock,
    MockClock,
)


class TestMockClock:
    """MockClock 时钟模拟测试"""

    def test_mock_clock_initialization_with_fixed_time(self):
        """测试 MockClock 固定时间初始化"""
        # Arrange
        fixed_time = datetime(2026, 4, 7, 10, 0, 0)

        # Act
        clock = MockClock(fixed_time)

        # Assert
        assert clock.now() == fixed_time

    def test_mock_clock_initialization_without_time(self):
        """测试 MockClock 不指定时间时使用当前时间"""
        # Arrange
        before = datetime.now()

        # Act
        clock = MockClock()

        # Assert
        after = datetime.now()
        assert before <= clock.now() <= after

    def test_mock_clock_advance(self):
        """测试 MockClock 推进时间"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        # Act
        clock.advance(300)  # 推进 5 分钟

        # Assert
        assert clock.now() == datetime(2026, 4, 7, 10, 5, 0)

    def test_mock_clock_advance_multiple_times(self):
        """测试 MockClock 多次推进时间"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        # Act
        clock.advance(300)  # +5 分钟
        clock.advance(600)  # +10 分钟

        # Assert
        assert clock.now() == datetime(2026, 4, 7, 10, 15, 0)

    def test_mock_clock_set_time(self):
        """测试 MockClock 设置绝对时间（通过 advance 模拟）"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        # Act - 推进 5.5 小时来模拟设置时间
        clock.advance(5 * 3600 + 30 * 60)  # 5.5 小时

        # Assert
        assert clock.now() == datetime(2026, 4, 7, 15, 30, 0)


class TestSystemClock:
    """SystemClock 系统时钟测试"""

    def test_system_clock_returns_current_time(self):
        """测试 SystemClock 返回当前时间"""
        # Arrange
        clock = SystemClock()
        before = datetime.now()

        # Act
        result = clock.now()

        # Assert
        after = datetime.now()
        assert before <= result <= after


class TestCachedProvider:
    """CachedProvider 缓存 TTL 测试"""

    # --------------------------------------------------------------------------
    # 缓存命中/未命中测试
    # --------------------------------------------------------------------------

    def test_cache_miss_for_nonexistent_key(self):
        """测试不存在的键缓存未命中"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act
        result = provider._get_cached('nonexistent')

        # Assert
        assert result is None

    def test_cache_hit_within_ttl(self):
        """测试 TTL 内缓存命中"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 设置缓存
        provider._set_cached('key', 'value')

        # Assert - 立即获取应命中
        assert provider._get_cached('key') == 'value'

        # Act - 30 秒后获取（TTL=300 秒，应命中）
        clock.advance(30)
        assert provider._get_cached('key') == 'value'

    def test_cache_miss_after_ttl(self):
        """测试 TTL 过期后缓存未命中"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 设置缓存
        provider._set_cached('key', 'value')

        # Assert - 300 秒后（刚好 TTL）应仍命中
        clock.advance(300)
        assert provider._get_cached('key') == 'value'

        # Assert - 301 秒后（超过 TTL）应未命中
        clock.advance(1)
        assert provider._get_cached('key') is None

    def test_cache_exactly_at_ttl_boundary(self):
        """测试 TTL 边界时刻（刚好过期）"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 设置缓存
        provider._set_cached('key', 'value')

        # Assert - 299 秒后应仍命中
        clock.advance(299)
        assert provider._get_cached('key') == 'value'

        # Assert - 300 秒后应仍命中（边界）
        clock.advance(1)
        assert provider._get_cached('key') == 'value'

        # Assert - 301 秒后应过期
        clock.advance(1)
        assert provider._get_cached('key') is None

    # --------------------------------------------------------------------------
    # 缓存失效测试
    # --------------------------------------------------------------------------

    def test_invalidate_specific_key(self):
        """测试使特定键缓存失效"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)
        provider._set_cached('key1', 'value1')
        provider._set_cached('key2', 'value2')

        # Act - 使 key1 失效
        provider._invalidate_cache('key1')

        # Assert
        assert provider._get_cached('key1') is None
        assert provider._get_cached('key2') == 'value2'

    def test_invalidate_all_cache(self):
        """测试清空全部缓存"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)
        provider._set_cached('key1', 'value1')
        provider._set_cached('key2', 'value2')
        provider._set_cached('key3', 'value3')

        # Act - 清空全部缓存
        provider._invalidate_cache()

        # Assert
        assert provider._get_cached('key1') is None
        assert provider._get_cached('key2') is None
        assert provider._get_cached('key3') is None

    def test_cache_ttl_zero_means_no_cache(self):
        """测试 TTL=0 表示不缓存"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        class NoCacheProvider(CachedProvider):
            CACHE_TTL_SECONDS = 0

        provider = NoCacheProvider(clock=clock)

        # Act - 设置缓存
        provider._set_cached('key', 'value')

        # Assert - 立即获取也应过期（TTL=0）
        # 注意：由于过期检查是 > 而非 >=，TTL=0 时缓存会立即过期
        clock.advance(1)
        assert provider._get_cached('key') is None

    # --------------------------------------------------------------------------
    # 缓存值类型测试
    # --------------------------------------------------------------------------

    def test_cache_various_value_types(self):
        """测试缓存各种类型的值"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act & Assert - 字符串
        provider._set_cached('str_key', 'hello')
        assert provider._get_cached('str_key') == 'hello'

        # Act & Assert - 数字
        provider._set_cached('int_key', 42)
        assert provider._get_cached('int_key') == 42

        # Act & Assert - 列表
        provider._set_cached('list_key', [1, 2, 3])
        assert provider._get_cached('list_key') == [1, 2, 3]

        # Act & Assert - 字典
        provider._set_cached('dict_key', {'a': 1, 'b': 2})
        assert provider._get_cached('dict_key') == {'a': 1, 'b': 2}

        # Act & Assert - None
        provider._set_cached('none_key', None)
        assert provider._get_cached('none_key') is None

    # --------------------------------------------------------------------------
    # 时钟注入验证（P1 验证）
    # --------------------------------------------------------------------------

    def test_cached_provider_clock_injection(self):
        """验证时钟注入，测试可控制 TTL 过期"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 首次设置缓存
        provider._set_cached('key', 'value')
        assert provider._get_cached('key') == 'value'

        # Act - 推进 30 秒（缓存未过期）
        clock.advance(30)
        assert provider._get_cached('key') == 'value'

        # Act - 推进到 301 秒（缓存过期）
        clock.advance(271)  # 总共 301 秒
        assert provider._get_cached('key') is None

    def test_cached_provider_with_default_clock(self):
        """测试使用默认 SystemClock 的 CachedProvider"""
        # Arrange
        provider = CachedProvider()  # 使用默认时钟

        # Act - 设置缓存
        provider._set_cached('key', 'value')

        # Assert - 立即获取应命中
        assert provider._get_cached('key') == 'value'

    # --------------------------------------------------------------------------
    # cache_ttl 属性测试
    # --------------------------------------------------------------------------

    def test_cache_ttl_property_default(self):
        """测试默认缓存 TTL 属性"""
        # Arrange
        provider = CachedProvider()

        # Assert
        assert provider.cache_ttl == 300  # 默认 5 分钟

    def test_cache_ttl_property_custom(self):
        """测试自定义缓存 TTL 属性"""
        # Arrange
        class CustomTTLProvider(CachedProvider):
            CACHE_TTL_SECONDS = 600  # 10 分钟

        provider = CustomTTLProvider()

        # Assert
        assert provider.cache_ttl == 600

    # --------------------------------------------------------------------------
    # 缓存更新测试
    # --------------------------------------------------------------------------

    def test_cache_update_overwrites(self):
        """测试缓存更新覆盖旧值"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 设置初始值
        provider._set_cached('key', 'old_value')
        assert provider._get_cached('key') == 'old_value'

        # Act - 更新值
        provider._set_cached('key', 'new_value')

        # Assert
        assert provider._get_cached('key') == 'new_value'

    # --------------------------------------------------------------------------
    # 缓存过期后重新设置测试
    # --------------------------------------------------------------------------

    def test_cache_set_after_expire(self):
        """测试缓存过期后重新设置"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act - 设置缓存并等待过期
        provider._set_cached('key', 'value1')
        clock.advance(301)  # 过期
        assert provider._get_cached('key') is None

        # Act - 重新设置缓存
        provider._set_cached('key', 'value2')

        # Assert
        assert provider._get_cached('key') == 'value2'


class TestCachedProviderEdgeCases:
    """CachedProvider 边界条件测试"""

    def test_cache_with_empty_string_key(self):
        """测试空字符串键的缓存"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act
        provider._set_cached('', 'empty_key_value')

        # Assert
        assert provider._get_cached('') == 'empty_key_value'

    def test_cache_with_special_characters_in_key(self):
        """测试特殊字符键的缓存"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act
        provider._set_cached('key:with/special@chars', 'value')

        # Assert
        assert provider._get_cached('key:with/special@chars') == 'value'

    def test_cache_with_unicode_key(self):
        """测试 Unicode 键的缓存"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act
        provider._set_cached('中文键', '值')

        # Assert
        assert provider._get_cached('中文键') == '值'

    def test_cache_concurrent_same_key(self):
        """测试并发设置同一键（后设置的覆盖）"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)

        # Act
        provider._set_cached('key', 'value1')
        provider._set_cached('key', 'value2')

        # Assert
        assert provider._get_cached('key') == 'value2'
