# 进度日志

> **说明**: 仅保留最近 3 天详细日志，更早的已归档至 `archive/completed-tasks/`。
> **最后更新**: 2026-04-10 下午

---

## 2026-04-10 下午 前端 Bug 修复 + API 契约分析报告

### 前端 Bug 修复（3 个）
1. **StrategyConfig.tsx 白屏**：`SimpleImage` 组件 const 不提升，从文件底部移到顶部
2. **Layout.tsx 侧边栏崩溃**：`colorClasses` 缺少 `cyan` 和 `orange` 颜色映射
3. **CSS 500 错误**：Vite 缓存损坏 + Tailwind 扫描到 `playwright-report/` 目录

**提交**: `f5b9070`
**验证**: Playwright E2E 15/15 全部通过

### API 契约不匹配分析
- 发现 7 个前后端接口不匹配问题（5 个 P0，1 个 P1，1 个已兼容）
- 根因：两套策略管理 API 并存，前端 baseURL 指向了旧 API
- 修复方案文档：`docs/reviews/2026-04-10-api-contract-mismatch-fix-plan.md`
- 推荐方案 A：前端 baseURL `/api` → `/api/v1/config`，后端补充系统配置端点
- 预估工时：约 3 小时

### 待办
| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 5 | API 契约对齐修复（方案 A） | P0 | ✅ 已完成 |
| 4 | Testnet 模拟盘验证 | P1 | 🔓 可启动 |

---

## 2026-04-10 前端 SystemSettings 数据适配（API 契约对齐）

### 修改内容
**目标**：将系统配置 API 从旧的 `/api/v1/config/strategy/params` 迁移到新的 `/api/v1/config/system`

**文件变更**：
1. `web-front/src/api/config.ts`
   - `SystemConfigResponse` 类型：新增 `restart_required`、`id`、`updated_at` 字段
   - `getSystemConfig()`: `GET /strategy/params` → `GET /system`
   - `updateSystemConfig()`: `PUT /strategy/params`（带 wrapper） → `PUT /system`（直接返回）
   - 更新注释：系统配置端点状态从"待后端补充"改为"GET/PUT"

2. `web-front/src/pages/config/SystemSettings.tsx`
   - `requires_restart` → `restart_required`（对齐后端字段名）

3. `web-front/src/pages/config/SystemTab.tsx`
   - `requires_restart` → `restart_required`（对齐后端字段名）

4. `web-front/src/pages/config/__tests__/SystemTab.test.tsx`
   - Mock 数据结构更新：从 `{ requires_restart, config: ... }` 改为 `{ restart_required, ...spread }`

### 验证结果
- TypeScript 编译：0 个新增错误（原有错误不受影响）
- 生产构建：成功（`npm run build` 通过）
- `requires_restart` 相关错误：0 个（已全部修复）

### 后端对接确认
- `GET /api/v1/config/system` → 返回 `SystemConfigResponse`（含 `restart_required` 字段）
- `PUT /api/v1/config/system` → 接受 `SystemConfigUpdateRequest`（嵌套结构：`ema.period`, `signal_pipeline.cooldown_seconds.queue.*`）

---

## 2026-04-10 API 契约对齐 - Phase 2 后端系统配置端点完成

**提交**: `2c91cef`

### 改动内容
1. **`src/interfaces/api_v1_config.py`**:
   - 新增嵌套 Pydantic 模型：`EmaConfig`, `QueueConfig`, `SignalPipelineConfig`, `WarmupConfig`
   - `SystemConfigResponse` 重构为嵌套格式：`{ema: {period}, signal_pipeline: {cooldown_seconds, queue}, warmup}`
   - `SystemConfigUpdateRequest` 重构为嵌套格式，匹配前端 `SystemConfigUpdateRequest`
   - 新增 `_flat_to_nested()` 转换函数：DB 扁平格式 → 前端嵌套格式
   - 新增 `_nested_to_flat()` 转换函数：前端嵌套格式 → DB 扁平格式
   - `check_admin_permission()` 新增 `DISABLE_AUTH` 环境变量 bypass 机制（本地开发）
   - `update_system_config()` 新增热重载通知 `notify_hot_reload("system")`

2. **`tests/unit/test_system_config_api.py`** (新增 39 个测试):
   - 嵌套模型测试：`EmaConfig`, `QueueConfig`, `SignalPipelineConfig`, `WarmupConfig`
   - `SystemConfigResponse` / `SystemConfigUpdateRequest` 嵌套格式验证
   - `_flat_to_nested` / `_nested_to_flat` 转换函数测试
   - `DISABLE_AUTH` bypass 机制测试（true/TRUE/1/yes 均支持）
   - GET /system 端点测试（正常/默认/503）
   - PUT /system 端点测试（完整/部分/空/503/500）

3. **`tests/unit/test_config_import_export.py`**:
   - 修复 4 个测试使用新的嵌套格式
   - GET /system 断言从 `data["ema_period"]` 改为 `data["ema"]["period"]`

### 验证结果
- 新增 39 个测试全部通过
- 135 个配置相关测试全部通过
- 98 个权限/快照/边界测试全部通过
- 无回归（旧 `api.py` 中的模型不受影响）

### API 契约对齐状态
| 端点 | 前端格式 | 后端格式 | 状态 |
|------|---------|---------|------|
| GET /api/v1/config/system | `{ema: {period}, signal_pipeline: {...}}` | ✅ 已对齐 | ✅ 完成 |
| PUT /api/v1/config/system | `{ema: {period}, signal_pipeline: {...}}` | ✅ 已对齐 | ✅ 完成 |
| Admin 认证 | 需要 X-User-Role: admin | ✅ 支持 DISABLE_AUTH bypass | ✅ 完成 |
| 热重载通知 | 期望收到通知 | ✅ 已添加 notify_hot_reload | ✅ 完成 |

### 当前待办
| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 7 | API 契约对齐 - Phase 3 端到端验证 | P0 | 待执行 |
| 4 | Testnet 模拟盘验证 | P1 | 🔓 可启动 |

---

## 2026-04-10 文档精简与归档（收工）

**整理结果**:
- task_plan.md: 364→62行, progress.md: 5,140→92行, findings.md: 5,975→122行
- 归档 36 个无效文件（handoff/重复/过渡性/临时验证报告）
- 整理 reports/reviews/designs/arch/v3 等散落文档
- 保留需确认的 18 个归档文件（计划/报告/设计文档）

**Git 提交**: `b3b9cb6`, `e2835fd`, `f293013`, `089ce73`

---

*最后更新：2026-04-10 16:30 - API 契约对齐 Phase 2 后端系统配置完成*
