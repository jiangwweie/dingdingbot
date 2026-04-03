# PRD - 配置管理系统重构

**文档编号**: PRD-2026-001  
**创建日期**: 2026-04-03  
**优先级**: 🔴 最高（架构重构）  
**预计工作量**: 5-7 天

---

## 1. 背景与目标

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

---

## 2. 功能需求

### F1: 数据库配置存储

**需求描述**: 将配置从 YAML 文件迁移到 SQLite 数据库，按类别分表存储。

**用户故事**:
> 作为系统管理员，我希望配置存储在数据库中，这样我可以动态修改配置而无需编辑文件。

**验收标准**:
- [ ] 策略配置存储在 `strategy_configs` 表（JSON 格式）
- [ ] 风控配置存储在 `risk_configs` 表（结构化字段）
- [ ] 系统配置存储在 `system_configs` 表（结构化字段）
- [ ] 币池配置存储在 `symbol_configs` 表
- [ ] 通知配置存储在 `notification_configs` 表
- [ ] 交易所 API 密钥从环境变量读取，不入库

**数据库表结构**:
```sql
-- 策略配置表
CREATE TABLE strategy_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    triggers      TEXT NOT NULL,      -- JSON
    filters       TEXT NOT NULL,      -- JSON
    logic_tree    TEXT,               -- JSON (可选)
    apply_to      TEXT NOT NULL,      -- JSON
    is_active     INTEGER DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 风控配置表（单例）
CREATE TABLE risk_configs (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    max_loss_percent  REAL NOT NULL DEFAULT 1.0,
    max_total_exposure REAL NOT NULL DEFAULT 0.8,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 系统配置表（单例）
CREATE TABLE system_configs (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    history_bars          INTEGER NOT NULL DEFAULT 100,
    queue_batch_size      INTEGER NOT NULL DEFAULT 10,
    queue_flush_interval  REAL NOT NULL DEFAULT 5.0,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 币池配置表
CREATE TABLE symbol_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL UNIQUE,
    is_core       INTEGER DEFAULT 1,
    is_enabled    INTEGER DEFAULT 1,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 通知配置表
CREATE TABLE notification_configs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel       TEXT NOT NULL,
    webhook_url   TEXT NOT NULL,
    is_enabled    INTEGER DEFAULT 1,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### F2: 配置导入/导出

**需求描述**: 支持将数据库配置导出为 YAML 文件，或从 YAML 文件导入恢复配置。

**用户故事**:
> 作为系统管理员，我希望导出配置为 YAML 文件，这样我可以定期备份配置，或在系统迁移时快速恢复。

**验收标准**:
- [ ] 导出格式为 YAML，包含所有配置类别
- [ ] 导出的 YAML 文件人类可读
- [ ] 导入前显示预览，列出将要修改的配置项
- [ ] 导入时验证 YAML 格式合法性
- [ ] 验证失败时提示具体错误位置和原因

**导出 YAML 格式示例**:
```yaml
# 盯盘狗配置导出 - 2026-04-03T10:00:00Z
exported_at: "2026-04-03T10:00:00Z"
version: "1.0"

risk_config:
  max_loss_percent: 1.0
  max_total_exposure: 0.8

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
    triggers: [...]
    filters: [...]
    apply_to: [...]
    is_active: true
```

---

### F3: 配置历史与版本管理

**需求描述**: 记录所有配置变更历史，支持手动创建快照和版本回滚。

**用户故事**:
> 作为系统管理员，我希望查看配置修改历史，并在配置出现问题时快速回滚到之前的版本。

**验收标准**:
- [ ] 每次配置修改自动记录到 `config_history` 表
- [ ] 历史记录包含：修改时间、修改内容、旧值、新值
- [ ] 支持手动创建命名快照（如"2026-04-03 优化 ATR 参数"）
- [ ] 支持从快照回滚配置
- [ ] 前端提供历史版本列表和对比功能

**数据库表结构**:
```sql
-- 配置历史表
CREATE TABLE config_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type     TEXT NOT NULL,
    config_id       INTEGER NOT NULL,
    action          TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by      TEXT DEFAULT 'user'
);

-- 配置快照表
CREATE TABLE config_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    config_json     TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by      TEXT DEFAULT 'user'
);
```

---

### F4: 默认配置初始化

**需求描述**: 首次启动时，如数据库为空，自动插入默认配置。

**用户故事**:
> 作为新用户，我希望系统首次启动时自动初始化默认配置，这样我可以立即开始使用，无需手动创建所有配置。

**验收标准**:
- [ ] 检测到数据库为空时自动初始化
- [ ] 默认风控配置：`max_loss_percent=1.0`, `max_total_exposure=0.8`
- [ ] 默认系统配置：`history_bars=100`, `queue_batch_size=10`, `queue_flush_interval=5.0`
- [ ] 默认币池：`["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]`
- [ ] 策略配置为空，需用户手动创建
- [ ] 通知配置为空，需用户手动配置

---

### F5: 前端配置管理页面

**需求描述**: 创建单页面配置管理界面，分区块展示所有配置项。

**用户故事**:
> 作为用户，我希望在一个页面内查看所有和修改配置，这样我无需在多个页面之间切换。

**验收标准**:
- [ ] 单页面结构，分区块展示所有配置
- [ ] 系统信息/启动配置：只读显示（灰色）
- [ ] 风控/币池/通知/策略：可编辑
- [ ] 修改后显示"保存"和"应用"按钮
- [ ] "保存"仅写入数据库，"应用"触发热重载
- [ ] 所有配置项支持 Tooltip 提示（鼠标悬停显示说明）
- [ ] 只读配置项 Tooltip 说明"此配置来自环境变量"

**页面结构**:
```
┌─────────────────────────────────────────────┐
│ ⚙️ 配置管理                                 │
├─────────────────────────────────────────────┤
│ 📊 系统信息（只读）                          │
│   交易所（实盘）、版本、启动时间、API 权限     │
├─────────────────────────────────────────────┤
│ 📁 启动配置（只读）                          │
│   K 线预热数量、队列配置                       │
├─────────────────────────────────────────────┤
│ 🛡️ 风控配置（可编辑）                        │
│   单笔最大损失、最大总敞口                   │
├─────────────────────────────────────────────┤
│ 📈 币池管理（可编辑）                        │
│   币池列表、添加/移除币种                    │
├─────────────────────────────────────────────┤
│ 🔔 通知配置（可编辑）                        │
│   Webhook URL、启用开关                      │
├─────────────────────────────────────────────┤
│ 🧠 策略配置（可编辑）                        │
│   策略列表、启用/禁用、编辑参数              │
├─────────────────────────────────────────────┤
│ 📁 备份/恢复                                 │
│   [导出 YAML] [导入 YAML] [查看历史]         │
└─────────────────────────────────────────────┘
```

---

### F6: 信号冷却逻辑重构

**需求描述**: 移除固定冷却期逻辑，改用高质量信号覆盖低质量信号。

**用户故事**:
> 作为交易员，我希望重要的高质量信号能够覆盖之前的低质量信号，而不是被固定冷却期阻挡，这样我不会错过关键的交易机会。

**验收标准**:
- [ ] 移除 `cooldown_seconds` 配置的冷却功能
- [ ] 新信号与同一币种相同方向的 pending 信号比较 `pattern_score`
- [ ] 新信号分数更高时：覆盖旧信号，旧信号状态改为 `SUPERSEDED`
- [ ] 新信号分数更低或相等时：忽略新信号
- [ ] 被覆盖的信号在 DB 中保留记录，状态标记为 `SUPERSEDED`
- [ ] 通知推送仅发送最终未被覆盖的信号

**伪代码**:
```python
def should_send_signal(new_signal):
    # 查找同一币种相同方向的 pending 信号
    existing = find_pending_signal(new_signal.symbol, new_signal.direction)
    
    if existing is None:
        return True  # 无现有信号，直接发送
    
    # 比较质量分数
    if new_signal.pattern_score > existing.pattern_score:
        # 高质量覆盖低质量
        existing.status = "SUPERSEDED"
        save(existing)
        return True
    else:
        return False  # 忽略低质量信号
```

---

### F7: 配置说明 Tooltip

**需求描述**: 所有配置项提供 Tooltip 提示，说明参数含义和使用建议。

**用户故事**:
> 作为用户，我希望看到每个配置项的说明，这样我不需要查阅文档就能理解参数的作用。

**验收标准**:
- [ ] 每个配置项在后端定义 `description` 字段
- [ ] 前端以 Tooltip 形式展示（鼠标悬停显示）
- [ ] Tooltip 内容简洁明了（≤100 字）
- [ ] 只读配置项 Tooltip 包含"此配置来自环境变量"说明

**配置说明示例**:
| 配置项 | Tooltip 文案 |
|--------|----------|
| `max_loss_percent` | "每笔交易愿意承担的最大风险百分比。1% 表示如果触发止损，最多损失账户总额的 1%。建议范围：0.5%~2%" |
| `max_total_exposure` | "所有持仓的总风险上限。80% 表示当已有持仓占用 80% 风险空间后，新信号会自动降低仓位或拒绝。" |
| `history_bars` | "系统启动时从交易所拉取的历史 K 线数量。较多的预热数据可以提高 EMA/MTF 等指标的准确性，但会增加启动时间。此配置来自环境变量，修改需重启。" |
| `min_wick_ratio` | "Pinbar 影线占 K 线全长的最小比例。较低的值会允许更多形态通过，但可能包含更多噪音。建议范围：0.5~0.7" |

---

## 3. 非功能需求

| 类别 | 需求 |
|------|------|
| **性能** | 配置热重载时间 < 1 秒 |
| **安全性** | API 密钥不入库，仅从环境变量读取 |
| **可靠性** | 配置修改失败时回滚，保持数据一致性 |
| **可追溯性** | 所有配置变更可追溯，支持审计 |
| **兼容性** | 支持从现有 YAML 配置迁移到数据库 |
| **系统定位** | V2 为实盘监控系统，不支持测试网切换 |

---

## 4. 配置分类与热重载规则

| 配置类别 | 热重载 | 说明 |
|----------|--------|------|
| **系统信息** | ❌ 只读 | 交易所（实盘）、版本、启动时间等 |
| **启动配置** | ❌ 需重启 | `history_bars`、队列配置（来自环境变量） |
| **风控配置** | ✅ 支持 | `max_loss_percent`、`max_total_exposure` |
| **币池配置** | ✅ 支持 | 添加/移除币种 |
| **通知配置** | ✅ 支持 | Webhook URL、启用开关 |
| **策略配置** | ✅ 支持 | 策略参数、启用/禁用 |

---

## 5. 依赖与约束

| 依赖项 | 说明 |
|--------|------|
| 环境变量 | `EXCHANGE_NAME`, `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`（移除 `EXCHANGE_TESTNET`） |
| 现有架构 | `ConfigManager`、`SignalPipeline` 需重构支持 DB 读取 |
| 前端框架 | React + TypeScript + TailwindCSS |
| 系统定位 | 仅实盘监控，无测试网开关 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 配置迁移丢失 | 高 | 迁移前自动备份 YAML 配置 |
| 热重载失败 | 中 | 提供"重启系统"提示 |
| YAML 导入验证失败 | 中 | 导入前预览，允许用户确认 |

---

## 7. 待办事项

- [ ] 架构师编写设计文档
- [ ] 编写实现计划
- [ ] 后端开发
- [ ] 前端开发
- [ ] 测试验证
- [ ] 部署上线

---

*文档版本：1.0 | 最后更新：2026-04-03*
