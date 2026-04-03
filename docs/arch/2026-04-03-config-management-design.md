# 配置管理系统重构 - 架构设计文档 (最终版)

**文档编号**: ARCH-2026-001  
**创建日期**: 2026-04-03  
**状态**: ✅ 最终版（已修复）  
**作者**: Architect
**关联影响**: ✅ 已分析
**必填校验**: ✅ 已设计
**快照功能**: ✅ 已规划
**自动快照**: ✅ 已设计
**配置对比**: ✅ 已设计
**API 版本化**: ✅ 已设计
**错误日志**: ✅ 已设计
**单例约束**: ✅ 触发器实现
**热重载安全**: ✅ 已设计
**API 密钥管理**: ✅ 已设计

---

## 0. 设计范围与约束

### 0.1 系统定位

| 约束项 | 说明 |
|--------|------|
| **用户规模** | 单用户系统，不考虑并发 |
| **性能要求** | 常规性能即可，热重载<1 秒 |
| **部署环境** | 本地/Docker 单实例部署 |

### 0.2 核心功能清单

| 功能 | 说明 | 状态 |
|------|------|------|
| 配置数据库化 | DB 为唯一配置源 | ✅ |
| 热重载支持 | 策略/风控/币池/通知支持热重载 | ✅ |
| 配置导入/导出 | YAML 格式备份恢复 | ✅ |
| 配置快照 | 创建/列表/预览/恢复/删除 | ✅ |
| **自动快照** | 重大操作前自动创建 | ✅ |
| 配置历史 | 触发器自动记录 | ✅ |
| **配置对比** | 任意两个版本间对比 | ✅ |
| **API 版本化** | 所有端点 `/api/v1/*` 前缀 | ✅ |
| **详细错误日志** | 记录详细堆栈和状态 | ✅ |

### 0.3 不需要考虑的功能

| 功能 | 原因 |
|------|------|
| 性能优化 | 单用户系统，无并发压力 |
| 并发控制 | 单用户，无并发修改风险 |
| 历史自动清理 | 单用户，数据量可控 |
| 操作日志导出 | 单用户，无需审计 |
| 快速重置 | 非必需体验优化 |
| HTTPS 强制 | 本地部署，内网通信 |
| JSON 导出 | YAML 已满足需求 |
| 权限控制 | 单用户系统 |

---

### 0.4 API 密钥管理方案

| 项目 | 说明 |
|------|------|
| **存储位置** | 系统环境变量 (`EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`) |
| **不支持 UI 修改** | 安全红线：API 密钥不可通过前端修改 |
| **多交易所支持** | 当前仅支持单一交易所，环境变量唯一定义 |
| **启动验证** | 系统启动时验证 API 密钥权限（只读检查） |
| **读取方式** | `os.getenv('EXCHANGE_API_KEY')`，不入库、不持久化 |

**环境变量配置示例** (`.env` 文件或系统环境变量):
```bash
# 交易所 API 密钥（只读权限）
EXCHANGE_API_KEY="your_api_key_here"
EXCHANGE_API_SECRET="your_api_secret_here"

# 可选：测试网开关
EXCHANGE_TESTNET=true
```

**启动验证逻辑**:
```python
# src/main.py
api_key = os.getenv('EXCHANGE_API_KEY')
api_secret = os.getenv('EXCHANGE_API_SECRET')

if not api_key or not api_secret:
    raise ConfigError("F-003: API 密钥未配置")

# 验证权限（只读检查）
await config_manager.check_api_key_permissions(exchange)
```

---

## 0. 关联影响分析

### 0.1 影响范围矩阵

| 模块 | 影响程度 | 说明 |
|------|----------|------|
| **ConfigManager** | 🔴 完全重构 | 从 YAML 加载改为 DB 加载，所有方法需重写 |
| **SignalPipeline** | 🟡 中等 | 冷却逻辑移除，改为高质量覆盖 |
| **StrategyEngine** | 🟢 低 | 仅需适配新的配置传入方式 |
| **ExchangeGateway** | 🟢 低 | API Key 改为纯环境变量读取 |
| **API 层** | 🟡 中等 | 新增配置管理端点，更新现有端点 |
| **前端策略工作台** | 🟡 中等 | 保存逻辑不变，但配置管理页面新建 |
| **回测沙箱** | 🟢 低 | 配置读取方式变化，接口不变 |
| **通知推送** | 🟢 低 | 配置来源变化，逻辑不变 |

### 0.2 关键依赖分析

```
启动流程依赖链:
main.py → ConfigManager.load_all_from_db() → ConfigRepository
   ↓
   ├─→ active_strategy → StrategyEngine
   ├─→ risk_config → RiskCalculator
   ├─→ symbols → ExchangeGateway.subscribe_ohlcv()
   ├─→ notifications → Notifier
   └─→ system_config (只读，启动时使用)

⚠️ 风险点：ConfigManager 初始化失败会导致整个系统启动失败
✅ 缓解：启动时检测 DB 状态，空库自动初始化默认配置
```

### 0.3 配置校验层级

| 层级 | 校验类型 | 说明 |
|------|----------|------|
| **数据库层** | CHECK 约束、NOT NULL、UNIQUE | 基础数据完整性 |
| **应用层** | Pydantic 模型校验 | 复杂业务规则、跨字段校验 |
| **API 层** | 请求体验证 | 格式校验、必填字段检查 |

---

## 1. 概述

### 1.1 背景

当前系统配置采用 YAML 文件（`core.yaml` + `user.yaml`）静态加载方式，存在以下痛点：

- **配置修改需重启**：任何参数调整都需要重启进程才能生效
- **无法追溯历史**：配置变更无记录，无法回滚到历史版本
- **配置分散管理**：策略参数、风控参数、系统参数混在一起
- **不支持多策略**：无法灵活管理多个策略配置
- **API 密钥硬编码**：敏感信息写在配置文件中，存在安全风险

### 1.2 目标

| 目标 | 说明 |
|------|------|
| **配置数据库化** | 所有配置存入 SQLite 数据库，支持动态读取 |
| **热重载支持** | 关键配置修改后，手动点击"应用"即可生效 |
| **版本控制** | 配置变更自动记录历史，支持快照回滚 |
| **备份恢复** | 支持 YAML 格式导入/导出，便于备份 |
| **安全增强** | API 密钥移至环境变量，不入库 |
| **信号质量优化** | 移除固定冷却期，改用高质量覆盖低质量逻辑 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **模块化隔离** | 配置模块独立，不影响其他功能（信号处理、通知推送、交易所网关） |
| **热加载支持** | 能热加载的配置必须支持热加载，不能热加载的配置明确标注 |
| **单一数据源** | DB 为唯一配置来源，YAML 文件仅作为导入/导出格式 |
| **向后兼容** | 不依赖历史数据，采用新表重新设计 |

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端配置管理页面                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │ 系统信息 │ │ 风控配置 │ │ 币池管理 │ │ 通知配置 │ │ 策略   ││
│  │ (只读)   │ │ (可编辑) │ │ (可编辑) │ │ (可编辑) │ │ 配置   ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘│
│                             │                                     │
│                    ┌────────▼────────┐                           │
│                    │  备份/恢复模块  │                           │
│                    │  (导入/导出)    │                           │
│                    └─────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
    ┌─────────────────┐ ┌───────────┐ ┌──────────────┐
    │  Config API     │ │ 导入/导出  │ │ 配置历史 API │
    │  /api/config/*  │ │ API       │ │ /api/snapshots│
    └────────┬────────┘ └───────────┘ └──────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ConfigManager (重构后)                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  load_all_from_db()  - 从 DB 加载所有配置到内存               ││
│  │  apply_config()      - 从 DB 重新加载配置 (热重载)             ││
│  │  export_to_yaml()    - 导出配置为 YAML 文件                   ││
│  │  import_from_yaml()  - 从 YAML 文件导入配置                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite 数据库                              │
│  ┌────────────────┐ ┌──────────────┐ ┌────────────────────────┐│
│  │strategy_configs│ │risk_configs  │ │system_configs          ││
│  ├────────────────┤ ├──────────────┤ ├────────────────────────┤│
│  │symbol_configs  │ │notification_ │ │config_history          ││
│  │                │ │configs       │ │config_snapshots        ││
│  └────────────────┘ └──────────────┘ └────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据库设计

### 3.1 表结构总览

| 表名 | 用途 | 单例 | 必填字段校验 |
|------|------|------|-------------|
| `strategy_configs` | 策略配置 | 否 | triggers, filters, apply_to |
| `risk_configs` | 风控配置 | 是 (id=1) | max_loss_percent, max_total_exposure |
| `system_configs` | 系统配置 | 是 (id=1) | history_bars, queue_batch_size |
| `symbol_configs` | 币池配置 | 否 | symbol (格式校验) |
| `notification_configs` | 通知配置 | 否 | webhook_url (URL 校验) |
| `config_history` | 配置历史 | 否 | 触发器自动记录 |
| `config_snapshots` | 配置快照 | 否 | config_json |

### 3.2 完整表结构（含必填校验）

#### 3.2.1 策略配置表 (`strategy_configs`)

```sql
CREATE TABLE strategy_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,           -- ✅ 必填，唯一
    description   TEXT,                           -- ❌ 可选
    triggers      TEXT NOT NULL,                  -- ✅ 必填，JSON 校验
    filters       TEXT NOT NULL DEFAULT '[]',     -- ✅ 必填，JSON 校验
    logic_tree    TEXT,                           -- ❌ 可选，JSON 校验
    apply_to      TEXT NOT NULL,                  -- ✅ 必填，JSON 数组
    is_active     INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_strategy_active ON strategy_configs(is_active);

-- ✅ 确保同一时间只有一个激活策略（使用触发器，SQLite 兼容）
CREATE TRIGGER check_single_active_strategy_before_insert
BEFORE INSERT ON strategy_configs
WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1) > 0
BEGIN
    SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
END;

CREATE TRIGGER check_single_active_strategy_before_update
BEFORE UPDATE ON strategy_configs
WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1 AND id != NEW.id) > 0
BEGIN
    SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
END;
```

**字段约束**:
| 字段 | 必填 | 校验规则 |
|------|------|---------|
| `name` | ✅ | UNIQUE, 1-100 字符 |
| `triggers` | ✅ | JSON 数组，至少 1 个触发器 |
| `filters` | ✅ | JSON 数组（可为空数组） |
| `apply_to` | ✅ | JSON 数组，格式 `SYMBOL:TIMEFRAME` |

**JSON 校验规则**:
```json
// triggers 示例
[
  {
    "type": "pinbar",
    "enabled": true,
    "params": {
      "min_wick_ratio": 0.5,
      "max_body_ratio": 0.35,
      "body_position_tolerance": 0.3
    }
  }
]

// apply_to 示例
["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m"]
```

#### 3.2.2 风控配置表 (`risk_configs`)

```sql
CREATE TABLE risk_configs (
    id                   INTEGER PRIMARY KEY,
    max_loss_percent     REAL NOT NULL DEFAULT 1.0 CHECK (max_loss_percent BETWEEN 0.001 AND 0.05),  -- ✅ 必填，0.1%~5%
    max_total_exposure   REAL NOT NULL DEFAULT 0.8 CHECK (max_total_exposure BETWEEN 0.5 AND 1.0),   -- ✅ 必填，50%~100%
    max_leverage         INTEGER NOT NULL DEFAULT 10 CHECK (max_leverage BETWEEN 1 AND 125),         -- ✅ 必填，1~125 倍
    description          TEXT,                                   -- ❌ 可选
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ✅ 单例约束：使用触发器强制只有一条记录 (id=1)
CREATE TRIGGER risk_configs_single_row_insert
BEFORE INSERT ON risk_configs
WHEN (SELECT COUNT(*) FROM risk_configs) >= 1
BEGIN
    SELECT RAISE(ABORT, 'risk_configs 只能有一条记录');
END;

CREATE TRIGGER risk_configs_enforce_id_insert
BEFORE INSERT ON risk_configs
WHEN NEW.id != 1
BEGIN
    SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
END;

CREATE TRIGGER risk_configs_enforce_id_update
BEFORE UPDATE ON risk_configs
WHEN NEW.id != 1
BEGIN
    SELECT RAISE(ABORT, 'risk_configs 的 id 必须为 1');
END;
```

**字段约束**:
| 字段 | 必填 | 约束范围 | 说明 |
|------|------|---------|------|
| `max_loss_percent` | ✅ | 0.001 ~ 0.05 | 单笔最大损失 (0.1%~5%) |
| `max_total_exposure` | ✅ | 0.5 ~ 1.0 | 最大总敞口 (50%~100%) |
| `max_leverage` | ✅ | 1 ~ 125 | 最大杠杆倍数 |

#### 3.2.3 系统配置表 (`system_configs`)

```sql
CREATE TABLE system_configs (
    id                   INTEGER PRIMARY KEY,
    history_bars         INTEGER NOT NULL DEFAULT 100 CHECK (history_bars BETWEEN 50 AND 1000),    -- ✅ 必填，50~1000
    queue_batch_size     INTEGER NOT NULL DEFAULT 10 CHECK (queue_batch_size BETWEEN 1 AND 100),   -- ✅ 必填，1~100
    queue_flush_interval REAL NOT NULL DEFAULT 5.0 CHECK (queue_flush_interval BETWEEN 1.0 AND 60.0), -- ✅ 必填，1~60 秒
    description          TEXT,                                   -- ❌ 可选
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ✅ 单例约束：使用触发器强制只有一条记录 (id=1)
CREATE TRIGGER system_configs_single_row_insert
BEFORE INSERT ON system_configs
WHEN (SELECT COUNT(*) FROM system_configs) >= 1
BEGIN
    SELECT RAISE(ABORT, 'system_configs 只能有一条记录');
END;

CREATE TRIGGER system_configs_enforce_id_insert
BEFORE INSERT ON system_configs
WHEN NEW.id != 1
BEGIN
    SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
END;

CREATE TRIGGER system_configs_enforce_id_update
BEFORE UPDATE ON system_configs
WHEN NEW.id != 1
BEGIN
    SELECT RAISE(ABORT, 'system_configs 的 id 必须为 1');
END;
```

**字段约束**:
| 字段 | 必填 | 约束范围 | 说明 |
|------|------|---------|------|
| `history_bars` | ✅ | 50 ~ 1000 | K 线预热数量 |
| `queue_batch_size` | ✅ | 1 ~ 100 | 队列批大小 |
| `queue_flush_interval` | ✅ | 1.0 ~ 60.0 | 队列刷新间隔 (秒) |

**注意**: 此表配置**不支持热重载**，修改后需重启系统。

#### 3.2.4 币池配置表 (`symbol_configs`)

```sql
CREATE TABLE symbol_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL UNIQUE CHECK (symbol MATCH '^[A-Z]+/[A-Z]+(:[A-Z]+)?$'),  -- ✅ 必填，格式校验
    is_core       INTEGER NOT NULL DEFAULT 1 CHECK (is_core IN (0, 1)),  -- ✅ 必填
    is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),  -- ✅ 必填
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_symbol_enabled ON symbol_configs(is_enabled);
```

**字段约束**:
| 字段 | 必填 | 校验规则 | 示例 |
|------|------|---------|------|
| `symbol` | ✅ | `^[A-Z]+/[A-Z]+(:[A-Z]+)?$` | `BTC/USDT:USDT` |
| `is_core` | ✅ | 0 或 1 | 1=核心币 |
| `is_enabled` | ✅ | 0 或 1 | 1=启用 |

#### 3.2.5 通知配置表 (`notification_configs`)

```sql
CREATE TABLE notification_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel       TEXT NOT NULL CHECK (channel IN ('feishu', 'wecom', 'telegram')),  -- ✅ 必填
    webhook_url   TEXT NOT NULL CHECK (webhook_url MATCH '^https?://.+'),            -- ✅ 必填，URL 校验
    is_enabled    INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),           -- ✅ 必填
    description   TEXT,                                                               -- ❌ 可选
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**字段约束**:
| 字段 | 必填 | 校验规则 | 示例 |
|------|------|---------|------|
| `channel` | ✅ | `'feishu'`, `'wecom'`, `'telegram'` | `feishu` |
| `webhook_url` | ✅ | `^https?://.+` | `https://open.feishu.cn/...` |
| `is_enabled` | ✅ | 0 或 1 | 1=启用 |

#### 3.2.6 配置历史表 (`config_history`)

```sql
CREATE TABLE config_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type     TEXT NOT NULL CHECK (config_type IN ('strategy', 'risk', 'system', 'symbol', 'notification')),  -- ✅ 必填
    config_id       INTEGER NOT NULL,                                                              -- ✅ 必填
    action          TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),                -- ✅ 必填
    old_value       TEXT,                                                                          -- ❌ 可选，JSON
    new_value       TEXT,                                                                          -- ❌ 可选，JSON
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),                                   -- ✅ 自动
    created_by      TEXT DEFAULT 'user'                                                            -- ✅ 自动
);

CREATE INDEX idx_history_type ON config_history(config_type, config_id);
CREATE INDEX idx_history_time ON config_history(created_at);
```

**自动记录触发器**:

```sql
-- ========== 策略配置历史触发器（INSERT/UPDATE/DELETE） ==========

-- 策略创建时自动记录历史
CREATE TRIGGER strategy_configs_audit_after_insert
AFTER INSERT ON strategy_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'strategy',
        NEW.id,
        'create',
        NULL,
        json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
        datetime('now'),
        'system'
    );
END;

-- 策略更新时自动记录历史
CREATE TRIGGER strategy_configs_audit_after_update
AFTER UPDATE ON strategy_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'strategy',
        NEW.id,
        'update',
        json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
        json_object('name', NEW.name, 'triggers', NEW.triggers, 'filters', NEW.filters, 'apply_to', NEW.apply_to, 'is_active', NEW.is_active),
        datetime('now'),
        'system'
    );
END;

-- 策略删除时自动记录历史
CREATE TRIGGER strategy_configs_audit_after_delete
AFTER DELETE ON strategy_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'strategy',
        OLD.id,
        'delete',
        json_object('name', OLD.name, 'triggers', OLD.triggers, 'filters', OLD.filters, 'apply_to', OLD.apply_to, 'is_active', OLD.is_active),
        NULL,
        datetime('now'),
        'system'
    );
END;

-- ========== 风控配置历史触发器（INSERT/UPDATE/DELETE） ==========

-- 风控创建时自动记录历史
CREATE TRIGGER risk_configs_audit_after_insert
AFTER INSERT ON risk_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'risk',
        NEW.id,
        'create',
        NULL,
        json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
        datetime('now'),
        'system'
    );
END;

-- 风控更新时自动记录历史
CREATE TRIGGER risk_configs_audit_after_update
AFTER UPDATE ON risk_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'risk',
        NEW.id,
        'update',
        json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
        json_object('max_loss_percent', NEW.max_loss_percent, 'max_total_exposure', NEW.max_total_exposure, 'max_leverage', NEW.max_leverage),
        datetime('now'),
        'system'
    );
END;

-- 风控删除时自动记录历史
CREATE TRIGGER risk_configs_audit_after_delete
AFTER DELETE ON risk_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'risk',
        OLD.id,
        'delete',
        json_object('max_loss_percent', OLD.max_loss_percent, 'max_total_exposure', OLD.max_total_exposure, 'max_leverage', OLD.max_leverage),
        NULL,
        datetime('now'),
        'system'
    );
END;

-- ========== 系统配置历史触发器（INSERT/UPDATE） ==========

-- 系统配置创建时自动记录历史
CREATE TRIGGER system_configs_audit_after_insert
AFTER INSERT ON system_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'system',
        NEW.id,
        'create',
        NULL,
        json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
        datetime('now'),
        'system'
    );
END;

-- 系统配置更新时自动记录历史
CREATE TRIGGER system_configs_audit_after_update
AFTER UPDATE ON system_configs
FOR EACH ROW
BEGIN
    INSERT INTO config_history (config_type, config_id, action, old_value, new_value, created_at, created_by)
    VALUES (
        'system',
        NEW.id,
        'update',
        json_object('history_bars', OLD.history_bars, 'queue_batch_size', OLD.queue_batch_size, 'queue_flush_interval', OLD.queue_flush_interval),
        json_object('history_bars', NEW.history_bars, 'queue_batch_size', NEW.queue_batch_size, 'queue_flush_interval', NEW.queue_flush_interval),
        datetime('now'),
        'system'
    );
END;
```

#### 3.2.7 配置快照表 (`config_snapshots`)

```sql
CREATE TABLE config_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                     -- ✅ 必填
    description     TEXT,                              -- ❌ 可选
    config_json     TEXT NOT NULL,                     -- ✅ 必填，完整配置 JSON
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),  -- ✅ 自动
    created_by      TEXT DEFAULT 'user'                -- ✅ 自动
);

CREATE INDEX idx_snapshot_name ON config_snapshots(name);
```

**字段约束**:
| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 快照名称（如："2026-04-03 优化 ATR 参数"） |
| `description` | ❌ | 快照描述 |
| `config_json` | ✅ | 完整配置 JSON（包含所有配置类别） |

**快照 JSON 格式**:
```json
{
  "exported_at": "2026-04-03T10:00:00Z",
  "version": "1.0",
  "strategy": { "id": 1, "name": "Pinbar+EMA60", ... },
  "risk": { "max_loss_percent": 1.0, "max_total_exposure": 0.8 },
  "system": { "history_bars": 100, "queue_batch_size": 10 },
  "symbols": [{ "symbol": "BTC/USDT:USDT", "is_core": true }],
  "notifications": [{ "channel": "feishu", "webhook_url": "..." }]
}
```

---

## 4. 配置快照功能设计

### 4.1 快照功能概览

| 功能 | API 端点 | 前端 UI | 状态 |
|------|----------|--------|------|
| 创建快照 | `POST /api/snapshots` | [+ 新建快照] 按钮 | ✅ |
| 快照列表 | `GET /api/snapshots` | 列表展示 | ✅ |
| 快照详情 | `GET /api/snapshots/{id}` | 点击展开 | ✅ |
| 快照预览 | `POST /api/snapshots/{id}/preview` | 预览对话框 | ✅ |
| 一键恢复 | `POST /api/snapshots/{id}/rollback` | [恢复] 按钮 | ✅ |
| 删除快照 | `DELETE /api/snapshots/{id}` | [删除] 按钮 | ✅ |
| 批量删除 | `POST /api/snapshots/batch-delete` | 待实现 | ⏸️ |

### 4.2 快照 API 设计

#### 创建快照

```http
POST /api/v1/snapshots
Content-Type: application/json

{
  "name": "2026-04-03 优化 ATR 参数",
  "description": "调整 ATR 过滤器 min_atr_ratio 从 0.3 到 0.5"
}
```

#### 快照列表

```http
GET /api/v1/snapshots?limit=50&offset=0
```

#### 快照预览（对比当前配置）

```http
POST /api/v1/snapshots/{id}/preview

Response:
{
  "snapshot_id": 1,
  "changes": [
    {
      "category": "risk",
      "field": "max_loss_percent",
      "current_value": 1.5,
      "snapshot_value": 1.0,
      "requires_restart": false
    }
  ],
  "requires_restart": false
}
```

#### 一键恢复

```http
POST /api/v1/snapshots/{id}/rollback

Request (optional):
{
  "create_snapshot_before": true  // 恢复前创建当前配置快照
}

Response:
{
  "success": true,
  "message": "配置已恢复到快照 #1",
  "requires_restart": false,
  "previous_snapshot_id": 3
}
```

#### 删除快照

```http
DELETE /api/v1/snapshots/{id}
```

**约束**: 不能删除唯一的快照（至少保留一个）

---

### 4.3 自动快照功能

在重大操作前**自动**创建快照，无需用户手动操作。

#### 触发场景

| 场景 | 快照命名格式 | 说明 |
|------|-------------|------|
| **配置导入前** | `auto-import-YYYYMMDD-HHMMSS` | 导入 YAML 配置前自动备份当前配置 |
| **批量修改前** | `auto-bulk-YYYYMMDD-HHMMSS` | 批量修改配置前自动备份 |
| **快照恢复前** | `auto-rollback-YYYYMMDD-HHMMSS` | 恢复到其他快照前自动备份当前配置 |
| **策略重大变更前** | `auto-strategy-YYYYMMDD-HHMMSS` | 策略配置大改前自动备份 |

#### 自动快照 API

```http
POST /api/v1/snapshots/auto
Content-Type: application/json

{
  "trigger": "import",  // 触发场景：import | bulk | rollback | strategy
  "description": "导入前自动备份"  // 可选，覆盖默认描述
}
```

**响应**:
```json
{
  "success": true,
  "snapshot_id": 5,
  "snapshot_name": "auto-import-20260403-143022",
  "created_at": "2026-04-03T14:30:22Z"
}
```

#### 自动快照标记

```sql
ALTER TABLE config_snapshots ADD COLUMN is_auto INTEGER DEFAULT 0 CHECK (is_auto IN (0, 1));
ALTER TABLE config_snapshots ADD COLUMN trigger_type TEXT;  -- import | bulk | rollback | strategy

#### 自动快照执行协议

| 项目 | 说明 |
|------|------|
| **触发时机** | 操作**前**执行（先创建快照，再执行原操作） |
| **失败策略** | 记录错误日志，但不阻断原操作（降级为非阻塞操作） |
| **命名规则** | `{trigger_type}-{YYYYMMDD}-{HHmmss}` |
| **保留策略** | 自动快照保留 30 天，手动快照永久保留 |

```

---

### 4.4 配置对比功能（增强）

支持**任意两个版本**之间的配置对比。

#### Diff 算法规则

配置对比使用以下 diff 算法：

| 数据类型 | 对比规则 |
|----------|----------|
| **标量字段** | 直接比较值（如 `max_loss_percent: 1.5 → 1.0`） |
| **数组字段** | 按元素 ID 对比，无 ID 则按索引对比 |
| **对象字段** | 递归比较各属性 |
| **JSON 字段** | 解析后递归对比（如 `triggers`, `filters`） |

**变更类型**:
- `added`: 目标版本中存在但源版本中不存在
- `modified`: 源版本和目标版本都存在但值不同
- `deleted`: 源版本中存在但目标版本中不存在

```python
def compute_diff(source: dict, target: dict, path: str = "") -> List[Change]:
    """
    计算两个配置对象之间的差异

    Diff 算法规则:
    1. 标量字段：直接比较值
    2. 数组字段：按元素 ID 对比，无 ID 则按索引对比
    3. 对象字段：递归比较各属性
    4. JSON 字段：解析后递归对比
    """
    changes = []

    all_keys = set(source.keys()) | set(target.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key

        if key not in source:
            # added
            changes.append(Change(
                field=current_path,
                change_type="added",
                source_value=None,
                target_value=target[key]
            ))
        elif key not in target:
            # deleted
            changes.append(Change(
                field=current_path,
                change_type="deleted",
                source_value=source[key],
                target_value=None
            ))
        elif source[key] != target[key]:
            # modified
            changes.append(Change(
                field=current_path,
                change_type="modified",
                source_value=source[key],
                target_value=target[key]
            ))

    return changes
```



#### 对比类型

| 对比类型 | API | 说明 |
|----------|-----|------|
| **快照 vs 当前** | `POST /api/v1/snapshots/{id}/preview` | 已有的预览功能 |
| **快照 vs 快照** | `POST /api/v1/snapshots/compare` | 两个快照之间对比 |
| **历史 vs 当前** | `POST /api/v1/history/{id}/compare` | 历史记录与当前对比 |
| **历史 vs 历史** | `POST /api/v1/history/compare` | 两个历史记录之间对比 |

#### 快照 vs 快照 对比 API

```http
POST /api/v1/snapshots/compare
Content-Type: application/json

{
  "source_snapshot_id": 1,
  "target_snapshot_id": 3
}
```

**响应**:
```json
{
  "source_snapshot": {
    "id": 1,
    "name": "2026-04-01 初始配置",
    "created_at": "2026-04-01T08:00:00Z"
  },
  "target_snapshot": {
    "id": 3,
    "name": "2026-04-03 优化 ATR 参数",
    "created_at": "2026-04-03T10:00:00Z"
  },
  "changes": [
    {
      "category": "risk",
      "field": "max_loss_percent",
      "source_value": 1.5,
      "target_value": 1.0,
      "change_type": "modified"
    },
    {
      "category": "strategy",
      "action": "modified",
      "name": "Pinbar+EMA60",
      "changes": {
        "filters": "ATR period 14 → 21"
      }
    },
    {
      "category": "symbols",
      "action": "added",
      "symbol": "DOGE/USDT:USDT"
    }
  ],
  "summary": {
    "total_changes": 3,
    "added": 1,
    "modified": 2,
    "deleted": 0
  }
}
```

---

### 4.5 前端快照管理 UI（更新）

```
┌─────────────────────────────────────────────────────────────┐
│ 📁 配置快照管理                          [+ 新建快照]        │
├─────────────────────────────────────────────────────────────┤
│  快照列表                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 🤖 auto-import-20260403-143022          [自动] [删除]  │ │
│  │    导入前自动备份                                       │ │
│  │    2026-04-03 14:30:22 | system                        │ │
│  │    [预览] [恢复] [对比]                                │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ ✅ 2026-04-03 优化 ATR 参数                             │ │
│  │    调整 ATR 过滤器 min_atr_ratio 从 0.3 到 0.5           │ │
│  │    2026-04-03 10:00:00 | user                          │ │
│  │    [预览] [恢复] [删除] [对比]                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  对比模式（选择两个快照后点击 [对比] 按钮）                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 对比：2026-04-01 初始配置  →  2026-04-03 优化 ATR 参数  │ │
│  │                                                         │ │
│  │  变更摘要：共 3 处变更                                   │ │
│  │  - 风控：max_loss_percent 1.5% → 1.0%                  │ │
│  │  - 策略：Pinbar+EMA60 ATR period 14 → 21              │ │
│  │  - 币池：+ DOGE/USDT:USDT                              │ │
│  │                                                         │ │
│  │  [关闭]  [恢复到目标版本]                               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

### 4.6 错误日志设计规范

#### 错误日志记录内容

```python
import logging
import traceback
from datetime import datetime

class ConfigErrorLogger:
    """配置错误日志记录器"""
    
    def __init__(self):
        self.logger = logging.getLogger('config_manager')
    
    def log_error(self, error_type: str, exception: Exception, context: dict = None):
        """
        记录详细错误日志
        
        Args:
            error_type: 错误类型（如 'LOAD_CONFIG', 'IMPORT_YAML', 'HOT_RELOAD'）
            exception: 异常对象
            context: 上下文信息（如配置类别、操作前状态等）
        """
        error_detail = {
            'timestamp': datetime.now().isoformat(),
            'error_type': error_type,
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'traceback': traceback.format_exc(),
            'context': context or {}
        }
        
        self.logger.error(f"Config Error: {error_type} - {json.dumps(error_detail, indent=2)}")
        
        # 同时返回给前端的简化错误信息
        return {
            'error': error_type,
            'message': str(exception),
            'timestamp': error_detail['timestamp']
        }

# 错误类型枚举
class ConfigErrorTypes:
    LOAD_CONFIG = "LOAD_CONFIG"           # 加载配置失败
    SAVE_CONFIG = "SAVE_CONFIG"           # 保存配置失败
    IMPORT_YAML = "IMPORT_YAML"           # 导入 YAML 失败
    EXPORT_YAML = "EXPORT_YAML"           # 导出 YAML 失败
    HOT_RELOAD = "HOT_RELOAD"             # 热重载失败
    ROLLBACK = "ROLLBACK"                 # 快照回滚失败
    VALIDATION = "VALIDATION"             # 配置验证失败
    DB_ERROR = "DB_ERROR"                 # 数据库错误
    AUTO_SNAPSHOT = "AUTO_SNAPSHOT"       # 自动快照失败
```

#### 错误日志示例

```json
{
  "timestamp": "2026-04-03T14:30:22.123456",
  "error_type": "HOT_RELOAD",
  "exception_type": "ValidationError",
  "exception_message": "max_loss_percent must be between 0.001 and 0.05",
  "traceback": "Traceback (most recent call last):\n  File \"src/application/config_manager.py\", line 123, in apply_config\n    ...\n  File \"src/domain/validators.py\", line 45, in validate_risk_config\n    raise ValidationError(...)\n",
  "context": {
    "old_value": {"max_loss_percent": 0.01},
    "new_value": {"max_loss_percent": 0.06},
    "category": "risk_config"
  }
}
```

---

### 4.7 前端快照管理 UI（完成）

```
┌─────────────────────────────────────────────────────────────┐
│ 📁 配置快照管理                          [+ 新建快照]        │
├─────────────────────────────────────────────────────────────┤
│  快照列表                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ✅ 2026-04-03 优化 ATR 参数                             │ │
│  │    调整 ATR 过滤器 min_atr_ratio 从 0.3 到 0.5           │ │
│  │    2026-04-03 10:00:00 | user                          │ │
│  │    [预览] [恢复] [删除]                                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

#### 3.1.3 系统配置表 (`system_configs`)

```sql
CREATE TABLE system_configs (
    id                   INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例约束
    history_bars         INTEGER NOT NULL DEFAULT 100,        -- K 线预热数量
    queue_batch_size     INTEGER NOT NULL DEFAULT 10,         -- 队列批大小
    queue_flush_interval REAL NOT NULL DEFAULT 5.0,           -- 队列刷新间隔 (秒)
    description          TEXT,                                 -- 配置说明
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**注意**: 这些参数**不支持热重载**，修改后需重启系统。

#### 3.1.4 币池配置表 (`symbol_configs`)

```sql
CREATE TABLE symbol_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL UNIQUE,       -- "BTC/USDT:USDT"
    is_core       INTEGER NOT NULL DEFAULT 1, -- 是否核心币（不可删除）
    is_enabled    INTEGER NOT NULL DEFAULT 1, -- 是否启用
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_symbol_enabled ON symbol_configs(is_enabled);
```

#### 3.1.5 通知配置表 (`notification_configs`)

```sql
CREATE TABLE notification_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel       TEXT NOT NULL,              -- 'feishu' | 'wecom' | 'telegram'
    webhook_url   TEXT NOT NULL,              -- Webhook URL
    is_enabled    INTEGER NOT NULL DEFAULT 1, -- 是否启用
    description   TEXT,                       -- 配置说明
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

#### 3.1.6 配置历史表 (`config_history`)

```sql
CREATE TABLE config_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type     TEXT NOT NULL,            -- 'strategy' | 'risk' | 'system' | 'symbol' | 'notification'
    config_id       INTEGER NOT NULL,         -- 对应表的 ID
    action          TEXT NOT NULL,            -- 'create' | 'update' | 'delete'
    old_value       TEXT,                     -- 旧配置 JSON
    new_value       TEXT,                     -- 新配置 JSON
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT 'user'
);

CREATE INDEX idx_history_type ON config_history(config_type, config_id);
CREATE INDEX idx_history_time ON config_history(created_at);
```

#### 3.1.7 配置快照表 (`config_snapshots`)

```sql
CREATE TABLE config_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,            -- 快照名称（如："2026-04-03 优化 ATR 参数"）
    description     TEXT,                     -- 快照描述
    config_json     TEXT NOT NULL,            -- 完整配置 JSON（包含所有配置类别）
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT 'user'
);

CREATE INDEX idx_snapshot_name ON config_snapshots(name);
```

### 3.2 删除历史表

```sql
-- 删除旧的 custom_strategies 表（如果有数据，先导出备份）
DROP TABLE IF EXISTS custom_strategies;
```

---

## 4. ConfigManager 重构设计

### 4.1 类结构设计

```python
class ConfigManager:
    """
    配置管理器 - 从数据库加载和管理所有配置
    
    职责:
    - 从 DB 加载配置到内存
    - 支持热重载（重新加载 DB 配置）
    - 支持导入/导出 YAML
    - 管理配置历史
    
    热重载支持:
    - ✅ 策略配置 - 支持
    - ✅ 风控配置 - 支持
    - ✅ 币池配置 - 支持
    - ✅ 通知配置 - 支持
    - ❌ 系统配置 - 不支持（需重启）
    """
    
    # ========== 初始化与加载 ==========
    def __init__(self, db_path: str)
    async def load_all_from_db(self) -> None
        """从 DB 加载所有配置到内存（启动时调用）"""
    
    # ========== 配置访问器 ==========
    @property
    def active_strategy(self) -> StrategyDefinition | None
    @property
    def risk_config(self) -> RiskConfig
    @property
    def system_config(self) -> SystemConfig
    @property
    def enabled_symbols(self) -> List[str]
    @property
    def enabled_notification_channels(self) -> List[NotificationChannel]
    
    # ========== 热重载 ==========
    async def apply_config(self) -> None
        """从 DB 重新加载配置（热重载入口）"""
    
    async def reload_strategy(self) -> None
    async def reload_risk_config(self) -> None
    async def reload_symbols(self) -> None
    async def reload_notifications(self) -> None
    
    # ========== 导入/导出 ==========
    def export_to_yaml(self, filepath: str) -> str
        """导出配置为 YAML 文件，返回 YAML 字符串"""
    
    async def import_from_yaml(self, yaml_content: str, preview: bool = True) -> ImportPreview
        """从 YAML 文件导入配置，返回预览结果"""
    
    # ========== 配置历史 ==========
    async def create_snapshot(self, name: str, description: str) -> int
        """创建配置快照"""
    
    async def rollback_to_snapshot(self, snapshot_id: int) -> None
        """回滚到指定快照"""
    
    async def get_history(self, config_type: str, limit: int = 50) -> List[HistoryEntry]
        """获取配置历史"""
    
    # ========== Observer 模式 ==========
    def add_observer(self, callback: Callable[[], Awaitable[None]]) -> None
    async def _notify_observers(self) -> None
```

### 4.2 热重载机制

#### 热重载安全协议

```python
async def apply_config(self) -> None:
    """
    从 DB 重新加载所有可热重载的配置
    
    热重载安全协议 (避免信号处理中断):
    1. 暂停信号管道处理 - 停止接收新的 K 线数据
    2. 等待当前 K 线处理完成 - 确保无进行中策略计算
    3. 重建 Strategy Runner - 使用新配置重建策略引擎
    4. 重新订阅 K 线 (如果币池变化) - ExchangeGateway 重新订阅
    5. 恢复信号管道处理 - 恢复 K 线接收和策略计算
    
    热重载规则:
    - 策略配置：支持 (重建 Strategy Runner)
    - 风控配置：支持 (原子替换)
    - 币池配置：支持 (重新订阅 K 线)
    - 通知配置：支持 (原子替换)
    - 系统配置：不支持 (需重启)
    """
    async with self._update_lock:
        # 1. 暂停信号管道 (通知 SignalPipeline 暂停处理)
        if signal_pipeline:
            await signal_pipeline.pause_processing()
        
        # 2. 等待当前 K 线处理完成 (最多等待 5 秒)
        await self._wait_for_current_kline_processing(timeout=5.0)
        
        # 3. 可热重载的配置按类别重新加载
        await self.reload_strategy()
        await self.reload_risk_config()
        await self.reload_symbols()
        await self.reload_notifications()
        
        # 4. 系统配置检查 (如变更，记录警告)
        self._check_system_config_changed()
        
        # 5. 恢复信号管道处理
        if signal_pipeline:
            await signal_pipeline.resume_processing()
        
        # 6. 通知 Observer
        await self._notify_observers()
```

#### 热重载实现细节

```python
async def reload_strategy(self) -> None:
    """重新加载策略配置 - 重建 Strategy Runner"""
    self._active_strategy = await self.config_repository.get_active_strategy()
    if self._active_strategy:
        self.strategy_engine.rebuild(self._active_strategy)

async def reload_risk_config(self) -> None:
    """重新加载风控配置 - 原子替换"""
    self._risk_config = await self.config_repository.get_risk_config()
    self.risk_calculator.update_config(self._risk_config)

async def reload_symbols(self) -> None:
    """重新加载币池配置 - 重新订阅 K 线"""
    old_symbols = set(self._enabled_symbols)
    self._enabled_symbols = await self.config_repository.get_enabled_symbols()
    new_symbols = set(self._enabled_symbols)
    
    if old_symbols != new_symbols:
        # 币池变化，需要重新订阅
        added = new_symbols - old_symbols
        removed = old_symbols - new_symbols
        await self.exchange_gateway.unsubscribe_ohlcv(removed)
        await self.exchange_gateway.subscribe_ohlcv(added)

async def reload_notifications(self) -> None:
    """重新加载通知配置 - 原子替换"""
    self._notification_channels = await self.config_repository.get_enabled_notifications()
```


### 4.3 模块化隔离设计

```python
# 配置模块与其他模块的边界

┌─────────────────────────────────────────────────────────────┐
│                      ConfigManager                          │
│  - 仅负责配置加载/热重载/导入导出                            │
│  - 不依赖：SignalPipeline, ExchangeGateway, StrategyEngine  │
└─────────────────────────────────────────────────────────────┘
           │ depends on
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    ConfigRepository                         │
│  - 纯数据库操作（CRUD）                                      │
│  - 不依赖：业务逻辑层                                        │
└─────────────────────────────────────────────────────────────┘
           │ depends on
           ▼
┌─────────────────────────────────────────────────────────────┐
│                      SQLite DB                              │
│  - 配置数据存储                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键隔离点**:
1. `ConfigManager` 不直接依赖 `SignalPipeline`，通过 Observer 模式解耦
2. `ConfigRepository` 是纯数据库操作层，可独立测试
3. 配置加载失败不影响其他模块启动（抛出明确异常）

---

## 5. API 设计

### 5.1 配置管理 API

#### 5.1.1 获取所有配置

```
GET /api/config
```

**响应**:
```json
{
  "strategy": { "id": 1, "name": "Pinbar+EMA60", "triggers": [...], "filters": [...] },
  "risk": { "max_loss_percent": 1.0, "max_total_exposure": 0.8 },
  "system": { "history_bars": 100, "queue_batch_size": 10 },
  "symbols": [
    { "symbol": "BTC/USDT:USDT", "is_core": true, "is_enabled": true }
  ],
  "notifications": [
    { "channel": "feishu", "webhook_url": "https://...", "is_enabled": true }
  ]
}
```

#### 5.1.2 更新风控配置（热重载）

```
PUT /api/config/risk
Content-Type: application/json

{
  "max_loss_percent": 1.5,
  "max_total_exposure": 0.75
}
```

**响应**:
```json
{
  "success": true,
  "message": "风控配置已更新，已触发热重载",
  "requires_restart": false
}
```

#### 5.1.3 更新系统配置（需重启）

```
PUT /api/config/system
Content-Type: application/json

{
  "history_bars": 200
}
```

**响应**:
```json
{
  "success": true,
  "message": "系统配置已更新，需要重启系统才能生效",
  "requires_restart": true
}
```

#### 5.1.4 管理币池配置

```
GET /api/config/symbols          # 获取所有币种
POST /api/config/symbols         # 添加币种
DELETE /api/config/symbols/{id}  # 移除币种（非核心）
```

#### 5.1.5 管理通知配置

```
GET /api/config/notifications          # 获取所有通知渠道
PUT /api/config/notifications/{id}     # 更新通知配置
POST /api/config/notifications         # 添加通知渠道
DELETE /api/config/notifications/{id}  # 删除通知渠道
```

### 5.2 策略配置 API

#### 5.2.1 获取策略列表

```
GET /api/strategies
```

**响应**:
```json
{
  "strategies": [
    { "id": 1, "name": "Pinbar+EMA60", "is_active": true },
    { "id": 2, "name": "吞没形态", "is_active": false }
  ]
}
```

#### 5.2.2 创建策略

```
POST /api/strategies
Content-Type: application/json

{
  "name": "My Pinbar Strategy",
  "description": "...",
  "triggers": [...],
  "filters": [...],
  "apply_to": ["BTC/USDT:USDT:15m"]
}
```

#### 5.2.3 激活策略

```
POST /api/strategies/{id}/activate
```

**说明**: 将指定策略标记为 `is_active=1`，其他策略标记为 `is_active=0`

### 5.3 导入/导出 API

#### 5.3.1 导出配置

```
POST /api/config/export
```

**响应**:
```json
{
  "success": true,
  "yaml_content": "# 盯盘狗配置导出...\nexported_at: \"2026-04-03T10:00:00Z\"\n...",
  "download_url": "/api/config/export/download?file=config_20260403.yaml"
}
```

#### 5.3.2 导入配置预览

```
POST /api/config/import/preview
Content-Type: application/json

{
  "yaml_content": "# 配置内容..."
}
```

**响应**:
```json
{
  "preview": {
    "valid": true,
    "changes": [
      { "category": "risk", "field": "max_loss_percent", "old": 1.0, "new": 1.5 },
      { "category": "strategy", "action": "update", "name": "Pinbar+EMA60" }
    ],
    "errors": [],
    "warnings": ["system_config.history_bars 变更需重启才能生效"]
  }
}
```

#### 5.3.3 确认导入

```
POST /api/config/import/confirm
Content-Type: application/json

{
  "yaml_content": "...",
  "preview_id": "abc123"  // 可选，用于验证预览一致性
}
```

#### preview_id 设计说明

| 项目 | 说明 |
|------|------|
| **生成方式** | UUID v4 |
| **存储位置** | 服务端临时缓存 (TTL: 10 分钟) |
| **用途** | 验证预览与确认的一致性（防止并发修改） |
| **可选原因** | 简单场景可省略，直接确认导入 |

```python
# 预览时生成 preview_id
async def import_preview(self, yaml_content: str) -> ImportPreview:
    preview_id = str(uuid.uuid4())
    preview_result = await self._validate_and_compute_changes(yaml_content)

    # 缓存预览结果，TTL 10 分钟
    await self.cache.set(
        key=f"import_preview:{preview_id}",
        value=json.dumps(preview_result.dict()),
        ttl=600  # 10 分钟
    )

    return ImportPreview(
        preview_id=preview_id,
        valid=preview_result.valid,
        changes=preview_result.changes,
        errors=preview_result.errors,
        warnings=preview_result.warnings
    )

# 确认时验证 preview_id
async def import_confirm(self, yaml_content: str, preview_id: str = None) -> ImportResult:
    if preview_id:
        # 验证预览一致性
        cached_preview = await self.cache.get(f"import_preview:{preview_id}")
        if not cached_preview:
            raise ValidationError("预览已过期，请重新预览")

        # 验证 YAML 内容未变化
        cached_hash = json.loads(cached_preview).get('yaml_hash')
        current_hash = hashlib.sha256(yaml_content.encode()).hexdigest()
        if cached_hash != current_hash:
            raise ValidationError("配置内容已变更，请重新预览")

    # 执行导入
    return await self._execute_import(yaml_content)
```

**响应**:
```json
{
  "success": true,
  "message": "配置已导入，部分配置需重启才能生效",
  "requires_restart": false
}
```

### 5.4 配置历史 API

#### 5.4.1 获取历史快照

```
GET /api/snapshots
```

#### 5.4.2 创建快照

```
POST /api/snapshots
Content-Type: application/json

{
  "name": "2026-04-03 优化 ATR 参数",
  "description": "调整 ATR 过滤器参数"
}
```

#### 5.4.3 回滚快照

```
POST /api/snapshots/{id}/rollback
```

#### 5.4.4 获取配置历史

```
GET /api/history?config_type=strategy&config_id=1&limit=50
```

---

## 6. 前端设计

### 6.1 配置管理页面结构

```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ 配置管理                              [保存] [应用] [?]  │
├─────────────────────────────────────────────────────────────┤
│ 📊 系统信息（只读）                                          │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 交易所：Binance (实盘)                                   │ │
│ │ 版本：v2.x.x                                            │ │
│ │ 启动时间：2026-04-03 10:00:00                           │ │
│ │ API 权限：✅ 只读                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 📁 启动配置（只读，修改需重启）                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ K 线预热数量：[100] ⓘ 系统启动时拉取的历史 K 线数量         │ │
│ │ 队列批大小：[10] ⓘ 批量落盘大小                          │ │
│ │ 队列刷新间隔：[5.0s] ⓘ 队列最大等待时间                  │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 🛡️ 风控配置（可热重载）                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 单笔最大损失：[1.0] % ⓘ 每笔交易最大风险百分比           │ │
│ │ 最大总敞口：[80] % ⓘ 所有持仓总风险上限                 │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 📈 币池管理（可热重载）                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [BTC/USDT:USDT ✅核心] [ETH/USDT:USDT ✅核心] ...       │ │
│ │ [+ 添加币种]                                             │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 🔔 通知配置（可热重载）                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 飞书 Webhook: [https://...] ✅启用                       │ │
│ │ 微信 Webhook: [...] ❌禁用                               │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 🧠 策略配置（可热重载）                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [Pinbar+EMA60 ✅启用] [吞没形态 ❌禁用] [...]           │ │
│ │ [+ 新建策略]                                             │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 📁 备份/恢复                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [导出 YAML]  [导入 YAML]  [查看历史]                     │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 前端组件结构

```
web-front/src/pages/Config.tsx           # 配置管理主页面
├── ConfigSection.tsx                     # 配置区块通用组件
├── SystemInfo.tsx                        # 系统信息区块
├── SystemConfig.tsx                      # 启动配置区块（只读）
├── RiskConfig.tsx                        # 风控配置区块
├── SymbolConfig.tsx                      # 币池管理区块
├── NotificationConfig.tsx                # 通知配置区块
├── StrategyConfig.tsx                    # 策略配置区块
└── BackupRestore.tsx                     # 备份/恢复区块

web-front/src/components/ConfigTooltip.tsx  # Tooltip 通用组件
```

---

## 7. 配置说明 Tooltip 设计

### 7.1 配置描述数据

```python
CONFIG_DESCRIPTIONS = {
    # 风控配置
    "max_loss_percent": {
        "label": "单笔最大损失",
        "description": "每笔交易愿意承担的最大风险百分比。1% 表示如果触发止损，最多损失账户总额的 1%。建议范围：0.5%~2%",
        "unit": "%",
        "min": 0.1,
        "max": 5.0
    },
    "max_total_exposure": {
        "label": "最大总敞口",
        "description": "所有持仓的总风险上限。80% 表示当已有持仓占用 80% 风险空间后，新信号会自动降低仓位或拒绝",
        "unit": "%",
        "min": 0.5,
        "max": 1.0
    },
    
    # 系统配置（只读）
    "history_bars": {
        "label": "K 线预热数量",
        "description": "系统启动时从交易所拉取的历史 K 线数量。较多的预热数据可以提高 EMA/MTF 等指标的准确性，但会增加启动时间。此配置来自环境变量，修改需重启",
        "unit": "根",
        "readonly": True
    },
    
    # 策略参数
    "min_wick_ratio": {
        "label": "最小影线占比",
        "description": "Pinbar 影线占 K 线全长的最小比例。较低的值会允许更多形态通过，但可能包含更多噪音。建议范围：0.5~0.7",
        "unit": "",
        "min": 0.3,
        "max": 0.9
    }
}
```

### 7.2 前端 Tooltip 组件

```tsx
interface TooltipProps {
  content: string;
  children: React.ReactNode;
}

const ConfigTooltip: React.FC<TooltipProps> = ({ content, children }) => {
  return (
    <div className="relative inline-block">
      {children}
      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 hidden group-hover:block z-50">
        <div className="bg-gray-800 text-white text-xs rounded py-1 px-2 w-64">
          {content}
        </div>
      </div>
    </div>
  );
};
```

---

## 8. 信号冷却逻辑重构

### 8.1 当前逻辑

```python
# 当前：固定冷却期
if symbol in cooldown_cache and (now - last_signal_time) < cooldown_seconds:
    return  # 冷却期内，忽略信号
```

### 8.2 新逻辑：高质量覆盖

```python
async def should_send_signal(self, new_signal: SignalResult) -> bool:
    """
    判断是否应该发送新信号
    
    规则:
    1. 如无 pending 信号，直接发送
    2. 如有 pending 信号，比较 pattern_score
    3. 新信号分数更高：覆盖旧信号，旧状态改为 SUPERSEDED
    4. 新信号分数更低或相等：忽略新信号
    """
    # 查找同一币种相同方向的 pending 信号
    existing = await self._repository.find_pending_signal(
        symbol=new_signal.symbol,
        direction=new_signal.direction
    )
    
    if existing is None:
        return True  # 无现有信号，直接发送
    
    # 比较质量分数
    if new_signal.pattern_score > existing.pattern_score:
        # 高质量覆盖低质量
        await self._repository.update_signal_status(
            signal_id=existing.id,
            status=SignalStatus.SUPERSEDED
        )
        return True
    else:
        return False  # 忽略低质量信号
```

### 8.3 数据库变更

```sql
-- 信号状态枚举增加 SUPERSEDED
ALTER TABLE signals ADD COLUMN status TEXT DEFAULT 'PENDING';

-- 或创建新的状态映射表
CREATE TABLE signal_status_enum (
    status TEXT PRIMARY KEY
);

INSERT INTO signal_status_enum VALUES 
    ('PENDING'), ('NOTIFIED'), ('SUPERSEDED'), ('EXPIRED');
```

---

## 9. 实现计划

### 阶段 1: 数据库层（Day 1-2）

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建新表 | `src/infrastructure/config_repository.py` | 新建配置仓储层 |
| 迁移脚本 | `scripts/migrate_config_to_db.py` | YAML → DB 迁移工具 |
| 删除旧表 | - | 清理 `custom_strategies` 表 |

### 阶段 2: ConfigManager 重构（Day 2-3）

| 任务 | 文件 | 说明 |
|------|------|------|
| 重写 ConfigManager | `src/application/config_manager.py` | 从 DB 加载配置 |
| 实现热重载 | 同上 | `apply_config()` 方法 |
| 实现导入/导出 | 同上 | `export_to_yaml()`, `import_from_yaml()` |

### 阶段 3: API 实现（Day 3-4）

| 任务 | 文件 | 说明 |
|------|------|------|
| 配置管理 API | `src/interfaces/api.py` | `/api/config/*` 端点 |
| 导入/导出 API | 同上 | `/api/config/export`, `/api/config/import` |
| 历史快照 API | 同上 | `/api/snapshots/*` 端点 |

### 阶段 4: 前端实现（Day 4-6）

| 任务 | 文件 | 说明 |
|------|------|------|
| 配置管理页面 | `web-front/src/pages/Config.tsx` | 单页面配置管理 |
| Tooltip 组件 | `web-front/src/components/ConfigTooltip.tsx` | 配置说明提示 |
| 导入/导出交互 | `web-front/src/pages/Config.tsx` | 备份/恢复功能 |

### 阶段 5: 信号冷却重构（Day 6）

| 任务 | 文件 | 说明 |
|------|------|------|
| 信号状态枚举 | `src/domain/models.py` | 增加 `SUPERSEDED` 状态 |
| 信号管道重构 | `src/application/signal_pipeline.py` | 高质量覆盖逻辑 |

### 阶段 6: 测试与部署（Day 7）

| 任务 | 说明 |
|------|------|
| 单元测试 | 配置加载、热重载、导入/导出 |
| 集成测试 | 配置管理端到端测试 |
| 部署上线 | 数据库迁移、应用更新 |

---

## 10. 风险评估与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 配置迁移丢失 | 高 | 迁移前自动备份 YAML 到 `config.backup.yaml` |
| 热重载失败 | 中 | 提供明确的错误提示和"重启系统"引导 |
| YAML 导入验证失败 | 中 | 导入前预览，允许用户确认和修正 |
| 模块化隔离不完整 | 中 | Code Review 重点检查依赖关系 |

---

## 11. 验收标准

### F1: 数据库配置存储

- [ ] 所有配置类别有对应的表
- [ ] 策略配置使用 JSON 灵活存储
- [ ] 风控/系统配置使用结构化字段
- [ ] 配置历史表和快照表正常工作

### F2: 配置导入/导出

- [ ] 导出格式为 YAML，人类可读
- [ ] 导入前显示预览
- [ ] 导入验证错误提示清晰

### F3: 配置历史版本管理

- [ ] 每次修改自动记录历史
- [ ] 支持手动创建命名快照
- [ ] 支持从快照回滚

### F4: 默认配置初始化

- [ ] 首次启动 DB 为空时自动初始化默认配置
- [ ] 默认值符合 PRD 要求

### F5: 前端配置管理页面

- [ ] 单页面展示所有配置
- [ ] 只读/可编辑区分清晰
- [ ] Tooltip 提示正常显示

### F6: 信号冷却逻辑重构

- [ ] 移除固定冷却期逻辑
- [ ] 高质量覆盖低质量逻辑正常
- [ ] 被覆盖信号状态标记为 SUPERSEDED

### F7: 配置说明 Tooltip

- [ ] 所有配置项有 Tooltip 说明
- [ ] 只读配置项 Tooltip 标注"修改需重启"

---

## 12. 相关文件

- PRD: `docs/products/2026-04-03-config-management-prd.md`
- 实现计划：待创建
- 契约文档：`docs/designs/config-management-contract.md`

---

*文档版本：1.0 | 最后更新：2026-04-03（已修复）*

---

## 附录 A. 架构问题修复记录

本次修复解决了架构评审中发现的以下问题：

| 问题 | 优先级 | 修复方案 | 修复位置 |
|------|--------|----------|----------|
| **单例约束不够严谨** | 🔴 高 | 改用 BEFORE INSERT 触发器强制单例约束 | 3.2.2, 3.2.3 |
| **策略激活单例约束语法不兼容 SQLite** | 🔴 高 | 改用 BEFORE INSERT/UPDATE 触发器 | 3.2.1 |
| **配置历史缺少 INSERT/DELETE 记录** | 🟡 中 | 补充所有表的 audit_after_insert 和 audit_after_delete 触发器 | 3.2.6 |
| **热重载缺少线程安全考虑** | 🟡 中 | 添加热重载安全协议（暂停→等待→重建→恢复） | 4.2 |
| **API 密钥存储方案缺失** | 🟡 中 | 明确 API 密钥存储在环境变量，不入库 | 0.4 |
| **自动快照触发时机不明确** | 🟢 低 | 明确触发时机、失败策略、命名规则 | 4.3 |
| **配置对比缺少 diff 算法说明** | 🟢 低 | 补充 diff 算法规则表 | 4.4 |
| **preview_id 生成逻辑未说明** | 🟢 低 | 明确生成方式、存储位置、验证逻辑 | 5.3.3 |

### 修复详情

#### 1. 单例约束改用触发器实现

**问题**: `CHECK (id = 1)` 约束在 SQLite 中不够强制。

**修复**:
```sql
-- 风控配置单例约束
CREATE TRIGGER risk_configs_single_row_insert
BEFORE INSERT ON risk_configs
WHEN (SELECT COUNT(*) FROM risk_configs) >= 1
BEGIN
    SELECT RAISE(ABORT, 'risk_configs 只能有一条记录');
END;
```

#### 2. 策略激活单例约束

**问题**: `CASE WHEN` 部分索引在 SQLite 中可能不工作。

**修复**:
```sql
CREATE TRIGGER check_single_active_strategy_before_insert
BEFORE INSERT ON strategy_configs
WHEN NEW.is_active = 1 AND (SELECT COUNT(*) FROM strategy_configs WHERE is_active = 1) > 0
BEGIN
    SELECT RAISE(ABORT, '同一时间只能有一个激活的策略');
END;
```

#### 3. 配置历史触发器完善

**问题**: 只有 UPDATE 触发器，缺少 INSERT 和 DELETE。

**修复**: 为所有配置表添加完整的 INSERT/UPDATE/DELETE 审计触发器。

#### 4. 热重载安全协议

**问题**: 未考虑正在处理 K 线时热重载的状态不一致风险。

**修复**:
```
热重载流程:
1. 暂停信号管道处理
2. 等待当前 K 线处理完成
3. 重建 Strategy Runner
4. 重新订阅 K 线（如果币池变化）
5. 恢复信号管道处理
```

---

*修复完成时间：2026-04-03*
