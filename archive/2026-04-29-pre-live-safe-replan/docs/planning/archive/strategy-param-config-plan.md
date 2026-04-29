# 策略参数可配置化开发计划

**创建日期**: 2026-04-02
**优先级**: P0 (RICE 评分 8.5)
**预计工时**: 3 人日
**状态**: 待启动

---

## 一、需求分析

### 1.1 问题陈述

当前系统已实现动态策略引擎 (`DynamicStrategyRunner`)，但策略参数硬编码在代码中：
- **Pinbar 参数**: `min_wick_ratio=0.6`, `max_body_ratio=0.3`, `body_position_tolerance=0.1`
- **Engulfing 参数**: `max_wick_ratio=0.6`
- **EMA 参数**: `period=60` (配置文件中)
- **Filter 参数**: 硬编码在各过滤器类中

**痛点**: 用户必须修改代码并重启服务才能调整参数，使用门槛高且中断交易。

### 1.2 用户故事

**US-1: 策略参数配置**
> 作为高级交易员，我希望在策略工作台配置 Pinbar、EMA 等策略参数，以便适应不同的市场环境。

**验收标准**:
- [ ] AC1: 用户可在 UI 界面编辑 Pinbar 参数（最小影线比、最大实体比等）
- [ ] AC2: 用户可配置 EMA 周期、MTF 使能状态
- [ ] AC3: 配置修改后通过热重载 API 即时生效，无需重启服务
- [ ] AC4: 配置保存后持久化，服务重启后自动加载

**US-2: 策略参数模板**
> 作为量化分析师，我希望保存和加载策略参数模板，以便快速切换不同市场策略。

**验收标准**:
- [ ] AC1: 用户可保存当前配置为命名模板（如"牛市激进"、"熊市保守"）
- [ ] AC2: 用户可从模板列表加载历史配置
- [ ] AC3: 模板支持导出/导入（JSON 格式）

**US-3: 参数预览与验证**
> 作为交易员，我希望在应用参数前预览效果，避免错误配置导致损失。

**验收标准**:
- [ ] AC1: 提供"Dry Run"预览功能，显示配置变更对比
- [ ] AC2: 参数超出合理范围时给出警告（如 EMA 周期<5 或>200）
- [ ] AC3: 预览成功后方可确认应用

---

## 二、MVP 范围定义

### 2.1 Must Have (P0 - 2 人日)

| 功能 | 描述 | 工时 |
|------|------|------|
| 策略参数编辑 UI | 表单形式编辑 Pinbar/Engulfing/EMA 参数 | 4h |
| 参数验证 | 前端 + 后端双重校验（Pydantic + 边界检查） | 2h |
| 热重载集成 | 调用现有 `ConfigManager.update_user_config()` API | 2h |
| 配置持久化 | 保存到 `user.yaml`，使用现有 `ConfigSnapshotService` | 2h |
| 参数模板管理 | 模板保存/加载功能 | 4h |

### 2.2 Should Have (P1 - 1 人日)

| 功能 | 描述 | 工时 |
|------|------|------|
| 参数预览 | 显示变更前后对比 | 2h |
| 参数范围警告 | 边界值警告提示 | 2h |

### 2.3 Out of Scope

| 排除功能 | 原因 |
|----------|------|
| 策略逻辑自定义 | 超出参数配置范围，需独立需求 |
| 实时参数调优 | 技术复杂度高，需单独评估 |

---

## 三、技术可行性分析

### 3.1 现有基础设施

**已具备的能力**:
- ✅ `ConfigManager.update_user_config()` - 热重载 API（支持原子性更新 + 观察者模式）
- ✅ `ConfigSnapshotService` - 配置快照版本化管理
- ✅ `StrategyDefinition` - 动态策略定义（支持 `logic_tree` 配置）
- ✅ `TriggerConfig` / `FilterConfig` - 触发器/过滤器配置模型
- ✅ `PinbarConfig` - Pinbar 参数配置类
- ✅ Pydantic 验证 - 自动参数校验

**需要新增的功能**:
- ⏳ 策略参数提取接口 - 从当前配置中提取可配置参数
- ⏳ 策略参数验证 API - 参数边界检查
- ⏳ 参数编辑 UI 组件 - React 表单组件
- ⏳ 参数模板管理 API - 模板 CRUD 操作

### 3.2 策略参数结构分析

#### Pinbar 参数
```python
# 位置：src/domain/strategy_engine.py:PinbarConfig
{
    "min_wick_ratio": Decimal("0.6"),      # 范围：(0, 1]
    "max_body_ratio": Decimal("0.3"),      # 范围：[0, 1)
    "body_position_tolerance": Decimal("0.1")  # 范围：[0, 0.5)
}
```

#### Engulfing 参数
```python
# 位置：src/domain/strategies/engulfing_strategy.py:EngulfingStrategy
{
    "max_wick_ratio": Decimal("0.6")  # 范围：[0, 1]
}
```

#### EMA 参数
```python
# 位置：config/core.yaml 和 user.yaml
{
    "ema_period": 60,        # 范围：[5, 200]
    "mtf_ema_period": 60     # 范围：[5, 200]
}
```

#### Filter 参数
```python
# 位置：src/domain/filter_factory.py
# EMA Filter
{"type": "ema", "period": 60, "enabled": True}
# MTF Filter
{"type": "mtf", "enabled": True}
# ATR Filter
{"type": "atr", "period": 14, "min_atr_ratio": 0.5, "enabled": True}
```

### 3.3 配置模型映射

**StrategyDefinition 结构**:
```python
StrategyDefinition:
  - id: str
  - name: str
  - logic_tree: LogicNode | LeafNode  # 递归逻辑树
  - triggers: List[TriggerConfig]     # 触发器列表
  - filters: List[FilterConfig]       # 过滤器链
  - apply_to: List[str]               # 作用域
```

**TriggerConfig 参数化**:
```python
TriggerConfig:
  - type: "pinbar" | "engulfing" | "doji" | "hammer"
  - params: Dict[str, Any]  # 策略特定参数
    # Pinbar params:
    #   - min_wick_ratio: Decimal
    #   - max_body_ratio: Decimal
    #   - body_position_tolerance: Decimal
    # Engulfing params:
    #   - max_wick_ratio: Decimal
```

**FilterConfig 参数化**:
```python
FilterConfig:
  - type: "ema" | "ema_trend" | "mtf" | "atr" | ...
  - params: Dict[str, Any]  # 过滤器特定参数
    # EMA params:
    #   - period: int
    # MTF params:
    #   - enabled: bool
    # ATR params:
    #   - period: int
    #   - min_atr_ratio: Decimal
```

---

## 四、技术方案设计

### 4.1 后端 API 设计

**新增端点**:
```
GET    /api/strategy/params          # 获取当前策略参数配置
PUT    /api/strategy/params          # 更新策略参数（支持预览）
POST   /api/strategy/params/preview  # 参数预览（Dry Run）
GET    /api/strategy/templates       # 获取模板列表
POST   /api/strategy/templates       # 保存新模板
DELETE /api/strategy/templates/{id}  # 删除模板
GET    /api/strategy/templates/{id}  # 获取模板详情
PUT    /api/strategy/templates/{id}  # 应用模板
```

**请求/响应模型**:
```python
# 策略参数配置
class StrategyParams(BaseModel):
    pinbar: PinbarParams = Field(...)
    engulfing: EngulfingParams = Field(...)
    ema: EmaParams = Field(...)
    filters: List[FilterParams] = Field(default_factory=list)

class PinbarParams(BaseModel):
    min_wick_ratio: Decimal = Field(..., ge=0, le=1)
    max_body_ratio: Decimal = Field(..., ge=0, lt=1)
    body_position_tolerance: Decimal = Field(..., ge=0, lt=0.5)

class EngulfingParams(BaseModel):
    max_wick_ratio: Decimal = Field(..., ge=0, le=1)

class EmaParams(BaseModel):
    period: int = Field(..., ge=5, le=200)

class FilterParams(BaseModel):
    type: str
    enabled: bool
    params: Dict[str, Any]

# 预览响应
class PreviewResult(BaseModel):
    old_config: StrategyParams
    new_config: StrategyParams
    changes: List[ChangeDetail]
    warnings: List[str]  # 参数范围警告

class ChangeDetail(BaseModel):
    field: str
    old_value: Any
    new_value: Any
```

### 4.2 前端组件设计

**组件层级**:
```
StrategyParamPanel/
├── PinbarParamForm/       # Pinbar 参数表单
├── EngulfingParamForm/    # Engulfing 参数表单
├── EmaParamForm/          # EMA 参数表单
├── FilterParamList/       # 过滤器参数列表
├── ParamPreviewModal/     # 预览对话框
└── TemplateManager/       # 模板管理组件
```

### 4.3 参数验证规则

| 参数 | 类型 | 范围 | 警告范围 | 默认值 |
|------|------|------|----------|--------|
| `min_wick_ratio` | Decimal | (0, 1] | <0.4 或 >0.8 | 0.6 |
| `max_body_ratio` | Decimal | [0, 1) | >0.4 | 0.3 |
| `body_position_tolerance` | Decimal | [0, 0.5) | >0.2 | 0.1 |
| `max_wick_ratio` (Engulfing) | Decimal | [0, 1] | >0.7 | 0.6 |
| `ema_period` | int | [5, 200] | <10 或 >100 | 60 |
| `mtf_ema_period` | int | [5, 200] | <10 或 >100 | 60 |
| `atr_period` | int | [5, 50] | <10 或 >20 | 14 |
| `min_atr_ratio` | Decimal | [0, 5] | <0.3 或 >1.0 | 0.5 |

---

## 五、任务分解

### 后端任务 (B1-B6)

| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| B1 | 创建 StrategyParams Pydantic 模型 | P0 | 1h | ☐ 待启动 |
| B2 | 实现 GET /api/strategy/params | P0 | 1h | ☐ 待启动 |
| B3 | 实现 PUT /api/strategy/params + 热重载集成 | P0 | 2h | ☐ 待启动 |
| B4 | 实现 POST /api/strategy/params/preview | P0 | 1h | ☐ 待启动 |
| B5 | 实现策略模板管理 API（CRUD） | P1 | 2h | ☐ 待启动 |
| B6 | 参数验证与边界检查 | P0 | 1h | ☐ 待启动 |

### 前端任务 (F1-F6)

| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| F1 | 创建 API 函数封装（api.ts） | P0 | 1h | ☐ 待启动 |
| F2 | 实现 StrategyParamPanel 主容器 | P0 | 2h | ☐ 待启动 |
| F3 | 实现 PinbarParamForm 组件 | P0 | 2h | ☐ 待启动 |
| F4 | 实现 EmaParamForm / FilterParamList | P0 | 2h | ☐ 待启动 |
| F5 | 实现 ParamPreviewModal 预览对话框 | P1 | 2h | ☐ 待启动 |
| F6 | 实现 TemplateManager 模板管理 | P1 | 3h | ☐ 待启动 |

### 测试任务 (T1-T4)

| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T1 | StrategyParams 模型单元测试 | P0 | 1h | ☐ 待启动 |
| T2 | 策略参数 API 集成测试 | P0 | 2h | ☐ 待启动 |
| T3 | 参数验证边界测试 | P0 | 1h | ☐ 待启动 |
| T4 | 前端 E2E 测试 | P1 | 2h | ☐ 待启动 |

---

## 六、执行阶段

### 阶段 1: 后端核心 (B1-B4, B6) - 预计 6h
- 创建 Pydantic 模型
- 实现参数获取/更新 API
- 集成热重载
- 参数验证

### 阶段 2: 前端核心 (F1-F4) - 预计 7h
- API 函数封装
- 参数表单组件
- 实时验证

### 阶段 3: 预览与模板 (B5, F5, F6) - 预计 7h
- 预览 API 与对话框
- 模板管理功能

### 阶段 4: 测试验证 (T1-T4) - 预计 6h
- 单元测试
- 集成测试
- E2E 测试

---

## 七、依赖关系

**上游依赖**:
- ✅ `ConfigManager` - 已实现热重载
- ✅ `ConfigSnapshotService` - 已实现快照管理
- ✅ `StrategyDefinition` - 已实现动态策略定义

**下游依赖**:
- ⏳ Phase 6 前端适配 - 策略工作台组件

---

## 八、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 参数校验不充分导致策略异常 | 中 | 高 | 严格 Pydantic 验证 + 边界测试 |
| 热重载失败导致配置不一致 | 低 | 高 | 原子性更新 + 回滚机制 |
| 前端表单验证与后端不一致 | 中 | 中 | 复用后端验证逻辑（通过 API） |
| 参数模板存储结构复杂 | 中 | 中 | 使用独立 YAML 文件存储模板 |

---

## 九、验收标准

### 功能验收
- [ ] 可在 UI 界面编辑 Pinbar/EMA/Filter 参数
- [ ] 参数修改后即时生效（热重载）
- [ ] 配置保存后持久化（重启后自动加载）
- [ ] 可保存/加载参数模板
- [ ] 参数超出范围时显示警告

### 技术验收
- [ ] 后端参数验证通过 Pydantic 模型
- [ ] 前端表单验证与后端一致
- [ ] 热重载 API 调用成功（无重启）
- [ ] 配置快照自动创建
- [ ] 单元测试覆盖率 ≥ 90%

---

*本文档为策略参数可配置化开发计划，具体实现方案以代码为准。*
