import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getRuntimeOrders,
  createResearchBacktestJob,
  getResearchJobs,
  getResearchRuns,
  getResearchRun,
  getResearchJob,
  getResearchRunReport,
  createCandidateRecord,
  getCandidateRecords,
} from './api';
import type { ResearchSpec, ResearchJobAccepted, ResearchJobListResponse, ResearchRunListResponse, ResearchRunResult, ResearchJob, CandidateRecord, ResearchRunReport } from '@/src/types';

describe('getRuntimeOrders', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('maps order_role=ENTRY -> role=ENTRY, raw_role=ENTRY, keeps type, default type is undefined', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          {
            order_id: '1',
            order_role: 'ENTRY',
            symbol: 'BTC/USDT',
            type: 'LIMIT',
            status: 'NEW',
            qty: 1,
            price: 50000,
            created_at: '2026-04-26T00:00:00Z'
          }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({
      role: 'ENTRY',
      raw_role: 'ENTRY',
      type: 'LIMIT'
    }));
  });

  it('maps order_role=TP1/TP2/TP5 -> role=TP, raw_role preserves original value', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'TP1', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '2', order_role: 'TP2', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '3', order_role: 'TP5', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP1' }));
    expect(orders[1]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP2' }));
    expect(orders[2]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP5' }));
  });

  it('maps order_role=SL -> role=SL, raw_role=SL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'SL', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'SL', raw_role: 'SL' }));
  });

  it('defaults to ENTRY if order_role is missing', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'ENTRY', raw_role: 'ENTRY' }));
  });

  it('does not depend on side to map TP/SL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'TP1', side: 'SELL', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '2', order_role: 'SL', side: 'BUY', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP1' }));
    expect(orders[1]).toEqual(expect.objectContaining({ role: 'SL', raw_role: 'SL' }));
  });
});

// ── Research Control Plane API adapters ────────────────────────────────

describe('createResearchBacktestJob', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('sends POST to /api/research/jobs/backtest with spec as body', async () => {
    const spec: ResearchSpec = {
      name: 'ETH baseline',
      symbol: 'ETH/USDT:USDT',
      timeframe: '1h',
      start_time_ms: 1700000000000,
      end_time_ms: 1700086400000,
    };
    const accepted: ResearchJobAccepted = {
      status: 'accepted',
      job_id: 'rj_abc123',
      job_status: 'PENDING',
    };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => accepted,
    });

    const result = await createResearchBacktestJob(spec);
    expect(result).toEqual(accepted);
    expect(result.job_id).toBe('rj_abc123');

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/jobs/backtest');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual(spec);
    expect(init.headers['Content-Type']).toBe('application/json');
  });
});

describe('getResearchJobs', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/jobs without status when no param', async () => {
    const resp: ResearchJobListResponse = { jobs: [], total: 0, limit: 100, offset: 0 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resp });

    const result = await getResearchJobs();
    expect(result.total).toBe(0);
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/jobs');
  });

  it('appends status query param when provided', async () => {
    const resp: ResearchJobListResponse = { jobs: [], total: 0, limit: 100, offset: 0 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resp });

    await getResearchJobs('RUNNING');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/jobs?status=RUNNING');
  });

  it('omits status query param when ALL is passed', async () => {
    const resp: ResearchJobListResponse = { jobs: [], total: 0, limit: 100, offset: 0 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resp });

    await getResearchJobs('ALL');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/jobs');
  });
});

describe('getResearchRuns', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/runs without job_id when no param', async () => {
    const resp: ResearchRunListResponse = { runs: [], total: 0, limit: 100, offset: 0 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resp });

    const result = await getResearchRuns();
    expect(result.total).toBe(0);
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/runs');
  });

  it('appends job_id query param when provided', async () => {
    const run: ResearchRunResult = {
      id: 'rr_001',
      job_id: 'rj_001',
      kind: 'backtest',
      spec_snapshot: {},
      summary_metrics: { total_return: 0.15 },
      artifact_index: { result: '/tmp/r.json' },
      source_profile: null,
      generated_at: '2026-04-27T00:00:00Z',
    };
    const resp: ResearchRunListResponse = { runs: [run], total: 1, limit: 100, offset: 0 };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => resp });

    const result = await getResearchRuns('rj_001');
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0].job_id).toBe('rj_001');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/runs?job_id=rj_001');
  });
});

describe('getResearchRun', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/runs/{id}', async () => {
    const run: ResearchRunResult = {
      id: 'rr_detail',
      job_id: 'rj_001',
      kind: 'backtest',
      spec_snapshot: { symbol: 'BTC/USDT:USDT' },
      summary_metrics: {},
      artifact_index: {},
      source_profile: null,
      generated_at: '2026-04-27T00:00:00Z',
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => run });

    const result = await getResearchRun('rr_detail');
    expect(result.id).toBe('rr_detail');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/runs/rr_detail');
  });
});

describe('getResearchJob', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/jobs/{id}', async () => {
    const job: ResearchJob = {
      id: 'rj_single',
      kind: 'backtest',
      name: 'test',
      spec_ref: 'reports/rj_single/spec.json',
      status: 'SUCCEEDED',
      run_result_id: 'rr_001',
      created_at: '2026-04-27T00:00:00Z',
      started_at: null,
      finished_at: null,
      requested_by: 'local',
      error_code: null,
      error_message: null,
      progress_pct: 100,
      spec: {
        name: 'test',
        symbol: 'ETH/USDT:USDT',
        timeframe: '1h',
        start_time_ms: 1700000000000,
        end_time_ms: 1700086400000,
      },
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => job });

    const result = await getResearchJob('rj_single');
    expect(result.id).toBe('rj_single');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/jobs/rj_single');
  });
});

describe('getResearchRunReport', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/runs/{id}/report', async () => {
    const report: ResearchRunReport = {
      total_return: 0.1,
      total_trades: 10,
      debug_equity_curve: [],
      positions: [],
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => report });

    const result = await getResearchRunReport('rr_test_report');
    expect(result.total_trades).toBe(10);
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/runs/rr_test_report/report');
  });
});

describe('createCandidateRecord', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('sends POST to /api/research/candidates with correct body', async () => {
    const candidate: CandidateRecord = {
      id: 'cand_001',
      run_result_id: 'rr_001',
      candidate_name: 'ETH momentum v2',
      status: 'DRAFT',
      review_notes: 'Initial review',
      applicable_market: null,
      risks: [],
      recommendation: null,
      created_at: '2026-04-27T00:00:00Z',
      updated_at: '2026-04-27T00:00:00Z',
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => candidate });

    const result = await createCandidateRecord('rr_001', 'ETH momentum v2', 'Initial review');
    expect(result.candidate_name).toBe('ETH momentum v2');
    expect(result.run_result_id).toBe('rr_001');

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/candidates');
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({
      run_result_id: 'rr_001',
      candidate_name: 'ETH momentum v2',
      review_notes: 'Initial review',
    });
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('defaults review_notes to empty string', async () => {
    const candidate: CandidateRecord = {
      id: 'cand_002',
      run_result_id: 'rr_002',
      candidate_name: 'test',
      status: 'DRAFT',
      review_notes: '',
      applicable_market: null,
      risks: [],
      recommendation: null,
      created_at: '2026-04-27T00:00:00Z',
      updated_at: '2026-04-27T00:00:00Z',
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => candidate });

    await createCandidateRecord('rr_002', 'test');
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect(body.review_notes).toBe('');
  });
});

describe('getCandidateRecords', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('calls /api/research/candidate-records without status when no param', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    await getCandidateRecords();
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/candidate-records');
  });

  it('appends status query param when provided', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    await getCandidateRecords('DRAFT');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/candidate-records?status=DRAFT');
  });

  it('omits status query param when ALL is passed', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

    await getCandidateRecords('ALL');
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('http://localhost:8000/api/research/candidate-records');
  });
});
