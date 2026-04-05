/**
 * E2E 测试辅助函数
 *
 * 提供常用测试操作的工具函数
 */

import { Page, ElementHandle } from 'puppeteer';

/**
 * 等待元素出现
 */
export async function waitForElement(
  page: Page,
  selector: string,
  options?: {
    visible?: boolean;
    timeout?: number;
  }
): Promise<ElementHandle | null> {
  const { visible = false, timeout = 5000 } = options || {};

  try {
    await page.waitForSelector(selector, {
      visible,
      timeout
    });
    return await page.$(selector);
  } catch (error) {
    return null;
  }
}

/**
 * 等待元素消失
 */
export async function waitForElementToDisappear(
  page: Page,
  selector: string,
  timeout = 5000
): Promise<void> {
  await page.waitForSelector(selector, {
    hidden: true,
    timeout
  });
}

/**
 * 点击元素
 */
export async function clickElement(
  page: Page,
  selector: string,
  options?: {
    delay?: number;
    clickCount?: number;
  }
): Promise<boolean> {
  try {
    const element = await page.$(selector);
    if (!element) return false;

    await element.click({
      delay: options?.delay || 0,
      clickCount: options?.clickCount || 1
    });
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * 输入文本
 */
export async function typeText(
  page: Page,
  selector: string,
  text: string,
  options?: {
    delay?: number;
    clear?: boolean;
  }
): Promise<boolean> {
  try {
    const element = await page.$(selector);
    if (!element) return false;

    // 清空输入框
    if (options?.clear) {
      await page.evaluate((sel) => {
        const el = document.querySelector(sel) as HTMLInputElement;
        if (el) el.value = '';
      }, selector);
    }

    await element.type(text, {
      delay: options?.delay || 50
    });
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * 获取元素文本内容
 */
export async function getElementText(
  page: Page,
  selector: string
): Promise<string | null> {
  try {
    const element = await page.$(selector);
    if (!element) return null;

    return await page.evaluate((el) => el.textContent || '', element);
  } catch (error) {
    return null;
  }
}

/**
 * 获取元素属性
 */
export async function getElementAttribute(
  page: Page,
  selector: string,
  attribute: string
): Promise<string | null> {
  try {
    const element = await page.$(selector);
    if (!element) return null;

    return await page.evaluate((el, attr) => el.getAttribute(attr), element, attribute);
  } catch (error) {
    return null;
  }
}

/**
 * 检查元素是否存在
 */
export async function elementExists(
  page: Page,
  selector: string
): Promise<boolean> {
  const element = await page.$(selector);
  return element !== null;
}

/**
 * 检查元素是否可见
 */
export async function elementIsVisible(
  page: Page,
  selector: string
): Promise<boolean> {
  try {
    const element = await page.$(selector);
    if (!element) return false;

    return await page.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }, element);
  } catch (error) {
    return false;
  }
}

/**
 * 等待页面导航完成
 */
export async function waitForNavigation(
  page: Page,
  options?: {
    waitUntil?: 'load' | 'domcontentloaded' | 'networkidle0' | 'networkidle2';
    timeout?: number;
  }
): Promise<void> {
  await page.waitForNavigation({
    waitUntil: options?.waitUntil || 'networkidle0',
    timeout: options?.timeout || 30000
  });
}

/**
 * 等待 API 请求完成
 */
export async function waitForRequest(
  page: Page,
  urlPattern: string | RegExp,
  timeout = 30000
): Promise<string> {
  const response = await page.waitForResponse(
    (res) => {
      if (typeof urlPattern === 'string') {
        return res.url().includes(urlPattern);
      }
      return urlPattern.test(res.url());
    },
    { timeout }
  );
  return response.url();
}

/**
 * 等待特定时间
 */
export async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 滚动到页面底部
 */
export async function scrollToBottom(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.scrollTo(0, document.body.scrollHeight);
  });
}

/**
 * 滚动到元素位置
 */
export async function scrollToElement(
  page: Page,
  selector: string
): Promise<boolean> {
  try {
    await page.evaluate((sel) => {
      const element = document.querySelector(sel);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, selector);
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * 获取页面所有 Cookie
 */
export async function getCookies(page: Page): Promise<Array<{ name: string; value: string }>> {
  return await page.cookies();
}

/**
 * 设置 Cookie
 */
export async function setCookie(
  page: Page,
  name: string,
  value: string,
  options?: {
    domain?: string;
    path?: string;
    secure?: boolean;
  }
): Promise<void> {
  await page.setCookie({
    name,
    value,
    domain: options?.domain || new URL(await page.url()).hostname,
    path: options?.path || '/',
    secure: options?.secure || false
  });
}

/**
 * 删除 Cookie
 */
export async function deleteCookie(page: Page, name: string): Promise<void> {
  const url = await page.url();
  const client = await page.createCDPSession();
  await client.send('Network.clearBrowserCookies', { name });
}

/**
 * 模拟键盘操作
 */
export async function pressKey(
  page: Page,
  key: string,
  options?: {
    count?: number;
    delay?: number;
  }
): Promise<void> {
  const count = options?.count || 1;
  const delay = options?.delay || 10;

  for (let i = 0; i < count; i++) {
    await page.keyboard.press(key, { delay });
  }
}

/**
 * 模拟选择下拉选项
 */
export async function selectOption(
  page: Page,
  selector: string,
  value: string
): Promise<boolean> {
  try {
    await page.select(selector, value);
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * 检查复选框状态
 */
export async function isCheckboxChecked(
  page: Page,
  selector: string
): Promise<boolean> {
  try {
    return await page.evaluate((sel) => {
      const el = document.querySelector(sel) as HTMLInputElement;
      return el ? el.checked : false;
    }, selector);
  } catch (error) {
    return false;
  }
}

/**
 * 切换复选框状态
 */
export async function toggleCheckbox(
  page: Page,
  selector: string
): Promise<boolean> {
  return await clickElement(page, selector);
}

/**
 * 获取 localStorage 值
 */
export async function getLocalStorageValue(
  page: Page,
  key: string
): Promise<string | null> {
  return await page.evaluate((k) => localStorage.getItem(k), key);
}

/**
 * 设置 localStorage 值
 */
export async function setLocalStorageValue(
  page: Page,
  key: string,
  value: string
): Promise<void> {
  await page.evaluate((k, v) => localStorage.setItem(k, v), key, value);
}

/**
 * 清除 localStorage
 */
export async function clearLocalStorage(page: Page): Promise<void> {
  await page.evaluate(() => localStorage.clear());
}

/**
 * 等待网络空闲
 */
export async function waitForNetworkIdle(
  page: Page,
  options?: {
    idleTime?: number;
    concurrency?: number;
    timeout?: number;
  }
): Promise<void> {
  await page.waitForNetworkIdle({
    idleTime: options?.idleTime || 500,
    concurrency: options?.concurrency || 0,
    timeout: options?.timeout || 30000
  });
}

/**
 * 测试报告助手 - 记录测试结果
 */
export interface TestReport {
  testName: string;
  status: 'pass' | 'fail' | 'skip';
  duration: number;
  screenshot?: string;
  error?: string;
}

export async function recordTestResult(
  result: TestReport
): Promise<void> {
  const reportPath = './reports/test-results.json';
  const fs = await import('fs');
  const path = await import('path');

  // 确保目录存在
  const dir = path.dirname(reportPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  // 读取现有报告
  let results: TestReport[] = [];
  if (fs.existsSync(reportPath)) {
    const content = fs.readFileSync(reportPath, 'utf-8');
    results = JSON.parse(content);
  }

  // 添加新结果
  results.push(result);

  // 保存报告
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));
}

/**
 * 截图辅助函数
 */
export async function takeScreenshot(
  page: Page,
  name: string,
  suffix = ''
): Promise<string> {
  const fs = await import('fs');
  const path = await import('path');

  const screenshotDir = path.join(process.cwd(), 'e2e', 'screenshots');

  // 确保目录存在
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${name}${suffix ? `-${suffix}` : ''}-${timestamp}.png`;
  const filepath = path.join(screenshotDir, filename);

  await page.screenshot({
    path: filepath,
    fullPage: false
  });

  return filepath;
}
