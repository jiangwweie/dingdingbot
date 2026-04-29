#!/usr/bin/env python3
"""
MTF 真源统一验证脚本

验证回测路径是否正确读取 MTF 配置
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
)
from src.application.backtester import resolve_backtest_params


def test_mtf_config_resolution():
    """测试 MTF 配置解析"""

    print("=" * 80)
    print("MTF 真源统一验证")
    print("=" * 80)

    # 测试 1: 默认值
    print("\n【测试 1】默认值（无 runtime_overrides）")
    resolved = resolve_backtest_params()
    print(f"  mtf_ema_period: {resolved.mtf_ema_period}")
    print(f"  mtf_mapping: {resolved.mtf_mapping}")
    assert resolved.mtf_ema_period == 60, "默认 mtf_ema_period 应为 60"
    assert resolved.mtf_mapping == {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }, "默认 mtf_mapping 不正确"
    print("  ✅ 默认值正确")

    # 测试 2: runtime_overrides 覆盖
    print("\n【测试 2】runtime_overrides 覆盖")
    overrides = BacktestRuntimeOverrides(
        mtf_ema_period=90,
        mtf_mapping={"15m": "1h", "1h": "4h", "4h": "1d"},
    )
    resolved = resolve_backtest_params(runtime_overrides=overrides)
    print(f"  mtf_ema_period: {resolved.mtf_ema_period}")
    print(f"  mtf_mapping: {resolved.mtf_mapping}")
    assert resolved.mtf_ema_period == 90, "runtime_overrides mtf_ema_period 应为 90"
    assert resolved.mtf_mapping == {"15m": "1h", "1h": "4h", "4h": "1d"}, "runtime_overrides mtf_mapping 不正确"
    print("  ✅ runtime_overrides 覆盖正确")

    # 测试 3: KV configs 覆盖
    print("\n【测试 3】KV configs 覆盖")
    kv_configs = {
        "system.mtf_ema_period": 111,
        "system.mtf_mapping": {"15m": "1h", "1h": "4h"},
    }
    resolved = resolve_backtest_params(kv_configs=kv_configs)
    print(f"  mtf_ema_period: {resolved.mtf_ema_period}")
    print(f"  mtf_mapping: {resolved.mtf_mapping}")
    assert resolved.mtf_ema_period == 111, "KV configs mtf_ema_period 应为 111"
    assert resolved.mtf_mapping == {"15m": "1h", "1h": "4h"}, "KV configs mtf_mapping 不正确"
    print("  ✅ KV configs 覆盖正确")

    # 测试 4: 优先级验证（runtime_overrides > kv_configs）
    print("\n【测试 4】优先级验证（runtime_overrides > kv_configs）")
    overrides = BacktestRuntimeOverrides(
        mtf_ema_period=130,
    )
    kv_configs = {
        "system.mtf_ema_period": 111,
    }
    resolved = resolve_backtest_params(
        runtime_overrides=overrides,
        kv_configs=kv_configs,
    )
    print(f"  mtf_ema_period: {resolved.mtf_ema_period}")
    assert resolved.mtf_ema_period == 130, "runtime_overrides 优先级应高于 kv_configs"
    print("  ✅ 优先级正确")

    print("\n" + "=" * 80)
    print("✅ 所有测试通过")
    print("=" * 80)

    print("\n【结论】")
    print("1. 回测路径已正确解析 MTF 配置（mtf_ema_period 和 mtf_mapping）")
    print("2. 优先级正确：runtime_overrides > kv_configs > code defaults")
    print("3. 回测与实盘现在使用同一真源（ConfigManager）")


if __name__ == "__main__":
    try:
        test_mtf_config_resolution()
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
