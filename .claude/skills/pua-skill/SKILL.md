---
name: pua
description: PUA (Prompt Upgrade Assistant) - 自动优化用户提示词，添加技术约束、验收标准、边界条件。
license: MIT
---

# PUA - Prompt Upgrade Assistant (提示词升级助手)

## 核心使命

**将简短的用户提示词升级为高质量、结构化的详细提示词**，自动补充：
- 技术约束（根据项目规范）
- 验收标准（可测试的标准）
- 边界条件（异常场景处理）
- 角色设定（专业角色扮演）
- 格式规范（Markdown/JSON 等）

---

## 工作流程

### 阶段 1: 上下文读取

**必须读取的项目文件**:
```
1. CLAUDE.md - 项目核心约束
2. docs/arch/系统开发规范与红线.md - 架构红线
3. .claude/team/backend-dev/SKILL.md - 后端规范
4. .claude/team/frontend-dev/SKILL.md - 前端规范
```

### 阶段 2: 需求分析

**识别任务类型**:
- [ ] 后端开发任务 → 添加 Decimal、asyncio、Clean Architecture 约束
- [ ] 前端开发任务 → 添加 React、TypeScript、TailwindCSS 约束
- [ ] 测试任务 → 添加覆盖率、边界条件要求
- [ ] 架构设计任务 → 添加技术选型、trade-off 分析要求

### 阶段 3: 提示词升级

**升级模板**:

```markdown
## 升级后的提示词

### 角色设定
作为 [角色名称]，请完成以下任务：

### 功能需求
[扩展后的需求描述]

### 技术约束
[根据项目规范自动补充]

1. **数据类型**:
   - 金额/价格必须使用 `decimal.Decimal`（禁止 `float`）
   - 类型注解完整，禁止 `Dict[str, Any]`

2. **异步规范**:
   - 使用 `async/await`，禁止同步阻塞调用
   - `async` 函数中禁止 `time.sleep()`

3. **架构分层**:
   - `domain/` 层禁止导入 I/O 框架（ccxt、aiohttp、fastapi、yaml）
   - 遵循 Clean Architecture 分层原则

### 验收标准
[可测试的标准]

- [ ] 功能实现完整
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 通过 `mypy --strict` 类型检查
- [ ] 通过 `pytest tests/unit/ -v` 测试
- [ ] 代码已使用 `black` 格式化

### 边界条件
[自动补充的边界场景]

- **空值处理**: None/""/[]/{} 是否检查
- **并发安全**: 是否有竞态条件
- **异常处理**: 网络异常/数据库异常是否处理

### 输出要求
[明确的交付物]

- 修改文件：`src/xxx/xxx.py`
- 测试文件：`tests/unit/test_xxx.py`
- 文档更新：`docs/xxx.md`（如需要）

---
**原始提示词**: [用户原始输入]
**升级日期**: [当前时间]
```

---

## 使用场景

### 场景 1: 用户输入简短需求

```
用户输入: "帮我写一个止损功能"

PUA 输出:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
作为量化交易系统的后端开发专家，请实现止损功能：

## 功能需求
1. 支持三种止损类型：
   - 固定金额止损（如每单最多亏 100U）
   - 百分比止损（如最多亏 2%）
   - 追踪止损（盈利后自动上移止损位）

2. 止损触发条件：
   - K 线闭合后检查（is_closed=True）
   - 支持多仓位并发触发

## 技术约束
1. **数据类型**:
   - 止损价位计算必须使用 `decimal.Decimal`
   - 禁止使用 `float` 进行金额计算

2. **异步规范**:
   - 止损检查必须异步执行（`async def check_stop_loss`）
   - 禁止阻塞事件循环

3. **架构分层**:
   - 止损逻辑放在 `src/domain/risk_calculator.py`
   - 数据库操作放在 `src/infrastructure/position_repository.py`

## 验收标准
- [ ] 实现三种止损类型
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 通过 `pytest tests/unit/test_risk_calculator.py -v`
- [ ] 通过 `mypy --strict src/domain/risk_calculator.py`

## 边界条件
- **空值处理**: 仓位为 None 时如何处理
- **并发安全**: 多个仓位同时触发止损时是否竞态
- **异常处理**: 交易所 API 失败时是否重试

## 输出要求
- 修改：`src/domain/risk_calculator.py`
- 测试：`tests/unit/test_risk_calculator.py`
- 文档：`docs/features/stop-loss.md`（如需要）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 场景 2: 用户输入模糊需求

```
用户输入: "前端页面报错了，修一下"

PUA 输出:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
作为前端开发专家，请诊断并修复前端页面报错：

## 问题诊断
1. **错误信息收集**:
   - 请提供浏览器控制台的完整错误堆栈
   - 截图或复制错误信息

2. **问题定位**:
   - 哪个页面报错？（路径：`/strategies`、`/orders` 等）
   - 什么操作触发？（点击按钮、提交表单等）
   - 报错时机？（加载时、提交时、交互时）

## 技术约束
1. **类型安全**:
   - TypeScript 类型定义完整
   - 禁止使用 `any` 类型

2. **React 规范**:
   - 使用函数式组件 + Hooks
   - 遵循 TailwindCSS 样式规范

3. **错误处理**:
   - 添加错误边界（Error Boundary）
   - 用户友好的错误提示

## 验收标准
- [ ] 错误已修复，页面正常工作
- [ ] 添加错误边界防止白屏
- [ ] 通过 `npm run build` 构建
- [ ] 通过 `npm run type-check` 类型检查

## 输出要求
- 修改文件：`gemimi-web-front/src/pages/xxx.tsx`
- 测试文件：`gemimi-web-front/src/__tests__/xxx.test.ts`（如需要）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 智能补充规则

### 根据任务类型自动补充约束

| 任务类型 | 自动补充的约束 |
|---------|--------------|
| **后端开发** | Decimal 精度、asyncio 异步、Clean Architecture 分层、Pydantic 验证 |
| **前端开发** | TypeScript 类型、React Hooks、TailwindCSS 样式、响应式布局 |
| **测试任务** | 覆盖率要求、边界条件、Mock 策略、回归测试 |
| **架构设计** | 技术选型 trade-off、影响范围评估、迁移路径、回滚方案 |
| **Bug 修复** | 根因分析、复现步骤、影响范围、预防措施 |

---

## 与其他 Skills 集成

### 调用时机

| 场景 | 调用 PUA |
|------|---------|
| 用户输入 < 20 字 | ✅ 自动升级 |
| 用户输入模糊不清 | ✅ 自动澄清问题 |
| 用户输入已详细 | ❌ 跳过升级 |
| 子 Agent 任务分配前 | ✅ 升级任务描述 |

### 与 PM 协作

```python
# PM 在分配任务前调用 PUA
upgraded_prompt = Agent(
    subagent_type="pua",
    prompt=f"升级以下任务描述：{original_user_input}"
)

# 然后使用升级后的提示词分配任务
Agent(subagent_type="backend-dev", prompt=upgraded_prompt)
```

---

## 配置示例

**添加到 settings.json**:
```json
{
  "skills": {
    "local": [
      {
        "name": "pua",
        "description": "Prompt Upgrade Assistant - 自动优化用户提示词",
        "path": "./.claude/skills/pua-skill/SKILL.md"
      }
    ]
  }
}
```

**添加为 subagent**:
```json
{
  "subagents": {
    "pua": {
      "name": "提示词升级助手",
      "description": "自动优化用户提示词，添加技术约束、验收标准",
      "model": "sonnet",
      "tools": ["all"],
      "skill": "pua"
    }
  }
}
```

---

## 使用方法

### 方式 1: 作为独立 subagent 调用

```python
Agent(
    subagent_type="pua",
    prompt="帮我写一个止损功能"
)
```

### 方式 2: PM 自动调用

PM 在分配任务前，自动调用 PUA 升级提示词。

---

**版本**: v1.0
**创建日期**: 2026-04-04
**适用项目**: 盯盘狗量化交易系统 v3.0