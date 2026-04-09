# 配置管理系统 Repository 层实现计划

**创建时间**: 2026-04-04
**负责人**: backend-dev
**状态**: 进行中

---

## 任务目标

实现 7 个 Repository 类，提供配置管理系统的数据库操作接口。

## 文件位置

- **实现文件**: `src/infrastructure/repositories/config_repositories.py`
- **导出文件**: `src/infrastructure/repositories/__init__.py`
- **测试文件**: `tests/unit/test_config_repositories.py`

## 7 个 Repository 类

| 类名 | 功能 | 关键方法 |
|------|------|----------|
| `StrategyConfigRepository` | 策略配置管理 | CRUD + toggle |
| `RiskConfigRepository` | 风控配置管理 | get_global, update |
| `SystemConfigRepository` | 系统配置管理 | get_global, update (restart_required) |
| `SymbolConfigRepository` | 币池配置管理 | get_all, get_active, CRUD, toggle |
| `NotificationConfigRepository` | 通知配置管理 | CRUD + test |
| `ConfigSnapshotRepository` | 配置快照管理 | CRUD + rollback |
| `ConfigHistoryRepository` | 配置历史管理 | 历史记录查询 |

## 技术要求

1. 使用 `async/await` 异步语法
2. 使用 `aiosqlite` 进行数据库操作
3. 所有方法添加类型注解
4. 使用 Pydantic 模型进行数据验证
5. 参数化查询防止 SQL 注入
6. 清晰的事务边界

## 依赖关系

- `src/infrastructure/database.py` - 数据库连接（但本实现使用独立的 aiosqlite 连接以保持一致性）
- `src/domain/models.py` - Pydantic 数据模型
- `src/domain/exceptions.py` - 异常体系
- `src/domain/logic_tree.py` - 逻辑树模型

## 进度追踪

- [ ] 创建基础错误类
- [ ] 实现 StrategyConfigRepository
- [ ] 实现 RiskConfigRepository
- [ ] 实现 SystemConfigRepository
- [ ] 实现 SymbolConfigRepository
- [ ] 实现 NotificationConfigRepository
- [ ] 实现 ConfigSnapshotRepository
- [ ] 实现 ConfigHistoryRepository
- [ ] 编写单元测试
- [ ] 运行测试验证
- [ ] 更新进度文档

## 预计工时

- 实现：4 小时
- 测试：2 小时
- 总计：6 小时
