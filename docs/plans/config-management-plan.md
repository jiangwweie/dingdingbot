# 配置管理系统重构 - 实现计划

**文档编号**: PLAN-2026-001  
**创建日期**: 2026-04-03  
**状态**: 待执行  
**预计工作量**: 7 天

---

## 1. 任务分解

### 阶段 1: 数据库层 (Day 1-2)

#### Task 1.1: 创建 ConfigRepository

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: 无

**文件**:
- 创建：`src/infrastructure/config_repository.py`
- 修改：`src/infrastructure/signal_repository.py` (删除 custom_strategies 相关)

**步骤**:
1. [ ] 创建 `ConfigRepository` 类
2. [ ] 实现策略配置 CRUD 方法
3. [ ] 实现风控配置 CRUD 方法
4. [ ] 实现系统配置 CRUD 方法
5. [ ] 实现币池配置 CRUD 方法
6. [ ] 实现通知配置 CRUD 方法
7. [ ] 实现配置历史 CRUD 方法
8. [ ] 实现配置快照 CRUD 方法
9. [ ] 编写单元测试

**验收标准**:
- 所有 CRUD 方法正常工作
- 单元测试覆盖率 100%
- 数据库事务正确处理

---

#### Task 1.2: 创建数据库迁移脚本

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 1.1

**文件**:
- 创建：`scripts/migrate_config_to_db.py`
- 创建：`scripts/init_config_db.py`

**步骤**:
1. [ ] 创建初始化脚本 `init_config_db.py`
2. [ ] 创建表结构（strategy_configs, risk_configs, etc.）
3. [ ] 插入默认配置（风控、系统、币池）
4. [ ] 创建迁移脚本 `migrate_config_to_db.py`（可选）
5. [ ] 删除旧 `custom_strategies` 表

**验收标准**:
- 首次启动自动初始化 DB
- 默认配置正确插入
- 旧表安全删除

---

### 阶段 2: ConfigManager 重构 (Day 2-3)

#### Task 2.1: 重写 ConfigManager 加载逻辑

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 1.1

**文件**:
- 修改：`src/application/config_manager.py`

**步骤**:
1. [ ] 移除 `load_core_config()` 和 `load_user_config()` 方法
2. [ ] 实现 `load_all_from_db()` 方法
3. [ ] 实现配置访问器属性（`active_strategy`, `risk_config`, etc.）
4. [ ] 更新 `print_startup_info()` 方法
5. [ ] 更新 `check_api_key_permissions()` 方法（从环境变量读取 API Key）

**验收标准**:
- 系统启动从 DB 加载配置
- API Key 从环境变量读取
- 启动信息正常打印

---

#### Task 2.2: 实现热重载机制

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 2.1

**文件**:
- 修改：`src/application/config_manager.py`

**步骤**:
1. [ ] 实现 `apply_config()` 方法
2. [ ] 实现 `reload_strategy()` 方法
3. [ ] 实现 `reload_risk_config()` 方法
4. [ ] 实现 `reload_symbols()` 方法
5. [ ] 实现 `reload_notifications()` 方法
6. [ ] 实现 `_check_system_config_changed()` 方法
7. [ ] 编写热重载单元测试

**验收标准**:
- 热重载后配置立即生效
- 系统配置变更正确提示需重启
- Observer 正确通知

---

#### Task 2.3: 实现导入/导出功能

**负责人**: backend-dev  
**优先级**: 🔴 高  
**依赖**: Task 2.1

**文件**:
- 修改：`src/application/config_manager.py`
- 创建：`src/application/config_importer.py`

**步骤**:
1. [ ] 实现 `export_to_yaml()` 方法
2. [ ] 实现 `import_from_yaml()` 方法
3. [ ] 实现 YAML 验证逻辑
4. [ ] 实现导入预览功能
5. [ ] 编写单元测试

**验收标准**:
- 导出 YAML 格式正确
- 导入验证逻辑正常
- 预览功能正常

---

### 阶段 3: API 实现 (Day 3-4)

#### Task 3.1: 配置管理 API

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 2.1

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 实现 `GET /api/config`
2. [ ] 实现 `PUT /api/config/risk`
3. [ ] 实现 `PUT /api/config/system`
4. [ ] 实现 `GET /api/config/symbols`
5. [ ] 实现 `POST /api/config/symbols`
6. [ ] 实现 `DELETE /api/config/symbols/{id}`
7. [ ] 实现 `GET /api/config/notifications`
8. [ ] 实现 `PUT/POST/DELETE /api/config/notifications/*`

**验收标准**:
- 所有端点正常工作
- 热重载正确触发
- 错误处理完善

---

#### Task 3.2: 策略配置 API

**负责人**: backend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 1.1

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 实现 `GET /api/strategies`
2. [ ] 实现 `GET /api/strategies/{id}`
3. [ ] 实现 `POST /api/strategies`
4. [ ] 实现 `PUT /api/strategies/{id}`
5. [ ] 实现 `DELETE /api/strategies/{id}`
6. [ ] 实现 `POST /api/strategies/{id}/activate`

**验收标准**:
- 所有端点正常工作
- 策略激活正确触发热重载

---

#### Task 3.3: 导入/导出 API

**负责人**: backend-dev  
**优先级**: 🔴 高  
**依赖**: Task 2.3

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 实现 `POST /api/config/export`
2. [ ] 实现 `POST /api/config/import/preview`
3. [ ] 实现 `POST /api/config/import/confirm`

**验收标准**:
- 导出 YAML 正确
- 导入预览功能正常
- 导入确认正确处理

---

#### Task 3.4: 配置历史 API

**负责人**: backend-dev  
**优先级**: 🟡 中  
**依赖**: Task 1.1

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 实现 `GET /api/snapshots`
2. [ ] 实现 `POST /api/snapshots`
3. [ ] 实现 `POST /api/snapshots/{id}/rollback`
4. [ ] 实现 `GET /api/history`

**验收标准**:
- 快照功能正常
- 回滚功能正常
- 历史查询正常

---

### 阶段 4: 前端实现 (Day 4-6)

#### Task 4.1: 配置管理页面

**负责人**: frontend-dev  
**优先级**: 🔴 最高  
**依赖**: Task 3.1

**文件**:
- 创建：`web-front/src/pages/Config.tsx`
- 创建：`web-front/src/components/ConfigSection.tsx`
- 创建：`web-front/src/components/SystemInfo.tsx`
- 创建：`web-front/src/components/RiskConfig.tsx`
- 创建：`web-front/src/components/SystemConfig.tsx`
- 创建：`web-front/src/components/SymbolConfig.tsx`
- 创建：`web-front/src/components/NotificationConfig.tsx`
- 创建：`web-front/src/components/StrategyConfig.tsx`
- 创建：`web-front/src/components/BackupRestore.tsx`

**步骤**:
1. [ ] 创建主页面框架
2. [ ] 实现系统信息区块（只读）
3. [ ] 实现启动配置区块（只读）
4. [ ] 实现风控配置区块（可编辑）
5. [ ] 实现币池管理区块（可编辑）
6. [ ] 实现通知配置区块（可编辑）
7. [ ] 实现策略配置区块（可编辑）
8. [ ] 实现备份/恢复区块
9. [ ] 集成测试

**验收标准**:
- 所有配置区块正常显示
- 编辑功能正常
- 保存/应用按钮正常工作

---

#### Task 4.2: Tooltip 组件

**负责人**: frontend-dev  
**优先级**: 🔴 高  
**依赖**: 无

**文件**:
- 创建：`web-front/src/components/ConfigTooltip.tsx`
- 创建：`web-front/src/lib/config-descriptions.ts`

**步骤**:
1. [ ] 创建 Tooltip 通用组件
2. [ ] 定义配置描述元数据
3. [ ] 为所有配置项添加 Tooltip

**验收标准**:
- Tooltip 正常显示
- 描述文案清晰准确

---

#### Task 4.3: 导入/导出交互

**负责人**: frontend-dev  
**优先级**: 🟡 中  
**依赖**: Task 3.3

**文件**:
- 修改：`web-front/src/pages/Config.tsx`

**步骤**:
1. [ ] 实现导出按钮和下载逻辑
2. [ ] 实现导入按钮和文件上传
3. [ ] 实现导入预览对话框
4. [ ] 实现导入确认逻辑

**验收标准**:
- 导出功能正常
- 导入预览显示变更
- 导入确认正确处理

---

### 阶段 5: 信号冷却重构 (Day 6)

#### Task 5.1: 信号状态枚举

**负责人**: backend-dev  
**优先级**: 🔴 高  
**依赖**: 无

**文件**:
- 修改：`src/domain/models.py`

**步骤**:
1. [ ] 定义 `SignalStatus` 枚举（增加 `SUPERSEDED`）
2. [ ] 更新数据库表结构

**验收标准**:
- 新状态枚举正常

---

#### Task 5.2: 信号管道重构

**负责人**: backend-dev  
**优先级**: 🔴 高  
**依赖**: Task 5.1

**文件**:
- 修改：`src/application/signal_pipeline.py`

**步骤**:
1. [ ] 移除冷却缓存逻辑
2. [ ] 实现 `should_send_signal()` 新逻辑
3. [ ] 实现高质量覆盖低质量逻辑
4. [ ] 编写单元测试

**验收标准**:
- 冷却逻辑移除
- 高质量覆盖逻辑正常
- 被覆盖信号状态正确标记

---

### 阶段 6: 测试与部署 (Day 7)

#### Task 6.1: 单元测试

**负责人**: qa  
**优先级**: 🔴 最高  
**依赖**: 所有开发任务

**文件**:
- 创建：`tests/unit/test_config_repository.py`
- 创建：`tests/unit/test_config_manager_v2.py`
- 创建：`tests/unit/test_config_importer.py`
- 修改：`tests/unit/test_signal_pipeline.py`

**步骤**:
1. [ ] ConfigRepository 测试
2. [ ] ConfigManager 测试
3. [ ] ConfigImporter 测试
4. [ ] SignalPipeline 测试（冷却重构）

**验收标准**:
- 所有测试通过
- 覆盖率 100%

---

#### Task 6.2: 集成测试

**负责人**: qa  
**优先级**: 🔴 高  
**依赖**: Task 6.1

**文件**:
- 创建：`tests/integration/test_config_management.py`
- 创建：`tests/integration/test_config_import_export.py`

**步骤**:
1. [ ] 配置管理端到端测试
2. [ ] 导入/导出端到端测试
3. [ ] 热重载测试

**验收标准**:
- 所有集成测试通过

---

#### Task 6.3: 部署上线

**负责人**: devops  
**优先级**: 🔴 最高  
**依赖**: Task 6.2

**步骤**:
1. [ ] 数据库迁移脚本执行
2. [ ] 后端应用更新
3. [ ] 前端应用更新
4. [ ] 验证服务健康
5. [ ] 验证配置功能

**验收标准**:
- 服务正常运行
- 配置功能正常

---

## 2. 依赖关系图

```
阶段 1 (DB 层)
├── Task 1.1: ConfigRepository
└── Task 1.2: 迁移脚本
    │
    ▼
阶段 2 (ConfigManager)
├── Task 2.1: 加载逻辑
├── Task 2.2: 热重载
└── Task 2.3: 导入/导出
    │
    ▼
阶段 3 (API)
├── Task 3.1: 配置管理 API
├── Task 3.2: 策略配置 API
├── Task 3.3: 导入/导出 API
└── Task 3.4: 配置历史 API
    │
    ▼
阶段 4 (前端)
├── Task 4.1: 配置管理页面
├── Task 4.2: Tooltip 组件
└── Task 4.3: 导入/导出交互
    │
    ▼
阶段 5 (信号冷却)
├── Task 5.1: 信号状态
└── Task 5.2: 信号管道
    │
    ▼
阶段 6 (测试部署)
├── Task 6.1: 单元测试
├── Task 6.2: 集成测试
└── Task 6.3: 部署上线
```

---

## 3. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| ConfigManager 重构影响其他模块 | 高 | 模块化隔离设计，独立测试 |
| 数据迁移丢失 | 高 | 迁移前备份 YAML |
| 热重载失败 | 中 | 明确错误提示和重启引导 |
| 前端页面工作量大 | 中 | 组件化开发，复用现有组件 |

---

## 4. 验收清单

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 配置管理页面正常
- [ ] 热重载功能正常
- [ ] 导入/导出功能正常
- [ ] 信号冷却重构完成
- [ ] 部署上线成功

---

*文档版本：1.0 | 最后更新：2026-04-03*
