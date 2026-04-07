# WebSocket K线时间戳BUG修复完整指南

## 问题诊断

### 问题现象
服务器检测到的信号时间点与前端渲染的K线价位对不上。

### 根本原因
WebSocket K线收盘检测逻辑错误，导致信号记录了**下一根K线的时间戳**，而不是实际触发信号的K线时间戳。

### 详细分析

#### 时间链路追踪（以信号ID 374为例）

**1. 实际触发信号的K线**
```
K线时间: 2026-04-07 01:45:00 - 02:00:00 UTC
K线时间戳: 1775526300000 毫秒 (开盘时间)
K线收盘价: 2098.28
信号入场价: 2098.27 ✅ 匹配
```

**2. 数据库错误记录**
```
kline_timestamp: 1775527200000 毫秒
转换时间: 2026-04-07 02:00:00 UTC (错误！)
时间偏差: 晚了15分钟 (下一根K线的开盘时间)
```

**3. WebSocket 执行流程**
```python
# 01:45-02:00期间
WebSocket推送: [1775526300000, 2108.91, 2109.38, 2096.29, 2098.28, ...]
                ↑ 01:45开盘的K线，实时更新
_candle_timestamps["ETH/USDT:USDT:15m"] = 1775526300000

# 02:00:00整点（新K线到达）
WebSocket推送: [..., [1775526300000, ...], [1775527200000, 2098.28, 2101.39, ...]]
                                                ↑ 新K线，02:00开盘

# 检测逻辑（原代码）
ohlcv = await watch_ohlcv()
kline = ohlcv[-1]  # ❌ 最新K线（timestamp=1775527200000）
if is_candle_closed(kline):  # 检测到时间戳变化
    callback(kline)  # ❌ 但kline是新K线数据

# 问题：应该使用ohlcv[-2]（刚收盘的K线），而不是ohlcv[-1]（新K线）
```

#### 币安交易所实际K线对比

```json
// 01:45-02:00 K线（正确的信号K线）
[1775526300000, "2108.91", "2109.38", "2096.29", "2098.28", "58023.284", 1775527199999]
 ↑ 开盘时间                ↑ 最高价      ↑ 最低价      ↑ 收盘价（匹配信号入场价）

// 02:00-02:15 K线（数据库错误记录的时间）
[1775527200000, "2098.28", "2101.39", "2091.93", "2098.14", ...]
 ↑ 错误的kline_timestamp
```

---

## 修复方案

### 修复内容

1. **后端代码修复** (`src/infrastructure/exchange_gateway.py`)
2. **数据库修复脚本** (`scripts/fix_websocket_timestamps.py`)
3. **单元测试** (`tests/unit/test_exchange_gateway.py`)

### 修复步骤

#### 步骤1：应用代码修复

代码已修复，主要改动：

**修改前**：
```python
ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)
candle = ohlcv[-1]  # ❌ 最新K线
kline = self._parse_ohlcv(candle, symbol, timeframe)
if self._is_candle_closed(kline, symbol, timeframe):
    await callback(kline)  # ❌ 错误的K线
```

**修改后**：
```python
ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)
if not ohlcv or len(ohlcv) < 2:
    continue
closed_kline = self._get_closed_candle(ohlcv, symbol, timeframe)
if closed_kline:
    await callback(closed_kline)  # ✅ 正确的收盘K线
```

**新增方法**：
```python
def _get_closed_candle(self, ohlcv, symbol, timeframe) -> Optional[KlineData]:
    """检测K线收盘并返回收盘K线数据（ohlcv[-2]）"""
    if len(ohlcv) < 2:
        return None

    key = f"{symbol}:{timeframe}"
    current_ts = ohlcv[-1][0]  # 新K线时间戳

    if key in self._candle_timestamps:
        if current_ts != self._candle_timestamps[key]:
            self._candle_timestamps[key] = current_ts
            # ✅ 返回倒数第二根（刚收盘的K线）
            closed_candle = ohlcv[-2]
            return self._parse_ohlcv(closed_candle, symbol, timeframe)
    else:
        self._candle_timestamps[key] = current_ts

    return None
```

#### 步骤2：修复数据库中的历史信号

```bash
# 1. 预览需要修复的信号
python scripts/fix_websocket_timestamps.py --dry-run

# 2. 执行修复
python scripts/fix_websocket_timestamps.py --execute

# 3. 验证修复结果
python scripts/fix_websocket_timestamps.py --verify
```

**修复逻辑**：
- 向前调整一个周期：`correct_ts = kline_timestamp - timeframe_ms`
- 15m周期：减去15分钟（900000毫秒）
- 1h周期：减去1小时（3600000毫秒）

#### 步骤3：重启服务

```bash
# 停止服务
docker-compose down

# 应用代码更新
git pull origin v2

# 重启服务
docker-compose up -d

# 检查日志
docker-compose logs -f monitor-dog-backend
```

#### 步骤4：验证修复

1. **查看新信号**：
   - 等待新信号触发
   - 检查 `kline_timestamp` 是否正确
   - 前端查看K线图，确认标记位置正确

2. **查看历史信号**：
   - 前端打开信号详情
   - 检查K线图上的信号标记是否对齐

3. **数据库验证**：
   ```bash
   ssh root@45.76.111.81
   python3 << 'EOF'
   import sqlite3
   conn = sqlite3.connect('/usr/local/monitorDog/data/signals-prod.db')
   cursor = conn.cursor()

   # 检查最近的信号
   signals = cursor.execute('''
       SELECT id, created_at, symbol, timeframe, kline_timestamp, entry_price
       FROM signals
       WHERE source='live'
       ORDER BY id DESC
       LIMIT 5
   ''').fetchall()

   for s in signals:
       print(f"ID: {s[0]}, TF: {s[3]}, TS: {s[4]}, Price: {s[5]}")

   conn.close()
   EOF
   ```

---

## 测试方案

### 单元测试

创建测试用例验证修复：

```python
# tests/unit/test_exchange_gateway.py

import pytest
from src.infrastructure.exchange_gateway import ExchangeGateway

@pytest.mark.asyncio
async def test_websocket_candle_closure_detection():
    """测试WebSocket K线收盘检测"""

    gateway = ExchangeGateway("binance", "test_key", "test_secret")

    # 模拟ohlcv数据（两次推送）
    ohlcv_1 = [
        [1775526300000, 2108.91, 2109.38, 2096.29, 2098.28, 58023.284],
        [1775527200000, 2098.28, 2101.39, 2091.93, 2098.14, 37571.558],  # 新K线
    ]

    # 第一次调用：应该返回None（初始化）
    result = gateway._get_closed_candle(ohlcv_1, "ETH/USDT:USDT", "15m")
    assert result is None

    # 模拟时间戳变化（下一次推送）
    ohlcv_2 = [
        [1775526300000, 2108.91, 2109.38, 2096.29, 2098.28, 58023.284],
        [1775527200000, 2098.28, 2101.39, 2091.93, 2098.14, 37571.558],
        [1775528100000, 2098.15, 2105.48, 2097.09, 2105.04, 49005.941],  # 新K线
    ]

    # 第二次调用：应该返回收盘K线（ohlcv_2[-2]）
    result = gateway._get_closed_candle(ohlcv_2, "ETH/USDT:USDT", "15m")
    assert result is not None
    assert result.timestamp == 1775527200000  # ✅ 第二根K线的时间戳
    assert float(result.close) == 2098.14
```

运行测试：
```bash
pytest tests/unit/test_exchange_gateway.py -v
```

---

## 影响范围

### 受影响的数据

- ✅ **WebSocket实时信号**（source='live'）：所有信号的时间戳都错误
- ❌ **回测信号**（source='backtest'）：不受影响（使用历史数据，时间戳正确）

### 需要修复的数据

```sql
-- 查询需要修复的信号数量
SELECT COUNT(*) FROM signals WHERE source = 'live' AND kline_timestamp IS NOT NULL;

-- 查询时间分布
SELECT
    timeframe,
    COUNT(*) as count,
    MIN(created_at) as earliest,
    MAX(created_at) as latest
FROM signals
WHERE source = 'live'
GROUP BY timeframe;
```

---

## 预防措施

### 1. 添加时间戳验证

在信号保存前验证时间戳合理性：

```python
# src/application/signal_pipeline.py

def validate_kline_timestamp(kline: KlineData) -> bool:
    """验证K线时间戳是否合理"""
    import time

    current_time = int(time.time() * 1000)  # 当前时间（毫秒）
    timeframe_map = {
        "15m": 15 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        ...
    }

    # K线时间戳不应该晚于当前时间
    if kline.timestamp > current_time:
        logger.error(f"K线时间戳在未来: {kline.timestamp} > {current_time}")
        return False

    # K线时间戳应该是周期对齐的
    timeframe_ms = timeframe_map.get(kline.timeframe)
    if timeframe_ms and kline.timestamp % timeframe_ms != 0:
        logger.warning(f"K线时间戳未对齐周期: {kline.timestamp} % {timeframe_ms} != 0")

    return True
```

### 2. 添加监控告警

```python
# 在信号保存时检查时间戳
if kline.timestamp != last_closed_timestamp:
    logger.error(f"K线时间戳异常: {kline.timestamp} != 预期 {last_closed_timestamp}")
    # 发送告警
```

### 3. 单元测试覆盖

确保WebSocket数据处理的测试覆盖：
- K线收盘检测
- 时间戳转换
- 边界情况处理

---

## 总结

### 修复清单

- [x] 后端代码修复 (`exchange_gateway.py`)
- [x] 数据修复脚本 (`fix_websocket_timestamps.py`)
- [ ] 执行数据库修复
- [ ] 重启服务
- [ ] 验证修复结果
- [ ] 添加监控告警

### 经验教训

1. **WebSocket数据流理解**：需要深入理解WebSocket数据推送机制
2. **时间戳处理**：时间戳的正确性和一致性至关重要
3. **测试覆盖**：关键逻辑需要有充分的单元测试
4. **监控验证**：生产环境需要监控验证数据正确性

---

**修复日期**: 2026-04-07
**修复人**: Claude Sonnet 4.6
**文档版本**: 1.0