# GPT 账号池精简方案设计

> **目标**：批量注册 GPT 账号 → 账号池健康检测 → 动态切换降级
> **原则**：最小化组件，最大化自动化

---

## 一、架构设计

### 1.1 博主方案 vs 精简方案

| 博主方案 (8容器) | 精简方案 (2容器) | 说明 |
|-----------------|-----------------|------|
| any-auto-register | ✅ 保留 | 造号核心 |
| inbucket | ❌ 删除 | 用公益临时邮箱替代 |
| CLIProxyAPI | ✅ 保留 | 协议清洗 + 内置轮询 |
| sub2api | ❌ 删除 | CPA 已覆盖 |
| codex2api | ❌ 删除 | CPA 已覆盖 |
| gpt-load | ❌ 删除 | CPA 内置轮询 |
| metapi | ❌ 删除 | 单用户不需要 |
| new-api | ⚠️ 可选 | 需要对外分发时保留 |

**精简架构**：
```
┌─────────────────────────────────────────────────────────┐
│                     用户请求                             │
└─────────────────────┬───────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│              CLIProxyAPI (端口 8317)                     │
│  ┌─────────────────────────────────────────────────┐   │
│  │  账号池管理器                                     │   │
│  │  - 多账号轮询负载均衡                            │   │
│  │  - 失败自动冷却                                  │   │
│  │  - 自动重试切换                                  │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  协议转换层                                       │   │
│  │  /v1/chat/completions → Codex API               │   │
│  │  /v1/messages → Claude API                      │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ 账号 1  │   │ 账号 2  │   │ 账号 N  │
   │ (Free)  │   │ (Free)  │   │ (Free)  │
   └─────────┘   └─────────┘   └─────────┘
        ▲             ▲             ▲
        └─────────────┼─────────────┘
                      │
┌─────────────────────────────────────────────────────────┐
│           any-auto-register (端口 8000)                  │
│  - 自动批量注册                                          │
│  - 账号有效性检测                                        │
│  - Token 自动续期                                        │
│  - 导出 CPA 格式 → 自动注入 CPA                          │
└─────────────────────────────────────────────────────────┘
```

---

## 二、核心组件详解

### 2.0 邮箱批量注册方案（核心痛点）

> **关键问题**：GPT 注册需要有效邮箱接收验证码，邮箱获取是整个流程的瓶颈。

#### 2.0.1 需求规模 vs 方案选择

| 需求规模 | 推荐方案 | 成本 | 自动化程度 |
|---------|---------|------|-----------|
| **≤30 个** | 手搓 + 半自动脚本 | 免费 | 低 |
| **30-100 个** | Cloudflare Worker 自建 | 免费（需域名） | 中 |
| **100-300 个** | LuckMail API | $1-3 | 高 |
| **≥300 个** | LuckMail + 多代理池 | $3-10 | 全自动 |

---

#### 2.0.2 小规模方案（≤30 个）：手搓 + 半自动

**适用场景**：个人自用，一次性需求

**方案 A：临时邮箱网站手动注册**

```
推荐临时邮箱网站：
1. https://temp-mail.org        - 无需注册，自动生成
2. https://10minutemail.com     - 10分钟有效期
3. https://guerrillamail.com    - 1小时有效期
4. https://tempmailaddress.com  - 可自定义前缀
```

**半自动化脚本**：
```python
#!/usr/bin/env python3
"""
semi_auto_register.py - 半自动 GPT 注册助手

流程：
1. 脚本打开临时邮箱网站
2. 用户手动复制邮箱地址
3. 脚本自动填充 GPT 注册表单
4. 用户手动完成验证码
5. 脚本保存账号信息
"""

import pyperclip
import webbrowser
from pathlib import Path

def main():
    accounts = []
    output_file = Path("accounts.txt")

    while True:
        print("\n=== GPT 半自动注册 ===")
        print("1. 打开临时邮箱网站")
        print("2. 输入邮箱地址（已复制到剪贴板）")
        print("3. 输入密码")
        print("4. 退出")

        choice = input("选择: ")

        if choice == "1":
            webbrowser.open("https://temp-mail.org")
            print("请在浏览器中复制邮箱地址")

        elif choice == "2":
            email = pyperclip.paste()
            print(f"邮箱: {email}")
            password = input("输入密码: ")

            accounts.append({
                "email": email,
                "password": password
            })

            print(f"已保存 {len(accounts)} 个账号")

        elif choice == "4":
            # 保存到文件
            with open(output_file, "a") as f:
                for acc in accounts:
                    f.write(f"{acc['email']}:{acc['password']}\n")
            print(f"已保存到 {output_file}")
            break

if __name__ == "__main__":
    main()
```

**方案 B：批量购买 Gmail/Outlook 账号**

```
购买渠道（自行甄别）：
- 淘宝/闲鱼：搜索"Gmail 账号"或"Outlook 账号"
- 价格：约 0.5-2 元/个
- 注意：需确认账号可用性

优点：省时省力
缺点：有风险，账号可能被回收
```

---

#### 2.0.3 中规模方案（30-100 个）：Cloudflare Worker 自建邮箱

**原理**：利用 Cloudflare Email Routing + Worker 接收邮件

**步骤 1：准备域名**

```bash
# 需要一个域名（约 $10/年）
# 推荐购买：Cloudflare Registrar / Namecheap
```

**步骤 2：配置 Cloudflare Email Routing**

```
1. 登录 Cloudflare Dashboard
2. 选择域名 → Email → Email Routing
3. 启用 Email Routing
4. 添加 DNS 记录（自动生成）
```

**步骤 3：创建 Worker 接收邮件**

```javascript
// worker.js - Cloudflare Worker 邮件接收
export default {
  async email(message, env, ctx) {
    const { from, to, subject, body } = message;

    // 存储到 KV
    const emailData = {
      from,
      to,
      subject,
      body: await body.text(),
      timestamp: Date.now()
    };

    await env.EMAILS.put(
      `${to}:${Date.now()}`,
      JSON.stringify(emailData)
    );

    // 提取验证码（简单正则）
    const codeMatch = emailData.body.match(/\b\d{6}\b/);
    if (codeMatch) {
      await env.CODES.put(to, codeMatch[0]);
    }
  }
}
```

**步骤 4：API 接口**

```javascript
// api.js - 获取验证码 API
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const email = url.searchParams.get("email");

  const code = await env.CODES.get(email);

  return new Response(JSON.stringify({
    email,
    code,
    success: !!code
  }), {
    headers: { "Content-Type": "application/json" }
  });
}
```

**步骤 5：批量生成邮箱**

```python
#!/usr/bin/env python3
"""
generate_emails.py - 批量生成随机邮箱地址
"""

import random
import string
import requests

def generate_random_email(domain: str, count: int):
    """生成随机邮箱地址"""
    emails = []
    for _ in range(count):
        prefix = ''.join(random.choices(string.ascii_lowercase, k=10))
        emails.append(f"{prefix}@{domain}")
    return emails

def check_code(api_url: str, email: str) -> str:
    """检查验证码"""
    resp = requests.get(f"{api_url}/api/code?email={email}")
    data = resp.json()
    return data.get("code", "")

# 使用示例
if __name__ == "__main__":
    DOMAIN = "your-domain.com"
    API_URL = "https://mail-worker.your-domain.com"

    # 生成 50 个邮箱
    emails = generate_random_email(DOMAIN, 50)

    for email in emails:
        print(f"邮箱: {email}")
        # 用于 GPT 注册...
```

**成本**：
- 域名：$10/年
- Cloudflare Worker：免费额度足够
- **总计：约 $10/年**

---

#### 2.0.4 大规模方案（≥100 个）：LuckMail API

**LuckMail 特点**：
- 自动购买活跃邮箱
- 支持 Microsoft IMAP 邮箱
- API 自动获取验证码

**API 配置**：

```bash
# 注册 LuckMail 账号
# https://mails.luckyous.com

# 获取 API Key
LUCKMAIL_API_KEY=your_api_key
```

**批量购买邮箱脚本**：

```python
#!/usr/bin/env python3
"""
luckmail_batch.py - LuckMail 批量购买邮箱
"""

import requests
import time

LUCKMAIL_API = "https://mails.luckyous.com/api/v1/openapi"
API_KEY = "your_api_key"

def buy_email():
    """购买一个邮箱"""
    resp = requests.post(
        f"{LUCKMAIL_API}/email/buy",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"type": "ms_imap"}  # Microsoft IMAP
    )
    return resp.json()

def get_code(email: str, timeout: int = 300):
    """等待验证码"""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"{LUCKMAIL_API}/email/code",
            headers={"Authorization": f"Bearer {API_KEY}"},
            params={"email": email}
        )
        data = resp.json()
        if data.get("code"):
            return data["code"]
        time.sleep(5)
    return None

def batch_buy(count: int):
    """批量购买邮箱"""
    emails = []
    for i in range(count):
        print(f"购买第 {i+1}/{count} 个邮箱...")
        result = buy_email()

        if result.get("success"):
            email = result["email"]
            emails.append(email)
            print(f"  ✓ {email}")
        else:
            print(f"  ✗ 失败: {result.get('error')}")

        time.sleep(2)  # 避免频率限制

    return emails

if __name__ == "__main__":
    # 批量购买 100 个邮箱
    emails = batch_buy(100)

    # 保存到文件
    with open("purchased_emails.txt", "w") as f:
        for email in emails:
            f.write(f"{email}\n")

    print(f"\n完成！共购买 {len(emails)} 个邮箱")
```

**成本**：
- 约 $0.01/个邮箱
- 100 个邮箱 ≈ $1
- 300 个邮箱 ≈ $3

---

#### 2.0.5 邮箱方案对比总结

| 方案 | 适用规模 | 成本 | 技术难度 | 稳定性 |
|------|---------|------|---------|--------|
| 临时邮箱网站 | ≤10 | 免费 | 低 | 低 |
| 手搓 + 脚本 | ≤30 | 免费 | 低 | 中 |
| 购买现成账号 | ≤50 | $0.5-2/个 | 低 | 中 |
| CF Worker 自建 | 30-100 | $10/年 | 中 | 高 |
| LuckMail API | ≥100 | $0.01/个 | 中 | 高 |

---

### 2.1 注册机选型对比

| 项目 | 语言 | 邮箱支持 | 代理轮换 | 并发 | 推荐度 |
|------|------|---------|---------|------|--------|
| **GptCrate** | Python | 4种（LuckMail/CF/Outlook/Hotmail007） | ✅ Round-robin | ✅ 多线程 | ⭐⭐⭐⭐⭐ |
| any-auto-register | Python | 7种 | ✅ 静态+动态 | ✅ 可配置 | ⭐⭐⭐⭐ |

**推荐 GptCrate**：代码更精简，注册流程更完整，支持 LuckMail API 自动购买活跃邮箱。

---

### 2.2 GptCrate 注册详解

#### 2.2.1 完整注册流程（12 步）

```
┌─────────────────────────────────────────────────────────────────────┐
│                      GptCrate 注册流程                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. [网络检查] 验证代理 IP 位置（排除 CN/HK）                         │
│       ↓                                                             │
│  2. [邮箱获取] 通过 LuckMail/CF Worker 获取临时邮箱                   │
│       ↓                                                             │
│  3. [OAuth 初始化] 生成 OAuth URL，获取 device_id Cookie              │
│       ↓                                                             │
│  4. [Sentinel Token] 从 sentinel.openai.com 获取反机器人 Token       │
│       ↓                                                             │
│  5. [提交邮箱] POST /api/accounts/authorize/continue                │
│       ↓                                                             │
│  6. [设置密码] 生成强密码，POST /api/accounts/user/register          │
│       ↓                                                             │
│  7. [邮箱验证] 轮询获取 OTP 验证码，提交验证                          │
│       ↓                                                             │
│  8. [创建账号] 提交随机姓名/生日，POST /api/accounts/create_account  │
│       ↓                                                             │
│  9. [静默重登] 清除 Cookie，用邮箱/密码重新认证                       │
│       ↓                                                             │
│  10. [工作区选择] 解析 auth Cookie，选择工作区和组织                  │
│       ↓                                                             │
│  11. [回调处理] 跟随重定向，捕获 OAuth callback URL (code/state)     │
│       ↓                                                             │
│  12. [Token 交换] 提交 callback，获取最终 access_token               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 邮箱方案详解

| 模式 | 配置 | 成本 | 成功率 | 说明 |
|------|------|------|--------|------|
| **LuckMail API** | `EMAIL_MODE=luckmail` | 按次 | 高 | ⭐ 推荐：自动购买活跃邮箱 |
| Cloudflare Worker | `EMAIL_MODE=cf_worker` | 免费 | 中 | 需自建域名 |
| 本地 Outlook | `EMAIL_MODE=local_outlook` | 免费 | 高 | 需提前准备账号 |
| Hotmail007 | `EMAIL_MODE=hotmail007` | 按次 | 中 | 微软邮箱 API |

**LuckMail 配置示例**：
```bash
# .env
EMAIL_MODE=luckmail
LUCKMAIL_API_URL=https://mails.luckyous.com/api/v1/openapi
LUCKMAIL_API_KEY=your_api_key
LUCKMAIL_EMAIL_TYPE=ms_imap           # 微软 IMAP 邮箱
LUCKMAIL_AUTO_BUY=true                # 自动购买
LUCKMAIL_CHECK_WORKERS=20             # 并发检测数
LUCKMAIL_MAX_RETRY=3                  # 最大重试
```

**Cloudflare Worker 自建邮箱**：
```bash
# .env
EMAIL_MODE=cf_worker
MAIL_DOMAIN=your-domain.com
MAIL_WORKER_BASE=https://mail-worker.your-domain.com
MAIL_ADMIN_PASSWORD=your-password
```

#### 2.2.3 代理轮换机制

```python
class ProxyRotator:
    """线程安全的 Round-Robin 代理轮换器"""

    def __init__(self, proxy_list: List[str]):
        self._proxies = list(proxy_list) if proxy_list else []
        self._index = 0
        self._lock = threading.Lock()

    def next(self) -> Optional[str]:
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy
```

**代理配置方式**：
```bash
# 方式 1: 单代理
PROXY=http://127.0.0.1:7890

# 方式 2: 代理列表文件（推荐）
PROXY_FILE=proxies.txt
```

**proxies.txt 格式**：
```
http://user:pass@proxy1.com:8080
socks5://user:pass@proxy2.com:1080
http://user:pass@proxy3.com:8080
```

#### 2.2.4 批量注册配置

```bash
# .env
BATCH_COUNT=10          # 批量注册数量
BATCH_THREADS=3         # 并发线程数（建议 3-5，过高易触发风控）

# 输出配置
TOKEN_OUTPUT_DIR=./tokens   # Token 输出目录
```

**启动命令**：
```bash
# 单次注册
uv run python gpt.py --once

# 批量注册
uv run python start.py

# Web UI（实验版）
uv run python web_ui.py
```

#### 2.2.5 Token 输出格式

```json
// tokens/account_20260419_123456.json
{
  "email": "user123@luckmail.com",
  "password": "Xk9#mP2$vL5@",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "refresh_xxx",
  "expires_at": 1713542400,
  "created_at": "2026-04-19T12:34:56Z"
}
```

---

### 2.3 CLIProxyAPI（协议清洗 + 账号池）

**职责**：
- 将 Codex/ChatGPT 转为标准 OpenAI API
- 多账号轮询负载均衡
- 失败自动冷却和切换

**核心配置**：

```yaml
# config.yaml
host: "0.0.0.0"
port: 8317

api-keys:
  - "sk-your-secret-key"  # 对外访问密钥

auth-dir: "./auths"  # OAuth 认证存储

# 账号池配置
codex-api-key:
  # 账号会由 any-auto-register 自动注入
  # 手动添加示例：
  - api-key: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # Codex Token
    prefix: "pool1"
    models:
      - name: "gpt-4o"
        alias: "gpt-4o-free"
      - name: "gpt-4o-mini"
        alias: "gpt-4o-mini-free"

# 负载均衡配置
request-retry: 3
max-retry-interval: 30
disable-cooling: false  # 开启冷却机制

# 代理配置（可选）
proxy:
  enabled: false
  url: "socks5://127.0.0.1:1080"
```

**内置健康检测机制**：

```
请求流程：
1. 客户端请求 → API Key 校验
2. 调度器选号（轮询/加权）
3. 上游请求
4. 响应处理：
   - 成功：记录成功次数
   - 401：账号进入 banned，冷却 6h
   - 429：账号进入 cooldown，解析 resets_at
   - 超时：标记 timeout，冷却 15min
   - 5xx：标记 error，冷却 15min
5. 失败自动切换下一个账号重试
```

---

## 三、数据流设计

### 3.1 账号生命周期

```
┌─────────────────────────────────────────────────────────────┐
│                      账号生命周期                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [注册] ──→ [激活] ──→ [可用池] ──→ [冷却] ──→ [恢复]      │
│    │          │           │           │           │        │
│    │          │           │           │           │        │
│    │          │           ▼           │           │        │
│    │          │      [失败检测]       │           │        │
│    │          │           │           │           │        │
│    │          │           ├─→ 429 ──→ 冷却 1h ──→ 恢复     │
│    │          │           │                              │  │
│    │          │           ├─→ 401 ──→ banned 6h ────────→│  │
│    │          │           │                              │  │
│    │          │           └─→ 连续失败 3次 ──→ 黑名单 ────→│  │
│    │          │                                          │  │
│    │          └─→ 3天未使用 ──→ 过期检测 ──→ 失效 ────────→│  │
│    │                                                       │
│    └─→ 注册失败 ──→ 丢弃                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 CPA 账号格式

```json
{
  "accounts": [
    {
      "email": "user1@tempmail.com",
      "token": "eyJhbGciOiJIUzI1NiIs...",
      "refresh_token": "refresh_xxx",
      "platform": "chatgpt",
      "created_at": "2026-04-19T10:00:00Z",
      "expires_at": "2026-04-22T10:00:00Z",
      "status": "active",
      "models": ["gpt-4o", "gpt-4o-mini"]
    }
  ]
}
```

---

## 四、自动化脚本

### 4.1 一键部署 (docker-compose.yml)

```yaml
version: "3.8"

services:
  # 造号机 - GptCrate
  gptcrate:
    image: python:3.11-slim
    container_name: gptcrate
    restart: unless-stopped
    working_dir: /app
    ports:
      - "8000:8000"
    volumes:
      - ./gptcrate:/app
      - ./data/tokens:/app/tokens
      - ./config/gptcrate/.env:/app/.env
    command: >
      bash -c "pip install uv && uv sync && uv run python web_ui.py"
    environment:
      - EMAIL_MODE=luckmail
      - LUCKMAIL_API_KEY=${LUCKMAIL_API_KEY}
      - PROXY_FILE=/app/proxies.txt
      - BATCH_COUNT=10
      - BATCH_THREADS=3
      - TOKEN_OUTPUT_DIR=/app/tokens
    networks:
      - token-pool

  # 协议清洗 + 账号池
  cli-proxy:
    image: eceasy/cli-proxy-api:latest
    container_name: cli-proxy
    restart: unless-stopped
    ports:
      - "8317:8317"
    volumes:
      - ./config/cpa:/app/config
      - ./data/tokens:/app/tokens:ro  # 只读访问 Token
      - ./auths:/app/auths
      - ./logs:/app/logs
    environment:
      - CLI_PROXY_CONFIG_PATH=/app/config/config.yaml
      - CLI_PROXY_AUTH_PATH=/app/auths
    depends_on:
      - gptcrate
    networks:
      - token-pool

  # Token 同步服务（自动将 GptCrate 输出同步到 CPA）
  token-sync:
    image: python:3.11-slim
    container_name: token-sync
    restart: unless-stopped
    volumes:
      - ./data/tokens:/tokens:ro
      - ./config/cpa:/config
    command: >
      bash -c "pip install watchdog && python3 /scripts/sync_tokens.py"
    depends_on:
      - gptcrate
      - cli-proxy
    networks:
      - token-pool

networks:
  token-pool:
    driver: bridge
```

### 4.2 Token 同步脚本

```python
#!/usr/bin/env python3
"""
sync_tokens.py - 自动同步 GptCrate 输出到 CLIProxyAPI 配置

监控 tokens/ 目录，当有新 Token 文件生成时：
1. 读取 Token JSON
2. 更新 CPA config.yaml 中的 codex-api-key 列表
3. 触发 CPA 热重载
"""

import json
import yaml
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

TOKENS_DIR = Path("/tokens")
CPA_CONFIG = Path("/config/config.yaml")

class TokenHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.json'):
            self.sync_token(event.src_path)

    def sync_token(self, token_file: str):
        # 读取新 Token
        with open(token_file) as f:
            data = json.load(f)

        # 读取 CPA 配置
        with open(CPA_CONFIG) as f:
            config = yaml.safe_load(f)

        # 添加新账号
        new_account = {
            "api-key": data["access_token"],
            "prefix": data["email"].split("@")[0],
            "models": [
                {"name": "gpt-4o", "alias": "gpt-4o-free"},
                {"name": "gpt-4o-mini", "alias": "gpt-4o-mini-free"}
            ]
        }

        if "codex-api-key" not in config:
            config["codex-api-key"] = []
        config["codex-api-key"].append(new_account)

        # 写回配置
        with open(CPA_CONFIG, 'w') as f:
            yaml.dump(config, f)

        print(f"[SYNC] Added account: {data['email']}")

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(TokenHandler(), str(TOKENS_DIR), recursive=False)
    observer.start()

    print("[SYNC] Watching tokens directory...")
    observer.join()
```

### 4.2 健康检测脚本

```python
#!/usr/bin/env python3
"""
账号池健康检测脚本
定时检测账号有效性，剔除失效账号
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from pathlib import Path

CONFIG = {
    "cpa_url": "http://cli-proxy:8317",
    "test_model": "gpt-4o-mini",
    "test_prompt": "Say 'ok' if you can hear me.",
    "timeout": 30,
    "blacklist_threshold": 3,
}

class AccountHealthChecker:
    def __init__(self):
        self.blacklist = {}  # {account_id: fail_count}

    async def check_account(self, account_id: str, token: str) -> dict:
        """检测单个账号健康状态"""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": CONFIG["test_model"],
            "messages": [{"role": "user", "content": CONFIG["test_prompt"]}],
            "max_tokens": 10
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{CONFIG['cpa_url']}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=CONFIG["timeout"])
                ) as resp:
                    if resp.status == 200:
                        return {"status": "healthy", "account_id": account_id}
                    elif resp.status == 401:
                        return {"status": "banned", "account_id": account_id}
                    elif resp.status == 429:
                        return {"status": "rate_limited", "account_id": account_id}
                    else:
                        return {"status": "error", "account_id": account_id, "code": resp.status}

        except asyncio.TimeoutError:
            return {"status": "timeout", "account_id": account_id}
        except Exception as e:
            return {"status": "error", "account_id": account_id, "error": str(e)}

    def update_blacklist(self, result: dict):
        """更新黑名单"""
        account_id = result["account_id"]
        if result["status"] in ["banned", "error", "timeout"]:
            self.blacklist[account_id] = self.blacklist.get(account_id, 0) + 1
        elif result["status"] == "healthy":
            self.blacklist.pop(account_id, None)

    def should_remove(self, account_id: str) -> bool:
        """判断是否应该移除账号"""
        return self.blacklist.get(account_id, 0) >= CONFIG["blacklist_threshold"]

async def main():
    checker = AccountHealthChecker()
    accounts_file = Path("./data/accounts.json")

    while True:
        accounts = json.loads(accounts_file.read_text())

        for account in accounts["accounts"]:
            if account["status"] != "active":
                continue

            result = await checker.check_account(account["email"], account["token"])
            checker.update_blacklist(result)

            print(f"[{datetime.now()}] {account['email']}: {result['status']}")

            if checker.should_remove(account["email"]):
                account["status"] = "removed"
                print(f"  → 已移除: {account['email']}")

        # 保存更新后的账号列表
        accounts_file.write_text(json.dumps(accounts, indent=2, ensure_ascii=False))

        # 每 10 分钟检测一次
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(main())
```

### 4.3 自动注册调度

```python
#!/usr/bin/env python3
"""
自动注册调度器
根据账号池状态自动补充新账号
"""

import asyncio
import aiohttp
from datetime import datetime

CONFIG = {
    "register_url": "http://any-auto-register:8000",
    "min_pool_size": 10,  # 最小账号池大小
    "max_pool_size": 50,  # 最大账号池大小
    "register_batch": 5,  # 每次注册数量
    "check_interval": 3600,  # 检测间隔（秒）
}

async def get_pool_status() -> dict:
    """获取账号池状态"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CONFIG['register_url']}/api/accounts/status") as resp:
            return await resp.json()

async def trigger_register(count: int):
    """触发批量注册"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CONFIG['register_url']}/api/register/batch",
            json={"count": count}
        ) as resp:
            return await resp.json()

async def main():
    while True:
        status = await get_pool_status()
        active_count = status.get("active_count", 0)

        print(f"[{datetime.now()}] 账号池状态: {active_count}/{CONFIG['max_pool_size']}")

        if active_count < CONFIG["min_pool_size"]:
            need = CONFIG["min_pool_size"] - active_count
            batch = min(need, CONFIG["register_batch"])

            print(f"  → 触发注册: {batch} 个账号")
            result = await trigger_register(batch)
            print(f"  → 注册结果: {result}")

        await asyncio.sleep(CONFIG["check_interval"])

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 五、踩坑点与解决方案

### 5.1 注册阶段

| 坑点 | 原因 | 解决方案 |
|------|------|---------|
| IP 被识别 | 数据中心 IP 被标记 | 使用住宅代理 (IPRoyal/SmartProxy) |
| 邮箱验证失败 | 公益邮箱被风控 | 使用 LuckMail API 或自建 CF Worker |
| 手机验证卡住 | OpenAI 检测虚拟号 | 使用 SMS-Activate 实体卡 |
| 注册成功率低 | 浏览器指纹被识别 | GptCrate 使用 curl_cffi 指纹伪装 |
| CN/HK IP 被拒 | OpenAI 地区限制 | 代理必须是非 CN/HK 地区 |
| 并发过高触发风控 | 短时间大量请求 | BATCH_THREADS 建议 3-5 |

**GptCrate 内置防护**：
- 网络检查：自动验证代理 IP 位置，排除 CN/HK
- 指纹伪装：使用 curl_cffi 模拟浏览器指纹
- Sentinel Token：获取 OpenAI 反机器人 Token

### 5.2 使用阶段

| 坑点 | 原因 | 解决方案 |
|------|------|---------|
| 账号 3 天失效 | Free 号有使用期限 | 定时批量注册补充 |
| 401 突然封号 | 高频调用触发风控 | 降低单账号调用频率 |
| 429 频繁限流 | 单账号请求过快 | 多账号轮询分散请求 |
| Token 过期 | Access Token 有效期短 | 自动 Refresh Token 续期 |

### 5.3 运维阶段

| 坑点 | 原因 | 解决方案 |
|------|------|---------|
| 容器假死 | 内存泄漏/网络问题 | 健康检查 + 自动重启 |
| 数据丢失 | 容器重启未持久化 | Volume 挂载数据目录 |
| 日志爆炸 | 请求日志过多 | 日志轮转 + 定期清理 |
| Token 不同步 | GptCrate 输出未同步到 CPA | token-sync 服务自动同步 |

### 5.4 邮箱服务踩坑

| 邮箱服务 | 坑点 | 解决方案 |
|---------|------|---------|
| LuckMail | 需付费 | 成本低，约 $0.01/次 |
| CF Worker | 需域名 + 技术能力 | 一次配置，长期免费 |
| 公益邮箱 | 易被风控 | 不推荐 |
| yyds 邮箱 | 全失败（跟帖反馈） | 不可用 |

---

## 六、成本估算

### 6.1 一次性投入

| 项目 | 成本 |
|------|------|
| VPS (2核4G) | $5-10/月 |
| 域名 (CF Worker 邮箱用) | $10/年 |

### 6.2 持续成本

| 项目 | 成本 | 说明 |
|------|------|------|
| 住宅代理 | $5-15/月 | 按流量计费，IPRoyal 等 |
| LuckMail 邮箱 | $0.01/次 | 按次计费，或自建 CF Worker 免费 |
| 手机接码 | $0.1-0.5/次 | SMS-Activate，按需使用 |
| **合计** | **$5-20/月** | |

### 6.3 与购买中转对比

| 方案 | 月成本 | 稳定性 | 维护成本 |
|------|--------|--------|---------|
| 自建账号池 | $5-20 | 中 | 高 |
| 购买中转 | $20-50 | 高 | 无 |

### 6.4 成本优化建议

1. **邮箱**：自建 Cloudflare Worker 邮箱 = 免费
2. **代理**：选择按流量计费，避免固定月费
3. **VPS**：选择性价比高的厂商（RackNerd/Vultr）

---

## 七、实施步骤

### Step 1: 环境准备

```bash
# 克隆项目
git clone https://github.com/junjiezhou1122/GptCrate.git
git clone https://github.com/router-for-me/CLIProxyAPI.git

# 创建目录结构
mkdir -p data/tokens config/{gptcrate,cpa} logs auths

# 准备代理列表
cat > gptcrate/proxies.txt << EOF
http://user:pass@proxy1.com:8080
socks5://user:pass@proxy2.com:1080
EOF
```

### Step 2: 配置 GptCrate

```bash
# 创建 .env 配置
cat > config/gptcrate/.env << EOF
# 邮箱配置（推荐 LuckMail）
EMAIL_MODE=luckmail
LUCKMAIL_API_URL=https://mails.luckyous.com/api/v1/openapi
LUCKMAIL_API_KEY=your_luckmail_key
LUCKMAIL_EMAIL_TYPE=ms_imap
LUCKMAIL_AUTO_BUY=true
LUCKMAIL_MAX_RETRY=3

# 代理配置
PROXY_FILE=proxies.txt

# 批量注册
BATCH_COUNT=10
BATCH_THREADS=3

# 输出
TOKEN_OUTPUT_DIR=./tokens
EOF

# 或使用 Cloudflare Worker 自建邮箱
cat > config/gptcrate/.env << EOF
EMAIL_MODE=cf_worker
MAIL_DOMAIN=your-domain.com
MAIL_WORKER_BASE=https://mail-worker.your-domain.com
MAIL_ADMIN_PASSWORD=your-password
PROXY_FILE=proxies.txt
BATCH_COUNT=10
BATCH_THREADS=3
TOKEN_OUTPUT_DIR=./tokens
EOF
```

### Step 3: 配置 CLIProxyAPI

```bash
# 创建 CPA 配置
cat > config/cpa/config.yaml << EOF
host: "0.0.0.0"
port: 8317

api-keys:
  - "sk-your-secret-key"

auth-dir: "./auths"

# 账号池（初始为空，由 token-sync 自动填充）
codex-api-key: []

# 负载均衡
request-retry: 3
max-retry-interval: 30
disable-cooling: false
EOF
```

### Step 4: 启动服务

```bash
# 启动所有容器
docker-compose up -d

# 查看日志
docker-compose logs -f gptcrate
docker-compose logs -f cli-proxy
```

### Step 5: 手动测试注册

```bash
# 进入容器
docker exec -it gptcrate bash

# 单次注册测试
uv run python gpt.py --once

# 查看输出
ls -la tokens/
cat tokens/*.json
```

### Step 6: 批量注册

```bash
# 方式 1: 命令行批量
docker exec -it gptcrate uv run python start.py

# 方式 2: Web UI
open http://localhost:8000
```

### Step 7: 验证 API

```bash
# 测试 API 连通性
curl http://localhost:8317/v1/models \
  -H "Authorization: Bearer sk-your-secret-key"

# 测试对话
curl http://localhost:8317/v1/chat/completions \
  -H "Authorization: Bearer sk-your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

### Step 8: 配置定时任务

```bash
# 添加 crontab
crontab -e

# 每 6 小时批量注册 5 个账号
0 */6 * * * docker exec gptcrate uv run python gpt.py --batch 5

# 每小时健康检测
0 * * * * python3 /path/to/health_checker.py
```

---

## 八、监控告警

### 8.1 关键指标

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| 活跃账号数 | < 5 | 账号池即将耗尽 |
| 注册成功率 | < 50% | 注册流程异常 |
| API 成功率 | < 90% | 账号池质量下降 |
| 平均响应时间 | > 10s | 上游服务异常 |

### 8.2 告警方式

```yaml
# 飞书/Telegram Webhook
alerts:
  - type: feishu
    webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
    triggers:
      - pool_low
      - register_failed
      - api_error
```

---

## 九、总结

### 精简方案优势

1. **组件少**：从 8 个容器精简到 2 个
2. **维护简单**：单一数据流，故障点少
3. **自动化**：注册 + 检测 + 切换全自动
4. **成本低**：月成本 $10-30

### 核心风险

1. **账号存活期短**：Free 号约 3 天，需持续注册
2. **平台风控升级**：OpenAI 可能加强检测
3. **合规风险**：批量注册违反 ToS

### 建议

- 作为**备用方案**，主力使用付费中转
- 保持账号池规模在 20-50 个
- 监控告警及时响应
- 定期检查注册成功率，调整策略
