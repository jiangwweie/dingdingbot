# 盯盘狗 Agent Team 开工/收工规范

**版本**: v4.0 (三阶段工作流 + Memory MCP 混合版)
**最后更新**: 2026-04-04 - 采用三阶段工作流 + Memory MCP 混合方案

---

## ⚠️ 全局强制要求 (红线)

### 所有成员必须使用 `planning-with-files-zh` 管理进度（Memory MCP 混合版）

**禁止使用内置的 `writing-plans` / `executing-plans` 技能**

**强制使用**: `planning-with-files-zh` 技能（Memory MCP 混合版）

**原因**:
- 内置 planning 不创建文件，上下文丢失后进度无法追溯
- `planning-with-files-zh` 强制创建持久化文件到 `docs/planning/` 目录
- 支持会话恢复和进度回溯
- **v4.0 新增**：Memory MCP 混合方案，架构决策永久保留 ⭐

**三文件管理规范（Memory MCP 混合版）**:

| 文件 | 路径 | 用途 | 更新时机 | 保留时长 |
|------|------|------|----------|----------|
| **Memory MCP** | Memory MCP 知识图谱 | 架构决策、技术选型、踩坑记录 | Arch 设计后立即写入 | **永久保留** ⭐ |
| **findings.md** | `docs/planning/findings.md` | 研究发现与技术笔记 | 发现重要技术洞见时立即更新 | **7 天归档** |
| **progress.md** | `docs/planning/progress.md` | 进度日志与会话记录 | 每个会话结束时更新 | **3 天归档** |

**v4.0 Memory MCP 混合特性** ⭐:

1. **Memory MCP 永久保留**:
   - 架构决策（如选择 REST API 而非 WebSocket）
   - 技术选型（如使用 Optuna 而非手动调参）
   - 架构约束（如 Clean Architecture 分层约束）
   - 技术踩坑（如 MCP 配置踩坑记录）
   - **效果**: 永久追溯，上下文丢失后仍可恢复 ⭐⭐⭐

2. **progress.md 分段读取**:
   - 仅保留最近 3 天详细日志
   - 超过 3 天自动归档到 `archive/progress-archive.md`
   - **效果**: 119K → 30K（减少 89K）

3. **findings.md 智能匹配**:
   - 按主题标签分类（asyncio, api, test, frontend）
   - 开工时仅读取相关发现（智能匹配标签）
   - **效果**: 82K → 10K（减少 72K）

**违反处理**: QA 在测试时必须检查是否使用了 `planning-with-files-zh`，未使用则标记为 P0 问题。

**相关技能**:
- `/kaigong` (v8.0 Memory MCP 混合版) - 开工时读取 Memory MCP + progress + findings
- `/shougong` (v5.0 Memory MCP 混合版) - 收工时写入 Memory MCP（今日总结）+ 自动归档

**废弃技能**:
- ~~`/handoff`~~ - 已废弃，用暂停关键词触发替代（用户输入"暂停"/"午休"/"休息"等关键词自动更新文档）

---

## 团队架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Project Manager (统一入口)                    │
│              (用户沟通 / 进度追踪 / 代码提交)                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│  Product Mgr    │ │   Architect     │ │        PM                │
│  (产品经理)     │ │   (架构师)      │ │     (项目经理)            │
│ - 需求收集      │ │ - 架构设计      │ │ - 任务分解              │
│ - 优先级排序    │ │ - 契约设计      │ │ - 并行调度              │
│ - 用户故事      │ │ - 影响评估      │ │ - 进度追踪              │
└─────────────────┘ └─────────────────┘ └─────────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────┐
                    │                          │                  │
                    ▼                          ▼                  ▼
           ┌───────────────┐        ┌───────────────┐   ┌──────────────────┐
           │  Backend Dev  │        │  Frontend Dev │   │   QA Tester      │
           │   (后端)      │        │    (前端)     │   │    (测试)        │
           └───────────────┘        └───────────────┘   └──────────────────┘
                    │                          │                  │
                    └──────────────────────────┼──────────────────┘
                                               ▼
                                      ┌─────────────────┐
                                      │  QA (含代码审查) │
                                      │    (审查员)     │
                                      └─────────────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Diagnostic      │
                                      │ Analyst         │
                                      │ (诊断分析师)     │
                                      └─────────────────┘
```

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
  │      PM       │ │  Backend Dev  │ │  Frontend Dev │
  │  专属规范     │ │  专属规范     │ │  专属规范     │
  └───────────────┘ └───────────────┘ └───────────────┘
                        │
                        ▼
                ┌───────────────┐
                │   QA Tester   │
                │ (含代码审查)  │
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
cd gemimi-web-front && npm run build  # 如已配置
npm run lint  # 如已配置
```

---

## 角色专属规范

### Product Manager (PdM) 专属

**文件位置**: `.claude/team/product-manager/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **需求背景**: 已理解 Who/What/Why
- [ ] **目标用户**: 已识别使用场景和人群
- [ ] **业务价值**: 已尝试量化（如可能）
- [ ] **竞争方案**: 已考虑现有解决方案
- [ ] **验收标准**: 已草拟 AC 列表
```

#### 🔴 收工时检查清单
```markdown
- [ ] **PRD 文档**: `docs/products/<feature>-brief.md` 已创建
- [ ] **用户故事**: 格式完整（As a... I want... So that...）
- [ ] **验收标准**: AC 列表清晰可测试
- [ ] **优先级评估**: RICE/WSJF 评分已完成
- [ ] **MVP 范围**: Must/Nice/Out 明确区分
- [ ] **需求池更新**: `docs/products/backlog.md` 已更新
```

---

### Architect (Arch) 专属

**文件位置**: `.claude/team/architect/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **PRD 阅读**: 已阅读产品需求 brief
- [ ] **约束识别**: 明确技术/时间/资源约束
- [ ] **现状分析**: 已分析现有系统架构
- [ ] **关联系统**: 识别可能受影响的模块
```

#### 🔴 收工时检查清单
```markdown
- [ ] **ADR 文档**: `docs/arch/<feature>-design.md` 已创建
- [ ] **OpenAPI Spec**: `docs/contracts/api-spec.yaml` 已生成 ⭐
- [ ] **契约验证**: 6 项验证清单已通过 ⭐
  - [ ] 所有端点已定义
  - [ ] 请求/响应模型已完整
  - [ ] 错误码已完整（F/C/W 系列）
  - [ ] 枚举值已完整
  - [ ] 数据类型已明确（Decimal 用 string）
  - [ ] 必填/可选字段已标注
- [ ] **契约表**: 接口契约表已完成（`docs/designs/<feature>-contract.md`）
- [ ] **Schema 对齐**: Pydantic ↔ TypeScript 类型已对齐
- [ ] **关联影响评估**: 已评估对现有模块的影响
- [ ] **技术债记录**: 新增技术债已记录（如有）
- [ ] **移交 PM**: 已通知项目经理可以开始任务分解
```

---

### Project Manager (PM) 专属

**文件位置**: `.claude/team/project-manager/SKILL.md`

#### 🚨 三条红线（违反=P0）

```
1. 【禁止代替执行】启动子Agent后，禁止PM自己写代码/改代码/跑测试
2. 【禁止串行】无依赖任务必须并行启动（同一消息中多个Agent调用）
3. 【禁止空返回】子Agent必须有工具调用记录，否则视为失败重试
```

详细并行调度模板见 SKILL.md 第5节。

#### 🟢 开工前检查清单
```markdown
- [ ] **需求确认**: 已确认需求来源（PdM PRD 或用户直接输入）
- [ ] **架构确认**: 已阅读架构设计文档（如有）
- [ ] **契约确认**: 已阅读接口契约表（如有）
- [ ] **资源确认**: 确认可用角色（Backend/Frontend/QA）
```

#### 🔴 收工时检查清单
```markdown
- [ ] **集成验证**: 所有子任务测试通过
- [ ] **交付报告**: `docs/delivery/<feature>-report.md` 已生成
- [ ] **进度更新**: `docs/planning/progress.md` 已更新
- [ ] **代码推送**: 已 git add/commit/push
- [ ] **用户验收**: 已通知用户验收
```

#### ⚠️ 用户确认环节
在任务分解完成后，必须请求用户确认：
1. 产品范围是否合理
2. 技术方案是否接受
3. 任务计划（工时、排期）是否批准

用户确认后，才能进入执行阶段。

---

### Backend Dev 专属

**文件位置**: `.claude/team/backend-dev/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (如有)
- [ ] **OpenAPI Spec 阅读确认**: 已阅读 docs/contracts/api-spec.yaml ⭐
- [ ] **接口确认**: 明确请求/响应 Schema
- [ ] **类型导入验证**: 已从 OpenAPI Spec 生成类型定义 ⭐
- [ ] **模型定位**: 确定需要修改的文件路径
- [ ] **测试定位**: 确定需要编写的测试文件
```

#### 🔴 收工时检查清单
```markdown
- [ ] **单元测试**: 新功能测试覆盖率 ≥ 80%
- [ ] **类型验证**: Pydantic 模型验证通过
- [ ] **契约一致性**: 实现与 OpenAPI Spec 一致 ⭐
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

# 验证类型定义来自 OpenAPI Spec ⭐
grep -r "from generated_client import" src/
```

---

### Frontend Dev 专属

**文件位置**: `.claude/team/frontend-dev/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (Props 定义)
- [ ] **OpenAPI Spec 阅读确认**: 已阅读 docs/contracts/api-spec.yaml ⭐
- [ ] **UI 确认**: 明确组件交互流程
- [ ] **组件定位**: 确定需要修改的组件文件
- [ ] **类型导入验证**: 已从 OpenAPI Spec 导入类型定义 ⭐
  ```bash
  # 生成 TypeScript 类型
  openapi-typescript docs/contracts/api-spec.yaml > gemimi-web-front/src/types/api.ts
  ```
```

#### 🔴 收工时检查清单
```markdown
- [ ] **组件渲染**: 组件可正常渲染无报错
- [ ] **类型检查**: TypeScript 无类型错误
- [ ] **契约一致性**: 实现与 OpenAPI Spec 一致 ⭐
- [ ] **样式验证**: 响应式布局正常
- [ ] **设计优化**: 已调用 `ui-ux-pro-max` (如需要)
- [ ] **代码简化**: 已调用 `code-simplifier` 优化 (如需要)
```

**验证命令**:
```bash
cd gemimi-web-front

# 类型检查
npm run type-check

# 构建验证
npm run build

# 样式检查
npm run lint

# 验证类型定义来自 OpenAPI Spec ⭐
grep -r "from '@/types/api'" src/
```

---

### QA Tester 专属

**文件位置**: `.claude/team/qa-tester/SKILL.md`

#### 🟢 开工前检查清单
```markdown
- [ ] **契约阅读**: 已阅读 API 契约表 (测试范围)
- [ ] **OpenAPI Spec 阅读确认**: 已阅读 docs/contracts/api-spec.yaml ⭐
- [ ] **数据准备**: 已准备测试数据和 Mock
- [ ] **测试定位**: 确定需要编写的测试文件
- [ ] **工具确认**: 确认需要调用的测试技能
```

#### 🔴 收工时检查清单
```markdown
- [ ] **测试报告**: 已生成测试通过率报告
- [ ] **覆盖率达标**: 新增代码覆盖率 ≥ 80%
- [ ] **回归测试**: 现有测试全部通过
- [ ] **契约一致性验证**: 实现与 OpenAPI Spec 一致 ⭐
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

# 验证 API 响应与 OpenAPI Spec 一致 ⭐
# 使用 schemathesis 进行契约测试
pip install schemathesis
st run docs/contracts/api-spec.yaml --base-url http://localhost:8000
```

---

### QA Tester 附加：代码质量审查

QA 在测试通过后，附带执行以下审查检查：

#### 🟢 审查检查清单
```markdown
- [ ] **架构检查**: Clean Architecture 分层验证通过
- [ ] **契约一致性**: 实现与 OpenAPI Spec 一致 ⭐
- [ ] **安全检查**: 无安全隐患 (命令注入、SQL 注入等)
- [ ] **类型检查**: Pydantic 类型定义完整，无 Dict[str, Any]
- [ ] **Decimal 精度**: 金额计算使用 Decimal
- [ ] **异步规范**: 无 time.sleep() 阻塞
```

**验证命令**:
```bash
# 运行测试验证
pytest tests/unit/ -v --tb=short
# 代码风格检查
flake8 src/ tests/
```

---

## 完整工作流程示例 (v4.0 - 三阶段工作流 + Memory MCP 混合版)

### 场景：开发"策略预览功能"（复杂任务）

```
【阶段 1】需求沟通（头脑风暴，强制交互式）

  执行方式：Foreground（用户可见）
  触发命令：/product-manager

  执行步骤：
    1.1 PdM 需求澄清（至少 3 个问题）
    1.2 用户确认需求理解（交互式）
    1.3 PdM 输出 PRD 文档

  输出文档：
    - docs/products/<feature>-brief.md（PRD）
    - Memory MCP（需求背景）

  用户审查点：需求理解确认 ⭐

  暂停触发：用户输入"暂停"/"午休"/"休息"等关键词
    → 自动更新 progress.md + findings.md + Memory MCP
    → Git 提交（不推送）


【阶段 2】架构设计 + 契约生成 + 开发 + 单元测试

  执行方式：Foreground（用户可见）
  触发命令：/architect → /pm

  执行步骤：
    2.1 Arch 架构设计（强制输出 OpenAPI Spec）⭐
        - 输出：ADR + OpenAPI Spec（docs/contracts/api-spec.yaml）⭐
        - 验证：6 项验证清单（所有端点、模型、错误码、枚举、类型、字段）⭐
        - Memory MCP：立即写入架构决策

    2.2 契约生成子任务（新增）⭐
        - 后端：从 OpenAPI Spec 生成类型定义 + Mock 服务器
          ```bash
          # 生成 Python 类型定义
          pip install openapi-python-client
          openapi-python-client generate --path docs/contracts/api-spec.yaml

          # 启动 Mock API 服务器
          npm install -g @stoplight/prism-cli
          prism mock docs/contracts/api-spec.yaml
          ```
        - 前端：从 OpenAPI Spec 导入类型定义
          ```bash
          # 生成 TypeScript 类型
          npm install -D openapi-typescript
          openapi-typescript docs/contracts/api-spec.yaml > gemimi-web-front/src/types/api.ts
          ```
        - 验证：契约文件生成成功，前后端类型一致 ⭐

    2.3 用户审查架构方案（交互式）
        - 审查 ADR + OpenAPI Spec + 契约生成结果
        - 用户回复"确认" → 继续
        - 用户回复"修改" → 返回 2.1

    2.4 PM 任务分解（自动）
        - 识别并行簇
        - 创建任务清单（TaskCreate）并标注依赖（TaskUpdate + addBlockedBy）

    2.5 Backend + Frontend 并行开发
        - Foreground 执行（用户可见进度）
        - 使用 Agent 工具并行调度
        - ⚠️ 禁止自己定义接口类型，必须从 OpenAPI Spec 导入 ⭐

    2.6 QA 单元测试
        - 后端单元测试（pytest）
        - 前端组件测试（React Testing Library）

    2.7 QA 实时审查（每个模块完成后）
        - 检查接口是否符合 OpenAPI Spec ⭐

  用户确认点：测试前确认（耗时 30-60 分钟）⭐

  输出文档：
    - 代码文件（src/, gemimi-web-front/）
    - 单元测试文件（tests/unit/）
    - docs/contracts/api-spec.yaml（OpenAPI Spec）⭐
    - docs/designs/<feature>-contract.md（契约表）
    - Memory MCP（架构决策）

  暂停触发：用户输入"暂停"/"午休"/"休息"等关键词
    → 自动更新 progress.md + findings.md + Memory MCP
    → Git 提交（不推送）


【阶段 3】集成测试 + 代码审查 + 交付

  执行方式：Foreground（用户可见）
  触发命令：/pm → /shougong

  执行步骤：
    3.1 QA 集成测试
        - 前端+后端 API 交互（Mock API）
        - 数据库集成测试

    3.2 QA E2E 测试（Playwright）
        - 关键路径覆盖

    3.3 QA 最终审查
        - 架构一致性检查
        - 安全隐患识别（OWASP Top 10）
        - 代码质量评估

    3.4 PM 交付汇报
        - 生成交付报告
        - 汇报完成情况

    3.5 收工（自动）
        - 更新 progress.md + findings.md
        - 写入 Memory MCP（今日总结）
        - Git 提交 + 推送
        - 自动归档旧文档（超过 7 天交接文档，超过 3 天进度日志）

  输出文档：
    - 测试报告（docs/test-reports/）
    - 交付文档（docs/delivery/）
    - Git 推送

  用户验收点：PM 汇报，用户验收 ⭐
```

---

## 交互式沟通检查点 (v4.0 - 三阶段)

| 阶段 | 负责人 | 检查点 | 产出物 |
|------|--------|--------|--------|
| **阶段 1** | PdM | 需求澄清对话，至少 3 个问题 | 需求理解确认 + PRD 文档 |
| **阶段 2** | Arch | 架构方案审查 + OpenAPI Spec 验证 ⭐ | 技术方向确认 + ADR + OpenAPI Spec ⭐ |
| **阶段 2** | Arch/Backend/Frontend | 契约生成验证（类型定义 + Mock 服务器）⭐ | 契约文件生成成功 ⭐ |
| **阶段 2** | PM | 测试前确认（耗时 30-60 分钟） | 测试执行批准 ⭐ |
| **阶段 3** | PM | 交付汇报，用户验收 | 交付确认 |

**核心原则**:
- **先对话，后文档** - 阶段 1 强制交互式沟通（头脑风暴）
- **先契约，后开发** - 阶段 2 强制 OpenAPI Spec + 契约生成 ⭐⭐⭐
- **先共创，后决策** - 阶段 2 架构方案选项与用户共创
- **关键点暂停** - 阶段 2 架构设计后暂停等待用户审查
- **文档是对话的产物** - 文档是对话结果的记录
- **Memory MCP 永久保留** - 架构决策永久追溯 ⭐

---

## 角色职责速查表

| 事项类型 | 负责人 | 说明 |
|---------|--------|------|
| **需求收集** | PdM | 新功能、改进建议 |
| **需求优先级** | PdM | 决定先做哪个 |
| **任务安排** | PM | 已确认需求的执行计划 |
| **进度查询** | PM | 现在做到哪了 |
| **技术方案** | Arch | 架构设计、技术选型 |
| **关联影响评估** | Arch | 变更对现有系统的影响 |
| **文档归档** | 各角色 | 各自负责对应文档 |
| **会话日志** | PM | progress.md 更新 |
| **代码提交** | PM | git commit/push |
| **交付验收** | PM | 生成交付报告 |
| **Bug 报告** | PdM(体验) / Arch(技术) | 影响评估 |
| **Bug 修复** | PM | 分配给 Dev 执行 |

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
