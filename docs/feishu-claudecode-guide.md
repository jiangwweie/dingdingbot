# 飞书远程控制 Claude Code — 安装与使用指南

## 概述

通过 `feishu-claudecode` 桥接服务，在飞书（含手机端）聊天远程控制本机 Claude Code 执行开发任务，实时查看执行进度和结果。

## 技术架构

```
飞书客户端 → WebSocket 长连接 → Node.js 桥接服务 → Claude Code Agent SDK → 本地执行
                                              ↓
                                        飞书交互卡片（流式更新，1.5s 节流）
```

- **通信方式**：飞书 WebSocket 长连接（无需公网 IP）
- **执行模式**：`bypassPermissions`（无人工审批，自动执行所有工具调用）
- **会话隔离**：按飞书 `chatId` 隔离，每个私聊/群聊独立 session
- **状态持久化**：会话历史保存到 `~/.metabot/sessions-default.json`

## 前置条件

| 项目 | 要求 | 本机状态 |
|---|---|---|
| Node.js | >= 18 | v22.22.0 |
| Claude Code | 已安装且已认证 | v2.1.100（API Key 认证） |
| 飞书应用 | 已创建并发布 | App ID: cli_a927a4374eb89cef |

## 飞书开放平台配置

1. **创建应用**：飞书开放平台 → 创建企业自建应用
2. **记录凭证**：获取 `App ID` 和 `App Secret`
3. **添加能力**：应用能力 → 添加「机器人」
4. **事件订阅**：选「使用长连接接收事件」→ 添加 `im.message.receive_v1`
5. **权限管理**：开通 `im:message`
6. **发布应用**：创建版本 → 发布 → 审核通过（个人测试可设仅自己可见）

## 安装与启动

```bash
git clone https://github.com/xvirobotics/feishu-claudecode.git
cd feishu-claudecode
npm install
# 配置 .env 后启动：
npm run dev
```

## 环境变量配置（.env）

| 变量 | 当前值 | 说明 |
|---|---|---|
| `FEISHU_APP_ID` | `cli_a927a4374eb89cef` | 飞书应用凭证 |
| `FEISHU_APP_SECRET` | `AuYDNC2V...` | 飞书应用凭证 |
| `CLAUDE_DEFAULT_WORKING_DIRECTORY` | `/Users/jiangwei/Documents/demo` | 默认工作目录，飞书端可用 `/cd` 覆盖 |
| `CLAUDE_ALLOWED_TOOLS` | `Read,Edit,Write,Glob,Grep,Bash` | 允许使用的工具列表，去掉 Bash 即为只读模式 |
| `CLAUDE_MAX_TURNS` | `200` | 单次请求最大对话轮数 |
| `CLAUDE_MAX_BUDGET_USD` | `10.0` | 单次请求最大 API 花费（美元） |
| `MEMORY_ENABLED` | `false` | 关闭内置 MetaMemory，避免与外部 Memory MCP 冲突 |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` | `1` | 禁止 Claude 自动保存记忆 |
| `API_PORT` | `9100` | 本地 API 端口 |
| `LOG_LEVEL` | `info` | 日志级别 |

## 使用方式

### 基本流程

1. 飞书中找到机器人（私聊）
2. 发送 `/cd /path/to/project` 设置工作目录（首次使用必须先设置）
3. 发送任意消息开始对话
4. 交互卡片实时更新执行进度

### 可用命令

| 命令 | 说明 |
|---|---|
| `/cd /path/to/project` | 设置工作目录 |
| `/reset` | 清除对话历史，开始新对话（保留工作目录） |
| `/stop` | 中止当前正在执行的任务 |
| `/status` | 查看当前会话状态（含用户 open_id） |
| `/help` | 显示帮助信息 |

### 最佳实践：任务切分工作流

```
1. 发送任务指令 → Claude 执行 → 卡片显示结果
2. /reset → 清除历史，保持工作目录
3. 发送下一个任务指令 → 重复
```

每个任务独立会话，互不干扰。超限后 `/reset` 即可继续。

## 会话超时与恢复机制

### 三种超时

| 类型 | 时间 | 触发条件 |
|---|---|---|
| 空闲超时 | 1 小时 | 1 小时内无任何流式消息产出 |
| 任务硬超时 | 24 小时 | 总执行时间上限 |
| 问题超时 | 5 分钟 | Claude 提问后用户未及时回复（自动回复"用户未及时回复，请自行判断继续"） |

### 超时后状态

**保留的：**
- Claude `session_id`（持久化到 `~/.metabot/sessions-default.json`，TTL 24 小时）
- 累计 token/花费/耗时统计
- 工作目录设置
- Claude 云端对话上下文（完整历史 + 工具调用结果）

**丢失的：**
- 飞书卡片上显示的进度状态（工具调用列表、已输出文本）
- 内存中的临时执行状态

### 超时后继续

**短任务（< 1 小时）**：直接在飞书发下一条消息，桥接服务自动通过 `resume: sessionId` 恢复 Claude 云端会话，对话历史和上下文全部保留。

**长任务（> 1 小时）**：建议让 Claude 在执行过程中把进度写到文件（如 `.claude/PROGRESS.md`），超时恢复后发一句"继续"，Claude 从恢复的 session 中读取进度自动接着干。

### 异常处理

如果恢复时发现 `session_id` 失效（Claude Cloud 服务端返回 "no conversation found"），桥接服务会自动：
1. 清除过期的 `session_id`
2. 用全新 session 重试同一个 prompt
3. 卡片显示 "_Session expired, retrying..._"

### `/reset` 与超时的区别

| 行为 | `/reset` | 超时 |
|---|---|---|
| Claude session_id | **清除** | **保留** |
| 累计统计 | **归零** | **保留** |
| 下一次执行 | **全新 session** | **恢复原有 session** |
| 工作目录 | 保留 | 保留 |

## 安全注意事项

- 以 `bypassPermissions` 模式运行，Claude 对工作目录有完整读写和执行权限
- 通过 `CLAUDE_ALLOWED_TOOLS` 限制可用工具
- 通过 `CLAUDE_MAX_BUDGET_USD` 限制单次花费
- `.env` 已加入 `.gitignore`，不会意外提交到版本控制
- 不建议将机器人指向包含敏感数据的目录

## 使用建议

基于单 Bot 单项目 + Dangerous 模式 + 任务切分的工作习惯：

### 1. 进度文件模式（长任务必备）

对于预计超过 1 小时的任务，在指令中加入要求：

> "执行过程中把当前进度和已完成的内容写到 `.claude/PROGRESS.md`，方便后续恢复时参考"

这样即使 session 失效，Claude 也能通过读取进度文件无缝衔接。

### 2. 项目级 CLAUDE.md

在项目根目录放置 `.claude/CLAUDE.md`，描述：
- 项目技术栈和架构
- 代码规范和命名约定
- 开发流程偏好

每次新 session（包括 `/reset` 后）Claude 都会自动读取，确保行为一致性。

### 3. MCP 配置确认

桥接服务会自动加载：
- `~/.claude/settings.json`（全局配置）
- `<工作目录>/.claude/settings.json`（项目配置）

确认你的 Memory MCP 已在全局配置中注册，飞书端的 Claude 会自动加载使用。

### 4. 本地与飞书工作目录隔离

飞书 bot 默认工作目录为 `/Users/jiangwei/Documents/demo`。如果你在本地也操作同一目录，可能产生文件冲突。建议：
- 飞书 bot 工作期间，本地不做同目录的编辑操作
- 或为飞书 bot 单独分配一个项目目录（通过 `/cd` 设置）

### 5. 文档输出规范

你习惯让 Claude 生成技术文档到 `docs/` 目录下，建议在指令中明确：

> "生成文档保存到 `docs/xxx.md`，使用现有文档结构和命名规范"

这样 Claude 会读取 `docs/` 下已有文件，保持格式一致。

### 6. 任务完成后的清理

每个任务完成后执行 `/reset` 清除历史，避免无关上下文干扰下一个任务。如果任务产生了重要中间产物（如临时文件、测试报告），让 Claude 保存到项目目录后再 reset。

### 多 Bot 模式（一机器人一项目）

当前使用的是**单 bot 模式**（`.env` 配一对凭证 + 一个工作目录）。

如果要运行多个飞书机器人（每个对应一个项目），可切换到**多 bot 模式**：

1. 在 `feishu-claudecode` 目录下创建 `bots.json`
2. 设置环境变量 `BOTS_CONFIG=./bots.json`
3. `.env` 中的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 将被忽略

`bots.json` 格式示例：

```json
{
  "feishuBots": [
    {
      "name": "project-a",
      "feishuAppId": "cli_xxx1",
      "feishuAppSecret": "secret1",
      "defaultWorkingDirectory": "/Users/jiangwei/Documents/project-a"
    },
    {
      "name": "project-b",
      "feishuAppId": "cli_xxx2",
      "feishuAppSecret": "secret2",
      "defaultWorkingDirectory": "/Users/jiangwei/Documents/project-b"
    }
  ]
}
```

每个 bot 的可选配置字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | bot 标识名 |
| `feishuAppId` | string | 是 | 飞书应用 App ID |
| `feishuAppSecret` | string | 是 | 飞书应用 App Secret |
| `defaultWorkingDirectory` | string | 是 | 固定工作目录（bot 自带，无需 `/cd`） |
| `maxTurns` | number | 否 | 继承环境变量或使用自定义值 |
| `maxBudgetUsd` | number | 否 | 继承环境变量或使用自定义值 |
| `model` | string | 否 | 指定模型，如 `claude-opus-4-6` |
| `allowedTools` | string | 否 | 工具列表，逗号分隔 |
| `outputsBaseDir` | string | 否 | 输出文件目录 |

**优势**：
- 每个 bot 自带工作目录，无需手动 `/cd`
- 多个项目可同时跑任务（并行执行）
- 会话历史按 bot 隔离，互不干扰
- 每个 bot 可单独配置模型、轮数上限、工具列表

**注意事项**：
- 所有 bot 凭证集中在一个 `bots.json` 文件中，注意保护
- 所有 bot 共享同一个进程的资源和限制

## 卡片显示优化

### 工具调用精简

默认情况下，Claude 的每次工具调用（Read/Edit/Bash 等）都会在飞书卡片上显示一行 ✅ 记录。当 Claude 分析项目结构时会读取大量文件，导致卡片被刷屏。

已优化为：**只显示最新 5 个工具调用 + 省略计数**。

示例：Claude 读了 12 个文件后，卡片底部显示：
```
... and 7 more tool calls
✅ Read .../memory/project-core-memory.md
✅ Read .../memory/MEMORY.md
✅ Bash
✅ Bash
✅ Bash cd /path && git log ...
```

## 服务管理

| 操作 | 命令 |
|---|---|
| 启动（开发模式） | `cd feishu-claudecode && npm run dev` |
| 停止 | `pkill -f "tsx src/index.ts"` |
| 查看日志 | 终端直接输出，或检查输出文件 |

## 已知限制

- 空闲超时 1 小时 / 硬超时 24 小时，长任务建议配合进度文件使用
- 同一 `chatId` 同时只能执行一个任务
- 飞书侧无发消息频率限制，快速连发可能排队
- 生成的图片自动上传飞书（PNG/JPEG/GIF/WEBP/BMP/SVG/TIFF，单张最大 10MB）
- 24 小时未活跃的 session 会被自动清理，如需更长时间间隔需从头开始
