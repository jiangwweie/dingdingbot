import {
  RuntimeOverview,
  Signal,
  Attempt,
  ExecutionIntent,
  Order,
  RuntimeHealth,
  Candidate,
  CandidateDetail,
  ReplayContext,
  BacktestRecord,
  CompareResponse,
  CompareRow,
  PortfolioContext,
  AppEvent,
  ConfigSnapshot,
  FreshnessStatus,
  CandidateRecord,
  CandidateRecordStatus,
  ResearchJob,
  ResearchJobAccepted,
  ResearchJobListResponse,
  ResearchJobStatus,
  ResearchRunListResponse,
  ResearchRunReport,
  ResearchRunResult,
  ResearchSpec
} from '@/src/types';

// Utility to simulate network delay
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

let refreshCount = 0;

export async function getRuntimeOverview(): Promise<RuntimeOverview> {
  await delay(400);
  refreshCount++;

  // Rotate freshness on each refresh to demonstrate the UI handling
  const freshnessOptions: FreshnessStatus[] = ['Fresh', 'Stale', 'Possibly Dead'];
  const currentFreshness = freshnessOptions[refreshCount % 3];

  const isDead = currentFreshness === 'Possibly Dead';
  const isStale = currentFreshness === 'Stale';

  return {
    profile: 'sim1_eth_runtime',
    version: '1.4.2',
    hash: 'a7b8c9d0',
    frozen: isDead,
    symbol: 'ETH/USDT',
    timeframe: '5m',
    mode: 'SIM-1',
    backend_summary: isDead ? '执行器无响应 (Executor strictly unresponsive)' : '主执行器运行中 (Primary executor Active)',
    exchange_health: isDead ? 'DOWN' : (isStale ? 'DEGRADED' : 'OK'),
    pg_health: isDead ? 'DOWN' : 'OK',
    webhook_health: isDead ? 'DOWN' : 'OK',
    breaker_count: isDead ? 5 : 0,
    reconciliation_summary: isDead ? '校验超时 (Timeout)' : '所有校验通过 (差异: 0.00)',
    server_time: new Date().toISOString(),
    last_runtime_update_at: new Date(Date.now() - (isDead ? 300000 : (isStale ? 60000 : 2000))).toISOString(),
    last_heartbeat_at: new Date(Date.now() - (isDead ? 300000 : (isStale ? 60000 : 1000))).toISOString(),
    freshness_status: currentFreshness,
    active_positions: 1,
    active_signals: 2,
    pending_intents: 0,
    pending_recovery_tasks: isDead ? 3 : 0,
    total_equity: 105240.50,
    unrealized_pnl: 1240.50,
  };
}

export async function getRuntimeSignals(): Promise<Signal[]> {
  await delay(300);
  return [
    { id: 'sig_1001', symbol: 'ETH/USDT:USDT', timeframe: '5m', direction: 'LONG', strategy_name: 'Pinbar EMA Trend', score: 0.85, status: 'executed', created_at: new Date(Date.now() - 30000).toISOString(), entry_price: 3245.50, stop_loss: 3210.00, position_size: 0.5, suggested_stop_loss: 3210.00, risk_reward_info: '1:2.5', tags: [{ name: 'EMA', value: 'Bullish' }] },
    { id: 'sig_1002', symbol: 'BTC/USDT:USDT', timeframe: '15m', direction: 'SHORT', strategy_name: 'Engulfing ATR', score: 0.72, status: 'blocked_by_risk', created_at: new Date(Date.now() - 180000).toISOString(), entry_price: 94200.00, stop_loss: 94800.00, position_size: 0.02, suggested_stop_loss: 94800.00, risk_reward_info: '1:1.8', tags: [{ name: 'ATR', value: 'High Volatility' }] },
    { id: 'sig_1003', symbol: 'SOL/USDT:USDT', timeframe: '1h', direction: 'LONG', strategy_name: 'Pinbar EMA Trend', score: 0.55, status: 'pending', created_at: new Date(Date.now() - 600000).toISOString(), entry_price: 178.20, stop_loss: 175.50, position_size: 5.0, suggested_stop_loss: 175.50, risk_reward_info: '1:2.0', tags: [{ name: 'EMA', value: 'Neutral' }] },
    { id: 'sig_1004', symbol: 'BNB/USDT:USDT', timeframe: '4h', direction: 'LONG', strategy_name: 'Pinbar EMA Trend', score: 0.71, status: 'expired', created_at: new Date(Date.now() - 86400000).toISOString(), entry_price: 625.00, stop_loss: 618.00, position_size: 1.0, suggested_stop_loss: 618.00, risk_reward_info: '1:3.0', tags: [] },
  ];
}

export async function getRuntimeAttempts(): Promise<Attempt[]> {
  await delay(300);
  return [
    { id: 'att_201', symbol: 'ETH/USDT', timeframe: '5m', direction: 'LONG', strategy_name: 'Alpha_V2', final_result: 'ACCEPTED', filter_results_summary: 'Passed 4/4', reject_reason: '', timestamp: new Date(Date.now() - 29000).toISOString() },
    { id: 'att_202', symbol: 'ETH/USDT', timeframe: '5m', direction: 'SHORT', strategy_name: 'Beta_Rev', final_result: 'REJECTED', filter_results_summary: 'Passed 3/4', reject_reason: 'Volatility Filter Tripped', timestamp: new Date(Date.now() - 179000).toISOString() },
  ];
}

export async function getRuntimeExecutionIntents(): Promise<ExecutionIntent[]> {
  await delay(200);
  return [
    { intent_id: 'int_001', signal_id: 'sig_1001', symbol: 'ETH/USDT:USDT', status: 'filled', created_at: new Date(Date.now() - 28000).toISOString(), updated_at: new Date(Date.now() - 26000).toISOString(), direction: 'LONG', intent_type: 'ENTRY', amount: 0.5, entry_price: 3245.50, stop_loss: 3210.00, order_id: 'ord_901' },
    { intent_id: 'int_002', signal_id: 'sig_1002', symbol: 'BTC/USDT:USDT', status: 'rejected', created_at: new Date(Date.now() - 7200000).toISOString(), updated_at: new Date(Date.now() - 7190000).toISOString(), direction: 'SHORT', intent_type: 'ENTRY', amount: 0.02, entry_price: 94200.00, stop_loss: 94800.00, reject_reason: 'Daily loss Limit Exceeded' },
    { intent_id: 'int_003', signal_id: 'sig_1003', symbol: 'SOL/USDT:USDT', status: 'pending', created_at: new Date(Date.now() - 600000).toISOString(), direction: 'LONG', intent_type: 'ENTRY', amount: 5.0, entry_price: 178.20, stop_loss: 175.50 },
  ];
}

export async function getRuntimeOrders(): Promise<Order[]> {
  await delay(250);
  return [
    { order_id: 'ord_901', role: 'ENTRY', raw_role: 'ENTRY', symbol: 'ETH/USDT:USDT', status: 'FILLED', quantity: 1.5, price: 3450.25, updated_at: new Date(Date.now() - 25000).toISOString() },
    { order_id: 'ord_902', role: 'TP', raw_role: 'TP1', symbol: 'ETH/USDT:USDT', type: 'LIMIT', status: 'NEW', quantity: 0.75, price: 3500.00, updated_at: new Date(Date.now() - 25000).toISOString() },
    { order_id: 'ord_903', role: 'TP', raw_role: 'TP2', symbol: 'ETH/USDT:USDT', type: 'LIMIT', status: 'NEW', quantity: 0.75, price: 3550.00, updated_at: new Date(Date.now() - 25000).toISOString() },
    { order_id: 'ord_904', role: 'SL', raw_role: 'SL', symbol: 'ETH/USDT:USDT', type: 'STOP_MARKET', status: 'NEW', quantity: 1.5, price: 3400.00, updated_at: new Date(Date.now() - 25000).toISOString() },
  ];
}

export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  await delay(400);
  const isDead = (refreshCount % 3 === 2); // 0=Fresh, 1=Stale, 2=Dead
  const isStale = (refreshCount % 3 === 1);

  return {
    pg_status: isDead ? 'DOWN' : 'OK',
    exchange_status: isDead ? 'DOWN' : (isStale ? 'DEGRADED' : 'OK'),
    notification_status: 'OK',
    recent_warnings: isDead ? [] : ['检测到 CCXT fetch_ticker 延迟峰值 (150ms)', '执行同步出现 50ms 的延迟'],
    recent_errors: isDead ? ['失去与交易所 WebSocket 的连接', '心跳检测超时 (>5min)', '数据库写入失败'] : [],
    startup_markers: {
      'Config Load (加载配置)': 'PASSED',
      'Exchange Connect (连接到交易所)': isDead ? 'FAILED' : 'PASSED',
      'State Restore (状态恢复)': isDead ? 'FAILED' : 'PASSED',
      'Start Event Loop (启动事件循环)': isDead ? 'PENDING' : 'PASSED'
    },
    breaker_summary: {
      total_tripped: isDead ? 5 : 0,
      active_breakers: isDead ? ['EXCHANGE_API_ERROR', 'MAX_DRAWDOWN_EXCEEDED'] : [],
      last_trip_time: isDead ? new Date().toISOString() : null
    },
    recovery_summary: {
      pending_tasks: isDead ? 3 : 0,
      completed_tasks: 12,
      last_recovery_time: new Date(Date.now() - 3600000).toISOString()
    }
  };
}

export async function getCandidates(): Promise<Candidate[]> {
  await delay(400);
  return [
    { candidate_name: 'cand_eth_alpha_01', generated_at: new Date(Date.now() - 86400000).toISOString(), source_profile: 'optuna_daily', git_commit: 'abc1237', objective: 'maximize_sharpe', review_status: 'PASS_STRICT', strict_gate_result: 'PASSED', warnings: [] },
    { candidate_name: 'cand_eth_beta_14', generated_at: new Date(Date.now() - 172800000).toISOString(), source_profile: 'optuna_weekly', git_commit: 'def4568', objective: 'maximize_return', review_status: 'PASS_STRICT_WITH_WARNINGS', strict_gate_result: 'PASSED', warnings: ['sortino_missing_or_suspect'] },
    { candidate_name: 'cand_eth_gamma_09', generated_at: new Date(Date.now() - 259200000).toISOString(), source_profile: 'optuna_daily', git_commit: 'abc1237', objective: 'maximize_sharpe', review_status: 'REJECT', strict_gate_result: 'FAILED', warnings: ['parameter_near_boundary'] },
  ];
}

export async function getCandidateDetail(candidateName: string): Promise<CandidateDetail> {
  await delay(300);
  return {
    candidate_name: candidateName,
    metadata: {
      candidate_name: candidateName,
      generated_at: new Date(Date.now() - 86400000).toISOString(),
      source_profile: { name: 'optuna_daily', version: 4, config_hash: 'cfg_abc123' },
      git: { branch: 'dev', commit: 'abc1237', is_dirty: false },
      objective: 'maximize_sharpe',
      status: 'candidate_only'
    },
    best_trial: {
      trial_number: 412,
      objective_value: 2.45,
      sharpe_ratio: 2.45,
      sortino_ratio: 3.12,
      total_return: 0.41,
      max_drawdown: 0.12,
      total_trades: 150,
      win_rate: 0.58,
      params: { rsi_period: 14, macd_fast: 12 }
    },
    top_trials: [
      { trial_number: 412, objective_value: 2.45, params: { rsi_period: 14, macd_fast: 12 }, total_trades: 150 },
      { trial_number: 189, objective_value: 2.41, params: { rsi_period: 21, macd_fast: 10 }, total_trades: 143 }
    ],
    fixed_params: { symbol: 'ETH/USDT', timeframe: '5m' },
    runtime_overrides: { 'RSI_PERIOD': 14, 'MACD_FAST': 12 },
    constraints: { min_trades: 100, max_drawdown: 0.25 },
    resolved_request: { mode: 'strict_v1_review', candidate_name: candidateName },
    reproduce_cmd: `poetry run python -m src.tools.replay --candidate ${candidateName}`
  };
}

export async function getReplayContext(candidateName: string): Promise<ReplayContext> {
  await delay(200);
  return {
    candidate_name: candidateName,
    reproduce_cmd: `poetry run python -m src.tools.replay --candidate ${candidateName} --output-dir reports/replay`,
    metadata: {
      candidate_name: candidateName,
      generated_at: new Date(Date.now() - 86400000).toISOString(),
      source_profile: { name: 'optuna_daily', version: 4, config_hash: 'cfg_abc123' },
      git: { branch: 'dev', commit: 'abc1237', is_dirty: false },
      objective: 'maximize_sharpe',
      status: 'candidate_only'
    },
    resolved_request: { mode: 'replay', timeframe: '5m', start: '2026-01-01', end: '2026-04-01' },
    runtime_overrides: { 'RSI_PERIOD': 14, 'MACD_FAST': 12 }
  };
}

export async function getBacktests(): Promise<BacktestRecord[]> {
  await delay(400);
  return [
    {
      id: 'bt_20260401_01',
      candidate_ref: 'cand_eth_alpha_01',
      symbol: 'ETH/USDT',
      timeframe: '5m',
      start_date: '2025-01-01',
      end_date: '2026-01-01',
      status: 'COMPLETED',
      metrics: { total_return: 0.45, sharpe: 2.1, max_drawdown: 0.15, win_rate: 0.54, trades: 1250 }
    },
    {
      id: 'bt_20260401_02',
      candidate_ref: 'cand_eth_beta_14',
      symbol: 'ETH/USDT',
      timeframe: '5m',
      start_date: '2025-01-01',
      end_date: '2026-01-01',
      status: 'COMPLETED',
      metrics: { total_return: 0.38, sharpe: 1.8, max_drawdown: 0.18, win_rate: 0.51, trades: 840 }
    },
    {
      id: 'bt_20260402_01',
      candidate_ref: 'cand_eth_gamma_09',
      symbol: 'ETH/USDT',
      timeframe: '5m',
      start_date: '2025-06-01',
      end_date: '2026-04-01',
      status: 'FAILED',
      metrics: { total_return: 0, sharpe: 0, max_drawdown: 0, win_rate: 0, trades: 0 }
    }
  ];
}

export async function getCompareData(): Promise<CompareResponse> {
  await delay(300);
  return {
    baseline_label: "cand_eth_alpha_01",
    candidate_a_label: "cand_eth_beta_14",
    candidate_b_label: null,
    rows: [
      { metric: "Total Return", baseline: 0.25, candidate_a: 0.45, candidate_b: null, diff_a: 0.20, diff_b: null },
      { metric: "Sharpe", baseline: 1.5, candidate_a: 2.1, candidate_b: null, diff_a: 0.6, diff_b: null },
      { metric: "Max Drawdown", baseline: 0.22, candidate_a: 0.15, candidate_b: null, diff_a: -0.07, diff_b: null },
      { metric: "Win Rate", baseline: 0.48, candidate_a: 0.54, candidate_b: null, diff_a: 0.06, diff_b: null },
      { metric: "Trades", baseline: 950, candidate_a: 1250, candidate_b: null, diff_a: 300, diff_b: null },
    ],
  };
}

const mockResearchJobs: ResearchJob[] = [
  {
    id: 'rj_mock_001',
    kind: 'backtest',
    name: 'eth-baseline-window-a',
    spec_ref: 'reports/research_runs/rj_mock_001/spec.json',
    status: 'SUCCEEDED',
    run_result_id: 'rr_mock_001',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    started_at: new Date(Date.now() - 3500000).toISOString(),
    finished_at: new Date(Date.now() - 3300000).toISOString(),
    requested_by: 'local',
    error_code: null,
    error_message: null,
    progress_pct: 100,
    spec: {
      name: 'eth-baseline-window-a',
      symbol: 'ETH/USDT:USDT',
      timeframe: '1h',
      start_time_ms: Date.now() - 30 * 86400000,
      end_time_ms: Date.now(),
      profile_name: 'backtest_eth_baseline',
      limit: 9000,
      mode: 'v3_pms',
    },
  },
  {
    id: 'rj_mock_002',
    kind: 'backtest',
    name: 'eth-regime-boundary-check',
    spec_ref: 'reports/research_runs/rj_mock_002/spec.json',
    status: 'RUNNING',
    run_result_id: null,
    created_at: new Date(Date.now() - 600000).toISOString(),
    started_at: new Date(Date.now() - 580000).toISOString(),
    finished_at: null,
    requested_by: 'local',
    error_code: null,
    error_message: null,
    progress_pct: 35,
    spec: {
      name: 'eth-regime-boundary-check',
      symbol: 'ETH/USDT:USDT',
      timeframe: '4h',
      start_time_ms: Date.now() - 90 * 86400000,
      end_time_ms: Date.now(),
      profile_name: 'backtest_eth_baseline',
      limit: 9000,
      mode: 'v3_pms',
    },
  },
];

const mockResearchRuns: ResearchRunResult[] = [
  {
    id: 'rr_mock_001',
    job_id: 'rj_mock_001',
    kind: 'backtest',
    spec_snapshot: { ...mockResearchJobs[0].spec },
    summary_metrics: {
      total_return: 0.18,
      max_drawdown: 0.11,
      win_rate: 0.54,
      total_trades: 42,
      sharpe_ratio: 1.45,
      sortino_ratio: 2.1,
      total_pnl: 1800,
      final_balance: 11800,
    },
    artifact_index: {
      spec: 'reports/research_runs/rj_mock_001/spec.json',
      result: 'reports/research_runs/rj_mock_001/result.json',
      metrics: 'reports/research_runs/rj_mock_001/metrics.json',
    },
    source_profile: 'backtest_eth_baseline',
    generated_at: new Date(Date.now() - 3300000).toISOString(),
  },
];

let mockCandidateRecords: CandidateRecord[] = [
  {
    id: 'cand_mock_001',
    run_result_id: 'rr_mock_001',
    candidate_name: 'candidate-rr_mock_001',
    status: 'DRAFT',
    review_notes: 'mock candidate only',
    applicable_market: null,
    risks: [],
    recommendation: null,
    created_at: new Date(Date.now() - 3200000).toISOString(),
    updated_at: new Date(Date.now() - 3200000).toISOString(),
  },
];

export async function createResearchBacktestJob(spec: ResearchSpec): Promise<ResearchJobAccepted> {
  await delay(250);
  const jobId = `rj_mock_${String(mockResearchJobs.length + 1).padStart(3, '0')}`;
  mockResearchJobs.unshift({
    id: jobId,
    kind: 'backtest',
    name: spec.name,
    spec_ref: `reports/research_runs/${jobId}/spec.json`,
    status: 'PENDING',
    run_result_id: null,
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
    requested_by: 'local',
    error_code: null,
    error_message: null,
    progress_pct: null,
    spec,
  });
  return { status: 'accepted', job_id: jobId, job_status: 'PENDING' };
}

export async function getResearchJobs(
  status?: ResearchJobStatus | 'ALL',
  limit = 100,
  offset = 0,
): Promise<ResearchJobListResponse> {
  await delay(250);
  const rows = status && status !== 'ALL'
    ? mockResearchJobs.filter(job => job.status === status)
    : mockResearchJobs;
  return {
    jobs: rows.slice(offset, offset + limit),
    total: rows.length,
    limit,
    offset,
  };
}

export async function getResearchJob(jobId: string): Promise<ResearchJob> {
  await delay(200);
  const job = mockResearchJobs.find(row => row.id === jobId);
  if (!job) throw new Error(`Research job not found: ${jobId}`);
  return job;
}

export async function getResearchRuns(
  jobId?: string,
  limit = 100,
  offset = 0,
): Promise<ResearchRunListResponse> {
  await delay(250);
  const rows = jobId ? mockResearchRuns.filter(run => run.job_id === jobId) : mockResearchRuns;
  return {
    runs: rows.slice(offset, offset + limit),
    total: rows.length,
    limit,
    offset,
  };
}

export async function getResearchRun(runResultId: string): Promise<ResearchRunResult> {
  await delay(200);
  const run = mockResearchRuns.find(row => row.id === runResultId);
  if (!run) throw new Error(`Research run result not found: ${runResultId}`);
  return run;
}

export async function getResearchRunReport(runResultId: string): Promise<ResearchRunReport> {
  await delay(200);
  const run = mockResearchRuns.find(row => row.id === runResultId);
  if (!run) throw new Error(`Research run result not found: ${runResultId}`);
  return {
    ...run.summary_metrics,
    initial_balance: 10000,
    debug_equity_curve: [
      { timestamp: Date.now() - 6 * 86400000, equity: 10000 },
      { timestamp: Date.now() - 5 * 86400000, equity: 10120 },
      { timestamp: Date.now() - 4 * 86400000, equity: 10060 },
      { timestamp: Date.now() - 3 * 86400000, equity: 10840 },
      { timestamp: Date.now() - 2 * 86400000, equity: 11220 },
      { timestamp: Date.now() - 1 * 86400000, equity: 11800 },
    ],
    positions: [
      {
        position_id: 'pos_mock_001',
        signal_id: 'sig_mock_001',
        symbol: 'ETH/USDT:USDT',
        direction: 'LONG',
        entry_price: '3200',
        exit_price: '3368',
        entry_time: Date.now() - 5 * 86400000,
        exit_time: Date.now() - 4 * 86400000,
        realized_pnl: '420',
        exit_reason: 'TP2',
      },
      {
        position_id: 'pos_mock_002',
        signal_id: 'sig_mock_002',
        symbol: 'ETH/USDT:USDT',
        direction: 'LONG',
        entry_price: '3420',
        exit_price: '3385',
        entry_time: Date.now() - 3 * 86400000,
        exit_time: Date.now() - 2 * 86400000,
        realized_pnl: '-110',
        exit_reason: 'SL',
      },
    ],
    close_events: [
      {
        position_id: 'pos_mock_001',
        order_id: 'ord_mock_tp1',
        event_type: 'TP1',
        close_price: '3260',
        close_qty: '1.2',
        close_pnl: '120',
        close_fee: '1.2',
        close_time: Date.now() - 4 * 86400000,
        exit_reason: 'TP1',
      },
    ],
  };
}

export async function createCandidateRecord(runResultId: string, candidateName: string, reviewNotes = ''): Promise<CandidateRecord> {
  await delay(250);
  const candidate: CandidateRecord = {
    id: `cand_mock_${String(mockCandidateRecords.length + 1).padStart(3, '0')}`,
    run_result_id: runResultId,
    candidate_name: candidateName,
    status: 'DRAFT',
    review_notes: reviewNotes,
    applicable_market: null,
    risks: [],
    recommendation: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  mockCandidateRecords = [candidate, ...mockCandidateRecords];
  return candidate;
}

export async function getCandidateRecords(
  status?: CandidateRecordStatus | 'ALL',
): Promise<CandidateRecord[]> {
  await delay(250);
  return status && status !== 'ALL'
    ? mockCandidateRecords.filter(candidate => candidate.status === status)
    : mockCandidateRecords;
}

export async function getPortfolioContext(): Promise<PortfolioContext> {
  await delay(350);
  return {
    total_equity: 105240.50,
    available_balance: 45240.50,
    unrealized_pnl: 1240.50,
    total_exposure: 60000.00,
    daily_loss_used: 450.00,
    daily_loss_limit: 2000.00,
    max_total_exposure: 80000.00,
    leverage_usage: 1.5,
    positions: [
      {
        symbol: 'ETH/USDT',
        direction: 'LONG',
        quantity: 15.5,
        entry_price: 3400.00,
        current_price: 3480.03,
        unrealized_pnl: 1240.50,
        pnl_percent: 0.0235,
        leverage: 2.0
      }
    ]
  };
}

export async function getEvents(): Promise<AppEvent[]> {
  await delay(250);
  return [
    { id: 'evt_9', timestamp: new Date(Date.now() - 5000).toISOString(), category: 'EXECUTION', severity: 'SUCCESS', message: 'Order filled: 1.5 ETH/USDT @ 3420.50', related_entities: ['ord_904'] },
    { id: 'evt_8', timestamp: new Date(Date.now() - 6000).toISOString(), category: 'SIGNAL', severity: 'INFO', message: 'Signal accepted: Alpha_V2 LONG ETH/USDT', related_entities: ['sig_1003', 'att_203'] },
    { id: 'evt_7', timestamp: new Date(Date.now() - 360000).toISOString(), category: 'WARNING', severity: 'WARN', message: 'Latency spike detected on CCXT fetch_ticker (150ms)' },
    { id: 'evt_6', timestamp: new Date(Date.now() - 3600000).toISOString(), category: 'RECOVERY', severity: 'SUCCESS', message: 'Self-healing task completed: Restart Exchange WS' },
    { id: 'evt_5', timestamp: new Date(Date.now() - 3601000).toISOString(), category: 'ERROR', severity: 'ERROR', message: 'Exchange API timeout' },
    { id: 'evt_4', timestamp: new Date(Date.now() - 7200000).toISOString(), category: 'RECONCILIATION', severity: 'INFO', message: 'Hourly reconciliation passed. Diff: 0' },
    { id: 'evt_3', timestamp: new Date(Date.now() - 86400000).toISOString(), category: 'STARTUP', severity: 'SUCCESS', message: 'Event loop started' },
    { id: 'evt_2', timestamp: new Date(Date.now() - 86400000 - 500).toISOString(), category: 'STARTUP', severity: 'INFO', message: 'State restored from DB' },
    { id: 'evt_1', timestamp: new Date(Date.now() - 86400000 - 1000).toISOString(), category: 'STARTUP', severity: 'INFO', message: 'System startup initialized' }
  ];
}

export async function getConfigSnapshot(): Promise<ConfigSnapshot> {
  await delay(400);
  return {
    identity: {
      profile: 'sim1_eth_runtime',
      version: '4',
      hash: 'a7b8c9d0'
    },
    market: {
      symbols: ['ETH/USDT'],
      timeframes: ['5m', '15m', '1h'],
      mtf_enabled: true
    },
    strategy: {
      name: 'Alpha_V2_Enhanced',
      direction_bias: 'NEUTRAL',
      key_parameters: {
        rsi_period: 14,
        macd_fast: 12,
        macd_slow: 26,
        atr_multiplier: 2.5
      }
    },
    risk: {
      max_loss_percent: 0.15,
      daily_max_loss_percent: 0.02,
      max_total_exposure: 80000,
      leverage: 2.0
    },
    execution: {
      tp_targets: 2,
      tp_ratios: [0.5, 0.5],
      stop_behavior: 'TRAILING',
      same_bar_policy: 'REJECT'
    },
    backend: {
      intent: 'pg_intent_store',
      order: 'ccxt_binance_vms',
      position: 'pg_position_manager'
    },
    source_of_truth_hints: [
      'Environment variable SIM_MODE=1 overrides API routing',
      'Strategy config inherited from Candidate "cand_eth_alpha_01"',
      'Risk limits bounded by safety-policy.yaml',
      'Runtime config resolved from runtime_profiles via RuntimeConfigResolver',
      'Config profiles/entries are legacy — changes take effect on next startup only'
    ],
    profile: 'sim1_eth_runtime',
    version: 4,
    hash: 'a7b8c9d0',
    environment: {
      exchange_name: 'binance',
      exchange_testnet: true,
      mode: 'SIM-1'
    }
  };
}
