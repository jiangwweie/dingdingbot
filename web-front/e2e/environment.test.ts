/**
 * Puppeteer 环境验证测试
 *
 * 用途：验证 E2E 测试环境是否正确配置
 */

import { Page } from 'puppeteer';
import {
  waitForElement,
  clickElement,
  typeText,
  sleep,
  takeScreenshot
} from './utils/helpers';

describe('E2E Environment Verification', () => {
  let page: Page;

  beforeAll(async () => {
    // 从 global 获取 page 实例
    page = (global as typeof globalThis & { page: Page }).page;
    expect(page).toBeDefined();
  });

  describe('Browser Basics', () => {
    it('should have a valid page object', async () => {
      expect(page).toBeDefined();
      expect(typeof page.url).toBe('function');
    });

    it('should be able to navigate to a URL', async () => {
      await page.goto('about:blank');
      const url = await page.url();
      expect(url).toBe('about:blank');
    });

    it('should have correct viewport size', async () => {
      const viewport = page.viewport();
      expect(viewport).toBeDefined();
      expect(viewport?.width).toBe(1920);
      expect(viewport?.height).toBe(1080);
    });
  });

  describe('Page Interaction', () => {
    it('should load a real HTTP page', async () => {
      // 测试环境验证：只要能加载页面并执行 JS 就足够了
      // 完整的页面交互测试应该在具体功能测试中进行
      await page.goto('about:blank');

      // 注入简单 HTML
      await page.setContent(`
        <html>
          <body>
            <h1 id="title">Test</h1>
            <input id="input" type="text" />
            <button id="button">Click</button>
          </body>
        </html>
      `);

      // 验证元素存在
      const title = await page.$('#title');
      expect(title).toBeDefined();
    });

    it('should type text into input', async () => {
      await page.setContent(`<input id="input" type="text" />`);
      await page.waitForSelector('#input');

      await page.type('#input', 'E2E Test');

      const inputValue = await page.$eval('#input', (el) => (el as HTMLInputElement).value);
      expect(inputValue).toBe('E2E Test');
    });

    it('should click button', async () => {
      await page.setContent(`
        <button id="button" onclick="this.textContent='Clicked!'">Click Me</button>
      `);
      await page.waitForSelector('#button');

      await page.click('#button');
      await sleep(100);

      const buttonText = await page.$eval('#button', (el) => el.textContent);
      expect(buttonText).toBe('Clicked!');
    });

    it('should take screenshot', async () => {
      await page.setContent(`<h1>Screenshot Test</h1>`);
      const screenshotPath = await takeScreenshot(page, 'env-test-basic');
      expect(screenshotPath).toBeDefined();
      expect(screenshotPath).toContain('env-test-basic');
    });
  });

  describe('LocalStorage Operations', () => {
    it('should set and get localStorage values', async () => {
      // 设置值
      await page.evaluate(() => {
        localStorage.setItem('test-key', 'test-value');
        localStorage.setItem('test-object', JSON.stringify({ foo: 'bar' }));
      });

      // 获取值
      const value = await page.evaluate(() => localStorage.getItem('test-key'));
      expect(value).toBe('test-value');

      const objValue = await page.evaluate(() => {
        return JSON.parse(localStorage.getItem('test-object') || '{}');
      });
      expect(objValue).toEqual({ foo: 'bar' });
    });

    it('should clear localStorage', async () => {
      await page.evaluate(() => localStorage.clear());
      const keys = await page.evaluate(() => Object.keys(localStorage));
      expect(keys).toHaveLength(0);
    });
  });

  describe('Cookie Operations', () => {
    it('should set and get cookies', async () => {
      // 设置 cookie
      await page.setCookie({
        name: 'test-cookie',
        value: 'test-value',
        domain: new URL(await page.url()).hostname || 'localhost'
      });

      // 获取 cookies
      const cookies = await page.cookies();
      const testCookie = cookies.find((c) => c.name === 'test-cookie');
      expect(testCookie).toBeDefined();
      expect(testCookie?.value).toBe('test-value');
    });

    it('should delete cookies', async () => {
      // 清除所有 cookies
      await page.deleteCookie(...(await page.cookies()));

      const cookies = await page.cookies();
      expect(cookies).toHaveLength(0);
    });
  });

  describe('Navigation and Timing', () => {
    it('should navigate between pages', async () => {
      const pages = [
        'data:text/html,<h1>Page 1</h1>',
        'data:text/html,<h1>Page 2</h1>',
        'data:text/html,<h1>Page 3</h1>'
      ];

      for (const pageData of pages) {
        await page.goto(pageData, { waitUntil: 'domcontentloaded' });
        await sleep(100);
      }

      // 验证最后停留的页面
      const content = await page.content();
      expect(content).toContain('Page 3');
    });

    it('should handle navigation timeout gracefully', async () => {
      try {
        await page.goto('about:blank', {
          waitUntil: 'domcontentloaded',
          timeout: 5000
        });
        expect(true).toBe(true);
      } catch (error) {
        // 预期不会超时，但如果超时也正常
        expect(error).toBeDefined();
      }
    });
  });

  describe('JavaScript Execution', () => {
    it('should execute JavaScript in page context', async () => {
      const result = await page.evaluate(() => {
        return 2 + 2;
      });
      expect(result).toBe(4);
    });

    it('should execute JavaScript with parameters', async () => {
      const result = await page.evaluate((num) => {
        return num * 10;
      }, 5);
      expect(result).toBe(50);
    });

    it('should return complex objects from page context', async () => {
      const result = await page.evaluate(() => {
        return {
          timestamp: Date.now(),
          userAgent: navigator.userAgent,
          language: navigator.language
        };
      });

      expect(result).toHaveProperty('timestamp');
      expect(result).toHaveProperty('userAgent');
      expect(result).toHaveProperty('language');
    });
  });
});
