import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E 测试配置
 *
 * 使用示例:
 * - npx playwright test              # 运行所有测试
 * - npx playwright test --headed     # 有头模式（显示浏览器）
 * - npx playwright test --debug      # 调试模式
 * - npx playwright test --ui         # UI 模式
 */
export default defineConfig({
  testDir: './tests/e2e/playwright',
  outputDir: './tests/e2e/playwright/test-results',

  // 超时设置
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },

  // 失败重试
  retries: process.env.CI ? 2 : 0,

  // 并行执行
  workers: process.env.CI ? 1 : undefined,

  // 报告
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],

  use: {
    // 基础 URL
    baseURL: 'http://localhost:3000',

    // 截图
    screenshot: 'only-on-failure',

    // 录屏
    video: 'retain-on-failure',

    // 追踪
    trace: 'retain-on-failure',

    // 浏览器上下文
    viewport: { width: 1280, height: 720 },
    actionTimeout: 10000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 60000,
  },
});
