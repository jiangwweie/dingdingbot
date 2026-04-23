# Sim-0.3 信号到 testnet 下单链路验证报告

> **验证时间**: 2026-04-23 21:08-21:10
> **验证目标**: 验证 SignalPipeline 能进入 ExecutionOrchestrator，并真实提交 testnet ENTRY
> **启动方式**: `PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py`
> **验证结果**: ⚠️ **未在观察窗口内出现有效信号**

---

## 启动命令

```bash
set -a
source .env
set +a
PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py
```

---

## 观察窗口

- **开始时间**: 2026-04-23 21:08:29
- **结束时间**: 2026-04-23 21:10:20
- **观察时长**: 120 秒（2 分钟）
- **监控 symbols**: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, BNB/USDT:USDT
- **监控 timeframes**: 15m, 1h, 4h, 1d

---

## 验证结果

### ⚠️ 未出现有效 SignalResult

在 120 秒观察窗口内：

- ✅ WebSocket 订阅成功（16 个 symbol/timeframe）
- ✅ K 线数据流正常（系统运行正常）
- ❌ **未触发任何 SignalResult**
- ❌ **未创建 ExecutionIntent**
- ❌ **未提交 testnet ENTRY**

---

## 原因判断

### 可能原因

1. **策略条件较严格**
   - 当前策略：burst_9（pinbar 触发器）
   - Pinbar 形态需要特定的 K 线结构
   - 120 秒窗口内可能未出现符合条件的 K 线

2. **市场条件不满足**
   - 策略可能包含过滤器（如 EMA 趋势过滤）
   - 当前市场状态可能不满足过滤器条件

3. **观察窗口过短**
   - 15m K 线每 15 分钟才闭合一次
   - 120 秒窗口内可能只有 0-1 根 K 线闭合
   - 即使 K 线闭合，也不一定触发信号

### 系统状态确认

- ✅ SignalPipeline 已启动（激活策略数：1）
- ✅ WebSocket 正常订阅
- ✅ 历史数据预热完成（1600 根 K 线）
- ✅ MTF EMA 指标就绪（12 个指标）
- ✅ REST API 服务器正常（http://localhost:8000）

**结论**: 系统运行正常，但策略条件未满足，未触发信号。

---

## 是否建议延长观察

### ✅ 建议延长观察窗口

**建议观察时长**: 至少 **15-30 分钟**

**理由**:
1. 15m K 线每 15 分钟闭合一次，需要等待至少 1-2 根 K 线闭合
2. Pinbar 形态需要特定市场条件，可能需要更长时间等待
3. 延长观察可以更准确判断系统是否能自然触发信号

**延长观察方案**:
```bash
# 启动主程序并观察 30 分钟
set -a && source .env && set +a
PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py
# 观察日志中的 SignalResult / ExecutionIntent 关键字
```

---

## 是否允许进入受控信号注入方案

### ✅ 允许进入受控信号注入方案

**方案建议**: Sim-0.3.1 受控信号注入验证

**目的**: 在不修改主链代码的前提下，验证信号到 testnet ENTRY 的完整链路

**实现方式**:
1. 设计一个最小化的信号注入接口（如 REST API endpoint）
2. 注入一个符合当前策略条件的模拟信号
3. 验证完整链路：SignalPipeline -> ExecutionOrchestrator -> testnet ENTRY
4. 验证后移除注入接口

**优点**:
- 不修改策略逻辑
- 不绕过 SignalPipeline
- 可控验证完整链路
- 避免长时间等待自然信号

**风险**:
- 需要最小化代码改动
- 需要确保注入接口只在 Sim-0 验证期间启用

---

## 是否允许进入 Sim-0.4

### ⚠️ 暂不允许进入 Sim-0.4

**原因**: 未验证信号到 testnet ENTRY 的完整链路

**前置条件**:
1. ✅ Sim-0.2 启动验证通过
2. ❌ Sim-0.3 信号验证未完成（未出现信号）

**下一步建议**:

### 方案 A: 延长观察窗口（推荐）

- 延长观察至 30 分钟
- 等待自然信号触发
- 如果仍无信号，进入方案 B

### 方案 B: 受控信号注入

- 设计最小化信号注入接口
- 验证完整链路
- 验证后移除注入接口

### 方案 C: 调整策略参数（不推荐）

- 降低策略条件（如移除过滤器）
- 增加信号触发概率
- **不推荐**: 违反"不改策略参数"约束

---

## 下一步建议

### 优先级 1: 延长观察窗口

```bash
# 启动主程序并观察 30 分钟
set -a && source .env && set +a
PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py
# 观察日志中的 SignalResult / ExecutionIntent 关键字
```

### 优先级 2: 设计受控信号注入方案

如果延长观察后仍无信号，设计 Sim-0.3.1 受控信号注入验证：

1. 新增 REST API endpoint: `POST /api/inject-signal`
2. 注入一个符合当前策略条件的模拟信号
3. 验证完整链路
4. 验证后移除注入接口

---

**验证人**: Claude Sonnet 4.6
**验证日期**: 2026-04-23