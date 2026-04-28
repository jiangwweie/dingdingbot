import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getResearchJobs, getResearchRuns } from '@/src/services/api';
import { ResearchJob, ResearchJobStatus, ResearchRunResult } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { AlertCircle, CheckSquare, CopyPlus, Eye, Loader2, Plus, Square } from 'lucide-react';
import { fmtDash, fmtDateTime } from '@/src/lib/console-utils';
import { comparePrimitive, compareTimestamp, EmptyFilterRow, FilterSelect, useTableSort } from '@/src/lib/table-utils';
import { ColumnVisibility, ColumnDef } from '@/src/components/ui/ColumnVisibility';
import {
  describeRunParameters,
  fmtMetric,
  fmtMoney,
  fmtRatio,
  fmtUtcMs,
  getRunMetric,
  researchJobStatusLabel,
  researchJobStatusVariant,
  signedMoneyClass,
  toNumber,
} from '@/src/lib/research-format';

const STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'PENDING', label: '等待中' },
  { value: 'RUNNING', label: '运行中' },
  { value: 'SUCCEEDED', label: '已完成' },
  { value: 'FAILED', label: '失败' },
  { value: 'CANCELED', label: '已取消' },
];

const RETURN_OPTIONS = [
  { value: 'ALL', label: '全部收益' },
  { value: 'POSITIVE', label: '正收益' },
  { value: 'GT10', label: '>10%' },
  { value: 'NEGATIVE', label: '亏损' },
];

function runFor(job: ResearchJob, runById: Map<string, ResearchRunResult>) {
  return job.run_result_id ? runById.get(job.run_result_id) : undefined;
}

function SummaryTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400 mb-1">{label}</p>
        <p className="font-mono text-lg font-bold tracking-tight text-zinc-900 dark:text-zinc-100 tabular-nums leading-none">{value}</p>
        {hint && <p className="text-[10px] text-zinc-400 mt-1.5">{hint}</p>}
      </CardContent>
    </Card>
  );
}

const JOB_COLUMNS: ColumnDef[] = [
  { key: 'select', label: '选择', defaultVisible: true },
  { key: 'name', label: '回测名称', defaultVisible: true },
  { key: 'symbol', label: '市场', defaultVisible: true },
  { key: 'timeframe', label: '时间窗口', defaultVisible: true },
  { key: 'params', label: '参数摘要', defaultVisible: true },
  { key: 'created_at', label: '创建时间', defaultVisible: false },
  { key: 'status', label: '状态', defaultVisible: true },
  { key: 'pnl', label: '总收益', defaultVisible: true },
  { key: 'return', label: '收益率', defaultVisible: true },
  { key: 'drawdown', label: '最大回撤', defaultVisible: true },
  { key: 'win_rate', label: '胜率', defaultVisible: true },
  { key: 'trades', label: '交易数', defaultVisible: false },
  { key: 'actions', label: '操作', defaultVisible: true },
];

export default function ResearchJobs() {
  const { refreshCount } = useRefreshContext();
  const [params] = useSearchParams();
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [runs, setRuns] = useState<ResearchRunResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ResearchJobStatus | 'ALL'>('ALL');
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  const [profileFilter, setProfileFilter] = useState('ALL');
  const [returnFilter, setReturnFilter] = useState('ALL');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(new Set());
  const sort = useTableSort<ResearchJob>('created_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    Promise.all([getResearchJobs(statusFilter), getResearchRuns()])
      .then(([jobRes, runRes]) => {
        if (!active) return;
        setJobs(jobRes.jobs || []);
        setRuns(runRes.runs || []);
        setLoading(false);
      })
      .catch(() => {
        if (active) { setError(true); setLoading(false); }
      });
    return () => { active = false; };
  }, [refreshCount, statusFilter]);

  const runById = useMemo(() => new Map(runs.map(r => [r.id, r])), [runs]);

  // Derive filter options from data
  const symbolOptions = useMemo(() => {
    const symbols = [...new Set(jobs.map(j => j.spec?.symbol).filter(Boolean) as string[])].sort();
    return [{ value: 'ALL', label: '全部交易对' }, ...symbols.map(s => ({ value: s, label: s }))];
  }, [jobs]);

  const profileOptions = useMemo(() => {
    const profiles = [...new Set(jobs.map(j => j.spec?.profile_name).filter(Boolean) as string[])].sort();
    return [{ value: 'ALL', label: '全部基线' }, ...profiles.map(p => ({ value: p, label: p }))];
  }, [jobs]);

  const filtered = useMemo(() => {
    let rows = jobs;

    // Symbol filter
    if (symbolFilter !== 'ALL') {
      rows = rows.filter(j => j.spec?.symbol === symbolFilter);
    }

    // Profile filter
    if (profileFilter !== 'ALL') {
      rows = rows.filter(j => j.spec?.profile_name === profileFilter);
    }

    // Return filter
    if (returnFilter !== 'ALL') {
      rows = rows.filter(j => {
        const run = runFor(j, runById);
        const ret = toNumber(getRunMetric(run, 'total_return'));
        if (ret === null) return false;
        if (returnFilter === 'POSITIVE') return ret > 0;
        if (returnFilter === 'GT10') return ret > 0.10;
        if (returnFilter === 'NEGATIVE') return ret < 0;
        return true;
      });
    }

    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'name': return comparePrimitive(a.name, b.name, sort.sortOrder);
        case 'status': return comparePrimitive(a.status, b.status, sort.sortOrder);
        case 'created_at': return compareTimestamp(a.created_at, b.created_at, sort.sortOrder);
        case 'symbol': return comparePrimitive(a.spec?.symbol, b.spec?.symbol, sort.sortOrder);
        default: return 0;
      }
    });
  }, [jobs, symbolFilter, profileFilter, returnFilter, runById, sort.sortField, sort.sortOrder]);

  const succeededRuns = runs.filter(r => jobs.some(j => j.run_result_id === r.id));
  const bestPnl = succeededRuns.reduce<number | null>((best, run) => {
    const pnl = toNumber(getRunMetric(run, 'total_pnl'));
    if (pnl === null) return best;
    return best === null ? pnl : Math.max(best, pnl);
  }, null);
  const lowestDrawdown = succeededRuns.reduce<number | null>((best, run) => {
    const dd = toNumber(getRunMetric(run, 'max_drawdown'));
    if (dd === null) return best;
    return best === null ? dd : Math.min(best, dd);
  }, null);

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 4) next.add(id);
      return next;
    });
  };

  const selectedJobs = jobs.filter(j => selectedIds.has(j.id));
  const canCompare = selectedIds.size >= 2 && selectedIds.size <= 4;

  if (loading && jobs.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>;
  if (error && jobs.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-4 h-4" /><span className="text-sm font-medium">回测历史加载失败</span></div>;

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between bg-zinc-50 dark:bg-zinc-900/40 p-2.5 rounded-sm border border-zinc-200 dark:border-zinc-800">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">回测历史 (Backtests)</h2>
        </div>
        <Link to="/research/new" className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-bold uppercase tracking-wider transition-colors shadow-sm">
          <Plus className="w-3.5 h-3.5" /> 新建回测
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
        <SummaryTile label="全部回测" value={String(jobs.length)} />
        <SummaryTile label="已完成" value={String(jobs.filter(j => j.status === 'SUCCEEDED').length)} />
        <SummaryTile label="失败" value={String(jobs.filter(j => j.status === 'FAILED').length)} />
        <SummaryTile label="最佳收益" value={fmtMoney(bestPnl)} />
        <SummaryTile label="最低回撤" value={fmtRatio(lowestDrawdown)} />
      </div>

      {params.get('created') && (
        <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-400 px-3 py-1.5 rounded-sm text-xs flex items-center gap-2">
          <CheckSquare className="w-4 h-4" />
          <span>已创建回测任务：<span className="font-mono font-bold">{params.get('created')}</span></span>
        </div>
      )}

      {error && jobs.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-3 py-1.5 rounded-sm text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span>部分数据刷新失败，显示缓存内容</span>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">筛选 (FILTERS)</span>
            <div className="flex items-center gap-2 ml-2">
              <FilterSelect value={statusFilter} onChange={v => setStatusFilter(v as ResearchJobStatus | 'ALL')} options={STATUS_OPTIONS} />
              <FilterSelect value={symbolFilter} onChange={setSymbolFilter} options={symbolOptions} />
              <FilterSelect value={profileFilter} onChange={setProfileFilter} options={profileOptions} />
              <FilterSelect value={returnFilter} onChange={setReturnFilter} options={RETURN_OPTIONS} />
            </div>
            <div className="ml-auto flex items-center gap-3">
              <span className="text-[10px] font-mono tracking-widest text-zinc-400 uppercase">{filtered.length} MATCHES</span>
              <ColumnVisibility columns={JOB_COLUMNS} storageKey="research_jobs_cols_v1" onChange={setVisibleColumns} />
            </div>
          </div>

          {/* Table */}
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-100/50 dark:bg-zinc-900/80">
                {visibleColumns.has('select') && <TableHead className="w-8 px-2" />}
                {visibleColumns.has('name') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('name')}>回测名称 (NAME){sort.sortIndicator('name')}</TableHead>}
                {visibleColumns.has('symbol') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('symbol')}>市场 (MARKET){sort.sortIndicator('symbol')}</TableHead>}
                {visibleColumns.has('timeframe') && <TableHead>时间窗口 (WINDOW)</TableHead>}
                {visibleColumns.has('params') && <TableHead>参数摘要 (PARAMS)</TableHead>}
                {visibleColumns.has('created_at') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('created_at')}>创建时间 (CREATED){sort.sortIndicator('created_at')}</TableHead>}
                {visibleColumns.has('status') && <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('status')}>状态 (STATUS){sort.sortIndicator('status')}</TableHead>}
                {visibleColumns.has('pnl') && <TableHead className="text-right">总收益 (PNL)</TableHead>}
                {visibleColumns.has('return') && <TableHead className="text-right">收益率 (%)</TableHead>}
                {visibleColumns.has('drawdown') && <TableHead className="text-right">最大回撤</TableHead>}
                {visibleColumns.has('win_rate') && <TableHead className="text-right">胜率</TableHead>}
                {visibleColumns.has('trades') && <TableHead className="text-right">交易</TableHead>}
                {visibleColumns.has('actions') && <TableHead className="text-right pr-4">操作</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <EmptyFilterRow colSpan={visibleColumns.size} />
              ) : filtered.map(job => {
                const run = runFor(job, runById);
                const isSelected = selectedIds.has(job.id);
                const pnlValue = getRunMetric(run, 'total_pnl');
                const returnValue = getRunMetric(run, 'total_return');
                return (
                  <TableRow key={job.id}>
                    {visibleColumns.has('select') && (
                    <TableCell className="px-2">
                      <button
                        type="button"
                        onClick={() => toggleSelect(job.id)}
                        className="text-zinc-400 hover:text-blue-500 transition-colors flex items-center justify-center p-1"
                        title={isSelected ? '取消选择' : '选择对比'}
                      >
                        {isSelected ? <CheckSquare className="w-4 h-4 text-blue-500" /> : <Square className="w-4 h-4 opacity-50" />}
                      </button>
                    </TableCell>
                    )}
                    {visibleColumns.has('name') && (
                    <TableCell>
                      <div className="font-bold text-zinc-800 dark:text-zinc-200 tracking-tight">{fmtDash(job.name)}</div>
                      <div className="text-[10px] text-zinc-500 truncate max-w-[160px] tracking-tight mt-0.5" title={job.spec?.notes || undefined}>{fmtDash(job.spec?.notes) || ''}</div>
                    </TableCell>
                    )}
                    {visibleColumns.has('symbol') && (
                    <TableCell>
                      <div className="font-mono font-bold">{fmtDash(job.spec?.symbol)}</div>
                      <div className="font-mono text-[9px] text-zinc-500 mt-0.5 tracking-widest uppercase">{fmtDash(job.spec?.timeframe)}</div>
                    </TableCell>
                    )}
                    {visibleColumns.has('timeframe') && <TableCell className="text-[10px] text-zinc-500 font-mono tracking-tighter leading-snug">{fmtUtcMs(job.spec?.start_time_ms)}<br />{fmtUtcMs(job.spec?.end_time_ms)}</TableCell>}
                    {visibleColumns.has('params') && <TableCell className="text-[10px] text-zinc-600 dark:text-zinc-400 max-w-[180px] break-words">{run ? describeRunParameters(run) : fmtDash(job.spec?.profile_name)}</TableCell>}
                    {visibleColumns.has('created_at') && <TableCell className="text-[10px] text-zinc-500 font-mono">{fmtDateTime(job.created_at)}</TableCell>}
                    {visibleColumns.has('status') && <TableCell><Badge variant={researchJobStatusVariant(job.status)} className="text-[9px] px-1.5 py-0.5">{researchJobStatusLabel(job.status)}</Badge></TableCell>}
                    {visibleColumns.has('pnl') && <TableCell className={`font-mono text-right font-bold tracking-tight ${signedMoneyClass(pnlValue)}`}>{fmtMoney(pnlValue)}</TableCell>}
                    {visibleColumns.has('return') && <TableCell className={`font-mono text-right font-bold tracking-tight ${signedMoneyClass(returnValue)}`}>{fmtRatio(returnValue)}</TableCell>}
                    {visibleColumns.has('drawdown') && <TableCell className="font-mono text-right text-rose-600 dark:text-rose-400 tabular-nums">{fmtRatio(getRunMetric(run, 'max_drawdown'))}</TableCell>}
                    {visibleColumns.has('win_rate') && <TableCell className="font-mono text-right tabular-nums">{fmtRatio(getRunMetric(run, 'win_rate'))}</TableCell>}
                    {visibleColumns.has('trades') && <TableCell className="font-mono text-right tabular-nums">{fmtMetric(getRunMetric(run, 'total_trades'), 0)}</TableCell>}
                    {visibleColumns.has('actions') && (
                    <TableCell className="text-right pr-4">
                      <div className="flex items-center justify-end gap-2 text-[11px] font-bold uppercase tracking-wider">
                        {job.run_result_id ? (
                          <Link className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-400 transition-colors" to={`/research/runs/${job.run_result_id}`}>
                            <Eye className="w-3.5 h-3.5" /> DETAIL
                          </Link>
                        ) : (
                          <span className="text-zinc-500 opacity-60">WAITING</span>
                        )}
                        {job.run_result_id && (
                          <Link className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors" to={`/research/new?clone_run=${encodeURIComponent(job.run_result_id)}`} title="基于此配置新建回测">
                            <CopyPlus className="w-3.5 h-3.5" />
                          </Link>
                        )}
                      </div>
                    </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Compare action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 px-4 py-2.5 rounded-sm shadow-xl border border-zinc-700 dark:border-zinc-300 font-sans">
          <span className="text-xs font-bold uppercase tracking-wider">已选 {selectedIds.size} 项</span>
          <div className="h-4 w-px bg-zinc-700 dark:bg-zinc-300"></div>
          {canCompare ? (
            <button
              type="button"
              disabled
              title="当前对比页仍只支持候选策略，回测结果直接对比需要下一阶段接入"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-zinc-700 dark:bg-zinc-300 text-white/50 dark:text-zinc-900/50 text-[11px] font-bold uppercase tracking-wider cursor-not-allowed"
            >
              对比待接入 (WIP)
            </button>
          ) : (
            <span className="text-[10px] text-zinc-400 dark:text-zinc-500 uppercase tracking-widest font-mono">NEEDS 2-4 ITEMS</span>
          )}
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500 hover:text-white dark:hover:text-zinc-900 transition-colors ml-2"
          >
            CLEAR
          </button>
        </div>
      )}
    </div>
  );
}
