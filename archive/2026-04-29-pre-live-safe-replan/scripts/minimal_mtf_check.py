#!/usr/bin/env python3
"""最小验证：对比 live 和 backtest 模式下的 MTF 配置"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.application.config_manager import load_all_configs_async


async def main():
    print("=" * 60)
    print("MTF 配置对比验证")
    print("=" * 60)

    # 实例化 ConfigManager
    config_manager = await load_all_configs_async()

    # 1. 读取 live 模式配置
    print("\n【1. Live 模式配置】")
    try:
        live_config = await config_manager.get_user_config()
        live_mtf_period = live_config.mtf_ema_period
        live_mtf_mapping = live_config.mtf_mapping

        print(f"  mtf_ema_period: {live_mtf_period}")
        print(f"  mtf_mapping: {live_mtf_mapping}")
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 读取 _system_config_cache（backtest 会使用这个）
    print("\n【2. Backtest 模式配置 (_system_config_cache)】")
    try:
        # 直接访问 _system_config_cache
        backtest_mtf_period = config_manager._system_config_cache.get("mtf_ema_period", 60)
        backtest_mtf_mapping = config_manager._system_config_cache.get(
            "mtf_mapping",
            {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"},
        )

        print(f"  mtf_ema_period: {backtest_mtf_period}")
        print(f"  mtf_mapping: {backtest_mtf_mapping}")
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. 对比结果
    print("\n【3. 对比结果】")
    print("-" * 60)

    period_match = live_mtf_period == backtest_mtf_period
    mapping_match = live_mtf_mapping == backtest_mtf_mapping

    print(f"  Live mtf_ema_period:     {live_mtf_period}")
    print(f"  Backtest mtf_ema_period: {backtest_mtf_period}")
    print(f"  {'✅ 一致' if period_match else '❌ 不一致'}")
    print()

    print(f"  Live mtf_mapping:     {live_mtf_mapping}")
    print(f"  Backtest mtf_mapping: {backtest_mtf_mapping}")
    print(f"  {'✅ 一致' if mapping_match else '❌ 不一致'}")
    print()

    # 4. 最终结论
    print("=" * 60)
    if period_match and mapping_match:
        print("✅ 结论：v3_pms 回测配置已与 live 模式完全一致")
    else:
        print("❌ 结论：配置不一致，需要检查 runtime_overrides 链路")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
