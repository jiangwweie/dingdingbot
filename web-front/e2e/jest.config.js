/**
 * Jest E2E 测试配置
 */

export default {
  // 测试文件匹配模式
  testMatch: ['**/e2e/**/*.test.ts'],

  // 模块文件扩展名
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],

  // 转换器配置
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        useESM: true,
        tsconfig: {
          module: 'ESNext',
          moduleResolution: 'node',
          target: 'ES2020',
          esModuleInterop: true,
          strict: true,
          skipLibCheck: true
        }
      }
    ]
  },

  // ESM 支持
  extensionsToTreatAsEsm: ['.ts'],

  // 测试环境
  testEnvironment: 'node',

  // 超时配置
  testTimeout: 30000,

  // 重试配置 (使用 --retryTimes CLI 参数)
  // retryTimes: process.env.CI ? 2 : 0,

  // 日志配置
  verbose: true,

  // 彩色输出
  collectCoverage: false,

  // 测试路径忽略
  testPathIgnorePatterns: ['/node_modules/', '/dist/'],

  // 设置文件
  setupFilesAfterEnv: ['<rootDir>/utils/setup.ts'],

  // 报告配置
  reporters: [
    'default'
    // HTML 报告器暂时禁用，需要先安装依赖
    // [
    //   'jest-html-reporter',
    //   {
    //     pageTitle: 'E2E Test Report',
    //     outputPath: './reports/test-report.html',
    //     includeFailureMsg: true,
    //     includeSuiteFailure: true
    //   }
    // ]
  ]
};
