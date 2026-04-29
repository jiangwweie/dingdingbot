# 诊断报告：PMS 回测报告列表全零数据

**报告编号**: DA-20260414-002
**优先级**: 🟠 P1

---

## 问题描述

| 字段 | 内容 |
|------|------|
| 用户报告 | 回测报告列表中所有记录显示：收益率 +0.00%, 胜率 +0.00%, 总盈亏 $0.00, 交易次数 0 |
| 影响范围 | 数据库中全部 10 条回测记录 |
| 核心现象 | `total_trades = 0` → 所有统计指标均为零（连带结果） |

---

## 根因分析

**根因**: 策略 '01' 的过滤器链（EMA trend + ATR + MTF，全部 AND 逻辑）拦截了所有 Pinbar 信号，导致 `SIGNAL_FIRED = 0`，没有 ENTRY 订单被创建，`total_trades` 保持初始值 0。

**触发链**:
```
用户执行 PMS 回测
  → _run_v3_pms_backtest() 遍历 K 线
    → runner.run_all() 运行策略 + 过滤器
      → Pinbar 检测到 34 次（FILTERED）
        → ema_trend 拦截 27 次
        → mtf 拦截 7 次
        → atr 拦截 0 次
      → NO_PATTERN 166 次
      → SIGNAL_FIRED = 0 次 ← 根因
    → 没有 ENTRY 订单创建
    → total_trades = 0（初始值）
    → report 中所有指标为零
    → save_report 写入数据库，值为零
```

**证据**:

1. 数据库验证 — 所有记录 `total_trades=0`, `positions_summary=NULL`:
```
('rpt_unknown_1768262400000_a03e1bd7', 'unknown', 'SOL/USDT:USDT', '15m', 0, '0.0', '0.0', '0.0', '0.0')
('rpt_b9cc3fd1-..._1768320000000_4d960ac2', '01', 'SOL/USDT:USDT', '15m', 0, '0.0', '0.0', '0.0', '0.0')
```

2. 用户策略 '01' 配置（从数据库 `strategy_snapshot` 提取）:
```json
{
  "logic_tree": {
    "gate": "AND",
    "children": [
      { "type": "trigger", "config": { "type": "pinbar", "params": {
        "min_wick_ratio": 0.5, "max_body_ratio": 0.35, "body_position_tolerance": 0.2
      }}},
      { "gate": "AND", "children": [
        { "type": "filter", "config": { "type": "ema_trend", "params": {"period": 60} }},
        { "type": "filter", "config": { "type": "atr", "params": {"period": 14, "min_atr_ratio": 0.5} }},
        { "type": "filter", "config": { "type": "mtf", "params": {} }}
      ]}
    ]
  }
}
```

3. 实际运行验证（200 根 SOL/USDT 15m 真实 K 线数据）:
```
Final result distribution:
  NO_PATTERN: 166   ← Pinbar 形态未检测到
  FILTERED:   34    ← 形态检测到但被过滤器拦截
  SIGNAL_FIRED: 0   ← 零信号触发

Filter failures:
  ema_trend: 27     ← EMA 趋势方向不匹配
  mtf:        7     ← 多周期趋势不一致
```

4. 回测引擎本身正常（验证通过）:
```
使用无 filters 的简化策略:
  total_trades: 12
  win_rate: 58.33%
  total_pnl: 1074.65 USDT
  positions: 12 笔
```

---

## 各场景验证

| 场景 | 是否触发 | 原因 |
|------|---------|------|
| PMS 回测（带 EMA+ATR+MTF filters） | **会触发** | 过滤器全拦截，SIGNAL_FIRED=0 |
| PMS 回测（无 filters，仅 Pinbar） | 不会 | 测试通过：12 笔交易 |
| v2_classic 回测 | 不会 | v2 模式有独立的信号统计逻辑 |
| 回测数据写入 | 不会 | save_report 正确写入 report 对象的值 |
| 回测数据读取 | 不会 | list_reports 正确读取数据库值 |

---

## 结论

**不是 bug，是策略配置问题**。回测引擎、数据写入、数据读取三个环节全部正常。

用户的策略 '01' 配置了三个过滤器（EMA trend period=60、ATR min_atr_ratio=0.5、MTF），全部使用 AND 逻辑。在 SOL/USDT 15m 的 200 根 K 线数据中，**所有 34 个 Pinbar 信号都被过滤器拦截**，导致零交易。

---

## 建议

### 立即操作（用户侧）
1. 临时禁用所有 filters，仅保留 Pinbar trigger，确认回测能产生交易
2. 逐个启用 filters，观察哪些过滤器在拦截信号
3. 调整 EMA period（60 可能过于滞后）或降低 MTF 要求

### 产品改进（方案 B — 推荐）
在 PMSBacktest 页面回测完成后，如果 `total_trades === 0`，增加友好提示：

```
回测完成但无交易记录。可能原因：
1. 策略过滤器过于严格 — 请检查 EMA/MTF/ATR 配置
2. 回测时间范围过短 — 建议至少 500 根 K 线
3. Pinbar 形态参数过于严格 — 检查 min_wick_ratio/max_body_ratio
```

**预估工作量**: 0.5 小时

### 调试增强（方案 C）
在 `_run_v3_pms_backtest` 中添加信号统计日志，回测结束后输出汇总：
```python
logger.info(
    f"Backtest signal summary: "
    f"{signal_count} fired, {filtered_count} filtered, {no_pattern_count} no pattern"
)
```

**预估工作量**: 0.5 小时

---

*诊断完成时间: 2026-04-14*
