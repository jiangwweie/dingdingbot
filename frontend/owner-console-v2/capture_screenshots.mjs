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

  // Helper to ensure Dark mode
  const setDarkMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      localStorage.setItem('brc_owner_console_theme', 'dark');
    });
    await page.waitForTimeout(300);
  };

  // Helper to ensure Light mode
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
  // 1. Dark Theme - Default Controls Page
  // ==========================================
  console.log('Capturing 1: Dark Controls Default...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_1_controls_dark_default.png'), fullPage: false });

  // ==========================================
  // 2. Light Theme - Default Controls Page
  // ==========================================
  console.log('Capturing 2: Light Controls Default...');
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_2_controls_light_default.png'), fullPage: false });

  // ==========================================
  // 3. Dark Theme - Selection Drawer
  // ==========================================
  console.log('Capturing 3: Dark Selection Drawer...');
  await setDarkMode();
  const drawerLink = page.getByText('标的明细与诊断');
  await drawerLink.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'screenshot_3_selection_drawer_dark.png'), fullPage: false });

  // ==========================================
  // 4. Light Theme - Selection Drawer
  // ==========================================
  console.log('Capturing 4: Light Selection Drawer...');
  await setLightMode();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, 'screenshot_4_selection_drawer_light.png'), fullPage: false });

  // Close Drawer
  const closeDrawerBtn = page.getByText('关闭诊断抽屉');
  await closeDrawerBtn.click();
  await page.waitForTimeout(400);

  // ==========================================
  // 5. Dark Theme - Flatten Modal
  // ==========================================
  console.log('Capturing 5: Dark Flatten Modal...');
  await setDarkMode();
  const flattenBtn = page.getByRole('button', { name: /受控平仓全部仓位 \(3\)/ });
  await flattenBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, 'screenshot_5_flatten_modal_dark.png'), fullPage: false });

  // ==========================================
  // 6. Light Theme - Flatten Modal
  // ==========================================
  console.log('Capturing 6: Light Flatten Modal...');
  await setLightMode();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(outDir, 'screenshot_6_flatten_modal_light.png'), fullPage: false });

  await browser.close();
  console.log('All 6 retina screenshots captured successfully!');
}

capture().catch((err) => {
  console.error(err);
  process.exit(1);
});

