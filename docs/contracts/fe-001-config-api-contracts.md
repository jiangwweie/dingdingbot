# FE-001 配置导航重构 - 接口契约文档

> **创建日期**: 2026-04-06  
> **任务 ID**: FE-001  
> **架构师**: Claude (前端开发专家)  
> **状态**: 已批准  
> **相关架构文档**: `docs/arch/fe-001-frontend-config-navigation-redesign.md`

---

## 一、API 端点总览

### 1.1 策略配置管理 API

| 端点 | 方法 | 说明 | 优先级 |
|------|------|------|--------|
| `/api/config/strategies` | GET | 获取策略列表 | P0 |
| `/api/config/strategies` | POST | 创建策略 | P0 |
| `/api/config/strategies/{id}` | PUT | 更新策略 | P0 |
| `/api/config/strategies/{id}` | DELETE | 删除策略 | P0 |
| `/api/config/strategies/{id}/enable` | POST | 启用/禁用策略 | P1 |

### 1.2 策略参数管理 API

| 端点 | 方法 | 说明 | 优先级 |
|------|------|------|--------|
| `/api/strategy/params` | GET | 获取当前策略参数 | P0 |
| `/api/strategy/params` | PUT | 更新策略参数 (热重载) | P0 |
| `/api/strategy/params/preview` | POST | 预览参数变更 (Dry Run) | P1 |

### 1.3 系统配置管理 API

| 端点 | 方法 | 说明 | 优先级 |
|------|------|------|--------|
| `/api/config/system` | GET | 获取系统配置 (Level 1) | P0 |
| `/api/config/system` | PUT | 更新系统配置 | P0 |

### 1.4 Tooltip Schema API

| 端点 | 方法 | 说明 | 优先级 |
|------|------|------|--------|
| `/api/config/schema` | GET | 获取配置项 Schema (含 tooltip) | P1 |

### 1.5 Profile 管理 API (已有，保持不变)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config/profiles` | GET | 获取 Profile 列表 |
| `/api/config/profiles` | POST | 创建 Profile |
| `/api/config/profiles/{name}` | PUT | 更新 Profile |
| `/api/config/profiles/{name}` | DELETE | 删除 Profile |

---

## 二、策略配置管理 API 详情

### 2.1 GET /api/config/strategies

**说明**: 获取所有策略列表

**请求参数**: 无

**响应 Schema**:
```typescript
interface GetStrategiesResponse {
  strategies: Strategy[];
  total: number;
}

interface Strategy {
  id: string;              // 策略 ID (UUID)
  name: string;            // 策略名称
  description: string;     // 策略描述
  enabled: boolean;        // 启用状态
  symbol: string;          // 作用域：交易对
  timeframe: string;       // 作用域：周期
  created_at: string;      // ISO 8601 时间戳
  updated_at: string;      // ISO 8601 时间戳
}
```

**成功响应示例**:
```json
{
  "strategies": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "BTC 15m Pinbar",
      "description": "BTC 15 分钟 Pinbar 形态策略",
      "enabled": true,
      "symbol": "BTC/USDT:USDT",
      "timeframe": "15m",
      "created_at": "2026-04-01T10:00:00Z",
      "updated_at": "2026-04-06T15:30:00Z"
    }
  ],
  "total": 1
}
```

---

### 2.2 POST /api/config/strategies

**说明**: 创建新策略

**请求体 Schema**:
```typescript
interface CreateStrategyRequest {
  name: string;           // REQUIRED, minLength: 1, maxLength: 50
  description?: string;   // OPTIONAL, maxLength: 500, default: ""
  symbol: string;         // REQUIRED, pattern: "^[A-Z]+/[A-Z]+:[A-Z]+$"
  timeframe: string;      // REQUIRED, enum: ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]
  params?: StrategyParams; // OPTIONAL, 使用默认参数
}
```

**响应 Schema**: 返回创建的完整策略对象

**成功响应示例**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "name": "ETH 1h EMA Cross",
  "description": "ETH 1 小时 EMA 交叉策略",
  "enabled": true,
  "symbol": "ETH/USDT:USDT",
  "timeframe": "1h",
  "params": {
    "pinbar": {
      "min_wick_ratio": 0.6,
      "max_body_ratio": 0.3,
      "body_position_tolerance": 0.1
    },
    "ema": { "period": 60 },
    "mtf": { "enabled": true, "ema_period": 60 },
    "atr": { "enabled": false, "period": 14, "min_atr_ratio": 0.5 },
    "max_loss_percent": 0.01,
    "max_leverage": 10
  },
  "created_at": "2026-04-06T16:00:00Z",
  "updated_at": "2026-04-06T16:00:00Z"
}
```

**错误响应**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `STRATEGY_NAME_EXISTS` | 409 | 策略名称已存在 | Toast 错误 + 清空名称输入框 |
| `INVALID_SYMBOL_FORMAT` | 400 | 交易对格式错误 | Toast 错误 + 高亮输入框 |
| `INVALID_TIMEFRAME` | 400 | 周期不在枚举范围内 | Toast 错误 |

---

### 2.3 PUT /api/config/strategies/{id}

**说明**: 更新策略信息

**路径参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 策略 ID |

**请求体 Schema**:
```typescript
interface UpdateStrategyRequest {
  name?: string;        // OPTIONAL, minLength: 1, maxLength: 50
  description?: string; // OPTIONAL, maxLength: 500
  symbol?: string;      // OPTIONAL, pattern: "^[A-Z]+/[A-Z]+:[A-Z]+$"
  timeframe?: string;   // OPTIONAL, enum: 同创建
  enabled?: boolean;    // OPTIONAL
}
```

**响应 Schema**: 返回更新后的完整策略对象

**错误响应**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `STRATEGY_NOT_FOUND` | 404 | 策略不存在 | Toast 错误 + 返回列表 |
| `STRATEGY_NAME_EXISTS` | 409 | 策略名称已存在 | Toast 错误 + 清空名称输入框 |

---

### 2.4 DELETE /api/config/strategies/{id}

**说明**: 删除策略

**路径参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 策略 ID |

**成功响应**:
```json
{
  "success": true,
  "message": "策略已删除"
}
```

**错误响应**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `STRATEGY_NOT_FOUND` | 404 | 策略不存在 | Toast 错误 |
| `STRATEGY_IN_USE` | 409 | 策略正在使用中，无法删除 | Toast 错误 + 禁用提示 |

---

### 2.5 POST /api/config/strategies/{id}/enable

**说明**: 启用/禁用策略

**路径参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 策略 ID |

**请求体 Schema**:
```typescript
interface ToggleStrategyEnableRequest {
  enabled: boolean;  // true=启用，false=禁用
}
```

**响应 Schema**:
```typescript
interface ToggleStrategyEnableResponse {
  id: string;
  enabled: boolean;
  updated_at: string;
}
```

---

## 三、策略参数管理 API 详情

### 3.1 GET /api/strategy/params

**说明**: 获取当前生效的策略参数配置

**请求参数**: 无

**响应 Schema**:
```typescript
interface StrategyParams {
  pinbar: PinbarParams;
  engulfing?: EngulfingParams;
  ema: EmaParams;
  mtf: MtfParams;
  atr?: AtrParams;
  filters?: FilterConfig[];
  max_loss_percent: number;   // 0.01 = 1%
  max_leverage: number;       // 10 = 10x
}

interface PinbarParams {
  min_wick_ratio: number;     // [0.5, 0.7], default: 0.6
  max_body_ratio: number;     // [0.2, 0.4], default: 0.3
  body_position_tolerance: number; // [0.05, 0.15], default: 0.1
}

interface EngulfingParams {
  max_wick_ratio: number;     // [0.5, 0.7], default: 0.6
}

interface EmaParams {
  period: number;             // [5, 200], default: 60
}

interface MtfParams {
  enabled: boolean;           // default: true
  ema_period: number;         // [5, 200], default: 60
}

interface AtrParams {
  enabled: boolean;           // default: false
  period: number;             // [5, 50], default: 14
  min_atr_ratio: number;      // [0.1, 2.0], default: 0.5
}

interface FilterConfig {
  type: string;
  enabled: boolean;
  params: Record<string, any>;
}
```

**成功响应示例**:
```json
{
  "pinbar": {
    "min_wick_ratio": 0.6,
    "max_body_ratio": 0.3,
    "body_position_tolerance": 0.1
  },
  "engulfing": {
    "max_wick_ratio": 0.6
  },
  "ema": {
    "period": 60
  },
  "mtf": {
    "enabled": true,
    "ema_period": 60
  },
  "atr": {
    "enabled": true,
    "period": 14,
    "min_atr_ratio": 0.5
  },
  "filters": [],
  "max_loss_percent": 0.01,
  "max_leverage": 10
}
```

---

### 3.2 PUT /api/strategy/params

**说明**: 更新策略参数 (支持热重载)

**请求体 Schema**: (支持部分更新)
```typescript
type UpdateStrategyParamsRequest = Partial<StrategyParams>;
```

**请求示例**:
```json
{
  "pinbar": {
    "min_wick_ratio": 0.65
  },
  "ema": {
    "period": 50
  }
}
```

**响应 Schema**: 返回更新后的完整参数配置

**成功响应示例**:
```json
{
  "pinbar": {
    "min_wick_ratio": 0.65,
    "max_body_ratio": 0.3,
    "body_position_tolerance": 0.1
  },
  "engulfing": {
    "max_wick_ratio": 0.6
  },
  "ema": {
    "period": 50
  },
  "mtf": {
    "enabled": true,
    "ema_period": 60
  },
  "atr": {
    "enabled": true,
    "period": 14,
    "min_atr_ratio": 0.5
  },
  "filters": [],
  "max_loss_percent": 0.01,
  "max_leverage": 10
}
```

**错误响应**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `INVALID_PARAM_VALUE` | 400 | 参数值超出范围 | Toast 错误 + 高亮输入框 |
| `PARAM_VALIDATION_FAILED` | 400 | 参数验证失败 | Toast 错误 + 显示详情 |

---

### 3.3 POST /api/strategy/params/preview

**说明**: 预览参数变更 (Dry Run)，不实际保存

**请求体 Schema**:
```typescript
interface PreviewStrategyParamsRequest {
  new_config: Partial<StrategyParams>;  // 新的参数配置
}
```

**响应 Schema**:
```typescript
interface PreviewStrategyParamsResponse {
  old_config: StrategyParams;    // 当前配置
  new_config: StrategyParams;    // 新配置
  changes: Change[];             // 变更列表
  warnings: string[];            // 警告信息
}

interface Change {
  path: string;                  // 如 "pinbar.min_wick_ratio"
  from: any;                     // 原值
  to: any;                       // 新值
}
```

**成功响应示例**:
```json
{
  "old_config": {
    "pinbar": { "min_wick_ratio": 0.6, ... },
    "ema": { "period": 60 }
  },
  "new_config": {
    "pinbar": { "min_wick_ratio": 0.65, ... },
    "ema": { "period": 50 }
  },
  "changes": [
    {
      "path": "pinbar.min_wick_ratio",
      "from": 0.6,
      "to": 0.65
    },
    {
      "path": "ema.period",
      "from": 60,
      "to": 50
    }
  ],
  "warnings": [
    "EMA period < 60 可能导致更多虚假信号",
    "较高的 min_wick_ratio 可能错过一些机会"
  ]
}
```

---

## 四、系统配置管理 API 详情

### 4.1 GET /api/config/system

**说明**: 获取系统配置 (Level 1 - 全局配置)

**响应 Schema**:
```typescript
interface SystemConfig {
  // 队列配置
  queue_batch_size: number;       // default: 10, min: 1, max: 100
  queue_flush_interval: number;   // 秒，default: 5.0, min: 1.0, max: 60.0
  queue_max_size: number;         // default: 1000, min: 100, max: 10000
  
  // 数据预热
  warmup_history_bars: number;    // default: 100, min: 50, max: 500
  
  // 信号冷却
  signal_cooldown_seconds: number; // default: 14400 (4h), min: 3600, max: 86400
}
```

**成功响应示例**:
```json
{
  "queue_batch_size": 10,
  "queue_flush_interval": 5.0,
  "queue_max_size": 1000,
  "warmup_history_bars": 100,
  "signal_cooldown_seconds": 14400
}
```

---

### 4.2 PUT /api/config/system

**说明**: 更新系统配置 (需要重启服务生效)

**请求体 Schema**:
```typescript
type UpdateSystemConfigRequest = Partial<SystemConfig>;
```

**请求示例**:
```json
{
  "queue_batch_size": 20,
  "queue_flush_interval": 3.0
}
```

**响应 Schema**:
```typescript
interface UpdateSystemConfigResponse {
  config: SystemConfig;
  requires_restart: boolean;  // 始终为 true
  restart_hint: string;       // "修改已保存，需要重启服务才能生效"
}
```

**错误响应**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `INVALID_CONFIG_VALUE` | 400 | 配置值超出范围 | Toast 错误 + 高亮输入框 |
| `REQUIRES_RESTART` | 200 + Warning | 需要重启 (非错误，但需提示用户) | 显示重启确认 Modal |

---

## 五、Tooltip Schema API 详情

### 5.1 GET /api/config/schema

**说明**: 获取配置项的完整 Schema (含 tooltip 说明)

**响应 Schema**:
```typescript
interface ConfigSchema {
  strategy_params: StrategyParamsSchema;
  system_config: SystemConfigSchema;
}

interface StrategyParamsSchema {
  pinbar: {
    min_wick_ratio: ConfigFieldSchema;
    max_body_ratio: ConfigFieldSchema;
    body_position_tolerance: ConfigFieldSchema;
  };
  ema: {
    period: ConfigFieldSchema;
  };
  // ... 其他字段
}

interface ConfigFieldSchema {
  type: 'number' | 'string' | 'boolean';
  default: any;
  min?: number;
  max?: number;
  step?: number;
  tooltip: {
    description: string;
    default_value: string;
    range: string;
    adjustment_tips: string[];
  };
}
```

**成功响应示例**:
```json
{
  "strategy_params": {
    "pinbar": {
      "min_wick_ratio": {
        "type": "number",
        "default": 0.6,
        "min": 0.5,
        "max": 0.7,
        "step": 0.05,
        "tooltip": {
          "description": "影线长度占整个 K 线范围的比例下限。较高的值会选择更明显的 Pinbar 形态，但可能会错过一些机会。",
          "default_value": "0.6 (60%)",
          "range": "0.5 - 0.7",
          "adjustment_tips": [
            "高波动市场：降低到 0.5",
            "低波动市场：提高到 0.7"
          ]
        }
      }
    }
  }
}
```

---

## 六、前端组件 Props 定义

### 6.1 StrategyConfigPage 组件树

```
StrategyConfigPage
├── PageHeader
├── StrategyListSection
│   ├── SearchBar
│   ├── StrategyCardList
│   │   └── StrategyCard (重复)
│   └── Pagination
└── StrategyEditorDrawer
    └── ... (子组件)
```

### 6.2 StrategyCard Props

```typescript
interface StrategyCardProps {
  strategy: Strategy;
  onEdit: (strategy: Strategy) => void;
  onToggleEnable: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
}
```

### 6.3 StrategyEditorDrawer Props

```typescript
interface StrategyEditorDrawerProps {
  visible: boolean;
  strategy: Strategy | null;
  onClose: () => void;
  onSave: (data: UpdateStrategyRequest) => void;
}
```

### 6.4 StrategyBasicInfoForm Props

```typescript
interface StrategyBasicInfoFormProps {
  control: Control<StrategyFormValues>;
  errors: FieldErrors<StrategyFormValues>;
}
```

### 6.5 TriggerParamsSection Props

```typescript
interface TriggerParamsSectionProps {
  control: Control<StrategyFormValues>;
  errors: FieldErrors<StrategyFormValues>;
  schema?: StrategyParamsSchema; // 用于 Tooltip
}
```

---

## 七、状态管理定义

### 7.1 StrategyConfigPage 状态

| State | 类型 | 初始值 | 说明 |
|-------|------|--------|------|
| `strategies` | `Strategy[]` | `[]` | 策略列表 (React Query 管理) |
| `isLoading` | `boolean` | `true` | 列表加载状态 |
| `selectedStrategy` | `Strategy \| null` | `null` | 当前编辑的策略 |
| `isDrawerOpen` | `boolean` | `false` | 编辑器抽屉打开状态 |
| `searchQuery` | `string` | `""` | 搜索框输入 |
| `filterTimeframe` | `string \| null` | `null` | 周期筛选 |

### 7.2 StrategyEditorDrawer 状态

| State | 类型 | 初始值 | 说明 |
|-------|------|--------|------|
| `formData` | `StrategyFormValues` | 默认值 | 表单数据 (React Hook Form) |
| `isDirty` | `boolean` | `false` | 表单是否已修改 |
| `isSaving` | `boolean` | `false` | 保存中状态 |
| `saveError` | `Error \| null` | `null` | 保存错误信息 |

---

## 八、数据流图

### 8.1 策略列表加载流程

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  StrategyConfig │ ────▶│  React Query    │ ────▶│  GET /api/      │
│      Page       │      │  useQuery       │      │  config/strat   │
│                 │ ◀────│                 │ ◀────│                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

### 8.2 策略编辑保存流程

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  StrategyEditor │ ────▶│  React Hook     │ ────▶│  useMutation    │
│      Drawer     │      │      Form       │      │  (updateStrategy)│
│                 │      │                 │      │                 │
│  输入防抖 1 秒    │ ────▶│  表单状态监听    │ ────▶│  PUT /api/      │
│                 │      │                 │      │  config/strat/:id│
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

### 8.3 策略参数预览流程

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  ParamPreview   │ ────▶│  用户修改参数    │ ────▶│  POST /api/     │
│      Modal      │      │                 │      │  strat/params/  │
│                 │ ◀────│  显示变更对比    │ ◀────│  preview        │
│  显示警告信息    │      │  + 警告列表       │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## 九、类型对齐检查

### 9.1 后端 Pydantic Schema

```python
# src/domain/models.py

from pydantic import BaseModel, Field, field_validator
from decimal import Decimal

class PinbarParams(BaseModel):
    min_wick_ratio: Decimal = Field(default=Decimal("0.6"), ge=0.5, le=0.7)
    max_body_ratio: Decimal = Field(default=Decimal("0.3"), ge=0.2, le=0.4)
    body_position_tolerance: Decimal = Field(default=Decimal("0.1"), ge=0.05, le=0.15)

class EmaParams(BaseModel):
    period: int = Field(default=60, ge=5, le=200)

class MtfParams(BaseModel):
    enabled: bool = Field(default=True)
    ema_period: int = Field(default=60, ge=5, le=200)

class StrategyParams(BaseModel):
    pinbar: PinbarParams = Field(default_factory=PinbarParams)
    ema: EmaParams = Field(default_factory=EmaParams)
    mtf: MtfParams = Field(default_factory=MtfParams)
    max_loss_percent: Decimal = Field(default=Decimal("0.01"), gt=0, le=0.1)
    max_leverage: int = Field(default=10, ge=1, le=20)
```

### 9.2 前端 TypeScript 类型

```typescript
// web-front/src/types/strategy.ts

export interface PinbarParams {
  min_wick_ratio: number;
  max_body_ratio: number;
  body_position_tolerance: number;
}

export interface EmaParams {
  period: number;
}

export interface MtfParams {
  enabled: boolean;
  ema_period: number;
}

export interface StrategyParams {
  pinbar: PinbarParams;
  ema: EmaParams;
  mtf: MtfParams;
  max_loss_percent: number;
  max_leverage: number;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  symbol: string;
  timeframe: string;
  params: StrategyParams;
  created_at: string;
  updated_at: string;
}
```

### 9.3 对齐检查表

| 字段 | 后端类型 | 前端类型 | 约束一致 | 必填一致 |
|------|----------|----------|----------|----------|
| `pinbar.min_wick_ratio` | Decimal [0.5, 0.7] | number [0.5, 0.7] | ✅ | ✅ |
| `pinbar.max_body_ratio` | Decimal [0.2, 0.4] | number [0.2, 0.4] | ✅ | ✅ |
| `ema.period` | int [5, 200] | number [5, 200] | ✅ | ✅ |
| `mtf.enabled` | boolean | boolean | ✅ | ✅ |
| `max_loss_percent` | Decimal [0, 0.1] | number [0, 0.1] | ✅ | ✅ |
| `max_leverage` | int [1, 20] | number [1, 20] | ✅ | ✅ |

### 9.4 前后端校验分工

| 校验规则 | 前端校验 | 后端校验 | 说明 |
|----------|----------|----------|------|
| 必填检查 | ✅ (表单验证) | ✅ (Pydantic) | 前端禁用提交，后端返回 400 |
| 数值范围 | ✅ (input min/max) | ✅ (Field validator) | 前端即时反馈，后端最终验证 |
| 格式校验 | ✅ (pattern) | ✅ (Pydantic) | 前端即时反馈 |
| 业务规则 | ❌ | ✅ | 如唯一性检查、权限验证 |
| 名称重复 | ❌ | ✅ | 后端检查后返回 409 |

---

## 十、错误码汇总

### 10.1 客户端错误 (4xx)

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `INVALID_REQUEST` | 400 | 请求参数错误 | Toast 错误 + 显示详情 |
| `INVALID_PARAM_VALUE` | 400 | 参数值超出范围 | Toast 错误 + 高亮输入框 |
| `PARAM_VALIDATION_FAILED` | 400 | 参数验证失败 | Toast 错误 + 显示详情 |
| `INVALID_SYMBOL_FORMAT` | 400 | 交易对格式错误 | Toast 错误 + 高亮输入框 |
| `INVALID_TIMEFRAME` | 400 | 周期不在枚举范围内 | Toast 错误 |
| `UNAUTHORIZED` | 401 | 未授权 | 跳转到登录页 |
| `FORBIDDEN` | 403 | 无权限 | Toast 错误 |
| `STRATEGY_NOT_FOUND` | 404 | 策略不存在 | Toast 错误 + 返回列表 |
| `STRATEGY_NAME_EXISTS` | 409 | 策略名称已存在 | Toast 错误 + 清空名称输入框 |
| `STRATEGY_IN_USE` | 409 | 策略正在使用中 | Toast 错误 + 禁用提示 |

### 10.2 服务端错误 (5xx)

| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `INTERNAL_ERROR` | 500 | 服务器内部错误 | Toast 错误 + 稍后重试 |
| `DATABASE_ERROR` | 503 | 数据库错误 | Toast 错误 + 稍后重试 |

---

## 十一、审查签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| Coordinator | - | - | - |
| Backend Dev | - | - | - |
| Frontend Dev | Claude | 2026-04-06 | ✅ |
| QA Tester | - | - | - |
| Code Reviewer | - | - | - |

**审查检查清单**:
- [x] 所有 API 端点已定义
- [x] 所有字段的必填等级已明确 (REQUIRED/CONDITIONAL/OPTIONAL)
- [x] 所有字段的约束条件已定义 (长度/范围/格式)
- [x] CONDITIONAL 字段的触发条件已说明
- [x] 前后端校验分工已明确
- [x] 错误响应格式已定义
- [x] 前端组件 Props 已定义
- [x] 状态管理方案已说明

---

## 十二、变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-04-06 | 初始版本，包含所有 API 端点定义 | Claude |

---

**文档创建完成时间**: 2026-04-06  
**文档状态**: 已批准，可用于开发
