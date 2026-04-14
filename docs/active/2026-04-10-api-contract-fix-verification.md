# API 契约对齐修复 - 验证报告

> **日期**: 2026-04-10
> **修复方案**: 方案 A（前端 baseURL 迁移）
> **测试执行**: QA Agent + 集成测试套件

---

## 测试结果总览

| 指标 | 数值 |
|------|------|
| **总测试数** | 199 |
| **通过** | 198 ✅ |
| **失败** | 1 ⚠️ |
| **通过率** | 99.5% |

### 各套件明细

| 测试套件 | 通过 | 失败 | 说明 |
|----------|------|------|------|
| `tests/integration/test_api_v1_config.py` | 41 | 1 | 策略 CRUD + 系统配置集成测试 |
| `tests/unit/test_system_config_api.py` | 39 | 0 | 系统配置 API 单元测试（新增） |
| `tests/unit/test_api_v1_config_permissions.py` | 48 | 0 | 权限验证测试 |
| `tests/unit/test_config_import_export.py` | 36 | 0 | 配置导入导出测试 |
| `tests/unit/test_config_api.py` | 20 | 0 | 配置 API 基础测试 |
| `tests/e2e/test_config_import_export_e2e.py` | 15 | 0 | E2E 配置流程测试 |

---

## 关键路径验证

| 路径 | 状态 | 详情 |
|------|------|------|
| 策略创建 `POST /api/v1/config/strategies` | ✅ | 返回 201 |
| 策略更新 `PUT /api/v1/config/strategies/{id}` | ✅ | 返回 200 |
| 策略删除 `DELETE /api/v1/config/strategies/{id}` | ✅ | 返回 200 |
| 策略列表 `GET /api/v1/config/strategies` | ✅ | 返回数组 |
| 策略切换 `POST /api/v1/config/strategies/{id}/toggle` | ✅ | 返回 200 |
| 系统配置读取 `GET /api/v1/config/system` | ✅ | 返回嵌套格式 `{ema: {period}}` |
| 系统配置更新 `PUT /api/v1/config/system` | ✅ | 接受嵌套格式，`restart_required=true` |
| 旧 `/api/strategies` 端点 | ✅ | 零修改，不受影响 |
| 权限验证（无认证→401，有 admin→200） | ✅ | 48/48 通过 |

---

## ⚠️ 已知 P1 Bug

### Decimal 类型绑定 SQLite 失败

| 维度 | 内容 |
|------|------|
| **文件** | `src/infrastructure/repositories/config_repositories.py:596` |
| **根因** | `_nested_to_flat()` 将 `queue_flush_interval` 转为 `Decimal`，SQLite `aiosqlite.execute()` 不支持 Decimal 参数绑定 |
| **触发条件** | `PUT /api/v1/config/system` 包含 `signal_pipeline.queue` 参数时 |
| **影响范围** | 系统配置更新队列参数时报错 |
| **修复建议** | 在 repository `update()` 中将 Decimal 转为 float，或 `_nested_to_flat()` 对 `queue_flush_interval` 保持 float |
| **优先级** | P1（功能可用但队列参数场景会失败） |

---

## 修改文件清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `web-front/src/api/config.ts` | +60/-10 | baseURL 迁移 + 端点更新 |
| `web-front/src/pages/config/StrategyConfig.tsx` | +287/-10 | 降级逻辑简化 |
| `web-front/src/pages/config/AdvancedStrategyForm.tsx` | +23 | 适配新 API |
| `web-front/src/pages/Backtest.tsx` | +132 | 适配新 API |
| `web-front/src/pages/PMSBacktest.tsx` | +131 | 适配新 API |
| `web-front/src/components/strategy/StrategyCard.tsx` | +170 | 适配新 API |
| `src/interfaces/api_v1_config.py` | +18 | 系统配置端点 |
| `src/application/config/config_parser.py` | +10 | 配置解析适配 |
| `tests/integration/test_api_v1_config.py` | +57 | 集成测试适配 |
| `tests/e2e/test_config_import_export_e2e.py` | +12 | E2E 测试适配 |

---

## Git 提交

| Commit | 说明 |
|--------|------|
| `a6a1ef1` | fix: API 契约对齐修复（方案 A）- 前后端接口统一 |
| `2c91cef` | feat(api): align system config endpoints with frontend contract |
| `7e70d2a` | fix: 前端 SystemSettings 数据适配新 /api/v1/config/system 端点 |
| `9df70eb` | fix: 前端 API baseURL 迁移至 /api/v1/config |

---

*报告生成：2026-04-10 15:30*
