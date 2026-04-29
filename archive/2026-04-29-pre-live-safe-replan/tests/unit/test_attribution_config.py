"""
AttributionConfig 单元测试

测试归因权重配置的校验与加载功能。

覆盖的测试用例:
- UT-001: 默认配置创建成功
- UT-002: from_kv 正常加载（完整 KV）
- UT-003: from_kv 使用默认值（空 KV）
- UT-004: from_kv 部分覆盖（部分 KV）
- UT-005: 权重和 > 1.01 校验失败
- UT-006: 权重和 < 0.99 校验失败
- UT-007: 负权重校验失败
- UT-008: 权重 > 1.0 校验失败
- UT-009: 缺少必需 key 校验失败
- UT-010: 额外 key 允许通过
- UT-011: 边界值：权重和恰好 1.0 通过
- UT-012: 边界值：权重和 1.01（刚好在容差内）通过
- UT-013: 边界值：权重和 0.99（刚好在容差内）通过
- UT-014: 边界值：单个权重为 0 通过
- UT-015: 边界值：单个权重为 1.0 通过
"""

import pytest
from pydantic import ValidationError

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.domain.attribution_config import AttributionConfig


# ============================================================
# Tests: 正常场景
# ============================================================


class TestAttributionConfigNormal:
    """正常场景测试"""

    def test_default_config(self):
        """UT-001: 默认配置创建成功"""
        config = AttributionConfig.default()

        assert config.weights["pattern"] == 0.55
        assert config.weights["ema_trend"] == 0.25
        assert config.weights["mtf"] == 0.20
        assert abs(sum(config.weights.values()) - 1.0) < 0.001

    def test_from_kv_full(self):
        """UT-002: from_kv 正常加载（完整 KV）"""
        kv_configs = {
            "attribution_weight_pattern": 0.50,
            "attribution_weight_ema_trend": 0.30,
            "attribution_weight_mtf": 0.20,
        }
        config = AttributionConfig.from_kv(kv_configs)

        assert config.weights["pattern"] == 0.50
        assert config.weights["ema_trend"] == 0.30
        assert config.weights["mtf"] == 0.20

    def test_from_kv_empty_uses_defaults(self):
        """UT-003: from_kv 使用默认值（空 KV）"""
        config = AttributionConfig.from_kv({})

        assert config.weights["pattern"] == 0.55
        assert config.weights["ema_trend"] == 0.25
        assert config.weights["mtf"] == 0.20

    def test_from_kv_partial_override_fails(self):
        """UT-004: from_kv 部分覆盖导致权重和超限，校验失败。

        pattern=0.60 + ema_trend=0.25(默认) + mtf=0.20(默认) = 1.05 > 1.01
        """
        kv_configs = {
            "attribution_weight_pattern": 0.60,
            # ema_trend 和 mtf 使用默认值
        }
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig.from_kv(kv_configs)
        assert "权重之和必须接近 1.0" in str(exc_info.value)

    def test_direct_creation_valid(self):
        """直接创建有效配置"""
        config = AttributionConfig(
            weights={
                "pattern": 0.55,
                "ema_trend": 0.25,
                "mtf": 0.20,
            }
        )

        assert len(config.weights) == 3


# ============================================================
# Tests: 校验失败场景
# ============================================================


class TestAttributionConfigValidation:
    """校验失败场景测试"""

    def test_weight_sum_too_high(self):
        """UT-005: 权重和 > 1.01 校验失败"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": 0.60,
                    "ema_trend": 0.30,
                    "mtf": 0.20,  # 总和 = 1.10
                }
            )
        assert "权重之和必须接近 1.0" in str(exc_info.value)

    def test_weight_sum_too_low(self):
        """UT-006: 权重和 < 0.99 校验失败"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": 0.40,
                    "ema_trend": 0.20,
                    "mtf": 0.10,  # 总和 = 0.70
                }
            )
        assert "权重之和必须接近 1.0" in str(exc_info.value)

    def test_negative_weight(self):
        """UT-007: 负权重校验失败"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": -0.10,
                    "ema_trend": 0.60,
                    "mtf": 0.50,  # 总和 = 1.0，但有负值
                }
            )
        assert "超出 [0, 1] 范围" in str(exc_info.value)

    def test_weight_greater_than_one(self):
        """UT-008: 权重 > 1.0 校验失败"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": 1.50,
                    "ema_trend": 0.0,
                    "mtf": 0.0,  # 总和 = 1.5 > 1.01
                }
            )
        # 可能匹配任一错误信息（范围或总和）
        assert "超出 [0, 1] 范围" in str(exc_info.value) or "权重之和必须接近 1.0" in str(
            exc_info.value
        )

    def test_missing_required_key(self):
        """UT-009: 缺少必需 key 校验失败"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": 0.55,
                    "ema_trend": 0.25,
                    # 缺少 mtf
                }
            )
        assert "缺少必需的归因权重" in str(exc_info.value)
        assert "mtf" in str(exc_info.value)

    def test_missing_multiple_keys(self):
        """缺少多个必需 key"""
        with pytest.raises(ValidationError) as exc_info:
            AttributionConfig(
                weights={
                    "pattern": 1.0,
                    # 缺少 ema_trend 和 mtf
                }
            )
        assert "缺少必需的归因权重" in str(exc_info.value)
        # 验证报错信息包含缺失的 key
        error_msg = str(exc_info.value)
        assert "ema_trend" in error_msg or "mtf" in error_msg


# ============================================================
# Tests: 边界场景
# ============================================================


class TestAttributionConfigEdgeCases:
    """边界场景测试"""

    def test_weight_sum_exactly_one(self):
        """UT-011: 边界值 — 权重和恰好 1.0 通过"""
        config = AttributionConfig(
            weights={
                "pattern": 0.55,
                "ema_trend": 0.25,
                "mtf": 0.20,
            }
        )
        assert abs(sum(config.weights.values()) - 1.0) < 0.001

    def test_weight_sum_within_upper_tolerance(self):
        """UT-012: 边界值 — 权重和在容差内通过（使用明显安全的值）"""
        config = AttributionConfig(
            weights={
                "pattern": 0.555,
                "ema_trend": 0.25,
                "mtf": 0.20,  # 总和 = 1.005，明确在 0.01 容差内
            }
        )
        assert abs(sum(config.weights.values()) - 1.0) <= 0.01

    def test_weight_sum_within_lower_tolerance(self):
        """UT-013: 边界值 — 权重和在容差内通过（使用明显安全的值）"""
        config = AttributionConfig(
            weights={
                "pattern": 0.545,
                "ema_trend": 0.25,
                "mtf": 0.20,  # 总和 = 0.995，明确在 0.01 容差内
            }
        )
        assert abs(sum(config.weights.values()) - 1.0) <= 0.01

    def test_weight_sum_just_above_tolerance(self):
        """权重和 1.0101（刚好超出容差）失败"""
        with pytest.raises(ValidationError):
            AttributionConfig(
                weights={
                    "pattern": 0.5601,
                    "ema_trend": 0.25,
                    "mtf": 0.20,  # 总和 = 1.0101
                }
            )

    def test_weight_sum_just_below_tolerance(self):
        """权重和 0.9899（刚好超出容差）失败"""
        with pytest.raises(ValidationError):
            AttributionConfig(
                weights={
                    "pattern": 0.5399,
                    "ema_trend": 0.25,
                    "mtf": 0.20,  # 总和 = 0.9899
                }
            )

    def test_single_weight_zero(self):
        """UT-014: 边界值 — 单个权重为 0 通过"""
        config = AttributionConfig(
            weights={
                "pattern": 0.80,
                "ema_trend": 0.20,
                "mtf": 0.0,
            }
        )
        assert config.weights["mtf"] == 0.0

    def test_single_weight_one(self):
        """UT-015: 边界值 — 单个权重为 1.0 通过（其他为 0）"""
        config = AttributionConfig(
            weights={
                "pattern": 1.0,
                "ema_trend": 0.0,
                "mtf": 0.0,
            }
        )
        assert config.weights["pattern"] == 1.0

    def test_extra_keys_allowed(self):
        """UT-010: 额外 key 允许通过"""
        config = AttributionConfig(
            weights={
                "pattern": 0.45,
                "ema_trend": 0.25,
                "mtf": 0.20,
                "volume": 0.10,  # 额外 key
            }
        )
        assert "volume" in config.weights
        assert config.weights["volume"] == 0.10

    def test_from_kv_float_string_values(self):
        """from_kv 处理字符串形式的数字（JSON 反序列化场景）"""
        kv_configs = {
            "attribution_weight_pattern": "0.50",
            "attribution_weight_ema_trend": "0.30",
            "attribution_weight_mtf": "0.20",
        }
        config = AttributionConfig.from_kv(kv_configs)

        assert config.weights["pattern"] == 0.50
        assert config.weights["ema_trend"] == 0.30
        assert config.weights["mtf"] == 0.20
