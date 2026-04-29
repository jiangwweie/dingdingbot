# 回测敞口限制问题记录

> **发现时间**: 2026-04-22
> **状态**: 待修复

## 问题描述

### 现象
黄金回测中 9 个信号被跳过，日志显示：
```
positions=1, total_value=32103.99, balance=10551.40, ratio=3.0426, max=0.8, available=0
[RISK_CALC] position_size=0: risk_amount <= 0
[BACKTEST_SKIP] 跳过信号 sig_xxx：position_size=0
```

### 根因
`max_total_exposure=0.8` (80%) 的设计假设持仓价值 ≤ 账户余额，但合约回测使用杠杆：

| 指标 | 值 |
|------|-----|
| 持仓名义价值 | 32,103 USDT |
| 账户余额 | 10,551 USDT |
| 敞口比例 | 304% |
| 限制 | 80% |
| 结果 | 新信号被阻止 |

### 触发链
```
杠杆仓位 → total_position_value = 32K (名义价值)
         → ratio = 32K / 10.5K = 304%
         → ratio > max_total_exposure (80%)
         → available_exposure = 0
         → position_size = 0
         → 信号被跳过
```

## 设计问题

| 维度 | 预期模型 | 实际模型 |
|------|---------|---------|
| 持仓价值 | ≤ 账户余额 × 80% | 账户余额 × 300%+ |
| 敞口限制 | 80% 无杠杆 | 杠杆仓位不受此限制 |
| 计算方式 | 名义价值 / 余额 | 应该用保证金 / 余额 |

## 待验证修复方案

### 方案 A: 调整敞口限制
```python
max_total_exposure = Decimal("2.5")  # 250%，允许杠杆
```

### 方案 B: 改用保证金口径
```python
margin_used = sum(pos.size * pos.entry_price / pos.leverage for pos in positions)
exposure_ratio = margin_used / balance
```

### 方案 C: 移除敞口限制
```python
max_total_exposure = Decimal("20")  # 基本不限制
```

## 其他缺失风控参数

| 风控维度 | 当前状态 | 实盘必要性 |
|---------|---------|-----------|
| 多笔持仓限制 | ❌ 未配置 | 防止风险集中 |
| 单笔持仓时间 | ❌ 未配置 | 防止资金占用过长 |
| 每日最大交易次数 | ❌ 未配置 | 防止过度交易 |
| 每日最大亏损 | ❌ 未配置 | 熔断保护 |

## 下一步

1. 先用 `max_total_exposure=2.5, max_loss_percent=5%` 跑 ETH 回测验证
2. 根据回测结果决定最终方案
