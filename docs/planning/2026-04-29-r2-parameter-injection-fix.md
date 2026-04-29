# R2 参数注入修复与 Sanity Check 计划

> **日期**: 2026-04-29
> **任务**: 修复 R2 脚本参数注入错误，并在全量运行前验证参数是否真正生效

---

## 1. 一句话根因

**R2 脚本错误地将风险参数（`max_loss_percent`, `max_total_exposure`, `max_leverage`）放入 `BacktestRuntimeOverrides`，但该类不包含这些字段，导致参数被静默忽略，所有 168 组配置返回完全相同的结果。**

---

## 2. 旧核心 bug 与本次脚本 bug 的区别

### 2.1 历史 bug 修复回顾

| Commit | Bug 描述 | 修复内容 | 影响范围 |
|--------|---------|---------|---------|
| **cb06ea0** | PMS 回测 `account_snapshot.positions=[]` 导致 `current_exposure_ratio=0` | 新增 `_build_account_snapshot()` 从 `positions_map` 构建真实持仓信息 | **核心代码** (`src/application/backtester.py`) |
| **96f0328** | `risk_calculator.py` exposure constraint 逻辑错误（混淆"风险金额"和"敞口金额"） | 重构为三层独立约束：Risk / Exposure / Leverage | **核心代码** (`src/domain/risk_calculator.py`) |
| **44e9694** | Backtester 未消费 `request.risk_overrides`，硬编码默认值 | 新增 `_build_risk_config()` 统一消费 `request.risk_overrides` | **核心代码** (`src/application/backtester.py`) |

### 2.2 本次脚本 bug

| Bug 描述 | 根因 | 影响范围 |
|---------|------|---------|
| **R2 脚本所有 168 组结果完全相同** | 使用 `BacktestRuntimeOverrides` 传递风险参数，但该类不包含 `max_loss_percent` 等字段 | **研究脚本** (`scripts/run_r2_capital_allocation_search.py`) |

### 2.3 关键区别

- **历史 bug**: 核心代码逻辑错误，影响所有回测
- **本次 bug**: 脚本层参数注入错误，核心代码已修复，只是未正确调用

**结论**: 核心代码已正确实现三层独立约束 + risk_overrides 消费，本次只需修复脚本层参数注入。

---

## 3. 修复后的关键代码片段

### 3.1 错误写法（修复前）

```python
# ❌ 错误：BacktestRuntimeOverrides 不包含风险参数字段
runtime_overrides = BacktestRuntimeOverrides(
    max_loss_percent=Decimal(str(risk)),      # ❌ 字段不存在！
    max_total_exposure=Decimal(str(exposure)), # ❌ 字段不存在！
    max_leverage=20,                           # ❌ 字段不存在！
    fee_rate=BNB9_FEE_RATE,
    slippage_rate=BNB9_SLIPPAGE,
    initial_balance=Decimal("10000.0"),
)

request = BacktestRequest(
    symbol=symbol,
    timeframe=timeframe,
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    # ❌ 未传递 risk_overrides
)
```

### 3.2 正确写法（修复后）

```python
# ✅ 修复：使用 RiskConfig 传递风险参数
from src.domain.models import RiskConfig

risk_overrides = RiskConfig(
    max_loss_percent=Decimal(str(risk)),
    max_total_exposure=Decimal(str(exposure)),
    max_leverage=20,
    daily_max_trades=50,
)

# ✅ runtime_overrides 只保留策略/订单/成本参数
runtime_overrides = BacktestRuntimeOverrides(
    allowed_directions=["LONG"],
    fee_rate=BNB9_FEE_RATE,
    slippage_rate=BNB9_SLIPPAGE,
    tp_slippage_rate=Decimal("0"),
)

# ✅ 创建 BacktestRequest（风险参数通过 risk_overrides 传递）
request = BacktestRequest(
    symbol=symbol,
    timeframe=timeframe,
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    risk_overrides=risk_overrides,  # ✅ 正确传递
)
```

### 3.3 参数传递链路

```
脚本层:
  risk_overrides = RiskConfig(max_loss_percent=..., max_total_exposure=..., ...)
  ↓
  request = BacktestRequest(risk_overrides=risk_overrides)
  ↓
核心层 (backtester.py):
  risk_config = self._build_risk_config(request)  # 44e9694 修复
  ↓
  account_snapshot = self._build_account_snapshot(..., positions_map)  # cb06ea0 修复
  ↓
风控层 (risk_calculator.py):
  position_size = min(
      risk_based_position,      # 风险约束
      exposure_based_position,  # 敞口约束 (96f0328 修复)
      leverage_based_position   # 杠杆约束
  )
```

---

## 4. 2023 四组 Sanity Check 计划

### 4.1 配置矩阵

| 组别 | Exposure | Risk | 预期变化 |
|------|----------|------|---------|
| 1 | 1.0 | 0.5% | 基准组 |
| 2 | 1.0 | 2.0% | Risk ↑ → PnL ↑, MaxDD ↑ |
| 3 | 3.0 | 0.5% | Exposure ↑ → Trades ↑, PnL ↑ |
| 4 | 3.0 | 2.0% | Risk + Exposure 双高 |

### 4.2 执行流程

```bash
# 运行 sanity check
python scripts/run_r2_sanity_check.py
```

**输出内容**:
- 参数注入证据：`risk_overrides.max_loss_percent`, `max_total_exposure`, `max_leverage`
- 回测结果：PnL, MaxDD, Trades, WinRate
- Debug 信息：`debug_curve_max_dd`

---

## 5. 哪些指标必须变化，才能证明参数生效

### 5.1 Risk 参数生效证据

**验证方法**: 对比组 1 vs 组 2（exposure 相同，risk 不同）

| 指标 | 组 1 (risk=0.5%) | 组 2 (risk=2.0%) | 预期变化 |
|------|------------------|------------------|---------|
| **PnL** | - | - | **↑ 显著增加**（风险预算 ↑） |
| **MaxDD** | - | - | **↑ 增加**（单笔损失 ↑） |
| **Trades** | - | - | 可能相同（取决于信号数量） |
| **Position Size** | - | - | **↑ 增加**（单笔仓位 ↑） |

**判定标准**: `abs(PnL_组2 - PnL_组1) > 100 USDT`

### 5.2 Exposure 参数生效证据

**验证方法**: 对比组 1 vs 组 3（risk 相同，exposure 不同）

| 指标 | 组 1 (exposure=1.0) | 组 3 (exposure=3.0) | 预期变化 |
|------|---------------------|---------------------|---------|
| **PnL** | - | - | **↑ 增加**（可开仓数 ↑） |
| **Trades** | - | - | **↑ 增加**（敞口空间 ↑） |
| **MaxDD** | - | - | 可能增加（持仓数 ↑） |
| **Position Count** | - | - | **↑ 增加**（同时持仓数 ↑） |

**判定标准**: `abs(PnL_组3 - PnL_组1) > 100 USDT` 或 `abs(Trades_组3 - Trades_组1) > 5`

### 5.3 结果多样性检查

**判定标准**:
- PnL 唯一值数量 ≥ 2
- MaxDD 唯一值数量 ≥ 2
- Trades 唯一值数量 ≥ 2

**如果 4 组结果完全相同**:
- ❌ 参数注入仍有问题
- ❌ 立即停止，不要继续全量运行

---

## 6. 等待确认后再运行

### 6.1 Sanity Check 输出示例

```json
{
  "sanity_check_date": "2026-04-29T...",
  "sanity_check_type": "R2_parameter_injection_audit",
  "cost_config": "BNB9",
  "results": [
    {
      "exposure": 1.0,
      "risk": 0.005,
      "pnl": -1234.56,
      "max_dd": 0.23,
      "trades": 45,
      "risk_overrides_max_loss_percent": 0.005,
      "risk_overrides_max_total_exposure": 1.0
    },
    ...
  ],
  "validation": {
    "valid": true,
    "pnl_variance": 4,
    "risk_pnl_diff": 567.89,
    "exposure_pnl_diff": 890.12
  }
}
```

### 6.2 后续行动

**如果 sanity check 通过**:
1. ✅ 参数注入修复成功
2. ✅ 可以继续全量运行 R2 搜索（168 组）
3. ✅ 生成年度最优配置报告

**如果 sanity check 失败**:
1. ❌ 停止并汇报
2. ❌ 检查核心代码是否正确消费 `risk_overrides`
3. ❌ 检查 `_build_account_snapshot()` 是否正确构建持仓信息
4. ❌ 检查 `risk_calculator.py` 三层约束是否正确实现

---

## 7. 代码证据链（确认旧 bug 未回归）

### 7.1 AccountSnapshot 包含真实 positions

**代码路径**: `src/application/backtester.py:412-449`

```python
def _build_account_snapshot(
    self,
    account: Account,
    positions_map: Dict[str, Position],
    timestamp: int,
) -> AccountSnapshot:
    """从 positions_map 构建 AccountSnapshot，包含真实持仓信息。"""
    position_infos = []
    for pos in positions_map.values():
        if not pos.is_closed and pos.current_qty > Decimal('0'):
            position_infos.append(PositionInfo(...))

    return AccountSnapshot(
        total_balance=account.total_balance,
        available_balance=account.available_balance,
        positions=position_infos,  # ✅ 真实持仓
        ...
    )
```

**调用位置**: `backtester.py:1978`

```python
account_snapshot = self._build_account_snapshot(account, positions_map, timestamp)
```

### 7.2 RiskCalculator 消费 account.positions

**代码路径**: `src/domain/risk_calculator.py` (96f0328 修复后)

```python
# Step 2: 敞口约束 → 限制总仓位
total_position_value = sum(
    pos.size * pos.entry_price for pos in account.positions  # ✅ 消费真实持仓
)
remaining_exposure_value = max(
    0,
    account.total_balance * max_total_exposure - total_position_value
)
exposure_based_position = remaining_exposure_value / entry_price
```

### 7.3 Backtester 消费 request.risk_overrides

**代码路径**: `src/application/backtester.py:400-410`

```python
def _build_risk_config(self, request: BacktestRequest) -> RiskConfig:
    """从 request.risk_overrides 构建 RiskConfig。"""
    if request.risk_overrides is not None:
        return request.risk_overrides  # ✅ 消费 risk_overrides
    return RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_leverage=20,
    )
```

**调用位置**: `backtester.py:597, 769, 1396, 1613`

---

## 8. 总结

### 8.1 修复内容

- ✅ 脚本层参数注入修复（使用 `RiskConfig` 而非 `BacktestRuntimeOverrides`）
- ✅ 增加"参数生效证据"输出
- ✅ Sanity check 验证流程（2023 年 4 组）
- ✅ 结果多样性检查（防止所有结果相同）

### 8.2 验证标准

- ✅ Risk 参数生效：`abs(PnL_组2 - PnL_组1) > 100 USDT`
- ✅ Exposure 参数生效：`abs(PnL_组3 - PnL_组1) > 100 USDT` 或 `abs(Trades_组3 - Trades_组1) > 5`
- ✅ 结果多样性：PnL/MaxDD/Trades 唯一值数量 ≥ 2

### 8.3 下一步

**等待用户确认后再运行全量搜索**。

---

*修复计划生成时间: 2026-04-29*
*修复脚本: `scripts/run_r2_sanity_check.py`*
*验证报告: `docs/planning/2026-04-29-r2-parameter-injection-fix.md`*