---
title: P2_3_CANONICAL_EXIT_ATTRIBUTION_DESIGN
status: IMPLEMENTED
date: 2026-08-16
phase: P2.3
---

# P2.3 Canonical Exit Attribution

## 已知事实

**`ExitRequested.reason`** 是正常退出的持久化起因；**Review** 仅在外部平仓成交明细缺失时提供补充事实。此前 Ticket 列表、因果页、策略统计和前端各自解释字符串，未知原因会显示为“技术原因待查看”。

## 决策

新增纯应用层 **`exit_attribution.py`**：

1. 只把已持久化的原因代码映射为 Owner 可读标签。
2. **Owner 平仓**、**部署 Drain** 使用前缀精确分类为受控退出。
3. 未知原因保留原代码，以“系统请求退出（code）”展示，不猜测市场或策略原因。
4. Ticket 因果页、策略受控退出筛选与前端文案均复用该事实分类；不改变生命周期、命令或 Review 数据。

## 边界

该能力不写 PostgreSQL、不创建 Exchange Command、不修改策略退出逻辑。退出的唯一执行链仍为：

```text
Lifecycle -> ExitRequested -> durable Exchange Command -> reconciliation -> settlement -> review
```
