---
name: doc-manager
description: Clean up and organize docs/ directory. Use when the user says "整理 docs", "整理文档", "clean up docs", "docs cleanup", "整理一下 docs", or when the docs/ directory needs maintenance. Automatically classifies documents into active/constraints/archive based on codebase cross-referencing, git sync status, and semantic relevance. No questions asked -- just does it.
---

# 文档管理 Skill

## 触发词

- "整理 docs" / "整理一下 docs" / "整理文档"
- "clean up docs" / "docs cleanup"
- "docs 太乱了" / "docs 太多了"

## 工作流程

**全部自动执行，不需要用户确认。**

### 步骤 1：扫描

运行 `python .agents/skills/doc-manager/scripts/scan.py`

扫描 `docs/` 下所有 `.md` 文件，提取：
- 文件路径、大小、修改时间
- 提到的 `src/` 路径
- 提到的类名、函数名
- 文件名中的日期、类型前缀
- 是否包含约束关键词（规范、必须、禁止、红线）

输出：`docs/.scan-result.json`

### 步骤 2：验证

运行 `python .agents/skills/doc-manager/scripts/validate.py`

对每个文档：
- 检查提到的 `src/` 路径是否存在
- 对不存在的做模糊匹配（可能改名了）
- `git log` 查文档自身的最后修改时间
- `git log` 查提到的代码文件的最后修改时间
- 计算存活分数

输出：`docs/.validate-result.json`

### 步骤 3：判定 + 移动

运行 `python .agents/skills/doc-manager/scripts/classify.py`

自动判定：
- 约束文档 → `docs/constraints/`
- 有效文档 → `docs/active/`
- 过期文档 → `docs/archive/YYYY-MM-DD/`

输出：`docs/.move-log.json`

### 步骤 4：生成索引

读取 `docs/active/` 和 `docs/constraints/` 下的文件，生成 `docs/INDEX.json`：

```json
{
  "generated_at": "...",
  "total_files": N,
  "active": [{"path": "...", "topics": [...], "refs": [...]}],
  "constraints": [{"path": "...", "topics": [...]}],
  "search_by_topic": {"websocket": ["..."]},
  "search_by_file": {"src/domain/models.py": ["..."]}
}
```

### 步骤 5：提交

```bash
git add docs/
git commit -m "chore: docs cleanup - archived N files, kept M active"
```

### 步骤 6：报告

输出一行总结：
```
整理了 268 个文档：移走 193 个，保留 75 个有效。索引已更新。
```

## 分类规则

详见 `references/rules.md`

## 恢复误归档

```bash
# 查看归档日志
cat docs/.move-log.json

# 恢复文件
git restore docs/archive/...  # 或直接去 archive/ 下找
```
