import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright";

const frontendPort = Number(process.env.PORT ?? "5198");
const apiPort = Number(process.env.OWNER_RUNTIME_API_PORT ?? "8028");
const pythonBin = process.env.PYTHON_BIN ?? "/opt/homebrew/bin/python3";
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const apiUrl = `http://127.0.0.1:${apiPort}`;
const artifactDir = path.resolve("artifacts", "real-backend-smoke");
const backendCwd = path.resolve("..");
const username = "owner";
const password = "pw";
const totpSecret = "JBSWY3DPEHPK3PXP";

const forbidden = [
  "Final" + "Gate",
  "Operation" + " Layer",
  "Required" + "Facts",
  "candi" + "date",
  "author" + "ization",
  "pre" + "flight",
  "pr" + "oof",
  "ref" + "Id",
  "next" + " step",
  "下" + "一步",
  "检查" + "器",
  "系统自动" + "观察中",
  "暂无可用" + "机会",
  "read" + "model",
  "mock",
];

function passwordHash() {
  const result = spawnSync(
    pythonBin,
    [
      "-c",
      "from src.interfaces.operator_auth import create_password_hash; print(create_password_hash('pw'))",
    ],
    {
      cwd: backendCwd,
      encoding: "utf8",
    },
  );
  if (result.status !== 0) {
    throw new Error(`Could not create test password hash: ${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

function base32Decode(value) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const normalized = value.replace(/\s+/g, "").toUpperCase();
  let bits = "";
  for (const char of normalized) {
    const index = alphabet.indexOf(char);
    if (index < 0) throw new Error(`Invalid base32 character: ${char}`);
    bits += index.toString(2).padStart(5, "0");
  }
  const bytes = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(Number.parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}

function totpCode(secret) {
  const counter = Math.floor(Date.now() / 1000 / 30);
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = digest.readUInt32BE(offset) & 0x7fffffff;
  return String(code % 1_000_000).padStart(6, "0");
}

async function writeJson(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

async function createRuntimeFixtures({ deployChannelReady = false } = {}) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "owner-console-mainline-"));
  const reportDir = path.join(dir, "runtime-signal-watcher");
  const liveFactsPath = path.join(dir, "strategy-group-live-facts.json");
  const noWriteSafety = {
    exchange_write_called: false,
    execution_intent_created: false,
    mutates_pg: false,
    order_created: false,
    order_lifecycle_called: false,
    places_order: false,
    runtime_budget_mutated: false,
    withdrawal_or_transfer_created: false,
  };
  const blockers = [
    "strategy-runtime-mainline-smoke:strategy_signal_not_ready_for_shadow_candidate_prepare",
  ];
  const ownerState = {
    status: "waiting_for_market",
    blocker_class: "waiting_for_market",
    blocked_at: "watcher_signal",
    blocked_reason: "no_fresh_strategy_signal",
    next_recover_condition: "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope",
    automatic_recovery_action: "continue_watcher_observation",
    downgrade_mode: "observe_only",
  };
  await writeJson(liveFactsPath, {
    status: "ready",
    account: {
      status: "fresh",
      available_balance_present: true,
      available_balance_positive: true,
      total_wallet_balance_present: true,
      can_trade: true,
    },
    active_position: {
      status: "no_active_position",
      active_count: 0,
      active_symbols: [],
    },
    open_orders: {
      status: "no_open_orders",
      open_order_count: 0,
      open_order_symbols: [],
    },
    protection: {
      status: "ready_for_candidate_specific_plan",
    },
    budget: {
      status: "available_for_candidate_specific_reservation",
      reason: "account_available_balance_covers_strategygroup_tiny_notional",
      max_notional_requirement_usdt: "8",
    },
    next_attempt_gate: {
      status: "ready_for_strategy_signal",
    },
    exchange_rules: {
      symbols: {
        BTCUSDT: { status: "TRADING" },
        ETHUSDT: { status: "TRADING" },
      },
    },
    safety_invariants: {
      signed_get_only: true,
      exchange_write_called: false,
      order_created: false,
      withdrawal_or_transfer_created: false,
    },
  });
  await writeJson(path.join(reportDir, "watcher-tick.json"), {
    status: "watching_no_signal",
    blockers,
    warnings: [],
    notification: {
      required: false,
      configured: true,
      attempted: false,
      sent: false,
      duplicate_suppressed: false,
      skipped_reason: "no_owner_attention_needed",
    },
    safety_invariants: {
      ...noWriteSafety,
      watcher_tick_only: true,
      forbidden_effects: [],
    },
  });
  await writeJson(path.join(reportDir, "notification-state.json"), {});
  await writeJson(path.join(reportDir, "wakeup-packet.json"), {
    status: "operator_packet_needs_review",
    safety_invariants: {
      ...noWriteSafety,
      wakeup_packet_only: true,
    },
  });
  await writeJson(path.join(reportDir, "operator-packet.json"), {
    status: "operator_review",
    safety_invariants: {
      ...noWriteSafety,
      operator_packet_only: true,
    },
  });
  await writeJson(path.join(reportDir, "status-packet.json"), {
    status: "ok",
    blockers,
    warnings: [],
    safety_invariants: {
      ...noWriteSafety,
      read_packets_only: true,
      forbidden_effects: [],
    },
  });
  await writeJson(path.join(reportDir, "latest-summary.json"), {
    status: "waiting_for_signal",
    blockers,
    warnings: [],
  });
  await writeJson(path.join(reportDir, "post-signal-resume-pack.json"), {
    status: "waiting_for_market",
    owner_state: ownerState,
    blockers,
    warnings: [],
    action_time_resume: {
      status: "waiting_for_market",
      next_step: "continue_watcher_observation",
      signal_input_json: null,
      shadow_candidate_id: null,
      prepared_authorization_id: null,
      allowed_auto_actions: ["continue_watcher_observation"],
      requires_action_time_final_gate: true,
      requires_official_operation_layer: true,
      places_order: false,
      calls_order_lifecycle: false,
      exchange_write_called: false,
      withdrawal_or_transfer_requested: false,
    },
    safety_invariants: {
      ...noWriteSafety,
      pack_builder_only: true,
      forbidden_effect_flags: [],
      sends_notification: false,
    },
  });
  await writeJson(path.join(reportDir, "strategygroup-runtime-pilot-status.json"), {
    status: "waiting_for_market",
    owner_state: ownerState,
    control_board: {
      strategy_group_rows: ["MPG", "TEQ", "FBS", "SOR", "PMR"].map((code, index) => ({
        strategy_group_id: `${code}-001`,
        name: code,
        runtime_state: "armed_observation",
        signal_state: "no_signal",
        owner_label: "等待机会",
        blocked_reason: "no_fresh_strategy_signal",
        selected: index === 0,
      })),
    },
    safety_invariants: {
      ...noWriteSafety,
      authorizes_execution: false,
      creates_candidate: false,
      pilot_status_builder_only: true,
      reads_existing_evidence_only: true,
      registers_runtime: false,
    },
  });
  await writeJson(path.join(reportDir, "strategy-group-live-facts-readiness.json"), {
    status: "strategy_group_live_facts_ready_for_armed_observation",
    owner_state: {
      status: "armed_observation_ready",
      blocked_at: "none",
      blocked_reason: "none",
      next_recover_condition: "fresh_strategy_signal_arrives",
      automatic_recovery_action: "continue_watcher_observation",
      downgrade_mode: "none",
    },
    blockers: [],
    safety_invariants: {
      ...noWriteSafety,
      authorizes_execution: false,
      creates_candidate: false,
      reads_live_facts_only: true,
      registers_runtime: false,
    },
  });
  await writeJson(path.join(reportDir, "runtime-dry-run-audit-chain.json"), {
    scope: "runtime_dry_run_audit_chain",
    status: "passed",
    checks: {
      scenario_count: 12,
      required_scenarios_present: true,
      all_scenarios_passed: true,
      dangerous_effects_absent: true,
      disabled_smoke_not_real_execution_proof: true,
      fresh_signal_fast_auto_chain_checked: true,
      legacy_local_registration_probe_tolerance_checked: true,
      mock_operation_layer_closed_loop_checked: true,
      operation_layer_blocker_review_policy_checked: true,
      operation_layer_hard_safety_blocker_matrix_checked: true,
      expanded_watcher_scope_execution_guard_checked: true,
      operation_layer_authorization_chain_guard_checked: true,
      post_submit_closed_loop_evidence_guard_checked: true,
      operation_layer_submit_result_identity_guard_checked: true,
      post_submit_finalize_result_identity_guard_checked: true,
      operation_layer_evidence_relay_checked: true,
      selected_strategygroup_dispatch_guard_checked: true,
      all_selected_strategygroups_reach_finalgate_dispatch_checked: true,
      shared_runtime_pipeline_checked: true,
      common_execution_chain_reuse_checked: true,
      strategygroup_adapter_boundary_checked: true,
    },
    safety_invariants: {
      exchange_write_called: false,
      order_created: false,
      order_lifecycle_called: false,
      withdrawal_or_transfer_created: false,
      disabled_smoke_is_real_execution_proof: false,
      dangerous_effects: [],
    },
  });
  if (deployChannelReady) {
    await writeJson(path.join(reportDir, "tokyo-deploy-channel-status.json"), {
      scope: "tokyo_runtime_governance_deploy_channel_status",
      status: "postdeploy_accepted",
      deployed_head: "owner-console-mainline-smoke",
      release_path: "/home/ubuntu/brc-deploy/releases/owner-console-mainline-smoke",
      checks: {
        blockers: [],
        tokyo_probe_blockers: [],
        tokyo_connectivity_blockers: [],
        tokyo_connectivity_probe_ready: true,
        postdeploy_acceptance_passed: true,
      },
      safety_invariants: {
        deploy_channel_status_only: true,
        places_order: false,
        calls_order_lifecycle: false,
        exchange_write_called: false,
        withdrawal_or_transfer_created: false,
        mutates_secrets: false,
        mutates_live_profile: false,
        mutates_order_sizing: false,
      },
    });
  }
  await writeJson(path.join(reportDir, "strategygroup-runtime-goal-status.json"), {
    scope: "strategygroup_runtime_goal_status",
    status: "waiting_for_signal",
    owner_state: {
      status: "waiting_for_opportunity",
      label: "等待机会",
      next_safe_checkpoint: "continue_watcher_observation",
      needs_owner_action: false,
    },
    real_order_boundary: {
      ready_for_real_order_action: false,
    },
    evidence: {
      submit_blocker_review: {
        required: false,
        allowed: false,
        project_progress_allowed: false,
        continue_observation_allowed: false,
        real_submit_allowed: false,
        next_safe_checkpoint: "continue_watcher_observation",
        blocker_keys: [],
      },
    },
    real_order_readiness_matrix: [
      { key: "selected_strategygroup_scope", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "fresh_signal", status: "waiting_for_market", blocker_class: "waiting_for_market", blocks_real_submit: true },
      { key: "required_facts", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "candidate_authorization", status: "waiting_for_market", blocker_class: "waiting_for_market", blocks_real_submit: true },
      { key: "action_time_finalgate", status: "waiting_for_market", blocker_class: "waiting_for_market", blocks_real_submit: true },
      { key: "official_operation_layer", status: "waiting_for_chain", blocker_class: "missing_fact", blocks_real_submit: true },
      { key: "active_position_open_order", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "protection", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "budget", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "duplicate_submit", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "symbol_side_notional_leverage_scope", status: "pass", blocker_class: "none", blocks_real_submit: false },
      { key: "hard_safety", status: "pass", blocker_class: "none", blocks_real_submit: false },
    ],
    safety_invariants: {
      ...noWriteSafety,
      reads_existing_evidence_only: true,
    },
  });
  return {
    cleanupPath: dir,
    liveFactsPath,
    reportDir,
  };
}

function startBackend({ liveFactsPath, reportDir }) {
  return spawn(
    pythonBin,
    [
      "owner-runtime-console/scripts/start-main-api-smoke.py",
      String(apiPort),
    ],
    {
      cwd: backendCwd,
      env: {
        ...process.env,
        SMOKE_BRC_OPERATOR_USERNAME: username,
        SMOKE_BRC_OPERATOR_PASSWORD_HASH: passwordHash(),
        SMOKE_BRC_OPERATOR_TOTP_SECRET: totpSecret,
        SMOKE_BRC_OPERATOR_SESSION_SECRET: "owner-console-mainline-smoke-session-secret",
        SMOKE_BRC_OPERATOR_SESSION_TTL_SECONDS: "3600",
        BRC_SIGNAL_WATCHER_REPORT_DIR: reportDir,
        BRC_STRATEGY_GROUP_HANDOFF_DIR: path.join(backendCwd, "docs/current/strategy-group-handoffs"),
        BRC_STRATEGY_GROUP_LIVE_FACTS_PATH: liveFactsPath,
        PYTHONPATH: backendCwd,
      },
      stdio: "inherit",
    },
  );
}

function startFrontend({ port = frontendPort, apiTarget = apiUrl } = {}) {
  return spawn(
    "node",
    ["scripts/serve-console.mjs", "--port", String(port), "--api-target", apiTarget],
    {
    cwd: process.cwd(),
    env: {
      ...process.env,
      OWNER_RUNTIME_API_PROXY_TARGET: apiTarget,
      VITE_OWNER_SOURCE_READINESS_ENABLED: "true",
      VITE_OWNER_USE_MOCK: "false",
    },
    stdio: "inherit",
    },
  );
}

async function isReachable(url) {
  try {
    const response = await fetch(url, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isReachable(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error(`Server did not become ready at ${url}`);
}

async function expectVisible(page, text) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({
      state: "visible",
      timeout: 7_000,
    });
  } catch (error) {
    const body = await page.locator("body").innerText().catch(() => "");
    throw new Error(`Expected visible text not found: ${text}\nPage text:\n${body.slice(0, 4000)}`, { cause: error });
  }
}

async function expectAbsent(page, text) {
  const count = await page.getByText(text, { exact: false }).count();
  if (count > 0) {
    throw new Error(`Forbidden text visible: ${text}`);
  }
}

async function openNav(page, label, expectedText) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await expectVisible(page, expectedText);
  await page.waitForTimeout(250);
}

async function expectActiveNav(page, label) {
  const active = page.locator('nav button[aria-current="page"]');
  const count = await active.count();
  const visibleTexts = [];
  for (let index = 0; index < count; index += 1) {
    const item = active.nth(index);
    if (await item.isVisible()) {
      visibleTexts.push((await item.innerText()).trim());
    }
  }
  if (visibleTexts.length !== 1) {
    throw new Error(`Expected one visible active nav item, got ${visibleTexts.length}: ${visibleTexts.join(", ")}`);
  }
  if (visibleTexts[0] !== label) {
    throw new Error(`Expected active nav ${label}, got ${visibleTexts[0]}`);
  }
}

async function stopProcess(child) {
  if (!child || child.killed) return;
  child.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 500));
}

async function login(context) {
  const response = await context.request.post(`${frontendUrl}/api/auth/login`, {
    data: {
      username,
      password,
      totp_code: totpCode(totpSecret),
    },
  });
  if (!response.ok()) {
    throw new Error(`Operator login failed: HTTP ${response.status()} ${await response.text()}`);
  }
}

async function runConnectedSmoke(browser, { deployChannelReady = false } = {}) {
  const expectedDeployChannel = deployChannelReady ? "部署通道正常" : "部署通道未检查";
  const fixtures = await createRuntimeFixtures({ deployChannelReady });
  const backend = startBackend(fixtures);
  const frontend = startFrontend();
  try {
    await waitForServer(`${apiUrl}/api/health`);
    await waitForServer(frontendUrl);

    const context = await browser.newContext({ viewport: { width: 1440, height: 1024 } });
    await login(context);
    const sourceResponse = await context.request.get(`${frontendUrl}/api/trading-console/owner-console-source-readiness`);
    const sourcePayload = await sourceResponse.json();
    console.log(
      "Source readiness:",
      JSON.stringify({
        status: sourcePayload?.data?.status,
        critical_unavailable_sources: sourcePayload?.data?.critical_unavailable_sources,
        owner_summary: sourcePayload?.data?.owner_summary,
      }, null, 2),
    );
    if (sourcePayload?.data?.owner_summary?.operation_audit !== "暂无审计动作") {
      throw new Error("Expected source-readiness operation audit to be ready_empty / 暂无审计动作");
    }
    if (sourcePayload?.data?.owner_summary?.market_opportunity !== "等待机会") {
      throw new Error("Expected source-readiness market opportunity to show 等待机会");
    }
    if (sourcePayload?.data?.owner_summary?.runtime_dry_run_audit !== "审计演练正常") {
      throw new Error("Expected source-readiness dry-run audit to show 审计演练正常");
    }
    if (sourcePayload?.data?.owner_summary?.deploy_channel !== expectedDeployChannel) {
      throw new Error(`Expected source-readiness deploy channel to show ${expectedDeployChannel}`);
    }
    const dryRunSummary = sourcePayload?.data?.source_health?.runtime_dry_run_audit?.summary;
    if (dryRunSummary?.scenario_count !== 12) {
      throw new Error("Expected source-readiness dry-run audit summary to include 12 scenarios");
    }
    if (dryRunSummary?.shared_runtime_pipeline_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm shared runtime pipeline");
    }
    if (dryRunSummary?.common_execution_chain_reuse_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm common execution-chain reuse");
    }
    if (dryRunSummary?.strategygroup_adapter_boundary_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm StrategyGroup adapter boundary");
    }
    if (dryRunSummary?.selected_strategygroup_dispatch_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm selected scope guard");
    }
    if (dryRunSummary?.all_selected_strategygroups_reach_finalgate_dispatch_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm all selected StrategyGroups reach FinalGate dispatch");
    }
    if (dryRunSummary?.operation_layer_hard_safety_blocker_matrix_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm hard safety blocker matrix coverage");
    }
    if (dryRunSummary?.expanded_watcher_scope_execution_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm expanded watcher scope execution guard");
    }
    if (dryRunSummary?.operation_layer_authorization_chain_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm operation evidence relay chain guard");
    }
    if (dryRunSummary?.post_submit_closed_loop_evidence_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm post-submit closed-loop evidence guard");
    }
    if (dryRunSummary?.operation_layer_submit_result_identity_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm Operation Layer submit result identity guard");
    }
    if (dryRunSummary?.post_submit_finalize_result_identity_guard_checked !== true) {
      throw new Error("Expected source-readiness dry-run audit summary to confirm post-submit finalize result identity guard");
    }
    if (sourcePayload?.data?.owner_summary?.real_order_readiness !== "等待机会") {
      throw new Error("Expected source-readiness real-order readiness to show 等待机会");
    }
    if (sourcePayload?.data?.real_order_readiness?.pass_count !== 8) {
      throw new Error("Expected source-readiness real-order readiness to include 8 passing checks");
    }
    if (sourcePayload?.data?.real_order_readiness?.submit_blocker_review?.required !== false) {
      throw new Error("Expected source-readiness real-order readiness to keep no-signal waiting out of submit-blocker review");
    }
    const page = await context.newPage();
    const consoleIssues = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        consoleIssues.push(`${message.type()}: ${message.text()}`);
      }
    });

    await page.goto(frontendUrl, { waitUntil: "networkidle" });
    await expectVisible(page, "BRC Owner Console");
    await expectVisible(page, "后端已连接");
    await expectVisible(page, "系统安全运行");
    await expectVisible(page, "等待机会");
    await expectVisible(page, "观察中，等待机会");
    await expectVisible(page, "实盘边界");
    await expectVisible(page, "实盘状态等待机会");
    await expectVisible(page, "8 项正常");
    await expectVisible(page, "4 项等待");
    await expectVisible(page, "0 项不可用");
    await expectAbsent(page, "系统审查已记录");
    await expectVisible(page, "资金正常");
    await expectVisible(page, "暂无订单");
    await expectVisible(page, "暂无持仓");
    await expectVisible(page, "对账正常");
    for (const strategy of ["MPG", "TEQ", "FBS", "SOR", "PMR"]) {
      await expectVisible(page, strategy);
    }
    await expectAbsent(page, "实盘状态暂不可用");
    await expectAbsent(page, "需要介入 1");

    await openNav(page, "系统", "只读保证");
    await expectActiveNav(page, "系统");
    await expectVisible(page, "策略组可见");
    await expectVisible(page, "审计演练正常");
    await expectVisible(page, "审计演练摘要");
    await expectVisible(page, "演练场景");
    await expectVisible(page, "12 项通过");
    await expectVisible(page, "观察范围");
    await expectVisible(page, "已隔离");
    await expectVisible(page, "证据接力");
    await expectVisible(page, "已校验");
    await expectVisible(page, "闭环证据");
    await expectVisible(page, "已校验");
    await expectVisible(page, "提交回执");
    await expectVisible(page, "已校验");
    await expectVisible(page, "收尾回执");
    await expectVisible(page, "已校验");
    await expectVisible(page, "共性管道");
    await expectVisible(page, "已覆盖");
    await expectVisible(page, "执行复用");
    await expectVisible(page, "已验证");
    await expectVisible(page, "选中范围");
    await expectVisible(page, "已校验");
    await expectVisible(page, "危险动作");
    await expectVisible(page, "未发生");
    await expectVisible(page, "实盘边界");
    await expectVisible(page, "部署通道");
    await expectVisible(page, expectedDeployChannel);
    await expectVisible(page, "owner_console_source_readiness");
    await page.screenshot({
      path: path.join(
        artifactDir,
        deployChannelReady
          ? "real-backend-system-deploy-channel-ready.png"
          : "real-backend-system.png",
      ),
      fullPage: true,
    });
    await openNav(page, "订单与持仓", "级联视图");
    await expectActiveNav(page, "订单与持仓");
    await expectVisible(page, "成交单");
    await expectVisible(page, "保护单");

    for (const text of forbidden) {
      await expectAbsent(page, text);
    }

    await page.screenshot({
      path: path.join(
        artifactDir,
        deployChannelReady
          ? "real-backend-connected-deploy-channel-ready.png"
          : "real-backend-connected.png",
      ),
      fullPage: true,
    });
    await context.close();

    if (consoleIssues.length > 0) {
      throw new Error(`Connected real-backend console issues:\n${consoleIssues.join("\n")}`);
    }
  } finally {
    await stopProcess(frontend);
    await stopProcess(backend);
    await rm(fixtures.cleanupPath, { recursive: true, force: true });
  }
}

async function runUnavailableSmoke(browser) {
  const deadApiTarget = `http://127.0.0.1:${apiPort + 97}`;
  const port = frontendPort + 1;
  const url = `http://127.0.0.1:${port}`;
  const frontend = startFrontend({ port, apiTarget: deadApiTarget });
  try {
    await waitForServer(url);
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto(url, { waitUntil: "networkidle" });
    await expectVisible(page, "运行状态不可用");
    await expectVisible(page, "资金路径保持关闭");
    await expectAbsent(page, "系统安全运行");
    await expectAbsent(page, "mock");
    await page.screenshot({
      path: path.join(artifactDir, "real-backend-unavailable.png"),
      fullPage: true,
    });
    await page.close();
  } finally {
    await stopProcess(frontend);
  }
}

await mkdir(artifactDir, { recursive: true });

const browser = await chromium.launch();
try {
  await runConnectedSmoke(browser);
  await runConnectedSmoke(browser, { deployChannelReady: true });
  await runUnavailableSmoke(browser);
} finally {
  await browser.close();
}

console.log(`Real backend smoke passed: ${frontendUrl} -> ${apiUrl}`);
console.log(`Screenshots: ${artifactDir}`);
