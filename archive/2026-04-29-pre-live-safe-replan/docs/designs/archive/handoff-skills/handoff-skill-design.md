---
title: "会话交接 Skill 设计方案"
date: 2026-04-03
type: design
---

## 🎯 核心定位

**名称**: `/handoff` (会话交接)

**触发方式**: 手动调用（用户明确执行 `/handoff` 命令）

**场景**: AI 会话结束时生成交接文档，确保跨会话上下文连续性，避免上下文丢失导致的重复工作和 AI 幻觉

**与 `/shougong` 的关系**: 定位独立
- `/handoff`: 通用会话交接工具（任何会话都可使用）
- `/shougong`: 项目结束场景的特定流程（全套收工流程）

---

## 📐 设计方案

### 1. 工作流程

```
【阶段 1】前置检查 → 【阶段 2】信息提取 → 【阶段 3】用户确认 → 【阶段 4】文档生成 → 【阶段 5】Git 提交
```

#### 阶段 1: 前置检查（自动）
- 读取 `docs/planning/task_plan.md` → 获取当前任务阶段
- 读取 `docs/planning/findings.md` → 合并技术发现
- 读取 `docs/planning/progress.md` → 获取历史进度
- 执行 `git status` → 检查未提交文件
- 执行 `git diff` → 查看变更内容

#### 阶段 2: 信息提取（自动）
AI 从当前会话上下文提取：
- **已完成工作**: 分析会话中的工具调用、代码修改、审查记录
- **审查发现的问题**: 从 Reviewer 反馈中提取问题清单和严重程度
- **下一步计划**: 从未完成任务、用户要求中推导
- **相关文件**: 从工具调用路径中提取关键文件列表
- **技术决策**: 从 Architect 讨论、用户确认中提取决策记录
- **阻塞项**: 从依赖关系、外部条件中分析阻塞因素
- **影响范围**: 从代码修改路径中分析影响模块

#### 阶段 3: 用户确认（交互）
生成预览并询问用户：
- 展示提取的信息摘要
- 询问是否需要补充或修正
- 确认后正式生成文档

#### 阅段 4: 文档生成（自动）
生成两部分内容：
1. **独立交接文档**: `docs/planning/<session-id>-handoff.md`
   - 会话 ID 格式：日期+序号（如 `20260403-001`）
   - 序号从 `001` 开始，每天递增（如当天第二个会话为 `002`）

2. **进度摘要追加**: 追加到 `docs/planning/progress.md`
   - 一行摘要格式：`- [2026-04-03 15:30] Session 001: 完成 Phase 5 准备工作，发现 2 个 P0 问题`

#### 阶段 5: Git 提交（自动）
- `git add docs/planning/`
- `git commit -m "docs: session handoff $(session-id)"`
- **不推送**，让用户决定推送时机

---

### 2. 交接文档模板

```markdown
---
session_id: 20260403-001
date: 2026-04-03 15:30
duration: 45min
---

# 会话交接文档 - Session 001

## ✅ 已完成工作

### 主要任务
- [x] 任务 A: 完成 ExchangeGateway 订单接口扩展（新增 5 个方法）
- [x] 任务 B: 修复 asyncio.Lock 事件循环冲突（DEBT-5）
- [ ] 任务 C: 集成测试 fixture 重构（部分完成，进度 60%）

### 关键代码变更
- `src/infrastructure/exchange_gateway.py`: 新增 `place_order()`, `cancel_order()`, `get_order()`, `get_open_orders()`, `get_order_history()` 方法
- `src/domain/order_manager.py`: 新增订单状态机逻辑
- `tests/integration/test_order_flow.py`: 修复 fixture 依赖注入问题

### 架构决策
- **决策 A**: 选择使用 CCXT async API 而非同步 API
  - **理由**: WebSocket 并发处理性能更优
  - **影响**: 需迁移所有 exchange 调用为 async
- **决策 B**: 暂不引入数据库行锁，使用 asyncio.Lock 保护并发
  - **理由**: Phase 5 MVP 阶段简化实现
  - **后续**: Phase 6 需引入 Redis 分布式锁

---

## 🔍 审查发现的问题

### P0 问题（严重，阻塞下一步）
- [ ] **P0-1**: `place_order()` 缺少参数校验，可能导致交易所 API 错误
  - **位置**: `src/infrastructure/exchange_gateway.py:124`
  - **影响**: 交易失败风险
  - **修复建议**: 新增 Pydantic 校验模型 `OrderRequest`

### P1 问题（重要，需尽快修复）
- [ ] **P1-1**: 订单状态机缺少 `FILLED` 状态处理
  - **位置**: `src/domain/order_manager.py:89`
  - **影响**: 订单成交后状态不更新

### P2 问题（次要，可延后）
- [ ] **P2-1**: 测试覆盖率不足，缺少异常场景测试
  - **位置**: `tests/integration/test_order_flow.py`
  - **影响**: 回归风险

---

## 📋 下一步计划

### 优先级排序
1. **P0-1 参数校验修复**（预计 30 分钟）- 阻塞实盘测试
2. **任务 C 集成测试完成**（预计 20 分钟）- 需完成 fixture 重构
3. **P1-1 状态机完善**（预计 45 分钟）- 影响订单跟踪准确性

### 阻塞项与依赖
- **阻塞项**: 前端 API 接口未完成，无法进行 E2E 测试
- **依赖**: Phase 5 实盘测试需用户配置交易所 API 密钥（交易权限）

### 预计工时
- 总计：约 1.5 小时
- 建议：下个会话优先处理 P0 问题

---

## 📂 相关文件索引

### 修改的代码文件
- `src/infrastructure/exchange_gateway.py` (新增 5 个方法，+180 行)
- `src/domain/order_manager.py` (新增状态机，+120 行)
- `tests/integration/test_order_flow.py` (修复 fixture，+15 行)

### 生成的文档
- `docs/planning/task_plan.md` (更新 Phase 5 进度)
- `docs/planning/findings.md` (新增 asyncio.Lock 最佳实践记录)
- `docs/diagnostic-reports/DA-20260403-001-order-api-503.md` (订单 API 诊断报告)

### 配置变更
- `config/user.yaml` (新增交易所测试网配置)

---

## 🚨 未完成事项提醒

- **P0 问题未修复**: 需下个会话优先处理参数校验
- **集成测试未完成**: fixture 重构剩余 40% 工作量
- **实盘测试未启动**: 需用户配置 API 密钥后才能测试

---

## 🔮 影响范围分析

### 修改的模块
- **基础设施层**: `exchange_gateway.py` 新增订单接口，影响所有交易所交互逻辑
- **领域层**: `order_manager.py` 新增状态机，影响订单生命周期管理
- **测试层**: fixture 重构影响所有集成测试

### 潜在风险
- **向下兼容**: 旧配置可能缺少订单相关字段，需检查 `user.yaml` 加载逻辑
- **并发安全**: asyncio.Lock 需验证是否正确保护所有共享状态
- **数据一致性**: 订单状态机需验证是否覆盖所有异常场景

---

## 💡 技术决策记录

### 决策 1: 使用 asyncio.Lock 而非数据库锁
- **背景**: Phase 5 MVP 需快速验证实盘逻辑
- **选择方案**: asyncio.Lock 保护本地并发
- **拒绝方案**: Redis 分布式锁（复杂度高，Phase 6 再引入）
- **理由**: MVP 阶段单进程部署，asyncio.Lock 已足够
- **后续**: Phase 6 需引入分布式锁支持多实例部署

### 决策 2: 订单状态机简化实现
- **背景**: 完整状态机需支持 `PENDING → PLACED → FILLED → CANCELLED → FAILED` 状态
- **当前实现**: 仅支持 `PLACED → FILLED → CANCELLED`
- **缺失状态**: `PENDING`, `FAILED`
- **理由**: MVP 阶段仅验证核心流程，异常场景延后处理
- **风险**: 订单失败时状态不更新，需人工干预

---

## 📊 会话统计

- **工具调用**: 23 次（Read: 12, Edit: 8, Bash: 3）
- **代码修改**: 3 个文件，新增 315 行
- **文档生成**: 3 个文档（task_plan.md, findings.md, 诊断报告）
- **Git 状态**: 2 个未提交文件（已在本次交接中提交）

---

## 🔗 下个会话建议

1. **启动命令**: `/handoff` 会自动读取本交接文档
2. **优先处理**: P0-1 参数校验问题（阻塞实盘测试）
3. **准备工作**: 提前配置交易所 API 密钥（交易权限）
4. **预计时长**: 1.5 小时（含实盘测试）

---
*本交接文档由 `/handoff` skill 自动生成*
```

---

### 3. Skill 配置文件

**文件路径**: `.claude/skills/handoff.md`

**配置内容**:
```markdown
---
name: handoff
description: 会话交接工具 - AI 会话结束时生成交接文档，确保跨会话上下文连续性
user_invocable: true
---

# 会话交接 Skill

## 触发方式
用户调用 `/handoff` 命令

## 工作流程
1. **前置检查**: 读取 task_plan.md, findings.md, progress.md + Git 状态检查
2. **信息提取**: 自动从会话上下文提取已完成工作、问题、计划、文件索引
3. **用户确认**: 展示预览，询问是否补充或修正
4. **文档生成**: 生成独立交接文档 + 追加进度摘要
5. **Git 提交**: 自动提交（不推送）

## 会话 ID 格式
- 格式: `<YYYYMMDD>-<序号>`
- 示例: `20260403-001`（当天第一个会话），`20260403-002`（当天第二个会话）
- 序号规则: 每天从 001 开始递增

## 交接文档内容
- 已完成工作详情
- 审查发现的问题（P0/P1/P2 分级）
- 下一步计划（优先级排序 + 工时预估）
- 相关文件索引（代码文件 + 文档 + 配置）
- 未完成事项提醒
- 技术决策记录
- 阻塞项与依赖分析
- 影响范围分析

## 文件路径
- 独立文档: `docs/planning/<session-id>-handoff.md`
- 进度摘要: 追加到 `docs/planning/progress.md`

## Git 操作
- `git add docs/planning/`
- `git commit -m "docs: session handoff $(session-id)"`
- **不推送**，用户手动推送

## 交互方式
- 自动提取信息 + 用户确认（半自动模式）
- 生成预览后询问是否需要修正
- 确认后正式生成文档

## 示例用法
```bash
# 会话结束时调用
/handoff

# 输出预览
📋 会话交接预览：
- 已完成工作: 3 个任务，315 行代码修改
- 审查发现: 1 个 P0 问题，1 个 P1 问题
- 下一步计划: P0 参数校验修复（预计 30 分钟）
- 相关文件: 5 个代码文件，3 个文档

是否确认生成交接文档？[Y/n/修正]

# 确认后生成
✅ 交接文档已生成：docs/planning/20260403-001-handoff.md
✅ 进度摘要已追加到 progress.md
✅ Git 已提交：docs: session handoff 20260403-001
```

## 注意事项
- 会话开始时会自动读取最新的交接文档（如果存在）
- 序号生成逻辑：检查当天已有的交接文档数量 +1
- 如果用户选择"修正"，会进入交互式编辑模式
```

---

## 🚀 实现建议

### 1. 会话 ID 序号生成逻辑

```python
import os
from datetime import datetime
from pathlib import Path

def generate_session_id(planning_dir: str = "docs/planning") -> str:
    """生成会话 ID（日期+序号）"""
    today = datetime.now().strftime("%Y%m%d")
    pattern = f"{today}-*-handoff.md"

    # 统计当天已有的交接文档数量
    existing_handoffs = list(Path(planning_dir).glob(pattern))
    next_number = len(existing_handoffs) + 1

    return f"{today}-{next_number:03d}"  # 001, 002, 003...
```

### 2. 信息提取逻辑

```python
def extract_session_info(conversation_history: list) -> dict:
    """从会话历史中提取交接信息"""
    info = {
        "completed_tasks": [],
        "code_changes": [],
        "review_issues": [],
        "next_steps": [],
        "files": [],
        "decisions": [],
        "blocking_items": [],
        "impact_analysis": []
    }

    for message in conversation_history:
        # 分析工具调用记录
        if "tool_calls" in message:
            for tool in message["tool_calls"]:
                if tool["name"] == "Edit":
                    info["code_changes"].append(tool["parameters"]["file_path"])
                elif tool["name"] == "Write":
                    info["files"].append(tool["parameters"]["file_path"])

        # 分析 Reviewer 反馈
        if "P0" in message["content"] or "P1" in message["content"]:
            info["review_issues"].append(extract_issue_info(message))

        # 分析技术决策
        if "决策" in message["content"] or "decision" in message["content"]:
            info["decisions"].append(extract_decision_info(message))

    return info
```

### 3. Git 状态检查逻辑

```python
import subprocess

def check_git_status() -> dict:
    """检查 Git 状态"""
    status = {
        "untracked_files": [],
        "modified_files": [],
        "staged_files": [],
        "diff_summary": ""
    }

    # 检查未提交文件
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("??"):
            status["untracked_files"].append(line[3:])
        elif line.startswith(" M"):
            status["modified_files"].append(line[3:])
        elif line.startswith("M "):
            status["staged_files"].append(line[3:])

    # 检查变更内容
    result = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True)
    status["diff_summary"] = result.stdout

    return status
```

---

## ✅ 验收标准

1. **功能完整性**
   - [ ] 能正确生成会话 ID（日期+序号）
   - [ ] 能自动提取会话信息（工作/问题/计划/文件）
   - [ ] 能读取 planning-with-files 文档
   - [ ] 能检查 Git 状态
   - [ ] 能生成交接文档模板
   - [ ] 能追加进度摘要到 progress.md
   - [ ] 能自动 Git 提交（不推送）

2. **用户体验**
   - [ ] 预览功能友好（清晰展示提取的信息）
   - [ ] 确认流程简洁（Y/n/修正选项）
   - [ ] 生成的文档结构清晰、易于阅读
   - [ ] Git 提交信息规范

3. **边界情况处理**
   - [ ] 处理当天第一个会话（序号 001）
   - [ ] 处理当天多个会话（序号递增）
   - [ ] 处理无变更的会话（仅记录进度）
   - [ ] 处理 Git 冲突（提示用户手动解决）
   - [ ] 处理文档目录不存在（自动创建）

---

## 📚 参考文档

- `CLAUDE.md` - 会话交接规范章节
- `docs/planning/task_plan.md` - 任务阶段追踪
- `docs/planning/findings.md` - 技术发现记录
- `docs/planning/progress.md` - 进度日志
- `docs/workflows/auto-pipeline.md` - 全自动流水线

---

*设计方案由 Brainstorming 会话生成（2026-04-03）*