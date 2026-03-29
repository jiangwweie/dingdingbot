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

*文档结束*
