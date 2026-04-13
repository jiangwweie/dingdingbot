# 任务计划

> **最后更新**: 2026-04-14 Float/Decimal 精度修复
> **当前活跃项目**: Float→Decimal 精度修复已完成（192 测试通过 + 31 新增精度测试通过）

---

## 已完成项目摘要

| 项目 | 完成日期 | 提交 | 状态 |
|------|----------|------|------|
| ConfigManager 三层架构 (Parser/Repository/Provider) | 2026-04-07 | `02a9947`~`f6fdb49` | ✅ |
| T010 订单集成测试 | 2026-04-07 | `8105122` | ✅ |
| P1-5 Provider 注册框架 (185 测试, 覆盖率 92%) | 2026-04-07 | `02a9947`~`f6fdb49` | ✅ |

> 详细任务清单见 `archive/completed-tasks/2026-04-config-manager-refactor.md`

---

## MVP 回测验证项目（2026-04-09 启动）

**目标**: 验证 Pinbar 策略有效性，跑通 MVP 最小交付版本

### 任务清单

| # | 任务 | 状态 | 交付 |
|---|------|------|------|
| 1 | Pinbar 单元测试 (57 新增测试) | ✅ 已完成 | `e7d34e8` |
| 2 | 集成测试-真实 K 线 (445K K 线, 5,406 信号) | ✅ 已完成 | `12e4928` |
| 3 | PMS 回测功能检查 (9.4/10 分) | ✅ 已完成 | `7c59ac6` |
| 4 | Testnet 模拟盘验证 | 🔓 可启动 | 待执行 |

### 回测核心发现

1. **15m 唯一全部正收益周期**（BTC/ETH/SOL 的 15m 均为正）
2. **SOL 表现最优**（15m +110%，各周期全部正收益）
3. 胜率 28%~41% + 盈亏比 1.7~2.25 = 正期望（趋势跟踪典型）
4. EMA 过滤器拒绝 82% 信号（可能过严）
5. 评分与胜率相关性弱
6. 最大连亏 9~16 笔

### 调参方向
- 优先优化 15m 级别 + SOL 品种
- 暂停 1h/4h 优化（当前配置亏损）
- 网格搜索 `min_wick_ratio`、`max_body_ratio`、`ema_period`
- 出场策略改用 ATR 追踪止损
- 放宽 EMA 过滤严格度、校准评分公式

---

## 里程碑总览

| 里程碑 | 日期 | 状态 |
|--------|------|------|
| ConfigManager Parser 层 | 2026-04-01 | ✅ |
| ConfigManager Repository 层 | 2026-04-03 | ✅ |
| ConfigManager Provider 注册 | 2026-04-07 | ✅ |
| ConfigManager 全量回归 | 2026-04-07 | ✅ |
| MVP Task 1: Pinbar 单元测试 | 2026-04-09 | ✅ |
| MVP Task 2: 集成测试 | 2026-04-09 | ✅ |
| MVP Task 3: PMS 回测检查 | 2026-04-09 | ✅ |
| MVP Task 4: Testnet 模拟盘 | 待定 | 🔓 可启动 |
| TODO 注释确认与清理 | 2026-04-13 | ✅ |
| Profile 死代码清理 + lib/api.ts 清理 | 2026-04-13 | ✅ |
| 回测 risk_overrides 消费断裂修复 | 2026-04-13 | ✅ |
| lifespan 补充 Config Repositories 初始化 | 2026-04-13 | ✅ |
| lifespan 补充 ConfigManager 初始化 | 2026-04-13 | ✅ |
| 回测数据加载修复 (DB 绝对路径 + CCXT 分页) | 2026-04-13 | ✅ `19e2d1e` |
| Float/Decimal 精度修复（7 个核心文件 + 31 个测试） | 2026-04-14 | ✅ 待提交 |

---

## 策略系统整合项目（2026-04-10 启动）

**背景**: 用户反馈策略管理混乱——两个重复页面、下发实盘后仪表盘空白、MTF 配置无效、回测需要手动组装策略。

**目标**: 消除重复入口、修复下发断裂、简化 MTF 配置、让回测能一键导入已保存策略。

### 第一阶段任务（本轮执行）

| # | 任务 | 优先级 | 状态 | 依赖 |
|---|------|--------|------|------|
| 1 | 旧页面功能迁移（Dry Run + Apply）+ 删除旧路由 | P0 | ✅ 已完成 | 无 |
| 2 | 修复策略下发断裂，统一走 apply API | P0 | ✅ 已完成 | Task 1 |
| 3 | 移除 MTF 冗余映射配置 | P1 | ✅ 已完成 | 无 |
| 4 | 策略详情预览（卡片添加查看详情） | P1 | ✅ 已完成 | 无 |
| 5 | 回测页面一键导入已保存策略 | P0 | ✅ 已完成 | 无 |
| 6 | 修复前端 RiskConfig 类型与后端不匹配 | P0 | ✅ 已完成 | 无 |
| 7 | 修复 YAML 全局 Decimal 构造器劫持 | P0 | ✅ 已完成 | 无 |
| 8 | 修复热重载缓存未刷新 | P1 | ✅ 已完成 | 无 |

### 第二阶段任务（后续）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 9 | 修复 BackupTab 导入/导出功能损坏 | P0 | ✅ 已完成 |
| 10 | 合并两个重复的 SystemTab 组件 | P1 | ✅ 已完成 |
| 11 | StrategyForm 触发器参数表单补全 | P1 | ✅ 已完成 |
| 12 | 共享 DB 连接池 | P1 | ✅ 已完成 |

### 第三阶段：YAML → DB 迁移 + 配置页面整合（2026-04-11 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 13 | YAML 运行时配置迁移到 DB（后端） | P0 | ✅ 已完成 |
| 14 | 配置页面整合（4 Tab 统一页面） | P0 | ✅ 已完成 |
| 15 | 生效配置总览 API + 前端组件 | P0 | ✅ 已完成 |
| 16 | 审查修复（5+1 问题） | P0/P1/P2 | ✅ 已完成 |

#### Phase 5 提交记录

| Commit | 说明 |
|--------|------|
| `89036df` | Part A: YAML 运行时配置迁移到 DB |
| `8fd136d` | Part B/C: 配置页面整合 + 生效配置总览 + YAML 清理 |
| `25334fc` | Fix: PMS 回测导航入口修复 |
| `3a62a82` | 审查修复: get_migration_status/api_secret/死变量/docstring |
| `8dde6b7` | Fix: MigrationStatus 类型不匹配 |

### 第六阶段：配置依赖注入统一修复（2026-04-12 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 29 | 统一配置依赖注入（方案 C） | P0 | ✅ 已完成 |

**修复摘要**：
- `lifespan="off"` 导致 7 个配置 Repository 未初始化，`/api/v1/config/*` 全线 503
- 方案 C：将 7 个 Repository 初始化移入 `main.py` Phase 9，通过 `set_dependencies()` 统一注入
- 新增 `api_config_globals.py` 打破 `api.py` ↔ `api_v1_config.py` 循环导入
- 删除 `api_v1_config.py` 的 `set_config_dependencies()` 函数，改为从 `api_config_globals` 导入
- 清理 `lifespan()` 中 40+ 行死代码
- 验收：12 个 `/api/v1/config/*` 端点 11/12 返回 200（effective 端点 500 为独立 bug）

**改动文件**：
| 文件 | 改动 |
|------|------|
| `src/interfaces/api_config_globals.py` | 新增（打破循环导入） |
| `src/interfaces/api.py` | `set_dependencies()` 扩容 + `lifespan()` 清理 |
| `src/interfaces/api_v1_config.py` | 删除 `set_config_dependencies()` + 改为 import 全局变量 |
| `src/main.py` | Phase 9 新增 7 个 Repository 初始化 + 传参 |
| `tests/` | 3 个测试文件 import 路径更新 |

### 第七阶段：TODO 清理 + 死代码清理（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 20 | 前端 TODO 注释确认与清理（1 处措辞更新，3 处保留） | P1 | ✅ 已完成 |
| 21 | 后端 TODO 注释确认与清理（4 处过时清理，18 处保留） | P1 | ✅ 已完成 |
| 24 | config-profile.ts 死代码确认 + 清理 | P2 | ✅ 已完成 |
| 25 + 28 | lib/api.ts 死代码清理（Profile API / Legacy types / 未用函数） | P2 | ✅ 已完成 |

**清理摘要**：
- 前端 4 处 TODO：1 处措辞更新（"实际项目" → "实现后端重启 API"），3 处保留（功能未完成）
- 后端 22 处 TODO：4 处过时清理/更新，18 处保留（真实待办）
- 删除 `ConfigProfiles.tsx` (524 行) + `types/config-profile.ts` (283 行) + `components/profiles/` (5 文件, 1010 行)
- `lib/api.ts` 删除 Profile API 10 函数 (~190 行)、LegacyStrategyConfig/LegacySystemConfig、`fetchConfig`/`updateConfig`/`fetchBacktestOrder`/`runReconciliation`
- 净减少 **~2,118 行代码**
- TypeScript 编译无新增错误（77 个预存错误不变）

### 第八阶段：方案 B 彻底统一策略表（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 28 | 架构师输出方案 B 详细修复方案 | P0 | ✅ 已完成 |
| 29 | 删除 api.py 中 8 个旧策略端点 + 旧模型 | P0 | ✅ 已完成 |
| 30 | 清理 SignalRepository 旧表定义 + CRUD 方法 | P0 | ✅ 已完成 |
| 31 | 前端 API 调用迁移到新端点 | P0 | ✅ 已完成 |
| 32 | 数据库迁移脚本 006_migrate_custom_strategies | P0 | ✅ 已完成 |
| 33 | 测试更新 + 全量回归 | P0 | ✅ 已完成 |

**改动摘要**：
- 后端删除 ~410 行（api.py 260 行 + signal_repository.py 150 行）
- 前端删除 ~101 行 + 修改 6 个文件
- 创建迁移脚本 006_migrate_custom_strategies.py
- 修复 3 个测试文件（test_strategy_apply、config_import_export_e2e、config_history）
- 后端 2746 passed（182 failed + 61 errors 均为预存问题）
- 净删除 **~830 行代码**

**提交**: `723145e`

### 第九阶段：策略编辑器 + 策略下发实盘全流程修复（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 34 | 完全删除策略编辑器自动保存功能 | P0 | ✅ 已完成 |
| 35 | configApiClient 添加认证拦截器（X-User-Role: admin） | P0 | ✅ 已完成 |
| 36 | 修复 apply 端点 strategy_id 类型 int → str（422 错误） | P0 | ✅ 已完成 |
| 37 | 补全过滤器参数表单 UI（4 种过滤器动态渲染） | P0 | ✅ 已完成 |
| 38 | 修复编辑模式 trigger_params 回显不正确 | P0 | ✅ 已完成 |
| 39 | 修复 apply 端点查询新表 strategies（404 错误） | P0 | ✅ 已完成 |
| 40 | 修复 apply 端点 ConfigManager 不存在的方法（500 错误） | P0 | ✅ 已完成 |

**修复摘要**：
- 删除自动保存：移除 debounce + hasUnsavedChanges 状态，保存按钮始终可用
- 认证拦截器：axios interceptor 全局注入 `X-User-Role: admin` 头
- 过滤器表单：新建 filterSchemas.ts（4 种过滤器 Schema），动态渲染添加/删除/启用/参数配置
- 编辑回显：删除 Form.Item initialValue 覆盖，正确 form.setFieldsValue 回填 trigger_params 和 filters
- apply 端点 422：strategy_id: int → str（UUID 解析失败）
- apply 端点 404：SignalRepository.get_custom_strategy_by_id → _strategy_repo.get_by_id（旧表已删除）
- apply 端点 500：移除不存在的 update_user_config()，改为 is_active 更新 + notify_hot_reload + pipeline.on_config_updated()

### 第十阶段：架构优化 + 风控配置前端（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 41 | YAML Fallback 清理：删除降级逻辑，改为默认配置 | P1 | ✅ 已完成 |
| 42 | 策略下发 timeframe 同步：合并 symbols/timeframes 到系统配置 | P0 | ✅ 已完成 |
| 43 | 编辑策略时调用详情接口（StrategyConfig 列表数据不完整） | P0 | ✅ 已完成 |
| 44 | SystemSettings 页面新增风控配置表单 | P0 | ✅ 已完成 |
| 45 | 修复风控配置在 tab 模式下不显示 | P0 | ✅ 已完成 |
| 46 | 修复风控配置表单提交未触发 API 请求 | P0 | ✅ 已完成 |

### 第十一阶段：回测 risk_overrides 消费断裂修复（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 47 | RiskConfig 增加 model_validator 自动 float→Decimal | P0 | ✅ 已完成 |
| 48 | BacktestRequest.risk_overrides 类型升级为 Optional[RiskConfig] | P0 | ✅ 已完成 |
| 49 | backtester.py 5 处硬编码替换为消费 risk_overrides | P0 | ✅ 已完成 |
| 50 | 回归测试 + 新测试验证 | P0 | ✅ 已完成 |

**修复摘要**：
- `RiskConfig` 增加 `model_config = ConfigDict(extra='ignore')` 和 `model_validator(mode='before')` 自动将 float 类型的 max_loss_percent/max_total_exposure/daily_max_loss 转为 Decimal，对已是 Decimal 的值幂等
- `BacktestRequest.risk_overrides` 类型从 `Dict[str,Any]` 升级为 `Optional[RiskConfig]`，在 API 入口层获得类型校验
- `backtester.py` 新增 `_build_risk_config()` 统一消费 risk_overrides，替换 5 处硬编码（v2_classic + v3_pms 两种模式）
- 前端无需改动，`Partial<RiskConfig>` 仍然兼容

**改动文件**：
| 文件 | 改动 |
|------|------|
| `src/domain/models.py` | RiskConfig 增加 validator + extra='ignore'；risk_overrides 类型变更 |
| `src/application/backtester.py` | 新增 `_build_risk_config()` + 5 处替换 |
| `docs/planning/architecture/adr-risk-overrides-consumption.md` | ADR 设计文档 |

**测试验证**：
- 风控相关测试 100 passed，0 failed
- 零回归（182 failed + 61 errors 均为预存问题）

### 第十二阶段：lifespan 补充 Config Repositories 初始化（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 51 | api.py lifespan 中补充 7 个 Config Repositories 初始化 + 关闭 | P0 | ✅ 已完成 |

**修复摘要**：
- 独立 uvicorn 模式下，lifespan 未初始化 Config Repositories → `/api/v1/config/strategies` 等返回 503
- main.py 嵌入模式 `lifespan="off"`，通过 `set_dependencies()` 手动注入，不受影响
- 在 lifespan startup 中幂等初始化 Strategy/Risk/System/Symbol/Notification/History/Snapshot repos
- 在 lifespan shutdown 中添加对应的 close() 清理

**改动文件**：
| 文件 | 改动 |
|------|------|
| `src/interfaces/api.py` | lifespan 函数增加 74 行（初始化 + 关闭） |

**验证结果**：
- `/api/v1/config/strategies` → 200 OK ✅
- `/api/v1/config/risk` → 200 OK ✅
- `/api/v1/config/system` → 200 OK ✅
- `/api/v1/config/symbols` → 200 OK ✅

**修复摘要**：
- YAML 清理：删除 `_load_core_config_from_yaml()` + `load_core_config_from_yaml()` + `load_user_config_from_yaml()`，新增 `_build_default_core_config()` 返回 hardcoded 默认值；删除 5 个过时测试；core.yaml 重命名为 .reference
- Timeframe 同步：新增 `merge_strategy_monitoring_config()` 方法，apply_strategy 端点增加 Step 2.5 合并 symbols/timeframes 到 system_configs（取并集，幂等）
- 策略详情接口：StrategyConfig.tsx handleEdit 改为 async，先调用 `configApi.getStrategy(id)` 获取完整详情
- 风控配置前端：SystemSettings.tsx 新增 `RiskConfigSection` 组件（tab/page 模式共用），调用已有 `configApi.getRiskConfig()` / `updateRiskConfig()` API；修复 tab 模式不显示 + 表单提交未触发 API 两个 bug

### 第十三阶段：回测数据加载修复（2026-04-13 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 53 | HistoricalDataRepository 默认路径改为 Path(__file__) 解析的绝对路径 | P0 | ✅ 已完成 |
| 54 | _query_klines_from_db 改为 ORDER BY timestamp DESC + reverse，返回最新 N 条 | P0 | ✅ 已完成 |
| 55 | fetch_historical_ohlcv 支持 since 参数，limit>1000 自动分页循环 | P0 | ✅ 已完成 |
| 56 | _fetch_from_exchange 传递 since=start_time | P0 | ✅ 已完成 |
| 57 | 3 个 backtest 端点的 finally 中关闭临时 gateway | P1 | ✅ 已完成 |
| 58 | ConfigManager.get_instance()/set_instance() 单例支持 | P2 | ✅ 已完成 |
| 59 | 新增 10 个单元测试验证以上修复 | P0 | ✅ 已完成 |

**修复摘要**：
- 根因链：后端 CWD = web-front/ → DB 相对路径指向空库 → fallback 到 CCXT → CCXT 无 since 参数返回"最近的 1000 条" → 时间范围过滤全部清除 → 0 条数据
- P0: 数据库路径改为基于 `__file__` 的绝对路径，不受 CWD 影响
- P0: SQL 查询改为 DESC 取最新 N 条，reverse 恢复升序
- P1: CCXT 分页循环（每次 1000 条），since 参数控制起始时间
- P2: Gateway 资源泄漏修复
- P3: ConfigManager 单例支持，修复回测 KV 配置加载失败

**改动文件**：
| 文件 | 改动 |
|------|------|
| `src/infrastructure/historical_data_repository.py` | DB 绝对路径 + SQL DESC + since 传参 |
| `src/infrastructure/exchange_gateway.py` | since 参数 + 分页循环 |
| `src/interfaces/api.py` | Gateway 清理 + ConfigManager 注册 |
| `src/application/config_manager.py` | get_instance/set_instance 类方法 |
| `tests/unit/` | 3 个测试文件 +10 测试 |

**测试验证**：
- DB 路径 3/3 通过，SQL 排序 2/2 通过，CCXT 分页 5/5 通过，Config 单例 2/3 通过（1 个 fixture 旧方法名问题，无关本次修复）

**提交**: `19e2d1e`

### 第十四阶段：Float/Decimal 精度修复（2026-04-14 完成）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| P1-1 | `PatternStrategy.calculate_score()` 返回 Decimal | P1 | ✅ 已完成 |
| P1-2 | `PatternResult.score` 改为 Decimal | P1 | ✅ 已完成 |
| P1-3 | `SignalResult.pnl_ratio` 改为 Decimal | P1 | ✅ 已完成 |
| P1-4 | backtester 回测结果改为 Decimal | P1 | ✅ 已完成 |
| P1-5 | `RiskCalculator.score` 参数改为 Decimal | P1 | ✅ 已完成 |
| P1-6 | `signal_pipeline._check_cover` score 参数改为 Decimal | P1 | ✅ 已完成 |
| P1-7 | `EngulfingStrategy.score` 改为 Decimal | P1 | ✅ 已完成 |
| 测试 | 新增 31 个 Decimal 精度测试（18 单元 + 7 集成 + 6 预存） | P1 | ✅ 已完成 |

**修复摘要**：
- 审计报告：全面排查 25+ 处 `float()` 转换，按 P0/P1/P2 分类
- 核心修改 6 个文件：删除浮点转换，保持 Decimal 贯穿计算链
- `strategy_engine.py`: `calculate_score()` 返回类型 `float` → `Decimal`，移除 4 处 `float()`
- `models.py`: `PatternResult.score` 改为 `Decimal`，`SignalResult.pnl_ratio` 改为 `Optional[Decimal]`
- `backtester.py`: `_simulate_win_rate` 和 `_calculate_attempt_outcome` 返回值改为 `Decimal`
- `engulfing_strategy.py`: score 保持 `Decimal`，边界比较改用 `Decimal("0.5")` / `Decimal("1.0")`
- `risk_calculator.py`: `score` 参数类型改为 `Decimal`
- `signal_pipeline.py`: `_check_cover` score 参数改为 `Decimal`
- P2 保留：`details={}` 字典中 `float()` 不变（仅 JSON 序列化用途）
- 信号 `SignalResult.score` 保留 `float`（UI 展示/排序专用，非金融计算）

**新增测试文件**：
- `tests/unit/test_decimal_precision.py` — 23 个单元测试
- `tests/integration/test_backtest_decimal_precision.py` — 7 个集成测试

**测试验证**：
- Decimal 精度相关 31 passed, 0 failed
- 全量回归 192 passed（7 个 pre-existing failures 不相关）

### 第四阶段：待办任务清单（2026-04-14 收工）

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 17 | BackupTab 手动验证 | P0 | 🔓 待验证 |
| 18 | Testnet 模拟盘验证 | P0 | 🔓 可启动 |
| 19 | Decimal 绑定 SQLite 加固 | P1 | 📋 待规划 |
| 26 | YAML 导入格式统一 | P2 | 📋 待规划 |
| 27 | v3 Phase 5 实盘集成 | P2 | ⏳ 待启动 |
| 52 | 共享 DB 连接池：将 17+ 个独立 aiosqlite 连接统一到 connection_pool，彻底消除 database is locked | P1 | 📋 待规划 |
| 60 | 重启后端验证回测数据加载修复 | P0 | 🔓 待验证 |

### 已知独立问题（非本次修复引入）

| # | 问题 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | `/api/v1/config/effective` → 500（`ConfigManager.get_system_config()` 不存在） | P1 | ✅ 已安排修复 |
| 2 | `test_config_repository.py` 3 个测试失败（`AssetPollingConfig` NameError） | P1 | ✅ 已安排修复 |

### 执行顺序

```
并行启动:
├── Task 1: 旧页面功能迁移 + 删除旧路由 (最大改动)
├── Task 3: 移除 MTF 冗余映射配置 (小改动)
├── Task 4: 策略详情预览 (中等改动)
├── Task 5: 回测页面一键导入 (中等改动)
├── Task 6: RiskConfig 类型对齐 (小改动)
├── Task 7: YAML Decimal 构造器修复 (小改动)
├── Task 8: 热重载缓存刷新 (中等改动)
│
Task 1 完成后:
└── Task 2: 修复策略下发断裂 (依赖 Task 1)
```
