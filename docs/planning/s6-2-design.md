# S6-2-4/5 信号覆盖与通知增强 - 设计文档

**创建时间**: 2026-03-29
**状态**: 设计完成，待实现

---

## 一、需求概述

### S6-2-4: 信号覆盖逻辑 + 冷却缓存重建

**目标**: 在冷却期内，允许更优信号覆盖旧信号，确保用户收到最有价值的交易机会。

**核心逻辑**:
1. 新信号产生时，检查是否存在同币种/周期/方向/策略的活跃信号
2. 如果存在且新信号评分更高，则覆盖旧信号
3. 启动时从数据库重建冷却缓存，确保重启后仍能正确覆盖

### S6-2-5: 通知消息增强

**目标**: 在通知中清晰展示信号覆盖和反向信号信息，帮助用户理解信号关系。

**核心功能**:
1. 覆盖通知：展示新旧信号评分对比
2. 反向信号通知：展示对立方向信号信息

---

## 二、数据库表设计

### signals 表字段（已完成 - S6-2-3）

```sql
CREATE TABLE signals (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL NOT NULL,
    created_at TEXT NOT NULL,
    -- S6-2 新增字段
    superseded_by TEXT,           -- 被哪个信号覆盖（指向新 signal_id）
    opposing_signal_id TEXT,      -- 对立信号 ID
    opposing_signal_score REAL,   -- 对立信号评分
    FOREIGN KEY (superseded_by) REFERENCES signals(signal_id)
);
```

### 索引设计

```sql
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signals_dedup ON signals(symbol, timeframe, direction, strategy_name, status);
CREATE INDEX idx_signals_created ON signals(created_at);
```

---

## 三、接口设计

### 3.1 SignalPipeline 接口

```python
class SignalPipeline:
    async def initialize(self) -> None:
        """启动时重建冷却缓存"""

    async def process_kline(self, kline: KlineData) -> None:
        """处理 K 线，包含覆盖逻辑检查"""

    async def _check_cover(
        self,
        kline: KlineData,
        attempt: SignalAttempt,
        score: float,
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """
        检查是否应该覆盖旧信号

        Returns:
            (should_cover, superseded_signal_id, old_signal_data)
        """
```

### 3.2 NotificationService 接口

```python
class NotificationService:
    async def send_signal(
        self,
        signal: SignalResult,
        superseded_signal: Optional[SignalResult] = None,  # S6-2-5 新增
        opposing_signal: Optional[SignalResult] = None,     # S6-2-5 新增
    ) -> None:
        """发送信号通知，支持覆盖和反向信号"""
```

### 3.3 新增消息模板函数

```python
def format_cover_signal_message(
    signal: SignalResult,
    superseded_signal: dict,  # 旧信号数据（包含 score）
) -> str:
    """
    覆盖通知模板

    包含：
    - 新信号完整信息
    - 旧信号评分对比
    - 覆盖原因说明
    """

def format_opposing_signal_message(
    signal: SignalResult,
    opposing_signal: dict,  # 反向信号数据
) -> str:
    """
    反向信号通知模板

    包含：
    - 当前信号信息
    - 反向信号方向和评分
    - 市场分歧提示
    """
```

---

## 四、字段对齐表

### 前后端字段映射

| 后端字段 | 前端字段 | 类型 | 说明 |
|---------|---------|------|------|
| `signal_id` | `id` | TEXT | 信号唯一标识 |
| `symbol` | `symbol` | TEXT | 币种对 |
| `timeframe` | `timeframe` | TEXT | 周期 |
| `direction` | `direction` | TEXT | LONG/SHORT |
| `status` | `status` | TEXT | 信号状态 |
| `score` | `pattern_score` | REAL | 形态评分 |
| `superseded_by` | `superseded_by` | TEXT | 覆盖者 ID |
| `opposing_signal_id` | `opposing_signal_id` | TEXT | 反向信号 ID |
| `opposing_signal_score` | `opposing_signal_score` | REAL | 反向信号评分 |

### 前端 Signal 接口（已完成）

```typescript
interface Signal {
    id: string;
    symbol: string;
    timeframe: string;
    direction: Direction;
    status: SignalStatus;
    entry_price: string;
    stop_loss: string;
    position_size: string;
    leverage: number;
    tags: SignalTag[];
    pattern_score?: number;         // S6-2 新增
    superseded_by?: string;         // S6-2 新增
    opposing_signal_id?: string;    // S6-2 新增
    opposing_signal_score?: number; // S6-2 新增
    created_at: string;
}

enum SignalStatus {
    PENDING = 'pending',
    ACTIVE = 'active',
    ENTERED = 'entered',
    STOP_LOSS = 'stop_loss',
    TAKE_PROFIT = 'take_profit',
    FAILED = 'failed',
    SUPERSEDED = 'superseded',  // S6-2 新增
}
```

---

## 五、覆盖逻辑详细设计

### 5.1 时间窗口映射

| 周期 | 覆盖时间窗口 |
|------|------------|
| 15m  | 4 小时      |
| 1h   | 24 小时     |
| 4h   | 72 小时     |
| 1d   | 30 天       |
| 1w   | 90 天       |

### 5.2 覆盖条件

```python
should_cover = (
    old_signal_exists
    and old_signal_status in ['ACTIVE', 'PENDING']
    and now - old_timestamp < time_window  # 在时间窗口内
    and new_score > old_score              # 新信号评分更高
)
```

### 5.3 冷却缓存重建

```python
async def initialize(self):
    # 从数据库加载所有 ACTIVE/PENDING 信号
    recent_signals = await self._repository.get_recently_fired_signals(
        limit=100,
        max_age_seconds=self._cooldown_seconds
    )

    # 重建缓存
    for signal in recent_signals:
        dedup_key = f"{symbol}:{timeframe}:{direction}:{strategy}"
        self._signal_cache[dedup_key] = {
            'timestamp': signal.timestamp / 1000,
            'signal_id': signal.signal_id,
            'score': signal.pattern_score,
        }
```

---

## 六、通知模板设计

### 6.1 标准信号通知

```
【交易信号提醒】

币种：BTC/USDT:USDT
周期：15m
方向：🟢 看多 (LONG)
入场价：65000.00
止损位：64500.00
建议仓位：0.15 BTC
当前杠杆：10x

指标标签:
  EMA: Bullish
  MTF: Confirmed
  Volume: Surge

风控信息：最大亏损 1%，盈亏比 1:2.5

---
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

### 6.2 覆盖信号通知

```
【信号覆盖提醒】⚡

币种：BTC/USDT:USDT
周期：15m
方向：🟢 看多 (LONG)
入场价：65200.00（更新）
止损位：64700.00（更新）
建议仓位：0.15 BTC
当前杠杆：10x

【覆盖原因】
新信号评分：0.85（原信号评分：0.72）
评分提升：+18%

指标标签:
  EMA: Bullish
  MTF: Confirmed
  ATR: Strong

风控信息：最大亏损 1%，盈亏比 1:3.0

---
⚡ 此信号覆盖了之前的信号 (ID: xxx)，因为形态质量更优
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

### 6.3 反向信号通知

```
【反向信号提醒】⚠️

币种：BTC/USDT:USDT
周期：15m
方向：🔴 看空 (SHORT)  ← 与原信号相反
入场价：64800.00
止损位：65300.00
建议仓位：0.15 BTC
当前杠杆：10x

【市场分歧提示】
当前方向信号评分：0.78
反向方向信号评分：0.82（更高）

⚠️ 注意：存在更优的反向信号，市场可能出现分歧

指标标签:
  EMA: Bearish
  MTF: Confirmed

风控信息：最大亏损 1%，盈亏比 1:2.8

---
⚠️ 市场存在反向信号，请谨慎判断
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

---

## 七、实现步骤

### S6-2-4 实现步骤

1. **修改 signal_pipeline.py**:
   - 在 `initialize()` 方法中添加缓存重建逻辑
   - 在 `process_kline()` 方法中调用 `_check_cover()`
   - 实现 `_get_timeframe_window()` 时间窗口计算
   - 修改覆盖处理逻辑，调用 `repository.update_superseded_by()`

2. **修改 signal_repository.py**:
   - 确认 `update_superseded_by()` 方法已实现
   - 添加 `get_active_signal()` 方法（如未实现）

### S6-2-5 实现步骤

1. **修改 notifier.py**:
   - 修改 `send_signal()` 方法签名，增加可选参数
   - 添加 `format_cover_signal_message()` 模板函数
   - 添加 `format_opposing_signal_message()` 模板函数
   - 修改 `format_signal_message()` 以支持新字段

2. **修改 signal_pipeline.py**:
   - 在调用 `send_signal()` 时传入 `superseded_signal` 和 `opposing_signal`

---

## 八、测试计划

### 单元测试

```python
# test_signal_pipeline.py
async def test_signal_cover_logic():
    """测试信号覆盖逻辑"""
    # 1. 创建旧信号（评分 0.7）
    # 2. 创建新信号（评分 0.85）
    # 3. 验证覆盖发生

async def test_cache_rebuild():
    """测试冷却缓存重建"""
    # 1. 插入测试信号到 DB
    # 2. 调用 pipeline.initialize()
    # 3. 验证缓存已重建
```

### 集成测试

```python
# test_notifier.py
def test_cover_signal_message():
    """测试覆盖通知模板"""

def test_opposing_signal_message():
    """测试反向信号模板"""
```

---

## 九、验收标准

- [ ] 信号覆盖逻辑正确，评分高的信号覆盖评分低的信号
- [ ] 冷却缓存启动时正确重建
- [ ] 通知消息包含覆盖和反向信号信息
- [ ] 前端正确展示被覆盖信号（视觉降级）
- [ ] 所有测试通过

---

*设计文档完成*
