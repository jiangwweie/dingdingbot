# Agentic Workflow Skills - 配置与使用指南

> **创建日期**: 2026-04-01
> **技能版本**: v1.0
> **适用项目**: 盯盘狗 v3.0 量化交易系统

---

## 已配置的技能清单

### ✅ 已注册技能 (settings.json)

| 技能名称 | 命令 | 用途 |
|---------|------|------|
| `team-coordinator` | `/coordinator` | 团队协调器 - 任务分解与调度 |
| `backend-dev` | `/backend` | 后端开发专家 |
| `frontend-dev` | `/frontend` | 前端开发专家 |
| `qa-tester` | `/qa` | 质量保障专家 |
| `code-reviewer` | `/reviewer` | 代码审查员 |
| `tdd-self-heal` | `/tdd` | TDD 闭环自愈 ⭐ 新增 |
| `type-precision-enforcer` | `/type-check` | 类型与精度宪兵 ⭐ 新增 |

---

## 技能使用说明

### 1. TDD 闭环自愈 (`/tdd`)

**触发方式**:
```
/tdd 实现 DynamicRiskManager 的移动止损功能
契约文档：docs/v3/phase3-risk-state-machine-contract.md
测试用例：UT-005 ~ UT-008
```

**工作流程**:
```
1. 解析契约文档 → 提取测试用例
2. 生成 pytest 测试代码
3. 运行测试 (预期失败)
4. 实现业务代码
5. 运行测试 (自动修复直到通过)
6. 提交代码
```

**文件位置**: `.claude/skills/agentic-workflow/tdd-self-heal/SKILL.md`

---

### 2. 类型与精度宪兵 (`/type-check`)

**触发方式**:
```
/type-check 审查 src/domain/risk_manager.py
```

**或直接运行检查脚本**:
```bash
# float 使用检测
python3 scripts/check_float.py

# TickSize/LotSize 格式化检测
python3 scripts/check_quantize.py
```

**检查项目**:
- ❌ float 污染 (domain/application 层)
- ❌ Decimal 缺少 quantize()
- ❌ CCXT 调用前未格式化
- ⚠️ Pydantic 判别器缺失

**文件位置**: `.claude/skills/agentic-workflow/type-precision-enforcer/SKILL.md`

---

## 待实现的技能 (设计文档已创建)

### 3. 契约双向同步 (Contract-to-Code Sync)

**状态**: 📋 设计完成，待实现
**文档**: `.claude/skills/agentic-workflow/contract-sync/DESIGN.md`

**预期功能**:
- 正向：契约文档 → 生成代码骨架
- 逆向：代码变更 → 自动更新契约文档

### 4. 并发幽灵猎手 (Concurrency Audit)

**状态**: 📋 设计完成，待实现
**文档**: `.claude/skills/agentic-workflow/concurrency-audit/DESIGN.md`

**预期功能**:
- AST 扫描并发反模式
- 持锁时网络 I/O 检测
- 死锁风险分析

### 5. 沙箱时间旅行 (Time-Travel Sandbox)

**状态**: 📋 设计完成，待实现
**文档**: `.claude/skills/agentic-workflow/time-sandbox/DESIGN.md`

**预期功能**:
- 伪造系统时间
- K 线状态快照
- 回测"未来函数"检测

---

## MCP 服务器配置

### 已配置 (全局 `~/.claude/mcp.json`)

| 服务器 | 状态 | 用途 |
|--------|------|------|
| `sqlite` | ✅ 已配置 | 查询 v3_dev.db |
| `filesystem` | ✅ 已配置 | 文件操作 |
| `puppeteer` | ✅ 已配置 | 无头浏览器 |
| `time` | ✅ 已配置 | 时区工具 |
| `duckdb` | ✅ 已配置 | OLAP 分析 |
| `telegram` | ⚠️ 需 Token | 告警通知 |
| `ssh` | ⚠️ 需主机信息 | 远程部署 |
| `sentry` | ⚠️ 需 Token | 异常追踪 |

**配置文件**: `~/.claude/mcp.json`

### 需要填写真实信息的服务器

编辑 `~/.claude/mcp.json` 填写以下内容：

```json
"telegram": {
  "env": {
    "TELEGRAM_BOT_TOKEN": "你的 Token",
    "TELEGRAM_CHAT_ID": "你的频道 ID"
  }
},
"ssh": {
  "env": {
    "SSH_HOST": "你的服务器 IP",
    "SSH_USER": "用户名",
    "SSH_KEY_PATH": "~/.ssh/id_ed25519"
  }
},
"sentry": {
  "env": {
    "SENTRY_ORG": "组织名",
    "SENTRY_PROJECT": "dingpingbot",
    "SENTRY_AUTH_TOKEN": "Token"
  }
}
```

---

## 快速开始

### 使用 TDD 技能开发新功能

```bash
# 1. 调用技能
/tdd 实现移动止损功能

# 2. AI 自动执行
# - 生成测试代码
# - 运行 pytest
# - 实现业务逻辑
# - 自我修复直到通过

# 3. 检查结果
git diff HEAD  # 查看变更
```

### 运行类型检查

```bash
# 方式 1: 使用技能
/type-check 审查 src/domain/

# 方式 2: 直接运行脚本
python3 scripts/check_float.py
python3 scripts/check_quantize.py

# 方式 3: CI/CD 自动运行
# 参见 .github/workflows/type-and-precision-check.yml (待创建)
```

---

## 检查脚本当前状态

### float 检测 (`scripts/check_float.py`)

```
$ python3 scripts/check_float.py
============================================================
float 使用检测 - 量化系统精度检查
============================================================

检查了 28 个 Python 文件

❌ 发现 34 处 float 使用:
  - models.py: 7 处 (score, pattern_score 等)
  - filter_factory.py: 8 处 (float() 调用)
  - strategy_engine.py: 7 处 (score 计算)
  - engulfing_strategy.py: 5 处 (score 计算)
  - config_manager.py: 5 处 (阈值配置)
  - signal_pipeline.py: 1 处 (flush_interval)
  - backtester.py: 2 处 (回测统计)

这些是待修复的技术债 (主要是评分/阈值相关，非金融计算)
```

### TickSize 检测 (`scripts/check_quantize.py`)

```bash
# 运行检测
python3 scripts/check_quantize.py
```

---

## 与现有工作流集成

### planning-with-files 集成

使用技能时自动更新规划文件：

```markdown
# docs/planning/progress.md

## 2026-04-01 Agentic Workflow 配置

### 完成工作
- ✅ 创建 TDD 闭环自愈技能
- ✅ 创建类型与精度宪兵技能
- ✅ 注册技能到 settings.json
- ✅ 创建检查脚本 (check_float.py, check_quantize.py)

### 技术债清单
- float 使用：34 处 (主要是评分/阈值)
- 待实现技能：3 个 (契约同步、并发审计、时间沙箱)
```

### Git 提交规范

```bash
# 技能开发提交
git add .claude/skills/agentic-workflow/
git commit -m "feat(skills): 添加 TDD 闭环自愈技能

- 支持契约文档解析
- 自动生成 pytest 测试
- 自我修复循环
- 最多重试 3 次

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

# 检查脚本提交
git add scripts/check_*.py
git commit -m "feat(ci): 添加类型精度检查脚本

- check_float.py: 检测 domain 层 float 污染
- check_quantize.py: 检测 CCXT 调用格式化
- 允许合理的 float 使用 (评分/阈值)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 故障排查

### 技能未加载

```bash
# 检查 settings.json 配置
cat .claude/settings.json | jq '.skills.local'

# 确认技能文件存在
ls -la .claude/skills/agentic-workflow/
```

### 检查脚本执行失败

```bash
# 确认 Python 环境
source venv/bin/activate
python3 --version  # 需要 3.11+

# 检查脚本权限
chmod +x scripts/check_*.py
```

### MCP 服务器未加载

```bash
# 检查全局配置
cat ~/.claude/mcp.json

# 重启 Claude Code
/exit
claude
```

---

## 参考文档

| 文档 | 位置 |
|------|------|
| MCP 配置指南 | `.claude/MCP-QUICKSTART.md` |
| MCP 环境变量 | `.claude/MCP-ENV-CONFIG.md` |
| 技能设计文档 | `.claude/skills/agentic-workflow/README.md` |
| 项目规范 | `docs/arch/系统开发规范与红线.md` |

---

*维护者：AI Builder*
*项目：盯盘狗 v3.0*
