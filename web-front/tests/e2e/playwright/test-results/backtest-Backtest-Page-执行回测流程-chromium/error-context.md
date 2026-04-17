# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: backtest.spec.ts >> Backtest Page >> 执行回测流程
- Location: tests/e2e/playwright/backtest.spec.ts:44:3

# Error details

```
TimeoutError: page.click: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('[data-testid="run-backtest-btn"]')
    - locator resolved to <button disabled data-testid="run-backtest-btn" class="w-full py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 shadow-lg bg-gray-200 text-gray-400 cursor-not-allowed">…</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
      - waiting 100ms
    19 × waiting for element to be visible, enabled and stable
       - element is not enabled
     - retrying click action
       - waiting 500ms

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e6]:
      - generic [ref=e7]:
        - generic [ref=e8]:
          - generic [ref=e9]: 🐶
          - generic [ref=e10]: 盯盘狗🐶
        - navigation [ref=e11]:
          - generic [ref=e12]:
            - button "监控中心" [ref=e13]:
              - img [ref=e14]
              - generic [ref=e16]: 监控中心
              - img [ref=e17]
            - generic [ref=e19]:
              - link "仪表盘" [ref=e20] [cursor=pointer]:
                - /url: /dashboard
                - img [ref=e21]
                - text: 仪表盘
              - link "信号" [ref=e23] [cursor=pointer]:
                - /url: /signals
                - img [ref=e24]
                - text: 信号
              - link "尝试溯源" [ref=e25] [cursor=pointer]:
                - /url: /attempts
                - img [ref=e26]
                - text: 尝试溯源
          - button "交易管理" [ref=e36]:
            - img [ref=e37]
            - generic [ref=e40]: 交易管理
            - img [ref=e41]
          - button "回测沙箱" [ref=e44]:
            - img [ref=e45]
            - generic [ref=e47]: 回测沙箱
            - img [ref=e48]
          - button "配置管理" [ref=e51]:
            - img [ref=e52]
            - generic [ref=e53]: 配置管理
            - img [ref=e54]
          - button "系统设置" [ref=e57]:
            - img [ref=e58]
            - generic [ref=e61]: 系统设置
            - img [ref=e62]
      - generic [ref=e64]:
        - generic [ref=e67]: 20s 后刷新
        - button "系统配置" [ref=e68]:
          - img [ref=e69]
  - main [ref=e72]:
    - generic [ref=e73]:
      - generic [ref=e74]:
        - generic [ref=e75]:
          - heading "回测沙箱" [level=1] [ref=e76]
          - paragraph [ref=e77]: 配置策略组合，执行历史数据回测验证
        - generic [ref=e78]:
          - button "回测历史" [ref=e79]:
            - img [ref=e80]
            - text: 回测历史
          - button "从策略工作台导入" [ref=e84]:
            - img [ref=e85]
            - text: 从策略工作台导入
      - generic [ref=e88]:
        - img [ref=e90]
        - generic [ref=e92]:
          - heading "如何使用回测沙箱" [level=3] [ref=e93]
          - generic [ref=e94]:
            - paragraph [ref=e95]:
              - strong [ref=e96]: 第 1 步：
              - text: 前往
              - button "策略配置" [ref=e97]
              - text: 创建或编辑策略组合
            - paragraph [ref=e98]:
              - strong [ref=e99]: 第 2 步：
              - text: 使用"预览"功能快速验证策略逻辑（单根 K 线）
            - paragraph [ref=e100]:
              - strong [ref=e101]: 第 3 步：
              - text: 点击右上角"从策略工作台导入"，选择已保存的策略执行历史回测
      - generic [ref=e102]:
        - generic [ref=e103]:
          - generic [ref=e104]:
            - generic [ref=e105]:
              - heading "快速配置" [level=2] [ref=e106]:
                - img [ref=e107]
                - text: 快速配置
              - generic [ref=e109]: Level 3
            - generic [ref=e110]:
              - generic [ref=e111]: 🪙 交易对
              - combobox [ref=e112]:
                - option "BTC/USDT:USDT" [selected]
                - option "ETH/USDT:USDT"
                - option "SOL/USDT:USDT"
                - option "BNB/USDT:USDT"
                - option "XRP/USDT:USDT"
                - option "ADA/USDT:USDT"
                - option "DOGE/USDT:USDT"
                - option "MATIC/USDT:USDT"
            - generic [ref=e113]:
              - generic [ref=e114]: 📊 时间周期
              - combobox [ref=e115]:
                - option "1 分钟"
                - option "5 分钟"
                - option "15 分钟"
                - option "1 小时" [selected]
                - option "4 小时"
                - option "1 天"
                - option "1 周"
            - generic [ref=e116]:
              - generic [ref=e117]: 📅 时间范围
              - generic [ref=e118]:
                - generic [ref=e119]:
                  - button "今天" [ref=e120]
                  - button "最近 7 天" [ref=e121]
                  - button "最近 30 天" [ref=e122]
                  - button "更多" [ref=e123]:
                    - text: 更多
                    - img [ref=e124]
                - generic [ref=e127]:
                  - img [ref=e128]
                  - generic [ref=e131]: "-"
                  - generic [ref=e132]: →
                  - generic [ref=e133]: "-"
          - generic [ref=e135] [cursor=pointer]:
            - generic [ref=e136]:
              - img [ref=e137]
              - generic [ref=e140]: 高级配置
            - img [ref=e141]
          - button "一键执行回测" [disabled] [ref=e143]:
            - img [ref=e144]
            - text: 一键执行回测
        - generic [ref=e147]:
          - img [ref=e149]
          - heading "等待执行回测" [level=3] [ref=e151]
          - paragraph [ref=e152]: 配置左侧的时间范围、交易对和策略组合，然后点击"一键执行回测"按钮开始分析
```

# Test source

```ts
  1  | /**
  2  |  * Playwright E2E 测试 - 回测页面核心流程
  3  |  *
  4  |  * 测试场景：
  5  |  * 1. 页面加载和初始状态
  6  |  * 2. 配置回测参数
  7  |  * 3. 执行回测
  8  |  */
  9  | import { test, expect } from '@playwright/test';
  10 | 
  11 | test.describe('Backtest Page', () => {
  12 |   test.beforeEach(async ({ page }) => {
  13 |     // 导航到回测页面
  14 |     await page.goto('/backtest');
  15 |   });
  16 | 
  17 |   test('页面加载成功', async ({ page }) => {
  18 |     // 验证页面标题
  19 |     await expect(page.locator('h1')).toContainText('回测沙箱');
  20 | 
  21 |     // 验证快速配置区存在
  22 |     await expect(page.locator('[data-testid="quick-config-section"]')).toBeVisible();
  23 |   });
  24 | 
  25 |   test('选择币种和周期', async ({ page }) => {
  26 |     // 选择币种
  27 |     await page.selectOption('[data-testid="symbol-select"]', 'ETH/USDT:USDT');
  28 |     await expect(page.locator('[data-testid="symbol-select"]')).toHaveValue('ETH/USDT:USDT');
  29 | 
  30 |     // 选择周期
  31 |     await page.selectOption('[data-testid="timeframe-select"]', '4h');
  32 |     await expect(page.locator('[data-testid="timeframe-select"]')).toHaveValue('4h');
  33 |   });
  34 | 
  35 |   test('高级配置折叠/展开', async ({ page }) => {
  36 |     // 默认折叠
  37 |     await expect(page.locator('[data-testid="advanced-config-content"]')).not.toBeVisible();
  38 | 
  39 |     // 点击展开
  40 |     await page.click('[data-testid="advanced-config-toggle"]');
  41 |     await expect(page.locator('[data-testid="advanced-config-content"]')).toBeVisible();
  42 |   });
  43 | 
  44 |   test('执行回测流程', async ({ page }) => {
  45 |     // 等待页面加载
  46 |     await page.waitForLoadState('networkidle');
  47 | 
  48 |     // 选择币种和周期
  49 |     await page.selectOption('[data-testid="symbol-select"]', 'BTC/USDT:USDT');
  50 |     await page.selectOption('[data-testid="timeframe-select"]', '1h');
  51 | 
  52 |     // 点击执行按钮（应该显示错误，因为日期未选择）
> 53 |     await page.click('[data-testid="run-backtest-btn"]');
     |                ^ TimeoutError: page.click: Timeout 10000ms exceeded.
  54 | 
  55 |     // 验证错误提示
  56 |     await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
  57 |   });
  58 | });
  59 | 
```