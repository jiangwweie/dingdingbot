# E2E 测试指南

> 本目录包含使用 Puppeteer 进行端到端测试的所有配置和测试文件。

## 目录结构

```
e2e/
├── environment.test.ts       # 环境验证测试（示例）
├── puppeteer.config.js       # Puppeteer 配置
├── jest.config.js            # Jest 配置
├── tsconfig.json             # TypeScript 配置
├── README.md                 # 本文档
└── utils/
    ├── setup.ts              # 全局设置和钩子
    ├── helpers.ts            # 测试辅助函数
    └── factories.ts          # Mock 数据工厂
```

## 快速开始

### 1. 安装依赖

```bash
cd web-front
npm install
```

首次运行会自动下载 Chromium（约 170MB）。

### 2. 启动开发服务器

E2E 测试需要在运行的应用上执行：

```bash
npm run dev
```

### 3. 运行测试

**基本测试**（有头模式，可见浏览器）：
```bash
npm run test:e2e
```

**调试模式**（有头 + 慢动作）：
```bash
npm run test:e2e:debug
```

**CI 模式**（无头 + 重试）：
```bash
npm run test:e2e:ci
```

## 配置说明

### puppeteer.config.js

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `puppeteer.headless` | 无头模式 | CI 环境 `true`，本地 `false` |
| `puppeteer.slowMo` | 慢动作延迟 | 50ms |
| `timeout.test` | 测试超时 | 30000ms |
| `retry.count` | 失败重试次数 | CI: 2, 本地：0 |

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TEST_BASE_URL` | 测试服务器地址 | `http://localhost:3000` |
| `CI` | CI 环境标志 | `false` |

## 编写测试

### 基本结构

```typescript
import { Page } from 'puppeteer';

describe('Feature Name', () => {
  let page: Page;

  beforeAll(() => {
    page = (global as any).page;
  });

  it('should do something', async () => {
    // 导航到页面
    await page.goto(`${global.baseURL}/some-page`);

    // 执行操作
    const element = await page.$('#some-element');
    expect(element).toBeDefined();
  });
});
```

### 使用辅助函数

```typescript
import {
  waitForElement,
  clickElement,
  typeText,
  takeScreenshot
} from './utils/helpers';

it('should interact with form', async () => {
  // 等待元素
  const input = await waitForElement(page, '#email', { visible: true });
  expect(input).not.toBeNull();

  // 输入文本
  await typeText(page, '#email', 'test@example.com');

  // 点击按钮
  await clickElement(page, '#submit-btn');

  // 失败时截图
  await takeScreenshot(page, 'form-submission');
});
```

### 使用数据工厂

```typescript
import { createStrategyConfig, createSignal } from './utils/factories';

it('should create strategy', async () => {
  const strategy = createStrategyConfig({
    name: 'My Test Strategy',
    symbols: ['BTC/USDT:USDT']
  });

  // 使用 strategy 数据进行测试...
});
```

## 辅助函数 API

### setup.ts

| 函数 | 说明 |
|------|------|
| `launchBrowser()` | 启动浏览器 |
| `createPage(browser)` | 创建新页面 |
| `closeBrowser(browser)` | 关闭浏览器 |
| `takeScreenshot(page, name)` | 截图 |
| `mockLogin(page, options)` | 模拟登录 |
| `mockLogout(page)` | 模拟登出 |
| `cleanupTestData(page)` | 清理测试数据 |

### helpers.ts

| 函数 | 说明 |
|------|------|
| `waitForElement(page, selector, options)` | 等待元素出现 |
| `clickElement(page, selector)` | 点击元素 |
| `typeText(page, selector, text)` | 输入文本 |
| `getElementText(page, selector)` | 获取元素文本 |
| `elementExists(page, selector)` | 检查元素是否存在 |
| `waitForNavigation(page)` | 等待导航完成 |
| `waitForRequest(page, urlPattern)` | 等待 API 请求 |
| `sleep(ms)` | 等待指定时间 |

## 调试技巧

### 1. 使用有头模式

```bash
# 关闭 headless 看到浏览器界面
npm run test:e2e:headed
```

### 2. 添加慢动作

在 `puppeteer.config.js` 中增加 `slowMo` 值：

```javascript
puppeteer: {
  launch: {
    slowMo: 200  // 每个操作延迟 200ms
  }
}
```

### 3. 使用 debug 语句

```typescript
// 在测试中添加暂停
await page.waitForSelector('#debug', { state: 'attached' });
```

### 4. 查看截图

失败截图保存在 `e2e/screenshots/` 目录。

## 常见问题

### Chromium 下载失败

使用国内镜像：

```bash
PUPPETEER_DOWNLOAD_HOST=https://npmmirror.com/mirrors puppeteer npm install
```

### 端口被占用

修改 `TEST_BASE_URL` 环境变量：

```bash
TEST_BASE_URL=http://localhost:3001 npm run test:e2e
```

### 超时错误

增加超时时间：

```javascript
// puppeteer.config.js
timeout: {
  test: 60000  // 增加到 60 秒
}
```

## 测试报告

测试完成后生成 HTML 报告：

```
e2e/reports/test-report.html
```

## 下一步

- **E2**: 策略配置页面 E2E 测试
- **E3**: 信号通知功能 E2E 测试
