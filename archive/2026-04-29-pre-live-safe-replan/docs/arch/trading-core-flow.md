# 盯盘狗交易核心业务流程图

> **最后更新**: 2026-04-23
> **文档目的**: 梳理从交易所数据接收到订单执行的完整业务流程

---

## 📊 核心业务流程总览

```mermaid
graph TB
    Start[交易所 WebSocket 推送] --> Kline{K线是否收盘?}

    Kline -->|否| Skip[跳过处理]
    Kline -->|是| Pipeline[SignalPipeline.process_kline]

    Pipeline --> UpdateHistory[更新K线历史缓存]
    UpdateHistory --> UpdateEMA[更新EMA等有状态指标]
    UpdateEMA --> StrategyEngine[策略引擎运行]

    StrategyEngine --> PatternDetect{形态检测}
    PatternDetect -->|无形态| NoPattern[记录 NO_PATTERN]
    PatternDetect -->|检测到形态| FilterChain[过滤器链检查]

    FilterChain --> FilterResult{过滤器通过?}
    FilterResult -->|否| Filtered[记录 FILTERED]
    FilterResult -->|是| SignalFired[信号触发 SIGNAL_FIRED]

    SignalFired --> RiskCalc[风控计算]
    RiskCalc --> SignalResult[生成 SignalResult]

    SignalResult --> DedupCheck{信号去重检查}
    DedupCheck -->|冷却期内| DedupSkip[跳过重复信号]
    DedupCheck -->|新信号| ExecuteSignal[执行信号]

    ExecuteSignal --> CapitalCheck{资金保护检查}
    CapitalCheck -->|拒绝| Blocked[信号被拦截]
    CapitalCheck -->|通过| CreateOrder[创建本地订单]

    CreateOrder --> SubmitEntry[提交ENTRY到交易所]
    SubmitEntry --> EntryResult{ENTRY执行结果}

    EntryResult -->|失败| Failed[订单失败]
    EntryResult -->|成功| MountProtection[挂载保护单 TP/SL]

    MountProtection --> Complete[执行完成]

    style Start fill:#e1f5ff
    style SignalFired fill:#c8e6c9
    style ExecuteSignal fill:#fff9c4
    style MountProtection fill:#f8bbd0
    style Complete fill:#c5e1a5
```

---

## 🔄 详细业务流程分解

### 1️⃣ 交易所数据接入层

```mermaid
graph LR
    WS[WebSocket 连接] --> Subscribe[订阅 K线频道]
    Subscribe --> Receive[接收实时推送]

    Receive --> Parse{解析 K线数据}
    Parse -->|x=true| ClosedKline[收盘K线]
    Parse -->|x=false| RunningKline[运行中K线]

    ClosedKline --> Callback[触发 process_kline 回调]
    RunningKline --> Ignore[忽略]

    style ClosedKline fill:#c8e6c9
    style RunningKline fill:#ffecb3
```

**关键逻辑**:
- **P0-1修复**: 优先使用交易所 `x` 字段判断收盘状态
- **时间戳推断**: 后备方案，检测时间戳变化
- **数据质量校验**: high ≥ open/close ≥ low

---

### 2️⃣ 信号处理管道 (SignalPipeline)

```mermaid
graph TB
    ProcessKline[process_kline] --> StoreHistory[存储K线历史]
    StoreHistory --> UpdateState[更新有状态指标]

    UpdateState --> RunStrategy[运行策略引擎]
    RunStrategy --> GetAttempts[获取 SignalAttempt 列表]

    GetAttempts --> LoopAttempts{遍历每个 Attempt}

    LoopAttempts -->|NO_PATTERN| RecordAttempt[记录尝试]
    LoopAttempts -->|FILTERED| RecordFilter[记录过滤器拒绝原因]
    LoopAttempts -->|SIGNAL_FIRED| CalcRisk[风控计算]

    CalcRisk --> GenSignal[生成 SignalResult]
    GenSignal --> CheckDedup{信号去重}

    CheckDedup -->|冷却期内| LogDedup[日志记录]
    CheckDedup -->|新信号| TrackSignal[追踪信号状态]

    TrackSignal --> SendNotify[发送通知]
    SendNotify --> PersistSignal[持久化到数据库]
    PersistSignal --> DispatchExecutor[派发到执行器]

    style SIGNAL_FIRED fill:#c8e6c9
    style CalcRisk fill:#fff9c4
```

**核心职责**:
- **K线历史管理**: 缓存最近200根K线，用于多周期分析
- **热重载支持**: 配置更新时重建策略引擎
- **异步队列**: 批量持久化 SignalAttempt，避免阻塞
- **信号去重**: 基于时间窗口 + 评分覆盖机制

---

### 3️⃣ 策略引擎层 (StrategyEngine)

```mermaid
graph TB
    UpdateState[update_state] --> UpdateEMA[更新EMA状态]
    UpdateState --> UpdateATR[更新ATR状态]
    UpdateState --> UpdateFilters[更新其他有状态过滤器]

    RunAll[run_all] --> LoopStrategies{遍历策略}

    LoopStrategies --> DetectPattern[形态检测]
    DetectPattern -->|Pinbar| PinbarLogic[Pinbar 逻辑]
    DetectPattern -->|Engulfing| EngulfingLogic[吞没逻辑]
    DetectPattern -->|其他| OtherPattern[其他形态]

    PinbarLogic --> PatternResult[PatternResult]
    EngulfingLogic --> PatternResult
    OtherPattern --> PatternResult

    PatternResult -->|None| NoPattern[NO_PATTERN]
    PatternResult -->|有形态| BuildContext[构建 FilterContext]

    BuildContext --> CheckFilters[检查过滤器链]

    CheckFilters --> LoopFilters{遍历过滤器}
    LoopFilters --> EMACheck[EMA趋势检查]
    LoopFilters --> MTFCheck[MTF多周期验证]
    LoopFilters --> ATRCheck[ATR波动率检查]
    LoopFilters --> OtherCheck[其他过滤器]

    EMACheck --> FilterPass{通过?}
    MTFCheck --> FilterPass
    ATRCheck --> FilterPass
    OtherCheck --> FilterPass

    FilterPass -->|否| RecordFilter[记录 FILTERED]
    FilterPass -->|是| CheckNext{还有过滤器?}

    CheckNext -->|是| LoopFilters
    CheckNext -->|否| SignalFired[SIGNAL_FIRED]

    style SignalFired fill:#c8e6c9
    style UpdateState fill:#e1f5ff
```

**核心组件**:
- **形态策略**: Pinbar, Engulfing, Doji 等
- **过滤器链**: EMA, MTF, ATR, Volume 等
- **短路评估**: 首个过滤器失败立即返回
- **统一评分**: `score = pattern_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3`

---

### 4️⃣ 过滤器链 (Filter Chain)

```mermaid
graph LR
    Pattern[PatternResult] --> Filter1[过滤器 1]

    Filter1 -->|通过| Filter2[过滤器 2]
    Filter1 -->|拒绝| Reject1[记录拒绝原因]

    Filter2 -->|通过| Filter3[过滤器 3]
    Filter2 -->|拒绝| Reject2[记录拒绝原因]

    Filter3 -->|通过| FilterN[... 更多过滤器]
    Filter3 -->|拒绝| Reject3[记录拒绝原因]

    FilterN -->|全部通过| Pass[过滤器链通过]
    FilterN -->|任一拒绝| RejectN[过滤器链拒绝]

    style Pass fill:#c8e6c9
    style Reject1 fill:#ffcdd2
    style Reject2 fill:#ffcdd2
    style Reject3 fill:#ffcdd2
```

**常用过滤器**:
| 过滤器 | 作用 | 关键参数 |
|--------|------|----------|
| **EMA Trend** | 趋势方向过滤 | `period=60`, `min_distance_pct` |
| **MTF** | 多周期趋势确认 | `mtf_mapping={15m:1h, 1h:4h}` |
| **ATR** | 波动率过滤 | `min_atr_multiple=0.5` |
| **Volume** | 成交量放大检查 | `volume_threshold=1.5` |
| **Time** | 交易时段过滤 | `trading_hours` |

---

### 5️⃣ 风控计算层 (RiskCalculator)

```mermaid
graph TB
    CalcStopLoss[计算止损] --> StopLogic{方向判断}

    StopLogic -->|LONG| LongSL[止损 = K线最低价]
    StopLogic -->|SHORT| ShortSL[止损 = K线最高价]

    LongSL --> CalcPosition[计算仓位]
    ShortSL --> CalcPosition

    CalcPosition --> RiskAmount[风险金额 = 余额 × 风险比例]
    RiskAmount --> StopDistance[止损距离 = 入场价与止损价的距离]
    StopDistance --> PositionSize[仓位 = 风险金额 / 止损距离]

    PositionSize --> LeverageCap{杠杆上限检查}
    LeverageCap -->|超限| AdjustLeverage[调整仓位到杠杆上限]
    LeverageCap -->|正常| KeepPosition[保持计算仓位]

    AdjustLeverage --> CalcTP[计算止盈级别]
    KeepPosition --> CalcTP

    CalcTP --> TP1[TP1: RR=1.5, 比例=50%]
    CalcTP --> TP2[TP2: RR=3.0, 比例=50%]

    TP1 --> GenResult[生成 SignalResult]
    TP2 --> GenResult

    style CalcPosition fill:#fff9c4
    style GenResult fill:#c8e6c9
```

**核心公式**:
```
Position_Size = (Available_Balance × Max_Loss_Percent) / |Entry - Stop|

Leverage = ⌈(Position_Size × Entry_Price) / Available_Balance⌉

TP_Price = Entry ± (|Entry - Stop| × Risk_Reward)
```

**动态敞口控制**:
- 当前敞口 = Σ(持仓数量 × 入场价)
- 敞口比例 = 当前敞口 / 总余额
- 可用敞口 = max(0, max_total_exposure - 敞口比例)
- 风险金额 = min(基础风险, 可用敞口 × 余额)

---

### 6️⃣ 执行编排层 (ExecutionOrchestrator)

```mermaid
graph TB
    ExecuteSignal[execute_signal] --> CreateIntent[创建 ExecutionIntent]

    CreateIntent --> CircuitBreaker{熔断检查}
    CircuitBreaker -->|已熔断| BlockSignal[拦截信号]
    CircuitBreaker -->|正常| CapitalCheck[资金保护检查]

    CapitalCheck -->|拒绝| BlockReason[记录拒绝原因]
    CapitalCheck -->|通过| CreateOrder[创建本地订单]

    CreateOrder --> SubmitEntry[提交 ENTRY 到交易所]

    SubmitEntry --> EntryStatus{ENTRY 状态}

    EntryStatus -->|FILLED| MountProtection[挂载保护单]
    EntryStatus -->|PARTIALLY_FILLED| WaitPartial[等待后续成交]
    EntryStatus -->|OPEN| WaitFill[等待成交]
    EntryStatus -->|FAILED| RecordFail[记录失败]

    MountProtection --> GenTPSL[生成 TP/SL 订单]
    GenTPSL --> SubmitTP[提交 TP 订单]
    GenTPSL --> SubmitSL[提交 SL 订单]

    SubmitTP --> CheckTP{TP 成功?}
    SubmitSL --> CheckSL{SL 成功?}

    CheckTP -->|是| RecordTP[记录 TP 订单]
    CheckTP -->|否| LogTPError[记录 TP 失败]

    CheckSL -->|是| RecordSL[记录 SL 订单]
    CheckSL -->|否| LogSLError[记录 SL 失败]

    RecordTP --> Complete[执行完成]
    RecordSL --> Complete

    style MountProtection fill:#f8bbd0
    style Complete fill:#c5e1a5
```

**关键状态**:
- **PENDING**: 初始状态
- **SUBMITTED**: 已提交交易所
- **PROTECTING**: ENTRY 成交，正在挂载保护单
- **COMPLETED**: 全部订单成功
- **FAILED**: 执行失败
- **BLOCKED**: 被拦截（资金保护/熔断）

---

### 7️⃣ 撮合引擎层 (MockMatchingEngine)

```mermaid
graph TB
    ReceiveKline[接收 K线数据] --> GetActiveOrders[获取活跃订单列表]

    GetActiveOrders --> SortOrders[按优先级排序订单]
    SortOrders --> DetectConflict{检测 Same-Bar 冲突}

    DetectConflict -->|有冲突| ApplyPolicy[应用冲突策略]
    DetectConflict -->|无冲突| DefaultPriority[默认优先级: SL > TP > ENTRY]

    ApplyPolicy -->|pessimistic| SLFirst[SL 优先]
    ApplyPolicy -->|random| RandomPick[随机决定 TP/SL 优先级]

    SLFirst --> LoopOrders[遍历排序后订单]
    RandomPick --> LoopOrders
    DefaultPriority --> LoopOrders

    LoopOrders --> CheckTrigger{检查触发条件}

    CheckTrigger -->|SL 订单| CheckSLTrigger[检查止损触发]
    CheckTrigger -->|TP 订单| CheckTPTrigger[检查止盈触发]
    CheckTrigger -->|ENTRY 订单| CheckEntryTrigger[检查入场触发]

    CheckSLTrigger -->|触发| ExecuteSL[执行止损成交]
    CheckTPTrigger -->|触发| ExecuteTP[执行止盈成交]
    CheckEntryTrigger -->|触发| ExecuteEntry[执行入场成交]

    ExecuteSL --> UpdatePosition[更新仓位]
    ExecuteTP --> UpdatePosition
    ExecuteEntry --> UpdatePosition

    UpdatePosition --> UpdateAccount[更新账户余额]
    UpdateAccount --> CheckRemaining{还有订单?}

    CheckRemaining -->|是| LoopOrders
    CheckRemaining -->|否| ReturnExecuted[返回已执行订单列表]

    style ExecuteSL fill:#ffcdd2
    style ExecuteTP fill:#c8e6c9
    style ExecuteEntry fill:#e1f5ff
```

**撮合优先级规则**:
| 优先级 | 订单类型 | 说明 |
|--------|----------|------|
| **1 (最高)** | SL (止损) | 防守至上，止损单优先判定 |
| **2 (中等)** | TP (止盈) | 止盈单次优先级 |
| **3 (最低)** | ENTRY (入场) | 入场单最低优先级 |

**Same-Bar 冲突策略**:
- **pessimistic (悲观)**: SL 优先（默认，与旧行为一致）
- **random (随机)**: 随机决定 TP/SL 优先级，可配置 TP 优先概率

**滑点计算**:
```python
# ENTRY 滑点（市价单）
LONG:  exec_price = kline.open × (1 + slippage_rate)
SHORT: exec_price = kline.open × (1 - slippage_rate)

# TP 滑点（限价单）
LONG:  exec_price = tp_price × (1 - tp_slippage_rate)
SHORT: exec_price = tp_price × (1 + tp_slippage_rate)

# SL 滑点（止损单）
LONG:  exec_price = sl_price × (1 - slippage_rate)
SHORT: exec_price = sl_price × (1 + slippage_rate)
```

**盈亏计算**:
```python
# LONG 盈亏
gross_pnl = (exec_price - entry_price) × filled_qty

# SHORT 盈亏
gross_pnl = (entry_price - exec_price) × filled_qty

# 净盈亏
net_pnl = gross_pnl - fee_paid
```

---

### 8️⃣ 订单生命周期管理 (OrderLifecycleService)

```mermaid
graph TB
    CreateOrder[创建订单] --> StateCREATED[状态: CREATED]

    StateCREATED --> SubmitOrder[提交到交易所]
    SubmitOrder --> StateSUBMITTED[状态: SUBMITTED]

    StateSUBMITTED --> ConfirmOrder{交易所确认?}
    ConfirmOrder -->|是| StateOPEN[状态: OPEN]
    ConfirmOrder -->|否| StateREJECTED[状态: REJECTED]

    StateOPEN --> CheckFill{成交检查}
    CheckFill -->|部分成交| StatePARTIALLY_FILLED[状态: PARTIALLY_FILLED]
    CheckFill -->|完全成交| StateFILLED[状态: FILLED]
    CheckFill -->|取消| StateCANCELED[状态: CANCELED]

    StatePARTIALLY_FILLED --> ContinueFill{继续成交?}
    ContinueFill -->|是| StateFILLED
    ContinueFill -->|否| StateCANCELED

    StateFILLED --> OrderComplete[订单完成]
    StateCANCELED --> OrderComplete
    StateREJECTED --> OrderComplete

    style StateCREATED fill:#e1f5ff
    style StateOPEN fill:#fff9c4
    style StateFILLED fill:#c8e6c9
    style StateCANCELED fill:#ffcdd2
    style StateREJECTED fill:#ffcdd2
```

**状态转换规则**:
| 当前状态 | 允许转换 | 触发条件 |
|----------|----------|----------|
| CREATED | SUBMITTED, CANCELED | 提交交易所 / 用户取消 |
| SUBMITTED | OPEN, REJECTED, CANCELED | 交易所确认 / 拒绝 / 超时 |
| OPEN | PARTIALLY_FILLED, FILLED, CANCELED | 部分成交 / 完全成交 / 用户取消 |
| PARTIALLY_FILLED | FILLED, CANCELED | 剩余成交 / 用户取消 |

**审计日志记录**:
- 每次状态转换自动记录审计日志
- 包含：订单 ID、旧状态、新状态、事件类型、触发源、时间戳

---

### 9️⃣ 订单编排管理 (OrderManager)

```mermaid
graph TB
    CreateChain[创建订单链] --> GenEntry[生成 ENTRY 订单]

    GenEntry --> WaitEntryFill[等待 ENTRY 成交]

    WaitEntryFill --> EntryFilled{ENTRY 成交?}
    EntryFilled -->|是| GenTPSL[生成 TP/SL 订单]
    EntryFilled -->|否| WaitEntryFill

    GenTPSL --> CalcTPPrice[计算 TP 价格]
    GenTPSL --> CalcSLPrice[计算 SL 价格]

    CalcTPPrice --> SubmitTP[提交 TP 订单]
    CalcSLPrice --> SubmitSL[提交 SL 订单]

    SubmitTP --> WaitTPFill[等待 TP 成交]
    SubmitSL --> WaitSLFill[等待 SL 成交]

    WaitTPFill --> TPFilled{TP 成交?}
    WaitSLFill --> SLFilled{SL 成交?}

    TPFilled -->|是| ApplyOCO[应用 OCO 逻辑]
    SLFilled -->|是| CancelAllTP[撤销所有 TP 订单]

    ApplyOCO --> CheckPosition{仓位已平?}
    CheckPosition -->|是| CancelRemaining[撤销剩余挂单]
    CheckPosition -->|否| UpdateSL[更新 SL 数量]

    style GenTPSL fill:#f8bbd0
    style ApplyOCO fill:#fff9c4
```

**TP/SL 价格计算**:
```python
# 止损价格（基于入场价和 RR 倍数）
LONG:  sl_price = entry_price × (1 - |rr_multiple| × 0.01)
SHORT: sl_price = entry_price × (1 + |rr_multiple| × 0.01)

# 止盈价格（基于入场价和止损价）
LONG:  tp_price = entry_price + rr_multiple × (entry_price - sl_price)
SHORT: tp_price = entry_price - rr_multiple × (sl_price - entry_price)
```

**OCO (One-Cancels-Other) 逻辑**:
- **TP 成交**:
  - 如果仓位已平（current_qty = 0）: 撤销所有剩余挂单
  - 如果仓位未平: 更新 SL 数量 = current_qty
- **SL 成交**: 撤销所有 TP 订单

---

### 🔟 保护单挂载机制

```mermaid
graph TB
    EntryFilled[ENTRY 成交] --> CheckExisting{已有保护单?}

    CheckExisting -->|无| GenNew[生成新保护单]
    CheckExisting -->|有| CalcDelta[计算增量成交量]

    CalcDelta --> DeltaCheck{delta_qty > 0?}
    DeltaCheck -->|否| Skip[跳过补挂]
    DeltaCheck -->|是| GenDelta[生成增量保护单]

    GenNew --> SubmitAll[提交全部 TP/SL]
    GenDelta --> CheckSL{已有 SL?}

    CheckSL -->|有| CancelOldSL[撤销旧 SL]
    CheckSL -->|无| SubmitDelta[提交增量 TP + 新 SL]

    CancelOldSL --> SubmitNewSL[提交新 SL 覆盖全仓]
    SubmitNewSL --> SubmitDelta

    SubmitAll --> CheckResult{全部成功?}
    SubmitDelta --> CheckResult

    CheckResult -->|是| Protected[仓位已保护]
    CheckResult -->|否| PartialFail[部分失败，记录错误]

    style EntryFilled fill:#e1f5ff
    style Protected fill:#c8e6c9
```

**保护单策略**:
- **TP 订单**: 分批止盈，按 `position_ratio` 分配数量
- **SL 订单**: 单一止损，覆盖全仓
- **增量补挂**: ENTRY 部分成交时，只为新增成交量补挂 TP
- **SL 替换**: 撤销旧 SL，创建新 SL 覆盖全仓

---

## 🔐 资金保护机制 (CapitalProtection)

```mermaid
graph TB
    PreCheck[pre_order_check] --> CheckBalance{余额检查}
    CheckBalance -->|余额不足| RejectBalance[拒绝：余额不足]

    CheckBalance -->|通过| CheckExposure{敞口检查}
    CheckExposure -->|超限| RejectExposure[拒绝：敞口超限]

    CheckExposure -->|通过| CheckDaily{每日限额检查}
    CheckDaily -->|超限| RejectDaily[拒绝：达到每日限额]

    CheckDaily -->|通过| CheckPosition{持仓数量检查}
    CheckPosition -->|超限| RejectPosition[拒绝：持仓过多]

    CheckPosition -->|通过| Allow[允许下单]

    style Allow fill:#c8e6c9
    style RejectBalance fill:#ffcdd2
    style RejectExposure fill:#ffcdd2
    style RejectDaily fill:#ffcdd2
    style RejectPosition fill:#ffcdd2
```

**保护规则**:
| 检查项 | 规则 | 错误码 |
|--------|------|--------|
| **余额检查** | `available_balance >= min_notional` | `INSUFFICIENT_BALANCE` |
| **敞口检查** | `total_exposure <= max_total_exposure` | `EXPOSURE_LIMIT_EXCEEDED` |
| **每日限额** | `daily_orders < max_daily_orders` | `DAILY_LIMIT_EXCEEDED` |
| **持仓数量** | `active_positions < max_positions` | `POSITION_LIMIT_EXCEEDED` |

---

## 🚨 熔断与恢复机制

```mermaid
graph TB
    OrderFailed[订单失败] --> CheckError{错误类型}

    CheckError -->|交易所错误| LogError[记录错误日志]
    CheckError -->|网络错误| Retry[重试机制]

    LogError --> CreateRecoveryTask[创建恢复任务]
    CreateRecoveryTask --> TriggerBreaker[触发熔断]

    TriggerBreaker --> BlockSymbol[拦截该 symbol 新信号]
    BlockSymbol --> Notify[发送告警通知]

    Notify --> ManualFix{人工介入?}
    ManualFix -->|是| ClearBreaker[清除熔断]
    ManualFix -->|否| AutoRecover[自动恢复]

    AutoRecover --> RetryTask[重试恢复任务]
    RetryTask --> CheckSuccess{恢复成功?}

    CheckSuccess -->|是| ClearBreaker
    CheckSuccess -->|否| Notify

    style TriggerBreaker fill:#ffcdd2
    style ClearBreaker fill:#c8e6c9
```

**熔断触发条件**:
- 撤销交易所 SL 订单失败
- 保护单挂载失败
- 连续订单失败次数超限

**恢复机制**:
- **PG 恢复表**: 记录待恢复任务
- **启动重建**: 从 PG 加载活跃恢复任务
- **自动重试**: 定时任务重试失败操作

---

## 📈 性能追踪与监控

```mermaid
graph LR
    SignalFired[信号触发] --> SaveAttempt[保存 SignalAttempt]
    SaveAttempt --> TrackStatus[追踪信号状态]

    TrackStatus --> PendingStatus[PENDING 状态]
    PendingStatus --> ActiveStatus[ACTIVE 状态]

    ActiveStatus --> TPHit{TP 命中?}
    ActiveStatus --> SLHit{SL 命中?}
    ActiveStatus --> Timeout{超时?}

    TPHit --> CompletedStatus[COMPLETED 状态]
    SLHit --> StoppedStatus[STOPPED 状态]
    Timeout --> ExpiredStatus[EXPIRED 状态]

    CompletedStatus --> CalcPerformance[计算绩效]
    StoppedStatus --> CalcPerformance
    ExpiredStatus --> CalcPerformance

    CalcPerformance --> UpdateStats[更新统计指标]
    UpdateStats --> Dashboard[绩效看板]

    style SignalFired fill:#e1f5ff
    style Dashboard fill:#c8e6c9
```

**绩效指标**:
- **胜率**: 盈利信号数 / 总信号数
- **盈亏比**: 平均盈利 / 平均亏损
- **最大回撤**: 历史最高点后的最大跌幅
- **夏普比率**: (收益率 - 无风险利率) / 波动率

---

## 🔧 关键技术细节

### Decimal 精度控制
```python
# ✅ 正确：使用 Decimal 进行金融计算
position_size = risk_amount / stop_distance
price = Decimal("42150.50")

# ❌ 错误：使用 float 导致精度丢失
position_size = float(risk_amount) / float(stop_distance)  # 禁止！
```

### asyncio 并发保护
```python
# 热重载时使用锁保护
async with self._runner_lock:
    self._runner = self._build_and_warmup_runner()
```

### WebSocket 去重机制
```python
# 基于 filled_qty 推进判断，避免重复处理
if filled_qty <= local_filled_qty and status == local_status:
    return None  # 跳过重复推送
```

---

## 📚 相关文档

- [系统架构规范](./arch/系统开发规范与红线.md)
- [v3.0 演进路线图](./v3/v3-evolution-roadmap.md)
- [订单生命周期管理](./arch/order-lifecycle.md)
- [风控系统设计](./arch/risk-management.md)

---

### 🔍 潜在隐患与优化建议

**1. K线驱动与时效性延迟**

- **现状**：流程图显示在 `1️⃣ 交易所数据接入层`，仅处理收盘 K 线（`x=true`）来触发后续流程。
- **隐患**：这意味着系统是一个纯粹的 Bar-On-Close 框架。在极端行情的加密货币市场中，等待 15 分钟或 1 小时线收盘再进场，可能会面临巨大的点差和滑点。
- **建议**：可以考虑在架构中预留“Tick 级内部触发”机制。即 K 线用于更新指标（EMA/ATR），但价格 Tick 变动可以用于内部的动态追踪止损（Trailing Stop）或特定极端形态的提前突破。

**2. 异步执行与数据库瓶颈**

- **现状**：`2️⃣ 信号处理管道` 中提到“异步队列：批量持久化 SignalAttempt，避免阻塞”。
- **隐患**：如果在极端波动下，信号量激增，PG（PostgreSQL）的并发写入可能会造成背压（Backpressure），导致 `DispatchExecutor` 获取信号的延迟。
- **建议**：在 `SendNotify` 和 `PersistSignal` 之间，引入类似 Redis 的内存中间件作为高频交易状态的缓冲，持久化操作可以完全退化为旁路后台任务。

**3. 热重载的锁粒度**

- **现状**：`async with self._runner_lock:` 保护热重载。
- **隐患**：如果在等待锁释放的期间，WebSocket 积压了大量数据包，解锁后可能会引发瞬间的计算洪峰。
- **建议**：可以采用双缓冲（Double Buffering）或指针切换的方式：在后台线程/协程中构建新的 `_runner`，构建完成后，只用原子操作（或极短的锁）切换引用，做到几乎零阻塞。

**4. 固化的信号评分公式**

- **现状**：`score = pattern_ratio * 0.7 + min(atr_ratio, 2.0) * 0.3`。
- **隐患**：这种硬编码的权重在长期回测中容易出现过拟合。
- **建议**：作为 PMS 系统的下一阶段演进，可以将这些权重参数提取到单独的配置文件或动态策略池中，便于后续引入机器学习模型或参数寻优算法来动态调整权重。

*本文档由 Claude Code 自动生成，基于代码分析整理*
