/**
 * Puppeteer E2E 测试配置
 *
 * 配置说明:
 * - headless: 生产环境使用 true，调试时改为 false
 * - slowMo: 慢动作模式，便于观察测试执行
 * - timeout: 默认超时时间
 */

import { defineConfig } from './jest.config.js';

export default {
  // Puppeteer 浏览器配置
  puppeteer: {
    launch: {
      // 无头模式：CI 环境强制 true，本地调试可设为 false
      headless: process.env.CI ? true : false,

      // 慢动作模式 (ms)，便于调试观察
      slowMo: process.env.CI ? 0 : 50,

      // 浏览器超时时间
      timeout: 30000,

      // Chromium 启动参数
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu'
      ]
    }
  },

  // 测试服务器配置
  server: {
    // 前端开发服务器地址
    baseUrl: process.env.TEST_BASE_URL || 'http://localhost:3000',

    // 服务器启动超时
    launchTimeout: 60000
  },

  // 测试超时配置
  timeout: {
    // 单个测试超时
    test: 30000,

    // 钩子函数超时 (beforeEach/afterEach)
    hook: 10000,

    // 页面加载超时
    pageLoad: 15000
  },

  // 重试配置
  retry: {
    // 失败重试次数
    count: process.env.CI ? 2 : 0,

    // 重试间隔 (ms)
    delay: 1000
  },

  // 截图配置
  screenshot: {
    // 失败时自动截图
    onFail: true,

    // 截图保存目录
    outputDir: './e2e/screenshots'
  },

  // 视频录制配置
  video: {
    // 失败时录制视频
    onFail: true,

    // 视频保存目录
    outputDir: './e2e/videos'
  }
};
