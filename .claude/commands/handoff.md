# 会话交接技能 (Session Handoff) - v2.0 精简版

**触发词**: handoff、交接、会话交接

**版本**: v2.0 (精简版 - 仅保留独特价值)

**核心定位**: 轻量级会话交接工具（任何会话都可使用），确保跨会文上下文连续性

**与 `/shougong` 的区别**:
- `/handoff`: 轻量级会话交接，**仅生成交接文档 + Git 提交（不推送）**
- `/shougong`: 全套收工流程，包含状态更新、看板同步、Git 推送 + **自动归档旧交接文档**

**v2.0 核心改进** ⭐:
- ✅ 精简内容（减少 70% 大小，从 7K → 2K）
- ✅ 删除冗余信息（完成任务/修改文件/Git提交已记录在 progress.md）
- ✅ 仅保留独特价值（技术决策/问题分析/阻塞依赖）
- ✅ 统一命名规范（强制 `<YYYYMMDD>-<序号>-handoff.md`）
- ✅ 限制每日最多 2 个交接文档

---

## 执行流程 (5 阶段)

### 阶段 1: 前置检查（自动）

读取 planning-with-files 文档 + Git 状态检查：

```bash
# 检查文档目录
ls docs/planning/ 2>/dev/null || mkdir -p docs/planning

# Git 状态
git status --porcelain
git diff --stat

# 提交历史（今日）
git log --since="00:00" --oneline
```

**读取文档**（如果存在）:
- `docs/planning/task_plan.md` → 当前任务阶段
- `docs/planning/findings.md` → 技术发现
- `docs/planning/progress.md` → 历史进度

---

### 阶段 2: 信息提取（自动）

AI 从当前会话上下文提取以下信息：

#### 2.1 已完成工作详情

提取逻辑：
- 分析工具调用记录（Edit, Write, Bash）
- 从会话对话中提取任务完成信息
- 从 Architect/Reviewer 反馈中提取决策记录

**输出字段**:
```markdown
### 主要任务
- [x] 任务 A: 完成功能 X（修改 Y 个文件，新增 Z 行）
- [x] 任务 B: 修复问题 P（影响模块 M）
- [ ] 任务 C: 部分完成（进度 60%）

### 关键代码变更
- `src/xxx.py`: 功能说明 + 变更行数
- `tests/xxx.py`: 测试说明 + 变更行数

### 架构决策
- **决策 A**: 选择方案 X 而非方案 Y
  - **理由**: 性能更优 / 复杂度更低
  - **影响**: 需迁移旧代码 / 影响模块 M
```

#### 2.2 审查发现的问题

提取逻辑：
- 从 Reviewer 反馈中提取问题（P0/P1/P2 分级）
- 从测试失败记录中提取问题
- 从诊断报告中提取问题

**输出字段**:
```markdown
### P0 问题（严重，阻塞下一步）
- [ ] **P0-1**: 问题描述
  - **位置**: `src/xxx.py:124`
  - **影响**: 功能失败风险
  - **修复建议**: 新增参数校验

### P1 问题（重要，需尽快修复）
- [ ] **P1-1**: 问题描述
  - **位置**: `src/xxx.py:89`
  - **影响**: 状态不准确

### P2 问题（次要，可延后）
- [ ] **P2-1**: 测试覆盖率不足
```

#### 2.3 下一步计划

提取逻辑：
- 从未完成任务中提取下一步计划
- 从阻塞项中推导优先级
- 从用户要求中提取待办事项

**输出字段**:
```markdown
### 优先级排序
1. **P0-1 参数校验修复**（预计 30 分钟）- 阻塞实盘测试
2. **任务 C 集成测试完成**（预计 20 分钟）- 需完成 fixture 重构
3. **P1-1 状态机完善**（预计 45 分钟）- 影响订单跟踪准确性

### 阻塞项与依赖
- **阻塞项**: 前端 API 接口未完成
- **依赖**: 实盘测试需配置交易所 API 密钥

### 预计工时
- 总计：约 1.5 小时
```

#### 2.4 相关文件索引

提取逻辑：
- 从工具调用路径中提取文件列表
- 按 类型分组：后端/前端/测试/文档/配置

**输出字段**:
```markdown
### 修改的代码文件
- `src/infrastructure/xxx.py` (+180 行)
- `src/domain/xxx.py` (+120 行)
- `tests/integration/xxx.py` (+15 行)

### 生成的文档
- `docs/planning/task_plan.md` (更新进度)
- `docs/planning/findings.md` (新增技术发现)
- `docs/diagnostic-reports/xxx.md` (诊断报告)

### 配置变更
- `config/user.yaml` (新增配置)
```

#### 2.5 精简内容策略 ⭐

**删除的冗余信息**（已记录在其他文档或可从 Git 推导）:
- ❌ **已完成工作详情**: 已记录在 `progress.md`
- ❌ **修改文件清单**: 可从 `git diff --stat` 获取
- ❌ **Git 提交记录**: 可从 `git log --since="00:00"` 获取
- ❌ **任务状态变更**: 已记录在 `task_plan.md` 或 `tasks.json`
- ❌ **未完成事项提醒**: 可从 `task_plan.md` P0 任务推导

**保留的独特价值**（无法从其他来源获取）:
- ✅ **技术决策记录**: 为何选择方案 A 而非方案 B（包含背景/理由/影响）
- ✅ **问题根因分析**: P0/P1 问题的根因/影响范围/修复建议
- ✅ **阻塞项与依赖**: 任务间的阻塞依赖关系
- ✅ **影响范围分析**: 修改的代码对其他模块的潜在影响
- ✅ **下一步优先级**: 精简版的优先级排序（TOP 3）

**精简后文档大小**: 约 **2K**（相比原版 7K 减少 70%）

---

### 阶段 3: 用户确认（交互）

生成预览并询问：

```
📋 会话交接预览：

**已完成工作**:
- 3 个任务完成，315 行代码修改
- 2 个架构决策记录

**审查发现的问题**:
- 1 个 P0 问题（阻塞实盘测试）
- 1 个 P1 问题（状态机不完整）
- 1 个 P2 问题（测试覆盖率不足）

**下一步计划**:
- 优先处理 P0 参数校验（预计 30 分钟）
- 完成集成测试（预计 20 分钟）

**相关文件**:
- 5 个代码文件，3 个文档

**会话统计**:
- 工具调用 23 次，代码修改 315 行
- Git 状态：2 个未提交文件

---

是否确认生成交接文档？
[Y] 确认生成
[N] 跳过本次交接
[E] 编辑补充信息
```

**用户选项**:
- `Y` → 直接生成交接文档
- `N` → 跳过本次交接（不生成文档）
- `E` → 进入交互式编辑模式（补充信息）

---

### 阶段 4: 文档生成（自动）

生成两部分内容：

#### 4.1 独立交接文档

**文件路径**: `docs/planning/<session-id>-handoff.md`

**会话 ID 格式**: `<YYYYMMDD>-<序号>`
- 示例：`20260403-001`（当天第一个会话），`20260403-002`（当天第二个会话）
- 序号规则：统计当天已有的交接文档数量 +1

**生成逻辑**:
```python
from datetime import datetime
from pathlib import Path

def generate_session_id() -> str:
    today = datetime.now().strftime("%Y%m%d")
    pattern = f"{today}-*-handoff.md"
    existing = list(Path("docs/planning").glob(pattern))
    number = len(existing) + 1
    return f"{today}-{number:03d}"
```

**文档模板**: 见附录 A

#### 4.2 进度摘要追加

追加到 `docs/planning/progress.md` 顶部：

```markdown
## {{YYYY-MM-DD}} - 会话交接

**会话 ID**: {{session-id}}
**开始时间**: {{会话开始时间}}
**结束时间**: {{当前时间}}
**持续时间**: {{时长}}

### 完成工作摘要
- [已完成工作一句话摘要]

### 待办事项
- [下一步计划一句话摘要]

### 关键文件
- [修改的关键文件列表（最多 5 个）]
```

---

### 阶段 5: Git 提交（自动）

```bash
# 1. 暂存文档
git add docs/planning/

# 2. 生成 commit message
message="docs: session handoff $(session-id)"

# 3. 提交（不推送）
git commit -m "$message"

# 4. 输出提交结果
git log --oneline -1
```

**Commit Message 格式**: `docs: session handoff 20260403-001`

**不推送理由**: 让用户决定推送时机（避免影响团队协作）

---

## 输出格式

```
✅ 会话交接完成

**交接文档**: docs/planning/20260403-001-handoff.md
**进度摘要**: 已追加到 docs/planning/progress.md

**Git 提交**: abc1234 docs: session handoff 20260403-001
**未推送**: 请手动推送（git push）

---

📌 下个会话建议：
1. 启动命令：/kaigong（会自动读取本交接文档）
2. 优先处理：[P0 问题列表]
3. 准备工作：[依赖项提醒]

预计工时：约 {{duration}} 分钟
```

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| `docs/planning/` 目录不存在 | 自动创建 `mkdir -p docs/planning` |
| 当天已有交接文档 | 序号自动递增（001 → 002 → 003） |
| 无变更（无代码修改） | 仅记录进度日志，生成简化交接文档 |
| Git 冲突 | 停止提交，列出冲突文件，请用户手动解决 |
| 用户选择 "N" 跳过 | 不生成文档，仅记录简短进度日志 |
| 用户选择 "E" 编辑 | 进入交互式编辑模式，逐项询问补充信息 |

---

## 附录 A: 交接文档精简版模板（v2.0）

```markdown
---
session_id: {{session-id}}
date: {{YYYY-MM-DD HH:MM}}
duration: {{duration}}min
---

# 会话交接文档（精简版） - Session {{序号}}

> **说明**: 本文档仅保留独特价值（技术决策/问题分析/阻塞依赖），冗余信息已记录在 `progress.md` 或可从 `git log` 获取。

---

## 💡 技术决策记录（独特价值）

### 决策 1: {{决策标题}}
- **背景**: {{决策背景}}
- **选择方案**: {{选择方案}}
- **拒绝方案**: {{拒绝方案}}
- **理由**: {{理由}}
- **影响**: {{影响范围}}
- **后续**: {{后续行动}}

---

## 🔍 问题分析（独特价值）

### P0 问题（严重，阻塞下一步）
- [ ] **P0-1**: {{问题描述}}
  - **位置**: `{{文件路径}}:{{行号}}`
  - **根因**: {{根因分析}}
  - **影响**: {{影响说明}}
  - **修复建议**: {{修复建议}}
  - **预计工时**: {{预计}}

### P1 问题（重要，需尽快修复）
- [ ] **P1-1**: {{问题描述}}
  - **根因**: {{根因}}
  - **修复建议**: {{修复建议}}

---

## 🚨 阻塞项与依赖（独特价值）

### 阻塞项
- **{{阻塞项名称}}**: {{阻塞说明}}（无法进行 {{任务}}）

### 外部依赖
- **{{依赖项名称}}**: {{依赖说明}}（需要 {{谁}} 提供）

---

## 🔮 影响范围分析（独特价值）

### 修改的模块
- **{{模块名}}**: {{文件名}} 新增 {{功能}}
  - **影响**: {{影响的其他模块/功能}}
  - **潜在风险**: {{可能的问题}}

### 向下兼容性
- **配置兼容**: {{旧配置是否兼容}}
- **API 兼容**: {{旧 API 是否可用}}

---

## 📋 下一步优先级（精简版）

### TOP 3 优先事项
1. **{{任务名称}}**（{{预计工时}} 分钟）- {{阻塞说明}}
2. **{{任务名称}}**（{{预计工时}} 分钟）- {{依赖说明}}
3. **{{任务名称}}**（{{预计工时}} 分钟）- {{说明}}

---

## 📊 会话统计（精简版）

- **修改文件**: {{文件数}} 个（详见 `git diff --stat`）
- **Git 提交**: {{提交数}} 次（详见 `git log --since="00:00"`）
- **任务状态**: {{完成数}} 个完成（详见 `task_plan.md`）

---

## 🔗 下个会话建议

1. **启动命令**: `/kaigong` 会自动读取本交接文档
2. **优先处理**: {{P0 任务 TOP 1}}
3. **准备工作**: {{依赖项提醒}}
4. **预计时长**: {{总计时长}} 分钟

---

*本交接文档由 `/handoff` skill 自动生成（v2.0 精简版）*
```

---

## 附录 B: 命名规范与归档策略（v2.0 新增） ⭐

### 命名规范（强制）

**格式**: `<YYYYMMDD>-<序号>-handoff.md`

**示例**:
- `20260403-001-handoff.md` ← 当天第一个会话
- `20260403-002-handoff.md` ← 当天第二个会话

**检查逻辑**:
```python
import re
from pathlib import Path

def validate_handoff_filename(filename: str) -> bool:
    """检查交接文档命名是否符合规范"""
    pattern = r"\d{8}-\d{3}-handoff\.md"
    return re.match(pattern, filename) is not None

def fix_handoff_filename(old_filename: str) -> str:
    """修复不符合规范的命名"""
    # 示例：restart-handoff.md → 20260403-003-handoff.md
    session_id = generate_session_id()
    return f"{session_id}-handoff.md"
```

---

### 每日交接限制

**限制**: 每天最多生成 **2 个**交接文档

**检查逻辑**:
```python
from datetime import datetime
from pathlib import Path

def check_daily_handoff_limit() -> bool:
    """检查今日交接文档是否超限"""
    today = datetime.now().strftime("%Y%m%d")
    pattern = f"{today}-*-handoff.md"
    existing = list(Path("docs/planning").glob(pattern))
    return len(existing) < 2  # 最多 2 个
```

**超限提示**:
```
⚠️ 今日交接文档已超限（最多 2 个）

建议：
1. 合并今日多个会话的工作到一个交接文档
2. 或使用精简版（仅记录关键决策和问题）
```

---

### 自动归档策略

**归档时机**: `/shougong` 时自动归档超过 7 天的交接文档

**归档逻辑**:
```python
from datetime import datetime, timedelta
from pathlib import Path
import shutil

def archive_old_handoffs(days: int = 7):
    """归档超过 N 天的交接文档"""
    planning_dir = Path("docs/planning")
    archive_dir = planning_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    # 找出超过 N 天的交接文档
    cutoff_date = datetime.now() - timedelta(days=days)
    old_handoffs = [
        f for f in planning_dir.glob("*-handoff.md")
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_date
    ]

    # 移动到归档目录
    for handoff in old_handoffs:
        shutil.move(str(handoff), str(archive_dir / handoff.name))
        print(f"📦 已归档: {handoff.name}")

    # 创建归档说明
    if old_handoffs:
        archive_readme = archive_dir / "README.md"
        archive_readme.write_text(f"# 归档交接文档\n\n归档时间: {datetime.now()}\n归档数量: {len(old_handoffs)}\n")
```

**归档后目录结构**:
```
docs/planning/
├── 2026-04-03-001-handoff.md    ← 最近 7 天的交接文档
├── 2026-04-03-002-handoff.md
├── archive/                      ← 归档目录
│   ├── 2026-03-25-001-handoff.md
│   ├── 2026-03-26-001-handoff.md
│   └── README.md                 ← 归档说明
├── progress.md                   ← 保留（进度日志）
├── findings.md                   ← 保留（技术发现）
└── task_plan.md                  ← 保留（任务计划）
```

---

### 文档大小限制

**限制**: 单个交接文档不超过 **5K**

**检查逻辑**:
```python
def check_handoff_size(filepath: Path) -> bool:
    """检查交接文档大小是否超限"""
    size_kb = filepath.stat().st_size / 1024
    return size_kb < 5  # 最多 5K
```

**超限提示**:
```
⚠️ 交接文档内容过长（当前 {{size}}K，限制 5K）

建议：
1. 使用精简版（仅保留技术决策/问题分析/阻塞依赖）
2. 详细信息已记录在 progress.md，可省略重复内容
```

---

---

## 使用示例

### 示例 1: 正常交接

```bash
# 用户调用
/handoff

# 输出预览
📋 会话交接预览：
已完成工作: 3 个任务，315 行代码
审查发现: 1 个 P0 问题，1 个 P1 问题
下一步计划: P0 参数校验修复（预计 30 分钟）
...

是否确认生成交接文档？[Y/n/e]

# 用户确认 Y
✅ 交接文档已生成：docs/planning/20260403-001-handoff.md
✅ Git 已提交：docs: session handoff 20260403-001
```

### 示例 2: 编辑补充信息

```bash
# 用户选择 E
进入交互式编辑模式：

1. 已完成工作详情（当前：3 个任务）
   是否补充？[y/N]
   → 用户输入 y
   → 请输入补充内容：还完成了性能优化测试...

2. 审查发现的问题（当前：1 个 P0）
   是否补充？[y/N]
   → 用户输入 y
   → 请输入补充内容：还发现了一个潜在的内存泄漏问题...

3. 下一步计划（当前：P0 参数校验）
   是否补充？[y/N]
   → 用户输入 N

生成最终交接文档...
```

### 示例 3: 跳过交接

```bash
# 用户选择 N
📌 本次会话不生成交接文档

仅记录简短进度日志到 progress.md...

✅ 进度已记录
```

---

## 与其他 Skill 的关系

| Skill | 定位 | 关系 |
|-------|------|------|
| `/kaigong` | 开工准备 | `/kaigong` 会自动读取 `/handoff` 生成的交接文档 |
| `/shougong` | 全套收工 | `/shougong` 包含交接文档生成，但功能更全面（状态更新、Git 推送） |
| `/handoff` | 轻量交接 | 独立工具，仅生成交接文档 + Git 提交（不推送） |

**推荐使用场景**:
- **中途交接**: 会话中途需要暂停（如午休、临时会议） → 使用 `/handoff`
- **当天收工**: 一天工作结束，需要完整收工流程 → 使用 `/shougong`

---

*版本：v1.0 | 最后更新：2026-04-03*