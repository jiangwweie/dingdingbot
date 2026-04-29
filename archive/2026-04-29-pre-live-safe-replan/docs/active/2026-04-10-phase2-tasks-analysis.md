# Phase 2 Tasks 架构分析: BackupTab / SystemTab / StrategyForm / DB Pool

> 日期: 2026-04-10
> 优先级: P0 (Task 9) + P1 (Task 10, 11, 12)
> 作者: 架构师

---

## 目录

1. [现状分析](#1-现状分析)
2. [技术方案](#2-技术方案)
3. [推荐方案](#3-推荐方案)
4. [接口契约表](#4-接口契约表)
5. [关联影响](#5-关联影响)
6. [风险点](#6-风险点)
7. [文件改动清单](#7-文件改动清单)

---

## 1. 现状分析

### 1.1 Task 9: BackupTab 导入/导出修复 (P0)

**当前代码位置**: `/Users/jiangwei/Documents/final/gemimi-web-front/src/pages/config/BackupTab.tsx`

**问题诊断**:

1. **导出路径错误** (第 131 行): 使用 `fetch('/api/config/export')` 旧路径。
   - 正确路径: `POST /api/v1/config/export` (见 `api_v1_config.py:1609`)

2. **导入路径错误** (第 107 行): 使用 `fetch('/api/config/import')` 旧路径。
   - 正确流程应为两步: `POST /api/v1/config/import/preview` + `POST /api/v1/config/import/confirm`

3. **预览数据结构完全不匹配** (第 89-97 行): 前端在本地解析 YAML 构建一个假的 `ImportPreview` 对象，其字段结构 (`changes: {added, modified, removed}`) 与后端 `ImportPreviewResult` 模型 (`summary: {strategies, risk, symbols, notifications}`, `preview_data`, `valid`, `preview_token`, `conflicts`, `requires_restart`) 完全不兼容。
   - 前端自己构建的 `preview_token: 'local'` 硬编码字符串，后续 `handleConfirmImport` 时无法传递给后端。

4. **确认导入直接 POST 文件**: `handleConfirmImport` (第 100-128 行) 构建 `FormData` 并 POST 到 `/api/config/import`，但后端 `confirm_import` 端点期望的是 `{"preview_token": "..."}` JSON 格式，且完全不支持文件上传。

5. **UI 渲染使用不存在的字段**: `renderPreview()` 中访问 `previewData.summary.strategies.added` 等字段，但前端构建的预览数据使用的是 `previewData.changes.modified` (一个数组)，字段名和数据类型全部错位。

**影响**: BackupTab 的导入/导出功能完全不可用，点击导出/导入均会返回 404 或 400 错误。

### 1.2 Task 10: 合并两个重复的 SystemTab 组件 (P1)

**当前代码位置**:
- `/Users/jiangwei/Documents/final/gemimi-web-front/src/pages/config/SystemTab.tsx` (336 行)
- `/Users/jiangwei/Documents/final/gemimi-web-front/src/pages/config/SystemSettings.tsx` (521 行)

**问题诊断**:

1. **功能重叠**: 两个组件都做同一件事 -- 展示和编辑系统配置（EMA、信号管道、预热、ATR 等），调用相同的 API (`configApi.getSystemConfig()` / `configApi.updateSystemConfig()`)。

2. **使用场景不同**:
   - `SystemTab` 被 `ConfigProfiles.tsx` 内部使用，作为 Tab 页嵌入
   - `SystemSettings` 被 `App.tsx` 路由到 `/config/system`，作为独立页面

3. **差异对比**:
   - `SystemSettings` 功能更全: 包含 Collapse 折叠面板、表单验证范围更精细、右侧快捷入口 (Profile/Backup/Snapshots)、小时格式化显示冷却时间
   - `SystemTab` 缺少高级功能: 所有字段平铺展示、无 Collapse、无快捷入口、表单验证范围较宽松
   - `SystemTab` 默认值有差异: `ema_period` 默认 20，`atr_min_ratio` 默认 1.5；`SystemSettings` 默认 60 和 0.5

4. **测试文件**: `gemimi-web-front/src/pages/config/__tests__/SystemTab.test.tsx` 仅针对 `SystemTab` 有 564 行测试。

**影响**: 维护两套代码容易导致配置行为不一致，用户在不同入口看到的默认值和验证范围可能不同。

### 1.3 Task 11: StrategyForm 触发器参数表单补全 (P1)

**当前代码位置**: `/Users/jiangwei/Documents/final/gemimi-web-front/src/pages/config/StrategyForm.tsx`

**问题诊断**:

1. **硬编码空对象** (第 108 行): `trigger_config.params: {}` 永远为空，带有 `TODO: 添加触发器参数配置表单` 注释。

2. **无触发器参数表单 UI**: 表单只有 `trigger_type` 下拉选择器，用户选择触发器类型后没有地方配置该类型的参数（如 pinbar 的 `min_wick_ratio`, `max_body_ratio`, `body_position_tolerance` 等）。

3. **过滤器配置也是 TODO** (第 109 行): `filter_configs: []` 也是硬编码空数组。

4. **后端默认参数参考** (见 `config_parser.py` `create_default_core_config`):
   ```python
   PinbarDefaults(
       min_wick_ratio=Decimal("0.6"),
       max_body_ratio=Decimal("0.3"),
       body_position_tolerance=Decimal("0.1"),
   )
   ```

5. **编辑模式未回填 params**: `useEffect` 中仅回填了 `trigger_type`，没有回填 `trigger_config.params`。

**影响**: 用户创建/编辑策略时无法自定义触发器参数，所有策略都使用后端默认参数值，丧失了配置灵活性。

### 1.4 Task 12: 共享 DB 连接池 (P1)

**当前代码位置**: `/Users/jiangwei/Documents/final/src/infrastructure/repositories/config_repositories.py` 及其他 14 处独立连接。

**问题诊断**:

1. **ConfigDatabaseManager 名不副实**: `ConfigDatabaseManager` (第 1789 行) 虽然创建了 `_shared_db` 连接，但向各 Repository 传入的是 `db_path` 字符串而非连接对象。每个 Repository 在 `initialize()` 中再次调用 `aiosqlite.connect(self.db_path)` 创建自己的独立连接。

2. **全局统计**: `grep aiosqlite.connect` 发现 **17 处独立连接创建**，分布在:
   - `src/infrastructure/repositories/config_repositories.py`: 8 处 (StrategyConfigRepository, RiskConfigRepository, SystemConfigRepository, SymbolConfigRepository, NotificationConfigRepository, ConfigHistoryRepository, ConfigSnapshotRepositoryExtended, 及 ConfigDatabaseManager 的 _shared_db)
   - `src/infrastructure/backtest_repository.py`: 1 处
   - `src/infrastructure/signal_repository.py`: 1 处
   - `src/infrastructure/config_snapshot_repository.py`: 1 处
   - `src/infrastructure/config_profile_repository.py`: 1 处
   - `src/infrastructure/reconciliation_repository.py`: 1 处
   - `src/infrastructure/config_entry_repository.py`: 1 处
   - `src/infrastructure/order_repository.py`: 1 处
   - `src/infrastructure/config/config_repository.py`: 1 处
   - `src/application/config_manager.py`: 1 处
   - `src/application/strategy_optimizer.py`: 1 处

3. **SQLite 虽支持多连接但效率低**: 每个独立连接意味着独立的 WAL 文件锁、独立的缓存，且在 WAL 模式下多个写连接可能产生锁竞争。

4. **database.py 的 SQLAlchemy 连接与 aiosqlite 连接并存**: `database.py` 使用 SQLAlchemy 异步引擎，而其他 Repository 直接使用 `aiosqlite`，两套体系互不相通。

**影响**: 高并发场景下可能出现锁竞争、内存浪费、连接泄漏风险；且没有统一的连接生命周期管理。

---

## 2. 技术方案

### 2.1 Task 9: BackupTab 导入/导出修复

#### 方案 A: 完全改用 configApi + 正确的后端 API 路径

**实现思路**:
- 导出: 调用 `configApi.exportConfig()` (需要在 `config.ts` 中新增) -> 后端 `POST /api/v1/config/export` -> 接收 `{yaml_content, filename}` -> 触发浏览器下载
- 预览: 将 YAML 内容通过 `POST /api/v1/config/import/preview` 发送到后端 -> 接收完整 `ImportPreviewResult` -> 渲染变更摘要
- 确认: 将后端返回的 `preview_token` 通过 `POST /api/v1/config/import/confirm` 发送 -> 完成导入

**优点**:
- 前后端 API 契约清晰，与后端 `ImportPreviewResult` / `ExportResponse` 模型完全对齐
- 预览由后端执行，可以检测与当前配置的冲突（重复策略名等）
- 支持两步确认流程，用户体验一致

**缺点**:
- 需要额外网络请求（预览 + 确认）
- 需要在 `config.ts` 中新增 `exportConfig`, `previewImport`, `confirmImport` 三个 API 方法

#### 方案 B: 保留前端 YAML 解析预览 + 修正 API 路径

**实现思路**:
- 保留前端 `js-yaml` 解析做简单的本地预览
- 仅在确认导入时调用后端 API
- 修正所有 API 路径为 `/api/v1/config/*`

**优点**:
- 预览无需网络请求，响应更快
- 改动量较小

**缺点**:
- 前端无法检测冲突（如重复策略名），预览准确性低
- 与后端 `import/preview` + `import/confirm` 的两步安全流程设计理念不一致
- 前端构建的预览数据结构与后端 `ImportPreview` 类型无法复用

#### 方案对比

| 维度 | 方案 A (推荐) | 方案 B |
|------|-------------|--------|
| 数据准确性 | 高（后端检测冲突） | 低（前端简单 diff） |
| 与后端一致性 | 完全对齐 | 部分对齐 |
| 网络请求 | 3 次（导出1+预览1+确认1） | 2 次（导出1+确认1） |
| 实现复杂度 | 中等 | 低 |
| 可维护性 | 高（前后端共享类型） | 中 |

### 2.2 Task 10: 合并两个重复的 SystemTab 组件

#### 方案 A: 保留 SystemSettings.tsx，删除 SystemTab.tsx

**实现思路**:
- 将 `ConfigProfiles.tsx` 中的 `<SystemTab />` 替换为 `<SystemSettings />`
- 将 `SystemSettings` 改造为既可作页面也可作嵌入组件（可选 `showHeader` prop 控制是否显示页面头部）
- 删除 `SystemTab.tsx`
- 更新测试文件引用

**优点**:
- 单一真相源，消除不一致
- 功能更完整的版本作为标准

**缺点**:
- `SystemSettings` 当前有页面头部、右侧快捷入口等布局，嵌入 `ConfigProfiles` 时需要条件渲染
- 需要改造 `SystemSettings` 组件使其兼容两种使用场景

#### 方案 B: 提取共享逻辑为 Hook/子组件

**实现思路**:
- 提取 `useSystemConfig()` hook（加载、保存、重置逻辑）
- `SystemTab` 和 `SystemSettings` 各自保留 UI 布局，但共享数据和操作逻辑
- 统一默认值和验证范围

**优点**:
- 两个入口可以保持不同的 UI 风格
- 风险较低，渐进式重构

**缺点**:
- 代码量不减少，仅提取逻辑
- 维护成本仍然较高（两套 UI 需要同步更新）

#### 方案 C: SystemTab.tsx 重定向/导出别名

**实现思路**:
- `SystemTab.tsx` 文件改为 `export { default as SystemTab } from './SystemSettings'`
- 保留文件但作为转发模块
- 确保 `ConfigProfiles.tsx` 的导入不受影响

**优点**:
- 改动最小，零风险
- 向后兼容

**缺点**:
- `SystemSettings` 的页面级布局（头部、右侧面板）在 `ConfigProfiles` 的 Tab 内显示会不协调
- 需要调整 `SystemSettings` 的样式使其在两种场景下都可用

#### 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| 代码消除 | 完全消除重复 | 无 | 部分 |
| 改动量 | 中等 | 较大 | 最小 |
| 视觉一致性 | 高 | 取决于实现 | 需适配 |
| 风险 | 低 | 中 | 极低 |

### 2.3 Task 11: StrategyForm 触发器参数表单补全

#### 方案 A: 动态参数表单（基于触发器类型渲染不同字段）

**实现思路**:
- 定义触发器参数 Schema 映射:
  ```typescript
  const TRIGGER_PARAM_SCHEMAS = {
    pinbar: [
      { key: 'min_wick_ratio', label: '最小影线比例', type: 'number', min: 0.1, max: 2.0, default: 0.6 },
      { key: 'max_body_ratio', label: '最大实体比例', type: 'number', min: 0.05, max: 1.0, default: 0.3 },
      { key: 'body_position_tolerance', label: '实体位置容差', type: 'number', min: 0, max: 0.5, default: 0.1 },
    ],
    engulfing: [
      { key: 'min_body_ratio', label: '最小实体比例', type: 'number', default: 1.5 },
      { key: 'min_prev_body_ratio', label: '最小前K线实体比例', type: 'number', default: 0.3 },
    ],
    // ... 其他触发器类型
  }
  ```
- 监听 `trigger_type` 变化，动态渲染对应的 `Form.Item`
- 提交时将动态表单值合并到 `trigger_config.params`

**优点**:
- 与后端 `PinbarDefaults` 等模型完全对齐
- 可扩展，新增触发器类型只需添加 schema 定义
- 编辑模式可正确回填参数

**缺点**:
- 需要在前端维护参数定义，与后端可能不同步
- 每个触发器类型需要单独定义字段

#### 方案 B: 从后端动态拉取参数 Schema

**实现思路**:
- 新增后端端点 `GET /api/v1/config/trigger-schemas` 返回各触发器的参数定义
- 前端根据返回的 Schema 动态生成表单
- Schema 可包含字段名、类型、范围、默认值、描述等

**优点**:
- 单一真相源，前后端参数定义完全一致
- 新增触发器类型时前端无需修改

**缺点**:
- 需要新增后端 API 端点
- 增加复杂度，对于当前仅 4 种触发器类型来说可能过度设计

#### 方案 C: JSON 手动输入（简单方案）

**实现思路**:
- 添加一个 JSON 编辑器（如 `<TextArea>` 或 Monaco Editor）
- 用户手动输入 `trigger_config.params` 的 JSON
- 提交时直接发送

**优点**:
- 实现最简单
- 灵活性最高

**缺点**:
- 用户体验差，需要知道参数名称和格式
- 无验证，容易输入错误
- 不符合普通用户的使用习惯

#### 方案对比

| 维度 | 方案 A (推荐) | 方案 B | 方案 C |
|------|-------------|--------|--------|
| 用户体验 | 好 | 好 | 差 |
| 实现复杂度 | 中 | 高 | 低 |
| 前后端一致性 | 需手动对齐 | 自动一致 | 无验证 |
| 可扩展性 | 中 | 高 | 高 |

### 2.4 Task 12: 共享 DB 连接池

#### 方案 A: 注入共享连接到 Repository（推荐）

**实现思路**:
- 创建一个全局 `SQLiteConnectionPool` 类:
  ```python
  class SQLiteConnectionPool:
      _instance: Optional[aiosqlite.Connection] = None

      @classmethod
      async def get_connection(cls, db_path: str) -> aiosqlite.Connection:
          if cls._instance is None:
              cls._instance = await aiosqlite.connect(db_path)
              await cls._instance.execute("PRAGMA journal_mode=WAL")
              await cls._instance.execute("PRAGMA synchronous=NORMAL")
          return cls._instance
  ```
- 修改各 Repository 的构造函数，接受可选的 `connection` 参数:
  ```python
  class StrategyConfigRepository:
      def __init__(self, db_path: str, connection: Optional[aiosqlite.Connection] = None):
          self.db_path = db_path
          self._db = connection  # 注入共享连接
          self._owns_connection = connection is None  # 标记是否自行管理生命周期
  ```
- `initialize()` 中不再调用 `aiosqlite.connect`，而是使用注入的连接
- 保持向后兼容：不传 `connection` 时仍自行创建

**优点**:
- 所有 Repository 共享同一连接，消除锁竞争
- 向后兼容，不影响独立使用 Repository 的场景
- `ConfigDatabaseManager` 可以真正发挥作用

**缺点**:
- 需要修改所有 Repository 的构造函数和 `initialize()` 方法
- 改动面较广（17 处独立连接）

#### 方案 B: 修复 ConfigDatabaseManager 使其真正共享

**实现思路**:
- `ConfigDatabaseManager.initialize()` 创建连接后，将连接对象传入各 Repository
- Repository 修改为接受连接对象而非路径:
  ```python
  self.strategy_repo = StrategyConfigRepository(self._shared_db)
  ```
- Repository 的 `initialize()` 不再创建新连接

**优点**:
- 改动集中在 `ConfigDatabaseManager` 和 Repository 构造函数
- 不影响 `ConfigDatabaseManager` 外的使用场景

**缺点**:
- 仅修复 `ConfigDatabaseManager` 管理的 Repository
- 不解决其他独立 Repository（如 `backtest_repository`, `signal_repository` 等）的问题

#### 方案 C: 使用 SQLAlchemy 统一连接

**实现思路**:
- 逐步将所有 `aiosqlite` 直接操作迁移到 `database.py` 的 SQLAlchemy 异步 Session
- 所有 Repository 使用 `get_db()` 获取 Session

**优点**:
- 统一的 ORM 层，类型安全
- 连接池由 SQLAlchemy 管理

**缺点**:
- 工作量巨大，需要重写所有 Repository
- 风险极高，容易引入回归 bug
- 不适合作为 Phase 2 的修复方案

#### 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| 覆盖范围 | 全部 | 仅 ConfigDB | 全部（需重写） |
| 改动量 | 中 | 小 | 极大 |
| 风险 | 低 | 低 | 高 |
| 向后兼容 | 是 | 是 | 否 |

---

## 3. 推荐方案

### Task 9 (P0): 方案 A -- 完全改用 configApi + 正确的后端 API

**理由**: 后端已有完善的 `export` / `import/preview` / `import/confirm` 三端点，前端只需对齐调用即可。预览由后端执行可以保证数据准确性（冲突检测、与现有配置对比）。前端当前代码的数据结构完全不匹配，修修补补不如彻底重写。

**关键改动**:
1. `config.ts` 新增三个方法: `exportConfig`, `previewImport`, `confirmImport`
2. `BackupTab.tsx` 重写 `handleUpload` -> 调用 `previewImport`
3. `BackupTab.tsx` 重写 `handleConfirmImport` -> 使用 `preview_token` 调用 `confirmImport`
4. `BackupTab.tsx` 重写 `handleExport` -> 调用 `exportConfig` 获取 `yaml_content` 并下载
5. 更新 `ImportPreview` 类型定义以匹配后端 `ImportPreviewResult`

### Task 10 (P1): 方案 A -- 保留 SystemSettings.tsx，删除 SystemTab.tsx

**理由**: 消除重复代码是最根本的解决方式。`SystemSettings` 功能更全、UI 更好。只需对 `SystemSettings` 做少量改造使其可嵌入使用。

**关键改动**:
1. `SystemSettings.tsx` 新增 `variant?: 'page' | 'tab'` prop，`'tab'` 模式隐藏页面头部和右侧面板
2. `ConfigProfiles.tsx` 替换 `<SystemTab />` 为 `<SystemSettings variant="tab" />`
3. 统一两个组件的默认值（使用 `SystemSettings` 的默认值）
4. 删除 `SystemTab.tsx`
5. 将 `SystemTab.test.tsx` 更新为测试 `SystemSettings`

### Task 11 (P1): 方案 A -- 动态参数表单

**理由**: 对于 4 种触发器类型，动态表单是最实用且性价比最高的方案。无需新增后端 API，且用户体验好。未来可平滑迁移到方案 B。

**关键改动**:
1. 新建 `gemimi-web-front/src/components/strategy/triggerSchemas.ts` 定义参数 Schema
2. 新建 `gemimi-web-front/src/components/strategy/TriggerParamsForm.tsx` 动态参数表单组件
3. `StrategyForm.tsx` 集成 `TriggerParamsForm`，回填 `trigger_config.params`
4. 提交时将动态表单值合并到 payload

### Task 12 (P1): 方案 A -- 注入共享连接到 Repository

**理由**: 向后兼容 + 全局覆盖。通过可选的 `connection` 参数实现渐进式迁移，不影响现有独立使用场景。

**关键改动**:
1. 新建 `src/infrastructure/connection_pool.py` 全局连接池
2. 修改各 Repository 构造函数接受可选 `connection` 参数
3. 修改各 Repository `initialize()` 使用注入连接而非自建
4. `ConfigDatabaseManager.initialize()` 传递共享连接给各 Repository

---

## 4. 接口契约表

### 4.1 Task 9: BackupTab 新增前端 API 方法

| 方法名 | 后端端点 | 请求体 | 响应体 | 说明 |
|--------|----------|--------|--------|------|
| `exportConfig(data)` | `POST /api/v1/config/export` | `ExportRequest` (可选, 默认全包含) | `ExportResponse {status, filename, yaml_content, created_at}` | 导出配置为 YAML |
| `previewImport(data)` | `POST /api/v1/config/import/preview` | `{yaml_content: string, filename?: string}` | `ImportPreviewResult {valid, preview_token, summary, conflicts, requires_restart, errors, preview_data}` | 预览导入变更 |
| `confirmImport(data)` | `POST /api/v1/config/import/confirm` | `{preview_token: string}` | `ImportConfirmResponse {status, snapshot_id, message, summary}` | 确认导入 |

### 4.2 后端端点（已有，无需变更）

| 端点 | 方法 | 说明 | 状态 |
|------|------|------|------|
| `/api/v1/config/export` | POST | 导出配置 | 已实现 |
| `/api/v1/config/import/preview` | POST | 预览导入 | 已实现 |
| `/api/v1/config/import/confirm` | POST | 确认导入 | 已实现 |

### 4.3 Task 11: 触发器参数 Schema（前端定义）

| 触发器类型 | 参数名 | 类型 | 默认值 | 范围 |
|-----------|--------|------|--------|------|
| pinbar | `min_wick_ratio` | number | 0.6 | 0.1 - 2.0 |
| pinbar | `max_body_ratio` | number | 0.3 | 0.05 - 1.0 |
| pinbar | `body_position_tolerance` | number | 0.1 | 0 - 0.5 |
| engulfing | `min_body_ratio` | number | 1.5 | 1.0 - 5.0 |
| engulfing | `min_prev_body_ratio` | number | 0.3 | 0.1 - 1.0 |
| doji | `max_body_ratio` | number | 0.1 | 0.01 - 0.3 |
| hammer | `min_wick_ratio` | number | 0.6 | 0.1 - 2.0 |
| hammer | `max_body_ratio` | number | 0.3 | 0.05 - 1.0 |

### 4.4 Task 12: 连接池接口

```python
class SQLiteConnectionPool:
    @classmethod
    async def get_connection(cls, db_path: str) -> aiosqlite.Connection
    @classmethod
    async def close(cls) -> None
```

---

## 5. 关联影响

### Task 9: BackupTab 导入/导出修复

| 受影响文件 | 影响类型 | 说明 |
|-----------|---------|------|
| `gemimi-web-front/src/api/config.ts` | 新增 | 添加 3 个 API 方法和对应类型 |
| `tests/e2e/test_config_import_export_e2e.py` | 无影响 | 测试直接使用后端 API，不依赖前端 |
| `tests/unit/test_config_import_export.py` | 无影响 | 单元测试直接测试后端 |
| `gemimi-web-front/src/pages/config/BackupTab.tsx` | 重写 | 整个组件的数据流需要重写 |

### Task 10: SystemTab 合并

| 受影响文件 | 影响类型 | 说明 |
|-----------|---------|------|
| `gemimi-web-front/src/pages/ConfigProfiles.tsx` | 修改 | 替换 `<SystemTab />` 导入和用法 |
| `gemimi-web-front/src/pages/config/SystemTab.tsx` | 删除 | 文件被删除或改为转发 |
| `gemimi-web-front/src/pages/config/SystemSettings.tsx` | 修改 | 添加 `variant` prop 支持嵌入模式 |
| `gemimi-web-front/src/pages/config/__tests__/SystemTab.test.tsx` | 修改 | 更新引用为 SystemSettings 或合并测试 |

### Task 11: StrategyForm 触发器参数

| 受影响文件 | 影响类型 | 说明 |
|-----------|---------|------|
| `gemimi-web-front/src/pages/config/StrategyForm.tsx` | 修改 | 集成动态参数表单 |
| `gemimi-web-front/src/components/strategy/triggerSchemas.ts` | 新增 | 触发器参数 Schema 定义 |
| `gemimi-web-front/src/components/strategy/TriggerParamsForm.tsx` | 新增 | 动态参数表单组件 |
| `gemimi-web-front/src/api/config.ts` | 无影响 | 接口类型已支持 `params: Record<string, any>` |
| `tests/unit/` (如有 StrategyForm 测试) | 新增 | 需要补充触发器参数测试 |

### Task 12: 共享 DB 连接池

| 受影响文件 | 影响类型 | 说明 |
|-----------|---------|------|
| `src/infrastructure/connection_pool.py` | 新增 | 全局连接池 |
| `src/infrastructure/repositories/config_repositories.py` | 修改 | 7 个 Repository 构造函数和 initialize |
| `src/infrastructure/backtest_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/signal_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_snapshot_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_profile_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_entry_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/order_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/reconciliation_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/application/config_manager.py` | 修改 | 构造函数支持注入连接 |
| `src/application/strategy_optimizer.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config/config_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/interfaces/api_v1_config.py` | 无影响 | 通过依赖注入使用 Repo，不受影响 |
| `tests/unit/test_config_import_export.py` | 可能影响 | 测试使用 `ConfigDatabaseManager`，需确认兼容 |
| `tests/e2e/test_config_import_export_e2e.py` | 可能影响 | 同上 |

---

## 6. 风险点

### Task 9 (P0)
1. **预览数据结构对齐风险**: 后端 `ImportPreviewResult` 的 `preview_data` 字段结构需与前端 `renderPreview()` 的访问路径完全对齐。需仔细核对 `preview_data.strategies` 中的字段名是否与 Table 的 `dataIndex` 匹配。
2. **YAML 导出下载兼容性**: 前端接收 `yaml_content` 字符串后创建 Blob 下载，需确保中文文件名和 UTF-8 编码正确。
3. **preview_token 超时**: TTL 缓存 5 分钟过期，用户在预览页面停留过久后确认导入会失败。需在 UI 上提示 token 有效期或支持重新预览。

### Task 10 (P1)
1. **默认值不一致**: `SystemTab` 和 `SystemSettings` 的默认值不同（`ema_period`: 20 vs 60, `atr_min_ratio`: 1.5 vs 0.5）。删除 `SystemTab` 后用户看到的默认值会变化，需确认以哪个为准（推荐后端 `config_parser.py` 的默认值）。
2. **布局适配**: `SystemSettings` 包含右侧快捷入口面板（Profile/Backup/Snapshots），在 `ConfigProfiles` 的 Tab 内嵌入时需要隐藏，否则会出现重复导航。
3. **测试覆盖**: `SystemTab.test.tsx` 有 564 行测试，合并后需要确保这些测试场景迁移到 `SystemSettings` 的测试中。

### Task 11 (P1)
1. **参数定义同步风险**: 前端维护的 Schema 可能与后端 `PinbarDefaults` 等模型不同步。建议在 Schema 中添加注释标明后端对应位置。
2. **编辑模式回填**: 需确保编辑现有策略时，`trigger_config.params` 中的值能正确回填到动态表单。如果 params 中包含后端新增的未知字段，需有兜底展示策略。
3. **过滤器配置**: 本次只处理触发器参数，过滤器配置仍是 TODO。需在 UI 上明确标注过滤器配置暂不可用。

### Task 12 (P1)
1. **事件循环冲突**: `asyncio.Lock` 必须在正确的事件循环中创建。如果连接池在不同事件循环中被访问（如测试环境），可能产生 `RuntimeError`。
2. **向后兼容**: 不传 `connection` 参数时，Repository 必须仍能独立工作（向后兼容）。确保 `initialize()` 在无注入连接时自行创建连接。
3. **测试环境兼容**: 测试使用的 `ConfigDatabaseManager` 可能因为连接池改动而行为变化。需确保测试中的 `db_manager.initialize()` / `db_manager.close()` 流程不变。
4. **连接泄漏**: 如果 `close()` 未被正确调用（如进程异常退出），共享连接可能泄漏。需在应用 shutdown hook 中确保调用。

---

## 7. 文件改动清单

### Task 9: BackupTab 导入/导出修复

| 文件 | 操作 | 说明 |
|------|------|------|
| `gemimi-web-front/src/api/config.ts` | 修改 | 新增 `exportConfig`, `previewImport`, `confirmImport` 方法及类型定义 |
| `gemimi-web-front/src/pages/config/BackupTab.tsx` | 重写 | 完全重写数据流：handleUpload、handleConfirmImport、handleExport |

### Task 10: 合并 SystemTab 组件

| 文件 | 操作 | 说明 |
|------|------|------|
| `gemimi-web-front/src/pages/config/SystemSettings.tsx` | 修改 | 添加 `variant` prop，支持嵌入模式 |
| `gemimi-web-front/src/pages/ConfigProfiles.tsx` | 修改 | 替换 `<SystemTab />` 为 `<SystemSettings variant="tab" />` |
| `gemimi-web-front/src/pages/config/SystemTab.tsx` | 删除 | 改为转发模块或直接删除 |
| `gemimi-web-front/src/pages/config/__tests__/SystemTab.test.tsx` | 修改 | 更新引用，迁移测试 |

### Task 11: StrategyForm 触发器参数表单

| 文件 | 操作 | 说明 |
|------|------|------|
| `gemimi-web-front/src/components/strategy/triggerSchemas.ts` | 新增 | 触发器参数 Schema 定义 |
| `gemimi-web-front/src/components/strategy/TriggerParamsForm.tsx` | 新增 | 动态参数表单组件 |
| `gemimi-web-front/src/pages/config/StrategyForm.tsx` | 修改 | 集成 TriggerParamsForm，回填 params |

### Task 12: 共享 DB 连接池

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/infrastructure/connection_pool.py` | 新增 | 全局 SQLite 连接池 |
| `src/infrastructure/repositories/config_repositories.py` | 修改 | 所有 Repository 构造函数和 initialize 支持注入连接 |
| `src/infrastructure/backtest_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/signal_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_snapshot_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_profile_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config_entry_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/order_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/reconciliation_repository.py` | 修改 | 构造函数支持注入连接 |
| `src/application/config_manager.py` | 修改 | 构造函数支持注入连接 |
| `src/application/strategy_optimizer.py` | 修改 | 构造函数支持注入连接 |
| `src/infrastructure/config/config_repository.py` | 修改 | 构造函数支持注入连接 |

### 汇总统计

| 操作 | 文件数 |
|------|--------|
| 新增 | 4 |
| 修改 | 15 |
| 删除 | 1 |
| **合计** | **20** |

### 实施顺序建议

1. **Task 9 (P0)** -- 优先修复，因为 BackupTab 完全不可用
2. **Task 10 (P1)** -- 简单且风险低，可快速完成
3. **Task 11 (P1)** -- 功能补全，独立于其他任务
4. **Task 12 (P1)** -- 最后实施，因为改动面最广，需充分测试

> Task 9、10、11 互相独立，可并行开发。Task 12 需在其他任务之后实施以确保不会引入额外的回归风险。
