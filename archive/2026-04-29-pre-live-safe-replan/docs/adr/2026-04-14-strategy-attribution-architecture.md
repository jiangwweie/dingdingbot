# ADR: 策略归因功能架构设计

> **日期**: 2026-04-14
> **阶段**: 阶段 5 - 策略归因
> **目标**: 为每个信号提供可解释的归因分析
> **状态**: ✅ 用户已确认，待任务分解

---

## 0. 头脑风暴决策记录

### 决策 1: 使用场景
- **结论**: 回测报告（离线批量计算）
- **排除**: 实时信号推送（不需要碰 WebSocket 管线）

### 决策 2: 权重配置方式
- **结论**: KV 配置 + `AttributionConfig` Pydantic 校验层 + 前端受控表单
- **理由**: 复用现有 ConfigManager KV 体系，零新基础设施
- **风险缓解**:
  - Pydantic 校验层拦截脏数据（权重和≈1.0、范围[0,1]、必需key）
  - 前端只暴露固定表单，不开放自由添加 KV key

### 决策 3: 精确度要求
- **结论**: 数学可验证
- **含义**: 每个贡献值可追溯到 `score × weight` 的计算过程，存入 `confidence_basis` 字段

### 推荐方案
- **选择**: 方案 B（归因解释层），非侵入式
- **渐进路径**: B 上线验证 → 数据积累 → 未来可选升级到 A

---

## 1. 需求分析

### 用户故事

作为交易员，我希望看到：
> "这个信号是因为 Pinbar 形态贡献 60% + EMA 趋势过滤通过贡献 20% + 成交量放大贡献 20%"

### 现有系统盘点

| 组件 | 现状 | 归因相关能力 |
|------|------|-------------|
| `PatternStrategy.calculate_score()` | `pattern_ratio × 0.7 + atr_ratio × 0.3` | 已有形态评分 |
| `FilterBase.check()` | 返回 `FilterResult(passed: bool, reason: str, metadata: Dict)` | 仅布尔决策，无评分贡献 |
| `SignalAttempt` | 记录 `filter_results: List[Tuple[str, FilterResult]]` | 有记录但仅用于日志 |
| `AttributionAnalyzer` | 回测后四维分析（形态/过滤器/趋势/RR） | 群体统计，非单信号级 |
| `SignalResult` | 有 `score: float` 字段 | 仅形态评分，不含过滤器贡献 |

### 核心差距

**当前评分公式仅包含形态质量**，过滤器是"布尔门"（通过/拒绝），不参与评分。
用户需要的"每个组件贡献百分比"在现有架构中不存在。

---

## 2. 方案 A: 过滤器评分化（加权投票模型）

### 2.1 核心思路

将过滤器从 **布尔门** 改造为 **评分器**，每个过滤器返回 0~1 的置信度分数，
最终信号评分 = 形态评分 × 权重 + 过滤器评分加权和。

### 2.2 架构变更

#### 2.2.1 新增 `FilterScore` 模型

```python
@dc_dataclass
class FilterScore:
    """过滤器的量化评分"""
    filter_name: str          # "ema_trend", "mtf", "volume_surge"
    score: Decimal            # 0.0 ~ 1.0，置信度
    weight: Decimal           # 该过滤器在总评分中的权重
    contribution: Decimal     # score × weight，实际贡献值
    reason: str               # 评分依据，如 "price 2.3% above EMA20"
    metadata: Dict[str, Any]  # 原始数据，用于诊断
```

#### 2.2.2 修改 `FilterBase` 接口

```python
class FilterBase(ABC):
    # 新增抽象方法
    @abstractmethod
    def score(self, pattern: PatternResult, context: FilterContext) -> FilterScore:
        """
        返回该过滤器的置信度评分。
        即使 passed=False，也返回评分（用于归因诊断）。
        """
        pass

    # 保留原有 check() 方法（向后兼容）
    @abstractmethod
    def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
        pass
```

#### 2.2.3 各过滤器评分逻辑示例

**EmaTrendFilterDynamic**:
```python
def score(self, pattern, context):
    price = context.current_price
    ema = self.ema_calculator.get_ema()
    distance_pct = abs(price - ema) / ema  # 价格偏离 EMA 的百分比

    if pattern.direction == Direction.LONG:
        if price > ema:
            # 顺趋势：偏离越大，信心越足
            confidence = min(distance_pct / Decimal("0.05"), Decimal("1.0"))  # 5% 偏离 = 满分
        else:
            confidence = Decimal("0.0")  # 逆趋势 = 零分
    else:
        # SHORT 逻辑对称
        ...

    return FilterScore(
        filter_name="ema_trend",
        score=confidence,
        weight=Decimal("0.25"),
        contribution=confidence * Decimal("0.25"),
        reason=f"price {distance_pct:.2%} {'above' if price > ema else 'below'} EMA",
        metadata={"price": price, "ema": ema, "distance_pct": distance_pct}
    )
```

**MtfFilterDynamic**:
```python
def score(self, pattern, context):
    # 检查更高周期趋势的一致性
    aligned_count = 0
    total_count = 0
    for tf, trend in context.higher_tf_trends.items():
        total_count += 1
        if (pattern.direction == Direction.LONG and trend == TrendDirection.BULLISH) or \
           (pattern.direction == Direction.SHORT and trend == TrendDirection.BEARISH):
            aligned_count += 1

    alignment_ratio = Decimal(str(aligned_count / total_count)) if total_count > 0 else Decimal("0.5")

    return FilterScore(
        filter_name="mtf",
        score=alignment_ratio,
        weight=Decimal("0.20"),
        contribution=alignment_ratio * Decimal("0.20"),
        reason=f"{aligned_count}/{total_count} higher timeframes aligned",
        metadata={"higher_tf_trends": context.higher_tf_trends}
    )
```

#### 2.2.4 修改评分聚合逻辑

```python
# 在 StrategyEngine 或 SignalPipeline 中
def calculate_attributed_score(
    pattern_score: Decimal,
    filter_scores: List[FilterScore],
) -> SignalAttribution:
    """计算带归因的信号评分"""

    # 权重分配
    pattern_weight = Decimal("0.55")
    filter_total_weight = sum(fs.weight for fs in filter_scores)  # 应为 0.45

    # 最终评分
    pattern_contrib = pattern_score * pattern_weight
    filter_contributions = [fs.contribution for fs in filter_scores]
    final_score = pattern_contrib + sum(filter_contributions)

    return SignalAttribution(
        final_score=min(final_score, Decimal("1.0")),
        components=[
            AttributionComponent(
                name="pattern",
                score=pattern_score,
                weight=pattern_weight,
                contribution=pattern_contrib
            ),
            *[
                AttributionComponent(
                    name=fs.filter_name,
                    score=fs.score,
                    weight=fs.weight,
                    contribution=fs.contribution
                )
                for fs in filter_scores
            ]
        ]
    )
```

#### 2.2.5 新增响应模型

```python
class SignalAttribution(BaseModel):
    """单信号的归因分析结果"""
    final_score: float
    components: List[AttributionComponent]
    percentages: Dict[str, float]  # {"pattern": 55.0, "ema_trend": 25.0, "mtf": 20.0}


class AttributionComponent(BaseModel):
    name: str
    score: float       # 0~1
    weight: float      # 权重
    contribution: float  # score × weight
```

### 2.3 数据流

```
KlineData
    |
    v
Strategy.detect() ──────────► PatternResult(score=0.72)
    |
    v
Filter.score() ×N ──────────► [FilterScore(ema=0.8), FilterScore(mtf=0.67), ...]
    |
    v
calculate_attributed_score()
    |
    ├── final_score = 0.72×0.55 + 0.8×0.25 + 0.67×0.20 = 0.728
    └── components = [
          {name: "pattern", contribution: 0.396, percentage: 54.4%},
          {name: "ema_trend", contribution: 0.200, percentage: 27.5%},
          {name: "mtf", contribution: 0.134, percentage: 18.4%}
        ]
    |
    v
SignalResult(attribution=SignalAttribution(...))
```

### 2.4 优缺点

| 维度 | 评价 |
|------|------|
| **优点** | |
| 数学上精确 | 每个组件贡献 = score × weight，可加总验证 |
| 用户可见 | 实时返回，不需要回测数据 |
| 可扩展 | 新增过滤器自动获得评分能力 |
| 兼容现有系统 | 保留 `check()` 布尔方法，过滤器仍可拒绝信号 |
| **缺点** | |
| 侵入性强 | 需要修改 `FilterBase` 接口和所有过滤器实现 |
| 评分函数设计困难 | 每个过滤器需要设计合理的 0~1 评分函数 |
| 权重主观性 | pattern:filter 权重比（如 55:45）需要调参 |
| 实现工作量 | 约 3-4 天（5 个过滤器 + 评分聚合 + API 扩展） |

---

## 3. 方案 B: 归因解释层（非侵入式 Shapley 近似）

### 3.1 核心思路

**不修改现有过滤器接口**。在现有 `SignalAttempt` 数据基础上，
构建一个独立的 `AttributionEngine`，使用 **特征重要性近似算法** 计算每个组件的贡献度。

核心思想：通过"反事实推理"——如果去掉某个过滤器，信号评分会下降多少？

### 3.2 架构变更

#### 3.2.1 新增 `AttributionEngine`

```python
class AttributionEngine:
    """
    非侵入式归因引擎，基于 SignalAttempt 数据计算组件贡献。

    不修改任何现有接口，纯分析层。
    权重通过 AttributionConfig.from_kv() 从 KV 配置加载并校验。
    """

    def __init__(self, config: AttributionConfig):
        self.config = config

    def attribute(self, attempt: SignalAttempt) -> SignalAttribution:
        """
        对单个 SignalAttempt 计算归因。

        算法:
        1. 基础分 = pattern.score × pattern_weight（从 KV 配置加载）
        2. 对每个通过的过滤器，根据"信心强度"计算附加分
        3. 信心强度基于过滤器的 metadata（如偏离度、对齐率），数学可验证
        4. 归一化到 0~1，并计算百分比贡献

        每个组件的贡献可追溯: contribution = score × weight
        """
        pattern_score = attempt.pattern.score if attempt.pattern else Decimal("0")

        # Step 1: 形态基础贡献
        pattern_weight = Decimal(str(self.config.weights["pattern"]))
        pattern_contrib = pattern_score * pattern_weight

        # Step 2: 过滤器信心评分（处理所有过滤器，包括被拒绝的）
        filter_scores = []
        for filter_name, filter_result in attempt_dict.get("filter_results", []):
            if isinstance(filter_result, dict):
                # 从 dict 读取
                passed = filter_result.get("passed", False)
                metadata = filter_result.get("metadata", {})
                reason = filter_result.get("reason", "")
            else:
                # 兼容 FilterResult 对象
                passed = filter_result.passed
                metadata = filter_result.metadata or {}
                reason = filter_result.reason

            if passed:
                # 通过的过滤器：计算信心评分
                confidence = self._calculate_filter_confidence(filter_name, metadata)
                weight = Decimal(str(
                    self.config.weights.get(filter_name, 0.10)
                ))
                filter_scores.append(FilterScore(
                    filter_name=filter_name,
                    score=confidence,
                    weight=weight,
                    contribution=confidence * weight,
                    reason=reason,
                    metadata=metadata,
                    confidence_basis=self._explain_confidence(
                        filter_name, metadata
                    ),
                    status="passed"
                ))
            else:
                # 被拒绝的过滤器：score=0，贡献为 0，标记为 rejected
                filter_scores.append(FilterScore(
                    filter_name=filter_name,
                    score=Decimal("0"),
                    weight=Decimal("0"),
                    contribution=Decimal("0"),
                    reason=reason,
                    metadata=metadata,
                    confidence_basis=f"REJECTED: {reason}",
                    status="rejected"
                ))

        # Step 3: 聚合
        total_filter_contrib = sum(fs.contribution for fs in filter_scores)
        final_score = pattern_contrib + total_filter_contrib
        final_score = min(final_score, Decimal("1.0"))

        # Step 4: 计算百分比（数学可验证）
        if final_score > 0:
            percentages = {
                "pattern": float(pattern_contrib / final_score * 100),
                **{
                    fs.filter_name: float(fs.contribution / final_score * 100)
                    for fs in filter_scores
                    if fs.status == "passed"
                }
            }
        else:
            # 最终评分为 0 时不伪造百分比（0 贡献 ≠ 100%）
            percentages = {}

        return SignalAttribution(
            final_score=float(final_score),
            components=[...],
            percentages=percentages,
            explanation=self._build_explanation(percentages)
        )

    def _calculate_filter_confidence(
        self, filter_name: str, metadata: Dict[str, Any]
    ) -> Decimal:
        """
        根据过滤器类型和 metadata 计算信心强度。
        每个信心函数都是数学可验证的确定性函数。

        信心值范围: 0.0 ~ 1.0

        当 metadata 缺少必需字段时，返回默认值并记录日志告警。
        """
        if filter_name in ("ema_trend", "ema"):
            # EMA 信心: 价格偏离 EMA 的百分比（线性映射）
            # 公式: confidence = min(distance_pct / 0.05, 1.0)
            # 含义: 价格偏离 EMA 5% 以上 = 满分信心
            price = metadata.get("price")
            ema = metadata.get("ema_value")
            if price and ema:
                distance = abs(Decimal(str(price)) - Decimal(str(ema))) / Decimal(str(ema))
                return min(distance / Decimal("0.05"), Decimal("1.0"))
            logger.warning(f"EMA metadata incomplete for attribution, default confidence=0.5")
            return Decimal("0.5")  # 默认中等信心

        elif filter_name == "mtf":
            # MTF 信心: 高周期对齐比例
            # 公式: confidence = aligned_count / total_count
            # 含义: 所有高周期趋势一致 = 满分信心
            aligned = metadata.get("aligned_count", 0)
            total = metadata.get("total_count", 1)
            if total > 0:
                return Decimal(str(aligned)) / Decimal(str(total))
            logger.warning(f"MTF metadata incomplete for attribution, default confidence=0.5")
            return Decimal("0.5")

        elif filter_name == "atr":
            # ATR 信心: K 线范围相对于 ATR 的倍数（capped at 2.0）
            # 公式: confidence = min(atr_ratio / 2.0, 1.0)
            atr_ratio = metadata.get("atr_ratio")
            if atr_ratio:
                return min(Decimal(str(atr_ratio)) / Decimal("2.0"), Decimal("1.0"))
            logger.warning(f"ATR metadata incomplete for attribution, default confidence=0.5")
            return Decimal("0.5")

        else:
            # 未知过滤器: 默认中等信心
            return Decimal("0.5")

    def _explain_confidence(self, filter_name: str, metadata: Dict[str, Any]) -> str:
        """
        生成信心评分的人类可读解释（数学可验证）。
        用户可以看到"这个数字怎么来的"。
        """
        if filter_name in ("ema_trend", "ema"):
            price = metadata.get("price")
            ema = metadata.get("ema_value")
            if price and ema:
                distance_pct = abs(price - ema) / ema * 100
                score = min(distance_pct / 5.0, 1.0)
                return f"price {price} is {distance_pct:.2f}% {'above' if price > ema else 'below'} EMA {ema}, score=min({distance_pct:.2f}/5.0, 1.0)={score:.3f}"
            return "metadata incomplete, default confidence=0.5"

        elif filter_name == "mtf":
            aligned = metadata.get("aligned_count", 0)
            total = metadata.get("total_count", 1)
            return f"{aligned}/{total} higher timeframes aligned, score={aligned}/{total}={aligned/total:.3f}"

        return "confidence function not defined for this filter"
```

#### 3.2.2 与 AttributionAnalyzer 的关系

本项目已有一个 `AttributionAnalyzer`（`src/application/attribution_analyzer.py`），两者的关系如下：

| | `AttributionAnalyzer`（已有） | `AttributionEngine`（新增） |
|---|---|---|
| 分析级别 | 回测报告级（群体统计） | 单信号级（个体归因） |
| 输入 | 完整的 BacktestReport | 单个 SignalAttempt |
| 输出 | 四维度归因（形态/过滤器/趋势/RR） | 每个组件的 score × weight 贡献 |
| 使用时机 | 回测完成后查看整体表现 | 查看单个信号时看具体贡献 |

两者互补，不冲突。

#### 3.2.3 数据契约

**P0 注意**：`SignalAttempt` 在回测引擎中被序列化为 `dict`（`_attempt_to_dict()`），不存在直接的反序列化方法。

归因引擎接受 `dict` 作为输入，而非 `SignalAttempt` 对象：

```python
class AttributionEngine:
    def attribute(self, attempt_dict: Dict[str, Any]) -> SignalAttribution:
        """
        从回测引擎序列化的 attempt dict 计算归因。

        attempt_dict 结构:
        {
            "strategy_name": "pinbar",
            "pattern": {"score": 0.72, "direction": "LONG", ...} | None,
            "filter_results": [(filter_name, {"passed": bool, "reason": str, "metadata": {...}}), ...],
            "final_result": "SIGNAL_FIRED" | "NO_PATTERN" | "FILTERED",
            "kline_timestamp": 1234567890
        }
        """
```

在回测报告中，归因通过以下方式集成：
```python
# 在 _run_v3_pms_backtest() 结束时
from src.application.config_manager import ConfigManager
from src.application.attribution_engine import AttributionEngine, AttributionConfig

# Step 1: 从 KV 加载归因配置
kv_configs = await config_manager.get_backtest_configs()
config = AttributionConfig.from_kv(kv_configs)

# Step 2: 对所有 attempts 批量计算归因
engine = AttributionEngine(config)
signal_attributions = [
    engine.attribute(_attempt_to_dict(a))
    for a in attempts
    if a.final_result == "SIGNAL_FIRED"
]

# Step 3: 填充到报告
report.signal_attributions = signal_attributions
report.aggregate_attribution = engine.get_aggregate_attribution(signal_attributions)
```

#### 3.2.4 元数据契约

每个信心函数都是确定性的数学公式，可追溯可验证。

**信心函数表**:

| 过滤器 | 公式 | 参数 | 范围 |
|--------|------|------|------|
| ema_trend | `min(distance_pct / 0.05, 1.0)` | distance_pct = \|price - ema\| / ema | 0 ~ 1 |
| mtf | `aligned_count / total_count` | 高周期趋势对齐比例 | 0 ~ 1 |
| atr | `min(atr_ratio / 2.0, 1.0)` | atr_ratio = candle_range / ATR | 0 ~ 1 |

**必需元数据表**:

| 过滤器 | 必需字段 | 类型 | 示例 |
|--------|---------|------|------|
| ema_trend | `price` | float | `65432.10` |
| ema_trend | `ema_value` | float | `64200.00` |
| ema_trend | `trend_direction` | str | `"bullish"` |
| mtf | `higher_tf_trends` | Dict | `{"1h": "bullish", "4h": "bearish"}` |
| mtf | `aligned_count` | int | `1` |
| mtf | `total_count` | int | `2` |
| atr | `atr_ratio` | float | `1.5` |

当 metadata 缺少必需字段时，归因引擎会：
1. 记录 WARNING 日志
2. 使用默认信心值 `0.5`
3. `confidence_basis` 中标注 "metadata incomplete"

#### 3.2.5 前端展示数据结构

```json
{
  "signal_id": "sig_abc123",
  "final_score": 0.728,
  "attribution": {
    "pattern": { "score": 0.72, "weight": 0.55, "contribution": 0.396, "percentage": 54.4 },
    "ema_trend": { "score": 0.80, "weight": 0.25, "contribution": 0.200, "percentage": 27.5 },
    "mtf": { "score": 0.67, "weight": 0.20, "contribution": 0.134, "percentage": 18.1 }
  },
  "explanation": "Pinbar 形态(54.4%) + EMA 趋势确认(27.5%) + 多周期对齐(18.1%)"
}
```

### 3.3 优缺点

| 维度 | 评价 |
|------|------|
| **优点** | |
| 非侵入式 | 不修改 `FilterBase` 接口，现有过滤器零改动 |
| 快速实现 | 约 1-2 天（AttributionEngine + metadata 补充 + API） |
| 保持领域层纯净 | AttributionEngine 放在 `application/` 层 |
| 可迭代优化 | 信心函数和权重可随时调整，不影响核心逻辑 |
| **缺点** | |
| 数学上不精确 | 信心函数是启发式的，非过滤器内部真实评分 |
| 依赖 metadata 完整性 | 如果 metadata 缺少关键字段，信心评分会降级为默认值 |
| 权重仍是主观的 | pattern:filter 权重比需要经验调参 |
| 无法实时拒绝 | 归因只在信号产生后计算，不参与决策 |

---

## 4. 方案对比

| 维度 | 方案 A: 过滤器评分化 | 方案 B: 归因解释层 |
|------|---------------------|-------------------|
| **侵入性** | 高（修改 FilterBase + 所有过滤器） | 低（新增独立引擎） |
| **数学精确性** | 高（过滤器直接返回评分） | 中（启发式信心近似） |
| **实现工作量** | 3-4 天 | 1-2 天 |
| **实时性** | 实时（评分即决策） | 事后（信号产生后分析） |
| **可解释性** | 精确（每个组件有明确评分函数） | 近似（信心函数模拟评分） |
| **可维护性** | 中（每个过滤器需维护评分逻辑） | 高（归因逻辑集中在一个类） |
| **扩展性** | 中（新过滤器需实现 score()） | 高（新过滤器只需补充 metadata） |
| **回测兼容** | 需要修改回测引擎 | 直接复用现有 attempts 数据 |

---

## 5. 推荐方案

### 推荐：方案 B（归因解释层）→ 渐进式升级到方案 A

**理由**:

1. **快速验证价值**: 方案 B 1-2 天即可上线，用户可以先看到归因效果
2. **风险低**: 不修改核心接口，不会破坏现有功能
3. **数据驱动**: 上线后收集真实信号的 metadata 数据，为方案 A 的评分函数设计提供依据
4. **渐进路径**: 当某个过滤器的信心函数被验证有效后，可将其升级为方案 A 的 `score()` 方法

### 实施路径

```
Phase B-1 (1天): 归因引擎核心
  ├── 新增 src/application/attribution_engine.py
  ├── 补充过滤器 metadata（EMA distance, MTF alignment）
  └── 集成到回测报告输出

Phase B-2 (0.5天): API 扩展
  ├── 新增归因查询 API 端点
  └── 在 SignalResult 中增加 attribution 字段

Phase B-3 (0.5天): 前端适配
  ├── 信号详情页增加归因展示
  └── 回测报告增加归因维度图表
```

---

## 6. 关键设计决策

### 决策 1: 权重配置方式

**选择**: KV 配置 + `AttributionConfig` Pydantic 校验层 + 前端受控表单

**存储方式**: 复用现有 `ConfigEntryRepository`（SQLite KV 存储），通过 `ConfigManager.get_backtest_configs()` / `save_backtest_configs()` 读写。

**KV Key 列表**:
| Key | 默认值 | 说明 |
|-----|--------|------|
| `attribution_weight_pattern` | `0.55` | 形态质量权重 |
| `attribution_weight_ema_trend` | `0.25` | EMA 趋势过滤器权重 |
| `attribution_weight_mtf` | `0.20` | 多周期对齐过滤器权重 |

**校验层** (`AttributionConfig`):
```python
from pydantic import BaseModel, field_validator

class AttributionConfig(BaseModel):
    """归因配置校验模型 — 从 KV 配置加载并校验"""
    weights: Dict[str, float]

    @field_validator('weights')
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        # 1. 必须包含必需的 key
        required = {"pattern", "ema_trend", "mtf"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"缺少必需的归因权重: {missing}")
        # 2. 权重和必须 ≈ 1.0
        total = sum(v.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"权重之和必须接近 1.0，当前: {total}")
        # 3. 每个权重必须在 [0, 1] 范围内
        for k, val in v.items():
            if not 0 <= val <= 1:
                raise ValueError(f"权重 {k}={val} 超出 [0, 1] 范围")
        return v

    @classmethod
    def from_kv(cls, kv_configs: Dict[str, Any]) -> "AttributionConfig":
        """从 KV 配置加载并校验"""
        weights = {
            "pattern": float(kv_configs.get("attribution_weight_pattern", 0.55)),
            "ema_trend": float(kv_configs.get("attribution_weight_ema_trend", 0.25)),
            "mtf": float(kv_configs.get("attribution_weight_mtf", 0.20)),
        }
        return cls(weights=weights)
```

**风险缓解**:
- Pydantic 校验层拦截脏数据（权重和≈1.0、范围[0,1]、必需 key）
- 前端只暴露固定表单（3 个输入框），不开放自由添加 KV key

**理由**: 项目已没有 YAML 配置文件（仅用于导入导出备份），KV 配置与现有回测参数体系一致（slippage_rate、fee_rate 等均用 KV 存储）。
不支持动态学习（太复杂，需要历史数据训练）。

### 决策 2: 归因是否影响信号触发

**选择**: 归因不影响信号触发，仅作为解释层

**理由**:
- 信号触发由过滤器布尔决策决定（保持确定性）
- 归因是事后分析，不改变决策逻辑
- 避免引入新的复杂性（如"评分低于阈值不触发"）

### 决策 4: 权重范围（P2-2）

**选择**: 全局权重，不按策略配置

**理由**: 归因权重是"解释工具"而非"优化参数"，全局权重确保不同策略间的归因结果可对比。
当前只有 pinbar/engulfing 两种策略，过滤器集合重叠度高，不需要按策略配置。
未来如果策略差异变大，可以引入 `attribution_weight_{strategy}_{filter}` 命名空间。

### 决策 3: 归因引擎放置位置

**选择**: `src/application/attribution_engine.py`

**理由**:
- 不是领域逻辑（不应在 `domain/`）
- 需要访问 `SignalAttempt` 和 `FilterResult`（在 `application/` 层最合适）
- 与 `AttributionAnalyzer`（现有回测归因）并列

---

## 7. 接口契约

### 7.1 归因引擎接口

```python
class AttributionEngine:
    def attribute(self, attempt: SignalAttempt) -> SignalAttribution:
        """单信号归因分析"""

    def attribute_batch(self, attempts: List[SignalAttempt]) -> List[SignalAttribution]:
        """批量归因"""

    def get_aggregate_attribution(self, attempts: List[SignalAttempt]) -> AggregateAttribution:
        """聚合归因（用于回测报告摘要）"""
```

### 7.2 响应模型

```python
class SignalAttribution(BaseModel):
    """单信号归因"""
    final_score: float
    components: List[AttributionComponent]
    percentages: Dict[str, float]
    explanation: str  # 人类可读的解释文本


class AttributionComponent(BaseModel):
    name: str
    score: float       # 0~1 组件评分
    weight: float      # 预设权重
    contribution: float  # score × weight
    percentage: float    # contribution / final_score × 100
    confidence_basis: str  # 信心评分的依据描述
    status: str = "passed"  # "passed" 或 "rejected"，标记过滤器是否通过


@dc_dataclass
class FilterScore:
    """过滤器评分（内部使用，不序列化）"""
    filter_name: str
    score: Decimal
    weight: Decimal
    contribution: Decimal
    reason: str
    metadata: Dict[str, Any]
    confidence_basis: str
    status: str = "passed"  # "passed" 或 "rejected"


class AggregateAttribution(BaseModel):
    """聚合归因（回测报告级别）"""
    avg_pattern_contribution: float
    avg_filter_contributions: Dict[str, float]
    top_performing_filters: List[str]
    worst_performing_filters: List[str]
```

### 7.3 API 端点

```
GET /api/signals/{signal_id}/attribution
  → SignalAttribution

GET /api/backtests/{report_id}/attribution/summary
  → AggregateAttribution

GET /api/backtests/{report_id}/attribution/signals
  → List[SignalAttribution]
```

---

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| metadata 缺失导致信心评分不准确 | 中 | 提供合理的默认值 + 日志告警 |
| 权重配置不合理导致归因失真 | 中 | 提供预设配置 + 文档说明调参方法 |
| 用户对归因结果过度信任 | 低 | 在 UI 中明确标注"归因为近似分析" |
| 归因计算增加响应延迟 | 低 | 归因逻辑简单，单次计算 < 1ms |

---

## 9. 后续演进

当方案 B 运行一段时间后，可以考虑：

1. **权重学习**: 基于历史回测数据，用网格搜索找到最优权重组合
2. **过滤器评分化迁移**: 将验证有效的信心函数升级为过滤器的 `score()` 方法（方案 A）
3. **实时归因**: 在 WebSocket 信号推送中直接包含 attribution 字段
4. **归因可视化**: 前端增加雷达图、瀑布图等可视化展示

---

---

## 10. QA 审查修复记录

> **审查日期**: 2026-04-15
> **审查人**: QA Agent
> **修复状态**: ✅ 已完成

### P0 修复

| # | 问题 | 修复 |
|---|------|------|
| P0-1 | `FilterBase.check()` 返回类型写错为 `TraceEvent` | 修正为 `FilterResult(passed: bool, reason: str, metadata: Dict)` |
| P0-2 | API 扩展中 `get_signal_attempt()` / `get_backtest_attempts()` 方法不存在 | 改为接受 `dict` 输入，归因在 `_run_v3_pms_backtest()` 中直接调用 |

### P1 修复

| # | 问题 | 修复 |
|---|------|------|
| P1-1 | `SignalAttempt.filter_results` 类型注解为 bare `list` | 已在 task_plan 中标注为实施任务 |
| P1-2 | Pydantic v1 `@validator` 语法 | 改为 Pydantic v2 `@field_validator` + `@classmethod` |
| P1-3 | MTF 信心函数 `Decimal(str(aligned / total))` float 混用 | 改为 `Decimal(str(aligned)) / Decimal(str(total))` |
| P1-4 | `AttributionEngine` 与 `AttributionAnalyzer` 命名关系不明 | 新增 3.2.2 节"与 AttributionAnalyzer 的关系"对比表 |
| P1-5 | FILTERED 信号的被拒绝过滤器被忽略 | 所有过滤器都处理，被拒绝的标记 `status="rejected"`，score=0 |
| P1-6 | metadata 缺失时无告警 | 信心函数中增加 `logger.warning()` 告警 |

### P2 修复

| # | 问题 | 修复 |
|---|------|------|
| P2-1 | `SignalResult` 模型变更未指定 | 新增 `FilterScore` 和 `AttributionComponent.status` 字段定义 |
| P2-2 | 全局权重按策略配置问题 | 新增决策 4，文档说明全局权重是按设计 |
| P2-3 | zero-score 时 percentages 显示 `{"pattern": 100.0}` | 改为 `{}`，不伪造百分比 |

---

