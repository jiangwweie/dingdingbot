# 配置管理系统重构 - 任务计划

**创建日期**: 2026-04-03  
**状态**: 执行中  
**预计工作量**: 7 天

---

## 并行簇拆分方案

### 簇 A: 数据库层（无依赖 - 已启动）
- **A1**: ConfigRepository 创建 (`src/infrastructure/config_repository.py`)
- **A2**: 数据库迁移脚本 (`scripts/init_config_db.py`, `scripts/migrate_config_to_db.py`)

### 簇 E: 信号冷却重构（无依赖 - 已启动）
- **E1**: 信号状态枚举 (`src/domain/models.py`)
- **E2**: 信号管道重构 (`src/application/signal_pipeline.py`)

### 簇 B: ConfigManager（依赖簇 A 完成）
- **B1**: 加载逻辑重写
- **B2**: 热重载机制
- **B3**: 导入/导出功能

### 簇 C: API 层（依赖簇 B）
- **C1**: 配置管理 API
- **C2**: 策略配置 API
- **C3**: 导入/导出 API
- **C4**: 配置历史 API

### 簇 D: 前端层（依赖簇 C）
- **D1**: 配置管理页面
- **D2**: Tooltip 组件
- **D3**: 导入/导出交互

### 簇 F: K 线图表组件化（无依赖 - 新增）
- **F1**: 后端通用 K 线接口 (`GET /api/klines`)
- **F2**: 前端 KlineChart 组件
- **F3**: SignalDetailsDrawer 重构
- **F4**: SignalAttempts 集成

---

## 任务清单

| ID | 任务 | 状态 | 依赖 | 负责人 |
|----|------|------|------|--------|
| 1 | 簇 A: ConfigRepository 创建 | ✅ 已完成 | 无 | backend-dev |
| 3 | 簇 A: 迁移脚本创建 | ✅ 已完成 | 无 | backend-dev |
| 2 | 簇 E: 信号状态枚举 | ✅ 已完成 | 无 | backend-dev |
| 11 | 簇 B: 加载逻辑重写 | ⏳ 待开始 | 1, 3 | backend-dev |
| 15 | 簇 B: 热重载机制 | ⏳ 待开始 | 1, 3 | backend-dev |
| 4 | 簇 B: 导入/导出 | ⏳ 待开始 | 1, 3 | backend-dev |
| 13 | 簇 C: 配置管理 API | ⏳ 待开始 | 11, 15, 4 | backend-dev |
| 5 | 簇 C: 策略配置 API | ⏳ 待开始 | 11, 15, 4 | backend-dev |
| 9 | 簇 C: 导入/导出 API | ⏳ 待开始 | 11, 15, 4 | backend-dev |
| 14 | 簇 C: 配置历史 API | ⏳ 待开始 | 1, 3 | backend-dev |
| 6 | 簇 D: 配置管理页面 | ✅ 已完成 | 13, 5, 9 | frontend-dev |
| 8 | 簇 D: Tooltip 组件 | ✅ 已完成 | 无 | frontend-dev |
| 10 | 簇 D: 导入/导出交互 | ✅ 已完成 | 13, 5, 9 | frontend-dev |
| 12 | 阶段 6: 单元测试 | ⏳ 待开始 | 所有开发 | qa |
| 7 | 阶段 6: 集成测试 | ⏳ 待开始 | 单元测试 | qa |
| 16 | 簇 F: 后端通用 K 线接口 | ⏳ 待开始 | 无 | backend-dev |
| 17 | 簇 F: KlineChart 组件 | ⏳ 待开始 | 16 | frontend-dev |
| 18 | 簇 F: SignalDetailsDrawer 重构 | ⏳ 待开始 | 17 | frontend-dev |
| 19 | 簇 F: SignalAttempts 集成 | ⏳ 待开始 | 17 | frontend-dev |

---

## 参考文档

1. 实现计划：`docs/plans/config-management-plan.md`
2. 架构设计：`docs/arch/2026-04-03-config-management-design.md`
3. API 契约：`docs/designs/config-management-contract.md`

---

*最后更新：2026-04-03*
