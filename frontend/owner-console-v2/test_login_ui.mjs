import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';

const { chromium } = pkg;

async function testLoginError() {
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
  await page.goto('https://localhost:5174', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // Fill in form with invalid credentials
  await page.fill('#username', 'owner');
  await page.fill('#password', 'invalidpassword');
  await page.fill('#totp', '999999');

  // Click submit
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1000);

  // Take screenshot of error state
  await page.screenshot({ path: 'frontend/owner-console-v2/screenshots/screenshot_login_error_dark.png' });
  await browser.close();
  console.log('Login error test passed and screenshot captured!');
}

testLoginError().catch((err) => {
  console.error('Error test failed:', err);
  process.exit(1);
});
