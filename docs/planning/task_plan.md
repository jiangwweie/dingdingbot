# 任务计划：P1-1 和 P1-2 配置修复

> **创建时间**: 2026-04-07
> **状态**: 进行中

---

## 任务概述

### P1-1: Decimal YAML 精度修复
- **文件位置**: `src/interfaces/api_v1_config.py:57-62`
- **问题**: Decimal 被转换为 float 后序列化，精度丢失
- **方案**: 使用字符串表示 Decimal

### P1-2: 缓存 TTL 机制
- **文件位置**: `src/interfaces/api_v1_config.py:1452`
- **问题**: 预览数据永久占用内存，无过期机制
- **方案**: 使用 cachetools.TTLCache

---

## 任务分解

### P1-1 实施步骤
- [x] 读取当前实现代码
- [x] 修改 `_decimal_representer` 使用字符串表示
- [x] 添加 `_decimal_constructor` 用于反序列化
- [x] 编写测试用例验证精度
- [ ] 运行测试验证

### P1-2 实施步骤
- [x] 确认项目依赖是否有 cachetools (确认：无)
- [x] 添加 cachetools 到 requirements.txt
- [x] 替换 `_import_preview_cache` 为 TTLCache
- [x] 更新使用 TTLCache 的代码（移除手动过期检查）
- [x] 验证过期行为测试
- [ ] 运行测试验证

---

## 进度追踪

| 时间 | 任务 | 状态 |
|------|------|------|
| 2026-04-07 | P1-1 实施 | 已完成 |
| 2026-04-07 | P1-2 实施 | 已完成 |
| 2026-04-07 | 测试验证 | 进行中 |
| 2026-04-07 | 代码提交 | 待开始 |

---

## 依赖关系

- P1-1 和 P1-2 串行执行（同一文件，避免冲突）
- 两个任务都完成后统一测试提交

---

## 其他任务

### T008 - P2-8 状态描述映射缺失修复 ✅ 已完成

**任务描述**: 补充 `OrderStateMachine.describe_transition()` 方法中缺失的状态转换描述

**实施步骤**:
- [x] 审计 `describe_transition()` 方法的状态描述映射
- [x] 确认所有 17 个合法状态转换描述已完整
- [x] 新增 `TestDescribeTransitionCompleteness` 测试类（7 个测试用例）
- [x] 运行测试验证（73 passed，无回归）
- [x] 更新进度日志

**验收标准**:
- ✅ 所有合法状态转换都有描述映射
- ✅ 新增 7 个单元测试全部通过
- ✅ 现有测试无回归 (73 passed)
