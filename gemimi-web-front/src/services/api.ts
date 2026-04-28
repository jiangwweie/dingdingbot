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
  ReviewSummary,
  ConfigSnapshot,
  PortfolioContext,
  AppEvent,
  BacktestRecord,
  CompareResponse,
  CandidateRecord,
  CandidateRecordStatus,
  ResearchJob,
  ResearchJobAccepted,
  ResearchJobListResponse,
  ResearchJobStatus,
  ResearchRunListResponse,
  ResearchRunReport,
  ResearchRunResult,
  ResearchSpec,
} from '@/src/types';

const BASE_URL = 'http://localhost:8000'; // Backend server address

type RuntimeSignalsPayload = {
  signals: Array<{
    signal_id: string;
    symbol: string;
    timeframe: string;
    direction: string;
    strategy_name: string;
    score?: number | null;
    status?: string | null;
    created_at: string;
    entry_price?: number | null;
    stop_loss?: number | null;
    position_size?: number | null;
    suggested_stop_loss?: number | null;
    suggested_position_size?: number | null;
    current_leverage?: number | null;
    risk_reward_info?: string | null;
    tags?: Array<{ name: string; value: string }> | null;
    updated_at?: string | null;
    expired_at?: string | null;
  }>;
};

type RuntimeAttemptsPayload = {
  attempts: Array<{
    attempt_id: string;
    signal_id?: string | null;
    symbol: string;
    timeframe: string;
    direction?: string | null;
    strategy_name?: string | null;
    final_result?: string | null;
    reject_reason?: string | null;
    filter_reason?: string | null;
    created_at: string;
  }>;
};

type RuntimeExecutionIntentsPayload = {
  intents: Array<{
    intent_id: string;
    symbol: string;
    status: string;
    created_at: string;
    updated_at?: string | null;
    related_signal_id?: string | null;
    side?: string | null;
    quantity?: number | null;
    direction?: string | null;
    intent_type?: string | null;
    amount?: number | null;
    entry_price?: number | null;
    stop_loss?: number | null;
    order_id?: string | null;
    reject_reason?: string | null;
  }>;
};

type RuntimeOrdersPayload = {
  orders: Array<{
    order_id: string;
    order_role?: string | null;
    symbol: string;
    type?: string | null;
    status: Order['status'];
    qty: number;
    price?: number | null;
    created_at: string;
    updated_at?: string | null;
  }>;
};

type RuntimeEventsPayload = {
  events: Array<{
    id: string;
    timestamp: string;
    category: AppEvent['category'];
    severity: AppEvent['severity'];
    message: string;
    related_entities?: string[];
  }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

/**
 * Adapter for Runtime Overview
 */
export async function getRuntimeOverview(): Promise<RuntimeOverview> {
  return request<RuntimeOverview>('/api/runtime/overview');
}

/**
 * Adapter for Portfolio
 */
export async function getPortfolioContext(): Promise<PortfolioContext> {
  return request<PortfolioContext>('/api/runtime/portfolio');
}

/**
 * Adapter for Health
 */
export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  return request<RuntimeHealth>('/api/runtime/health');
}

/**
 * Adapter for Candidates
 */
export async function getCandidates(): Promise<Candidate[]> {
  return request<Candidate[]>('/api/research/candidates');
}

/**
 * Adapter for Signals
 */
export async function getRuntimeSignals(): Promise<Signal[]> {
  const res = await request<RuntimeSignalsPayload>('/api/runtime/signals');
  return (res.signals || []).map(sig => ({
    id: sig.signal_id,
    symbol: sig.symbol,
    timeframe: sig.timeframe,
    direction: sig.direction,
    strategy_name: sig.strategy_name,
    score: sig.score || 0,
    status: sig.status ?? undefined,
    created_at: sig.created_at,
    entry_price: sig.entry_price ?? undefined,
    stop_loss: sig.stop_loss ?? undefined,
    position_size: sig.position_size ?? undefined,
    suggested_stop_loss: sig.suggested_stop_loss ?? undefined,
    risk_reward_info: sig.risk_reward_info ?? undefined,
    tags: sig.tags ?? undefined,
  }));
}

/**
 * Adapter for Attempts
 */
export async function getRuntimeAttempts(): Promise<Attempt[]> {
  const res = await request<RuntimeAttemptsPayload>('/api/runtime/attempts');
  return (res.attempts || []).map(att => ({
    id: att.attempt_id,
    symbol: att.symbol,
    timeframe: att.timeframe,
    direction: att.direction || '--',
    strategy_name: att.strategy_name || '--',
    final_result: att.final_result || '--',
    filter_results_summary: att.filter_reason || att.reject_reason || '--',
    reject_reason: att.reject_reason || '',
    timestamp: att.created_at
  }));
}

/**
 * Adapter for Execution Intents
 */
export async function getRuntimeExecutionIntents(): Promise<ExecutionIntent[]> {
  const res = await request<RuntimeExecutionIntentsPayload>('/api/runtime/execution/intents');
  return (res.intents || []).map(intent => ({
    intent_id: intent.intent_id,
    signal_id: intent.related_signal_id || '',
    symbol: intent.symbol,
    status: intent.status as any,
    created_at: intent.created_at,
    updated_at: intent.updated_at || intent.created_at,
    direction: intent.direction || intent.side || undefined,
    intent_type: intent.intent_type || undefined,
    amount: intent.amount ?? intent.quantity ?? undefined,
    entry_price: intent.entry_price ?? undefined,
    stop_loss: intent.stop_loss ?? undefined,
    order_id: intent.order_id || undefined,
    reject_reason: intent.reject_reason || undefined,
  }));
}

/**
 * Adapter for Orders
 */
export async function getRuntimeOrders(): Promise<Order[]> {
  const res = await request<RuntimeOrdersPayload>('/api/runtime/execution/orders');
  return (res.orders || []).map(ord => ({
    order_id: ord.order_id,
    role: String(ord.order_role || 'ENTRY').startsWith('TP')
      ? 'TP'
      : String(ord.order_role || 'ENTRY') === 'SL'
      ? 'SL'
      : 'ENTRY',
    raw_role: ord.order_role || 'ENTRY',
    symbol: ord.symbol,
    type: ord.type || undefined,
    status: ord.status as any,
    quantity: ord.qty,
    price: ord.price,
    updated_at: ord.updated_at || ord.created_at
  }));
}

/**
 * Adapter for Candidate Detail
 */
export async function getCandidateDetail(candidateName: string): Promise<CandidateDetail> {
  return request<CandidateDetail>(`/api/research/candidates/${candidateName}`);
}

/**
 * Adapter for Replay Context
 */
export async function getReplayContext(candidateName: string): Promise<ReplayContext> {
  return request<ReplayContext>(`/api/research/replay/${candidateName}`);
}

/**
 * Adapter for Review Summary
 */
export async function getReviewSummary(candidateName: string): Promise<ReviewSummary> {
  return request<ReviewSummary>(`/api/research/candidates/${candidateName}/review-summary`);
}

/**
 * Adapter for Config Snapshot
 */
export async function getConfigSnapshot(): Promise<ConfigSnapshot> {
  return request<ConfigSnapshot>('/api/config/snapshot');
}

/**
 * Adapter for Events Timeline
 */
export async function getRuntimeEvents(): Promise<AppEvent[]> {
  const res = await request<RuntimeEventsPayload>('/api/runtime/events');
  return (res.events || []).map(evt => ({
    id: evt.id,
    timestamp: evt.timestamp,
    category: evt.category,
    severity: evt.severity,
    message: evt.message,
    related_entities: evt.related_entities || [],
  }));
}

type ResearchBacktestsPayload = {
  backtests: Array<{
    id: string;
    candidate_ref: string;
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    status: BacktestRecord['status'];
    metrics: {
      total_return: number | null;
      sharpe: number | null;
      max_drawdown: number | null;
      win_rate: number | null;
      trades: number | null;
    };
  }>;
};

/**
 * Adapter for Research Backtests
 */
export async function getBacktests(): Promise<BacktestRecord[]> {
  const res = await request<ResearchBacktestsPayload>('/api/research/backtests');
  return (res.backtests || []).map(bt => ({
    id: bt.id,
    candidate_ref: bt.candidate_ref,
    symbol: bt.symbol,
    timeframe: bt.timeframe,
    start_date: bt.start_date,
    end_date: bt.end_date,
    status: bt.status,
    metrics: {
      total_return: bt.metrics.total_return,
      sharpe: bt.metrics.sharpe,
      max_drawdown: bt.metrics.max_drawdown,
      win_rate: bt.metrics.win_rate,
      trades: bt.metrics.trades,
    },
  }));
}

/**
 * Research Control Plane: create a backtest job.
 */
export async function createResearchBacktestJob(spec: ResearchSpec): Promise<ResearchJobAccepted> {
  return request<ResearchJobAccepted>('/api/research/jobs/backtest', {
    method: 'POST',
    body: JSON.stringify(spec),
  });
}

/**
 * Research Control Plane: list jobs.
 */
export async function getResearchJobs(
  status?: ResearchJobStatus | 'ALL',
  limit?: number,
  offset?: number,
): Promise<ResearchJobListResponse> {
  const params = new URLSearchParams();
  if (status && status !== 'ALL') params.set('status', status);
  if (limit !== undefined) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));
  const qs = params.toString();
  return request<ResearchJobListResponse>(`/api/research/jobs${qs ? `?${qs}` : ''}`);
}

export async function getResearchJob(jobId: string): Promise<ResearchJob> {
  return request<ResearchJob>(`/api/research/jobs/${jobId}`);
}

export async function getResearchRuns(
  jobId?: string,
  limit?: number,
  offset?: number,
): Promise<ResearchRunListResponse> {
  const params = new URLSearchParams();
  if (jobId) params.set('job_id', jobId);
  if (limit !== undefined) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));
  const qs = params.toString();
  return request<ResearchRunListResponse>(`/api/research/runs${qs ? `?${qs}` : ''}`);
}

export async function getResearchRun(runResultId: string): Promise<ResearchRunResult> {
  return request<ResearchRunResult>(`/api/research/runs/${runResultId}`);
}

export async function getResearchRunReport(runResultId: string): Promise<ResearchRunReport> {
  return request<ResearchRunReport>(`/api/research/runs/${runResultId}/report`);
}

export async function createCandidateRecord(runResultId: string, candidateName: string, reviewNotes = ''): Promise<CandidateRecord> {
  return request<CandidateRecord>('/api/research/candidates', {
    method: 'POST',
    body: JSON.stringify({
      run_result_id: runResultId,
      candidate_name: candidateName,
      review_notes: reviewNotes,
    }),
  });
}

export async function getCandidateRecords(status?: CandidateRecordStatus | 'ALL'): Promise<CandidateRecord[]> {
  const params = new URLSearchParams();
  if (status && status !== 'ALL') params.set('status', status);
  const qs = params.toString();
  return request<CandidateRecord[]>(`/api/research/candidate-records${qs ? `?${qs}` : ''}`);
}

/**
 * Adapter for Compare
 */
export async function getCompareData(
  baselineRef?: string,
  candidateA?: string,
  candidateB?: string,
): Promise<CompareResponse> {
  const params = new URLSearchParams();
  if (baselineRef) params.set('baseline_ref', baselineRef);
  if (candidateA) params.set('candidate_a', candidateA);
  if (candidateB) params.set('candidate_b', candidateB);
  const qs = params.toString();
  return request<CompareResponse>(`/api/research/compare/candidates${qs ? `?${qs}` : ''}`);
}
