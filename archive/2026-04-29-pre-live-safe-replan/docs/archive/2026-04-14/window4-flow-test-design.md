# Window 4: 全链路业务流程测试设计

**创建日期**: 2026-03-31
**测试类型**: End-to-End Business Flow Test
**执行环境**: Binance Testnet + 模拟 K 线

---

## 🎯 测试目标

验证从**信号输入**到**订单成交**再到**平仓退出**的完整业务闭环，确保各组件协作正确。

---

## 📋 关键链路节点清单

### 节点 1: 模拟 K 线数据输入

**目的**: 构造能触发 Pinbar 形态的 K 线序列

**预期行为**:
```python
# 构造看涨 Pinbar 的 K 线数据
kline = KlineData(
    symbol="BTC/USDT:USDT",
    timeframe="15m",
    timestamp=1234567890000,
    open=Decimal("100000"),
    high=Decimal("100500"),
    low=Decimal("98000"),   # 长下影线
    close=Decimal("100400"), # 收盘价接近高点
    volume=Decimal("1000"),
    is_closed=True
)
```

**验证点**:
- [ ] K 线数据格式正确
- [ ] 影线长度满足 Pinbar 条件（下影线 ≥ 60% 总长度）
- [ ] 实体位置在顶部（看涨 Pinbar）

**预期结果**: K 线数据通过验证，输入到 SignalPipeline

---

### 节点 2: SignalPipeline 接收 K 线

**目的**: 验证管道正确接收并预处理 K 线数据

**预期行为**:
```python
# SignalPipeline 内部处理
# 1. 将 K 线添加到历史缓存
# 2. 更新 MTF EMA 指标
# 3. 准备传递给策略引擎
```

**验证点**:
- [ ] K 线历史缓存已更新
- [ ] MTF EMA 指标已计算
- [ ] 无异常抛出

**预期结果**: K 线数据成功进入管道，无错误

---

### 节点 3: 策略引擎执行（形态检测）

**目的**: 验证 Pinbar 形态被正确识别

**预期行为**:
```python
# Pinbar 检测逻辑
wick_length = min(open, close) - low  # 下影线长度
body_length = abs(close - open)        # 实体长度
total_length = high - low              # 总长度

# 看涨 Pinbar 条件
assert wick_length / total_length >= 0.6  # 下影线 ≥ 60%
assert body_length / total_length <= 0.3  # 实体 ≤ 30%
assert (high - min(open, close)) / total_length <= 0.1  # 上影线 ≤ 10%
```

**验证点**:
- [ ] Pinbar 形态被识别
- [ ] 信号方向正确（LONG）
- [ ] 形态质量评分 > 0.5

**预期结果**: 生成 `SignalResult`，包含：
- direction: LONG
- entry_price: 100400
- suggested_stop_loss: 98000
- suggested_position_size: 待计算
- tags: [{"name": "Pinbar", "value": "Bullish"}]

---

### 节点 4: 风控计算（止损 + 仓位）

**目的**: 验证止损价格和仓位计算正确

**预期行为**:
```python
# RiskCalculator 计算
entry_price = Decimal("100400")
stop_loss = Decimal("98000")  # Pinbar 低点
balance = Decimal("5000")     # 账户余额
max_loss_percent = Decimal("0.02")  # 2% 单笔最大损失

# 止损距离
stop_distance = abs(entry_price - stop_loss) / entry_price  # ≈ 2.39%

# 仓位数量
risk_amount = balance * max_loss_percent  # 100 USDT
position_size = risk_amount / stop_distance  # ≈ 0.00418 BTC
```

**验证点**:
- [ ] 止损价格 = Pinbar 低点
- [ ] 仓位大小符合 2% 风险限制
- [ ] 使用 Decimal 精度计算

**预期结果**: 
- stop_loss: 98000
- position_size: ≈ 0.00418 BTC
- leverage: 1x（默认）

---

### 节点 5: 资金保护检查（下单前）

**目的**: 验证 CapitalProtectionManager 正确执行资金检查

**预期行为**:
```python
# 检查项清单
checks = [
    ("单笔损失", loss_usdt / balance < 0.02),      # < 2%
    ("单次仓位", position_value / balance < 0.20), # < 20%
    ("每日损失", daily_pnl / balance > -0.05),     # > -5%
    ("交易次数", trade_count < 50),                # < 50 次
    ("最低余额", balance > 100),                   # > 100 USDT
]
```

**验证点**:
- [ ] 所有检查项通过
- [ ] 无 CapitalProtectionError 抛出
- [ ] 检查日志记录完整

**预期结果**: 所有检查通过，允许下单

---

### 节点 6: OrderManager 创建订单链

**目的**: 验证订单链正确创建

**预期行为**:
```python
# 创建订单链（仅 ENTRY 订单）
entry_order = Order(
    id="ord_xxx",
    signal_id="sig_xxx",
    symbol="BTC/USDT:USDT",
    direction=Direction.LONG,
    order_type=OrderType.MARKET,
    order_role=OrderRole.ENTRY,
    requested_qty=Decimal("0.00418"),
    status=OrderStatus.OPEN,
    reduce_only=False
)
```

**验证点**:
- [ ] ENTRY 订单创建成功
- [ ] 订单参数正确（数量、方向、类型）
- [ ] TP/SL 订单未立即创建（等待成交后动态生成）

**预期结果**: 返回仅包含 ENTRY 订单的订单链

---

### 节点 7: ExchangeGateway 执行订单

**目的**: 验证订单正确提交到 Binance Testnet

**预期行为**:
```python
# 调用交易所 API
result = await gateway.place_order(
    symbol="BTC/USDT:USDT",
    order_type="market",
    side="buy",
    amount=Decimal("0.00418"),
    reduce_only=False
)
```

**验证点**:
- [ ] 订单提交成功
- [ ] 获得交易所订单 ID
- [ ] 订单状态为 FILLED 或 OPEN

**预期结果**: 
- order_id: 系统 UUID
- exchange_order_id: Binance 订单 ID
- status: FILLED（市价单通常立即成交）

---

### 节点 8: 订单成交回报处理

**目的**: 验证订单成交后正确处理

**预期行为**:
```python
# 订单成交回调
# 1. 更新订单状态为 FILLED
# 2. 记录成交价格（可能有滑点）
# 3. 触发 TP/SL 订单生成
```

**验证点**:
- [ ] 订单状态更新为 FILLED
- [ ] 平均成交价格已记录
- [ ] TP/SL 订单开始生成

**预期结果**: 
- filled_order.average_exec_price: 实际成交价
- TP/SL 订单已创建并挂出

---

### 节点 9: PositionManager 更新持仓

**目的**: 验证持仓正确创建/更新

**预期行为**:
```python
# 持仓更新逻辑
# 1. 检查是否已有持仓
# 2. 如有同向持仓 → 增加仓位
# 3. 如无反向持仓 → 新建仓位
# 4. 计算平均开仓价
```

**验证点**:
- [ ] 仓位记录已创建
- [ ] 平均开仓价正确
- [ ] 仓位 ID 与订单关联

**预期结果**:
- position_id: 新仓位 ID
- entry_price: 平均开仓价
- quantity: 持仓数量

---

### 节点 10: 飞书告警推送

**目的**: 验证订单事件触发告警通知

**预期行为**:
```python
# 发送成交通知
await notifier.send_order_filled(
    order=filled_order,
    pnl=Decimal("0")  # 刚开仓，暂无盈亏
)
```

**验证点**:
- [ ] 飞书 Webhook 调用成功
- [ ] 消息格式正确
- [ ] 包含关键信息（币种、方向、数量、价格）

**预期结果**: 飞书收到订单成交通知

---

### 节点 11: 信号持久化

**目的**: 验证信号结果正确存入数据库

**预期行为**:
```python
# 信号入库
await repository.save_signal(
    signal_id="sig_xxx",
    symbol="BTC/USDT:USDT",
    direction="LONG",
    status="TRIGGERED",
    ...
)
```

**验证点**:
- [ ] 信号记录已创建
- [ ] 状态更新为 TRIGGERED
- [ ] 与订单 ID 关联

**预期结果**: 数据库中可查询到信号记录

---

## 📊 验证检查清单

| 节点 | 验证内容 | 验证方式 | 预期结果 |
|------|----------|----------|----------|
| 1 | K 线数据构造 | 断言检查 | 符合 Pinbar 条件 |
| 2 | 管道接收 | 无异常抛出 | 成功进入管道 |
| 3 | 形态检测 | SignalResult 非空 | 检测到 Pinbar |
| 4 | 风控计算 | 断言止损/仓位值 | 计算正确 |
| 5 | 资金保护 | 无异常抛出 | 检查通过 |
| 6 | 订单链创建 | 断言订单数量 | ENTRY 订单创建成功 |
| 7 | 订单执行 | 断言 is_success | 订单提交成功 |
| 8 | 成交回报 | 断言状态=FILLED | 订单成交处理完成 |
| 9 | 持仓更新 | 查询持仓记录 | 持仓已创建 |
| 10 | 飞书告警 | 断言发送成功 | 通知已推送 |
| 11 | 信号入库 | 查询数据库 | 信号记录存在 |

---

## 🛠️ 实现方案

### Mock 策略

由于 `CapitalProtectionManager` 依赖 `AccountService`，我们将：
1. **Mock AccountService**: 提供假的账户余额和持仓数据
2. **Mock Notifier**: 捕获告警调用，验证参数
3. **真实 ExchangeGateway**: 连接 Binance Testnet 执行真实订单

### 测试数据结构

```python
@dataclass
class FlowTestResult:
    """全链路测试结果"""
    node_name: str
    expected: str
    actual: str
    passed: bool
    details: Dict[str, Any]
```

---

## 📝 测试报告模板

```markdown
### 节点 X: [节点名称]

**预期**: [预期行为描述]
**实际**: [实际执行结果]
**状态**: ✅ PASS / ❌ FAIL

**详情**:
- 关键数据: [...]
- 差异分析: [...]
```

---

*Window 4 全链路业务流程测试设计 v1.0*
