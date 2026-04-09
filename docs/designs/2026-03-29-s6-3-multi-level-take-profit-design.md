# 多级别止盈功能设计文档

**创建日期**: 2026-03-29
**版本**: v0.1.0
**状态**: 待批准
**任务编号**: S6-3

---

## 一、功能概述

### 1.1 背景

当前系统仅有单一止盈 (`take_profit_1`)，无法满足分批止盈的交易策略需求。交易者通常希望：
- 在 TP1 止盈 50% 仓位，锁定基础利润
- 在 TP2 止盈剩余 50% 仓位，博取更大行情

### 1.2 功能目标

| 目标 | 说明 |
|------|------|
| **多级别止盈** | 支持 TP1、TP2 等多个止盈级别 |
| **动态计算** | 基于止损距离和盈亏比自动计算止盈价格 |
| **配置化** | 支持用户自定义止盈级别、仓位比例、盈亏比 |
| **前端可视化** | K 线图上绘制所有止盈线，与止损线区分 |

### 1.3 核心规格

**默认止盈策略**：
```
TP1: 50% 仓位 @ 1:1.5 盈亏比
TP2: 50% 仓位 @ 1:3.0 盈亏比
```

**止盈价格公式**：
- **LONG**: `TP = Entry + (|Entry - Stop| × RiskReward)`
- **SHORT**: `TP = Entry - (|Entry - Stop| × RiskReward)`

---

## 二、系统架构

### 2.1 数据流

```
┌──────────────────────────────────────────────────────────────┐
│                     多级别止盈数据流                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │  RiskConfig │ ──► │ RiskCalculator │ ──► │ SignalResult │    │
│  │  (止盈配置)  │     │ (计算止盈价格) │     │ (包含各级别)  │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
│                                               │               │
│                                               ▼               │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │ SignalTable │ ◄── │ Repository  │ ◄── │  signal_id  │    │
│  │ take_profits│     │ (持久化)    │     │ (外键关联)  │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
│                                               │               │
│                                               ▼               │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │  Frontend   │ ◄── │  API /signals│ ◄── │ SignalDTO   │    │
│  │ (K 线图渲染) │     │  (返回 JSON) │     │ (包含 TP)    │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 模块依赖

```
domain/
├── models.py              # TakeProfitLevel, TakeProfitConfig, SignalResult 扩展
├── risk_calculator.py     # calculate_take_profit_levels() 方法

application/
├── signal_pipeline.py     # 传递止盈数据到 Repository

infrastructure/
├── signal_repository.py   # signal_take_profits 表 CRUD
├── notifier.py            # 通知消息包含止盈信息

interfaces/
├── api.py                 # /signals 返回 take_profit_levels
```

---

## 三、数据模型设计

### 3.1 TakeProfitLevel（止盈级别）

```python
class TakeProfitLevel(BaseModel):
    """单个止盈级别"""
    id: str                    # "TP1", "TP2", ...
    position_ratio: Decimal    # 仓位比例 (0.5 = 50%)
    risk_reward: Decimal       # 盈亏比 (1.5 = 1:1.5)
    price: Decimal             # 计算后的止盈价格
```

### 3.2 TakeProfitConfig（止盈配置）

```python
class TakeProfitConfig(BaseModel):
    """止盈策略配置"""
    enabled: bool = True
    levels: List[TakeProfitLevel]
```

### 3.3 SignalResult 扩展

```python
class SignalResult(BaseModel):
    # ... 现有字段 ...
    symbol: str
    entry_price: Decimal
    suggested_stop_loss: Decimal
    # ...

    # 新增字段
    take_profit_levels: List[Dict[str, Any]] = Field(default_factory=list)
    # 结构：[
    #   {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "43000"},
    #   {"id": "TP2", "position_ratio": "0.5", "risk_reward": "3.0", "price": "46000"}
    # ]
```

### 3.4 数据库设计

```sql
-- 新建止盈级别表
CREATE TABLE IF NOT EXISTS signal_take_profits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    tp_id TEXT NOT NULL,              -- "TP1", "TP2"
    position_ratio TEXT NOT NULL,     -- 仓位比例
    risk_reward TEXT NOT NULL,        -- 盈亏比
    price_level TEXT NOT NULL,        -- 止盈价格
    status TEXT DEFAULT 'PENDING',    -- PENDING/WON/CANCELLED
    filled_at TEXT,
    pnl_ratio TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_signal_tp_signal_id
ON signal_take_profits(signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_tp_status
ON signal_take_profits(status);
```

---

## 四、核心实现

### 4.1 止盈计算逻辑

**文件**: `src/domain/risk_calculator.py`

```python
def calculate_take_profit_levels(
    self,
    entry_price: Decimal,
    stop_loss: Decimal,
    direction: Direction,
    config: Optional[TakeProfitConfig] = None,
) -> List[TakeProfitLevel]:
    """
    计算多级别止盈价格

    核心公式:
    - LONG: TP = Entry + (|Entry - Stop| × RiskReward)
    - SHORT: TP = Entry - (|Entry - Stop| × RiskReward)

    Args:
        entry_price: 入场价格
        stop_loss: 止损价格
        direction: 方向 (LONG/SHORT)
        config: 止盈配置（可选，使用默认配置如果为空）

    Returns:
        止盈级别列表
    """
    # 使用默认配置或用户配置
    if config is None or not config.enabled:
        config = self._get_default_take_profit_config()

    stop_distance = abs(entry_price - stop_loss)
    levels = []

    for level in config.levels:
        if direction == Direction.LONG:
            tp_price = entry_price + (stop_distance * level.risk_reward)
        else:  # SHORT
            tp_price = entry_price - (stop_distance * level.risk_reward)

        levels.append(TakeProfitLevel(
            id=level.id,
            position_ratio=level.position_ratio,
            risk_reward=level.risk_reward,
            price=self._quantize_price(tp_price, entry_price),
        ))

    return levels
```

### 4.2 默认配置

```python
def _get_default_take_profit_config(self) -> TakeProfitConfig:
    """获取默认止盈配置"""
    return TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
        ]
    )
```

### 4.3 SignalResult 生成

**文件**: `src/domain/risk_calculator.py`

```python
def calculate_signal_result(
    self,
    kline: KlineData,
    account: AccountSnapshot,
    direction: Direction,
    tags: List[Dict[str, str]] = None,
    kline_timestamp: int = 0,
    strategy_name: str = "unknown",
    score: float = 0.0,
) -> SignalResult:
    # ... 现有代码 ...

    # 计算止盈级别
    take_profit_levels = self.calculate_take_profit_levels(
        entry_price, stop_loss, direction
    )

    return SignalResult(
        # ... 现有字段 ...
        take_profit_levels=[
            {
                "id": tp.id,
                "position_ratio": str(tp.position_ratio),
                "risk_reward": str(tp.risk_reward),
                "price": str(tp.price),
            }
            for tp in take_profit_levels
        ],
    )
```

### 4.4 数据库持久化

**文件**: `src/infrastructure/signal_repository.py`

```python
async def store_take_profit_levels(
    self,
    signal_id: int,
    take_profit_levels: List[Dict[str, Any]],
) -> None:
    """
    保存止盈级别到数据库

    Args:
        signal_id: 信号 ID
        take_profit_levels: 止盈级别列表
    """
    for tp in take_profit_levels:
        await self._db.execute(
            """
            INSERT INTO signal_take_profits
            (signal_id, tp_id, position_ratio, risk_reward, price_level, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                signal_id,
                tp["id"],
                tp["position_ratio"],
                tp["risk_reward"],
                tp["price"],
            ),
        )
    await self._db.commit()
```

### 4.5 API 返回

**文件**: `src/interfaces/api.py`

```python
@app.get("/api/signals")
async def get_signals(query: SignalQuery):
    # ... 现有代码 ...

    # 加载止盈级别
    signals_with_tp = []
    for signal in signals:
        tp_levels = await repository.get_take_profit_levels(signal["id"])
        signal["take_profit_levels"] = tp_levels
        signals_with_tp.append(signal)

    return signals_with_tp
```

---

## 五、前端实现

### 5.1 K 线图止盈线绘制

**文件**: `web-front/src/components/SignalDetailsDrawer.tsx`

```typescript
// 在现有止损线代码后添加（第 169 行后）

// Add visual horizontal lines for Take Profit levels
if (data.signal.take_profit_levels && data.signal.take_profit_levels.length > 0) {
  data.signal.take_profit_levels.forEach((tp) => {
    candleSeries.createPriceLine({
      price: Number(tp.price),
      color: APPLE_GREEN,
      lineWidth: 1,
      lineStyle: 2, // Dashed
      axisLabelVisible: true,
      title: `${tp.id} (${Number(tp.position_ratio) * 100}%)`,
    });
  });
}
```

### 5.2 前端类型定义

**文件**: `web-front/src/lib/api.ts`

```typescript
export interface Signal {
  // ... 现有字段 ...
  id: number;
  symbol: string;
  direction: 'long' | 'short';
  entry_price: string;
  stop_loss: string;
  take_profit?: string;        // 遗留字段（兼容旧数据）
  take_profit_levels?: Array<{  // 新增
    id: string;
    position_ratio: string;
    risk_reward: string;
    price: string;
  }>;
  // ...
}
```

### 5.3 前端 UI 展示

**文件**: `web-front/src/components/SignalDetailsDrawer.tsx`

```typescript
{/* Take Profit Levels - 多级别展示 */}
<div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
  <div className="flex items-center gap-2 mb-2">
    <TrendingUp className="w-4 h-4 text-gray-400" />
    <span className="text-xs text-gray-500 uppercase">止盈目标</span>
  </div>
  <div className="space-y-1">
    {data.signal.take_profit_levels?.map((tp) => (
      <div key={tp.id} className="flex justify-between text-sm">
        <span className="text-gray-500">{tp.id}:</span>
        <span className="font-mono text-apple-green">
          {Number(tp.price).toFixed(2)}
          <span className="text-xs text-gray-400 ml-1">
            ({Number(tp.position_ratio) * 100}% @ 1:{Number(tp.risk_reward)})
          </span>
        </span>
      </div>
    ))}
    {!data.signal.take_profit_levels?.length && (
      <span className="text-sm text-gray-400">-</span>
    )}
  </div>
</div>
```

---

## 六、配置化方案

### 6.1 core.yaml 默认配置

```yaml
# 止盈策略配置（新增）
take_profit:
  enabled: true
  default_strategy: "1_5_3"  # 预设策略 ID
  levels:
    - id: TP1
      position_ratio: 0.5
      risk_reward: 1.5
    - id: TP2
      position_ratio: 0.5
      risk_reward: 3.0
```

### 6.2 user.yaml 用户覆盖

```yaml
# 用户可自定义止盈策略
take_profit:
  enabled: true
  levels:
    - id: TP1
      position_ratio: 0.4
      risk_reward: 1.2
    - id: TP2
      position_ratio: 0.3
      risk_reward: 2.5
    - id: TP3
      position_ratio: 0.3
      risk_reward: 5.0
```

### 6.3 配置加载

**文件**: `src/application/config_manager.py`

```python
class CoreConfig(BaseModel):
    # ... 现有字段 ...
    take_profit: TakeProfitConfig = Field(
        default_factory=lambda: TakeProfitConfig(
            enabled=True,
            levels=[
                TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
                TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
            ]
        )
    )
```

---

## 七、回测集成

### 7.1 回测止盈处理

**文件**: `src/application/backtester.py`

```python
async def check_exit_conditions(
    self,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit_levels: List[Dict[str, Any]],
    direction: Direction,
    kline: KlineData,
) -> Optional[str]:
    """
    检查是否触发止盈或止损

    TODO: 未来实现分批止盈模拟
    当前逻辑：价格触及任意 TP 级别即判定为 WON

    分批成交模拟需要考虑:
    1. TP1 先成交 50% 仓位
    2. TP2 后成交 50% 仓位
    3. 如果价格 reversal，可能只成交部分级别
    参考实现：performance_tracker.py 的 check_signal 方法

    Args:
        entry_price: 入场价格
        stop_loss: 止损价格
        take_profit_levels: 止盈级别列表
        direction: 方向
        kline: 当前 K 线

    Returns:
        "WON" / "LOST" / None (继续持有)
    """
    kline_high = kline.high
    kline_low = kline.low

    if direction == Direction.LONG:
        # 检查止损
        if kline_low <= stop_loss:
            return "LOST"
        # 检查止盈（当前简化逻辑：触及任意 TP 即止盈）
        for tp in take_profit_levels:
            if kline_high >= Decimal(tp["price"]):
                return "WON"
    else:  # SHORT
        # 检查止损
        if kline_high >= stop_loss:
            return "LOST"
        # 检查止盈
        for tp in take_profit_levels:
            if kline_low <= Decimal(tp["price"]):
                return "WON"

    return None
```

---

## 八、通知消息格式

### 8.1 飞书/微信消息

**文件**: `src/infrastructure/notifier.py`

```python
def format_signal_message(signal: SignalResult) -> str:
    # ... 现有代码 ...

    # 构建止盈信息
    tp_section = ""
    if signal.take_profit_levels:
        tp_lines = [
            f"  {tp['id']}: {tp['price']} ({tp['position_ratio']} @ 1:{tp['risk_reward']})"
            for tp in signal.take_profit_levels
        ]
        tp_section = "\n止盈目标:\n" + "\n".join(tp_lines) + "\n"
    else:
        tp_section = "\n止盈目标：无\n"

    message = f"""【交易信号提醒】

币种：{signal.symbol}
周期：{signal.timeframe}
方向：{direction_text}
入场价：{signal.entry_price}
止损位：{signal.suggested_stop_loss}
{tp_section}
指标标签:
{tags_section}
风控信息：{signal.risk_reward_info}

---
⚠️ 本系统仅为观测与通知工具，不构成投资建议
"""
```

---

## 九、测试计划

### 9.1 单元测试

| 测试 | 说明 |
|------|------|
| `test_calculate_take_profit_levels_long` | LONG 方向止盈计算 |
| `test_calculate_take_profit_levels_short` | SHORT 方向止盈计算 |
| `test_take_profit_config_override` | 用户配置覆盖默认值 |
| `test_store_take_profit_levels` | 数据库持久化 |

### 9.2 集成测试

| 测试 | 说明 |
|------|------|
| `test_signal_generation_with_tp` | 信号生成包含止盈级别 |
| `test_api_response_with_tp` | API 返回包含 take_profit_levels |
| `test_frontend_kline_rendering` | K 线图正确绘制 TP1/TP2/SL |

---

## 十、实现计划

### Phase 1: 后端基础（2-3h）

| 任务 | 文件 | 说明 |
|------|------|------|
| F-1 | `src/domain/models.py` | 定义 TakeProfitLevel, TakeProfitConfig |
| F-2 | `src/domain/risk_calculator.py` | 实现 calculate_take_profit_levels() |
| F-3 | `src/infrastructure/signal_repository.py` | 创建表 + CRUD 方法 |
| F-4 | `src/interfaces/api.py` | API 返回 take_profit_levels |

### Phase 2: 前端渲染（1-2h）

| 任务 | 文件 | 说明 |
|------|------|------|
| F-5 | `web-front/src/lib/api.ts` | 扩展 Signal 类型 |
| F-6 | `web-front/src/components/SignalDetailsDrawer.tsx` | K 线图绘制止盈线 |
| F-7 | `web-front/src/components/SignalDetailsDrawer.tsx` | 数据面板展示多级别 |

### Phase 3: 测试与修复（1-2h）

| 任务 | 说明 |
|------|------|
| F-8 | 编写单元测试 |
| F-9 | 集成测试验证 |
| F-10 | 端到端测试（实盘信号 + 前端渲染） |

---

## 十一、验收标准

1. **后端**：
   - [ ] 止盈价格计算正确（LONG/SHORT 各测 3 个用例）
   - [ ] 数据库正确保存止盈级别
   - [ ] API 返回格式正确

2. **前端**：
   - [ ] K 线图上 TP1/TP2/SL 三条线正确显示
   - [ ] 止盈线颜色为绿色（与止损红色区分）
   - [ ] 数据面板显示多级别止盈信息

3. **配置**：
   - [ ] 默认配置生效
   - [ ] 用户配置可覆盖

---

## 十二、风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| 旧数据兼容 | 新信号用新表，旧信号保留 take_profit_1 字段 |
| 前端类型错误 | TypeScript 严格类型检查 |
| 计算精度问题 | 全部使用 Decimal，禁止 float |
| 通知消息过长 | 限制止盈级别显示数量（最多 3 级） |

---

## 十三、技术债记录

| 编号 | 说明 | 优先级 |
|------|------|--------|
| #TP-1 | 回测分批止盈模拟未实现 | 低 |
| #TP-2 | 实盘止盈追踪逻辑未实现 | 中 |

---

## 十四、接口文档

### 14.1 REST API 接口

#### GET /api/signals - 获取信号列表

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 返回数量限制 (默认 50, 最大 500) |
| offset | int | 否 | 偏移量 (默认 0) |
| symbol | string | 否 | 币种过滤，如 "BTC/USDT:USDT" |
| direction | string | 否 | 方向过滤 ("long" / "short") |
| status | string | 否 | 状态过滤 ("PENDING" / "WON" / "LOST") |
| strategy_name | string | 否 | 策略名称过滤 |
| start_time | string | 否 | 开始时间 (ISO 8601 或时间戳) |
| end_time | string | 否 | 结束时间 (ISO 8601 或时间戳) |

**响应格式**:

```json
{
  "signals": [
    {
      "id": 1234,
      "symbol": "BTC/USDT:USDT",
      "timeframe": "15m",
      "direction": "long",
      "entry_price": "40000.00",
      "stop_loss": "38000.00",
      "position_size": "0.05263157",
      "leverage": 5,
      "status": "PENDING",
      "pnl_ratio": 0,
      "score": 0.85,
      "strategy_name": "pinbar",
      "kline_timestamp": 1743264000000,
      "created_at": "2026-03-29T12:00:00Z",
      "take_profit_levels": [
        {
          "id": "TP1",
          "position_ratio": "0.5",
          "risk_reward": "1.5",
          "price": "43000.00"
        },
        {
          "id": "TP2",
          "position_ratio": "0.5",
          "risk_reward": "3.0",
          "price": "46000.00"
        }
      ],
      "tags": [
        {"name": "EMA", "value": "Bullish"},
        {"name": "ATR", "value": "0.65"}
      ]
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

#### GET /api/signals/{id} - 获取信号详情

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| id | int | 信号 ID |

**响应格式**:

```json
{
  "signal": {
    "id": 1234,
    "symbol": "BTC/USDT:USDT",
    "timeframe": "15m",
    "direction": "long",
    "entry_price": "40000.00",
    "stop_loss": "38000.00",
    "position_size": "0.05263157",
    "leverage": 5,
    "status": "PENDING",
    "pnl_ratio": 0,
    "score": 0.85,
    "strategy_name": "pinbar",
    "kline_timestamp": 1743264000000,
    "created_at": "2026-03-29T12:00:00Z",
    "take_profit_levels": [
      {
        "id": "TP1",
        "position_ratio": "0.5",
        "risk_reward": "1.5",
        "price": "43000.00",
        "status": "PENDING"
      },
      {
        "id": "TP2",
        "position_ratio": "0.5",
        "risk_reward": "3.0",
        "price": "46000.00",
        "status": "PENDING"
      }
    ],
    "tags": [
      {"name": "EMA", "value": "Bullish"}
    ]
  }
}
```

---

#### GET /api/signals/{id}/context - 获取信号上下文（含 K 线数据）

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| id | int | 信号 ID |

**响应格式**:

```json
{
  "signal": {
    "id": 1234,
    "symbol": "BTC/USDT:USDT",
    "timeframe": "15m",
    "direction": "long",
    "entry_price": "40000.00",
    "stop_loss": "38000.00",
    "take_profit_levels": [
      {"id": "TP1", "price": "43000.00", "position_ratio": "0.5", "risk_reward": "1.5"},
      {"id": "TP2", "price": "46000.00", "position_ratio": "0.5", "risk_reward": "3.0"}
    ],
    "kline_timestamp": 1743264000000
  },
  "klines": [
    [1743260400000, 39800, 40100, 39700, 39900],  // [time, open, high, low, close]
    [1743261300000, 39900, 40200, 39850, 40000],
    [1743262200000, 40000, 40300, 39950, 40100],
    ...  // 信号前后各 10 根 K 线，共 21 根
  ]
}
```

---

### 14.2 数据库操作接口

#### SignalRepository 方法

```python
class SignalRepository:
    # ========== 写操作 ==========

    async def store_take_profit_levels(
        self,
        signal_id: int,
        take_profit_levels: List[Dict[str, Any]],
    ) -> None:
        """
        保存止盈级别到数据库

        Args:
            signal_id: 信号 ID
            take_profit_levels: 止盈级别列表，结构:
                [
                    {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "43000"},
                    ...
                ]
        """

    async def update_take_profit_status(
        self,
        signal_id: int,
        tp_id: str,
        status: str,
        pnl_ratio: Optional[Decimal] = None,
        filled_at: Optional[str] = None,
    ) -> None:
        """
        更新止盈级别状态

        Args:
            signal_id: 信号 ID
            tp_id: 止盈级别 ID (如 "TP1")
            status: 新状态 ("WON" / "CANCELLED")
            pnl_ratio: 盈亏比（可选）
            filled_at: 成交时间（可选）
        """

    # ========== 读操作 ==========

    async def get_take_profit_levels(
        self,
        signal_id: int,
    ) -> List[Dict[str, Any]]:
        """
        获取信号的止盈级别

        Args:
            signal_id: 信号 ID

        Returns:
            止盈级别列表:
                [
                    {
                        "id": 1,
                        "tp_id": "TP1",
                        "position_ratio": "0.5",
                        "risk_reward": "1.5",
                        "price_level": "43000.00",
                        "status": "PENDING"
                    },
                    ...
                ]
        """

    async def get_pending_signals(self, symbol: str) -> List[Dict[str, Any]]:
        """
        获取待处理信号（包含止盈级别）

        Args:
            symbol: 币种

        Returns:
            信号列表，每个信号包含 take_profit_levels 字段
        """
```

---

## 十五、测试用例设计

### 15.1 单元测试

#### 测试文件：`tests/unit/test_risk_calculator.py`

**用例 1: LONG 方向止盈计算**

```python
async def test_calculate_take_profit_levels_long():
    """测试 LONG 方向止盈价格计算"""
    config = TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
        ]
    )
    calculator = RiskCalculator(config)

    entry_price = Decimal("40000")
    stop_loss = Decimal("38000")  # 止损距离 = 2000
    direction = Direction.LONG

    levels = calculator.calculate_take_profit_levels(entry_price, stop_loss, direction, config)

    # 验证
    assert len(levels) == 2

    # TP1: 40000 + (2000 * 1.5) = 43000
    assert levels[0].id == "TP1"
    assert levels[0].price == Decimal("43000")
    assert levels[0].position_ratio == Decimal("0.5")
    assert levels[0].risk_reward == Decimal("1.5")

    # TP2: 40000 + (2000 * 3.0) = 46000
    assert levels[1].id == "TP2"
    assert levels[1].price == Decimal("46000")
    assert levels[1].position_ratio == Decimal("0.5")
    assert levels[1].risk_reward == Decimal("3.0")
```

**用例 2: SHORT 方向止盈计算**

```python
async def test_calculate_take_profit_levels_short():
    """测试 SHORT 方向止盈价格计算"""
    config = TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
        ]
    )
    calculator = RiskCalculator(config)

    entry_price = Decimal("40000")
    stop_loss = Decimal("42000")  # 止损距离 = 2000
    direction = Direction.SHORT

    levels = calculator.calculate_take_profit_levels(entry_price, stop_loss, direction, config)

    # 验证
    assert len(levels) == 1

    # TP1: 40000 - (2000 * 1.5) = 37000 (SHORT 止盈在下方)
    assert levels[0].id == "TP1"
    assert levels[0].price == Decimal("37000")
```

**用例 3: 用户配置覆盖默认值**

```python
async def test_take_profit_config_override():
    """测试用户配置覆盖默认值"""
    config = TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.4"), risk_reward=Decimal("1.2")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.3"), risk_reward=Decimal("2.5")),
            TakeProfitLevel(id="TP3", position_ratio=Decimal("0.3"), risk_reward=Decimal("5.0")),
        ]
    )
    calculator = RiskCalculator(config)

    entry_price = Decimal("100")
    stop_loss = Decimal("90")  # 止损距离 = 10
    direction = Direction.LONG

    levels = calculator.calculate_take_profit_levels(entry_price, stop_loss, direction, config)

    # 验证 3 个级别
    assert len(levels) == 3

    # TP1: 100 + (10 * 1.2) = 112
    assert levels[0].price == Decimal("112")
    # TP2: 100 + (10 * 2.5) = 125
    assert levels[1].price == Decimal("125")
    # TP3: 100 + (10 * 5.0) = 150
    assert levels[2].price == Decimal("150")
```

**用例 4: 止盈配置禁用**

```python
async def test_take_profit_disabled():
    """测试止盈配置禁用时返回空列表"""
    config = TakeProfitConfig(enabled=False, levels=[])
    calculator = RiskCalculator(config)

    entry_price = Decimal("40000")
    stop_loss = Decimal("38000")
    direction = Direction.LONG

    levels = calculator.calculate_take_profit_levels(
        entry_price, stop_loss, direction, config
    )

    # 验证返回空列表
    assert levels == []
```

---

#### 测试文件：`tests/unit/test_signal_repository.py`

**用例 5: 保存止盈级别**

```python
async def test_store_take_profit_levels():
    """测试保存止盈级别到数据库"""
    repository = SignalRepository("test.db")
    await repository.initialize()

    # 先创建测试信号
    signal_id = await repository._db.execute(
        """
        INSERT INTO signals (symbol, timeframe, direction, entry_price, stop_loss, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT:USDT", "15m", "long", "40000", "38000", "2026-03-29T12:00:00Z")
    )
    await repository._db.commit()

    # 保存止盈级别
    take_profit_levels = [
        {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "43000"},
        {"id": "TP2", "position_ratio": "0.5", "risk_reward": "3.0", "price": "46000"},
    ]
    await repository.store_take_profit_levels(signal_id, take_profit_levels)

    # 验证
    async with repository._db.execute(
        "SELECT * FROM signal_take_profits WHERE signal_id = ?", (signal_id,)
    ) as cursor:
        rows = await cursor.fetchall()

        assert len(rows) == 2
        assert rows[0]["tp_id"] == "TP1"
        assert rows[0]["price_level"] == "43000"
        assert rows[0]["status"] == "PENDING"
        assert rows[1]["tp_id"] == "TP2"
        assert rows[1]["price_level"] == "46000"

    await repository.close()
```

**用例 6: 获取止盈级别**

```python
async def test_get_take_profit_levels():
    """测试获取止盈级别"""
    repository = SignalRepository("test.db")
    await repository.initialize()

    # 先创建测试数据
    signal_id = await repository._db.execute(
        """
        INSERT INTO signals (symbol, timeframe, direction, entry_price, stop_loss, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT:USDT", "15m", "long", "40000", "38000", "2026-03-29T12:00:00Z")
    )
    await repository.store_take_profit_levels(signal_id, [
        {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "43000"},
        {"id": "TP2", "position_ratio": "0.5", "risk_reward": "3.0", "price": "46000"},
    ])

    # 获取
    levels = await repository.get_take_profit_levels(signal_id)

    # 验证
    assert len(levels) == 2
    assert levels[0]["tp_id"] == "TP1"
    assert levels[0]["price_level"] == "43000"
    assert levels[1]["tp_id"] == "TP2"

    await repository.close()
```

---

### 15.2 集成测试

#### 测试文件：`tests/integration/test_take_profit.py`

**用例 7: 完整信号生成流程**

```python
async def test_signal_generation_with_tp():
    """测试信号生成包含止盈级别的完整流程"""
    # 初始化组件
    config_manager = load_all_configs()
    calculator = RiskCalculator(config_manager.core_config.take_profit)
    repository = SignalRepository("test.db")

    # 模拟 K 线和账户数据
    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1743264000000,
        open=Decimal("39800"),
        high=Decimal("40200"),
        low=Decimal("39700"),
        close=Decimal("40000"),
        volume=Decimal("1000"),
        is_closed=True
    )

    account = AccountSnapshot(
        total_balance=Decimal("100000"),
        available_balance=Decimal("50000"),
        unrealized_pnl=Decimal("0"),
        positions=[],
        timestamp=1743264000000
    )

    # 生成信号
    signal = calculator.calculate_signal_result(
        kline=kline,
        account=account,
        direction=Direction.LONG,
        tags=[{"name": "EMA", "value": "Bullish"}],
        kline_timestamp=1743264000000,
        strategy_name="pinbar",
        score=0.85
    )

    # 验证信号包含止盈级别
    assert signal.take_profit_levels is not None
    assert len(signal.take_profit_levels) >= 2

    # 验证止盈价格计算正确
    tp1 = next(tp for tp in signal.take_profit_levels if tp["id"] == "TP1")
    tp2 = next(tp for tp in signal.take_profit_levels if tp["id"] == "TP2")

    # 止损距离 = 40000 - 38000 = 2000
    # TP1 = 40000 + 2000 * 1.5 = 43000
    assert Decimal(tp1["price"]) == Decimal("43000")
    # TP2 = 40000 + 2000 * 3.0 = 46000
    assert Decimal(tp2["price"]) == Decimal("46000")

    await repository.close()
```

**用例 8: API 返回验证**

```python
async def test_api_response_with_tp():
    """测试 API 返回包含 take_profit_levels"""
    # 启动测试服务器
    async with TestClient(app) as client:
        # 创建测试信号
        response = await client.post("/api/signals", json={
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "direction": "long",
            "entry_price": "40000",
            "stop_loss": "38000",
            "take_profit_levels": [
                {"id": "TP1", "price": "43000", "position_ratio": "0.5", "risk_reward": "1.5"},
                {"id": "TP2", "price": "46000", "position_ratio": "0.5", "risk_reward": "3.0"},
            ]
        })

        assert response.status_code == 200
        signal_id = response.json()["id"]

        # 获取信号详情
        response = await client.get(f"/api/signals/{signal_id}")
        data = response.json()

        # 验证响应包含止盈级别
        assert "take_profit_levels" in data["signal"]
        assert len(data["signal"]["take_profit_levels"]) == 2

        tp_levels = data["signal"]["take_profit_levels"]
        assert tp_levels[0]["id"] == "TP1"
        assert tp_levels[0]["price"] == "43000"
        assert tp_levels[1]["id"] == "TP2"
        assert tp_levels[1]["price"] == "46000"
```

---

### 15.3 前端测试

#### 测试文件：`web-front/src/components/__tests__/SignalDetailsDrawer.test.tsx`

**用例 9: K 线图渲染止盈线**

```typescript
import { render, screen } from '@testing-library/react';
import SignalDetailsDrawer from '../SignalDetailsDrawer';
import { fetchSignalContext } from '../../lib/api';

// Mock API 调用
jest.mock('../../lib/api');

describe('SignalDetailsDrawer', () => {
  it('should render take profit lines on chart', async () => {
    const mockSignal = {
      id: 1234,
      symbol: 'BTC/USDT:USDT',
      direction: 'long',
      entry_price: '40000',
      stop_loss: '38000',
      take_profit_levels: [
        { id: 'TP1', price: '43000', position_ratio: '0.5', risk_reward: '1.5' },
        { id: 'TP2', price: '46000', position_ratio: '0.5', risk_reward: '3.0' },
      ],
      kline_timestamp: 1743264000000,
    };

    (fetchSignalContext as jest.Mock).mockResolvedValue({
      signal: mockSignal,
      klines: [
        [1743260400000, 39800, 40100, 39700, 39900],
        // ... 更多 K 线
      ],
    });

    render(<SignalDetailsDrawer signalId="1234" isOpen={true} onClose={() => {}} />);

    // 等待图表加载
    await screen.findByTestId('kline-chart');

    // 验证止盈信息展示
    expect(screen.getByText('TP1')).toBeInTheDocument();
    expect(screen.getByText('43000.00')).toBeInTheDocument();
    expect(screen.getByText('TP2')).toBeInTheDocument();
    expect(screen.getByText('46000.00')).toBeInTheDocument();
  });
});
```

---

### 15.4 端到端测试

#### 测试文件：`tests/e2e/test_take_profit_flow.py`

**用例 10: 完整止盈流程测试**

```python
async def test_end_to_end_take_profit_flow():
    """
    端到端测试：从信号生成到前端渲染的完整流程

    测试步骤:
    1. 后端生成信号（含止盈级别）
    2. 保存到数据库
    3. API 返回正确的 JSON 格式
    4. 前端正确渲染 K 线图和止盈线
    """
    # 步骤 1-3: 后端测试
    from src.domain.risk_calculator import RiskCalculator, TakeProfitConfig, TakeProfitLevel
    from src.infrastructure.signal_repository import SignalRepository
    from src.domain.models import Direction, KlineData, AccountSnapshot
    from decimal import Decimal

    # 初始化
    config = TakeProfitConfig(
        enabled=True,
        levels=[
            TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
            TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
        ]
    )
    calculator = RiskCalculator(config)
    repository = SignalRepository("test.db")

    # 生成信号
    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1743264000000,
        open=Decimal("40000"),
        high=Decimal("40500"),
        low=Decimal("39500"),
        close=Decimal("40000"),
        volume=Decimal("1000"),
        is_closed=True
    )

    account = AccountSnapshot(
        total_balance=Decimal("100000"),
        available_balance=Decimal("50000"),
        unrealized_pnl=Decimal("0"),
        positions=[],
        timestamp=1743264000000
    )

    signal = calculator.calculate_signal_result(
        kline=kline,
        account=account,
        direction=Direction.LONG,
        tags=[],
        kline_timestamp=1743264000000,
        strategy_name="pinbar",
        score=0.8
    )

    # 验证信号数据
    assert signal.entry_price == Decimal("40000")
    assert signal.suggested_stop_loss == Decimal("39500")  # Pinbar low
    assert len(signal.take_profit_levels) >= 2

    # 验证止盈价格
    stop_distance = Decimal("500")  # 40000 - 39500
    expected_tp1 = Decimal("40000") + (stop_distance * Decimal("1.5"))  # 40750
    expected_tp2 = Decimal("40000") + (stop_distance * Decimal("3.0"))  # 41500

    tp1 = signal.take_profit_levels[0]
    tp2 = signal.take_profit_levels[1]

    assert abs(Decimal(tp1["price"]) - expected_tp1) < Decimal("1")  # 允许 1 以内误差
    assert abs(Decimal(tp2["price"]) - expected_tp2) < Decimal("1")

    await repository.close()
```

---

### 15.5 测试用例汇总表

| 编号 | 测试名称 | 类型 | 文件 | 状态 |
|------|----------|------|------|------|
| UT-1 | LONG 方向止盈计算 | 单元 | test_risk_calculator.py | ⏸️ |
| UT-2 | SHORT 方向止盈计算 | 单元 | test_risk_calculator.py | ⏸️ |
| UT-3 | 用户配置覆盖默认值 | 单元 | test_risk_calculator.py | ⏸️ |
| UT-4 | 止盈配置禁用 | 单元 | test_risk_calculator.py | ⏸️ |
| UT-5 | 保存止盈级别 | 单元 | test_signal_repository.py | ⏸️ |
| UT-6 | 获取止盈级别 | 单元 | test_signal_repository.py | ⏸️ |
| IT-1 | 完整信号生成流程 | 集成 | test_take_profit.py | ⏸️ |
| IT-2 | API 返回验证 | 集成 | test_take_profit.py | ⏸️ |
| FT-1 | K 线图渲染止盈线 | 前端 | SignalDetailsDrawer.test.tsx | ⏸️ |
| ET-1 | 端到端流程测试 | E2E | test_take_profit_flow.py | ⏸️ |

---

## 十六、实现检查清单

### 后端

- [ ] 定义 `TakeProfitLevel` 和 `TakeProfitConfig` 模型
- [ ] 实现 `calculate_take_profit_levels()` 方法
- [ ] 创建 `signal_take_profits` 表
- [ ] 实现 `store_take_profit_levels()` 方法
- [ ] 实现 `get_take_profit_levels()` 方法
- [ ] 修改 API 返回包含 `take_profit_levels`
- [ ] 修改通知消息格式
- [ ] 编写单元测试
- [ ] 编写集成测试

### 前端

- [ ] 扩展 `Signal` 类型定义
- [ ] K 线图绘制止盈线（绿色虚线）
- [ ] 数据面板展示多级别止盈信息
- [ ] 编写前端测试

### 配置

- [ ] `core.yaml` 添加默认止盈配置
- [ ] `user.yaml` 示例配置

---

*文档结束*
