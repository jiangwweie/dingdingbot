# 配置管理功能 - 版本化快照方案 B - 技术设计文档

> **创建日期**: 2026-04-02
> **任务 ID**: P1-CONFIG-SNAPSHOT
> **版本**: v1.0
> **状态**: 待执行

---

## 1. 产品需求概述

### 1.1 MVP 范围

| 功能模块 | 说明 | 优先级 |
|----------|------|--------|
| 配置导出 | 下载脱敏后的 YAML 配置文件 | P0 |
| 配置导入 | 上传 YAML 验证后应用 | P0 |
| 手动快照 | 用户手动创建配置快照 | P0 |
| 自动快照 | 每次配置变更自动创建快照 | P0 |
| 快照列表 | 查看所有历史快照 | P1 |
| 快照回滚 | 恢复到历史快照版本 | P1 |
| 快照删除 | 删除指定快照（保护最近 N 个） | P2 |

### 1.2 自动快照策略

**用户决策**: 方案 B - 每次配置变更自动创建

| 触发场景 | 自动快照 | 说明 |
|----------|----------|------|
| PUT /api/config | ✅ 创建 | 配置热重载时 |
| POST /api/strategies | ✅ 创建 | 新增策略模板 |
| PUT /api/strategies/{id} | ✅ 创建 | 更新策略模板 |
| DELETE /api/strategies/{id} | ✅ 创建 | 删除策略模板 |
| POST /api/strategies/{id}/apply | ✅ 创建 | 应用策略到实盘 |

---

## 2. 架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  ConfigPage  │  │ SnapshotList │  │ ImportExport │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP REST API
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Config Management Endpoints                 │   │
│  │  GET    /api/config              - 获取当前配置          │   │
│  │  PUT    /api/config              - 更新配置 (自动快照)    │   │
│  │  GET    /api/config/export      - 导出 YAML              │   │
│  │  POST   /api/config/import      - 导入 YAML              │   │
│  │  GET    /api/config/snapshots   - 快照列表               │   │
│  │  POST   /api/config/snapshots   - 创建快照 (手动)        │   │
│  │  GET    /api/config/snapshots/{id} - 快照详情           │   │
│  │  POST   /api/config/snapshots/{id}/rollback - 回滚     │   │
│  │  DELETE /api/config/snapshots/{id} - 删除快照          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               ConfigSnapshotService                      │   │
│  │  - create_snapshot()      - 创建快照                     │   │
│  │  - get_snapshots()        - 查询快照列表                 │   │
│  │  - get_snapshot_by_id()   - 获取快照详情                 │   │
│  │  - rollback_to_snapshot() - 回滚到快照                   │   │
│  │  - delete_snapshot()      - 删除快照                     │   │
│  │  - auto_snapshot()        - 自动快照钩子                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               ConfigSnapshotRepository                   │   │
│  │  - SQLite 表：config_snapshots                          │   │
│  │  - 字段：id, version, config_json, description,          │   │
│  │           created_at, created_by, is_active              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SQLite Database                               │
│  TABLE: config_snapshots                                        │
│  - id INTEGER PRIMARY KEY AUTOINCREMENT                         │
│  - version TEXT NOT NULL                                        │
│  - config_json TEXT NOT NULL                                    │
│  - description TEXT                                             │
│  - created_at TEXT NOT NULL (ISO 8601)                          │
│  - created_by TEXT DEFAULT 'user'                               │
│  - is_active INTEGER DEFAULT 0                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流设计

#### 2.2.1 配置导出流程

```
Frontend                    API                      FileSystem
    │                        │                           │
    │ GET /api/config/export │                           │
    ├───────────────────────>│                           │
    │                        │                           │
    │                        │ 1. 获取当前配置 (脱敏)      │
    │                        ├──────────────────────────>│
    │                        │                           │
    │                        │ 2. 生成 YAML 内容           │
    │                        │                           │
    │  YAML 文件下载          │                           │
    │<───────────────────────│                           │
    │                        │                           │
```

#### 2.2.2 配置导入流程

```
Frontend                    API                      ConfigManager
    │                        │                           │
    │ POST /api/config/import │                          │
    │ (multipart/form-data)  │                           │
    ├───────────────────────>│                           │
    │                        │                           │
    │                        │ 1. 解析 YAML 文件          │
    │                        │ 2. 验证配置 Schema          │
    │                        ├──────────────────────────>│
    │                        │                           │
    │                        │ 3. 创建快照 (备份当前)      │
    │                        │ 4. 应用新配置 (热重载)      │
    │                        │                           │
    │  成功/失败响应          │                           │
    │<───────────────────────│                           │
    │                        │                           │
```

#### 2.2.3 自动快照触发流程

```
Config Update              ConfigManager         SnapshotService
    │                           │                     │
    │ 1. 调用 update_config()   │                     │
    ├──────────────────────────>│                     │
    │                           │                     │
    │                           │ 2. 调用自动快照钩子   │
    │                           ├────────────────────>│
    │                           │                     │
    │                           │                     │ 3. 保存当前配置
    │                           │                     │ 4. 生成版本号
    │                           │                     │ 5. 入库
    │                           │<────────────────────┤
    │                           │                     │
    │                           │ 6. 继续执行热重载     │
    │<──────────────────────────┤                     │
    │                           │                     │
```

### 2.3 自动快照触发机制

```python
# src/application/config_manager.py

class ConfigManager:
    async def update_user_config(
        self, 
        new_config_dict: Dict[str, Any],
        auto_snapshot: bool = True,  # 新增参数
        snapshot_description: str = ""  # 快照描述
    ) -> UserConfig:
        """
        Hot-reload user configuration with optional auto-snapshot.
        
        Args:
            new_config_dict: Partial or full user config dictionary
            auto_snapshot: Whether to create snapshot before update
            snapshot_description: Description for the snapshot
        """
        # Step 1: Create auto-snapshot (if enabled)
        if auto_snapshot and self._snapshot_service:
            await self._snapshot_service.create_auto_snapshot(
                config=self._user_config,
                description=snapshot_description or "配置变更自动快照"
            )
        
        # Step 2~5: Existing atomic update logic...
```

**触发器注册**:
```python
# src/interfaces/api.py

# 依赖注入
_snapshot_service: Optional[ConfigSnapshotService] = None

def set_dependencies(
    # ... 其他依赖 ...
    snapshot_service: Optional[ConfigSnapshotService] = None,
):
    global _snapshot_service
    _snapshot_service = snapshot_service
```

---

## 3. 接口契约表

### 3.1 API 端点定义

| 端点 | 方法 | 说明 | 请求体 | 响应体 | 错误码 |
|------|------|------|--------|--------|--------|
| `/api/config` | GET | 获取当前配置（脱敏） | - | `ConfigResponse` | - |
| `/api/config` | PUT | 更新配置（自动快照） | `ConfigUpdateRequest` | `ConfigResponse` | `CONFIG-001` |
| `/api/config/export` | GET | 导出 YAML 文件 | - | YAML 文件下载 | - |
| `/api/config/import` | POST | 导入 YAML 配置 | `multipart/form-data` | `ConfigResponse` | `CONFIG-002`, `CONFIG-003` |
| `/api/config/snapshots` | GET | 快照列表（分页） | QueryParams | `SnapshotListResponse` | - |
| `/api/config/snapshots` | POST | 创建手动快照 | `CreateSnapshotRequest` | `SnapshotResponse` | - |
| `/api/config/snapshots/{id}` | GET | 快照详情 | - | `SnapshotDetailResponse` | `CONFIG-004` |
| `/api/config/snapshots/{id}/rollback` | POST | 回滚到快照 | - | `ConfigResponse` | `CONFIG-004`, `CONFIG-005` |
| `/api/config/snapshots/{id}` | DELETE | 删除快照 | - | `DeleteResponse` | `CONFIG-004`, `CONFIG-006` |

### 3.2 请求/响应 Schema

#### 3.2.1 获取配置（GET /api/config）

**响应体** `ConfigResponse`:
```python
class ConfigResponse(BaseModel):
    status: Literal["success"]
    config: Dict[str, Any]  # 脱敏后的配置
    created_at: str  # ISO 8601
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 是 | 固定为 "success" |
| `config` | object | 是 | 脱敏后的配置对象 |
| `created_at` | string | 是 | 配置最后更新时间 |

#### 3.2.2 更新配置（PUT /api/config）

**请求体** `ConfigUpdateRequest`:
```python
class ConfigUpdateRequest(BaseModel):
    """配置更新请求（支持部分更新）"""
    exchange: Optional[ExchangeConfigUpdate] = None
    user_symbols: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    active_strategies: Optional[List[StrategyDefinition]] = None
    risk: Optional[RiskConfigUpdate] = None
    asset_polling: Optional[AssetPollingConfig] = None
    notification: Optional[NotificationConfigUpdate] = None
    mtf_ema_period: Optional[int] = None
    mtf_mapping: Optional[Dict[str, str]] = None
```

| 字段 | 类型 | 必填 | 约束条件 | 说明 |
|------|------|------|----------|------|
| `exchange` | object | 否 | - | 交易所配置（部分更新） |
| `user_symbols` | array | 否 | `minItems: 0` | 用户自定义币种列表 |
| `timeframes` | array | 否 | `minItems: 1` | 监控的时间周期 |
| `active_strategies` | array | 否 | - | 活跃策略列表 |
| `risk` | object | 否 | - | 风控配置（部分更新） |
| `asset_polling` | object | 否 | - | 资产轮询配置 |
| `notification` | object | 否 | - | 通知配置（部分更新） |
| `mtf_ema_period` | integer | 否 | `min: 5, max: 200` | MTF EMA 周期 |
| `mtf_mapping` | object | 否 | - | MTF 时间周期映射 |

**响应体** `ConfigResponse`（同上）

**错误码**:
| 错误码 | HTTP 状态码 | 说明 | 前端处理方式 |
|--------|-------------|------|--------------|
| `CONFIG-001` | 422 | 配置验证失败 | toast 显示错误详情 |
| `CONFIG-002` | 400 | 配置导入格式错误 | toast 显示 YAML 解析错误 |
| `CONFIG-003` | 400 | 配置导入验证失败 | toast 显示字段验证错误 |

#### 3.2.3 导出配置（GET /api/config/export）

**响应**:
- Content-Type: `application/x-yaml`
- Content-Disposition: `attachment; filename="user_config_{timestamp}.yaml"`
- Body: YAML 文件内容（脱敏）

#### 3.2.4 导入配置（POST /api/config/import）

**请求体** `multipart/form-data`:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | YAML 配置文件 |
| `description` | string | 否 | 快照描述（默认："配置导入"） |

**响应体** `ConfigResponse`

**错误码**:
| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `CONFIG-002` | 400 | YAML 解析失败 |
| `CONFIG-003` | 422 | 配置验证失败 |

#### 3.2.5 快照列表（GET /api/config/snapshots）

**请求参数** (Query Params):
| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `limit` | integer | 否 | 20 | `min: 1, max: 100` | 每页数量 |
| `offset` | integer | 否 | 0 | `min: 0` | 偏移量 |
| `created_by` | string | 否 | - | - | 创建者筛选 |
| `is_active` | boolean | 否 | - | - | 是否当前激活 |

**响应体** `SnapshotListResponse`:
```python
class SnapshotListItem(BaseModel):
    id: int
    version: str
    description: str
    created_at: str
    created_by: str
    is_active: bool

class SnapshotListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    data: List[SnapshotListItem]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `total` | integer | 是 | 总记录数 |
| `limit` | integer | 是 | 每页数量 |
| `offset` | integer | 是 | 偏移量 |
| `data` | array | 是 | 快照列表 |

#### 3.2.6 创建快照（POST /api/config/snapshots）

**请求体** `CreateSnapshotRequest`:
```python
class CreateSnapshotRequest(BaseModel):
    version: str = Field(..., pattern=r"^v\d+\.\d+\.\d+$")  # 语义化版本号
    description: str = Field(default="", max_length=200)
```

| 字段 | 类型 | 必填 | 约束条件 | 默认值 | 说明 |
|------|------|------|----------|--------|------|
| `version` | string | 是 | `pattern: "^v\d+\.\d+\.\d+$"` | - | 语义化版本号 |
| `description` | string | 否 | `maxLength: 200` | `""` | 快照描述 |

**响应体** `SnapshotResponse`:
```python
class SnapshotResponse(BaseModel):
    id: int
    version: str
    description: str
    created_at: str
    created_by: str
    is_active: bool
```

#### 3.2.7 快照详情（GET /api/config/snapshots/{id}）

**路径参数**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | integer | 是 | 快照 ID |

**响应体** `SnapshotDetailResponse`:
```python
class SnapshotDetailResponse(BaseModel):
    id: int
    version: str
    config: Dict[str, Any]  # 脱敏配置
    description: str
    created_at: str
    created_by: str
    is_active: bool
```

**错误码**:
| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `CONFIG-004` | 404 | 快照不存在 |

#### 3.2.8 快照回滚（POST /api/config/snapshots/{id}/rollback）

**路径参数**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | integer | 是 | 快照 ID |

**响应体** `ConfigResponse`

**错误码**:
| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `CONFIG-004` | 404 | 快照不存在 |
| `CONFIG-005` | 500 | 回滚失败（配置验证失败） |

#### 3.2.9 删除快照（DELETE /api/config/snapshots/{id}）

**路径参数**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | integer | 是 | 快照 ID |

**响应体** `DeleteResponse`:
```python
class DeleteResponse(BaseModel):
    status: Literal["success"]
    message: str
```

**错误码**:
| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `CONFIG-004` | 404 | 快照不存在 |
| `CONFIG-006` | 400 | 不能删除最近 N 个快照（保护机制） |

---

## 4. 数据库设计

### 4.1 表结构

```sql
-- config_snapshots 表
CREATE TABLE IF NOT EXISTS config_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL UNIQUE,
    config_json     TEXT NOT NULL,           -- JSON 字符串（已脱敏）
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL,           -- ISO 8601 UTC
    created_by      TEXT DEFAULT 'user',
    is_active       INTEGER DEFAULT 0,       -- 0: 历史快照，1: 当前激活
    
    -- 索引
    INDEX idx_config_active (is_active),
    INDEX idx_config_created_at (created_at DESC)
);
```

### 4.2 Repository 接口

```python
class ConfigSnapshotRepository:
    """配置快照数据持久层"""
    
    async def create(self, snapshot: ConfigSnapshot) -> int:
        """创建快照，返回 ID"""
        
    async def get_by_id(self, id: int) -> Optional[ConfigSnapshot]:
        """按 ID 获取快照详情"""
        
    async def get_list(
        self, 
        limit: int = 20, 
        offset: int = 0,
        created_by: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[List[ConfigSnapshot], int]:
        """获取快照列表（分页）"""
        
    async def get_active(self) -> Optional[ConfigSnapshot]:
        """获取当前激活的快照"""
        
    async def set_active(self, id: int) -> None:
        """设置指定快照为激活状态（其他自动设为非激活）"""
        
    async def delete(self, id: int) -> bool:
        """删除快照"""
        
    async def count(self) -> int:
        """获取快照总数"""
```

---

## 5. 服务层设计

### 5.1 ConfigSnapshotService

```python
class ConfigSnapshotService:
    """配置快照业务逻辑层"""
    
    def __init__(
        self, 
        repository: ConfigSnapshotRepository,
        config_manager: ConfigManager
    ):
        self.repo = repository
        self.config_manager = config_manager
    
    async def create_manual_snapshot(
        self, 
        version: str, 
        description: str = "",
        created_by: str = "user"
    ) -> ConfigSnapshot:
        """创建手动快照"""
        
    async def create_auto_snapshot(
        self, 
        config: UserConfig,
        description: str = "配置变更自动快照"
    ) -> ConfigSnapshot:
        """创建自动快照（版本号自动生成）"""
        
    async def rollback_to_snapshot(self, id: int) -> UserConfig:
        """回滚到指定快照"""
        
    async def delete_snapshot(self, id: int, protect_recent_count: int = 5) -> bool:
        """删除快照（保护最近 N 个）"""
```

### 5.2 自动快照钩子

```python
# src/application/config_manager.py

class ConfigManager:
    def __init__(self, config_dir: Optional[str] = None):
        # ... 现有初始化代码 ...
        self._snapshot_service: Optional[ConfigSnapshotService] = None
    
    def set_snapshot_service(self, service: ConfigSnapshotService) -> None:
        """注入快照服务依赖"""
        self._snapshot_service = service
    
    async def update_user_config(
        self, 
        new_config_dict: Dict[str, Any],
        auto_snapshot: bool = True,
        snapshot_description: str = ""
    ) -> UserConfig:
        """更新用户配置（可选自动快照）"""
        if auto_snapshot and self._snapshot_service:
            # 在更新前创建快照
            await self._snapshot_service.create_auto_snapshot(
                config=self._user_config,
                description=snapshot_description or f"配置变更自动快照 - {datetime.now(timezone.utc).isoformat()}"
            )
        
        # ... 现有更新逻辑 ...
```

---

## 6. 前端设计

### 6.1 组件树结构

```
ConfigManagement
├── ConfigEditor
│   ├── ExchangeConfigForm
│   ├── RiskConfigForm
│   ├── StrategyConfigPanel
│   └── NotificationConfigForm
├── SnapshotPanel
│   ├── SnapshotList
│   │   └── SnapshotItem
│   ├── SnapshotDetail (Drawer)
│   └── SnapshotActions
└── ImportExport
    ├── ExportButton
    └── ImportDialog
```

### 6.2 状态管理

```typescript
interface ConfigState {
  currentConfig: UserConfig | null;
  snapshots: SnapshotListItem[];
  loading: boolean;
  error: string | null;
  importDialogOpen: boolean;
  snapshotDetailDrawerOpen: boolean;
}

interface ConfigActions {
  fetchConfig: () => Promise<void>;
  updateConfig: (config: Partial<UserConfig>) => Promise<void>;
  exportConfig: () => void;
  importConfig: (file: File, description?: string) => Promise<void>;
  fetchSnapshots: (params: SnapshotQueryParams) => Promise<void>;
  createSnapshot: (version: string, description: string) => Promise<void>;
  rollbackToSnapshot: (id: number) => Promise<void>;
  deleteSnapshot: (id: number) => Promise<void>;
}
```

### 6.3 API 函数封装

```typescript
// web-front/src/lib/api.ts

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch('/api/config');
  return res.json();
}

export async function updateConfig(config: Partial<UserConfig>): Promise<ConfigResponse> {
  const res = await fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  return res.json();
}

export async function exportConfig(): Promise<Blob> {
  const res = await fetch('/api/config/export');
  return res.blob();
}

export async function importConfig(
  file: File, 
  description?: string
): Promise<ConfigResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (description) formData.append('description', description);
  
  const res = await fetch('/api/config/import', {
    method: 'POST',
    body: formData,
  });
  return res.json();
}

export async function fetchSnapshots(
  params: { limit?: number; offset?: number } = {}
): Promise<SnapshotListResponse> {
  const qs = new URLSearchParams(params as Record<string, string>);
  const res = await fetch(`/api/config/snapshots?${qs}`);
  return res.json();
}

export async function createSnapshot(
  version: string, 
  description: string
): Promise<SnapshotResponse> {
  const res = await fetch('/api/config/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version, description }),
  });
  return res.json();
}

export async function rollbackToSnapshot(id: number): Promise<ConfigResponse> {
  const res = await fetch(`/api/config/snapshots/${id}/rollback`, {
    method: 'POST',
  });
  return res.json();
}

export async function deleteSnapshot(id: number): Promise<DeleteResponse> {
  const res = await fetch(`/api/config/snapshots/${id}`, {
    method: 'DELETE',
  });
  return res.json();
}
```

---

## 7. 任务分解

### 7.1 后端任务（预计 8h）

| ID | 任务 | 工时 | 优先级 | 说明 |
|----|------|------|--------|------|
| B1 | 创建 `ConfigSnapshot` Pydantic 模型 | 0.5h | P0 | `src/domain/models.py` |
| B2 | 实现 `ConfigSnapshotRepository` | 2h | P0 | SQLite 持久层 |
| B3 | 实现 `ConfigSnapshotService` | 2h | P0 | 业务逻辑层 |
| B4 | 实现 API 端点（导出/导入） | 1.5h | P0 | `/api/config/export`, `/api/config/import` |
| B5 | 实现 API 端点（快照 CRUD） | 1.5h | P1 | 列表/详情/创建/删除/回滚 |
| B6 | 集成自动快照钩子到 `ConfigManager` | 0.5h | P0 | 配置变更自动触发 |

### 7.2 前端任务（预计 10h）

| ID | 任务 | 工时 | 优先级 | 说明 |
|----|------|------|--------|------|
| F1 | 创建 API 函数封装 | 1h | P0 | `web-front/src/lib/api.ts` |
| F2 | 配置页面重构 | 2h | P0 | 分离配置编辑器和快照面板 |
| F3 | 导出按钮组件 | 0.5h | P0 | 一键下载 YAML |
| F4 | 导入对话框组件 | 1.5h | P0 | 文件上传 + 预览 + 验证 |
| F5 | 快照列表组件 | 2h | P1 | 表格展示 + 分页 |
| F6 | 快照详情抽屉 | 1.5h | P1 | 配置 diff 预览 |
| F7 | 快照操作（回滚/删除） | 1.5h | P1 | 确认对话框 + Toast |

### 7.3 测试任务（预计 6h）

| ID | 任务 | 工时 | 优先级 | 说明 |
|----|------|------|--------|------|
| T1 | Repository 单元测试 | 1.5h | P0 | CRUD 操作测试 |
| T2 | Service 单元测试 | 2h | P0 | 业务逻辑测试 |
| T3 | API 集成测试 | 1.5h | P0 | 端点测试 |
| T4 | 前端 E2E 测试 | 1h | P1 | 配置管理流程测试 |

---

## 8. 风险评估

### 8.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **R1: YAML 导入验证不充分** | 高 | 中 | 1. 严格 Pydantic 验证；2. 导入前预览；3. 自动备份当前配置 |
| **R2: 自动快照性能影响** | 中 | 低 | 1. 异步非阻塞创建；2. 配置更新不受阻；3. 批量更新时合并快照 |
| **R3: 快照数据库锁竞争** | 中 | 低 | 1. 使用 WAL 模式；2. 读写分离；3. 异步队列落盘 |
| **R4: 配置热重载与快照时序问题** | 高 | 低 | 1. 先快照后更新；2. 原子操作；3. 事务保护 |
| **R5: 敏感信息泄露** | 高 | 中 | 1. 导出时脱敏；2. 快照 JSON 脱敏存储；3. 审计日志 |

### 8.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **R6: 误删除重要快照** | 高 | 中 | 1. 保护最近 N 个快照；2. 删除确认对话框；3. 软删除机制 |
| **R7: 回滚后配置不兼容** | 高 | 低 | 1. 回滚前验证；2. 回滚失败 Graceful 降级；3. 版本兼容性检查 |

---

## 9. 交付验收标准

### 9.1 功能验收

- [ ] 配置导出功能正常，YAML 文件可下载
- [ ] 配置导入功能正常，验证后应用
- [ ] 手动快照创建成功
- [ ] 自动快照在配置变更时触发
- [ ] 快照列表正确展示（分页）
- [ ] 快照回滚功能正常
- [ ] 快照删除功能正常（保护机制生效）

### 9.2 质量验收

- [ ] 单元测试覆盖率 > 85%
- [ ] E2E 测试通过率 100%
- [ ] 无 P0/P1 级 Bug
- [ ] 代码审查通过

---

## 10. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-04-02 | 初始版本 | AI Architect |

---

**审查检查清单**:
- [ ] 所有 API 端点已定义
- [ ] 请求/响应 Schema 完整
- [ ] 错误码系统完整
- [ ] 数据库设计合理
- [ ] 前端组件树清晰
- [ ] 任务分解可执行
- [ ] 风险评估全面

---

*本文档作为配置管理功能开发的 SSOT，所有开发、审查、测试工作应以此为基准。*
