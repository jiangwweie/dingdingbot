# 实施报告：方案 C - 回测引擎 ATR 过滤器修复

**实施时间**: 2026-03-31
**版本**: v2 (commit: c469943)
**类型**: 架构重构 + Bug 修复

---

## 问题背景

回测引擎的 `IsolatedStrategyRunner` 硬编码创建过滤器，缺少 ATR 过滤器，导致：
- 22.6% 的回测信号止损距离过近（<0.3%）
- 实盘和回测过滤器链不一致
- 诊断报告：`docs/diagnostic-reports/backtest-atr-filter-missing-20260331.md`

---

## 修复内容

### 代码变更

**文件**: `src/application/backtester.py`

#### 1. 删除 Legacy 类
- 删除 `IsolatedStrategyRunner` 类（原 62-98 行）
- 删除 `IsolatedStrategyConfig` dataclass

#### 2. 新增方法
```python
def _build_runner_from_request(self, request: BacktestRequest) -> DynamicStrategyRunner:
    """统一构建 DynamicStrategyRunner，支持两种格式：
    1. strategies 字段（新格式）
    2. legacy 参数（自动转换）
    """

def _convert_legacy_to_strategy_definition(self, request: BacktestRequest) -> StrategyDefinition:
    """将 legacy 参数转换为 StrategyDefinition
    - 包含 EMA 过滤器（period=60）
    - 包含 MTF 过滤器
    - 包含 ATR 过滤器（period=14, min_atr_ratio=0.005）
    """
```

#### 3. 过滤器配置
```python
# ATR 过滤器默认启用（与生产环境一致）
filters_config.append(FilterConfig(
    type="atr",
    enabled=True,
    params={
        "period": 14,
        "min_atr_ratio": "0.005",  # 0.5%
        "min_absolute_range": "0.1"
    }
))
```

### 测试新增

**文件**: `tests/unit/test_backtester_atr.py`

| 测试类 | 测试数量 | 说明 |
|--------|---------|------|
| `TestLegacyToStrategyDefinition` | 4 | 验证 legacy 参数转换 |
| `TestBuildRunnerFromRequest` | 2 | 验证 Runner 构建 |
| `TestAtrFilterInBacktest` | 2 | 验证 ATR 过滤器功能 |
| `TestBacktesterIntegration` | 2 | 集成测试 |
| **总计** | **10** | **100% 通过** |

---

## 架构对比

| 组件 | 修复前 | 修复后 |
|------|--------|--------|
| 回测引擎 | `IsolatedStrategyRunner` | `DynamicStrategyRunner` |
| 过滤器创建 | 硬编码 | `FilterFactory` |
| ATR 过滤器 | ❌ 不支持 | ✅ 支持（默认启用） |
| 与生产环境一致性 | ❌ 不一致 | ✅ 一致 |
| 维护成本 | 高（重复逻辑） | 低（统一实现） |

---

## 验证结果

### 单元测试
```
pytest tests/unit/test_backtester_atr.py -v
======================== 10 passed, 9 warnings ========================

pytest tests/unit/test_filter_factory.py -v
======================== 38 passed, 1 warning =========================
```

### 过滤器支持对比

| 过滤器类型 | 修复前 | 修复后 |
|-----------|--------|--------|
| EMA Trend | ✅ | ✅ |
| MTF | ✅ | ✅ |
| **ATR Volatility** | ❌ | ✅ |
| Volume Surge | ❌ | ✅ |

---

## 向后兼容性

- ✅ Legacy 参数仍然有效（`min_wick_ratio`、`trend_filter_enabled` 等）
- ✅ 自动转换为 `StrategyDefinition` 格式
- ✅ `strategies` 字段（新格式）优先使用

---

## 部署步骤

### 服务器部署

```bash
cd /usr/local/monitorDog
git fetch origin
git checkout v2
git pull origin v2

# 重启 Docker 容器
docker-compose down
docker-compose up -d

# 健康检查
curl -f http://localhost:8000/api/health
```

### 验证回测 ATR 过滤器

```bash
# 执行回测并检查信号标签
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol": "ETH/USDT:USDT", "timeframe": "1h", "limit": 100}'

# 检查返回信号 tags 中是否包含 ATR 标签
# 期望：[{"name": "MTF", ...}, {"name": "EMA", ...}, {"name": "ATR", ...}]
```

---

## 预期效果

修复后，回测信号将通过完整的过滤器链：
- ATR 过滤器拒绝波动率 < 0.5% 的信号
- 止损距离过近的信号将被正确过滤
- 回测与实盘结果一致性提升

---

## 技术债清理

本次修复同时清理了以下技术债：
1. 删除了 `IsolatedStrategyRunner` legacy 代码（~100 行）
2. 统一了回测和实盘的过滤器创建逻辑
3. 减少了未来添加新过滤器的复杂度

---

## 相关文件

- **修改**: `src/application/backtester.py`
- **新增**: `tests/unit/test_backtester_atr.py`
- **诊断报告**: `docs/diagnostic-reports/backtest-atr-filter-missing-20260331.md`

---

**实施人员**: Backend Dev + Team Coordinator
**审查人员**: QA Tester
**部署状态**: 待部署
