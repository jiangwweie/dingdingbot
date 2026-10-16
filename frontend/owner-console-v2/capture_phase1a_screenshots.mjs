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

  // Switch to Controls tab
  const controlsTab = page.getByRole('button', { name: /主控中心/ }).first();
  await controlsTab.click();
  await page.waitForTimeout(500);

  // 1. Dark Controls Phase 1A
  console.log('Capturing Phase 1A Controls Dark...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_phase1a_controls_dark.png'), fullPage: false });

  // 2. Light Controls Phase 1A
  console.log('Capturing Phase 1A Controls Light...');
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_phase1a_controls_light.png'), fullPage: false });

  await browser.close();
  console.log('Phase 1A screenshots captured successfully!');
}

capture().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
