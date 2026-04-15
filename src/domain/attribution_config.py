"""
Attribution Config - 策略归因权重配置校验模型。

从 KV 配置加载归因权重，通过 Pydantic 校验层拦截脏数据。
"""

from typing import Any, Dict

from pydantic import BaseModel, field_validator


# 必需的归因权重 key
_REQUIRED_WEIGHT_KEYS = {"pattern", "ema_trend", "mtf"}

# 权重和允许的偏差
_WEIGHT_SUM_TOLERANCE = 0.01

# 权重有效范围
_WEIGHT_MIN = 0.0
_WEIGHT_MAX = 1.0


class AttributionConfig(BaseModel):
    """
    归因配置校验模型 — 从 KV 配置加载并校验。

    权重和必须 ≈ 1.0（偏差 <= 0.01），每个权重在 [0, 1] 范围内，
    且必须包含 pattern、ema_trend、mtf 三个必需 key。

    Attributes:
        weights: 归因权重字典，key 为组件名称，value 为权重值。
    """

    weights: Dict[str, float]

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """校验权重完整性、范围和总和。"""
        # 1. 必须包含必需的 key
        missing = _REQUIRED_WEIGHT_KEYS - set(v.keys())
        if missing:
            raise ValueError(f"缺少必需的归因权重: {missing}")

        # 2. 权重和必须 ≈ 1.0
        total = sum(v.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"权重之和必须接近 1.0，当前: {total:.4f}")

        # 3. 每个权重必须在 [0, 1] 范围内
        for key, val in v.items():
            if not _WEIGHT_MIN <= val <= _WEIGHT_MAX:
                raise ValueError(f"权重 {key}={val} 超出 [0, 1] 范围")

        return v

    @classmethod
    def from_kv(cls, kv_configs: Dict[str, Any]) -> "AttributionConfig":
        """
        从 KV 配置加载并校验。

        Args:
            kv_configs: KV 配置字典，来自 ConfigManager.get_backtest_configs()。

        Returns:
            校验通过的 AttributionConfig 实例。
        """
        weights = {
            "pattern": float(kv_configs.get("attribution_weight_pattern", 0.55)),
            "ema_trend": float(kv_configs.get("attribution_weight_ema_trend", 0.25)),
            "mtf": float(kv_configs.get("attribution_weight_mtf", 0.20)),
        }
        return cls(weights=weights)

    @classmethod
    def default(cls) -> "AttributionConfig":
        """返回默认配置。"""
        return cls(
            weights={
                "pattern": 0.55,
                "ema_trend": 0.25,
                "mtf": 0.20,
            }
        )
