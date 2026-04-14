# 配置页面整合与 YAML 全面迁移设计文档

> **日期**: 2026-04-11
> **作者**: Team Architect
> **状态**: Draft
> **关联任务**: #4, #5, #6, #7
> **覆盖范围**: YAML 运行时迁移到 DB + 配置页面整合 + 生效配置总览

---

## 目录

1. [现状分析](#1-现状分析)
2. [Part A: YAML → DB 迁移方案](#2-part-a-yaml--db-迁移方案)
3. [Part B: 配置页面整合方案](#3-part-b-配置页面整合方案)
4. [Part C: 生效配置总览 API + 前端](#4-part-c-生效配置总览-api--前端)
5. [执行顺序与依赖图](#5-执行顺序与依赖图)
6. [风险评估与回滚方案](#6-风险评估与回滚方案)
7. [工作量估算与任务分解](#7-工作量估算与任务分解)

---

## 1. 现状分析

### 1.1 当前配置数据流总览

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│  user.yaml    │────▶│ ConfigManager    │────▶│ SignalPipeline │
│  (YAML 文件)  │     │ get_user_config() │     │ / StrategyEngine│
└──────────────┘     └──────────────────┘     └────────────────┘
       │                      │
       │ YAML fallback        │ DB reads
       ▼                      ▼
┌──────────────┐     ┌──────────────────┐
│ UserConfig    │     │ SQLite DB        │
│ Exchange/TF/  │     │ strategies,      │
│ AssetPolling/ │     │ risk_configs,    │
│ Notification  │     │ system_configs   │
└──────────────┘     └──────────────────┘
```

### 1.2 当前 YAML 读取位置清单

**ConfigManager (`src/application/config_manager.py`):**

| 方法 | 行号 | 从 YAML 读取什么 |
|------|------|------------------|
| `_load_user_config_from_yaml()` | 982 | 完整 UserConfig (exchange, timeframes, asset_polling, notification) |
| `_build_user_config_dict()` | 880 | `yaml_config.exchange`, `yaml_config.timeframes`, `yaml_config.asset_polling` |
| `_build_notification_config()` | 959 | YAML fallback (当 DB 无数据时) |
| `get_user_config_sync()` | 850 | 完全依赖 YAML |

**ConfigRepository (`src/application/config/config_repository.py`):**

| 方法 | 行号 | 从 YAML 读取什么 |
|------|------|------------------|
| `_load_user_config_from_yaml()` | 757 | 完整 UserConfig |
| `get_user_config_dict()` | 725 | `yaml_config.exchange`, `yaml_config.timeframes`, `yaml_config.asset_polling` |
| `_build_notification_config()` | 800 | YAML fallback |
| `update_user_config_item()` | 821 | **直接写回 YAML 文件** |

### 1.3 当前 DB 读取位置清单

| 配置项 | 存储表 | 读取方法 |
|--------|--------|----------|
| 策略定义 | `strategies` | `_load_strategies_from_db()` |
| 风控参数 | `risk_configs` | `_load_risk_config()` |
| 系统参数 | `system_configs` | `_load_system_config()` |
| 通知渠道 | `notifications` | `_build_notification_config()` (DB 优先，YAML fallback) |
| 币种列表 | `symbols` | 通过 `_build_user_config_dict()` |

### 1.4 从 YAML 读取但尚未入库的配置项

| 配置项 | 当前存储 | Pydantic 模型 | 影响范围 |
|--------|----------|---------------|----------|
| **exchange.name** | `user.yaml` | `ExchangeConfig` | ExchangeGateway 初始化 |
| **exchange.api_key** | `user.yaml` | `ExchangeConfig` | 交易所认证 |
| **exchange.api_secret** | `user.yaml` | `ExchangeConfig` | 交易所认证 |
| **exchange.testnet** | `user.yaml` | `ExchangeConfig` | 测试网/实网切换 |
| **timeframes** | `user.yaml` | `List[str]` | K线订阅、策略作用域 |
| **asset_polling.enabled** | `user.yaml` (隐含) | `AssetPollingConfig` | 资产轮询开关 |
| **asset_polling.interval_seconds** | `user.yaml` | `AssetPollingConfig` | 轮询频率 |

### 1.5 核心模型定义 (`src/application/config_manager.py`)

```python
class ExchangeConfig(BaseModel):        # 行 124
    name: str
    api_key: str
    api_secret: str
    testnet: bool = False

class AssetPollingConfig(BaseModel):    # 行 140
    interval_seconds: int = 60

class NotificationChannel(BaseModel):   # 行 144
    type: str         # 'feishu' or 'wecom'
    webhook_url: str

class UserConfig(BaseModel):            # 行 160
    exchange: ExchangeConfig
    timeframes: List[str]
    active_strategies: List[StrategyDefinition]
    risk: RiskConfig
    asset_polling: AssetPollingConfig
    notification: NotificationConfig
    mtf_ema_period: int
    mtf_mapping: Dict[str, str]
```

### 1.6 现有 API 路由 (`src/interfaces/api_v1_config.py`)

当前前缀: `prefix="/api/v1/config"` (行 664)

已有端点: `/risk`, `/system`, `/strategies`, `/symbols`, `/notifications`, `/export`, `/import/*`, `/snapshots/*`, `/history/*`

**缺失端点**: exchange 配置 CRUD, timeframes CRUD, effective config 总览

### 1.7 结论

**核心发现**: 当前系统处于"混合模式" -- 策略/风控/系统参数已入库，但交易所凭证、时间周期、资产轮询仍在 YAML 中。本次设计目标是**彻底消除 YAML 运行时读取**，实现 DB-only 运行时配置。

---

## 2. Part A: YAML → DB 迁移方案

### 2.1 新增数据库表 DDL

#### 2.1.1 `exchange_configs` 表

```sql
-- ============================================================
-- 8. exchange_configs - 交易所连接配置表
-- ============================================================
-- 存储交易所连接凭证（单例模式，id='primary'）
-- 设计原则：与 system_configs/risk_configs 一致的单例模式
-- ============================================================
CREATE TABLE IF NOT EXISTS exchange_configs (
    id TEXT PRIMARY KEY DEFAULT 'primary',              -- 固定为'primary'（支持未来多交易所）
    exchange_name TEXT NOT NULL DEFAULT 'binance',       -- CCXT 交易所 ID (binance/bybit/okx)
    api_key TEXT NOT NULL,                               -- API Key
    api_secret TEXT NOT NULL,                            -- API Secret
    testnet BOOLEAN DEFAULT TRUE,                        -- 是否使用测试网
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1                            -- 乐观锁版本号
);

CREATE INDEX IF NOT EXISTS idx_exchange_configs_updated ON exchange_configs(updated_at);
```

**设计说明**:
- 使用 `id='primary'` 单例模式（与 `system_configs`/`risk_configs` 一致）
- `exchange_name` 存储 CCXT ID（如 `binance`, `bybit`, `okx`）
- `api_key`/`api_secret` 明文存储（与现有 YAML 存储方式一致；加密存储留作后续 Phase）

#### 2.1.2 扩展 `system_configs` 表

```sql
-- 扩展列（通过 ALTER TABLE 添加）：
ALTER TABLE system_configs ADD COLUMN timeframes TEXT NOT NULL DEFAULT '["15m","1h"]';
ALTER TABLE system_configs ADD COLUMN asset_polling_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE system_configs ADD COLUMN asset_polling_interval INTEGER DEFAULT 60;
```

**注意**: SQLite `ALTER TABLE ADD COLUMN` 不会修改已有行的默认值，已有行将为 NULL。需要在迁移脚本中显式 UPDATE。

#### 2.1.3 新增 `migration_metadata` 表

```sql
-- ============================================================
-- 9. migration_metadata - 迁移状态追踪表
-- ============================================================
CREATE TABLE IF NOT EXISTS migration_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初始状态
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('yaml_fully_migrated', 'false');
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('one_time_import_done', 'false');
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('import_version', 'v1');
```

### 2.2 代码变更位置与详细说明

#### 2.2.1 `src/infrastructure/db/config_tables.sql`

**新增**:
- `exchange_configs` 表定义
- `migration_metadata` 表定义
- `system_configs` 新增列

**修改**:
- 更新文件头部注释：`7 张核心表` → `9 张核心表`

#### 2.2.2 `src/application/config/config_repository.py`

**新增方法**:

```python
async def get_exchange_config(self) -> ExchangeConfig:
    """从 DB 获取交易所连接配置。"""

async def update_exchange_config(self, config: ExchangeConfig) -> None:
    """更新交易所连接配置。触发 config_history 记录。"""

async def get_timeframes(self) -> List[str]:
    """从 DB 获取监控时间周期列表。"""

async def update_timeframes(self, timeframes: List[str]) -> None:
    """更新监控时间周期列表。"""

async def get_asset_polling_config(self) -> AssetPollingConfig:
    """从 DB 获取资产轮询配置。"""

async def update_asset_polling_config(self, config: AssetPollingConfig) -> None:
    """更新资产轮询配置。"""
```

**修改方法**:

| 方法 | 当前行为 | 目标行为 |
|------|----------|----------|
| `get_user_config_dict()` | 混合读取 YAML + DB (行 725) | 纯 DB 读取所有配置 |
| `_build_notification_config()` | DB 优先 + YAML fallback (行 800) | 纯 DB 读取，无 fallback |
| `update_user_config_item()` | 直接写回 YAML (行 821) | 写 DB 对应表 |
| `_initialize_default_configs()` | 初始化 system/risk/symbols | 新增初始化 exchange 默认值 |

#### 2.2.3 `src/application/config_manager.py`

**新增方法**:

```python
async def _perform_yaml_import(self) -> bool:
    """
    一次性 YAML → DB 导入。

    仅在以下条件同时满足时执行:
    1. migration_metadata.one_time_import_done == 'false'
    2. exchange_configs 表为空
    3. config/user.yaml 文件存在

    Returns:
        True 表示执行了导入，False 表示跳过
    """
```

**修改 `initialize_from_db()`** (行 330):
- 在 `_validate_and_apply_default_configs()` 之后，添加 `await self._perform_yaml_import()` 调用
- 在加载缓存阶段新增 exchange/timeframes/asset_polling 的缓存加载

**修改方法**:

| 方法 | 当前行为 | 目标行为 |
|------|----------|----------|
| `_load_user_config_from_yaml()` (行 982) | 运行时读取 YAML | **废弃**为运行时方法，保留仅用于 export 功能 |
| `get_user_config_sync()` (行 850) | 调用 YAML 解析 | 改为从 `_user_config_cache` 返回同步快照 |
| `_build_user_config_dict()` (行 880) | 混合 YAML + DB | 纯 DB 读取 |
| `_build_notification_config()` (行 959) | DB + YAML fallback | 纯 DB 读取 |

#### 2.2.4 `src/application/signal_pipeline.py`

**潜在影响**: 需检查是否有直接调用 `_load_user_config_from_yaml()` 的代码。如有，改为通过 ConfigManager 的公共接口获取。

### 2.3 `_perform_yaml_import()` 详细逻辑

```python
async def _perform_yaml_import(self) -> bool:
    """One-time YAML → DB migration on first startup."""

    # Step 1: Check if already done
    meta = await self._get_migration_meta()
    if meta.get("one_time_import_done") == "true":
        logger.info("YAML import: already completed, skipping")
        return False

    # Step 2: Check if exchange_configs already has data
    async with self._db.execute(
        "SELECT COUNT(*) as cnt FROM exchange_configs WHERE id = 'primary'"
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["cnt"] > 0:
            logger.info("YAML import: exchange_configs already populated, marking done")
            await self._set_migration_meta("one_time_import_done", "true")
            return False

    # Step 3: Check if user.yaml exists
    user_yaml = self.config_dir / 'user.yaml'
    if not user_yaml.exists():
        logger.info("YAML import: user.yaml not found, skipping (using defaults)")
        await self._set_migration_meta("one_time_import_done", "true")
        await self._set_migration_meta("yaml_fully_migrated", "false")
        return False

    # Step 4: Parse and insert into DB
    try:
        with open(user_yaml, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)

        # 4a. Insert exchange config
        exchange = yaml_data.get('exchange', {})
        await self._db.execute("""
            INSERT INTO exchange_configs (id, exchange_name, api_key, api_secret, testnet)
            VALUES ('primary', ?, ?, ?, ?)
        """, (
            exchange.get('name', 'binance'),
            exchange.get('api_key', ''),
            exchange.get('api_secret', ''),
            exchange.get('testnet', True),
        ))

        # 4b. Insert timeframes into system_configs
        timeframes = yaml_data.get('timeframes', ['15m', '1h'])
        await self._db.execute("""
            UPDATE system_configs
            SET timeframes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 'global'
        """, (json.dumps(timeframes),))

        # 4c. Insert asset_polling into system_configs
        polling = yaml_data.get('asset_polling', {})
        await self._db.execute("""
            UPDATE system_configs
            SET asset_polling_enabled = ?, asset_polling_interval = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 'global'
        """, (
            polling.get('enabled', True) if isinstance(polling, dict) else True,
            polling.get('interval_seconds', 60) if isinstance(polling, dict) else 60,
        ))

        await self._db.commit()

        # Step 5: Mark import complete
        await self._set_migration_meta("one_time_import_done", "true")
        await self._set_migration_meta("yaml_fully_migrated", "true")

        logger.info("YAML import: successfully imported all configurations to DB")
        return True

    except Exception as e:
        logger.error(f"YAML import failed: {e}")
        raise
```

### 2.4 YAML 文件最终定位

| 文件 | 当前用途 | 迁移后用途 |
|------|----------|------------|
| `config/user.yaml` | 运行时读取 exchange/timeframes/asset_polling | **仅用于 import/export 备份恢复** |
| `config/core.yaml` | 运行时读取系统默认参数 | **仅用于 import/export 备份恢复** |

**Import/Export 流程保持不变**:
- **Export**: 从 DB 读取所有配置 → 组装为 YAML 格式 → 下载文件
- **Import**: 上传 YAML 文件 → 解析 → 写入 DB → 触发热重载

---

## 3. Part B: 配置页面整合方案

### 3.1 当前路由结构

```
/config           → ConfigManagement.tsx（旧页面，2 个 Tab：策略参数/系统配置）
/config/strategies → StrategyConfig.tsx（独立策略配置页）
/config/system    → SystemSettings.tsx（独立系统设置页）
/config/profiles  → ConfigProfiles.tsx（Profile 管理，计划废弃）
```

**侧边栏导航** (`Layout.tsx`):
- "策略配置" 分类下有: 策略配置 (`/config/strategies`)、系统设置 (`/config/system`)
- "系统设置 (下拉)" 分类下有: Profile 管理 (`/config/profiles`)、配置快照 (`/snapshots`)、账户 (`/account`)

### 3.2 目标路由结构

```
/config?tab=strategies  → 统一 ConfigManagement（4 个 Ant Design Tabs）
/config?tab=system      → 统一 ConfigManagement
/config?tab=backup      → 统一 ConfigManagement
/config?tab=effective   → 统一 ConfigManagement
```

**旧路由变为 301 重定向**:
```
/config/strategies → /config?tab=strategies
/config/system     → /config?tab=system
/config/profiles   → /config?tab=backup
```

### 3.3 侧边栏导航变更

**变更文件**: `web-front/src/components/Layout.tsx`

**变更后导航结构**:
```
配置管理 (cyan 分类)
  └── /config            → 配置中心

系统设置 (下拉, gray 分类)
  ├── /config?tab=system → 系统设置
  ├── /snapshots         → 配置快照
  └── /account           → 账户
```

> 注: 也可将配置管理下的子项拆分更细，取决于用户体验偏好。

### 3.4 统一配置页面结构

```
┌────────────────────────────────────────────────────────────────┐
│ 配置管理                                    [导出] [导入]       │
├────────────────────────────────────────────────────────────────┤
│ [Tab: 策略管理] [Tab: 系统设置] [Tab: 备份恢复] [Tab: 生效配置] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Tab 1: 策略管理 → <StrategyConfig />（已有，直接复用）          │
│  Tab 2: 系统设置 → <SystemSettings variant="tab" /> + 新增:     │
│                exchange 编辑、timeframes 多选、轮询开关          │
│  Tab 3: 备份恢复 → <BackupTab /> + ConfigProfiles 整合          │
│  Tab 4: 生效配置 → <EffectiveConfigView /> (新组件, 只读)       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 3.5 前端文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `web-front/src/App.tsx` | **修改** | 移除独立路由，添加重定向规则 |
| `web-front/src/components/Layout.tsx` | **修改** | 合并导航项 |
| `web-front/src/pages/ConfigManagement.tsx` | **重写** | 改为 Ant Design Tabs 容器（替代现有旧页面） |
| `web-front/src/pages/config/SystemSettings.tsx` | **修改** | 新增 exchange/API Key/时间周期/轮询 编辑 |
| `web-front/src/pages/config/BackupTab.tsx` | **修改** | 整合 ConfigProfiles 功能 |
| `web-front/src/pages/ConfigProfiles.tsx` | **废弃** | 功能整合到 BackupTab |
| `web-front/src/pages/config/EffectiveConfigView.tsx` | **新建** | 只读展示生效配置总览 |
| `web-front/src/api/config.ts` | **修改** | 新增 exchange/timeframes/effective API 调用 |
| `web-front/src/lib/api.ts` | **修改** | 新增对应的 TS 类型定义 |

### 3.6 App.tsx 路由变更

**变更前** (当前 `web-front/src/App.tsx` 行 42-45):
```tsx
<Route path="config" element={<ConfigManagement />} />
<Route path="config/strategies" element={<StrategyConfig />} />
<Route path="config/system" element={<SystemSettings />} />
<Route path="config/profiles" element={<ConfigProfiles />} />
```

**变更后**:
```tsx
<Route path="config" element={<ConfigManagement />} />

{/* 旧路由重定向 */}
<Route path="config/strategies" element={<Navigate to="/config?tab=strategies" replace />} />
<Route path="config/system" element={<Navigate to="/config?tab=system" replace />} />
<Route path="config/profiles" element={<Navigate to="/config?tab=backup" replace />} />
```

### 3.7 ConfigManagement 重写设计

```tsx
// web-front/src/pages/ConfigManagement.tsx (重写)
import { useState, useEffect } from 'react';
import { Tabs, Alert } from 'antd';
import { useSearchParams } from 'react-router-dom';
import StrategyConfig from './config/StrategyConfig';
import SystemSettings from './config/SystemSettings';
import BackupTab from './config/BackupTab';
import EffectiveConfigView from './config/EffectiveConfigView';

export default function ConfigManagement() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'strategies';

  const items = [
    {
      key: 'strategies',
      label: '策略管理',
      children: <StrategyConfig />,
    },
    {
      key: 'system',
      label: '系统设置',
      children: <SystemSettings variant="tab" />,
    },
    {
      key: 'backup',
      label: '备份恢复',
      children: <BackupTab />,
    },
    {
      key: 'effective',
      label: '生效配置总览',
      children: <EffectiveConfigView />,
    },
  ];

  const handleChange = (key: string) => {
    setSearchParams({ tab: key });
  };

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-gray-900 mb-1">
        配置管理
      </h1>
      <p className="text-sm text-gray-500 mb-6">
        管理策略参数、系统配置、导入导出、版本快照
      </p>
      <Tabs
        activeKey={activeTab}
        onChange={handleChange}
        items={items}
        size="large"
      />
    </div>
  );
}
```

---

## 4. Part C: 生效配置总览 API + 前端

### 4.1 新 API: `GET /api/v1/config/effective`

**Endpoint**:
```
GET /api/v1/config/effective
```

**响应** (200 OK):
```typescript
interface EffectiveConfigResponse {
  exchange: {
    name: string;             // "binance"
    api_key: string;          // "sk***abc123" (masked)
    api_secret: string;       // "****" (masked)
    testnet: boolean;
  };
  system: {
    core_symbols: string[];
    ema_period: number;
    mtf_ema_period: number;
    mtf_mapping: Record<string, string>;
    signal_cooldown_seconds: number;
    timeframes: string[];
    atr_filter_enabled: boolean;
    atr_period: number;
    atr_min_ratio: string;
  };
  risk: {
    max_loss_percent: string;
    max_leverage: number;
    max_total_exposure: string;
    daily_max_trades?: number;
    daily_max_loss?: string;
    cooldown_minutes: number;
  };
  notification: {
    channels: Array<{
      id: string;
      type: string;
      webhook_url: string;    // masked URL
      is_active: boolean;
    }>;
  };
  strategies: Array<{
    id: string;
    name: string;
    is_active: boolean;
    trigger_type: string;
    filter_count: number;
    symbols: string[];
    timeframes: string[];
  }>;
  symbols: Array<{
    symbol: string;
    is_core: boolean;
    is_active: boolean;
  }>;
  asset_polling: {
    enabled: boolean;
    interval_seconds: number;
  };
  migration_status: {
    yaml_fully_migrated: boolean;
    one_time_import_done: boolean;
    import_version: string;
  };
  config_version: number;     // ConfigManager 的 _config_version
  created_at: string;         // ISO 8601
}
```

**脱敏规则**:
- `api_key`: 保留前 4 后 4 字符，中间用 `***` 替代（使用现有 `mask_secret()` 函数）
- `api_secret`: 完全隐藏为 `****`
- `webhook_url`: 保留协议和域名前缀，路径部分用 `****` 替代

### 4.2 后端实现位置

**文件**: `src/interfaces/api_v1_config.py`

**新增端点**:
```python
@router.get("/effective", response_model=EffectiveConfigResponse)
async def get_effective_config(
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """Get the complete merged runtime configuration."""
    # 从 ConfigManager 缓存构建完整配置
    # 脱敏敏感字段
    # 返回 EffectiveConfigResponse
```

**新增 Pydantic 响应模型**:
```python
class ExchangeConfigMasked(BaseModel):
    name: str
    api_key: str        # masked
    api_secret: str     # masked
    testnet: bool

class MigrationStatus(BaseModel):
    yaml_fully_migrated: bool
    one_time_import_done: bool
    import_version: str

class EffectiveConfigResponse(BaseModel):
    exchange: ExchangeConfigMasked
    system: SystemConfigSummary
    risk: RiskConfigSummary
    notification: NotificationSummary
    strategies: List[StrategySummary]
    symbols: List[SymbolSummary]
    asset_polling: AssetPollingSummary
    migration_status: MigrationStatus
    config_version: int
    created_at: str
```

### 4.3 前端 EffectiveConfigView 组件设计

```tsx
// web-front/src/pages/config/EffectiveConfigView.tsx
import { useState } from 'react';
import { Collapse, Descriptions, Tag, Button, Alert, Spin } from 'antd';
import { EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons';
import { useSWRConfig } from 'swr';

export default function EffectiveConfigView() {
  const { data, error, isLoading } = useSWR('/api/v1/config/effective');
  const [revealedFields, setRevealedFields] = useState<Set<string>>(new Set());

  if (isLoading) return <Spin />;
  if (error) return <Alert message="加载失败" type="error" />;

  const sections = [
    {
      key: 'exchange',
      title: '交易所连接',
      items: [
        { key: 'name', label: '交易所', value: data.exchange.name },
        { key: 'api_key', label: 'API Key', value: data.exchange.api_key, masked: true },
        { key: 'testnet', label: '测试网', value: data.exchange.testnet ? '是' : '否' },
      ],
    },
    {
      key: 'system',
      title: '系统设置',
      items: [
        { key: 'timeframes', label: '监控周期', value: data.system.timeframes.join(', ') },
        { key: 'core_symbols', label: '核心币种', value: data.system.core_symbols.join(', ') },
        { key: 'mtf_mapping', label: 'MTF 映射', value: JSON.stringify(data.system.mtf_mapping) },
        // ...
      ],
    },
    // risk, notification, strategies, symbols, asset_polling...
  ];

  return (
    <div className="space-y-4">
      {/* 迁移状态指示器 */}
      {data.migration_status.yaml_fully_migrated ? (
        <Alert message="YAML 迁移完成" description="所有配置已从数据库读取" type="success" showIcon />
      ) : (
        <Alert message="YAML 迁移未完成" description="首次启动后将自动从 YAML 导入配置" type="warning" showIcon />
      )}

      {/* 分组折叠面板 */}
      <Collapse accordion>
        {sections.map(section => (
          <Collapse.Panel header={section.title} key={section.key}>
            <Descriptions column={2} bordered size="small">
              {section.items.map(item => (
                <Descriptions.Item key={item.key} label={item.label}>
                  {item.masked && !revealedFields.has(item.key) ? (
                    <span>
                      {item.value}
                      <Button
                        type="link"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => revealField(item.key)}
                      />
                    </span>
                  ) : (
                    item.value
                  )}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Collapse.Panel>
        ))}
      </Collapse>
    </div>
  );
}
```

---

## 5. 执行顺序与依赖图

### 5.1 依赖图

```
                    ┌─────────────────────┐
                    │  Part A (后端优先)   │
                    │  YAML → DB 迁移      │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
    │ A1: 新 DB表  │  │ A2: Repository│  │ A3: ConfigMgr│
    │ DDL + 迁移   │──▶│ 新增 CRUD    │──▶│ 移除 YAML    │
    └─────────────┘  └─────────────┘  └─────────────┘
                                              │
                                              ▼
                                      ┌──────────────┐
                                      │ A4: 新 API    │
                                      │ exchange/    │
                                      │ timeframes/  │
                                      │ effective    │
                                      └──────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          │                   │                   │
                          ▼                   ▼                   ▼
                   ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
                   │ Part B: 页面 │    │ Part C: 生效  │    │ 后端测试     │
                   │ 整合 (前端)   │    │ 配置前端      │    │ (独立)       │
                   └─────────────┘    └─────────────┘    └──────────────┘
                          │                   │
                          └─────────┬─────────┘
                                    ▼
                          ┌─────────────────┐
                          │ 集成测试 + E2E   │
                          │ (最后)           │
                          └─────────────────┘
```

### 5.2 并行执行策略

| 阶段 | 任务 | 并行度 | 前置依赖 |
|------|------|--------|----------|
| **Phase 1** | A1: 新 DB 表 DDL + migration | 串行 (先行) | 无 |
| **Phase 2** | A2: Repository 新增 CRUD | 串行 | A1 完成 |
| **Phase 3** | A3: ConfigManager 移除 YAML | 串行 | A2 完成 |
| **Phase 4** | A4: 新 API 端点 | **可并行** B, C | A3 完成 |
| **Phase 5** | B: 前端页面整合 | **可并行** A4, C | 无 (可用 mock) |
| **Phase 5** | C: 生效配置前端 | **可并行** A4, B | 无 (可用 mock) |
| **Phase 6** | 集成测试 + E2E | 串行 | A4, B, C 全部完成 |

---

## 6. 风险评估与回滚方案

### 6.1 风险评估

| 风险 ID | 风险描述 | 概率 | 影响 | 缓解措施 |
|---------|----------|------|------|----------|
| **R1** | 迁移脚本执行失败，DB 中无 exchange 配置 | 低 | 高 | 迁移前校验 user.yaml 完整性；失败时保留 YAML fallback |
| **R2** | SQLite `ALTER TABLE` 在已有行上产生 NULL 值 | 中 | 中 | 迁移脚本显式 UPDATE 已有行 |
| **R3** | `get_user_config_sync()` 无异步 DB 调用 | 低 | 中 | 初始化后将配置缓存为内存对象，sync 方法读缓存 |
| **R4** | Ant Design Tabs 与现有 Tailwind 样式冲突 | 低 | 低 | Ant Design 6.x 支持 CSS-in-JS，隔离良好 |
| **R5** | 热重载时 ExchangeGateway 需要重新初始化连接 | 中 | 高 | API 更新 exchange config 后触发热重载流程 |
| **R6** | 旧路由书签/收藏夹失效 | 低 | 低 | 301 重定向保留兼容性 |
| **R7** | 用户未提供 user.yaml（全新安装） | 中 | 中 | 迁移脚本检测到无 YAML 时自动跳过，使用默认值 |

### 6.2 回滚方案

**触发条件**:
- 迁移后系统无法正常启动
- ExchangeGateway 无法连接交易所

**回滚步骤**:
1. 停止应用
2. 将 `_use_yaml_fallback` 设回 `true`
3. 删除 `migration_metadata` 表中的 `one_time_import_done` 标记
4. 重启应用（将回退到 YAML 读取模式）

**数据恢复**:
- 所有配置变更都有 `config_history` 表记录
- 可随时从 `config_snapshots` 回滚到迁移前快照

---

## 7. 工作量估算与任务分解

### 7.1 总体估算

| 阶段 | 任务 | 预估工时 | 并行度 |
|------|------|----------|--------|
| Part A-1 | 新 DB 表 DDL + migration_metadata | 1h | 先行 |
| Part A-2 | ConfigRepository 新增 6 个 CRUD 方法 | 2.5h | 串行 A-1 |
| Part A-3 | ConfigManager 移除 YAML 读取 + _perform_yaml_import | 3h | 串行 A-2 |
| Part A-4 | 新 API 端点 (exchange/timeframes/effective) | 2.5h | 串行 A-3 |
| Part A-5 | 空配置验证适配新表 | 1h | 并行 A-3 |
| Part B-1 | ConfigManagement 重写为 Ant Design Tabs 容器 | 2h | 可并行 A |
| Part B-2 | SystemSettings 适配 variant="tab" + 新增字段编辑 | 3h | 可并行 A |
| Part B-3 | BackupTab 整合 ConfigProfiles | 1.5h | 可并行 A |
| Part B-4 | App.tsx 路由 + Layout.tsx 导航变更 | 1h | 依赖 B-1 |
| Part B-5 | EffectiveConfigView 新组件 | 2.5h | 可并行 A |
| Part C-1 | API 类型定义 + config.ts 新增调用 | 1h | 依赖 A-4 |
| Test | 单元测试 + 集成测试 + E2E | 4h | 最后 |
| **合计** | | **~25h** | **A 和 B/C 可并行 → ~17h 关键路径** |

### 7.2 详细任务分解

#### Task A-1: 新 DB 表 DDL (1h)
- [ ] 更新 `config_tables.sql` 添加 `exchange_configs` 表
- [ ] 更新 `config_tables.sql` 添加 `migration_metadata` 表
- [ ] 更新 `config_tables.sql` 扩展 `system_configs` 列
- [ ] 更新 `ConfigRepository._create_tables()` 和 `ConfigManager._create_tables()`
- [ ] 更新 `_initialize_default_configs()` 初始化 exchange 默认值

#### Task A-2: ConfigRepository 新增 CRUD (2.5h)
- [ ] `get_exchange_config()` / `update_exchange_config()`
- [ ] `get_timeframes()` / `update_timeframes()`
- [ ] `get_asset_polling_config()` / `update_asset_polling_config()`
- [ ] 修改 `get_user_config_dict()` 移除 YAML 依赖
- [ ] 修改 `_build_notification_config()` 移除 YAML fallback
- [ ] 修改 `update_user_config_item()` 写 DB 而非 YAML
- [ ] 单元测试

#### Task A-3: ConfigManager 重构 (3h)
- [ ] 新增 `_perform_yaml_import()` 一次性导入逻辑
- [ ] 修改 `initialize_from_db()` 调用 yaml_import
- [ ] 修改 `_build_user_config_dict()` 纯 DB 读取
- [ ] 修改 `_build_notification_config()` 移除 YAML fallback
- [ ] 修改 `get_user_config_sync()` 从缓存返回
- [ ] 删除/废弃 `_load_user_config_from_yaml()` 运行时用途
- [ ] 确保 `_user_config_cache` 存在并正确初始化
- [ ] 单元测试

#### Task A-4: 新 API 端点 (2.5h)
- [ ] `GET /api/v1/config/exchange` (api_key masked)
- [ ] `PUT /api/v1/config/exchange` (热重载触发)
- [ ] `GET /api/v1/config/timeframes`
- [ ] `PUT /api/v1/config/timeframes`
- [ ] `GET /api/v1/config/effective` (完整合并配置)
- [ ] 响应模型 Pydantic 定义
- [ ] 脱敏函数实现
- [ ] 集成测试

#### Task A-5: 空配置验证适配 (1h)
- [ ] 修改 `_is_empty_config()` 检查 `exchange_configs` 表
- [ ] 修改 `_apply_hardcoded_defaults()` 初始化 exchange 默认值
- [ ] 单元测试

#### Task B-1: ConfigManagement 重写 (2h)
- [ ] 改为 Ant Design Tabs 容器
- [ ] Tab 1: 嵌入 `<StrategyConfig />`
- [ ] Tab 2: 嵌入 `<SystemSettings variant="tab" />`
- [ ] Tab 3: 嵌入 `<BackupTab />` + 整合 Profile 功能
- [ ] Tab 4: 嵌入 `<EffectiveConfigView />`
- [ ] URL query string 同步 (activeTab ↔ ?tab=)

#### Task B-2: SystemSettings 适配 (3h)
- [ ] 新增交易所连接编辑 (name, testnet)
- [ ] 新增 API Key/Secret 编辑 (masked, show/hide)
- [ ] 新增时间周期多选
- [ ] 新增资产轮询开关 + 间隔
- [ ] 调用新的 `/api/v1/config/exchange` API
- [ ] 热重载触发逻辑

#### Task B-3: BackupTab 整合 (1.5h)
- [ ] 整合 ConfigProfiles 的 Profile 管理功能
- [ ] 保留导出/导入功能
- [ ] 保留快照列表和回滚功能

#### Task B-4: 路由与导航变更 (1h)
- [ ] `App.tsx`: 移除独立路由，添加重定向
- [ ] `Layout.tsx`: 合并导航项

#### Task B-5: EffectiveConfigView (2.5h)
- [ ] 只读分组展示 (Collapse + Descriptions)
- [ ] 敏感字段脱敏 + show/hide
- [ ] 迁移状态指示器
- [ ] 单元测试

#### Task C-1: API 类型定义 (1h)
- [ ] `lib/api.ts`: 新增 EffectiveConfigResponse 等类型
- [ ] `api/config.ts`: 新增 fetchEffectiveConfig 等函数

#### Test: 全面测试 (4h)
- [ ] ConfigRepository 新增方法单元测试
- [ ] ConfigManager YAML 移除回归测试
- [ ] API 端点集成测试
- [ ] 前端组件单元测试
- [ ] E2E 测试: 完整配置编辑流程
- [ ] 迁移脚本 E2E 测试 (有/无 YAML 两种场景)

---

## 附录 A: 关键文件索引

| 文件 | 用途 |
|------|------|
| `src/application/config_manager.py` | ConfigManager 主类，需重构 |
| `src/application/config/config_repository.py` | Repository 层，需新增方法 |
| `src/infrastructure/db/config_tables.sql` | DB 表结构定义，需扩展 |
| `src/interfaces/api_v1_config.py` | API 路由，需新增端点 |
| `web-front/src/App.tsx` | 路由定义，需变更 |
| `web-front/src/components/Layout.tsx` | 侧边栏导航，需变更 |
| `web-front/src/pages/ConfigManagement.tsx` | 配置主页面，需重写 |
| `web-front/src/pages/config/SystemSettings.tsx` | 系统设置页，需适配 |
| `web-front/src/pages/config/BackupTab.tsx` | 备份恢复页，需整合 |
