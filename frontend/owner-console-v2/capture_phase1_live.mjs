import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';

const { chromium } = pkg;

const outDir = path.resolve('screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

async function capture() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 2,
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();

  const setDarkMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      localStorage.setItem('brc_owner_console_theme', 'dark');
    });
    await page.waitForTimeout(300);
  };

  const setLightMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      localStorage.setItem('brc_owner_console_theme', 'light');
    });
    await page.waitForTimeout(300);
  };

  console.log('Navigating to https://localhost:5174 ...');
  await page.goto('https://localhost:5174', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);

  // 1. Unauthenticated Login Screen - Dark Mode
  console.log('Capturing Login Dark...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_login_dark.png'), fullPage: false });

  // 2. Unauthenticated Login Screen - Light Mode
  console.log('Capturing Login Light...');
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_login_light.png'), fullPage: false });

  await browser.close();
  console.log('Live Phase 1 screenshots captured successfully!');
}

capture().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
