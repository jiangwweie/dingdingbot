# ADR: Risk Overrides 消费断裂 + Decimal/float 类型不匹配修复

> **编号**: ADR-002
> **状态**: 已批准
> **日期**: 2026-04-13
> **作者**: 架构师（Agent 团队）
> **影响模块**: `src/domain/models.py`, `src/application/backtester.py`

---

## 1. 问题陈述

### 1.1 配置消费断裂

前端回测页面允许用户修改风控参数（`max_loss_percent`、`max_leverage`），通过 API 请求体 `risk_overrides` 字段传给了后端。然而 `src/application/backtester.py` 中 **5 处** `RiskConfig` 实例化全部硬编码了默认值，从未消费 `request.risk_overrides`：

| 行号 | 方法 | 硬编码值 | 影响 |
|------|------|----------|------|
| L251 | `run_backtest()` | `max_loss_percent=Decimal("0.01"), max_leverage=20` | 胜率模拟忽略用户配置 |
| L255 | `run_backtest()` | `max_loss_percent=Decimal("0.01"), max_leverage=20` | 盈亏比计算忽略用户配置 |
| L404 | `_build_strategy_config()` | `max_loss_percent=Decimal("0.01"), max_leverage=20` | 策略运行器忽略用户配置 |
| L991 | `_save_backtest_signals()` | `max_loss_percent=Decimal("0.01"), max_leverage=20` | 信号落盘仓位计算忽略用户配置 |
| L1192 | `run_pms_backtest()` | `max_loss_percent=Decimal('0.01'), max_leverage=20` | v3 PMS 模式忽略用户配置 |

**直接后果**: 前端修改风控参数后，回测结果（仓位大小、止损距离、盈亏比）与用户预期完全不一致，形成**数据流断裂**。

### 1.2 Decimal/float 类型不匹配

`BacktestRequest.risk_overrides` 的当前类型是 `Optional[Dict[str, Any]]`（`src/domain/models.py` L604-607）。JSON 请求体中的数值反序列化为 Python `float`，但 `RiskConfig` 的字段类型是 `Decimal`：

```python
# 当前定义（L604-607）
risk_overrides: Optional[Dict[str, Any]] = Field(
    default=None,
    description="Risk config overrides for this backtest"
)

# RiskConfig 字段（L167-168）
max_loss_percent: Decimal = Field(...)
max_leverage: int = Field(...)
```

如果直接将 `{"max_loss_percent": 0.02, "max_leverage": 10}` 中的 `0.02`（float）传入 `RiskConfig`，Pydantic v2 虽然会尝试 coerce，但在后续 `Decimal * float` 运算中会触发类型错误（金融计算要求全链路 `Decimal`）。

### 1.3 根因

`risk_overrides` 从未经过**类型提升**（从 `Dict[str, Any]` 到 `RiskConfig`），也没有在入口层进行**类型校验与转换**。

---

## 2. 决策

### 采用方案 B：model_validator + 类型变更 + 消费端改造

| 子项 | 决策 | 理由 |
|------|------|------|
| **类型转换位置** | `RiskConfig.model_validator(mode='before')` | 在 Pydantic 构造期统一转换，所有创建点自动受益，无需逐处修改 |
| **API 类型变更** | `risk_overrides: Optional[RiskConfig]` | 利用 Pydantic 在 API 入口层拦截非法输入，消除 `Dict[str, Any]` 黑洞 |
| **消费端改造** | 新增 `_build_risk_config()` 方法统一构造 | 消除 5 处硬编码，建立 SSOT（Single Source of Truth） |

### 拒绝方案 A（手动转换）

方案 A：在 `backtester.py` 中手动 `Decimal(str(v))` 转换。

**拒绝理由**:
- 转换逻辑散落在消费端，违反 DRY
- 无法解决 `Dict[str, Any]` 在 API 入口层的类型安全问题
- 未来新增 `RiskConfig` 创建点仍需手动转换

### 拒绝方案 C（全局替换 float→Decimal）

方案 C：修改前端/JSON 序列化层，所有数值以字符串形式传输。

**拒绝理由**:
- 前端改动量大，破坏现有 `Partial<RiskConfig>` 表单
- JSON 原生不支持 Decimal，需要自定义序列化器
- 与 Pydantic 的自动类型提升能力重复造轮子

---

## 3. 影响范围：16 处 RiskConfig 创建点分析

通过全代码库搜索 `RiskConfig(`，共找到 **16 处**实例化点（不含文档/测试/归档文件）。逐一分析如下：

### 3.1 生产代码（需要改动，5 处）

| # | 文件:行号 | 当前写法 | 改动策略 |
|---|-----------|----------|----------|
| 1 | `backtester.py:251` | `RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | **改为使用 `_build_risk_config(request)`** |
| 2 | `backtester.py:255` | `RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | **改为使用 `_build_risk_config(request)`** |
| 3 | `backtester.py:404` | `RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | **改为使用 `_build_risk_config(request)`**（需将 request 传入此方法） |
| 4 | `backtester.py:991` | `RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | **改为使用 `_build_risk_config(request)`**（request 已作为参数传入） |
| 5 | `backtester.py:1192` | `RiskConfig(max_loss_percent=Decimal('0.01'), max_leverage=20)` | **改为使用 `_build_risk_config(request)`**（需将 request 传入此方法或直接使用） |

### 3.2 生产代码（不需改动，11 处）

| # | 文件:行号 | 当前写法 | 不需改动的理由 |
|---|-----------|----------|----------------|
| 6 | `src/main.py:194` | 从 `user_config.risk` 取值构造 | 来源是 YAML 配置经 ConfigManager 加载，已是 `Decimal`，不涉及 JSON float |
| 7 | `config_parser.py:232` | `RiskConfig(**data)` | `data` 来自数据库行（字符串），由 `Decimal(str(row[...]))` 预处理后传入 |
| 8 | `config_parser.py:298` | 硬编码默认值 | 仅在解析失败时返回的 fallback 默认值，构造时已用 `Decimal("0.01")`，类型正确 |
| 9 | `config_manager.py:803` | 从数据库行构造 | 已用 `Decimal(str(row["max_loss_percent"]))` 显式转换，类型正确 |
| 10 | `config_manager.py:812` | 缓存未命中时的默认值 | 已用 `Decimal("0.01")` 构造，类型正确 |
| 11 | `config_manager.py:1148` | fallback 默认值 | 已用 `Decimal("0.01")` 构造，类型正确 |
| 12 | `config_repository.py:785` | `RiskConfig(**updated_data)` | 来自数据库更新，字段经 Pydantic 校验 |
| 13 | `config_repository.py:797` | 从数据库行构造 | 已用 `Decimal(str(row[...]))` 显式转换，类型正确 |
| 14 | `config_repository.py:806` | 缓存未命中默认值 | 已用 `Decimal("0.01")` 构造，类型正确 |
| 15 | `config_repository.py:862` | fallback 默认值 | 已用 `Decimal("0.01")` 构造，类型正确 |
| 16 | `tests/run_simulation.py:252` | 从 user config 取值 | 来源是 YAML 配置，已是 `Decimal`，不涉及 JSON float |

### 3.3 测试代码（不需改动，多处）

所有测试文件中的 `RiskConfig` 构造均使用 `Decimal("0.01")` 字面量，类型正确，不受影响。

### 3.4 结论

- **仅需改动 backtester.py 中的 5 处**
- 其余 11 处生产代码均已正确处理 Decimal 类型，无需修改
- `model_validator(mode='before')` 提供额外安全保障，即使未来出现 float 传入也能自动转换

---

## 4. 改动清单

### 改动 1：RiskConfig 增加 model_validator

**文件**: `src/domain/models.py`（约 L165-203）

**变更内容**:

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from decimal import Decimal
from typing import Optional

class RiskConfig(BaseModel):
    """Risk management configuration"""
    max_loss_percent: Decimal = Field(..., description="Max loss per trade as % of balance")
    max_leverage: int = Field(..., ge=1, le=125, description="Maximum leverage allowed")
    max_total_exposure: Decimal = Field(
        default=Decimal('0.8'),
        ge=0,
        le=1,
        description="Maximum total exposure as % of balance (e.g., 0.8 = 80%)"
    )
    daily_max_trades: Optional[int] = Field(default=None, ge=1)
    daily_max_loss: Optional[Decimal] = Field(default=None)
    max_position_hold_time: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra='ignore')  # 新增：向后兼容

    @model_validator(mode='before')  # 新增：在字段校验前转换类型
    @classmethod
    def coerce_floats_to_decimal(cls, data):
        """将 JSON 反序列化产生的 float 自动转换为 Decimal。

        对已是 Decimal 的输入幂等（不重复转换）。
        确保所有数值字段在 Pydantic 校验阶段之前就是 Decimal。
        """
        if isinstance(data, dict):
            float_fields = ['max_loss_percent', 'max_total_exposure', 'daily_max_loss']
            for field_name in float_fields:
                value = data.get(field_name)
                if value is not None and not isinstance(value, Decimal):
                    data[field_name] = Decimal(str(value))  # str() 避免 float 精度问题
        return data

    @field_validator('max_loss_percent')
    @classmethod
    def validate_loss_percent(cls, v):
        if v <= 0 or v > Decimal('1'):
            raise ValueError("Max loss percent must be between 0 and 1")
        return v

    @field_validator('max_total_exposure')
    @classmethod
    def validate_total_exposure(cls, v):
        if v < 0 or v > Decimal('1'):
            raise ValueError("Max total exposure must be between 0 and 1")
        return v
```

**关键点**:
- `mode='before'` 确保在 `field_validator` 之前执行，`field_validator` 接收到的已经是 `Decimal`
- `Decimal(str(value))` 而非 `Decimal(value)`，避免 `Decimal(0.01)` 产生 `0.010000000000000000208...` 问题
- `extra='ignore'` 保护向后兼容：如果未来 JSON 传入了 RiskConfig 未定义的字段，不会报错

### 改动 2：BacktestRequest.risk_overrides 类型变更

**文件**: `src/domain/models.py`（约 L604-607）

**变更内容**:

```python
# 变更前
risk_overrides: Optional[Dict[str, Any]] = Field(
    default=None,
    description="Risk config overrides for this backtest"
)

# 变更后
risk_overrides: Optional[RiskConfig] = Field(
    default=None,
    description="Risk config overrides for this backtest (supports Partial<RiskConfig>)"
)
```

**影响**:
- 前端 `Partial<RiskConfig>` 仍然兼容：只需传 `{max_loss_percent: 0.02, max_leverage: 10}`
- Pydantic 会自动将 float 值通过 `model_validator` 转换为 `Decimal`
- 非法输入（如 `max_loss_percent: -1`）在 API 入口层即被拦截，返回 422 错误

### 改动 3：backtester.py 消费 risk_overrides

**文件**: `src/application/backtester.py`

#### 3.1 新增 `_build_risk_config` 方法

```python
def _build_risk_config(self, request: BacktestRequest) -> RiskConfig:
    """Build RiskConfig from request overrides or defaults.

    优先级: request.risk_overrides > code defaults
    """
    if request.risk_overrides is not None:
        return RiskConfig(
            max_loss_percent=request.risk_overrides.max_loss_percent,
            max_leverage=request.risk_overrides.max_leverage,
            max_total_exposure=request.risk_overrides.max_total_exposure,
            daily_max_trades=request.risk_overrides.daily_max_trades,
            daily_max_loss=request.risk_overrides.daily_max_loss,
            max_position_hold_time=request.risk_overrides.max_position_hold_time,
        )
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
```

#### 3.2 替换 5 处硬编码

| 行号 | 原代码 | 新代码 |
|------|--------|--------|
| L251 | `RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | `self._build_risk_config(request)` |
| L255 | `risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | `risk_config = self._build_risk_config(request)` |
| L404 | `risk_config = RiskConfig(...)` 在 `_build_strategy_config()` 中 | 需要此方法签名增加 `request: BacktestRequest` 参数，然后调用 `self._build_risk_config(request)` |
| L991 | `risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)` | `risk_config = self._build_risk_config(request)`（`request` 已作为参数） |
| L1192 | `risk_config = RiskConfig(max_loss_percent=Decimal('0.01'), max_leverage=20)` | 需确认 `run_pms_backtest()` 方法签名是否已有 `request` 参数，有则直接调用 |

---

## 5. 风险与缓解

### 5.1 向后兼容

| 风险 | 缓解 |
|------|------|
| 旧版本前端可能传入 `risk_overrides` 中额外的未知字段 | `model_config = ConfigDict(extra='ignore')` 忽略未知字段 |
| 现有 API 调用者可能传入 `Dict[str, Any]` | Pydantic 类型变更在 FastAPI 入口层自动校验，不匹配返回 422 |
| 已保存的回测请求记录可能包含旧格式 | 不影响历史数据，仅影响新请求的解析 |

### 5.2 测试影响

| 风险 | 缓解 |
|------|------|
| 现有单元测试直接构造 `RiskConfig(max_loss_percent=Decimal("0.01"), ...)` | 不受影响，validator 对 Decimal 输入幂等 |
| 测试中可能用 `Dict[str, Any]` 模拟 risk_overrides | 需要改为 `RiskConfig` 实例或使用 Pydantic `model_validate()` |
| 集成测试中的 API 请求体 | JSON payload 不变，Pydantic 自动处理类型转换 |

**需检查的测试文件**:
- `tests/unit/test_backtester.py`（如有直接构造 Dict 类型 risk_overrides 的测试）
- `tests/e2e/` 中的回测相关 E2E 测试

### 5.3 前端影响

| 风险 | 缓解 |
|------|------|
| 前端 TypeScript 类型可能需要更新 | 前端 `Partial<RiskConfig>` 接口不变，无需改动 |
| 表单提交 `max_loss_percent` 为 number 类型 | `model_validator` 自动将 float 转为 Decimal，前端无需修改 |

---

## 6. 验证计划

### 6.1 手动验证（开发完成后）

1. **前端回测页面测试**:
   - 打开回测页面，修改风控参数（如 max_loss_percent = 0.02, max_leverage = 15）
   - 发起回测请求
   - 检查回测结果中的仓位大小是否与 2% 风险匹配（而非默认的 1%）

2. **API 层类型拦截验证**:
   - 使用 Postman/curl 发送非法请求：`{"max_loss_percent": -0.1, "max_leverage": 200}`
   - 确认返回 422 错误，错误信息指出字段校验失败

3. **v2_classic 和 v3_pms 两种模式**:
   - 分别用两种模式发起回测
   - 确认两种模式都正确使用了用户配置的风控参数

### 6.2 自动化测试

1. **单元测试 - RiskConfig model_validator**:
   - 测试 float 输入自动转换为 Decimal
   - 测试 Decimal 输入保持不变（幂等）
   - 测试字符串数字输入（如 `"0.02"`）也能正确转换
   - 测试 `extra='ignore'` 忽略未知字段

2. **单元测试 - _build_risk_config**:
   - 有 risk_overrides 时返回覆盖后的配置
   - 无 risk_overrides 时返回默认配置
   - risk_overrides 部分字段时（只传 max_loss_percent），其余字段使用 RiskConfig 默认值

3. **集成测试 - 端到端**:
   - 发送包含 risk_overrides 的回测请求
   - 验证回测报告中的仓位计算结果与预期一致
   - 验证 v2_classic 和 v3_pms 两种模式

### 6.3 回归测试

运行现有测试套件，确认无回归：

```bash
pytest tests/unit/ -v --tb=short
pytest tests/integration/ -v --tb=short
```

预期：**所有 275+ 测试通过**，新增 5-8 个关于 risk_overrides 的测试用例。

---

## 7. 实施顺序

```
1. models.py: RiskConfig 增加 model_validator + extra='ignore'
       ↓
2. models.py: BacktestRequest.risk_overrides 类型变更为 Optional[RiskConfig]
       ↓
3. backtester.py: 新增 _build_risk_config() 方法
       ↓
4. backtester.py: 替换 5 处硬编码为 _build_risk_config(request)
       ↓
5. 运行测试，修复失败的测试
       ↓
6. 手动验证前端回测页面
```

预计改动量：**~40 行新增，~15 行删除**，涉及 2 个文件。

---

*本文档由架构师 Agent 生成，经用户批准后进入实施阶段。*
