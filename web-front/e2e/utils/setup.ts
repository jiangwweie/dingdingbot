/**
 * E2E 测试全局设置
 *
 * 用途:
 * - 配置 Jest 全局超时
 * - 设置 Puppeteer 浏览器实例
 * - 提供全局辅助函数
 */

import puppeteer, { Browser, Page } from 'puppeteer';
import path from 'path';
import { fileURLToPath } from 'url';

// ES Module __dirname 替代方案
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 全局类型声明
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace NodeJS {
    interface Global {
      browser: Browser;
      page: Page;
      baseURL: string;
    }
  }
}

// 配置常量
const CONFIG = {
  // 默认超时时间
  DEFAULT_TIMEOUT: 30000,

  // 页面加载超时
  PAGE_LOAD_TIMEOUT: 15000,

  // 元素等待超时
  ELEMENT_WAIT_TIMEOUT: 5000,

  // 基础 URL
  BASE_URL: process.env.TEST_BASE_URL || 'http://localhost:3000',

  // 截图目录
  SCREENSHOT_DIR: path.join(__dirname, '../screenshots'),

  // 视频目录
  VIDEO_DIR: path.join(__dirname, '../videos')
};

// 确保输出目录存在
import fs from 'fs';

function ensureDir(dir: string): void {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

/**
 * 启动浏览器
 */
export async function launchBrowser(): Promise<Browser> {
  const isCI = process.env.CI === 'true';

  return await puppeteer.launch({
    // 本地调试使用有头模式，便于观察
    headless: isCI ? true : false,

    // 慢动作模式（本地调试）
    slowMo: isCI ? 0 : 100,

    // Chromium 参数
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--no-first-run',
      '--no-zygote',
      '--disable-gpu',
      '--disable-web-security',
      '--disable-features=VizDisplayCompositor',
      // 确保 JavaScript 启用
      '--js-flags=--max-old-space-size=4096'
    ],

    // 超时设置
    timeout: CONFIG.DEFAULT_TIMEOUT,

    // 默认视口
    defaultViewport: {
      width: 1920,
      height: 1080,
      deviceScaleFactor: 1
    }
  });
}

/**
 * 创建新页面
 */
export async function createPage(browser: Browser): Promise<Page> {
  const page = await browser.newPage();

  // 设置视口
  await page.setViewport({
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1
  });

  // 设置默认超时
  page.setDefaultTimeout(CONFIG.DEFAULT_TIMEOUT);
  page.setDefaultNavigationTimeout(CONFIG.PAGE_LOAD_TIMEOUT);

  // 启用请求拦截（可选，用于 mock）
  await page.setRequestInterception(false);

  return page;
}

/**
 * 关闭浏览器
 */
export async function closeBrowser(browser?: Browser): Promise<void> {
  if (browser) {
    await browser.close();
  }
}

/**
 * 截图辅助函数
 */
export async function takeScreenshot(
  page: Page,
  name: string,
  suffix = ''
): Promise<string> {
  ensureDir(CONFIG.SCREENSHOT_DIR);

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${name}${suffix ? `-${suffix}` : ''}-${timestamp}.png`;
  const filepath = path.join(CONFIG.SCREENSHOT_DIR, filename);

  await page.screenshot({
    path: filepath,
    fullPage: false
  });

  return filepath;
}

/**
 * 等待页面加载完成
 */
export async function waitForPageLoad(
  page: Page,
  options?: { waitUntil?: 'load' | 'domcontentloaded' | 'networkidle0' | 'networkidle2' }
): Promise<void> {
  await page.waitForLoadState(options?.waitUntil ?? 'networkidle0', {
    timeout: CONFIG.PAGE_LOAD_TIMEOUT
  });
}

/**
 * 等待网络空闲
 */
export async function waitForNetworkIdle(page: Page, timeout = 10000): Promise<void> {
  try {
    await page.waitForNetworkIdle({
      idleTime: 500,
      timeout
    });
  } catch (error) {
    // 超时也继续执行
    console.log('等待网络空闲超时，继续执行');
  }
}

/**
 * 清理测试数据
 */
export async function cleanupTestData(page: Page): Promise<void> {
  // 清除 localStorage（忽略 data: URL 等不支持的场景）
  try {
    await page.evaluate(() => {
      try {
        localStorage.clear();
        sessionStorage.clear();
      } catch (e) {
        // 忽略 storage 不支持的错误
      }
    });
  } catch (e) {
    // 忽略 storage 不支持的错误
  }

  // 清除 Cookies
  try {
    await page.deleteCookie(...(await page.cookies()));
  } catch (e) {
    // 忽略 cookie 操作错误
  }
}

/**
 * 模拟登录（用于测试）
 *
 * 注意：这是测试专用的 mock 登录，不经过真实认证流程
 */
export async function mockLogin(
  page: Page,
  options?: {
    email?: string;
    token?: string;
  }
): Promise<void> {
  const email = options?.email || 'test@example.com';
  const token = options?.token || 'mock-jwt-token-for-testing';

  // 通过注入 token 模拟登录状态
  await page.evaluate((userData) => {
    localStorage.setItem('user', JSON.stringify({
      email: userData.email,
      name: 'Test User'
    }));
    localStorage.setItem('token', userData.token);
  }, { email, token });

  // 刷新页面使登录生效
  await page.reload({ waitUntil: 'networkidle0' });
}

/**
 * 模拟登出
 */
export async function mockLogout(page: Page): Promise<void> {
  await cleanupTestData(page);
  await page.reload({ waitUntil: 'networkidle0' });
}

// Jest 全局钩子
beforeAll(async () => {
  // 确保输出目录存在
  ensureDir(CONFIG.SCREENSHOT_DIR);
  ensureDir(CONFIG.VIDEO_DIR);

  // 启动浏览器并挂载到 global
  global.browser = await launchBrowser();
  global.page = await createPage(global.browser);
  global.baseURL = CONFIG.BASE_URL;
}, CONFIG.DEFAULT_TIMEOUT);

afterAll(async () => {
  // 关闭浏览器
  if (global.browser) {
    await closeBrowser(global.browser);
  }
}, CONFIG.DEFAULT_TIMEOUT);

// 每个测试前重置状态
beforeEach(async () => {
  // 清理测试数据
  if (global.page) {
    await cleanupTestData(global.page);

    // 返回首页
    await global.page.goto(global.baseURL, {
      waitUntil: 'networkidle0',
      timeout: CONFIG.PAGE_LOAD_TIMEOUT
    });
  }
});

// 每个测试后清理
afterEach(async () => {
  // 测试失败时截图
  if (global.page && expect.getState().currentTestName) {
    const testResult = expect.getState();
    if (testResult.currentTestResult === 'fail') {
      await takeScreenshot(
        global.page,
        'failure',
        testResult.currentTestName?.replace(/\s+/g, '-') || 'unknown'
      );
    }
  }
});

// 导出配置常量
export { CONFIG };
