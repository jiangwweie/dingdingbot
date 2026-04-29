# MTF 过滤 `higher_tf_data_unavailable` 问题修复

**日期**: 2026-03-29
**问题**: ETH/USDT 1h 回测时 MTF 过滤器返回 `higher_tf_data_unavailable`
**状态**: 已修复

---

## 问题现象

在 ETH/USDT 1h 回测中，MTF 过滤器返回 `higher_tf_data_unavailable`，导致信号被错误过滤。

### 数据库记录

```sql
-- signal_attempts 表中的错误记录
id=4080, symbol='ETH/USDT:USDT', timeframe='1h',
kline_timestamp=1774760400000 (2026-03-29 13:00:00 本地时间 / 05:00:00 UTC),
strategy_name='01pinbar-ema60',
filter_reason='higher_tf_data_unavailable'
```

### 预期行为

- 1h K 线时间戳 `1774760400000` (05:00 UTC) 应该匹配 4h K 线时间戳 `1774756800000` (04:00 UTC)
- 4h MTF 趋势应该是 **看跌**（假设 04:00 收盘的 4h K 线 close < open）

---

## 根因分析

### 问题原因

回测时 1h 数据和 4h 数据的加载逻辑不一致：

| 数据层级 | limit 计算逻辑 |
|---------|---------------|
| **1h 数据** | 当指定时间范围时：`limit = max(expected_bars * 1.2, request.limit, 1000)` |
| **4h 数据** | 仅使用 `request.limit`（默认 100） |

**关键问题**：
1. 前端发送回测请求时指定了 `start_time` 和 `end_time`（如 04:00-05:00）
2. 1h 数据加载会计算时间范围，获取足够的 K 线（至少 1000 根），然后按时间范围过滤
3. **4h 数据加载仅使用 `request.limit=100`，没有考虑时间范围**
4. 交易所返回 K 线是**从"当前最新时间"往前推**，而不是从指定时间开始
5. 如果 100 根 4h K 线的时间范围无法覆盖 1h 数据的时间戳，MTF 过滤就会失败

### 代码流程

```
用户请求：start_time=04:00, end_time=05:00, timeframe='1h'
     ↓
_fetch_klines(request)
     ↓
1h 数据：limit = max(1*1.2, 100, 1000) = 1000
        过滤后得到 2 根 (04:00, 05:00)
     ↓
_run_strategy_loop(...)
     ↓
4h 数据：limit = request.limit = 100  ← 问题所在！
     ↓
_get_closest_higher_tf_trends(1774760400000, higher_tf_data)
     ↓
如果 higher_tf_data 中没有 <= 1774760400000 的时间戳
     ↓
返回 {}  ← 空字典
     ↓
MtfFilter.check_with_timeframe()
     ↓
higher_tf_trend = None
     ↓
返回 FilterResult(passed=False, reason="higher_tf_data_unavailable")
```

### 时间戳对齐验证

```python
# 1h 时间戳：1774760400000 -> 2026-03-29T05:00:00+00:00
# 4h 时间戳应该是：1774756800000 -> 2026-03-29T04:00:00+00:00
# 时间差：60 分钟（正确的 MTF 映射：1h -> 4h）

four_hours_ms = 4 * 60 * 60 * 1000  # 14400000ms
closest_4h_ts = (1774760400000 // four_hours_ms) * four_hours_ms
# = 1774756800000 (04:00 UTC) ✓ 时间戳对齐是正确的
```

**结论**：时间戳对齐逻辑正确，问题在于 4h 数据没有被正确加载。

---

## 修复方案

### 修复位置

文件：`src/application/backtester.py`
方法：`_run_strategy_loop()` 和 `_run_dynamic_strategy_loop()`

### 修复逻辑

```python
if higher_tf:
    if klines:
        min_kline_ts = min(k.timestamp for k in klines)
        max_kline_ts = max(k.timestamp for k in klines)

        higher_tf_minutes = self._parse_timeframe(higher_tf)
        duration_ms = max_kline_ts - min_kline_ts

        # 1. 计算覆盖 kline 范围需要的 4h K 线数量
        expected_higher_tf_bars = max(
            int(duration_ms / (higher_tf_minutes * 60 * 1000)) + 5,
            100
        )

        # 2. 如果用户指定了时间范围，用时间范围重新计算
        if request.start_time and request.end_time:
            full_duration_ms = end_ts - start_ts
            full_expected_bars = int(full_duration_ms / (higher_tf_minutes * 60 * 1000)) + 5
            expected_higher_tf_bars = max(expected_higher_tf_bars, full_expected_bars, 1000)

        # 3. 【关键修复】计算从"当前时间"回溯到 min_kline_ts 需要的 4h K 线数量
        current_ts = int(time.time() * 1000)
        time_from_now_ms = current_ts - min_kline_ts
        bars_from_now = int(time_from_now_ms / (higher_tf_minutes * 60 * 1000)) + 10

        # 4. 使用两者中较大的值，确保覆盖
        limit = max(expected_higher_tf_bars, bars_from_now, 1000)
```

### 修复前后对比

| 场景 | 修复前 limit | 修复后 limit |
|------|-------------|-------------|
| 回测当前时间范围（04:00-05:00） | 100 | 1000 |
| 回测 7 天前的时间范围 | 100 | ~252 (7 天 * 6 根 4h/天 + buffer) |
| 回测 30 天前的时间范围 | 100 | ~1080 (30 天 * 6 根 4h/天 + buffer) |

---

## 验证方法

### 1. 运行回测测试

```bash
# 使用前端或 API 发送回测请求
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH/USDT:USDT",
    "timeframe": "1h",
    "start_time": 1774756800000,
    "end_time": 1774760400000,
    "strategies": [...]
  }'
```

### 2. 检查日志输出

修复后应该看到：
```
INFO: Fetching 1000 4h candles for MTF (klines range: 1774756800000-1774760400000, need 10 bars from now)
INFO: Loaded 1000 4h candles for MTF validation
```

### 3. 检查数据库记录

```sql
-- 检查是否还有 higher_tf_data_unavailable 错误
SELECT COUNT(*) FROM signal_attempts
WHERE filter_reason = 'higher_tf_data_unavailable';

-- 检查 MTF 过滤通过的记录
SELECT * FROM signal_attempts
WHERE trace_tree LIKE '%mtf_confirmed%'
LIMIT 5;
```

---

## 经验总结

### 关键发现

1. **交易所 API 行为**：`fetch_ohlcv(symbol, timeframe, limit=N)` 返回**从当前最新时间往前推 N 根**K 线，而不是从指定时间开始。

2. **时间范围参数的重要性**：当回测请求指定了 `start_time` 和 `end_time` 时，必须确保所有相关数据（包括 MTF 数据）都能覆盖这个时间范围。

3. **保守的 limit 设置**：对于可能依赖历史数据的场景（如 MTF、多周期分析），应该使用保守的 limit 值（如至少 1000 根）。

### 未来改进建议

1. **添加 MTF 数据覆盖检查**：在运行策略前，验证 4h 数据是否覆盖了 1h 数据的时间范围。

2. **添加诊断日志**：当 MTF 过滤返回 `higher_tf_data_unavailable` 时，记录详细的诊断信息（4h 数据的时间戳范围、1h 时间戳等）。

3. **单元测试**：添加测试用例验证 MTF 数据加载逻辑，特别是针对历史时间范围的回测场景。

---

## 相关文件

- `src/application/backtester.py` - 回测引擎
- `src/domain/strategy_engine.py` - MTF 过滤器实现
- `src/domain/filter_factory.py` - 工厂模式过滤器
