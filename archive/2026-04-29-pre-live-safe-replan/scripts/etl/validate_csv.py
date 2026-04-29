#!/usr/bin/env python3
"""
Binance Vision CSV 数据验证工具

验证 CSV 文件结构、数据质量和时间戳连续性。
"""

import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd


# Binance Vision CSV 标准列名
CSV_COLUMNS = [
    'open_time', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
]

# 时间周期映射 (毫秒)
TIMEFRAME_MS = {
    '1m': 60 * 1000,
    '3m': 3 * 60 * 1000,
    '5m': 5 * 60 * 1000,
    '15m': 15 * 60 * 1000,
    '30m': 30 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '2h': 2 * 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,
    '6h': 6 * 60 * 60 * 1000,
    '12h': 12 * 60 * 60 * 1000,
    '1d': 24 * 60 * 60 * 1000,
    '1w': 7 * 24 * 60 * 60 * 1000,
}


def parse_filename(filename: str) -> dict:
    """
    解析币安文件名

    格式：SYMBOL-TIMEFRAME-YEAR-MONTH.csv
    示例：BTCUSDT-15m-2024-01.csv

    返回:
        {
            'symbol': 'BTCUSDT',
            'timeframe': '15m',
            'year': 2024,
            'month': 1,
        }
    """
    base = filename.replace('.csv', '')
    parts = base.split('-')

    if len(parts) < 4:
        return None

    # 处理可能包含连字符的交易对名称 (如 BTC-USDT)
    timeframe_idx = 1
    for i, part in enumerate(parts[1:], 1):
        if part.endswith('m') or part.endswith('h') or part.endswith('d') or part.endswith('w'):
            timeframe_idx = i
            break

    symbol = '-'.join(parts[:timeframe_idx])
    timeframe = parts[timeframe_idx]
    year = int(parts[timeframe_idx + 1])
    month = int(parts[timeframe_idx + 2]) if len(parts) > timeframe_idx + 2 else None

    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'year': year,
        'month': month,
    }


def validate_csv(file_path: str, verbose: bool = True) -> dict:
    """
    验证单个 CSV 文件

    返回:
        {
            'valid': bool,
            'errors': List[str],
            'warnings': List[str],
            'stats': dict,
            'info': dict,
        }
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'stats': {},
        'info': {},
    }

    file_path = Path(file_path)
    if not file_path.exists():
        result['valid'] = False
        result['errors'].append(f"文件不存在：{file_path}")
        return result

    # 解析文件名
    info = parse_filename(file_path.name)
    result['info'] = info
    if info is None:
        result['warnings'].append(f"无法解析文件名：{file_path.name}")

    try:
        # 加载 CSV (检测是否有表头)
        # 先读第一行判断是否有表头
        with open(file_path, 'r') as f:
            first_line = f.readline().strip()

        has_header = 'open_time' in first_line or 'open' in first_line

        if has_header:
            # 有表头，使用表头名称
            df = pd.read_csv(file_path)
            # 标准化列名
            column_mapping = {
                'quote_asset_volume': 'quote_volume',
                'number_of_trades': 'count',
                'taker_buy_base_volume': 'taker_buy_volume',
                'taker_buy_quote_volume': 'taker_buy_quote_volume',
            }
            df = df.rename(columns=column_mapping)
        else:
            # 无表头，使用标准列名
            df = pd.read_csv(file_path, names=CSV_COLUMNS)

        if verbose:
            print(f"\n{'='*60}")
            print(f"文件：{file_path.name}")
            print(f"{'='*60}")

        # 基础统计
        result['stats'] = {
            'total_rows': len(df),
            'columns': list(df.columns),
        }

        if verbose:
            print(f"总行数：{len(df):,}")
            print(f"列：{list(df.columns)}")

        # 检查空值
        null_counts = df.isnull().sum()
        if null_counts.any():
            for col, count in null_counts.items():
                if count > 0:
                    result['warnings'].append(f"列 '{col}' 有 {count} 个空值")
                    if verbose:
                        print(f"  ⚠️  列 '{col}' 有 {count} 个空值")

        # 数据精度检查 - 确保 OHLCV 是有效数字
        for col in ['open', 'high', 'low', 'close', 'volume']:
            try:
                # 尝试转换为 Decimal
                df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else None)
            except Exception as e:
                result['errors'].append(f"列 '{col}' 包含无效数值：{str(e)}")
                result['valid'] = False

        # 时间戳连续性检查
        expected_interval = TIMEFRAME_MS.get(info['timeframe'] if info else '15m', 15 * 60 * 1000)

        # 计算时间间隔
        time_diffs = df['open_time'].diff()

        # 找出不连续的位置
        gaps = time_diffs[time_diffs != expected_interval]

        if len(gaps) > 1:  # 第一个值是 NaN，跳过
            gap_count = len(gaps) - 1  # 减去第一个 NaN
            result['warnings'].append(f"发现 {gap_count} 处时间戳不连续")

            if verbose and gap_count > 0:
                print(f"\n  ⚠️  时间戳不连续位置 (共 {gap_count} 处):")
                for idx in gaps.index[1:10]:  # 只显示前 10 个
                    prev_idx = idx - 1
                    if prev_idx >= 0:
                        prev_time = df.loc[prev_idx, 'open_time']
                        curr_time = df.loc[idx, 'open_time']
                        gap_seconds = (curr_time - prev_time) / 1000
                        print(f"    - 行 {idx}: 间隔 {gap_seconds/3600:.1f} 小时 "
                              f"({datetime.fromtimestamp(prev_time/1000)} -> "
                              f"{datetime.fromtimestamp(curr_time/1000)})")

                if gap_count > 10:
                    print(f"    ... 还有 {gap_count - 10} 处")
        else:
            if verbose:
                print(f"  ✅ 时间戳连续 (间隔 {expected_interval/1000/60:.0f} 分钟)")

        # OHLCV 逻辑检查
        invalid_ohlc = df[
            (df['high'] < df['low']) |
            (df['open'] < df['low']) |
            (df['open'] > df['high']) |
            (df['close'] < df['low']) |
            (df['close'] > df['high'])
        ]

        if len(invalid_ohlc) > 0:
            result['errors'].append(f"发现 {len(invalid_ohlc)} 行 OHLCV 数据逻辑错误")
            result['valid'] = False
            if verbose:
                print(f"\n  ❌ 发现 {len(invalid_ohlc)} 行 OHLCV 数据逻辑错误 (high < low 等)")
        else:
            if verbose:
                print(f"  ✅ OHLCV 数据逻辑正确")

        # 价格和数量精度检查
        for col in ['open', 'high', 'low', 'close']:
            # 检查小数位数
            decimal_places = df[col].astype(str).apply(lambda x: len(x.split('.')[-1]) if '.' in x else 0)
            max_places = decimal_places.max()
            if max_places > 8:
                result['warnings'].append(f"列 '{col}' 最大小数位数为 {max_places}，可能超过 8 位精度")

        # 成交量检查
        if df['volume'].min() < 0:
            result['errors'].append("发现负成交量")
            result['valid'] = False

        # 基础统计
        result['stats'].update({
            'start_time': int(df['open_time'].min()),
            'end_time': int(df['open_time'].max()),
            'start_date': datetime.fromtimestamp(df['open_time'].min() / 1000).isoformat(),
            'end_date': datetime.fromtimestamp(df['open_time'].max() / 1000).isoformat(),
            'price_range': {
                'min': float(df['low'].min()),
                'max': float(df['high'].max()),
            },
            'total_volume': float(df['volume'].sum()),
        })

        if verbose:
            print(f"\n  数据范围:")
            print(f"    开始：{result['stats']['start_date']}")
            print(f"    结束：{result['stats']['end_date']}")
            print(f"    价格区间：{result['stats']['price_range']['min']:,.2f} - {result['stats']['price_range']['max']:,.2f}")
            print(f"    总成交量：{result['stats']['total_volume']:,.3f}")

    except Exception as e:
        result['valid'] = False
        result['errors'].append(f"读取 CSV 失败：{str(e)}")
        if verbose:
            print(f"\n  ❌ 读取 CSV 失败：{str(e)}")

    return result


def validate_directory(dir_path: str) -> dict:
    """
    验证目录下所有 CSV 文件

    返回:
        {
            'total_files': int,
            'valid_files': int,
            'invalid_files': int,
            'files': List[dict],
        }
    """
    dir_path = Path(dir_path)
    results = {
        'total_files': 0,
        'valid_files': 0,
        'invalid_files': 0,
        'files': [],
    }

    csv_files = sorted(dir_path.glob('*.csv'))
    results['total_files'] = len(csv_files)

    for csv_file in csv_files:
        result = validate_csv(str(csv_file), verbose=False)
        result['file_path'] = str(csv_file)
        results['files'].append(result)

        if result['valid']:
            results['valid_files'] += 1
        else:
            results['invalid_files'] += 1

    return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Binance Vision CSV 数据验证工具')
    parser.add_argument('path', help='CSV 文件或目录路径')
    parser.add_argument('-q', '--quiet', action='store_true', help='静默模式，只输出 JSON 结果')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式结果')

    args = parser.parse_args()

    path = Path(args.path)

    if path.is_file():
        result = validate_csv(str(path), verbose=not args.quiet)
    elif path.is_dir():
        result = validate_directory(str(path))
    else:
        print(f"错误：路径不存在 - {path}")
        sys.exit(1)

    if args.json or args.quiet:
        import json
        # Decimal 和 datetime 不能直接序列化，需要转换
        def serialize(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            return obj

        # 简单序列化
        print(json.dumps(result, indent=2, default=str))
    else:
        # 打印汇总
        if 'files' in result:
            print(f"\n{'='*60}")
            print(f"验证汇总")
            print(f"{'='*60}")
            print(f"总文件数：{result['total_files']}")
            print(f"有效文件：{result['valid_files']} ✅")
            print(f"无效文件：{result['invalid_files']} ❌")

            # 列出无效文件
            invalid = [f for f in result['files'] if not f['valid']]
            if invalid:
                print(f"\n无效文件列表:")
                for f in invalid:
                    print(f"  - {Path(f['file_path']).name}: {f['errors']}")

            # 列出有警告的文件
            warned = [f for f in result['files'] if f.get('warnings')]
            if warned:
                print(f"\n有警告的文件 (时间戳不连续等):")
                for f in warned[:10]:
                    print(f"  - {Path(f['file_path']).name}: {len(f.get('warnings', []))} 个警告")
                if len(warned) > 10:
                    print(f"  ... 还有 {len(warned) - 10} 个")
        else:
            # 单文件结果
            if result['valid']:
                print(f"\n✅ 验证通过")
            else:
                print(f"\n❌ 验证失败")
                for error in result['errors']:
                    print(f"  - {error}")

            if result['warnings']:
                print(f"\n⚠️  警告:")
                for warning in result['warnings'][:10]:
                    print(f"  - {warning}")
