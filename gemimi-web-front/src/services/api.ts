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
  ConfigSnapshot,
  PortfolioContext,
} from '@/src/types';

const BASE_URL = 'http://localhost:8000'; // Backend server address

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
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
  const res = await request<{ signals: any[] }>('/api/runtime/signals');
  return (res.signals || []).map(sig => ({
    id: sig.signal_id,
    symbol: sig.symbol,
    timeframe: sig.timeframe,
    direction: sig.direction,
    strategy_name: sig.strategy_name,
    score: sig.score || 0,
    status: sig.status || 'FIRED',
    created_at: sig.created_at
  }));
}

/**
 * Adapter for Attempts
 */
export async function getRuntimeAttempts(): Promise<Attempt[]> {
  const res = await request<{ attempts: any[] }>('/api/runtime/attempts');
  return (res.attempts || []).map(att => ({
    id: att.attempt_id,
    symbol: att.symbol,
    timeframe: att.timeframe,
    direction: att.direction || 'FLAT', // Now provided by backend ConsoleAttemptItem
    strategy_name: att.strategy_name || 'N/A', // Now provided by backend ConsoleAttemptItem
    final_result: att.final_result === 'ACCEPTED' ? 'ACCEPTED' : 'REJECTED',
    filter_results_summary: att.filter_reason || att.reject_reason || '--',
    reject_reason: att.reject_reason || '',
    timestamp: att.created_at
  }));
}

/**
 * Adapter for Execution Intents
 */
export async function getRuntimeExecutionIntents(): Promise<ExecutionIntent[]> {
  const res = await request<{ intents: any[] }>('/api/runtime/execution/intents');
  return (res.intents || []).map(intent => ({
    intent_id: intent.intent_id,
    signal_id: intent.related_signal_id || 'N/A',
    symbol: intent.symbol,
    status: intent.status as any,
    created_at: intent.created_at,
    updated_at: intent.updated_at || intent.created_at
  }));
}

/**
 * Adapter for Orders
 */
export async function getRuntimeOrders(): Promise<Order[]> {
  const res = await request<{ orders: any[] }>('/api/runtime/execution/orders');
  return (res.orders || []).map(ord => ({
    order_id: ord.order_id,
    role: (ord.side || 'ENTRY') as any, // Use side (BUY/SELL) as role for better visibility
    symbol: ord.symbol,
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
export async function getReviewSummary(candidateName: string): Promise<any> {
  return request<any>(`/api/research/candidates/${candidateName}/review-summary`);
}

/**
 * Adapter for Config Snapshot
 */
export async function getConfigSnapshot(): Promise<ConfigSnapshot> {
  return request<ConfigSnapshot>('/api/config/snapshot');
}
