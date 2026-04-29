"""
配置迁移脚本 - 从 user.yaml 迁移策略参数到数据库

用途：
    python scripts/migrate_config_to_db.py

功能：
1. 读取 user.yaml 和 core.yaml
2. 提取策略参数 (Pinbar/EMA/MTF/ATR 等)
3. 迁移到 config_entries_v2 表
4. 生成迁移报告
"""
import asyncio
import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from src.infrastructure.config_entry_repository import ConfigEntryRepository
from src.domain.models import StrategyParams


async def migrate_config_to_db(config_dir: str = "config") -> dict:
    """
    迁移配置从 YAML 到数据库

    Args:
        config_dir: 配置文件目录

    Returns:
        迁移报告字典
    """
    config_path = Path(config_dir)
    user_yaml_path = config_path / "user.yaml"
    core_yaml_path = config_path / "core.yaml"

    repo = ConfigEntryRepository()
    await repo.initialize()

    report = {
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "entries_migrated": 0,
        "entries": [],
        "errors": [],
    }

    version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M%S')}"

    try:
        # 读取 core.yaml
        if core_yaml_path.exists():
            with open(core_yaml_path, 'r', encoding='utf-8') as f:
                core_config = yaml.safe_load(f)

            # 迁移 Pinbar 参数
            if 'pinbar_defaults' in core_config:
                pinbar = core_config['pinbar_defaults']
                for key, value in pinbar.items():
                    config_key = f"strategy.pinbar.{key}"
                    await repo.upsert_entry(config_key, Decimal(str(value)), version)
                    report["entries"].append({
                        "key": config_key,
                        "value": str(value),
                        "type": "decimal",
                        "source": "core.yaml"
                    })
                    report["entries_migrated"] += 1

            # 迁移 EMA 参数
            if 'ema' in core_config:
                ema = core_config['ema']
                for key, value in ema.items():
                    config_key = f"strategy.ema.{key}"
                    await repo.upsert_entry(config_key, int(value), version)
                    report["entries"].append({
                        "key": config_key,
                        "value": str(value),
                        "type": "number",
                        "source": "core.yaml"
                    })
                    report["entries_migrated"] += 1

            # 迁移 MTF EMA 周期
            if 'mtf_ema_period' in core_config:
                config_key = "strategy.mtf.ema_period"
                await repo.upsert_entry(config_key, int(core_config['mtf_ema_period']), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(core_config['mtf_ema_period']),
                    "type": "number",
                    "source": "core.yaml"
                })
                report["entries_migrated"] += 1

            # 迁移 MTF 映射
            if 'mtf_mapping' in core_config:
                config_key = "strategy.mtf.mapping"
                await repo.upsert_entry(config_key, core_config['mtf_mapping'], version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(core_config['mtf_mapping']),
                    "type": "json",
                    "source": "core.yaml"
                })
                report["entries_migrated"] += 1

            # 迁移 ATR 过滤器配置
            if 'atr_filter' in core_config:
                atr = core_config['atr_filter']
                config_key = "strategy.atr.enabled"
                await repo.upsert_entry(config_key, bool(atr.get('enabled', True)), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(atr.get('enabled', True)),
                    "type": "boolean",
                    "source": "core.yaml"
                })
                report["entries_migrated"] += 1

                config_key = "strategy.atr.period"
                await repo.upsert_entry(config_key, int(atr.get('period', 14)), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(atr.get('period', 14)),
                    "type": "number",
                    "source": "core.yaml"
                })
                report["entries_migrated"] += 1

                config_key = "strategy.atr.min_atr_ratio"
                await repo.upsert_entry(config_key, Decimal(str(atr.get('min_atr_ratio', 0.5))), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(atr.get('min_atr_ratio', 0.5)),
                    "type": "decimal",
                    "source": "core.yaml"
                })
                report["entries_migrated"] += 1

        # 读取 user.yaml
        if user_yaml_path.exists():
            with open(user_yaml_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)

            # 迁移风控参数
            if 'risk' in user_config:
                risk = user_config['risk']
                config_key = "risk.max_loss_percent"
                await repo.upsert_entry(config_key, Decimal(str(risk.get('max_loss_percent', '0.01'))), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(risk.get('max_loss_percent', '0.01')),
                    "type": "decimal",
                    "source": "user.yaml"
                })
                report["entries_migrated"] += 1

                config_key = "risk.max_leverage"
                await repo.upsert_entry(config_key, int(risk.get('max_leverage', 10)), version)
                report["entries"].append({
                    "key": config_key,
                    "value": str(risk.get('max_leverage', 10)),
                    "type": "number",
                    "source": "user.yaml"
                })
                report["entries_migrated"] += 1

        print(f"✅ 迁移完成！共迁移 {report['entries_migrated']} 条配置")
        print("\n迁移详情:")
        for entry in report["entries"]:
            print(f"  - {entry['key']}: {entry['value']} ({entry['type']}) [来自 {entry['source']}]")

    except Exception as e:
        report["errors"].append(str(e))
        print(f"❌ 迁移失败：{e}")
        import traceback
        traceback.print_exc()

    finally:
        await repo.close()

    return report


async def export_db_to_yaml(output_path: str = "config/migrated_config.yaml") -> bool:
    """
    从数据库导出配置到 YAML 文件

    Args:
        output_path: 输出 YAML 文件路径

    Returns:
        是否成功
    """
    repo = ConfigEntryRepository()
    await repo.initialize()

    try:
        # 获取所有配置
        all_entries = await repo.get_all_entries()

        # 构建嵌套结构
        config = {
            "strategy": {},
            "risk": {},
        }

        for key, value in all_entries.items():
            parts = key.split('.')
            if len(parts) >= 2:
                category = parts[0]
                subcategory = parts[1]
                param_key = '.'.join(parts[2:]) if len(parts) > 2 else None

                if category not in config:
                    config[category] = {}

                if param_key:
                    if subcategory not in config[category]:
                        config[category][subcategory] = {}
                    config[category][subcategory][param_key] = value
                else:
                    config[category][subcategory] = value

        # 写入 YAML 文件
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 转换 Decimal 为 float 以便 YAML 序列化
        def convert_decimals(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(v) for v in obj]
            return obj

        config_clean = convert_decimals(config)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(
                config_clean,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        print(f"✅ 配置已导出到：{output_path}")
        return True

    except Exception as e:
        print(f"❌ 导出失败：{e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await repo.close()


async def main():
    """主函数"""
    print("=" * 60)
    print("配置迁移工具 - YAML → Database")
    print("=" * 60)

    # 从 YAML 迁移到数据库
    print("\n【步骤 1】从 YAML 迁移配置到数据库...")
    report = await migrate_config_to_db()

    # 从数据库导出到 YAML（用于验证）
    print("\n【步骤 2】从数据库导出配置到 YAML（验证用）...")
    await export_db_to_yaml("config/migrated_config_backup.yaml")

    print("\n" + "=" * 60)
    print("迁移完成!")
    print(f"  - 迁移条目数：{report['entries_migrated']}")
    print(f"  - 错误数：{len(report['errors'])}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
