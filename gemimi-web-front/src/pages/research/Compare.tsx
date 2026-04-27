import React, { useEffect, useState } from 'react';
import { getCompareData, getCandidates } from '@/src/services/api';
import { CompareResponse, CompareRow, Candidate } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, ArrowUpRight, ArrowDownRight, AlertCircle } from 'lucide-react';
import { fmtPct, fmtDec, fmtInt, DASH } from '@/src/lib/console-utils';

type PageState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'empty' }
  | { status: 'data'; data: CompareResponse; stale?: boolean };

function formatValue(val: number | null, metric: string): string {
  if (val === null) return DASH;
  if (metric === 'Trades') return fmtInt(val);
  if (metric === 'Max Drawdown' || metric === 'Total Return' || metric === 'Win Rate') {
    return fmtPct(val);
  }
  return fmtDec(val);
}

const selectCls =
  'bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1 text-sm font-mono text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500 max-w-[220px] truncate';

export default function Compare() {
  const { refreshCount } = useRefreshContext();

  // Candidate list for selectors
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatesError, setCandidatesError] = useState(false);

  // Selector state
  const [baselineRef, setBaselineRef] = useState<string>('');
  const [candidateARef, setCandidateARef] = useState<string>('');
  const [candidateBRef, setCandidateBRef] = useState<string>('');

  // Compare data
  const [pageState, setPageState] = useState<PageState>({ status: 'loading' });

  // ── Load candidate list once ──────────────────────────────────
  useEffect(() => {
    let active = true;
    getCandidates()
      .then(res => { if (active) setCandidates(res); })
      .catch(() => { if (active) setCandidatesError(true); });
    return () => { active = false; };
  }, [refreshCount]);

  // ── Initialize selector defaults from first compare load ──────
  const [initialized, setInitialized] = useState(false);

  // ── Fetch compare data ────────────────────────────────────────
  useEffect(() => {
    let active = true;
    setPageState(prev => {
      if (prev.status === 'data') return { ...prev, stale: false };
      return { status: 'loading' };
    });

    // Only pass selector params after initialization (first load uses defaults)
    const bl = initialized ? baselineRef : undefined;
    const ca = initialized ? candidateARef : undefined;
    const cb = initialized ? candidateBRef : undefined;

    getCompareData(bl, ca, cb)
      .then(res => {
        if (!active) return;
        if (!res.rows || res.rows.length === 0) {
          setPageState({ status: 'empty' });
        } else {
          setPageState({ status: 'data', data: res, stale: false });
          if (!initialized) {
            setBaselineRef(res.baseline_label);
            setCandidateARef(res.candidate_a_label);
            if (res.candidate_b_label) setCandidateBRef(res.candidate_b_label);
            setInitialized(true);
          }
        }
      })
      .catch(() => {
        if (!active) return;
        setPageState(prev => {
          if (prev.status === 'data') return { ...prev, stale: true };
          return { status: 'error', message: '对比数据加载失败' };
        });
      });
    return () => { active = false; };
  }, [refreshCount, initialized, baselineRef, candidateARef, candidateBRef]);

  // ── Dedup logic ───────────────────────────────────────────────
  const isDuplicateBaseline = (name: string) =>
    name === candidateARef || name === candidateBRef;
  const isDuplicateA = (name: string) =>
    name === baselineRef || name === candidateBRef;
  const isDuplicateB = (name: string) =>
    name === baselineRef || name === candidateARef;

  // ── Selector change handlers ──────────────────────────────────
  const handleBaselineChange = (val: string) => {
    setBaselineRef(val);
    // If A or B now duplicates baseline, clear them
    if (candidateARef === val) setCandidateARef('');
    if (candidateBRef === val) setCandidateBRef('');
  };

  const handleAChange = (val: string) => {
    setCandidateARef(val);
    if (candidateBRef === val) setCandidateBRef('');
  };

  const handleBChange = (val: string) => {
    setCandidateBRef(val);
  };

  // ── Render helpers ────────────────────────────────────────────
  if (pageState.status === 'loading') {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (pageState.status === 'error') {
    return (
      <div className="flex h-32 items-center justify-center text-rose-400 gap-2">
        <AlertCircle className="w-5 h-5" />
        <span>{pageState.message}</span>
      </div>
    );
  }

  if (pageState.status === 'empty') {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-bold tracking-tight">策略对比</h2>
          <p className="text-xs text-zinc-500 mt-1">候选策略核心指标与基准线对比。</p>
        </div>
        <Card>
          <CardContent className="py-10 text-center text-zinc-500">暂无可比较数据</CardContent>
        </Card>
      </div>
    );
  }

  const { data } = pageState;
  const hasCandidateB = data.candidate_b_label != null;
  const showStaleWarning = pageState.stale;

  const renderDirectionalDiff = (diff: number | null, metric: string) => {
    if (diff === null) return <span className="text-zinc-500 text-xs">{DASH}</span>;
    const lowerIsBetter = metric === 'Max Drawdown';
    const effectiveSign = lowerIsBetter ? -diff : diff;
    if (effectiveSign > 0) {
      return (
        <span className="text-emerald-400 flex items-center text-xs justify-end">
          <ArrowUpRight className="w-3 h-3 mr-0.5" /> +{Math.abs(diff).toFixed(3)}
        </span>
      );
    }
    if (effectiveSign < 0) {
      return (
        <span className="text-rose-400 flex items-center text-xs justify-end">
          <ArrowDownRight className="w-3 h-3 mr-0.5" /> -{Math.abs(diff).toFixed(3)}
        </span>
      );
    }
    return <span className="text-zinc-500 text-xs justify-end flex">0.000</span>;
  };

  const renderCell = (val: number | null, metric: string) => {
    if (val === null) return <span className="text-zinc-500">{DASH}</span>;
    return <span className="font-mono">{formatValue(val, metric)}</span>;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight">策略对比</h2>
        <p className="text-xs text-zinc-500 mt-1">候选策略核心指标与基准线对比。</p>
      </div>

      {/* ── Selector bar ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-4 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg px-4 py-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500 font-medium">Baseline</label>
          <select
            value={baselineRef}
            onChange={e => handleBaselineChange(e.target.value)}
            className={selectCls}
            disabled={candidates.length === 0}
          >
            {candidates.length === 0 && <option value="">--</option>}
            {candidates.map(c => (
              <option key={c.candidate_name} value={c.candidate_name} disabled={isDuplicateBaseline(c.candidate_name)}>
                {c.candidate_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500 font-medium">Candidate A</label>
          <select
            value={candidateARef}
            onChange={e => handleAChange(e.target.value)}
            className={selectCls}
            disabled={candidates.length === 0}
          >
            {candidates.length === 0 && <option value="">--</option>}
            {candidates.map(c => (
              <option key={c.candidate_name} value={c.candidate_name} disabled={isDuplicateA(c.candidate_name)}>
                {c.candidate_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500 font-medium">Candidate B <span className="text-zinc-400">(可选)</span></label>
          <select
            value={candidateBRef}
            onChange={e => handleBChange(e.target.value)}
            className={selectCls}
          >
            <option value="">-- 无 --</option>
            {candidates.map(c => (
              <option key={c.candidate_name} value={c.candidate_name} disabled={isDuplicateB(c.candidate_name)}>
                {c.candidate_name}
              </option>
            ))}
          </select>
        </div>

        {candidatesError && (
          <span className="text-xs text-amber-500 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> 候选列表加载失败
          </span>
        )}
      </div>

      {/* ── Current comparison summary ───────────────────────── */}
      <div className="flex items-center gap-3 text-xs text-zinc-500 font-mono">
        <span>Base: <span className="text-zinc-300">{data.baseline_label || '--'}</span></span>
        <span className="text-zinc-600">|</span>
        <span>A: <span className="text-blue-400">{data.candidate_a_label || '--'}</span></span>
        <span className="text-zinc-600">|</span>
        <span>B: <span className="text-amber-400">{data.candidate_b_label ?? '--'}</span></span>
      </div>

      {showStaleWarning && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>多维度评估基准对比</CardTitle>
          <div className="flex items-center space-x-2 text-xs">
            <div className="flex items-center"><div className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5"></div> 改善</div>
            <div className="flex items-center ml-2"><div className="w-2 h-2 rounded-full bg-rose-500 mr-1.5"></div> 退步</div>
            <span className="text-zinc-500 ml-2">(方向感知：回撤越低越好)</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                <TableHead className="font-semibold text-zinc-700 dark:text-zinc-300">评价指标</TableHead>
                <TableHead className="font-semibold text-zinc-700 dark:text-zinc-300 border-r border-zinc-200 dark:border-zinc-800 text-right pr-4">
                  {data.baseline_label || 'Baseline'}
                </TableHead>
                <TableHead className="font-semibold text-blue-400 text-right pr-4">
                  {data.candidate_a_label || 'Candidate A'}
                </TableHead>
                <TableHead className="text-right text-xs pr-4 text-zinc-500 font-normal border-r border-zinc-200 dark:border-zinc-800">vs Base</TableHead>
                {hasCandidateB && (
                  <>
                    <TableHead className="font-semibold text-amber-500 text-right pr-4">
                      {data.candidate_b_label}
                    </TableHead>
                    <TableHead className="text-right text-xs pr-4 text-zinc-500 font-normal">vs Base</TableHead>
                  </>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-medium text-zinc-700 dark:text-zinc-300">{row.metric}</TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400 border-r border-zinc-200 dark:border-zinc-800 text-right pr-4">
                    {renderCell(row.baseline, row.metric)}
                  </TableCell>
                  <TableCell className="font-mono text-right pr-4">{renderCell(row.candidate_a, row.metric)}</TableCell>
                  <TableCell className="text-right border-r border-zinc-200 dark:border-zinc-800 pr-4">{renderDirectionalDiff(row.diff_a, row.metric)}</TableCell>
                  {hasCandidateB && (
                    <>
                      <TableCell className="font-mono text-right pr-4">{renderCell(row.candidate_b, row.metric)}</TableCell>
                      <TableCell className="text-right pr-4">{renderDirectionalDiff(row.diff_b, row.metric)}</TableCell>
                    </>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <p className="text-xs text-zinc-500">
        数据来源：候选策略 best_trial 指标。diff = candidate − baseline；绿色 = 改善方向，红色 = 退步方向（回撤指标越低越好）。
      </p>
    </div>
  );
}
