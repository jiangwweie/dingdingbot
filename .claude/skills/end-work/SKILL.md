---
name: end-work
description: 收工技能 - 检查未提交变更、运行测试、更新进度日志、生成会话总结
license: Proprietary
---

# 🏁 收工技能 (End Work)

**触发方式**: 用户说「收工」「结束工作」「今天的任务完成了」等

---

## 核心职责

1. **检查未提交变更** - git status 列出所有修改
2. **运行测试套件** - 快速验证代码质量
3. **更新进度日志** - 记录今日完成工作和待办
4. **生成会话总结** - 创建交接文档
5. **更新任务状态** - 标记完成的任务
6. **生成 commit message** - 根据变更生成草稿
7. **检查规划文件** - 确认三文件已更新

---

## 执行步骤

### 步骤 1: 检查未提交变更

```bash
# 显示所有修改
git status

# 显示具体变更内容
git diff --stat
```

**输出**: 列出所有修改文件，提醒用户提交

### 步骤 2: 运行测试套件

```bash
# 快速验证测试
pytest tests/unit/ -v --tb=short
```

**如有失败**: 提醒用户修复或记录为待办

### 步骤 3: 读取并更新进度日志

```python
# 读取 progress.md
with open("docs/planning/progress.md") as f:
    progress = f.read()

# 添加今日总结
today_summary = f"""
---
## {日期} - 收工

**时间**: {HH:MM}

### 今日完成
- {完成的任务 1}
- {完成的任务 2}

### 遇到问题
- {问题 1 及解决方案}

### 待办事项
- {明日待办 1}
- {明日待办 2}

---
"""
```

### 步骤 4: 检查任务计划状态

```python
# 读取 task_plan.md
with open("docs/planning/task_plan.md") as f:
    task_plan = f.read()

# 解析任务状态
pending_tasks = [...]  # 提取 pending 任务
completed_tasks = [...]  # 提取今日完成的任务
```

### 步骤 5: 生成 Commit Message 建议

根据 git diff 内容生成：

```markdown
feat: 实现策略预览接口和组件

- 后端：实现 /api/strategies/preview 端点
- 前端：实现 NodeRenderer 递归组件
- 测试：添加预览接口单元测试

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### 步骤 6: 生成会话总结

创建交接文档：`docs/planning/{日期}-handoff.md`

```markdown
# 会话交接文档 ({日期})

## 完成的工作
1. {任务 1}
2. {任务 2}

## 待办事项
1. {待办 1}
2. {待办 2}

## 注意事项
- {技术细节/踩坑记录}

## 相关文件
- `docs/planning/progress.md` - 详细进度日志
- `docs/planning/findings.md` - 技术发现
```

### 步骤 7: 检查规划文件

确认以下文件已更新：
- [ ] `docs/planning/task_plan.md` - 任务状态已更新
- [ ] `docs/planning/progress.md` - 今日总结已记录
- [ ] `docs/planning/findings.md` - 技术发现已记录

---

## 输出格式

```markdown
## 🏁 收工报告 ({日期})

### 未提交变更
{git status 输出}

### 测试结果
- 运行测试：{pytest 输出摘要}
- 通过率：{XX}%

### 今日完成
- ✅ {任务 1}
- ✅ {任务 2}

### 待办事项
- ⏳ {待办 1}
- ⏳ {待办 2}

### 提交建议
```
{commit message 草稿}
```

### 会话总结
已创建：`docs/planning/{日期}-handoff.md`

---
**收工时间**: {HH:MM} | 进度已记录到 `progress.md`
```

---

## 示例输出

```markdown
## 🏁 收工报告 (2026-03-31)

### 未提交变更
M src/interfaces/api.py
M web-front/src/components/PreviewButton.tsx
?? tests/unit/test_preview_api.py

### 测试结果
- 运行测试：15 passed, 0 failed
- 通过率：100%

### 今日完成
- ✅ 实现策略预览 API 接口
- ✅ 实现递归评估引擎
- ✅ 前端预览组件开发
- ✅ 编写单元测试

### 待办事项
- ⏳ 前端样式优化
- ⏳ 集成测试编写
- ⏳ 性能优化（缓存）

### 提交建议
```
feat: 实现策略预览功能（接口 + 组件）

- 后端：/api/strategies/preview 端点
- 后端：evaluate_node() 递归引擎
- 前端：PreviewButton + NodeRenderer 组件
- 测试：预览接口单元测试

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### 会话总结
已创建：`docs/planning/2026-03-31-handoff.md`

---
**收工时间**: 18:30 | 进度已记录到 `progress.md`
```

---

## 异常处理

| 场景 | 处理方式 |
|------|----------|
| 测试失败 | 显示失败详情，询问是否修复或记录为待办 |
| 有大文件未提交 | 提醒确认是否应该提交 |
| 规划文件未更新 | 提醒用户更新或代为更新 |
| Git 有冲突 | 提醒先解决冲突再收工 |

---

## 相关文件

- `docs/planning/task_plan.md` - 任务计划
- `docs/planning/progress.md` - 进度日志
- `docs/planning/findings.md` - 技术发现
- `docs/planning/{date}-handoff.md` - 会话交接文档（可选生成）

---

*好好休息，明天继续 🐶*
