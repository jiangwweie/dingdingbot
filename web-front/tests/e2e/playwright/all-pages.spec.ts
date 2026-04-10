/**
 * E2E 测试 - 前端全量页面检查（16 个页面）
 *
 * 验证所有主要路由能正常加载、无崩溃、渲染内容。
 * 每个页面会截图用于人工复核。
 */
import { test, expect } from '@playwright/test';

test.describe('Frontend Pages - Full Check', () => {
  const pages = [
    // 监控中心
    { name: 'Dashboard', path: '/dashboard', expectText: /盯盘|Dashboard|dashboard/i },
    { name: 'Signals', path: '/signals', expectText: /信号|Signal|signal/i },
    { name: 'SignalAttempts', path: '/attempts', expectText: /尝试|Attempt|attempt|信号/i },

    // 交易管理
    { name: 'Positions', path: '/positions', expectText: /持仓|Position|position/i },
    { name: 'Orders', path: '/orders', expectText: /订单|Order|order/i },

    // 回测沙箱
    { name: 'Backtest', path: '/backtest', expectText: /回测|Backtest|backtest/i },
    { name: 'BacktestReports', path: '/backtest-reports', expectText: /回测|报告|Report|report/i },
    { name: 'PMSBacktest', path: '/pms-backtest', expectText: /回测|Backtest|PMS|pms/i },
    { name: 'StrategyWorkbench', path: '/strategies', expectText: /策略|Strategy|strategy/i },

    // 配置管理
    { name: 'ConfigManagement', path: '/config', expectText: /配置|Config|config/i },
    { name: 'ConfigStrategies', path: '/config/strategies', expectText: /策略|Strategy|strategy/i },
    { name: 'ConfigSystem', path: '/config/system', expectText: /系统|System|system|配置/i },
    { name: 'ConfigProfiles', path: '/config/profiles', expectText: /配置|Config|profile|Profile/i },

    // 其他
    { name: 'Snapshots', path: '/snapshots', expectText: /快照|Snapshot|snapshot/i },
    { name: 'Account', path: '/account', expectText: /账户|Account|account|资产/i },
  ];

  for (const pageDef of pages) {
    test(`${pageDef.name} (${pageDef.path}) loads correctly`, async ({ page }) => {
      // Navigate and wait for network idle
      const response = await page.goto(pageDef.path, { waitUntil: 'networkidle', timeout: 15000 });

      // Verify HTTP 200
      expect(response?.status()).toBe(200);

      // Verify page rendered — body is non-empty
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.length).toBeGreaterThan(10);

      // Verify recognizable content exists
      await expect(page.locator('body')).toContainText(pageDef.expectText, { timeout: 5000 });

      // Take screenshot for manual review
      await page.screenshot({
        path: `tests/e2e/playwright/screenshots/${pageDef.name.toLowerCase()}-page.png`,
        fullPage: true,
      });
    });
  }
});
