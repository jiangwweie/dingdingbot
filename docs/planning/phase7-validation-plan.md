# Phase 7 收尾验证任务计划

> **创建日期**: 2026-04-02  
> **执行人**: AI Builder  
> **预计工时**: 5 小时  
> **优先级**: P1

---

## 任务概述

Phase 7 回测数据本地化核心功能已完成，需要进行收尾验证确保数据完整性和 MTF 数据对齐正确性。

---

## 验证任务清单

### T5: 数据完整性验证 (2h)

**目标**: 检查 SQLite 中 K 线数据的质量和完整性

**子任务**:
| ID | 验证项 | 方法 | 预期结果 |
|----|--------|------|----------|
| T5-1 | 检查 K 线数据时间范围 | 查询 SQLite 中各周期的最小/最大时间戳 | 确认数据跨度 (2020-01 → 2026-02) |
| T5-2 | 验证数据字段完整性 | 抽样检查 OHLCV 字段非空且合理 | high ≥ low, close/open 在合理范围 |
| T5-3 | 确认回测引擎读取本地数据 | 运行回测并追踪数据源调用 | HistoricalDataRepository.get_klines 被调用 |

**SQL 查询示例**:
```sql
-- 检查各周期的数据范围
SELECT 
    symbol,
    timeframe,
    COUNT(*) as kline_count,
    MIN(timestamp) as min_ts,
    MAX(timestamp) as max_ts,
    datetime(MIN(timestamp)/1000, 'unixepoch') as min_date,
    datetime(MAX(timestamp)/1000, 'unixepoch') as max_date
FROM klines 
GROUP BY symbol, timeframe
ORDER BY timeframe, symbol;

-- 检查数据质量 (high < low 的异常记录)
SELECT COUNT(*) as bad_records 
FROM klines 
WHERE high < low OR open <= 0 OR close <= 0;
```

---

### T8: MTF 数据对齐验证 (2h)

**目标**: 验证多周期数据时间戳对齐逻辑正确性

**子任务**:
| ID | 验证项 | 方法 | 预期结果 |
|----|--------|------|----------|
| T8-1 | 验证 MTF 映射配置 | 检查 `DEFAULT_MTF_MAPPING` | 15m→1h, 1h→4h, 4h→1d, 1d→1w |
| T8-2 | 检查时间戳对齐逻辑 | 运行 `get_last_closed_kline_index` 测试 | 只返回已收盘的 K 线 |
| T8-3 | 测试策略引擎 MTF 过滤器 | 运行 MTF 端到端测试 | 无 `higher_tf_data_unavailable` 错误 |

**验证场景**:
```
场景 1: 15m K 线在 10:15
- 当前时间戳：10:15
- 1h K 线 10:00-11:00 尚未收盘
- 应使用 09:00-10:00 的 1h K 线 (索引 0)

场景 2: 15m K 线在 11:00
- 当前时间戳：11:00
- 1h K 线 10:00-11:00 刚刚收盘
- 应使用 10:00-11:00 的 1h K 线 (索引 1)
```

**测试用例**:
```python
# 运行现有测试验证
pytest tests/unit/test_timeframe_utils.py -v
pytest tests/unit/test_backtester_mtf.py -v
```

---

### T7: 性能基准测试 (1h)

**目标**: 验证本地数据源带来的性能提升

**基准对比**:
| 场景 | 交易所源 | 本地源 | 预期提升 |
|------|----------|--------|----------|
| 单次回测 (15m, 100 根) | ~2-5s (网络) | ~0.1s (本地) | 20-50x |
| 参数扫描 (10 次) | ~20-50s | ~1-5s | 10-20x |

**测试方法**:
```python
import time
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.infrastructure.exchange_gateway import ExchangeGateway

# 测试本地读取性能
repo = HistoricalDataRepository(db_path="data/v3_dev.db")
await repo.initialize()

start = time.time()
klines = await repo.get_klines(
    symbol="BTC/USDT:USDT",
    timeframe="15m",
    limit=1000,
)
local_time = time.time() - start
print(f"本地读取耗时：{local_time*1000:.2f}ms")
```

---

## 验证报告模板

### 数据完整性验证结果

| 验证项 | 状态 | 详情 |
|--------|------|------|
| T5-1: 时间范围 | ☐ 通过/☐ 失败 | ... |
| T5-2: 字段完整性 | ☐ 通过/☐ 失败 | ... |
| T5-3: 回测数据源 | ☐ 通过/☐ 失败 | ... |

### MTF 数据对齐验证结果

| 验证项 | 状态 | 详情 |
|--------|------|------|
| T8-1: MTF 映射 | ☐ 通过/☐ 失败 | ... |
| T8-2: 时间戳对齐 | ☐ 通过/☐ 失败 | ... |
| T8-3: MTF 过滤器 | ☐ 通过/☐ 失败 | ... |

### 性能基准测试结果

| 测试项 | 交易所源 (ms) | 本地源 (ms) | 提升倍数 |
|--------|---------------|-------------|----------|
| 获取 100 根 K 线 | - | - | - |
| 获取 1000 根 K 线 | - | - | - |

---

## 下一步计划

验证完成后:
1. 更新 `task_plan.md` 标记 Phase 7 完成
2. 更新 `progress.md` 记录验证日志
3. Git 提交验证报告

---

*文档创建：2026-04-02*
