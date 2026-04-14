# 文档分类规则

## 判定流程

对每个文档依次执行以下判定，**从上到下，命中即停止**：

### 1. 永久约束（→ constraints/）

命中条件（满足任一）：
- `is_permanent == true`（在 CLAUDE.md 中被引用，或在 planning 根目录）
- 路径在 `CONSTRAINT_PATHS` 白名单中
- `is_constraint == true` 且 `final_score >= 0.1`

### 2. 有效文档（→ active/）

命中条件：
- `final_score >= 0.3`
- 或 `final_score >= 0.1` 且 `alive_ratio > 0.5`（一半以上的代码引用还存在）

### 3. 过期文档（→ archive/YYYY-MM-DD/）

不满足以上条件的全部归档。

## 分数计算

```
final_score = 0.4 * alive_ratio + 0.4 * git_sync_score + 0.2 * age_decay

alive_ratio    = 存活的代码引用数 / 总代码引用数
git_sync_score = 1.0 - (文档之后被改过的代码数 / 已检查的代码数)
age_decay      = max(0, 1.0 - 天数/7)
```

## 模糊匹配

当文档提到的文件不存在时，尝试：
1. 按 basename 精确匹配
2. 按 basename 去下划线后匹配
3. 按路径包含关系匹配

匹配成功视为"存活"，避免误判文件名变更导致的过期。

## 跳过规则

以下文件不处理：
- 已在 `docs/active/`、`docs/constraints/`、`docs/archive/` 中
- 在已知 archive 子目录中（如 `docs/planning/archive/`）
- `.scan-result.json`、`.validate-result.json`、`.move-log.json`、`INDEX.json`
