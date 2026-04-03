# 配置管理系统重构 - API 契约文档 (v1)

**文档编号**: CONTRACT-2026-001  
**创建日期**: 2026-04-03  
**状态**: ✅ 最终版  
**API 版本**: v1

---

## 0. API 版本化说明

所有 API 端点统一使用 `/api/v1/` 前缀，便于未来 API 升级：

```
/api/v1/config/*          # 配置管理
/api/v1/strategies/*      # 策略配置
/api/v1/snapshots/*       # 配置快照
/api/v1/history/*         # 配置历史
/api/v1/config/export     # 配置导出
/api/v1/config/import/*   # 配置导入
```

---

## 1. 配置管理 API 契约 (v1)

### 1.1 获取所有配置

**端点**: `GET /api/v1/config`

**响应** (200 OK):
```typescript
interface ConfigResponse {
  strategy: {
    id: number;
    name: string;
    description: string | null;
    triggers: TriggerConfig[];
    filters: FilterConfig[];
    logic_tree?: LogicNode;
    apply_to: string[];
    is_active: boolean;
  } | null;
  risk: RiskConfig;
  system: SystemConfig;
  symbols: SymbolConfig[];
  notifications: NotificationConfig[];
}

interface RiskConfig {
  max_loss_percent: number;
  max_total_exposure: number;
  max_leverage: number;
}

interface SystemConfig {
  history_bars: number;        // ⚠️ 修改需重启
  queue_batch_size: number;    // ⚠️ 修改需重启
  queue_flush_interval: number; // ⚠️ 修改需重启
}

interface SymbolConfig {
  id: number;
  symbol: string;
  is_core: boolean;
  is_enabled: boolean;
}

interface NotificationConfig {
  id: number;
  channel: 'feishu' | 'wecom' | 'telegram';
  webhook_url: string;
  is_enabled: boolean;
}
```

---

### 1.2 更新风控配置

**端点**: `PUT /api/v1/config/risk`

**请求**:
```typescript
interface UpdateRiskRequest {
  max_loss_percent?: number;  // 0.1 ~ 5.0
  max_total_exposure?: number; // 0.5 ~ 1.0
  max_leverage?: number;       // 1 ~ 125
}
```

**响应** (200 OK):
```typescript
interface UpdateConfigResponse {
  success: boolean;
  message: string;
  requires_restart: boolean;  // false = 已热重载
}
```

---

### 1.3 更新系统配置

**端点**: `PUT /api/v1/config/system`

**请求**:
```typescript
interface UpdateSystemRequest {
  history_bars?: number;
  queue_batch_size?: number;
  queue_flush_interval?: number;
}
```

**响应** (200 OK):
```typescript
interface UpdateConfigResponse {
  success: boolean;
  message: string;
  requires_restart: boolean;  // true = 需重启
}
```

---

### 1.4 获取币池列表

**端点**: `GET /api/v1/config/symbols`

**响应** (200 OK):
```typescript
interface SymbolListResponse {
  symbols: SymbolConfig[];
}
```

---

### 1.5 添加币种

**端点**: `POST /api/v1/config/symbols`

**请求**:
```typescript
interface AddSymbolRequest {
  symbol: string;  // 格式："BTC/USDT:USDT"
  is_core?: boolean;
  is_enabled?: boolean;
}
```

**响应** (201 Created):
```typescript
interface AddSymbolResponse {
  id: number;
  symbol: string;
  is_core: boolean;
  is_enabled: boolean;
}
```

---

### 1.6 移除币种

**端点**: `DELETE /api/v1/config/symbols/{id}`

**错误** (400 Bad Request):
```typescript
interface DeleteSymbolError {
  error: string;  // "核心币种不可删除"
}
```

---

### 1.7 获取通知配置列表

**端点**: `GET /api/v1/config/notifications`

**响应** (200 OK):
```typescript
interface NotificationListResponse {
  notifications: NotificationConfig[];
}
```

---

### 1.8 更新通知配置

**端点**: `PUT /api/v1/config/notifications/{id}`

**请求**:
```typescript
interface UpdateNotificationRequest {
  webhook_url?: string;
  is_enabled?: boolean;
}
```

---

### 1.9 添加通知渠道

**端点**: `POST /api/v1/config/notifications`

**请求**:
```typescript
interface AddNotificationRequest {
  channel: 'feishu' | 'wecom' | 'telegram';
  webhook_url: string;
  is_enabled?: boolean;
}
```

---

## 2. 策略配置 API 契约

### 2.1 获取策略列表

**端点**: `GET /api/v1/strategies`

**响应** (200 OK):
```typescript
interface StrategyListResponse {
  strategies: {
    id: number;
    name: string;
    description: string | null;
    is_active: boolean;
    created_at: string;
    updated_at: string;
  }[];
}
```

---

### 2.2 获取策略详情

**端点**: `GET /api/v1/strategies/{id}`

**响应** (200 OK):
```typescript
interface StrategyDetailResponse {
  id: number;
  name: string;
  description: string | null;
  triggers: TriggerConfig[];
  filters: FilterConfig[];
  logic_tree?: LogicNode;
  apply_to: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
```

---

### 2.3 创建策略

**端点**: `POST /api/v1/strategies`

**请求**:
```typescript
interface CreateStrategyRequest {
  name: string;
  description?: string;
  triggers: TriggerConfig[];
  filters: FilterConfig[];
  logic_tree?: LogicNode;
  apply_to: string[];
}
```

**响应** (201 Created):
```typescript
interface CreateStrategyResponse {
  id: number;
  name: string;
  message: string;
}
```

---

### 2.4 更新策略

**端点**: `PUT /api/v1/strategies/{id}`

**请求**:
```typescript
interface UpdateStrategyRequest {
  name?: string;
  description?: string;
  triggers?: TriggerConfig[];
  filters?: FilterConfig[];
  logic_tree?: LogicNode;
  apply_to?: string[];
}
```

---

### 2.5 删除策略

**端点**: `DELETE /api/v1/strategies/{id}`

**响应** (200 OK):
```typescript
interface DeleteStrategyResponse {
  success: boolean;
  message: string;
}
```

---

### 2.6 激活策略

**端点**: `POST /api/v1/strategies/{id}/activate`

**响应** (200 OK):
```typescript
interface ActivateStrategyResponse {
  success: boolean;
  message: string;
  requires_restart: boolean;  // false = 已热重载
}
```

---

## 3. 导入/导出 API 契约

### 3.1 导出配置

**端点**: `POST /api/v1/config/export`

**响应** (200 OK):
```typescript
interface ExportConfigResponse {
  success: boolean;
  yaml_content: string;
  download_url: string;
  exported_at: string;
}
```

**YAML 格式示例**:
```yaml
# 盯盘狗配置导出 - 2026-04-03T10:00:00Z
exported_at: "2026-04-03T10:00:00Z"
version: "1.0"

risk_config:
  max_loss_percent: 1.0
  max_total_exposure: 0.8
  max_leverage: 10

system_config:
  history_bars: 100
  queue_batch_size: 10
  queue_flush_interval: 5.0

symbols:
  - symbol: "BTC/USDT:USDT"
    is_core: true
    is_enabled: true

strategies:
  - name: "Pinbar+EMA60"
    triggers:
      - type: "pinbar"
        params:
          min_wick_ratio: 0.5
          max_body_ratio: 0.35
    filters:
      - type: "ema"
        params:
          period: 60
    apply_to:
      - "BTC/USDT:USDT:15m"
    is_active: true
```

---

### 3.2 导入预览

**端点**: `POST /api/v1/config/import/preview`

**请求**:
```typescript
interface ImportPreviewRequest {
  yaml_content: string;
}
```

**响应** (200 OK):
```typescript
interface ImportPreviewResponse {
  valid: boolean;
  changes: {
    category: 'strategy' | 'risk' | 'system' | 'symbol' | 'notification';
    action: 'create' | 'update' | 'delete';
    field?: string;
    old_value?: any;
    new_value?: any;
  }[];
  errors: {
    line?: number;
    field: string;
    message: string;
  }[];
  warnings: string[];
}
```

---

### 3.3 确认导入

**端点**: `POST /api/v1/config/import/confirm`

**请求**:
```typescript
interface ImportConfirmRequest {
  yaml_content: string;
  preview_id?: string;  // 可选，用于验证预览一致性
}
```

**响应** (200 OK):
```typescript
interface ImportConfirmResponse {
  success: boolean;
  message: string;
  requires_restart: boolean;
  applied_changes: number;  // 应用的变更数
}
```

---

## 4. 配置历史 API 契约

### 4.1 获取快照列表

**端点**: `GET /api/v1/snapshots`

**响应** (200 OK):
```typescript
interface SnapshotListResponse {
  snapshots: {
    id: number;
    name: string;
    description: string | null;
    created_at: string;
    created_by: string;
  }[];
}
```

---

### 4.2 创建快照

**端点**: `POST /api/v1/snapshots`

**请求**:
```typescript
interface CreateSnapshotRequest {
  name: string;
  description?: string;
}
```

**响应** (201 Created):
```typescript
interface CreateSnapshotResponse {
  id: number;
  name: string;
  message: string;
}
```

---

### 4.3 回滚快照

**端点**: `POST /api/v1/snapshots/{id}/rollback`

**请求** (可选):
```typescript
interface RollbackRequest {
  create_snapshot_before?: boolean;  // 恢复前是否创建当前配置快照，默认 true
}
```

**响应** (200 OK):
```typescript
interface RollbackSnapshotResponse {
  success: boolean;
  message: string;
  requires_restart: boolean;
  previous_snapshot_id?: number;  // 恢复前创建的快照 ID
}
```

---

### 4.4 自动快照

**端点**: `POST /api/v1/snapshots/auto`

**请求**:
```typescript
interface AutoSnapshotRequest {
  trigger: 'import' | 'bulk' | 'rollback' | 'strategy';  // 触发场景
  description?: string;  // 可选，覆盖默认描述
}
```

**响应** (201 Created):
```typescript
interface AutoSnapshotResponse {
  success: boolean;
  snapshot_id: number;
  snapshot_name: string;  // 自动生成，如 "auto-import-20260403-143022"
  created_at: string;
}
```

---

### 4.5 配置对比

#### 快照 vs 快照 对比

**端点**: `POST /api/v1/snapshots/compare`

**请求**:
```typescript
interface CompareSnapshotsRequest {
  source_snapshot_id: number;
  target_snapshot_id: number;
}
```

**响应** (200 OK):
```typescript
interface CompareSnapshotsResponse {
  source_snapshot: {
    id: number;
    name: string;
    created_at: string;
  };
  target_snapshot: {
    id: number;
    name: string;
    created_at: string;
  };
  changes: {
    category: 'strategy' | 'risk' | 'system' | 'symbol' | 'notification';
    action: 'added' | 'modified' | 'deleted';
    field?: string;
    source_value?: any;
    target_value?: any;
  }[];
  summary: {
    total_changes: number;
    added: number;
    modified: number;
    deleted: number;
  };
}
```

#### 历史 vs 历史 对比

**端点**: `POST /api/v1/history/compare`

**请求**:
```typescript
interface CompareHistoryRequest {
  source_history_id: number;
  target_history_id: number;
}
```

**响应**: 同上 `CompareSnapshotsResponse`

---

### 4.6 获取配置历史

**端点**: `GET /api/v1/history`

**查询参数**:
- `config_type`: string (可选) - 'strategy' | 'risk' | 'system' | 'symbol' | 'notification'
- `config_id`: number (可选) - 配置 ID
- `limit`: number (可选，默认 50)

**响应** (200 OK):
```typescript
interface HistoryListResponse {
  history: {
    id: number;
    config_type: string;
    config_id: number;
    action: 'create' | 'update' | 'delete';
    old_value: any | null;
    new_value: any | null;
    created_at: string;
    created_by: string;
  }[];
}
```

---

## 5. 错误响应契约

### 5.1 通用错误格式

```typescript
interface ErrorResponse {
  error: string;
  code?: string;
  details?: any;
}
```

### 5.2 常见错误

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 400 | CONFIG_VALIDATION_ERROR | 配置验证失败 |
| 400 | SYMBOL_FORMAT_ERROR | 币种格式错误 |
| 400 | CORE_SYMBOL_DELETE_ERROR | 核心币种不可删除 |
| 404 | STRATEGY_NOT_FOUND | 策略不存在 |
| 404 | SNAPSHOT_NOT_FOUND | 快照不存在 |
| 500 | CONFIG_PERSIST_ERROR | 配置持久化失败 |
| 500 | IMPORT_VALIDATION_ERROR | 导入验证失败 |

---

## 6. 前端类型定义

### 6.1 配置描述元数据

```typescript
interface ConfigDescription {
  label: string;
  description: string;
  unit?: string;
  min?: number;
  max?: number;
  readonly?: boolean;
  requires_restart?: boolean;
}

const CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  max_loss_percent: {
    label: '单笔最大损失',
    description: '每笔交易愿意承担的最大风险百分比。1% 表示如果触发止损，最多损失账户总额的 1%。建议范围：0.5%~2%',
    unit: '%',
    min: 0.1,
    max: 5.0
  },
  // ... 其他配置
};
```

---

## 7. 热重载规则表

| 配置类别 | 热重载 | 说明 |
|----------|--------|------|
| 策略配置 | ✅ 支持 | 重建 Strategy Runner |
| 风控配置 | ✅ 支持 | 原子替换 |
| 币池配置 | ✅ 支持 | 重新订阅 K 线 |
| 通知配置 | ✅ 支持 | 原子替换 |
| 系统配置 | ❌ 不支持 | 需重启系统 |

---

*文档版本：1.0 | 最后更新：2026-04-03*
