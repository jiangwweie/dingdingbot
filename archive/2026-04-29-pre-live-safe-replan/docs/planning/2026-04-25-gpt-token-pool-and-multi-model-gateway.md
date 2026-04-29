# GPT Token Pool + New API 多模型网关整合方案

> **创建日期**: 2026-04-25
> **状态**: 待实施
> **目标**: 将 5 个 GPT Plus 订阅 + GLM + 讯飞统一接入 New API 网关，为 Claude Code / Codex 提供高可用多模型代理

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Agent 层                                                     │
│  Claude Code ──→ cc-switch ──┐                               │
│  Codex CLI   ──→ cc-switch ──┤                               │
│                               ▼                               │
│                    New API (localhost:3000)                    │
│                    统一入口 + 令牌 + 渠道轮询                   │
│                               │                               │
│              ┌────────────────┼────────────────┐              │
│              ▼                ▼                ▼              │
│         Sub2API         GLM 渠道          小米/讯飞 渠道       │
│     (localhost:8080)   (直连智谱)        (直连讯飞)            │
│              │                                               │
│     ┌────────┼────────┐                                     │
│     ▼        ▼        ▼                                     │
│  Plus-A   Plus-B   Plus-C/D/E                               │
│  (GPT-4o) (GPT-4o) (GPT-4o)                                 │
└──────────────────────────────────────────────────────────────┘
```

### 组件职责

| 组件 | 仓库 | Stars | 职责 |
|------|------|-------|------|
| **Sub2API** | [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api) | 15.3k | Plus 订阅转 OpenAI 兼容 API，自动 token 刷新 + 账号轮询 |
| **New API** | [QuantumNous/new-api](https://github.com/QuantumNous/new-api) | 28.8k | 多渠道聚合网关，渠道轮询/降级/格式转换/额度看板 |
| **cc-switch** | [farion1231/cc-switch](https://github.com/farion1231/cc-switch) | - | Claude Code / Codex 本地代理切换（已部署） |

---

## 2. 分步部署指南

### 2.1 部署 Sub2API

```bash
mkdir -p ~/sub2api-deploy && cd ~/sub2api-deploy

# 一键脚本部署
curl -sSL https://raw.githubusercontent.com/Wei-Shaw/sub2api/main/deploy/docker-deploy.sh | bash

# 编辑 .env（脚本自动生成）
# 关键变量：
#   POSTGRES_PASSWORD=xxx
#   JWT_SECRET=xxx
#   SERVER_PORT=8080
#   RUN_MODE=simple  （个人用推荐简单模式）

docker compose up -d
```

管理后台：`http://localhost:8080`

**配置 5 个 Plus 账号**：
1. 后台 → 上游账号管理 → 添加账号
2. 类型选 `OAuth`（OpenAI Plus 订阅）
3. 依次填入 5 个账号的 Access Token / Refresh Token
4. Sub2API 自动处理 token 刷新和账号轮询
5. 生成下游 API Key（如 `sk-sub2api-xxx`）

**验证**：
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-sub2api-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}'
```

### 2.2 部署 New API

```bash
mkdir -p ~/new-api-deploy && cd ~/new-api-deploy

# SQLite 模式（个人用足够）
docker run --name new-api -d --restart always \
  -p 3000:3000 \
  -e TZ=Asia/Shanghai \
  -v ./data:/data \
  calciumion/new-api:latest
```

管理后台：`http://localhost:3000`
默认账号：`root` / `123456`（**首次登录立即改密码**）

### 2.3 配置渠道

#### 渠道 1-5：Sub2API Plus 账号

后台 → 渠道管理 → 添加渠道：

| 字段 | 值 |
|------|-----|
| 类型 | OpenAI |
| 名称 | Sub2API-Plus-1 ~ Sub2API-Plus-5 |
| Base URL | `http://localhost:8080` |
| 密钥 | `sk-sub2api-xxx` |
| 模型 | `gpt-4o,gpt-4o-mini,o3-mini` |
| 优先级 | 1（最高） |
| 权重 | 1（均等轮询） |

> 5 个渠道指向同一 Sub2API 端点，Sub2API 内部在 5 个 Plus 账号间轮询。
> 也可拆为 5 个独立 Sub2API key，让 New API 也参与调度。

#### 渠道 6：GLM（智谱）

| 字段 | 值 |
|------|-----|
| 类型 | OpenAI（智谱兼容 OpenAI 格式） |
| 名称 | ZhipuAI-GLM4 |
| Base URL | `https://open.bigmodel.cn/api/paas/v4` |
| 密钥 | GLM API Key |
| 模型 | `glm-4-plus,glm-4-flash` |
| 优先级 | 2（低于 Plus） |
| 权重 | 1 |

#### 渠道 7：小米/讯飞

| 字段 | 值 |
|------|-----|
| 类型 | Anthropic（讯飞走 Anthropic 协议） |
| 名称 | Xunfei-Astron |
| Base URL | `https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic` |
| 密钥 | 讯飞 API Key |
| 模型 | `astron-code-latest` |
| 优先级 | 3（最低，降级用） |
| 权重 | 1 |

### 2.4 生成最终令牌

后台 → 令牌管理 → 添加令牌：

| 字段 | 值 |
|------|-----|
| 名称 | local-dev |
| 额度 | 无限（或按需设上限） |
| 可用模型 | 全部 |

生成后得到 `sk-newapi-xxx`。

### 2.5 Claude Code 接入

**方式 A：通过 cc-switch（推荐）**

1. cc-switch 管理界面 → Provider 管理
2. 添加/修改 Provider：
   - 类型：Anthropic
   - Base URL：`http://localhost:3000`
   - API Key：`sk-newapi-xxx`
3. 开启 failover：`enableFailoverToggle: true`

**方式 B：直接环境变量**

```bash
# ~/.zshrc
export ANTHROPIC_BASE_URL="http://localhost:3000"
export ANTHROPIC_AUTH_TOKEN="sk-newapi-xxx"
```

### 2.6 Codex 接入

修改 `~/.codex/config.toml`：

```toml
model = "gpt-4o"

[model_providers.newapi]
name = "New API Gateway"
base_url = "http://localhost:3000"
env_key = "NEWAPI_API_KEY"
```

```bash
# ~/.zshrc
export NEWAPI_API_KEY="sk-newapi-xxx"
```

---

## 3. 关键机制说明

### 3.1 New API 渠道选择逻辑

1. **同优先级渠道**：按权重随机轮询
2. **请求失败**：自动重试下一个同优先级渠道
3. **所有同优先级失败**：降级到下一优先级
4. **重试次数**：后台 → 系统设置 → 运行设置 → 失败重试次数（建议 3）

### 3.2 Sub2API 账号调度

- **Sticky Session**：同一会话粘滞到同一 Plus 账号
- **并发控制**：每账号并发上限（避免触发 OpenAI 限流）
- **Token 自动刷新**：Refresh Token 到期前自动续期

### 3.3 格式转换

New API 自动格式转换能力：
- Claude Code 发 Anthropic 格式 → New API 自动转 OpenAI 格式 → 转发到 Sub2API
- Codex 发 OpenAI 格式 → New API 直接转发
- GLM 兼容 OpenAI 格式 → 直接透传

---

## 4. 降级链路

```
请求到达 New API
  │
  ├─ 优先级 1：Sub2API Plus 渠道（5 个轮询）
  │   └─ 全部失败 → 降级
  │
  ├─ 优先级 2：GLM 渠道
  │   └─ 失败 → 降级
  │
  └─ 优先级 3：讯飞渠道
      └─ 失败 → 返回错误
```

---

## 5. 风险与注意事项

| 风险 | 说明 | 应对 |
|------|------|------|
| ToS 风险 | Sub2API 将 Plus 订阅转为 API，可能违反 OpenAI ToS | 仅个人使用，不对外分发 |
| Token 过期 | Plus Access Token 有效期有限 | Sub2API 自动刷新，确保 Refresh Token 有效 |
| IP 风险 | OpenAI 可能检测非正常 API 调用模式 | 使用与 ChatGPT 登录相同的 IP |
| HAR 验证 | GPT-4 等模型可能需要 HAR 验证 | Sub2API 已内置处理，首次配置可能需手动获取 |
| 单点故障 | Sub2API 挂了，所有 Plus 渠道不可用 | New API 降级到 GLM/讯飞渠道 |

---

## 6. 部署验证清单

```
□ Sub2API 容器运行正常 (localhost:8080)
□ 5 个 Plus 账号已添加且状态正常
□ Sub2API 可正常响应 gpt-4o 请求
□ New API 容器运行正常 (localhost:3000)
□ 7 个渠道已配置（5×Plus + GLM + 讯飞）
□ 渠道轮询生效（多次请求分配到不同渠道）
□ GLM 渠道可独立响应
□ 讯飞渠道可独立响应
□ New API 令牌已生成
□ Claude Code 通过 cc-switch → New API 可正常请求
□ Codex 通过 New API 可正常请求
□ Plus 渠道失败时自动降级到 GLM
□ 额度看板可正常显示各渠道用量
```

---

## 7. 现有环境基线

### cc-switch 当前状态

- 代理地址：`127.0.0.1:15721`
- 当前 Provider：讯飞星辰 `astron-code-latest`
- failover：**未开启**（`enableFailoverToggle: false`）
- 支持 App：Claude ✅ / Codex ✅

### 历史配置（2026-03-02 备份）

曾使用 Kimi K2 作为 Claude 替代 Provider：
```
ANTHROPIC_BASE_URL = https://api.moonshot.cn/anthropic
ANTHROPIC_MODEL = kimi-k2-thinking-turbo
```

### 已知痛点

cc-switch 日志显示讯飞星辰频繁 429/500：
```
[FWD-003] Provider 讯飞星辰 请求失败: 上游 HTTP 500
  - EngineInternalError: The system is busy, please try again later
  - 429 Too Many Requests, Rate Limit
```

整合后此问题将通过 New API 自动降级到 GLM 渠道解决。

---

## 8. 方案选型记录

### 调研过的方案

| 方案 | 类型 | 优劣 | 结论 |
|------|------|------|------|
| One API | 自托管网关 | 中文生态最全，但路由/降级逻辑简单 | New API 是其超集，选 New API |
| LiteLLM Proxy | 自托管网关 | 路由/降级最强，但 UI 不直观，配置复杂 | 不需要语义路由，暂不引入 |
| OpenRouter | 云服务 | 零运维，但不支持自带 Key，加价 5-15% | 已有订阅，无需额外付费 |
| One Hub | 自托管网关 | One API 增强分支，但稳定性待验证 | New API 功能更全 |
| Portkey Gateway | 自托管/云 | 可观测性最强，但开源版功能有限 | 个人用不需要企业级可观测性 |
| Codex 原生多 Provider | 本地配置 | 零部署，但无降级/额度管理 | 不满足需求 |

### 最终选择：Sub2API + New API 组合

- Sub2API：解决 Plus 订阅转 API 的核心问题
- New API：解决多渠道聚合 + 轮询 + 降级 + 额度管理
- cc-switch：保留作为 Claude Code / Codex 的本地代理层

不引入 LiteLLM 的理由：cc-switch 已覆盖 Claude 侧代理+切换，New API 已覆盖 OpenAI 侧轮询+降级，无需额外一层。
