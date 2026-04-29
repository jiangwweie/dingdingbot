# 币安合约 K 线数据下载器

## 概述

从 [Binance Vision](https://data.binance.vision/) 下载 U 本位合约 (USDS-M) K 线数据。

数据源格式：
```
https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{TIMEFRAME}/{SYMBOL}-{TIMEFRAME}-{YEAR}-{MONTH}.zip
```

## 安装依赖

```bash
pip install aiohttp
```

## 使用示例

### 1. 下载单个文件

```bash
python3 scripts/etl/binance_downloader.py download \
    --symbol BTCUSDT \
    --timeframe 1h \
    --year 2026 \
    --month 2
```

### 2. 批量下载（推荐）

下载 BTC 2023-01 到 2026-02 的 15min, 1h, 4h, 1d 数据：

```bash
python3 scripts/etl/binance_downloader.py batch \
    --symbol BTCUSDT \
    --timeframes 15m,1h,4h,1d \
    --start 2023-01 \
    --end 2026-02
```

### 3. 下载多个交易对

```bash
python3 scripts/etl/binance_downloader.py multi \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT \
    --timeframes 15m,1h,4h,1d \
    --start 2023-01 \
    --end 2026-02
```

## 参数说明

### download 命令

| 参数 | 必填 | 说明 |
|------|------|------|
| `--symbol` | ✅ | 交易对 (例如：BTCUSDT, ETHUSDT) |
| `--timeframe` | ✅ | 时间周期 (1m, 5m, 15m, 1h, 4h, 1d, 1w) |
| `--year` | ✅ | 年份 |
| `--month` | ✅ | 月份 |
| `--output` | ❌ | 输出目录 (默认：~/Documents/data/binance) |

### batch 命令

| 参数 | 必填 | 说明 |
|------|------|------|
| `--symbol` | ✅ | 交易对 |
| `--timeframes` | ✅ | 时间周期列表，逗号分隔 |
| `--start` | ✅ | 开始日期 (YYYY-MM) |
| `--end` | ✅ | 结束日期 (YYYY-MM) |
| `--output` | ❌ | 输出目录 |

### multi 命令

| 参数 | 必填 | 说明 |
|------|------|------|
| `--symbols` | ✅ | 交易对列表，逗号分隔 |
| `--timeframes` | ✅ | 时间周期列表，逗号分隔 |
| `--start` | ✅ | 开始日期 (YYYY-MM) |
| `--end` | ✅ | 结束日期 (YYYY-MM) |
| `--output` | ❌ | 输出目录 |

## 输出目录结构

```
~/Documents/data/binance/
├── BTCUSDT/
│   ├── 15m/
│   │   ├── BTCUSDT-15m-2023-01.zip
│   │   ├── BTCUSDT-15m-2023-02.zip
│   │   └── ...
│   ├── 1h/
│   │   ├── BTCUSDT-1h-2023-01.zip
│   │   └── ...
│   ├── 4h/
│   └── 1d/
├── ETHUSDT/
│   └── ...
└── SOLUSDT/
    └── ...
```

## 特性

- ✅ 自动创建目录结构
- ✅ 支持并发下载 (默认 5 个并发)
- ✅ 自动重试 (失败重试 3 次)
- ✅ 断点续传 (已存在文件自动跳过)
- ✅ 进度显示

## 与 ETL 工具集成

下载后可使用 `etl_converter.py` 将 ZIP 数据导入 SQLite:

```bash
# 解压并转换单个文件
python3 scripts/etl/etl_converter.py unzip-convert \
    ~/Documents/data/binance/BTCUSDT/1h/BTCUSDT-1h-2026-01.zip \
    --symbol "BTC/USDT:USDT" \
    --timeframe "1h"

# 批量转换整个目录
python3 scripts/etl/etl_converter.py batch \
    ~/Documents/data/binance/BTCUSDT/1h/ \
    --symbol "BTC/USDT:USDT"
```

## 可用时间周期

| 周期 | 说明 |
|------|------|
| 1m, 3m, 5m | 分钟线 |
| 15m, 30m | 15 分钟/30 分钟 |
| 1h, 2h, 4h, 6h, 12h | 小时线 |
| 1d | 日线 |
| 1w | 周线 |

## 注意事项

1. **网络要求**: 需要稳定的网络连接，建议使用代理
2. **数据范围**: 币安提供 2020-09 至今的数据
3. **磁盘空间**: 完整历史数据约需 10-50GB (取决于交易对数量)
