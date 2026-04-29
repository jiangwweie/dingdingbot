# Same-Bar 撮合顺序可配置实现总结

> **实现日期**: 2026-04-22
> **版本**: 最小版本（v1.0）
> **目的**: 解决固定悲观撮合可能过早错杀参数的问题

---

## 一、修改文件列表

### 1. 核心模型层（Domain）

**文件**: `src/domain/models.py`

**改动**:
- `BacktestRuntimeOverrides`: 新增 3 个撮合参数字段
  - `same_bar_policy: Optional[str]` - 撮合策略（pessimistic/random）
  - `same_bar_tp_first_prob: Optional[Decimal]` - TP 优先概率
  - `random_seed: Optional[int]` - 随机种子

- `ResolvedBacktestParams`: 新增 3 个撮合参数字段（带默认值）
  - `same_bar_policy: str = "pessimistic"`
  - `same_bar_tp_first_prob: Decimal = Decimal("0.5")`
  - `random_seed: Optional[int] = None`

- `BACKTEST_PARAM_DEFAULTS`: 新增撮合参数默认值
  ```python
  "same_bar_policy": "pessimistic",
  "same_bar_tp_first_prob": Decimal("0.5"),
  "random_seed": None,
  ```

### 2. 撮合引擎层（Domain）

**文件**: `src/domain/matching_engine.py`

**改动**:
- `MockMatchingEngine.__init__()`: 新增 3 个参数
  - `same_bar_policy: str = "pessimistic"`
  - `same_bar_tp_first_prob: Decimal = Decimal("0.5")`
  - `random_seed: Optional[int] = None`

- 新增方法 `_detect_same_bar_conflicts()`:
  - 检测同一根 K 线内 TP/SL 都会被触发的场景
  - 返回存在冲突的 signal_id 集合

- 修改方法 `_sort_orders_by_priority()`:
  - 新增参数 `kline: KlineData`（用于冲突检测）
  - 根据 `same_bar_policy` 决定 TP/SL 优先级
  - 仅在冲突场景下应用 random 策略

### 3. 回测引擎层（Application）

**文件**: `src/application/backtester.py`

**改动**:
- 新增函数 `resolve_str()`:
  - 解析字符串类型参数
  - 遵循优先级：runtime overrides > request > profile KV > code default

- 修改函数 `resolve_backtest_params()`:
  - 新增撮合参数解析逻辑
  - 将解析结果传递给 `ResolvedBacktestParams`

- 修改 `MockMatchingEngine` 初始化:
  - 传递撮合参数：`same_bar_policy`, `same_bar_tp_first_prob`, `random_seed`

### 4. 测试脚本

**文件**: `scripts/test_same_bar_policy.py`

**用途**: 验证功能正确性
- 测试 pessimistic 策略（默认）
- 测试 random 策略（不同 TP 优先概率）
- 验证 random_seed 可复现性

---

## 二、参数传递链路说明

### 优先级链（从高到低）

```
1. BacktestRuntimeOverrides（运行时覆盖）
   ↓
2. BacktestRequest（请求参数）
   ↓
3. Profile KV（配置数据库）
   ↓
4. BACKTEST_PARAM_DEFAULTS（代码默认值）
```

### 完整传递流程

```
用户输入
  ↓
BacktestRuntimeOverrides(
    same_bar_policy="random",
    same_bar_tp_first_prob=Decimal("0.3"),
    random_seed=42
)
  ↓
resolve_backtest_params()
  ├─ resolve_str("same_bar_policy", ...)
  ├─ resolve_decimal("same_bar_tp_first_prob", ...)
  └─ 直接传递 random_seed
  ↓
ResolvedBacktestParams(
    same_bar_policy="random",
    same_bar_tp_first_prob=Decimal("0.3"),
    random_seed=42
)
  ↓
MockMatchingEngine(
    same_bar_policy="random",
    same_bar_tp_first_prob=Decimal("0.3"),
    random_seed=42
)
  ↓
撮合引擎初始化随机数生成器
  rng = random.Random(42)
```

### 参数验证

- `same_bar_policy`: 枚举值 `"pessimistic"` 或 `"random"`
- `same_bar_tp_first_prob`: Decimal 类型，范围 [0, 1]
- `random_seed`: int 或 None（None 表示不固定）

---

## 三、冲突场景的旧逻辑 vs 新逻辑

### 场景定义

**Same-Bar 冲突**: 同一根 K 线内，`high` 和 `low` 同时覆盖 TP 和 SL 价格。

**示例**（多头仓位）:
```
K线数据: high=2550, low=2480
TP1 价格: 2520（会被触发：high >= 2520）
SL 价格:  2490（会被触发：low <= 2490）
```

### 旧逻辑（固定悲观撮合）

**实现**:
```python
# _sort_orders_by_priority() 固定返回
SL 订单优先级 = 1（最高）
TP 订单优先级 = 2（中等）
ENTRY 订单优先级 = 3（最低）
```

**结果**:
- SL 必定先成交
- TP 被撤销
- **所有 same-bar 冲突都按最不利情况处理**

**问题**:
- 可能过早错杀参数
- 无法评估真实市场中的不确定性

### 新逻辑（可配置撮合）

#### 策略 1: pessimistic（默认，与旧逻辑一致）

**实现**:
```python
if same_bar_policy == "pessimistic":
    SL 优先级 = 1
    TP 优先级 = 2
```

**结果**:
- SL 优先成交
- 与旧逻辑完全一致
- **保持向后兼容**

#### 策略 2: random（新增）

**实现**:
```python
if same_bar_policy == "random":
    # 检测冲突
    conflict_signals = _detect_same_bar_conflicts(orders, kline)

    # 仅在冲突时随机决定
    if order.signal_id in conflict_signals:
        if rng.random() < same_bar_tp_first_prob:
            TP 优先级 = 1  # TP 先成交
            SL 优先级 = 2
        else:
            SL 优先级 = 1  # SL 先成交
            TP 优先级 = 2
```

**结果**:
- 根据 `same_bar_tp_first_prob` 概率决定 TP/SL 优先级
- 使用 `random_seed` 保证可复现
- **非冲突场景仍按默认优先级**

**示例**:
```python
# 配置
same_bar_policy = "random"
same_bar_tp_first_prob = 0.3  # TP 优先概率 30%
random_seed = 42

# 结果
- 30% 的冲突场景：TP 先成交
- 70% 的冲突场景：SL 先成交
- 非冲突场景：不受影响
```

---

## 四、下一步：Monte Carlo 批量框架（待补充）

### 当前实现已支持

✅ 单次回测可配置撮合策略
✅ 随机种子可复现
✅ 参数传递链路完整

### 需要补充的内容

#### 1. Monte Carlo 批量运行器

**功能**: 自动运行多次回测，统计结果分布

**示例实现**:
```python
async def run_monte_carlo(
    request: BacktestRequest,
    runtime_overrides: BacktestRuntimeOverrides,
    n_simulations: int = 100,
) -> Dict[str, Any]:
    """
    Monte Carlo 模拟

    Args:
        request: 回测请求
        runtime_overrides: 基础参数（不含 random_seed）
        n_simulations: 模拟次数

    Returns:
        {
            "mean_pnl": Decimal,
            "std_pnl": Decimal,
            "min_pnl": Decimal,
            "max_pnl": Decimal,
            "percentile_5": Decimal,
            "percentile_95": Decimal,
        }
    """
    results = []

    for i in range(n_simulations):
        # 每次使用不同种子
        overrides = BacktestRuntimeOverrides(
            **runtime_overrides.model_dump(),
            same_bar_policy="random",
            random_seed=i,  # 固定种子序列
        )

        report = await backtester.run_backtest(request, overrides)
        results.append(float(report.total_pnl))

    # 统计分析
    return {
        "mean_pnl": Decimal(str(np.mean(results))),
        "std_pnl": Decimal(str(np.std(results))),
        "min_pnl": Decimal(str(np.min(results))),
        "max_pnl": Decimal(str(np.max(results))),
        "percentile_5": Decimal(str(np.percentile(results, 5))),
        "percentile_95": Decimal(str(np.percentile(results, 95))),
    }
```

#### 2. 结果可视化

**功能**: 绘制 PnL 分布图、置信区间

**示例**:
```python
import matplotlib.pyplot as plt
import seaborn as sns

def plot_monte_carlo_distribution(results: List[float]):
    """绘制 Monte Carlo 结果分布"""
    plt.figure(figsize=(10, 6))
    sns.histplot(results, kde=True, bins=30)
    plt.axvline(np.mean(results), color='r', linestyle='--', label='Mean')
    plt.axvline(np.percentile(results, 5), color='g', linestyle=':', label='5th Percentile')
    plt.axvline(np.percentile(results, 95), color='g', linestyle=':', label='95th Percentile')
    plt.xlabel('Total PnL (USDT)')
    plt.ylabel('Frequency')
    plt.title('Monte Carlo Simulation Results')
    plt.legend()
    plt.savefig('monte_carlo_distribution.png')
```

#### 3. 参数敏感性分析

**功能**: 测试不同 `same_bar_tp_first_prob` 对结果的影响

**示例**:
```python
async def sensitivity_analysis(
    request: BacktestRequest,
    tp_probs: List[Decimal] = [Decimal("0.0"), Decimal("0.25"), Decimal("0.5"), Decimal("0.75"), Decimal("1.0")],
    n_simulations: int = 100,
):
    """参数敏感性分析"""
    results = {}

    for prob in tp_probs:
        overrides = BacktestRuntimeOverrides(
            same_bar_policy="random",
            same_bar_tp_first_prob=prob,
        )

        mc_result = await run_monte_carlo(request, overrides, n_simulations)
        results[float(prob)] = mc_result

    return results
```

#### 4. 性能优化

**问题**: 当前实现每次回测都重新加载数据

**优化方向**:
- 缓存 K 线数据
- 并行运行多次模拟（asyncio.gather）
- 预计算冲突场景

#### 5. 统计检验

**功能**: 验证 random 策略是否显著改善结果

**示例**:
```python
from scipy import stats

def statistical_test(
    pessimistic_pnl: float,
    random_pnls: List[float],
):
    """统计检验：random 策略是否显著优于 pessimistic"""
    t_stat, p_value = stats.ttest_1samp(random_pnls, pessimistic_pnl)

    return {
        "t_statistic": t_stat,
        "p_value": p_value,
        "significant": p_value < 0.05,
    }
```

---

## 五、使用示例

### 示例 1: 默认悲观策略

```python
from src.domain.models import BacktestRuntimeOverrides

overrides = BacktestRuntimeOverrides(
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    same_bar_policy="pessimistic",  # 或不传（默认）
)
```

### 示例 2: 随机策略（可复现）

```python
overrides = BacktestRuntimeOverrides(
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    same_bar_policy="random",
    same_bar_tp_first_prob=Decimal("0.3"),  # TP 优先概率 30%
    random_seed=42,  # 固定种子
)
```

### 示例 3: Monte Carlo 批量测试

```python
# 运行 100 次模拟
for i in range(100):
    overrides = BacktestRuntimeOverrides(
        ema_period=50,
        same_bar_policy="random",
        same_bar_tp_first_prob=Decimal("0.5"),
        random_seed=i,  # 每次不同种子
    )

    report = await backtester.run_backtest(request, overrides)
    results.append(float(report.total_pnl))

# 统计分析
print(f"Mean PnL: {np.mean(results):.2f}")
print(f"Std PnL: {np.std(results):.2f}")
print(f"5th Percentile: {np.percentile(results, 5):.2f}")
print(f"95th Percentile: {np.percentile(results, 95):.2f}")
```

---

## 六、兼容性与安全性

### 向后兼容

✅ 默认行为不变（`same_bar_policy="pessimistic"`）
✅ 不影响现有 stress 基线结果
✅ 不改 live 交易逻辑（仅回测路径）

### 边界情况处理

✅ 非冲突场景：不受影响
✅ 无 TP/SL 订单：不受影响
✅ random_seed=None：每次随机

### 性能影响

- 冲突检测：O(n) 复杂度（n = 订单数）
- 随机数生成：O(1) 复杂度
- **整体影响可忽略**

---

## 七、测试验证

### 测试脚本

**文件**: `scripts/test_same_bar_policy.py`

**测试内容**:
1. 默认 pessimistic 策略
2. random 策略（不同 TP 优先概率）
3. random_seed 可复现性

**运行方式**:
```bash
python3 scripts/test_same_bar_policy.py
```

### 预期结果

- pessimistic 策略：与旧行为完全一致
- random 策略：不同 TP 优先概率产生不同结果
- 相同 random_seed：产生相同结果

---

## 八、总结

### 已完成

✅ 撮合参数走正式参数链
✅ 默认行为保持兼容
✅ random 策略实现可配置
✅ 随机种子保证可复现
✅ 冲突检测逻辑完整
✅ 测试脚本验证功能

### 待补充（Monte Carlo）

⏳ 批量运行器
⏳ 结果可视化
⏳ 参数敏感性分析
⏳ 性能优化
⏳ 统计检验

### 核心价值

1. **解决固定悲观撮合问题**: 不再过早错杀参数
2. **评估真实市场不确定性**: 通过 Monte Carlo 模拟
3. **保持向后兼容**: 默认行为不变
4. **最小实现**: 不引入复杂抽象，易于理解维护

---

*实现完成日期: 2026-04-22*
*下一步: Monte Carlo 批量框架（可选）*
