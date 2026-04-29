# API 契约不匹配修复方案

> **日期**: 2026-04-10
> **发现者**: 前端 E2E 测试 + 手动 API 验证
> **方案设计师**: 架构师 Agent

---

## 一、问题根因

系统中存在**两套策略管理 API**，前端使用了错误的那套。

| 维度 | 旧 API (`api.py`) | 新 API (`api_v1_config.py`) |
|------|-------------------|----------------------------|
| 路径前缀 | `/api/strategies` | `/api/v1/config/strategies` |
| 设计目的 | 策略模板（嵌套 `StrategyDefinition`） | 策略实例（扁平表单结构） |
| 创建请求体 | `{name, strategy: StrategyDefinition}` | `{name, trigger_config, filter_configs, ...}` |
| toggle 端点 | 不存在 | `POST /strategies/{id}/toggle` |
| 认证 | 无 | admin 依赖检查 |
| 返回格式 | `{strategies: [...]}` | 直接返回 `[...]` |

**前端现状**：数据结构匹配新 API（扁平结构），但 baseURL 指向了旧 API。

---

## 二、问题清单

| # | 功能 | 前端请求 | 后端实际 | 严重度 |
|---|------|---------|---------|--------|
| 1 | 策略创建 | `POST /api/strategies`（扁平结构） | 需嵌套 `StrategyDefinition` 对象 | **P0** |
| 2 | 策略更新 | `PUT /api/strategies/:id`（扁平结构） | 需嵌套 `StrategyDefinition` 对象 | **P0** |
| 3 | 策略列表 | `GET /api/strategies` | 返回 `{strategies:[...]}`，前端有降级 | 🟢 可用 |
| 4 | 策略启用/禁用 | `POST /api/strategies/:id/toggle` | **端点不存在**（仅在新 API 有） | **P0** |
| 5 | 系统参数更新 | `PUT /api/strategy/params`（嵌套结构） | 期望 `{pinbar, engulfing, ema, mtf, atr}` | **P0** |
| 6 | 系统配置读取 | `GET /api/strategy/params` | 返回格式与前端 `SystemConfigResponse` 不匹配 | 🟡 |
| 7 | 系统配置写入 | `PUT /api/config/system`（嵌套结构） | 期望 `{queue_batch_size, warmup_history_bars, ...}` | **P0** |

---

## 三、方案对比

### 方案 A：前端路由迁移（推荐）

前端 `baseURL` 从 `/api` → `/api/v1/config`，后端补充系统配置端点。

| 维度 | 评分 | 说明 |
|------|------|------|
| 复杂度 | 低 | 前端改 baseURL + 后端新增 2 个端点 |
| 维护成本 | 低 | 单一数据流 |
| 风险 | 低 | 改动集中在 `config.ts` + `api_v1_config.py` |

### 方案 B：旧 API 新增转换器

在 `api.py` 新增接受扁平结构的端点。维护两套策略 API，成本高。

### 方案 C：中间层转换（BFF）

单体应用过度设计，不推荐。

### 结论：方案 A 最优

---

## 四、改动清单

### Phase 1：策略 CRUD + Toggle（P0）

| # | 改动 | 文件 | 工时 |
|---|------|------|------|
| 1 | `config.ts` baseURL 从 `/api` → `/api/v1/config` | `gemimi-web-front/src/api/config.ts` | 5 min |
| 2 | 风险配置路径 `/config` → `/risk` | `gemimi-web-front/src/api/config.ts` | 2 min |
| 3 | 策略列表降级逻辑修复 | `gemimi-web-front/src/pages/config/StrategyConfig.tsx` | 2 min |
| 4 | admin 认证确认/bypass | `src/interfaces/api_v1_config.py` | 15 min |

### Phase 2：系统配置（P0）

| # | 改动 | 文件 | 工时 |
|---|------|------|------|
| 5 | 新增 `GET/PUT /api/v1/config/system` 端点 | `src/interfaces/api_v1_config.py` | 90 min |
| 6 | `SystemSettings.tsx` 数据适配 | `gemimi-web-front/src/pages/config/SystemSettings.tsx` | 15 min |

### Phase 3：验证

| # | 改动 | 工时 |
|---|------|------|
| 7 | 策略创建/更新/删除/列表/切换 全流程测试 | 30 min |
| 8 | 系统配置读取/更新 全流程测试 | 20 min |
| 9 | 确认旧 `/api/strategies` 端点不受影响 | 10 min |

**总工时**：约 3 小时

---

## 五、保留不动的旧端点

| 旧端点 | 使用者 |
|--------|--------|
| `GET /api/strategies` | 回测沙箱 |
| `GET /api/strategies/meta` | 动态表单元数据 |
| `GET /api/strategies/{id}` | 回测详情 |
| `POST /api/strategies/preview` | 策略预览 |
| `POST /api/strategies/{id}/apply` | 策略下发 |
| `GET/PUT /api/config` | 完整配置导入导出 |
| `GET/PUT /api/strategy/params` | 旧版策略参数 |

---

## 六、关键风险

1. **`check_admin_permission`**：本地开发环境是否有 bypass 机制需确认
2. **`/config` 端点**：切换 baseURL 后，`getRiskConfig` 路径变成 `/api/v1/config/config`（错误），需改为 `/risk`
3. **系统配置 hot-reload**：新端点需确保通知机制正确

---

*方案待确认后开始实施*
