import { spawn } from 'child_process';
import https from 'https';
import path from 'path';
import fs from 'fs';

const VITE_PORT = 5199;
const CDP_PORT = 9233;
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SCRIPT_DIR = path.dirname(new URL(import.meta.url).pathname);
const OUT_DIR = path.join(SCRIPT_DIR, 'screenshots');
const VITE_BIN = path.join(SCRIPT_DIR, 'node_modules/.bin/vite');
const USER_DATA_DIR = `/tmp/chrome-cdp-profile-${Date.now()}`;

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

function waitUrlReady(url, maxRetries = 50, interval = 200) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const check = () => {
      const req = https.get(url, { rejectUnauthorized: false }, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });
      req.on('error', retry);
    };

    const retry = () => {
      retries++;
      if (retries > maxRetries) {
        reject(new Error(`Server at ${url} failed to respond within timeout`));
      } else {
        setTimeout(check, interval);
      }
    };

    check();
  });
}

async function run() {
  console.log(`Starting isolated Vite server on port ${VITE_PORT}...`);
  const viteProcess = spawn(
    VITE_BIN,
    ['--port', String(VITE_PORT), '--strictPort'],
    {
      cwd: SCRIPT_DIR,
      stdio: 'pipe',
      detached: false,
    }
  );

  let chromeProcess = null;
  let ws = null;

  try {
    const baseUrl = `https://127.0.0.1:${VITE_PORT}/trading/overview_preview.html`;
    await waitUrlReady(baseUrl);
    console.log(`Vite server ready at ${baseUrl}`);

    console.log(`Launching Chrome with CDP on port ${CDP_PORT}...`);
    chromeProcess = spawn(CHROME_PATH, [
      '--headless=new',
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${USER_DATA_DIR}`,
      '--hide-scrollbars',
      '--ignore-certificate-errors',
    ], { stdio: 'pipe' });

    // Wait for CDP to be ready
    let targetPage = null;
    for (let i = 0; i < 40; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new`, { method: 'PUT' });
        targetPage = await res.json();
        break;
      } catch {
        await new Promise((r) => setTimeout(r, 250));
      }
    }

    if (!targetPage?.webSocketDebuggerUrl) {
      throw new Error('Failed to connect to Chrome DevTools Protocol (CDP)');
    }

    ws = new WebSocket(targetPage.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });
    console.log('Connected to Chrome CDP WebSocket.');

    let msgId = 1;
    function sendCdp(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = msgId++;
        const handler = (event) => {
          const data = JSON.parse(event.data);
          if (data.id === id) {
            ws.removeEventListener('message', handler);
            if (data.error) {
              reject(new Error(`CDP Error [${method}]: ${JSON.stringify(data.error)}`));
            } else {
              resolve(data.result);
            }
          }
        };
        ws.addEventListener('message', handler);
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    const captures = [
      {
        name: 'screenshot_phase1_overview_normal_dark.png',
        url: `${baseUrl}?scenario=normal&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_phase1_overview_normal_light.png',
        url: `${baseUrl}?scenario=normal&theme=light&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_phase1_overview_manual_dark.png',
        url: `${baseUrl}?scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_phase1_overview_manual_light.png',
        url: `${baseUrl}?scenario=manual&theme=light&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_phase1_overview_empty_dark.png',
        url: `${baseUrl}?scenario=empty&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_phase1_overview_narrow_dark.png',
        url: `${baseUrl}?scenario=normal&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
      },
      {
        name: 'screenshot_phase1_overview_narrow_manual.png',
        url: `${baseUrl}?scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
      },
      {
        name: 'screenshot_trades_desktop_dark.png',
        url: `${baseUrl}?tab=trades&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        requireActiveManualCard: true,
      },
      {
        name: 'screenshot_trades_desktop_expanded.png',
        url: `${baseUrl}?tab=trades&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        requireActiveManualCard: true,
        expandTradesAndOpenMissingDrawer: true,
      },
      {
        name: 'screenshot_trades_narrow_dark.png',
        url: `${baseUrl}?tab=trades&scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
        requireActiveManualCard: true,
      },
      {
        name: 'screenshot_strategies_desktop_dark.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_strategies_drawer_dark.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        openStrategyDrawer: true,
      },
      {
        name: 'screenshot_strategies_narrow_dark.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
      },
      {
        name: 'screenshot_strategies_exit_config_desktop.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        expandExitConfig: true,
      },
      {
        name: 'screenshot_strategies_exit_config_preview.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        expandExitConfig: true,
        triggerExitConfigPreview: true,
      },
      {
        name: 'screenshot_strategies_exit_config_narrow.png',
        url: `${baseUrl}?tab=strategies&scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
        expandExitConfig: true,
      },
      {
        name: 'screenshot_review_desktop_dark.png',
        url: `${baseUrl}?tab=review&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_review_desktop_expanded.png',
        url: `${baseUrl}?tab=review&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        expandReviewRow: true,
      },
      {
        name: 'screenshot_review_narrow_dark.png',
        url: `${baseUrl}?tab=review&scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
      },
      {
        name: 'screenshot_controls_desktop_dark.png',
        url: `${baseUrl}?tab=controls&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
      },
      {
        name: 'screenshot_controls_flatten_blocked.png',
        url: `${baseUrl}?tab=controls&scenario=manual&theme=dark&hide_controls=true`,
        width: 1440,
        height: 900,
        isMobile: false,
        openBlockedFlattenModal: true,
      },
      {
        name: 'screenshot_controls_narrow_dark.png',
        url: `${baseUrl}?tab=controls&scenario=manual&theme=dark&hide_controls=true`,
        width: 390,
        height: 844,
        isMobile: true,
      },
    ];

    for (const c of captures) {
      console.log(`\n============================================================`);
      console.log(`Capturing ${c.name} (target: ${c.width}x${c.height}, mobile: ${c.isMobile})...`);

      // 1. Set authentic viewport emulation via CDP
      await sendCdp('Emulation.setDeviceMetricsOverride', {
        width: c.width,
        height: c.height,
        deviceScaleFactor: 1,
        mobile: c.isMobile,
      });

      // 2. Navigate to target URL
      await sendCdp('Page.navigate', { url: c.url });

      // 3. Poll for verification facts to be available and complete
      let verification = null;
      const startMs = Date.now();
      while (Date.now() - startMs < 15000) {
        const evalRes = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });

        if (evalRes?.result?.value?.isLoaded) {
          const actualUrl = new URL(evalRes.result.value.href);
          const expectedUrl = new URL(c.url);
          if (actualUrl.origin === expectedUrl.origin && actualUrl.pathname === expectedUrl.pathname &&
              [...expectedUrl.searchParams].every(([key, value]) => actualUrl.searchParams.get(key) === value)) {
            verification = evalRes.result.value;
            break;
          }
        }
        await new Promise((r) => setTimeout(r, 200));
      }

      // 4. HARD ASSERTION: Verification data must exist and be valid
      if (!verification) {
        const diagnostics = await sendCdp('Runtime.evaluate', {
          expression: 'JSON.stringify({url:location.href,ready:document.readyState,facts:window.__getOverviewVerification?.(),text:document.body.innerText.slice(0,300)})',
          returnByValue: true,
        });
        console.error(diagnostics.result?.value);
        throw new Error(`CRITICAL: Page verification data missing or timed out for ${c.name}`);
      }

      if (c.requireActiveManualCard) {
        let activeCardReady = false;
        const aStart = Date.now();
        while (Date.now() - aStart < 5000) {
          const aRes = await sendCdp('Runtime.evaluate', {
            expression: `(() => {
              const cards = document.querySelectorAll('[data-testid="active-trade-card"]');
              if (cards.length < 1) return false;
              const txt = cards[0].textContent || '';
              return txt.includes('人工管理 · 不再自动处置') && txt.includes('同币种 (BTCUSDT) 新增开仓已锁定');
            })()`,
            returnByValue: true,
          });
          if (aRes?.result?.value) {
            activeCardReady = true;
            break;
          }
          await new Promise((r) => setTimeout(r, 150));
        }
        if (!activeCardReady) {
          throw new Error(`CRITICAL: Active manual trade card with authority & restriction tags did not render in ${c.name}`);
        }
        const reEvalActive = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEvalActive?.result?.value) verification = reEvalActive.result.value;
      }

      if (c.openStrategyDrawer) {
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            const row = document.querySelector('[data-strategy-version-id="sgv:CPM-RO-001:v1"]');
            if (row) row.click();
          })()`,
        });
        let stratDrawerReady = false;
        const sStart = Date.now();
        while (Date.now() - sStart < 5000) {
          const sRes = await sendCdp('Runtime.evaluate', {
            expression: 'Boolean(document.querySelector("[data-testid=\\"strategy-detail-drawer\\"]"))',
            returnByValue: true,
          });
          if (sRes?.result?.value) {
            stratDrawerReady = true;
            break;
          }
          await new Promise((r) => setTimeout(r, 150));
        }
        if (!stratDrawerReady) {
          throw new Error(`CRITICAL: StrategyDetailDrawer failed to open in ${c.name}`);
        }
        const reEvalStrat = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEvalStrat?.result?.value) verification = reEvalStrat.result.value;
      }

      if (c.expandExitConfig) {
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            const sum = Array.from(document.querySelectorAll('summary')).find(s => s.textContent && s.textContent.includes('TP1 与 MA50 参数'));
            if (sum && sum.parentElement && !sum.parentElement.open) sum.parentElement.open = true;
          })()`,
        });
        let panelReady = false;
        const pStart = Date.now();
        while (Date.now() - pStart < 5000) {
          const pRes = await sendCdp('Runtime.evaluate', {
            expression: 'Boolean(document.querySelector("[data-testid=\\"exit-configuration-panel\\"]") && (document.querySelector("[data-testid=\\"exit-configuration-panel\\"] tbody tr") || document.querySelector("[data-testid=\\"exit-config-mobile-list\\"]")))',
            returnByValue: true,
          });
          if (pRes?.result?.value) {
            panelReady = true;
            break;
          }
          await new Promise((r) => setTimeout(r, 150));
        }
        if (!panelReady) {
          throw new Error(`CRITICAL: ExitConfigurationPanel failed to load in ${c.name}`);
        }
        if (c.triggerExitConfigPreview) {
          await sendCdp('Runtime.evaluate', {
            expression: `(() => {
              const btn = Array.from(document.querySelectorAll('[data-testid="exit-configuration-panel"] button')).find(b => b.textContent && b.textContent.includes('生成服务端预览'));
              if (btn) btn.click();
            })()`,
          });
          let previewReady = false;
          const pvStart = Date.now();
          while (Date.now() - pvStart < 5000) {
            const pvRes = await sendCdp('Runtime.evaluate', {
              expression: 'Boolean(document.querySelector("[data-testid=\\"exit-config-preview\\"]"))',
              returnByValue: true,
            });
            if (pvRes?.result?.value) {
              previewReady = true;
              break;
            }
            await new Promise((r) => setTimeout(r, 150));
          }
          if (!previewReady) {
            throw new Error(`CRITICAL: ExitConfigurationPanel preview failed to render in ${c.name}`);
          }
        }
        const reEvalExit = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEvalExit?.result?.value) verification = reEvalExit.result.value;
      }

      if (c.expandTradesAndOpenMissingDrawer) {
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            document.querySelectorAll('details').forEach(d => { d.open = true; });
            const missingBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('ticket:unloaded-missing-999'));
            if (missingBtn) missingBtn.click();
          })()`,
        });
        let drawerLoaded = false;
        const dStart = Date.now();
        while (Date.now() - dStart < 5000) {
          const dRes = await sendCdp('Runtime.evaluate', {
            expression: 'Boolean(document.querySelector("[data-testid=\\"causality-drawer\\"]") && document.querySelector("[data-testid=\\"causality-entry-price\\"]"))',
            returnByValue: true,
          });
          if (dRes?.result?.value) {
            drawerLoaded = true;
            break;
          }
          await new Promise((r) => setTimeout(r, 150));
        }
        if (!drawerLoaded) {
          throw new Error(`CRITICAL: Missing-ticket CausalityDrawer failed to open or load in ${c.name}`);
        }
        // Re-evaluate verification facts after expanding details
        const reEval = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEval?.result?.value) verification = reEval.result.value;
      }

      if (c.expandReviewRow) {
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            const btn = document.querySelector('[data-testid="review-table"] button[aria-expanded]');
            if (btn) btn.click();
          })()`,
        });
        await new Promise((r) => setTimeout(r, 200));
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            document.querySelectorAll('details').forEach(d => { d.open = true; });
          })()`,
        });
        const reEvalRev = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEvalRev?.result?.value) verification = reEvalRev.result.value;
      }

      if (c.openBlockedFlattenModal) {
        await sendCdp('Runtime.evaluate', {
          expression: `(() => {
            const btn = document.querySelector('[data-testid="danger-zone-flatten-btn"]');
            if (btn) btn.click();
          })()`,
        });
        let modalReady = false;
        const mStart = Date.now();
        while (Date.now() - mStart < 5000) {
          const mRes = await sendCdp('Runtime.evaluate', {
            expression: 'Boolean(document.querySelector("[data-testid=\\"controlled-flatten-modal\\"]"))',
            returnByValue: true,
          });
          if (mRes?.result?.value) {
            modalReady = true;
            break;
          }
          await new Promise((r) => setTimeout(r, 150));
        }
        if (!modalReady) {
          throw new Error(`CRITICAL: ControlledFlattenModal failed to open in ${c.name}`);
        }
        const reEvalCtrl = await sendCdp('Runtime.evaluate', {
          expression: 'window.__getOverviewVerification ? window.__getOverviewVerification() : null',
          returnByValue: true,
        });
        if (reEvalCtrl?.result?.value) verification = reEvalCtrl.result.value;
      }

      console.log(`  Facts loaded: scenario=${verification.scenario}, innerWidth=${verification.innerWidth}px, scrollWidth=${verification.scrollWidth}px, scrollHeight=${verification.scrollHeight}px`);

      // 5. HARD ASSERTION: Viewport width must exactly match expected
      if (verification.innerWidth !== c.width) {
        throw new Error(`CRITICAL: Browser viewport mismatch! Expected ${c.width}px, got ${verification.innerWidth}px`);
      }

      // 6. HARD ASSERTION: Critical overview elements must be present
      if (!verification.hasCriticalElements) {
        throw new Error(`CRITICAL: Essential overview components missing from DOM for ${c.name}`);
      }

      // 7. HARD ASSERTION: No horizontal document overflow allowed
      if (verification.scrollWidth > verification.innerWidth) {
        throw new Error(
          `CRITICAL: Document horizontal overflow detected! scrollWidth (${verification.scrollWidth}px) > innerWidth (${verification.innerWidth}px)`
        );
      }

      // 8. HARD ASSERTION: No DOM elements bleeding out of viewport boundaries
      if (verification.overflowElements && verification.overflowElements.length > 0) {
        throw new Error(
          `CRITICAL: Elements bleeding past right viewport edge: ${JSON.stringify(verification.overflowElements)}`
        );
      }

      // 9. HARD ASSERTION: No unexpected or unauthorized network requests
      if (verification.unexpectedRequests && verification.unexpectedRequests.length > 0) {
        throw new Error(
          `CRITICAL: Unauthorized network requests detected in isolated sandbox: ${JSON.stringify(verification.unexpectedRequests)}`
        );
      }

      // 10. Measure full document layout height via CDP
      const layoutMetrics = await sendCdp('Page.getLayoutMetrics');
      const contentHeight = Math.ceil(layoutMetrics.contentSize.height);
      const fullHeight = Math.max(contentHeight, verification.scrollHeight);

      console.log(`  Full page height resolved: ${fullHeight}px (contentSize: ${contentHeight}px)`);

      // 11. Override device metrics to full content height for complete top-to-bottom screenshot
      await sendCdp('Emulation.setDeviceMetricsOverride', {
        width: c.width,
        height: fullHeight,
        deviceScaleFactor: 1,
        mobile: c.isMobile,
      });

      // Allow 200ms for layout to settle after height adjustment
      await new Promise((r) => setTimeout(r, 200));

      // 12. Capture full-height PNG screenshot
      const shotRes = await sendCdp('Page.captureScreenshot', {
        format: 'png',
        fromSurface: true,
      });

      const outPath = path.join(OUT_DIR, c.name);
      fs.writeFileSync(outPath, Buffer.from(shotRes.data, 'base64'));
      const stats = fs.statSync(outPath);

      if (stats.size < 25000) {
        throw new Error(`CRITICAL: Screenshot size abnormally small (${stats.size} bytes), image may be blank`);
      }

      console.log(`  ✓ PASS: Saved ${c.name} (${stats.size} bytes, dimensions: ${c.width}x${fullHeight})`);
      console.log(`  ✓ Verified: 0 horizontal overflow | 0 element bleed | 0 unauthorized API requests`);
    }

    console.log('\n============================================================');
    console.log('All Phase 1 screenshots captured and strict CDP assertions passed.');
    console.log('============================================================');
  } finally {
    if (ws) {
      try { ws.close(); } catch {}
    }
    if (chromeProcess) {
      chromeProcess.kill('SIGTERM');
    }
    if (viteProcess) {
      viteProcess.kill('SIGTERM');
    }
    // Clean up temporary user data directory
    try {
      fs.rmSync(USER_DATA_DIR, { recursive: true, force: true });
    } catch {}
  }
}

run().catch((err) => {
  console.error('\nCapture and Verification Failed:', err);
  process.exit(1);
});
