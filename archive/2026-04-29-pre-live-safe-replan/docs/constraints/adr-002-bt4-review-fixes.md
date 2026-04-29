# BT-4 策略归因分析功能代码审查修复方案设计

**文档编号**: ADR-002  
**创建日期**: 2026-04-06  
**状态**: 待审批  
**优先级**: Critical > Important > Minor

---

## 一、背景与概述

BT-4 策略归因分析功能是回测系统的核心分析模块，提供四个维度的归因分析：
- **B 维度**: 形态质量归因（Pinbar 评分与表现的关系）
- **C 维度**: 过滤器归因（各过滤器对策略表现的影响）
- **D 维度**: 市场趋势归因（不同市场趋势下的交易表现）
- **F 维度**: 盈亏比归因（不同盈亏比设置下的表现）

本文档针对代码审查中发现的问题提供详细的修复方案设计。

---

## 二、问题清单与修复方案

### Critical 问题（必须修复）

#### C-01: `_compare_score_performance` 方法存在除零错误风险

**问题描述**:  
在 `src/application/attribution_analyzer.py` 的 `_compare_score_performance` 方法中，调用 `_calculate_win_rate` 时未考虑空列表情况，虽然 `_calculate_win_rate` 内部有保护，但代码可读性差。

**根因分析**:
```python
def _compare_score_performance(self, high_score: List[Dict], low_score: List[Dict]) -> str:
    high_win_rate = self._calculate_win_rate(high_score)  # 空列表时 safe，但意图不明确
    low_win_rate = self._calculate_win_rate(low_score)
```

**修复方案**:
在调用比较方法前增加空列表检查，提高代码可读性和防御性。

**修改位置**: `src/application/attribution_analyzer.py:118-120`

**建议实现**:
```python
# 原代码 (第 118-119 行)
"analysis": {
    "high_score_performs_better": self._compare_score_performance(high_score, low_score),
},

# 修改后
"analysis": {
    "high_score_performs_better": self._compare_score_performance(high_score, low_score) if high_score or low_score else "数据不足",
},
```

同时更新 `_compare_score_performance` 方法增加防御性检查：
```python
def _compare_score_performance(self, high_score: List[Dict], low_score: List[Dict]) -> str:
    """比较高分组和低分组的表现"""
    if not high_score and not low_score:
        return "数据不足"
    if not high_score:
        return "仅有低分组数据"
    if not low_score:
        return "仅有高分组数据"
    
    high_win_rate = self._calculate_win_rate(high_score)
    low_win_rate = self._calculate_win_rate(low_score)

    if high_win_rate > low_win_rate:
        return "高分组表现更优"
    elif low_win_rate > high_win_rate:
        return "低分组表现更优"
    else:
        return "两组表现相近"
```

**影响范围**: 
- 仅影响归因分析报告的 `analysis` 字段输出
- 不会破坏现有 API 接口兼容性

**测试要求**:
```python
def test_compare_score_performance_with_empty_lists(self):
    """测试空列表时的边界情况"""
    analyzer = AttributionAnalyzer()
    
    # 两组都为空
    result = analyzer._compare_score_performance([], [])
    assert result == "数据不足"
    
    # 仅高分组为空
    result = analyzer._compare_score_performance([], [{"pnl_ratio": 1.0}])
    assert result == "仅有低分组数据"
    
    # 仅低分组为空
    result = analyzer._compare_score_performance([{"pnl_ratio": 1.0}], [])
    assert result == "仅有高分组数据"
```

---

#### C-02: `_analyze_trend` 方法存在除零错误风险

**问题描述**:  
在 `_analyze_trend` 方法第 198 行，计算 `alignment_ratio` 时虽然已有三元运算符保护，但代码风格不一致。

**根因分析**:
```python
# 第 198 行 - 已有保护，但可改进
"alignment_ratio": aligned_trades / len(fired_signals) if fired_signals else 0.0,
```

**修复方案**:
将该计算抽取到辅助方法 `_calculate_alignment_ratio` 中，保持代码一致性。

**修改位置**: `src/application/attribution_analyzer.py:184-199`

**建议实现**:
```python
def _analyze_trend(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """维度 D: 市场趋势归因分析"""
    fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]

    bullish_trend = [s for s in fired_signals if self._get_trend_direction(s) == "bullish"]
    bearish_trend = [s for s in fired_signals if self._get_trend_direction(s) == "bearish"]

    aligned_trades = self._count_aligned_trades(fired_signals)
    against_trend = len(fired_signals) - aligned_trades
    
    total_signals = len(fired_signals)

    return {
        "bullish_trend": {
            "trade_count": len(bullish_trend),
            "win_rate": self._calculate_win_rate(bullish_trend),
            "avg_pnl": self._calculate_avg_pnl(bullish_trend),
        },
        "bearish_trend": {
            "trade_count": len(bearish_trend),
            "win_rate": self._calculate_win_rate(bearish_trend),
            "avg_pnl": self._calculate_avg_pnl(bearish_trend),
        },
        "alignment_stats": {
            "aligned_trades": aligned_trades,
            "against_trend_trades": against_trend,
            "alignment_ratio": self._calculate_alignment_ratio(aligned_trades, total_signals),
        },
    }

# 新增辅助方法
def _calculate_alignment_ratio(self, aligned_trades: int, total_trades: int) -> float:
    """计算顺势交易比例"""
    if total_trades == 0:
        return 0.0
    return aligned_trades / total_trades
```

**影响范围**: 
- 代码重构，不影响功能逻辑
- 提高代码可测试性

**测试要求**:
```python
def test_calculate_alignment_ratio_with_zero_total(self):
    """测试零总数时的边界情况"""
    analyzer = AttributionAnalyzer()
    result = analyzer._calculate_alignment_ratio(0, 0)
    assert result == 0.0
    
def test_calculate_alignment_ratio_normal(self):
    """测试正常情况"""
    analyzer = AttributionAnalyzer()
    result = analyzer._calculate_alignment_ratio(75, 100)
    assert result == 0.75
```

---

#### C-03: `AttributionAnalysisRequest` 缺少字段验证器

**问题描述**:  
`AttributionAnalysisRequest` 类缺少字段验证器，允许 `report_id` 和 `backtest_report` 同时为空或同时存在，可能导致运行时错误。

**根因分析**:
```python
# src/interfaces/api.py:1723-1726
class AttributionAnalysisRequest(BaseModel):
    """归因分析请求"""
    report_id: Optional[str] = Field(None, description="回测报告 ID（从数据库加载）")
    backtest_report: Optional[Dict[str, Any]] = Field(None, description="直接传入回测报告数据")
```

当前设计允许：
- 两个字段都为 `None` ❌
- 两个字段都不为 `None` ⚠️（优先级不明确）

**修复方案**:
使用 Pydantic 的 `model_validator` 添加互斥验证。

**修改位置**: `src/interfaces/api.py:1723-1735`

**建议实现**:
```python
from pydantic import BaseModel, Field, model_validator, ValidationError
from typing import Optional, Dict, Any

class AttributionAnalysisRequest(BaseModel):
    """归因分析请求"""
    report_id: Optional[str] = Field(None, description="回测报告 ID（从数据库加载）")
    backtest_report: Optional[Dict[str, Any]] = Field(None, description="直接传入回测报告数据")
    
    @model_validator(mode='after')
    def validate_mutually_exclusive_fields(self):
        """验证 report_id 和 backtest_report 有且仅有一个存在"""
        if self.report_id is None and self.backtest_report is None:
            raise ValueError("必须提供 report_id 或 backtest_report 其中之一")
        return self
    
    def has_report_data(self) -> bool:
        """检查是否直接提供了回测报告数据"""
        return self.backtest_report is not None
    
    def get_report_id(self) -> Optional[str]:
        """获取报告 ID"""
        return self.report_id
```

**影响范围**:
- API 请求验证更严格，会拒绝无效请求
- 需要在 API 端点处理验证异常

**测试要求**:
```python
def test_attribution_request_requires_one_field():
    """测试请求必须提供至少一个字段"""
    with pytest.raises(ValidationError) as exc_info:
        AttributionAnalysisRequest()
    assert "必须提供 report_id 或 backtest_report" in str(exc_info.value)

def test_attribution_request_accepts_report_id():
    """测试接受 report_id"""
    request = AttributionAnalysisRequest(report_id="test-id")
    assert request.report_id == "test-id"

def test_attribution_request_accepts_backtest_report():
    """测试接受 backtest_report"""
    request = AttributionAnalysisRequest(backtest_report={"attempts": []})
    assert request.backtest_report is not None
```

---

### Important 问题（应该修复）

#### I-01: `filter_attribution` 的 `impact_on_win_rate` 硬编码为 0.0

**问题描述**:  
在 `_analyze_filters` 方法中，`impact_on_win_rate` 字段硬编码为 `0.0`，未实际计算 EMA/MTF 过滤器对胜率的真实影响。

**根因分析**:
```python
# src/application/attribution_analyzer.py:147-163
return {
    "ema_filter": {
        "enabled_trades": len(ema_enabled),
        "passed_trades": len(ema_passed),
        "disabled_trades": len(ema_disabled),
        "win_rate_with_ema": self._calculate_win_rate(ema_passed),
        "impact_on_win_rate": 0.0,  # ❌ 硬编码
    },
    ...
}
```

**修复方案**:
计算启用过滤器与禁用过滤器时的胜率差异。

**修改位置**: `src/application/attribution_analyzer.py:147-163`

**建议实现**:
```python
def _analyze_filters(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """维度 C: 过滤器归因分析"""
    fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]
    filtered_signals = [a for a in attempts if a.get("final_result") == "FILTERED"]

    # 分析 EMA 过滤器
    ema_enabled = [s for s in fired_signals if self._has_filter(s, "ema_trend")]
    ema_passed = [s for s in fired_signals if self._filter_passed(s, "ema_trend")]
    ema_disabled = [s for s in fired_signals if self._has_filter(s, "ema_trend") and not self._filter_passed(s, "ema_trend")]
    
    # 分析 MTF 过滤器
    mtf_enabled = [s for s in fired_signals if self._has_filter(s, "mtf")]
    mtf_passed = [s for s in fired_signals if self._filter_passed(s, "mtf")]
    mtf_disabled = [s for s in fired_signals if self._has_filter(s, "mtf") and not self._filter_passed(s, "mtf")]

    # 过滤器拒绝统计
    rejection_stats = self._calculate_rejection_stats(filtered_signals)
    
    # 计算过滤器影响（通过过滤器的胜率 - 被过滤器拒绝的模拟胜率）
    ema_impact = self._calculate_filter_impact(ema_passed, ema_disabled)
    mtf_impact = self._calculate_filter_impact(mtf_passed, mtf_disabled)

    return {
        "ema_filter": {
            "enabled_trades": len(ema_enabled),
            "passed_trades": len(ema_passed),
            "disabled_trades": len(ema_disabled),
            "win_rate_with_ema": self._calculate_win_rate(ema_passed),
            "win_rate_without_ema": self._calculate_win_rate(ema_disabled),
            "impact_on_win_rate": ema_impact,
        },
        "mtf_filter": {
            "enabled_trades": len(mtf_enabled),
            "passed_trades": len(mtf_passed),
            "disabled_trades": len(mtf_disabled),
            "win_rate_with_mtf": self._calculate_win_rate(mtf_passed),
            "win_rate_without_mtf": self._calculate_win_rate(mtf_disabled),
            "impact_on_win_rate": mtf_impact,
        },
        "rejection_stats": rejection_stats,
    }

# 新增辅助方法
def _calculate_filter_impact(self, passed: List[Dict], disabled: List[Dict]) -> float:
    """计算过滤器对胜率的影响"""
    passed_win_rate = self._calculate_win_rate(passed)
    disabled_win_rate = self._calculate_win_rate(disabled)
    # 正向影响：通过过滤器的胜率高于被拒绝的
    return round(passed_win_rate - disabled_win_rate, 4)
```

**影响范围**:
- `filter_attribution` 响应结构新增 `win_rate_without_ema` 和 `win_rate_without_mtf` 字段
- `impact_on_win_rate` 将返回实际计算值

**测试要求**:
```python
def test_filter_impact_calculation():
    """测试过滤器影响计算"""
    analyzer = AttributionAnalyzer()
    
    passed = [{"pnl_ratio": 2.0}, {"pnl_ratio": 1.5}, {"pnl_ratio": -1.0}]  # 2/3 = 66.7%
    disabled = [{"pnl_ratio": -1.0}, {"pnl_ratio": -0.5}]  # 0/2 = 0%
    
    impact = analyzer._calculate_filter_impact(passed, disabled)
    assert impact > 0  # 正向影响
```

---

#### I-02: `optimal_range.suggested_rr` 返回格式不正确

**问题描述**:  
`_analyze_rr` 方法中 `optimal_range.suggested_rr` 返回的是字符串（如 "high"、"medium"），应该返回更明确的盈亏比区间描述。

**根因分析**:
```python
# src/application/attribution_analyzer.py:251-254
"optimal_range": {
    "suggested_rr": optimal_group.replace("_rr", ""),  # 返回 "high"、"medium"、"low"
    "reasoning": f"最多交易落在该区间 ({len(groups.get(optimal_group, []))} 笔)",
},
```

**修复方案**:
返回具体的盈亏比区间范围而非组名。

**修改位置**: `src/application/attribution_analyzer.py:251-255`

**建议实现**:
```python
# 在类级别定义最优范围映射
RR_RANGE_MAP = {
    "high_rr": "2:1 以上",
    "medium_rr": "1:1 - 2:1",
    "low_rr": "0:1 - 1:1",
}

def _analyze_rr(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """维度 F: 盈亏比归因分析"""
    fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED" and a.get("pnl_ratio") is not None]

    # 按盈亏比分组
    high_rr = [s for s in fired_signals if s.get("pnl_ratio", 0) > self.HIGH_RR_THRESHOLD]
    medium_rr = [s for s in fired_signals if self.MEDIUM_RR_THRESHOLD <= s.get("pnl_ratio", 0) <= self.HIGH_RR_THRESHOLD]
    low_rr = [s for s in fired_signals if 0 < s.get("pnl_ratio", 0) < self.MEDIUM_RR_THRESHOLD]
    stop_loss = [s for s in fired_signals if s.get("pnl_ratio", 0) < 0]

    def group_stats(signals: List[Dict]) -> Dict[str, Any]:
        return {
            "count": len(signals),
            "win_rate": self._calculate_win_rate(signals),
            "avg_pnl": self._calculate_avg_pnl(signals),
        }

    # 识别最优盈亏比区间（按胜率排序，而非交易数量）
    groups = {
        "high_rr": high_rr,
        "medium_rr": medium_rr,
        "low_rr": low_rr,
    }
    
    # 计算各组胜率，找出最优组
    group_win_rates = {k: self._calculate_win_rate(v) for k, v in groups.items() if v}
    optimal_group = max(group_win_rates.keys(), key=lambda k: group_win_rates[k]) if group_win_rates else "medium_rr"
    
    # 计算最优组的平均 PnL
    optimal_avg_pnl = self._calculate_avg_pnl(groups.get(optimal_group, []))

    return {
        "high_rr": {
            **group_stats(high_rr),
            "threshold": f"> {int(self.HIGH_RR_THRESHOLD)}:1",
        },
        "medium_rr": {
            **group_stats(medium_rr),
            "threshold": f"{int(self.MEDIUM_RR_THRESHOLD)}:1 - {int(self.HIGH_RR_THRESHOLD)}:1",
        },
        "low_rr": {
            **group_stats(low_rr),
            "threshold": f"< {int(self.MEDIUM_RR_THRESHOLD)}:1 (盈利)",
        },
        "stop_loss": {
            **group_stats(stop_loss),
            "threshold": "< 0:1 (止损)",
        },
        "optimal_range": {
            "suggested_rr": self.RR_RANGE_MAP.get(optimal_group, "1:1 - 2:1"),
            "reasoning": f"该区间胜率最高 ({group_win_rates.get(optimal_group, 0):.1%})，平均盈亏比 {optimal_avg_pnl:.2f}",
            "optimal_group": optimal_group.replace("_rr", ""),
        },
    }
```

**影响范围**:
- `suggested_rr` 返回中文描述（如 "2:1 以上"）
- 新增 `optimal_group` 字段保留原始组名供程序使用
- `reasoning` 字段信息更丰富

**测试要求**:
```python
def test_optimal_range_returns_readable_format():
    """测试最优区间返回可读格式"""
    analyzer = AttributionAnalyzer()
    report = analyzer.analyze(sample_backtest_report)
    
    optimal = report.rr_attribution["optimal_range"]
    assert optimal["suggested_rr"] in ["2:1 以上", "1:1 - 2:1", "0:1 - 1:1"]
    assert "optimal_group" in optimal
```

---

#### I-03: 集成测试中 `test_client` fixture 存在资源泄漏风险

**问题描述**:  
在 `tests/integration/test_attribution_api.py` 中，`test_client` fixture 没有正确清理 FastAPI lifespan 中创建的资源。

**根根分析**:
```python
# tests/integration/test_attribution_api.py:54-66
@pytest.fixture
def test_client():
    """创建 FastAPI 测试客户端"""
    from src.interfaces.api import app

    mock_account_getter = Mock(return_value=None)

    with patch('src.interfaces.api._get_repository', return_value=Mock()):
        with patch('src.interfaces.api._account_getter', mock_account_getter):
            with patch('src.interfaces.api._get_exchange_gateway', return_value=Mock()):
                client = TestClient(app)
                yield client
                # ❌ 缺少资源清理
```

**修复方案**:
使用 `TestClient` 的上下文管理器确保资源正确关闭，或显式调用清理方法。

**修改位置**: `tests/integration/test_attribution_api.py:54-67`

**建议实现**:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


@pytest.fixture
def test_client():
    """创建 FastAPI 测试客户端（带资源清理）"""
    from src.interfaces.api import app

    mock_account_getter = Mock(return_value=None)

    with patch('src.interfaces.api._get_repository', return_value=Mock()):
        with patch('src.interfaces.api._account_getter', mock_account_getter):
            with patch('src.interfaces.api._get_exchange_gateway', return_value=Mock()):
                # 使用 TestClient 的上下文管理器确保资源清理
                with TestClient(app) as client:
                    yield client
```

**影响范围**:
- 测试资源管理更健壮
- 避免测试间的状态污染

**测试要求**:
无需额外测试，运行现有测试套件验证无资源泄漏警告。

---

#### I-04: `AttributionReport` 缺少版本字段

**问题描述**:  
`AttributionReport` 模型缺少版本字段，不利于后续 API 演进和数据分析。

**根因分析**:
```python
# src/domain/models.py:1264-1277
class AttributionReport(FinancialModel):
    """策略归因分析报告"""
    shape_quality: Dict[str, Any] = Field(default_factory=dict, description="形态质量归因")
    filter_attribution: Dict[str, Any] = Field(default_factory=dict, description="过滤器归因")
    trend_attribution: Dict[str, Any] = Field(default_factory=dict, description="市场趋势归因")
    rr_attribution: Dict[str, Any] = Field(default_factory=dict, description="盈亏比归因")
    # ❌ 缺少版本字段
```

**修复方案**:
添加版本字段和元数据字段。

**修改位置**: `src/domain/models.py:1264-1278`

**建议实现**:
```python
class AttributionReport(FinancialModel):
    """
    策略归因分析报告

    包含四个维度的归因分析结果：
    - shape_quality: 形态质量归因（B 维度）
    - filter_attribution: 过滤器归因（C 维度）
    - trend_attribution: 市场趋势归因（D 维度）
    - rr_attribution: 盈亏比归因（F 维度）
    """
    version: str = Field(default="1.0.0", description="归因分析报告版本")
    shape_quality: Dict[str, Any] = Field(default_factory=dict, description="形态质量归因")
    filter_attribution: Dict[str, Any] = Field(default_factory=dict, description="过滤器归因")
    trend_attribution: Dict[str, Any] = Field(default_factory=dict, description="市场趋势归因")
    rr_attribution: Dict[str, Any] = Field(default_factory=dict, description="盈亏比归因")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据（分析时间、数据源等）")
```

同时在 `AttributionAnalyzer.analyze()` 方法中设置版本：
```python
def analyze(self, backtest_report: Dict[str, Any]) -> AttributionReport:
    """执行完整的归因分析"""
    attempts = backtest_report.get("attempts", [])
    
    from datetime import datetime, timezone
    
    return AttributionReport(
        version="1.0.0",
        shape_quality=self._analyze_shape_quality(attempts),
        filter_attribution=self._analyze_filters(attempts),
        trend_attribution=self._analyze_trend(attempts),
        rr_attribution=self._analyze_rr(attempts),
        metadata={
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "total_attempts": len(attempts),
            "fired_signals": len([a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]),
        },
    )
```

**影响范围**:
- 响应结构新增 `version` 和 `metadata` 字段
- 向后兼容（有默认值）

**测试要求**:
```python
def test_attribution_report_has_version():
    """测试报告包含版本字段"""
    from src.application.attribution_analyzer import AttributionAnalyzer
    
    analyzer = AttributionAnalyzer()
    report = analyzer.analyze(sample_backtest_report)
    
    assert report.version == "1.0.0"
    assert "analyzed_at" in report.metadata
    assert "total_attempts" in report.metadata
```

---

### Minor 问题（建议修复）

#### M-04: 日志缺少上下文信息

**问题描述**:  
在 API 端点中，错误日志缺少关键上下文信息（如 report_id、用户 ID 等），不利于问题排查。

**根因分析**:
```python
# src/interfaces/api.py:1820
logger.error(f"Attribution analysis failed: {e}")
# ❌ 缺少 report_id 上下文
```

**修复方案**:
在日志中添加关键上下文信息。

**修改位置**: `src/interfaces/api.py:1820, 1883`

**建议实现**:
```python
@app.post("/api/backtest/{report_id}/attribution", response_model=AttributionAnalysisResponse)
async def analyze_backtest_attribution(report_id: str):
    """对回测报告进行策略归因分析"""
    try:
        # ... 现有代码 ...
    except Exception as e:
        logger.error(f"Attribution analysis failed for report_id={report_id}: {type(e).__name__} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest/attribution/preview", response_model=AttributionAnalysisResponse)
async def preview_backtest_attribution(request: AttributionAnalysisRequest):
    """预览归因分析"""
    try:
        # ... 现有代码 ...
    except Exception as e:
        request_context = "backtest_report" if request.backtest_report else f"report_id={request.report_id}"
        logger.error(f"Attribution preview failed for {request_context}: {type(e).__name__} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
```

**影响范围**:
- 日志格式变更，更易于问题排查
- 不影响功能逻辑

**测试要求**:
无需额外测试，可通过手动验证日志输出。

---

## 三、实施顺序与依赖关系

### 修复优先级

| 优先级 | 问题编号 | 问题描述 | 预计工时 | 依赖关系 |
|--------|----------|----------|----------|----------|
| P0 | C-01 | _compare_score_performance 除零风险 | 0.5h | 无 |
| P0 | C-02 | _analyze_trend 除零风险 | 0.5h | 无 |
| P0 | C-03 | AttributionAnalysisRequest 缺少验证器 | 1h | 无 |
| P1 | I-01 | filter_attribution 硬编码 0.0 | 1h | 无 |
| P1 | I-02 | optimal_range.suggested_rr 格式不正确 | 1h | 无 |
| P1 | I-03 | test_client fixture 资源泄漏 | 0.5h | 无 |
| P1 | I-04 | AttributionReport 缺少版本字段 | 1h | 无 |
| P2 | M-04 | 日志缺少上下文信息 | 0.5h | 无 |

### 实施顺序建议

```
阶段 1: Critical 修复 (C-01, C-02, C-03)
  └─ 目标：消除运行时错误风险
  └─ 预计：2h

阶段 2: Important 功能修复 (I-01, I-02)
  └─ 目标：修复核心功能缺陷
  └─ 预计：2h

阶段 3: Important 质量修复 (I-03, I-04)
  └─ 目标：提升代码质量和可维护性
  └─ 预计：1.5h

阶段 4: Minor 优化 (M-04)
  └─ 目标：提升可维护性
  └─ 预计：0.5h
```

---

## 四、测试计划

### 单元测试新增/更新

| 测试文件 | 新增测试用例 | 优先级 |
|----------|--------------|--------|
| `test_attribution_analyzer.py` | `test_compare_score_performance_with_empty_lists` | P0 |
| `test_attribution_analyzer.py` | `test_calculate_alignment_ratio_with_zero_total` | P0 |
| `test_attribution_analyzer.py` | `test_filter_impact_calculation` | P1 |
| `test_attribution_analyzer.py` | `test_optimal_range_returns_readable_format` | P1 |
| `test_attribution_analyzer.py` | `test_attribution_report_has_version` | P1 |
| `test_attribution_api.py` | `test_attribution_request_requires_one_field` | P0 |

### 集成测试验证

运行现有测试套件，确保所有修复不破坏现有功能：
```bash
pytest tests/unit/test_attribution_analyzer.py -v
pytest tests/integration/test_attribution_api.py -v
```

---

## 五、风险评估

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| API 响应结构变更导致前端不兼容 | 低 | 中 | version 字段有默认值，向后兼容 |
| 新增验证器导致现有客户端失败 | 中 | 低 | 在下一个 breaking change 版本中生效 |
| 测试 fixture 变更影响其他测试 | 低 | 低 | 仅影响 attribution 相关测试 |

---

## 六、验收标准

1. **Critical 问题全部修复**：C-01、C-02、C-03 必须有对应的代码修复和测试覆盖
2. **Important 问题修复率≥80%**：I-01 至 I-04 至少修复 3 个
3. **所有单元测试通过**：`pytest tests/unit/test_attribution_analyzer.py` 全部通过
4. **所有集成测试通过**：`pytest tests/integration/test_attribution_api.py` 全部通过
5. **无回归**：现有测试用例不得失败

---

## 七、参考文档

- [BT-4 策略归因分析功能设计](../designs/bt4-attribution-design.md)
- [系统开发规范与红线](./2026-03-25-系统开发规范与红线.md)
- [Phase 6 Code Review](../reviews/phase6-code-review.md)

---

**审批记录**:

| 角色 | 姓名 | 审批意见 | 日期 |
|------|------|----------|------|
| 技术负责人 | | | |
| 产品经理 | | | |
| QA 负责人 | | | |
