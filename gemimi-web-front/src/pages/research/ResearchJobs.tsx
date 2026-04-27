import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getResearchJobs, getResearchRuns } from '@/src/services/api';
import { ResearchJob, ResearchJobStatus, ResearchRunResult } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { AlertCircle, Loader2, Plus } from 'lucide-react';
import { fmtDash, fmtDateTime, fmtDec, fmtInt, fmtPct } from '@/src/lib/console-utils';
import { comparePrimitive, compareTimestamp, EmptyFilterRow, FilterSelect, useTableSort } from '@/src/lib/table-utils';

const statusVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s) {
    case 'SUCCEEDED': return 'success';
    case 'RUNNING': return 'info';
    case 'FAILED': return 'danger';
    case 'PENDING': return 'warning';
    case 'CANCELED': return 'default';
    default: return 'default';
  }
};

const STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'PENDING', label: 'PENDING' },
  { value: 'RUNNING', label: 'RUNNING' },
  { value: 'SUCCEEDED', label: 'SUCCEEDED' },
  { value: 'FAILED', label: 'FAILED' },
  { value: 'CANCELED', label: 'CANCELED' },
];

function numMetric(run: ResearchRunResult | undefined, key: string): number | null {
  const value = run?.summary_metrics?.[key];
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export default function ResearchJobs() {
  const { refreshCount } = useRefreshContext();
  const [params] = useSearchParams();
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [runs, setRuns] = useState<ResearchRunResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ResearchJobStatus | 'ALL'>('ALL');
  const sort = useTableSort<ResearchJob>('created_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    Promise.all([
      getResearchJobs(statusFilter),
      getResearchRuns(),
    ]).then(([jobRes, runRes]) => {
      if (!active) return;
      setJobs(jobRes.jobs || []);
      setRuns(runRes.runs || []);
      setLoading(false);
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount, statusFilter]);

  const runById = useMemo(() => new Map(runs.map(r => [r.id, r])), [runs]);

  const filtered = useMemo(() => {
    return [...jobs].sort((a, b) => {
      switch (sort.sortField) {
        case 'name': return comparePrimitive(a.name, b.name, sort.sortOrder);
        case 'status': return comparePrimitive(a.status, b.status, sort.sortOrder);
        case 'created_at': return compareTimestamp(a.created_at, b.created_at, sort.sortOrder);
        case 'symbol': return comparePrimitive(a.spec?.symbol, b.spec?.symbol, sort.sortOrder);
        default: return 0;
      }
    });
  }, [jobs, sort.sortField, sort.sortOrder]);

  if (loading && jobs.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && jobs.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>研究任务加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">研究任务</h2>
          <p className="text-xs text-zinc-500 mt-1">Research Control Plane jobs；candidate-only，不影响 runtime。</p>
        </div>
        <Link to="/research/new" className="inline-flex items-center gap-2 px-3 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium">
          <Plus className="w-4 h-4" />
          新建回测
        </Link>
      </div>

      {params.get('created') && (
        <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-400 px-4 py-2 rounded text-sm">
          已创建任务：<span className="font-mono">{params.get('created')}</span>
        </div>
      )}

      {error && jobs.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800">
            <span className="text-xs text-zinc-500">状态</span>
            <FilterSelect value={statusFilter} onChange={v => setStatusFilter(v as ResearchJobStatus | 'ALL')} options={STATUS_OPTIONS} />
            <span className="ml-auto text-xs text-zinc-500">{jobs.length} 条</span>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                <TableHead>ID</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('name')}>名称{sort.sortIndicator('name')}</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>交易对{sort.sortIndicator('symbol')}</TableHead>
                <TableHead>周期</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('created_at')}>创建时间{sort.sortIndicator('created_at')}</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('status')}>状态{sort.sortIndicator('status')}</TableHead>
                <TableHead className="text-right">Return</TableHead>
                <TableHead className="text-right">Sharpe</TableHead>
                <TableHead className="text-right">Trades</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <EmptyFilterRow colSpan={10} />
              ) : filtered.map(job => {
                const run = job.run_result_id ? runById.get(job.run_result_id) : undefined;
                return (
                  <TableRow key={job.id}>
                    <TableCell className="font-mono text-xs">{fmtDash(job.id)}</TableCell>
                    <TableCell>{fmtDash(job.name)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(job.spec?.symbol)}</TableCell>
                    <TableCell className="font-mono">{fmtDash(job.spec?.timeframe)}</TableCell>
                    <TableCell className="text-xs text-zinc-500">{fmtDateTime(job.created_at)}</TableCell>
                    <TableCell><Badge variant={statusVariant(job.status)}>{job.status}</Badge></TableCell>
                    <TableCell className="font-mono text-right">{fmtPct(numMetric(run, 'total_return'))}</TableCell>
                    <TableCell className="font-mono text-right">{fmtDec(numMetric(run, 'sharpe_ratio'))}</TableCell>
                    <TableCell className="font-mono text-right">{fmtInt(numMetric(run, 'total_trades'))}</TableCell>
                    <TableCell>
                      {job.run_result_id ? (
                        <Link className="text-blue-400 hover:text-blue-300 font-mono text-xs" to={`/research/runs/${job.run_result_id}`}>
                          {job.run_result_id}
                        </Link>
                      ) : (
                        <span className="text-zinc-500">--</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
