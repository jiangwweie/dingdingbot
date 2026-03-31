# 收工技能 - 全套收工

**触发词**: 收工、结束工作、结束、下班、shougong

---

## 执行流程

### 1. 检查未提交变更

```bash
git status
git diff --stat
```

列出所有修改的文件和变更统计。

### 2. 运行测试套件

```bash
pytest tests/unit/ -v --tb=short -x
```

快速验证代码无破坏性变更，显示测试结果。

### 3. 检查规划文件三件套

检查以下文件是否更新：
- [ ] `docs/planning/task_plan.md` - 任务状态是否更新
- [ ] `docs/planning/findings.md` - 技术发现是否记录
- [ ] `docs/planning/progress.md` - 进度日志是否更新

如果有未更新的，提醒用户。

### 4. 更新进度日志

在 `docs/planning/progress.md` 顶部添加今日总结：

```markdown
## {{当前日期}} - 收工

### 完成工作
- [待用户补充或 AI 总结]

### 遇到的问题
- [待用户补充]

### 明日待办
- [待用户补充]

### Git 提交
```
<待生成 commit message 草稿>
```
```

### 5. 生成会话总结

创建交接文档 `docs/planning/{{日期}}-handoff.md`：

```markdown
# {{日期}} 会话交接

## 完成工作
[总结本次会话完成的工作]

## 审查发现的问题
[列出审查发现的问题清单]

## 下一步计划
[下一步工作计划与预计工时]

## 相关文件索引
[相关文件路径]
```

### 6. 更新任务状态

如果 `task_plan.md` 中有任务完成，提醒用户更新状态。

### 7. Git 提交建议

根据变更内容生成 commit message 草稿：

```bash
git status --short | 分析变更类型，生成符合约定的提交信息
```

---

## 输出格式

```
🐶 收工 - 今日总结

📝 未提交变更：
 M file1.py
 M file2.md

🧪 测试结果：XX/XX 通过 (XX%)

📋 规划文件检查：
- task_plan.md: ✅ 已更新 / ❌ 待更新
- findings.md: ✅ 已记录 / ❌ 待记录
- progress.md: ✅ 已更新 / ❌ 待记录

📄 交接文档：docs/planning/{{日期}}-handoff.md

💡 建议提交信息：
feat/fix/docs: [简要描述]

---
🎉 辛苦了！明天继续。
```
