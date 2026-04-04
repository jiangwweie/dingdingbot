# ADR-2026-004-001: 配置管理系统架构重构设计

> **架构决策记录 (Architecture Decision Record)**
> **文档级别**: P8 架构师评审级
> **决策日期**: 2026-04-04
> **最后更新**: 2026-04-04
> **状态**: ✅ 已确认 (Confirmed)
> **影响范围**: ConfigManager + 前端配置页面 + 数据库表结构 + 信号管道

---

## 更新记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.1 | 2026-04-04 | 确认 API 设计：添加策略管理端点、导入预览/确认流程、统一 API 路径版本 |

---

## 1. 确认后的 API 设计

### 1.1 API 路径版本规范

```
统一前缀: /api/v1/config/*

设计原则:
- 所有配置相关 API 统一使用 v1 版本前缀
- RESTful 风格，资源名词复数形式
- 动作通过 HTTP Method 区分 (GET/POST/PUT/DELETE)
```

### 1.2 完整 API 端点列表

```
┌─────────────────────────────────────────────┬──────────┬────────────────────────┐
│ 端点                                        │ 方法     │ 功能                   │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 全局配置                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config                              │ GET      │ 获取全部配置摘要        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 风控配置                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/risk                         │ GET      │ 获取风控配置            │
│ /api/v1/config/risk                         │ PUT      │ 更新风控（热重载✅）    │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 系统配置                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/system                       │ GET      │ 获取系统配置            │
│ /api/v1/config/system                       │ PUT      │ 更新系统（需重启⚠️）    │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 策略配置（配置页面管理）                      │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/strategies                   │ GET      │ 获取策略列表            │
│ /api/v1/config/strategies                   │ POST     │ 创建策略                │
│ /api/v1/config/strategies/{id}              │ GET      │ 获取策略详情            │
│ /api/v1/config/strategies/{id}              │ PUT      │ 更新策略（热重载✅）    │
│ /api/v1/config/strategies/{id}              │ DELETE   │ 删除策略                │
│ /api/v1/config/strategies/{id}/toggle       │ POST     │ 启用/禁用策略           │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 币池配置                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/symbols                      │ GET      │ 获取币池列表            │
│ /api/v1/config/symbols                      │ POST     │ 添加币种                │
│ /api/v1/config/symbols/{symbol}             │ PUT      │ 更新币种（热重载✅）    │
│ /api/v1/config/symbols/{symbol}/toggle      │ POST     │ 启用/禁用币种           │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 通知配置                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/notifications                │ GET      │ 获取通知渠道列表        │
│ /api/v1/config/notifications                │ POST     │ 添加通知渠道            │
│ /api/v1/config/notifications/{id}           │ PUT      │ 更新通知渠道            │
│ /api/v1/config/notifications/{id}           │ DELETE   │ 删除通知渠道            │
│ /api/v1/config/notifications/{id}/test      │ POST     │ 测试通知渠道            │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 导入导出（YAML）                             │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/export                       │ POST     │ 导出 YAML               │
│ /api/v1/config/import/preview               │ POST     │ 预览导入（安全）        │
│ /api/v1/config/import/confirm               │ POST     │ 确认导入                │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ 快照管理                                     │          │                        │
├─────────────────────────────────────────────┼──────────┼────────────────────────┤
│ /api/v1/config/snapshots                    │ GET      │ 获取快照列表            │
│ /api/v1/config/snapshots                    │ POST     │ 创建快照                │
│ /api/v1/config/snapshots/{id}               │ GET      │ 获取快照详情            │
│ /api/v1/config/snapshots/{id}/activate      │ POST     │ 回滚到快照              │
│ /api/v1/config/snapshots/{id}               │ DELETE   │ 删除快照                │
└─────────────────────────────────────────────┴──────────┴────────────────────────┘
```

### 1.3 策略配置在配置页面管理（与策略工作台冗余）

```
┌─────────────────────────────────────────────────────────────────┐
│                    策略管理架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   配置页面 (Config.tsx)          策略工作台 (Strategy Workbench)│
│   ┌──────────────────┐          ┌──────────────────┐           │
│   │ • 策略列表        │          │ • 可视化构建      │           │
│   │ • 启用/禁用       │◄────────►│ • 复杂过滤器链    │           │
│   │ • 基础参数编辑    │   冗余   │ • 高级触发器配置  │           │
│   │ • 删除策略        │          │ • 策略模板        │           │
│   └────────┬─────────┘          └──────────────────┘           │
│            │                                                    │
│            ▼                                                    │
│   ┌──────────────────────────────────────────┐                 │
│   │         统一后端 API                      │                 │
│   │  /api/v1/config/strategies/*              │                 │
│   └──────────────────────────────────────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**设计原则**:
- 配置页面提供**简单管理**（列表、开关、基础编辑）
- 策略工作台提供**高级构建**（可视化、复杂链、模板）
- 两者操作同一数据源，互为冗余入口

### 1.4 导入预览/确认流程（安全设计）

```
┌─────────────────────────────────────────────────────────────────┐
│                    安全导入流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 选择 YAML 文件                                         │
│     │                                                           │
│     ▼                                                           │
│  Step 2: POST /api/v1/config/import/preview                     │
│     │  {                                                       │
│     │    "yaml_content": "...",                                │
│     │    "filename": "backup_20260404.yaml"                    │
│     │  }                                                       │
│     ▼                                                           │
│  Step 3: 返回预览结果                                           │
│     │  {                                                       │
│     │    "valid": true,                                        │
│     │    "preview_token": "uuid-xxx",                          │
│     │    "expires_at": "2026-04-04T21:00:00Z",                 │
│     │    "summary": {                                          │
│     │      "strategies": {"added": 2, "modified": 1, "deleted": 0},
│     │      "risk": {"modified": true},                         │
│     │      "symbols": {"added": 3},                            │
│     │      "notifications": {"added": 1}                       │
│     │    },                                                    │
│     │    "conflicts": [],                                      │
│     │    "requires_restart": false                             │
│     │  }                                                       │
│     │                                                           │
│     ▼                                                           │
│  Step 4: 用户确认（前端展示变更对比）                            │
│     │                                                           │
│     ▼                                                           │
│  Step 5: POST /api/v1/config/import/confirm                     │
│     │  {                                                       │
│     │    "preview_token": "uuid-xxx"                           │
│     │  }                                                       │
│     ▼                                                           │
│  Step 6: 实际写入数据库 + 创建快照 + 热重载                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**安全设计**:
- `preview_token` 有效期 5 分钟
- 预览不修改任何数据
- 确认时需携带 token，防止重复提交
- 自动创建快照，支持回滚

---

## 2. 前端配置页面功能模块

### 2.1 页面结构 (web-front/src/pages/Config.tsx)

```
Config.tsx
├── Header
│   └── 配置标题 + 最后更新时间
├── Tabs
│   ├── 风控配置 (RiskTab)
│   ├── 系统配置 (SystemTab)
│   ├── 策略管理 (StrategiesTab)  ⭐ 新增
│   ├── 币池管理 (SymbolsTab)
│   ├── 通知配置 (NotificationsTab)
│   └── 备份恢复 (BackupTab)
└── Footer
    └── 保存按钮 / 重启提示
```

### 2.2 策略管理模块详细设计

```typescript
// 策略列表组件
interface StrategiesTabProps {
  strategies: StrategyConfig[];
  onToggle: (id: string, enabled: boolean) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
  onCreate: () => void;
}

// 策略配置表单
interface StrategyFormProps {
  strategy?: StrategyConfig;  // 为空表示创建
  onSave: (values: StrategyFormValues) => void;
  onCancel: () => void;
}

// 基础策略参数（配置页面支持）
interface StrategyFormValues {
  name: string;
  description?: string;
  enabled: boolean;
  trigger: {
    type: 'pinbar' | 'engulfing' | 'doji';
    params: Record<string, number>;
  };
  filters: {
    type: 'ema' | 'mtf' | 'atr';
    enabled: boolean;
    params: Record<string, number>;
  }[];
  symbols: string[];
  timeframes: string[];
}
```

### 2.3 各 Tab 功能对照表

| Tab | 功能 | API 端点 | 热重载 |
|-----|------|---------|--------|
| 风控配置 | 编辑单笔最大损失、总敞口、杠杆、冷却时间 | `/api/v1/config/risk` | ✅ 立即生效 |
| 系统配置 | 编辑历史 K 线数、队列参数、EMA 周期 | `/api/v1/config/system` | ⚠️ 提示重启 |
| 策略管理 | 策略列表、启用/禁用、基础编辑、删除 | `/api/v1/config/strategies/*` | ✅ 立即生效 |
| 币池管理 | 币种列表、启用/禁用、添加/删除 | `/api/v1/config/symbols/*` | ✅ 立即生效 |
| 通知配置 | Webhook 配置、测试、启用/禁用 | `/api/v1/config/notifications/*` | ✅ 立即生效 |
| 备份恢复 | YAML 导出、导入预览/确认、快照管理 | `/api/v1/config/export`<br>`/api/v1/config/import/*`<br>`/api/v1/config/snapshots/*` | - |

---

## 3. 数据库表结构（已确认）

### 3.1 表清单（7 张表，无数据迁移）

```
✅ strategies          - 策略配置（配置页面管理）
✅ risk_configs        - 风控配置
✅ system_configs      - 系统配置（需重启）
✅ symbols             - 币池配置
✅ notifications       - 通知配置
✅ config_snapshots    - 配置快照
✅ config_history      - 配置历史
```

### 3.2 初始化策略

**确认**: 不考虑历史数据迁移，使用空数据库初始化

```python
# scripts/init_config_db.py
async def initialize_empty_database(db: Database):
    """
    初始化空数据库，填充默认值
    """
    # 1. 创建表结构
    await db.execute(SCHEMA_SQL)
    
    # 2. 插入系统默认配置
    await db.execute("""
        INSERT INTO system_configs (id, core_symbols, ema_period, mtf_ema_period, ...)
        VALUES ('global', '["BTC/USDT:USDT", ...]', 60, 60, ...)
    """)
    
    # 3. 插入默认风控配置
    await db.execute("""
        INSERT INTO risk_configs (id, max_loss_percent, max_leverage, ...)
        VALUES ('global', 0.01, 10, ...)
    """)
    
    # 4. 插入核心币种
    await db.execute("""
        INSERT INTO symbols (symbol, is_core, is_active) VALUES
        ('BTC/USDT:USDT', TRUE, TRUE),
        ('ETH/USDT:USDT', TRUE, TRUE),
        ('SOL/USDT:USDT', TRUE, TRUE),
        ('BNB/USDT:USDT', TRUE, TRUE)
    """)
    
    # 5. strategies / notifications 为空表（用户后续配置）
    
    logger.info("Empty database initialized with defaults")
```

---

## 4. 开发任务分解

### 4.1 后端开发任务

| 任务 | 内容 | 预计工时 | 依赖 |
|------|------|---------|------|
| **BACKEND-1** | 创建 7 张数据库表（DDL） | 1h | 无 |
| **BACKEND-2** | 实现 Config Repository 层 | 2h | BACKEND-1 |
| **BACKEND-3** | 重构 ConfigManager（数据库驱动） | 2h | BACKEND-2 |
| **BACKEND-4** | 实现策略管理 API 端点 | 1.5h | BACKEND-3 |
| **BACKEND-5** | 实现导入预览/确认 API | 1.5h | BACKEND-3 |
| **BACKEND-6** | 热重载 Observer 机制 | 1h | BACKEND-3 |
| **BACKEND-7** | 单元测试 | 2h | BACKEND-1~6 |

### 4.2 前端开发任务

| 任务 | 内容 | 预计工时 | 依赖 |
|------|------|---------|------|
| **FRONTEND-1** | 策略管理 Tab 组件 | 2h | API 就绪 |
| **FRONTEND-2** | 策略列表 + 启用/禁用 | 1.5h | FRONTEND-1 |
| **FRONTEND-3** | 策略创建/编辑表单 | 2h | FRONTEND-1 |
| **FRONTEND-4** | 导入预览/确认流程 | 1.5h | API 就绪 |
| **FRONTEND-5** | 重启提示组件 | 0.5h | 无 |
| **FRONTEND-6** | 集成测试 | 1h | FRONTEND-1~5 |

### 4.3 任务依赖图

```
BACKEND-1 (DDL)
    │
    ▼
BACKEND-2 (Repository)
    │
    ▼
BACKEND-3 (ConfigManager) ───────┐
    │                            │
    ├──► BACKEND-4 (策略 API)    │
    │                            │
    ├──► BACKEND-5 (导入 API)    │
    │                            │
    └──► BACKEND-6 (热重载)      │
         │                       │
         ▼                       ▼
    BACKEND-7 (测试) ◄──────── FRONTEND-1~6 (前端)
```

---

## 5. 最终确认清单

### 5.1 架构决策确认 ✅

- [x] **API 路径版本**: 统一为 `/api/v1/config/*`
- [x] **导入预览**: 需要 preview/confirm 流程（安全）
- [x] **策略管理**: 配置页面管理策略，与策略工作台冗余
- [x] **数据迁移**: 不考虑历史数据，空数据库初始化

### 5.2 验收标准（18 项）

**功能验收**:
- [ ] AC-1: ConfigManager 从 SQLite 数据库读取配置
- [ ] AC-2: 7 张配置表创建成功，包含默认数据
- [ ] AC-3: 业务配置热重载立即生效
- [ ] AC-4: 系统配置变更标记 restart_required
- [ ] AC-5: YAML 导入/导出功能正常（含预览/确认）
- [ ] AC-6: 配置快照创建和回滚功能正常
- [ ] AC-7: 配置历史记录自动创建
- [ ] AC-8: **策略管理在配置页面可用**

**性能验收**:
- [ ] AC-9: 配置加载延迟 < 100ms
- [ ] AC-10: 配置更新延迟 < 500ms
- [ ] AC-11: 热重载通知延迟 < 50ms

**兼容性验收**:
- [ ] AC-12: SignalPipeline 无需改动
- [ ] AC-13: API 端点符合设计
- [ ] AC-14: 前端配置页面功能完整

**质量验收**:
- [ ] AC-15: 单元测试覆盖率 ≥ 80%
- [ ] AC-16: 通过 pytest
- [ ] AC-17: 通过 mypy
- [ ] AC-18: 通过 black 格式化

---

**文档状态**: ✅ 已确认 (Confirmed)

**下一步**: 进入开发阶段，按任务分解并行执行前后端开发。

**预估总工时**: 后端 11h + 前端 8.5h = **19.5h**
