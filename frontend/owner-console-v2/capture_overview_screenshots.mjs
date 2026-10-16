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
    deviceScaleFactor: 2, // crisp retina
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

  await page.goto('http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // ==========================================
  // 1. Dark Theme - Overview Page Default
  // ==========================================
  console.log('Capturing 1: Dark Overview Default...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_dark_default.png'), fullPage: false });

  // ==========================================
  // 2. Light Theme - Overview Page Default
  // ==========================================
  console.log('Capturing 2: Light Overview Default...');
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_light_default.png'), fullPage: false });

  // ==========================================
  // 3. Dark Theme - 8-Stage Causality Drawer
  // ==========================================
  console.log('Capturing 3: Dark Causality Drawer...');
  await setDarkMode();
  const causalityBtn = page.getByRole('button', { name: '查看交易因果' }).first();
  await causalityBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_causality_drawer_dark.png'), fullPage: false });

  // ==========================================
  // 4. Light Theme - 8-Stage Causality Drawer
  // ==========================================
  console.log('Capturing 4: Light Causality Drawer...');
  await setLightMode();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_causality_drawer_light.png'), fullPage: false });

  // Close Drawer
  const closeBtn = page.getByRole('button', { name: '关闭', exact: true });
  await closeBtn.click();
  await page.waitForTimeout(400);

  // ==========================================
  // 5. Dark Theme - Switch Tab to Controls
  // ==========================================
  console.log('Capturing 5: Switch Tab to Controls (Dark)...');
  await setDarkMode();
  const controlsTab = page.getByRole('button', { name: /主控中心/ }).first();
  await controlsTab.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'screenshot_controls_nav_switch_dark.png'), fullPage: false });

  await browser.close();
  console.log('All 5 high-res screenshots captured successfully in screenshots/');
}

capture().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
