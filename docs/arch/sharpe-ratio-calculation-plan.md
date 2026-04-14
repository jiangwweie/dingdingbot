# ADR: 夏普比率（Sharpe Ratio）计算方案

**编号**: ADR-2026-0414-SR01
**状态**: 待用户确认
**作者**: Backend Developer
**创建日期**: 2026-04-14
**关联 Issue**: Task #2 (Bug2 设计)

---

## 1. 问题定义

### 1.1 现状

回测引擎 `src/application/backtester.py:1472` 硬编码 `sharpe_ratio=None`，所有 PMSBacktestReport 的夏普比率字段始终返回 `null`。前端检测为 null 时显示 "N/A"。

```python
# backtester.py:1472
report = PMSBacktestReport(
    ...
    sharpe_ratio=None,  # 硬编码，始终为 None
    ...
)
```

### 1.2 夏普比率的回测意义

| 维度 | 说明 |
|------|------|
| **定义** | 每承担一单位风险所获得的超额收益 |
| **公式** | `Sharpe = E[Rp - Rf] / σ(Rp - Rf)` |
| **解读** | >1 优秀、>1.5 良好、<0 亏损、<1 风险调整收益不足 |
| **回测价值** | 单纯看总盈亏无法评估策略的风险收益比，夏普比率为策略质量提供量化标尺 |
| **缺失影响** | 用户无法比较不同策略的风险调整收益，回测报告可信度降低 |

### 1.3 当前数据可用性

从 `backtester.py` 的主循环可知，回测引擎已收集以下数据：

| 数据项 | 位置 | 可用于夏普 |
|--------|------|-----------|
| `position_summaries` (List[PositionSummary]) | 每笔交易平仓时记录 | ✅ 包含 realized_pnl |
| `total_pnl` (累计) | 每笔交易后累加 | ✅ 可用于逐笔序列 |
| `klines` (K线序列) | 回测输入 | ✅ 可用于构建权益曲线 |
| `account.total_balance` | 每个 K 线更新 | ✅ 可用于权益曲线 |

---

## 2. 方案对比

### 方案 A: 基于逐笔 realized_pnl 计算（经典夏普）

**核心思路**: 将每笔已平仓交易的 `realized_pnl` 视为单期收益，计算收益率序列的均值/标准差比。

**公式**:
```
对于 N 笔已平仓交易:
  R_i = position_i.realized_pnl / initial_balance    # 单笔收益率
  mean_R = Σ R_i / N                                  # 平均收益率
  σ_R = sqrt(Σ(R_i - mean_R)² / (N - 1))             # 样本标准差
  Sharpe_per_period = mean_R / σ_R                    # 周期夏普
  Sharpe_annualized = Sharpe_per_period × sqrt(annual_periods)
```

**年化方法**:
```
# 根据回测时间跨度和交易频率确定年化因子
total_ms = backtest_end - backtest_start
total_days = Decimal(total_ms) / (1000 × 60 × 60 × 24)
# 年化因子 = sqrt(365 / total_days × N)
# 简化: 假设交易日均匀分布
annualization_factor = sqrt(N × 365 / total_days)
```

**数据采集方式**:
```python
# 在 backtester.py 主循环中，当 position.is_closed 时收集
pnl_series: List[Decimal] = []
# 在现有的 position 关闭逻辑处添加:
if position.is_closed:
    pnl_series.append(position.realized_pnl)
```

**适用场景**:
- 交易笔数充足（>= 20 笔）
- 交易间隔相对均匀
- 关注单笔交易的风险收益质量

**优点**:
1. 公式经典，业界标准，易于理解
2. 数据来源简单，直接从已有的 `position.realized_pnl` 提取
3. 不依赖权益曲线的连续性，对交易频率不敏感
4. 能反映策略单笔交易的风险调整表现

**缺点**:
1. **假设交易间隔均匀** -- 实际交易中可能密集开平仓，导致年化失真
2. **持仓时长不敏感** -- 一笔持仓 1 天和持仓 30 天的 pnl 权重相同
3. 交易笔数较少时（< 10 笔），标准差估计不稳定
4. 无法捕捉持仓期间的浮亏波动（仅关注已实现盈亏）

**预估工作量**: 1 小时

---

### 方案 B: 基于权益曲线收益率计算（近似夏普）

**核心思路**: 在每个 K 线时间点记录权益值（`account.total_balance`），构建权益曲线，计算逐期收益率序列的夏普比率。

**公式**:
```
对于每个 K 线时间点 t:
  E_t = account.total_balance at time t               # 权益值
  R_t = (E_t - E_{t-1}) / E_{t-1}                     # 逐期收益率
  mean_R = Σ R_t / T                                   # 平均收益率
  σ_R = sqrt(Σ(R_t - mean_R)² / (T - 1))              # 样本标准差
  Sharpe_per_bar = mean_R / σ_R
  Sharpe_annualized = Sharpe_per_bar × sqrt(bars_per_year)
```

**年化方法**:
```
# 根据 K 线周期确定 bars_per_year
bars_per_year = {
    "15m": 365 × 24 × 4,   # 35,040 根
    "1h":  365 × 24,        # 8,760 根
    "4h":  365 × 6,         # 2,190 根
    "1d":  365,              # 365 根
    "1w":  52,               # 52 根
}
annualization_factor = sqrt(bars_per_year[timeframe])
```

**数据采集方式**:
```python
# 在 backtester.py 主循环中，每个 K 线记录权益
equity_curve: List[Tuple[int, Decimal]] = []  # [(timestamp, equity), ...]
for kline in klines:
    # ... 撮合引擎执行后 ...
    equity_curve.append((kline.timestamp, account.total_balance))
```

**适用场景**:
- 关注策略在时间维度上的整体波动
- 需要对比不同策略的风险收益特征曲线
- 交易频率不均匀或极低频策略

**优点**:
1. **捕捉持仓期间的波动** -- 不仅看已实现盈亏，也反映浮盈浮亏
2. **时间权重合理** -- 每个 K 线周期权重相等，不受交易频率影响
3. 数据点充足（N 根 K 线 = N 个数据点），统计稳定性好
4. 可直接绘制权益曲线图供前端展示
5. 业界量化平台（QuantConnect、Backtrader）的标准做法

**缺点**:
1. **需要改动主循环** -- 每个 K 线周期都要记录权益值
2. 权益值包含浮盈浮亏，可能高估实际风险（用户只能获取已实现盈亏）
3. 需要额外的存储空间（权益曲线数据量 = K 线数量）
4. 对于极高频策略（15m 周期回测 1 年 = 35,040 个数据点），计算量较大

**预估工作量**: 2 小时

---

## 3. 方案对比总结

| 维度 | 方案 A (逐笔 PnL) | 方案 B (权益曲线) |
|------|-------------------|-------------------|
| **数据精度** | 仅已实现盈亏 | 含浮盈浮亏的完整权益 |
| **数据点数量** | 交易笔数 N | K 线数量 T |
| **统计稳定性** | N 小时需 >= 20 笔 | T 通常 > 500，稳定 |
| **年化准确性** | 依赖均匀间隔假设 | 基于固定 K 线周期，准确 |
| **实现复杂度** | 低（收集 pnl 数组） | 中（记录权益曲线） |
| **前端可复用** | 仅返回 Sharpe 值 | 可返回权益曲线数据 |
| **行业标准** | 经典做法 | 量化平台主流做法 |

---

## 4. 推荐方案

**推荐: 方案 B (权益曲线)**

**理由**:

1. **统计稳定性更好**: 回测通常有数百到数千根 K 线，数据点充足。而策略可能只有 5-10 笔交易，方案 A 在小样本下标准差估计极不稳定。

2. **年化因子准确**: K 线周期固定（如 1h），年化因子 `sqrt(8760)` 是精确的。方案 A 依赖交易间隔均匀的假设，实际交易中密集开平仓会导致年化严重失真。

3. **信息量更大**: 权益曲线数据可以同时用于夏普比率计算和前端权益曲线图展示，一举两得。

4. **符合行业标准**: QuantConnect、Backtrader 等量化平台均使用权益曲线法计算夏普比率。

5. **实现成本可控**: 只需在主循环中添加一行 `equity_curve.append(...)`，计算逻辑放在报告生成阶段，不增加主循环负担。

---

## 5. 实施计划

### 5.1 需要修改的文件

| 文件 | 修改类型 | 修改内容 |
|------|---------|---------|
| `src/application/backtester.py` | 修改 | 1. 主循环中收集权益曲线<br>2. 添加 `_calculate_sharpe_ratio()` 方法<br>3. 报告生成时调用计算 |
| `src/domain/models.py` | 无需修改 | `PMSBacktestReport.sharpe_ratio` 字段已存在 |
| `tests/unit/test_backtester.py` | 新增 | 夏普比率计算测试 |

### 5.2 实施步骤

**Step 1: 主循环添加权益曲线收集** (15 分钟)

在 `backtester.py` 的主循环中（Step 6），每个 K 线处理后记录权益值：

```python
# 在 backtester.py:1209 附近，state tracking 区域添加
equity_curve: List[Tuple[int, Decimal]] = []

# 在主循环末尾（for kline in klines 的最后）添加
equity_curve.append((kline.timestamp, account.total_balance))
```

**Step 2: 实现夏普比率计算函数** (30 分钟)

```python
def _calculate_sharpe_ratio(
    equity_curve: List[Tuple[int, Decimal]],
    timeframe: str,
) -> Optional[Decimal]:
    """
    基于权益曲线计算年化夏普比率

    Args:
        equity_curve: [(timestamp_ms, equity_value), ...]
        timeframe: K 线周期 (15m/1h/4h/1d/1w)

    Returns:
        年化夏普比率，数据不足时返回 None
    """
    if len(equity_curve) < 2:
        return None

    # 计算逐期收益率
    returns: List[Decimal] = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1][1]
        curr_equity = equity_curve[i][1]
        if prev_equity > 0:
            r = (curr_equity - prev_equity) / prev_equity
            returns.append(r)

    if len(returns) < 2:
        return None

    # 计算均值和标准差
    n = Decimal(len(returns))
    mean_return = sum(returns) / n
    variance = sum((r - mean_return) ** 2 for r in returns) / (n - Decimal('1'))
    std_return = variance.sqrt() if variance > 0 else Decimal('0')

    if std_return == Decimal('0'):
        return Decimal('0')

    # 周期夏普
    sharpe_per_period = mean_return / std_return

    # 年化
    bars_per_year = self.BARS_PER_YEAR.get(timeframe, 8760)
    annualization_factor = Decimal(str(math.sqrt(bars_per_year)))

    return sharpe_per_period * annualization_factor
```

**Step 3: 报告生成时调用** (10 分钟)

在 `backtester.py:1472` 处替换硬编码 `None`：

```python
sharpe_ratio = self._calculate_sharpe_ratio(equity_curve, request.timeframe),
```

**Step 4: 单元测试** (30 分钟)

```python
class TestSharpeRatioCalculation:
    def test_insufficient_data_returns_none(self):
        # 只有 1 个数据点应返回 None
        ...

    def test_zero_volatility_returns_zero(self):
        # 权益值恒定应返回 0
        ...

    def test_positive_sharpe(self):
        # 稳定上涨的权益曲线应返回正夏普
        ...

    def test_negative_sharpe(self):
        # 持续下跌的权益曲线应返回负夏普
        ...

    def test_annualization_correct(self):
        # 不同 timeframes 的年化因子是否正确
        ...
```

### 5.3 预估总工作量

| 步骤 | 预估时间 |
|------|---------|
| Step 1: 权益曲线收集 | 15 分钟 |
| Step 2: 计算函数实现 | 30 分钟 |
| Step 3: 报告生成集成 | 10 分钟 |
| Step 4: 单元测试 | 30 分钟 |
| **总计** | **约 1.5 小时** |

---

## 6. 风险点与边界处理

### 6.1 交易笔数不足 / 数据点不足

| 场景 | 处理策略 |
|------|---------|
| K 线数量 < 2 | 返回 `None`（前端显示 "数据不足"） |
| 收益率序列标准差为 0 | 返回 `Decimal('0')`（无波动即无风险调整收益） |
| 前一期权益值为 0 | 跳过该期（避免除零），计入日志 |

### 6.2 Decimal 精度问题

- **收益率计算**: `(curr - prev) / prev` -- `prev` 可能为 `Decimal(0)`，需先判断
- **平方根计算**: `Decimal.sqrt()` 要求被开方数 `>= 0`，`variance` 理论上永远 `>= 0`，但浮点误差可能导致负值，需用 `max(Decimal('0'), variance)`
- **年化因子**: `math.sqrt()` 返回 `float`，需 `Decimal(str(...))` 转回 Decimal

### 6.3 性能影响

- **权益曲线存储**: 500 根 K 线 × 16 字节 ≈ 8KB，内存影响可忽略
- **计算复杂度**: O(N) 遍历 + O(N) 均值/方差计算，N < 10,000 时 < 1ms
- **不影响主循环**: 计算放在报告生成阶段（Step 9），不在主循环内

### 6.4 无风险利率假设

- **当前方案**: 假设 `Rf = 0`（无风险利率为 0）
- **理由**: 加密货币市场无风险利率难以精确定义（稳定币收益率/USDT 定存利率波动大），且回测场景下 Rf 影响极小
- **扩展性**: 可在未来通过 `BacktestRequest` 新增 `risk_free_rate` 参数

---

## 7. 关联影响

| 受影响模块 | 影响类型 | 风险等级 | 处理方案 |
|-----------|---------|---------|---------|
| `src/application/backtester.py` | 新增字段+方法 | P0 | 主逻辑修改 |
| `src/domain/models.py` | 已有字段使用 | 无 | 无需修改 |
| `web-front/src/components/v3/backtest/` | 前端展示 | P2 | 前端已有 null 检测，无需改 |
| `tests/unit/test_backtester.py` | 新增测试 | P1 | QA 负责 |

---

## 8. 技术债

### 已知限制

1. **无风险利率为 0**: 未来可改为从配置读取
2. **权益曲线仅记录总余额**: 未区分可用余额和冻结保证金，可能在极端杠杆情况下失真
3. **未考虑资金费用**: 权益曲线中的余额已包含资金费用影响，但收益率序列未单独剥离

### 后续优化计划

1. 增加 Sortino Ratio（仅考虑下行波动率）
2. 增加 Calmar Ratio（收益/最大回撤）
3. 权益曲线数据可复用于前端展示（当前仅计算夏普比率）
