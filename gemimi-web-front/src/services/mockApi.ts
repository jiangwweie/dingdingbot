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
  FreshnessStatus
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
    freshness_status: currentFreshness
  };
}

export async function getRuntimeSignals(): Promise<Signal[]> {
  await delay(300);
  return [
    { id: 'sig_1001', symbol: 'ETH/USDT', timeframe: '5m', direction: 'LONG', strategy_name: 'Alpha_V2', score: 0.85, status: 'FIRED', created_at: new Date(Date.now() - 30000).toISOString() },
    { id: 'sig_1002', symbol: 'ETH/USDT', timeframe: '5m', direction: 'SHORT', strategy_name: 'Beta_Rev', score: 0.72, status: 'REJECTED', created_at: new Date(Date.now() - 180000).toISOString() },
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
    { intent_id: 'int_001', signal_id: 'sig_1001', symbol: 'ETH/USDT', status: 'COMPLETED', created_at: new Date(Date.now() - 28000).toISOString(), updated_at: new Date(Date.now() - 26000).toISOString() },
  ];
}

export async function getRuntimeOrders(): Promise<Order[]> {
  await delay(250);
  return [
    { order_id: 'ord_901', role: 'ENTRY', symbol: 'ETH/USDT', status: 'FILLED', quantity: 1.5, price: 3450.25, updated_at: new Date(Date.now() - 25000).toISOString() },
    { order_id: 'ord_902', role: 'TP', symbol: 'ETH/USDT', status: 'NEW', quantity: 1.5, price: 3500.00, updated_at: new Date(Date.now() - 25000).toISOString() },
    { order_id: 'ord_903', role: 'SL', symbol: 'ETH/USDT', status: 'NEW', quantity: 1.5, price: 3400.00, updated_at: new Date(Date.now() - 25000).toISOString() },
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
    metadata: { study_name: 'eth_study_1', trials: 500, duration_seconds: 3600 },
    best_trial: { number: 412, value: 2.45, params: { rsi_period: 14, macd_fast: 12 } },
    top_trials: [
      { number: 412, value: 2.45 },
      { number: 189, value: 2.41 }
    ],
    fixed_params: { symbol: 'ETH/USDT', timeframe: '5m' },
    runtime_overrides: { 'RSI_PERIOD': 14, 'MACD_FAST': 12 },
    constraints: { min_trades: 100, max_drawdown: 0.25 },
    resolved_request: '严格 v1 评估已完成 (Strict v1 evaluation complete.)',
    rubric_evaluation: { 'sharpe_ratio': 2.45, 'total_trades': 150, 'max_drawdown': 0.12 }
  };
}

export async function getReplayContext(candidateName: string): Promise<ReplayContext> {
  await delay(200);
  return {
    candidate_name: candidateName,
    reproduce_cmd: `poetry run python -m src.tools.replay --candidate ${candidateName} --output-dir reports/replay`,
    metadata: { created_by: 'optuna_worker', engine: 'v2' },
    resolved_request: { mode: 'replay', timeframe: '5m', start: '2026-01-01', end: '2026-04-01' },
    runtime_overrides: { 'RSI_PERIOD': 14, 'MACD_FAST': 12 }
  };
}
