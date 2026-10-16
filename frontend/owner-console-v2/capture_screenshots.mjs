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
  await page.goto('http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  // 1. Controls 默认完整页面
  console.log('Capturing screenshot 1: default page...');
  await page.screenshot({ path: path.join(outDir, 'screenshot_1_controls_default.png'), fullPage: false });

  // 2. Dynamic Selection 操作及诊断抽屉
  console.log('Capturing screenshot 2: selection drawer...');
  const drawerBtn = page.getByText('底层工程诊断 (Drawer)');
  await drawerBtn.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(outDir, 'screenshot_2_selection_drawer.png'), fullPage: false });

  // Close drawer
  const closeDrawerBtn = page.getByText('关闭诊断抽屉');
  await closeDrawerBtn.click();
  await page.waitForTimeout(400);

  // 3. 受控平仓确认弹窗
  console.log('Capturing screenshot 3: flatten modal...');
  const flattenBtn = page.getByRole('button', { name: /受控平仓全部仓位 \(3\)/ });
  await flattenBtn.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(outDir, 'screenshot_3_flatten_modal.png'), fullPage: false });

  await browser.close();
  console.log('All screenshots captured successfully!');
}

capture().catch((err) => {
  console.error(err);
  process.exit(1);
});
