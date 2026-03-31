# 盯盘狗 Agent Team 开工/收工规范

**版本**: v1.0
**最后更新**: 2026-03-31

---

## 分层设计架构

```
┌─────────────────────────────────────────────────────┐
│  项目级规范 WORKFLOW.md (所有角色共同遵守)           │
│  - 通用检查清单                                      │
│  - 通用验证命令                                      │
└─────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
  │ Coordinator   │ │  Backend Dev  │ │  Frontend Dev │
  │ 专属规范     │ │  专属规范     │ │  专属规范     │
  └───────────────┘ └───────────────┘ └───────────────┘
                        │
                        ▼
                ┌───────────────┐
                │   QA Tester   │
                │  专属规范     │
                └───────────────┘
                        │
                        ▼
                ┌───────────────┐
                │  Code Reviewer│
                │  专属规范     │
                └───────────────┘
```

---

## 项目级规范 (所有角色遵守)

### 通用开工检查清单（所有角色遵守）

在开始任何任务前，所有角色必须完成以下检查：

```markdown
- [ ] **理解需求**: 已阅读并复述任务目标
- [ ] **确认边界**: 明确任务范围和交付物
- [ ] **检查依赖**: 确认前置任务已完成或无需依赖
- [ ] **环境准备**: 本地开发环境已就绪
```

**开工流程**:
```
1. 阅读任务描述 → 2. 复述理解 → 3. 确认无疑问 → 4. 开始执行
```

---

### 通用收工检查清单（所有角色遵守）

在完成任务后，所有角色必须完成以下检查：

```markdown
- [ ] **自验证通过**: 本地测试/运行正常
- [ ] **代码格式化**: 遵循项目代码规范
- [ ] **无 TODO 遗留**: 或已明确标注待办事项
- [ ] **提交规范**: Git commit message 符合约定式规范
- [ ] **文档更新**: 相关文档已同步更新（如适用）
```

**通用提交前验证命令**:
```bash
# 后端验证
pytest tests/unit/ -v --tb=short
black src/ tests/  # 如已配置
mypy src/  # 如已配置

# 前端验证
cd web-front && npm run build  # 如已配置
npm run lint  # 如已配置
```

---

## 角色专属规范

### Coordinator 专属

**文件位置**: `.claude/team/team-coordinator/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **任务规划**: 已调用 `planning-with-files-zh` 创建计划
- [ ] **文件创建**: `docs/planning/task_plan.md` 已生成
- [ ] **任务分解**: 已使用 `TaskCreate` 创建任务清单
- [ ] **依赖标注**: 已识别任务依赖关系 (addBlockedBy)
- [ ] **角色分配**: 已确定需要参与的角色
```

**调用示例**:
```python
Agent(subagent_type="planning-with-files-zh",
      prompt="为策略预览功能创建执行计划，输出到 docs/planning/task_plan.md")
```

#### 🔴 收工时检查清单
```markdown
- [ ] **集成验证**: 所有子任务测试通过
- [ ] **交付报告**: 已生成交付报告
- [ ] **进度更新**: `docs/planning/progress.md` 已更新
- [ ] **代码推送**: 已提交并推送到远程分支
- [ ] **诊断报告**: Bug 修复类任务已更新诊断报告状态
```

**验证命令**:
```bash
# 运行完整测试套件
pytest tests/unit/ tests/integration/ -v --tb=short

# 检查变更统计
git diff --stat HEAD
```

---

### Backend Dev 专属

**文件位置**: `.claude/team/backend-dev/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (如有)
- [ ] **接口确认**: 明确请求/响应 Schema
- [ ] **模型定位**: 确定需要修改的文件路径
- [ ] **测试定位**: 确定需要编写的测试文件
```

#### 🔴 收工时检查清单
```markdown
- [ ] **单元测试**: 新功能测试覆盖率 ≥ 80%
- [ ] **类型验证**: Pydantic 模型验证通过
- [ ] **代码简化**: 已调用 `code-simplifier` 优化 (如需要)
- [ ] **异步检查**: 无同步阻塞调用 (async 中无 time.sleep)
- [ ] **日志脱敏**: 敏感信息已脱敏
```

**验证命令**:
```bash
# 运行相关测试
pytest tests/unit/test_xxx.py -v

# 检查导入
python -c "from src.domain.xxx import xxx"

# 确认无循环导入
pytest --import-mode=importlib tests/unit/
```

---

### Frontend Dev 专属

**文件位置**: `.claude/team/frontend-dev/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (Props 定义)
- [ ] **UI 确认**: 明确组件交互流程
- [ ] **组件定位**: 确定需要修改的组件文件
- [ ] **类型定义**: 准备 TypeScript 类型定义
```

#### 🔴 收工时检查清单
```markdown
- [ ] **组件渲染**: 组件可正常渲染无报错
- [ ] **类型检查**: TypeScript 无类型错误
- [ ] **样式验证**: 响应式布局正常
- [ ] **设计优化**: 已调用 `ui-ux-pro-max` (如需要)
- [ ] **代码简化**: 已调用 `code-simplifier` 优化 (如需要)
```

**验证命令**:
```bash
cd web-front

# 类型检查
npm run type-check

# 构建验证
npm run build

# 样式检查
npm run lint
```

---

### QA Tester 专属

**文件位置**: `.claude/team/qa-tester/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (测试范围)
- [ ] **数据准备**: 已准备测试数据和 Mock
- [ ] **测试定位**: 确定需要编写的测试文件
- [ ] **工具确认**: 确认需要调用的测试技能
```

#### 🔴 收工时检查清单
```markdown
- [ ] **测试报告**: 已生成测试通过率报告
- [ ] **覆盖率达标**: 新增代码覆盖率 ≥ 80%
- [ ] **回归测试**: 现有测试全部通过
- [ ] **E2E 测试**: 关键路径已覆盖 (如需要)
- [ ] **失败分析**: 失败测试已分析根因
```

**验证命令**:
```bash
# 运行完整测试套件
pytest tests/unit/ tests/integration/ -v --tb=short

# 生成覆盖率报告
pytest --cov=src --cov-report=html

# 检查覆盖率
coverage report --fail-under=80
```

---

### Code Reviewer 专属

**文件位置**: `.claude/team/code-reviewer/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表和变更范围
- [ ] **审查重点**: 明确需要重点关注的风险区域
- [ ] **工具准备**: 准备好审查工具和测试命令
```

#### 🔴 收工时检查清单
```markdown
- [ ] **审查报告**: 已生成正式审查报告
- [ ] **问题标注**: 所有问题已标注优先级 (P0/P1/P2)
- [ ] **架构检查**: Clean Architecture 分层验证通过
- [ ] **安全检查**: 无安全隐患 (命令注入、SQL 注入等)
- [ ] **批准决定**: 明确批准/拒绝/需改进
```

**验证命令**:
```bash
# 运行测试验证
pytest tests/unit/ -v --tb=short

# 类型检查 (如已配置)
mypy src/

# 代码风格检查
flake8 src/ tests/
```

---

## 完整工作流程示例

### 场景：开发"策略预览功能"（复杂任务）

```
【阶段 -1】开工准备 (Coordinator)
   ↓ 调用 planning-with-files-zh 创建计划
   ↓ 生成 docs/planning/task_plan.md
   ↓ 创建任务清单 (TaskCreate)

【阶段 0】需求接收
   ↓ Coordinator 分析需求

【阶段 1】契约设计
   ↓ 编写 API 契约表 (docs/designs/preview-contract.md)

【阶段 2】任务分解
   ↓ Backend: 实现 API 接口
   ↓ Frontend: 实现预览组件
   ↓ QA: 编写测试用例

【阶段 3】并行开发 (各角色按专属规范执行)
   ↓ Backend Dev → 调用 code-simplifier 优化 → 运行 pytest
   ↓ Frontend Dev → 调用 ui-ux-pro-max 设计 → 运行 npm run build
   ↓ QA Tester → 编写测试 → 运行覆盖率检查

【阶段 4】审查验证
   ↓ Reviewer 审查代码
   ↓ 发现问题 → 返回对应角色修复

【阶段 5】测试执行
   ↓ QA 运行完整测试套件
   ↓ 生成测试报告

【阶段 6】提交汇报
   ↓ Coordinator 生成交付报告
   ↓ git commit & push

【阶段 7】收工总结 (Coordinator)
   ↓ 更新 docs/planning/progress.md
   ↓ 更新诊断报告（如适用）
```

---

## 检查清单模板（可复制使用）

### 任务开始处粘贴

```markdown
## 开工检查

### 通用检查
- [ ] 理解需求
- [ ] 确认边界
- [ ] 检查依赖
- [ ] 环境准备

### 角色专属检查
[根据角色插入对应检查项]
```

### 任务结束处粘贴

```markdown
## 收工检查

### 通用检查
- [ ] 自验证通过
- [ ] 代码格式化
- [ ] 无 TODO 遗留
- [ ] 提交规范
- [ ] 文档更新

### 角色专属检查
[根据角色插入对应检查项]
```

---

## 违规处理

| 违规类型 | 处理方式 |
|----------|----------|
| 未开工检查 | 提醒补充，任务标记为"需改进" |
| 未收工验证 | 测试失败则返回修复 |
| 文档未更新 | 创建待办任务补充 |

---

**本规范适用于所有 Agent Team 成员，确保交付质量一致性。**
