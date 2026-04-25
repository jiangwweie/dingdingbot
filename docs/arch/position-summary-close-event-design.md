---
name: PositionSummary 一对多出场事件设计
description: PMS 回测报告中 PositionSummary 采用一对多事件列表记录每次出场，替代固定字段方案，支持任意级别止盈止损
type: feedback
---

# 架构决策：PositionSummary 一对多出场事件设计

**决策日期**: 2026-04-14
**问题编号**: P0-1 部分平仓 PnL 归因

## 背景

当前 `PositionSummary` 只有单一 `exit_price` 和累计 `realized_pnl`，导致：
- 部分平仓场景下，exit_price < entry_price 但 realized_pnl > 0，看起来矛盾
- 无法区分 TP1/SL 各自盈亏
- 无法还原出场路径和时间序列
- 无法追溯父子订单关系

## 方案否决

**方案 A（固定字段）**：新增 tp1_pnl/sl_pnl/tp1_exit_price/sl_exit_price
- 否决理由：加 TP2 就要加字段，无限扩展，死胡同

## 选中方案：一对多事件列表

借鉴 `signal_take_profits` 表的一对多设计思路，将出场记录改为事件列表：

```python
class PositionCloseEvent(FinancialModel):
    """单次出场事件"""
    position_id: str           # 关联仓位
    order_id: str              # 关联订单（保留父子关系）
    event_type: str            # TP1/TP2/TP3/SL/TRAILING/MANUAL
    close_price: Decimal       # 实际成交价
    close_qty: Decimal         # 平仓数量
    close_pnl: Decimal         # 实际盈亏
    close_fee: Decimal         # 手续费
    close_time: int            # 时间戳（支持时间序列）
    exit_reason: str
    original_sl_price: Optional[Decimal]   # 原始止损价
    modified_sl_price: Optional[Decimal]   # 修改后止损价

class PositionSummary(FinancialModel):
    close_events: List[PositionCloseEvent]  # 动态列表，支持任意级别
    
    @property
    def realized_pnl(self) -> Decimal:
        return sum(e.close_pnl for e in self.close_events)
```

## 设计考量

| 维度 | 解决方案 |
|------|---------|
| 盈亏归因 | 每次出场独立 PnL |
| 时间序列 | close_time 时间戳 |
| 父子关系 | order_id 关联订单 |
| 仓位比例 | close_qty 占总仓位比例 |
| 扩展性 | 列表支持任意级别 |
| 存储方式 | JSON 序列化，无需 DB 迁移 |

## 关联影响

| 模块 | 影响 | 风险 |
|------|------|------|
| src/domain/models.py | 新增 PositionCloseEvent 模型 | P0 |
| src/application/backtester.py | 记录出场事件逻辑 | P0 |
| src/infrastructure/backtest_repository.py | 序列化支持嵌套列表 | P0 |
| gemimi-web-front/src/lib/api.ts | TS 接口新增 | P1 |
| BacktestReportDetailModal.tsx | 前端事件列表渲染 | P1 |

## 备注

- PositionSummary 是 JSON 存储在 backtest_reports 表中，不需要数据库迁移
- 设计风格与已有的 signal_take_profits 表保持一致
- 后续再写详细设计文档
