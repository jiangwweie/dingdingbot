# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: all-pages.spec.ts >> Frontend Pages - Full Check >> StrategyWorkbench (/strategies) loads correctly
- Location: tests/e2e/playwright/all-pages.spec.ts:38:5

# Error details

```
Error: expect(received).toBeGreaterThan(expected)

Expected: > 10
Received:   0
```

# Test source

```ts
  1  | /**
  2  |  * E2E 测试 - 前端全量页面检查（16 个页面）
  3  |  *
  4  |  * 验证所有主要路由能正常加载、无崩溃、渲染内容。
  5  |  * 每个页面会截图用于人工复核。
  6  |  */
  7  | import { test, expect } from '@playwright/test';
  8  | 
  9  | test.describe('Frontend Pages - Full Check', () => {
  10 |   const pages = [
  11 |     // 监控中心
  12 |     { name: 'Dashboard', path: '/dashboard', expectText: /盯盘|Dashboard|dashboard/i },
  13 |     { name: 'Signals', path: '/signals', expectText: /信号|Signal|signal/i },
  14 |     { name: 'SignalAttempts', path: '/attempts', expectText: /尝试|Attempt|attempt|信号/i },
  15 | 
  16 |     // 交易管理
  17 |     { name: 'Positions', path: '/positions', expectText: /持仓|Position|position/i },
  18 |     { name: 'Orders', path: '/orders', expectText: /订单|Order|order/i },
  19 | 
  20 |     // 回测沙箱
  21 |     { name: 'Backtest', path: '/backtest', expectText: /回测|Backtest|backtest/i },
  22 |     { name: 'BacktestReports', path: '/backtest-reports', expectText: /回测|报告|Report|report/i },
  23 |     { name: 'PMSBacktest', path: '/pms-backtest', expectText: /回测|Backtest|PMS|pms/i },
  24 |     { name: 'StrategyWorkbench', path: '/strategies', expectText: /策略|Strategy|strategy/i },
  25 | 
  26 |     // 配置管理
  27 |     { name: 'ConfigManagement', path: '/config', expectText: /配置|Config|config/i },
  28 |     { name: 'ConfigStrategies', path: '/config/strategies', expectText: /策略|Strategy|strategy/i },
  29 |     { name: 'ConfigSystem', path: '/config/system', expectText: /系统|System|system|配置/i },
  30 |     { name: 'ConfigProfiles', path: '/config/profiles', expectText: /配置|Config|profile|Profile/i },
  31 | 
  32 |     // 其他
  33 |     { name: 'Snapshots', path: '/snapshots', expectText: /快照|Snapshot|snapshot/i },
  34 |     { name: 'Account', path: '/account', expectText: /账户|Account|account|资产/i },
  35 |   ];
  36 | 
  37 |   for (const pageDef of pages) {
  38 |     test(`${pageDef.name} (${pageDef.path}) loads correctly`, async ({ page }) => {
  39 |       // Navigate and wait for network idle
  40 |       const response = await page.goto(pageDef.path, { waitUntil: 'networkidle', timeout: 15000 });
  41 | 
  42 |       // Verify HTTP 200
  43 |       expect(response?.status()).toBe(200);
  44 | 
  45 |       // Verify page rendered — body is non-empty
  46 |       const bodyText = await page.locator('body').innerText();
> 47 |       expect(bodyText.length).toBeGreaterThan(10);
     |                               ^ Error: expect(received).toBeGreaterThan(expected)
  48 | 
  49 |       // Verify recognizable content exists
  50 |       await expect(page.locator('body')).toContainText(pageDef.expectText, { timeout: 5000 });
  51 | 
  52 |       // Take screenshot for manual review
  53 |       await page.screenshot({
  54 |         path: `tests/e2e/playwright/screenshots/${pageDef.name.toLowerCase()}-page.png`,
  55 |         fullPage: true,
  56 |       });
  57 |     });
  58 |   }
  59 | });
  60 | 
```