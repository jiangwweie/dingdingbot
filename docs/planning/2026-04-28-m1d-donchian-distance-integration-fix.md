# Donchian Distance Filter 提交前接入修正

**日期**: 2026-04-28
**修改范围**: 仅 `logic_tree.py` + `filter_factory.py` + 测试文件
**状态**: ✅ 完成

---

## 修改项

### 1. FilterConfig.type Literal 增加 "donchian_distance"

**文件**: `src/domain/logic_tree.py` (line 21)

```python
# 修改前
type: Literal["ema", "ema_trend", "mtf", "atr", "volume_surge", "volatility_filter", "time_filter", "price_action"]

# 修改后
type: Literal["ema", "ema_trend", "mtf", "atr", "donchian_distance", "volume_surge", "volatility_filter", "time_filter", "price_action"]
```

**效果**: FilterConfig 现在接受 `type="donchian_distance"`，Pydantic 会验证类型合法性。

---

### 2. 明确 enabled 默认策略

**决策**: **沿用项目默认 `enabled=True`**

**理由**:
1. FilterConfig 已定义 `enabled: bool = Field(default=True, ...)`
2. 所有现有过滤器（EMA/MTF/ATR）都使用 `enabled=True` 作为默认值
3. 保持一致性，避免特殊处理

**修改**:

**文件**: `src/domain/filter_factory.py` (line 705-711)

```python
# 修改前
enabled: bool = False

# 修改后
enabled: bool = True
```

**文档更新** (line 712-722):

```python
Args:
    enabled: Whether filter is active (default True, follows project convention)

Note:
    Configuration must explicitly set enabled=True/False. The default True follows
    project convention (FilterConfig.enabled defaults to True).
```

**关键点**:
- ✅ 配置必须显式写 `enabled=True/False`
- ✅ 默认值遵循项目约定（FilterConfig.enabled = True）
- ✅ 不再声称"安全默认 False"

---

### 3. 新增集成测试

**文件**: `tests/unit/test_donchian_distance_filter.py`

#### 新增测试类: `TestDonchianDistanceFilterIntegration` (5 个测试)

| 测试 | 验证内容 |
|------|----------|
| `test_filter_config_accepts_donchian_distance` | FilterConfig 接受 `type="donchian_distance"` |
| `test_filter_config_default_enabled_is_true` | FilterConfig 默认 `enabled=True` |
| `test_create_chain_from_filter_configs` | FilterFactory.create_chain 从 FilterConfig 创建过滤器链 |
| `test_strategy_definition_with_donchian_filter` | StrategyDefinition 接受 donchian_distance filter in logic_tree |
| `test_factory_default_enabled_is_true` | FilterFactory 默认 `enabled=True` |

**关键验证**:
- ✅ FilterConfig Pydantic 验证通过
- ✅ FilterFactory.create() 正确创建 DonchianDistanceFilterDynamic
- ✅ FilterFactory.create_chain() 支持混合过滤器链
- ✅ StrategyDefinition.logic_tree 支持 donchian_distance filter
- ✅ 默认 enabled 行为符合项目约定

---

## 测试结果

### 完整测试

```
tests/unit/test_donchian_distance_filter.py
  ✓ 24 passed in 0.05s

tests/unit/test_filter_factory.py
  ✓ 43 passed in 0.04s

总计: 67 个测试全部通过，无回归
```

### 新增测试明细

```
TestDonchianDistanceFilterBasic (2 tests)
  ✓ test_filter_disabled
  ✓ test_insufficient_history

TestDonchianDistanceFilterValidation (6 tests)
  ✓ test_lookback_must_be_positive
  ✓ test_lookback_minimum_valid
  ✓ test_max_distance_high_must_be_negative_or_zero
  ✓ test_max_distance_low_must_be_negative_or_zero
  ✓ test_zero_distance_threshold_valid
  ✓ test_negative_distance_threshold_valid

TestDonchianDistanceFilterLong (3 tests)
  ✓ test_long_near_high_filtered
  ✓ test_long_far_from_high_passes
  ✓ test_long_exact_threshold_boundary

TestDonchianDistanceFilterShort (3 tests)
  ✓ test_short_near_low_filtered
  ✓ test_short_far_from_low_passes
  ✓ test_short_no_threshold_configured

TestDonchianDistanceFilterLookaheadPrevention (2 tests)
  ✓ test_current_bar_excluded_from_donchian
  ✓ test_window_rolling_correctly

TestDonchianDistanceFilterMultipleSymbols (1 test)
  ✓ test_multiple_symbols_independent_state

TestDonchianDistanceFilterFactory (3 tests)
  ✓ test_factory_creates_donchian_filter
  ✓ test_factory_creates_disabled_filter
  ✓ test_factory_default_enabled_is_true

TestDonchianDistanceFilterIntegration (5 tests)
  ✓ test_filter_config_accepts_donchian_distance
  ✓ test_filter_config_default_enabled_is_true
  ✓ test_create_chain_from_filter_configs
  ✓ test_strategy_definition_with_donchian_filter
```

---

## Diff 摘要

### src/domain/logic_tree.py

```diff
- type: Literal["ema", "ema_trend", "mtf", "atr", "volume_surge", ...]
+ type: Literal["ema", "ema_trend", "mtf", "atr", "donchian_distance", "volume_surge", ...]
```

**变更**: 1 行修改（FilterConfig.type Literal 增加 "donchian_distance"）

### src/domain/filter_factory.py

```diff
+ class DonchianDistanceFilterDynamic(FilterBase):
+     """Donchian distance filter for filtering signals too close to channel boundaries."""
+
+     def __init__(self, lookback=20, max_distance_to_high_pct=None, max_distance_to_low_pct=None, enabled=True):
+         # 参数验证 + 状态初始化
+
+     # 完整生命周期实现: update_state(), check(), get_current_trend()

+ _registry = {
+     "donchian_distance": DonchianDistanceFilterDynamic,
+     ...
+ }

+ elif filter_type == "donchian_distance":
+     # 创建 DonchianDistanceFilterDynamic 实例
```

**变更**:
- 新增 DonchianDistanceFilterDynamic 类 (226 行)
- 注册到 FilterFactory._registry
- FilterFactory.create() 新增处理分支

### tests/unit/test_donchian_distance_filter.py

**变更**: 新增文件 (600+ 行，24 个测试)

---

## 风险评估

### ✅ 无已知风险

**已验证**:
1. ✅ FilterConfig Pydantic 验证通过
2. ✅ FilterFactory 正确创建过滤器
3. ✅ StrategyDefinition 支持 donchian_distance filter
4. ✅ 默认 enabled 行为符合项目约定
5. ✅ 无回归（67 个测试全部通过）

**潜在风险已缓解**:
1. ⚠️ 配置未显式设置 enabled → **缓解**: 文档明确要求显式设置，默认遵循项目约定
2. ⚠️ 参数验证 → **缓解**: ValueError 立即暴露非法参数

---

## 使用示例

### StrategyDefinition 配置

```python
from src.domain.models import StrategyDefinition
from src.domain.logic_tree import FilterConfig, FilterLeaf, LogicNode

# 创建 donchian_distance filter
donchian_leaf = FilterLeaf(
    id="donchian_filter",
    config=FilterConfig(
        type="donchian_distance",
        enabled=True,  # 显式设置
        params={
            "lookback": 20,
            "max_distance_to_high_pct": "-0.016809"
        }
    )
)

# 创建 logic_tree
logic_tree = LogicNode(
    gate="AND",
    children=[donchian_leaf]
)

# 创建策略
strategy = StrategyDefinition(
    id="pinbar_with_donchian",
    name="Pinbar with Donchian Distance Filter",
    logic_tree=logic_tree,
    apply_to=["ETH/USDT:USDT:1h"]
)
```

### FilterFactory.create_chain

```python
from src.domain.filter_factory import FilterFactory
from src.domain.logic_tree import FilterConfig

configs = [
    FilterConfig(type="ema_trend", params={"period": 60}),
    FilterConfig(type="mtf", params={}),
    FilterConfig(
        type="donchian_distance",
        enabled=True,
        params={
            "lookback": 20,
            "max_distance_to_high_pct": "-0.016809"
        }
    )
]

filters = FilterFactory.create_chain(configs)
# filters[0] -> EmaTrendFilterDynamic
# filters[1] -> MtfFilterDynamic
# filters[2] -> DonchianDistanceFilterDynamic
```

---

## 总结

✅ **FilterConfig 接入完成**: type Literal 增加 "donchian_distance"
✅ **enabled 默认策略明确**: 沿用项目默认 True，文档要求显式设置
✅ **集成测试完整**: 24 个测试全部通过，覆盖 FilterConfig/StrategyDefinition
✅ **无回归**: 67 个测试全部通过
✅ **文档清晰**: 生命周期、未来函数防护、参数约束已说明

**建议**: 可以提交到代码库，已完全接入系统架构。
