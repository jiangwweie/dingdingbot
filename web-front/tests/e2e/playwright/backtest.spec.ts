/**
 * Playwright E2E 测试 - 回测页面核心流程
 *
 * 测试场景：
 * 1. 页面加载和初始状态
 * 2. 配置回测参数
 * 3. 执行回测
 */
import { test, expect } from '@playwright/test';

test.describe('Backtest Page', () => {
  test.beforeEach(async ({ page }) => {
    // 导航到回测页面
    await page.goto('/backtest');
  });

  test('页面加载成功', async ({ page }) => {
    // 验证页面标题
    await expect(page.locator('h1')).toContainText('回测沙箱');

    // 验证快速配置区存在
    await expect(page.locator('[data-testid="quick-config-section"]')).toBeVisible();
  });

  test('选择币种和周期', async ({ page }) => {
    // 选择币种
    await page.selectOption('[data-testid="symbol-select"]', 'ETH/USDT:USDT');
    await expect(page.locator('[data-testid="symbol-select"]')).toHaveValue('ETH/USDT:USDT');

    // 选择周期
    await page.selectOption('[data-testid="timeframe-select"]', '4h');
    await expect(page.locator('[data-testid="timeframe-select"]')).toHaveValue('4h');
  });

  test('高级配置折叠/展开', async ({ page }) => {
    // 默认折叠
    await expect(page.locator('[data-testid="advanced-config-content"]')).not.toBeVisible();

    // 点击展开
    await page.click('[data-testid="advanced-config-toggle"]');
    await expect(page.locator('[data-testid="advanced-config-content"]')).toBeVisible();
  });

  test('执行回测流程', async ({ page }) => {
    // 等待页面加载
    await page.waitForLoadState('networkidle');

    // 选择币种和周期
    await page.selectOption('[data-testid="symbol-select"]', 'BTC/USDT:USDT');
    await page.selectOption('[data-testid="timeframe-select"]', '1h');

    // 点击执行按钮（应该显示错误，因为日期未选择）
    await page.click('[data-testid="run-backtest-btn"]');

    // 验证错误提示
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
  });
});
