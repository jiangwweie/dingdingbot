import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { createCandidateRecord, getResearchRun, getResearchRunReport } from '@/src/services/api';
import { CandidateRecord, ResearchRunResult, ResearchPositionResult, ResearchRunReport, ResearchCloseEvent } from '@/src/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { AlertCircle, ArrowLeft, CopyPlus, Loader2, Rocket, ChevronDown, ChevronRight, LayoutList } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent, MarkLineComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { fmtDateTime, DASH } from '@/src/lib/console-utils';
import { cn } from '@/src/lib/utils';
import {
  computeAnnualizedReturn,
  computeMaxConsecutiveLosses,
  computeProfitFactor,
  describeRunParameters,
  directionLabel,
  directionVariant,
  closeEventLabel,
  closeEventVariant,
  fmtMoney,
  fmtMetric,
  fmtRatio,
  fmtUtcMs,
  getResolvedOrderStrategy,
  getResolvedRuntime,
  getRunMetric,
  pnlRatioClass,
  signedMoneyClass,
  toNumber,
} from '@/src/lib/research-format';

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkAreaComponent, MarkLineComponent, CanvasRenderer]);

function KPITile({ label, value, className = '' }: { label: string; value: string; className?: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400 mb-1">{label}</p>
        <p className={`font-mono text-lg font-bold tracking-tight tabular-nums leading-none ${className}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function ResolvedParamRow({ label, value }: { label: string; value: unknown }) {
  const display = value === null || value === undefined ? DASH : String(value);
  return (
    <div className="flex items-baseline gap-2 text-xs py-1.5 border-b border-zinc-100 dark:border-zinc-800/50 last:border-b-0" key={label}>
      <span className="text-zinc-500 shrink-0 min-w-[140px] tracking-tight">{label}</span>
      <span className="font-mono text-zinc-900 dark:text-zinc-100 break-all leading-relaxed">{display}</span>
    </div>
  );
}

function EquityDrawdownChart({ run }: { run: ResearchRunResult }) {
  const equityCurve = run.debug_equity_curve;
  const summaryMetrics = run.summary_metrics || {};
  const maxDDStart = toNumber(summaryMetrics.max_drawdown_start_ms);
  const maxDDEnd = toNumber(summaryMetrics.max_drawdown_end_ms);

  const option = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return null;

    const times = equityCurve.map(p => p.timestamp);
    const values = equityCurve.map(p => toNumber(p.equity)).filter((v): v is number => v !== null);
    if (values.length === 0) return null;
    const peak = values.reduce((max, v) => Math.max(max, v), values[0]);
    const drawdowns = values.map((v, i) => {
      const runningPeak = values.slice(0, i + 1).reduce((m, val) => Math.max(m, val), values[0]);
      return ((v - runningPeak) / runningPeak) * 100;
    });

    const markAreaData: Array<Array<{ xAxis: number }>> = [];
    if (maxDDStart && maxDDEnd) {
      markAreaData.push([{ xAxis: maxDDStart }, { xAxis: maxDDEnd }]);
    }

    return {
      backgroundColor: 'transparent',
      tooltip: { 
        trigger: 'axis' as const, 
        backgroundColor: 'rgba(24,24,27,0.9)', 
        borderColor: '#3f3f46', 
        textStyle: { color: '#e4e4e7', fontSize: 12 },
        axisPointer: { type: 'cross', label: { backgroundColor: '#3f3f46' } },
        padding: [8, 12]
      },
      legend: { data: ['权益 (Equity)', '回撤 (Drawdown)'], top: 0, right: 20, icon: 'roundRect', textStyle: { color: '#a1a1aa', fontSize: 11 } },
      grid: [
        { left: 60, right: 20, top: 40, height: '52%' },
        { left: 60, right: 20, top: '70%', height: '20%' },
      ],
      xAxis: [
        { type: 'time' as const, gridIndex: 0, axisLabel: { color: '#71717a', fontSize: 10, hideOverlap: true }, axisLine: { lineStyle: { color: '#3f3f46' } }, axisTick: { show: false }, splitLine: { show: false } },
        { type: 'time' as const, gridIndex: 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#3f3f46' } }, axisTick: { show: false }, splitLine: { show: false } },
      ],
      yAxis: [
        { 
          type: 'value' as const, 
          gridIndex: 0, 
          axisLabel: { color: '#71717a', fontSize: 10, formatter: (val: number) => val >= 1000 ? `${(val/1000).toFixed(0)}k` : val }, 
          splitLine: { lineStyle: { color: '#27272a', type: 'dashed' } },
          scale: true
        },
        { 
          type: 'value' as const, 
          gridIndex: 1, 
          axisLabel: { color: '#71717a', fontSize: 10, formatter: '{value}%' }, 
          splitLine: { lineStyle: { color: '#27272a', type: 'dashed' } },
          max: 0
        },
      ],
      dataZoom: [
        { type: 'inside' as const, xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider' as const, xAxisIndex: [0, 1], bottom: 0, height: 20, borderColor: 'transparent', fillerColor: 'rgba(59,130,246,0.1)', handleStyle: { color: '#60a5fa' }, textStyle: { color: '#71717a' } },
      ],
      series: [
        {
          name: '权益 (Equity)',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: times.map((t, i) => [t, values[i]]),
          lineStyle: { color: '#3b82f6', width: 2, shadowColor: 'rgba(59,130,246,0.4)', shadowBlur: 8, shadowOffsetY: 2 },
          itemStyle: { color: '#3b82f6' },
          showSymbol: false,
          smooth: 0.1,
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(59,130,246,0.2)' },
              { offset: 1, color: 'rgba(59,130,246,0.01)' },
            ])
          },
          markLine: {
            silent: true,
            symbol: 'none',
            label: { show: false },
            lineStyle: { type: 'dashed', color: '#71717a', width: 1, opacity: 0.5 },
            data: [{ yAxis: values[0] }]
          },
          markArea: markAreaData.length > 0 ? {
            silent: true,
            itemStyle: { color: 'rgba(244,63,94,0.08)', borderColor: 'rgba(244,63,94,0.2)', borderWidth: 1 },
            data: markAreaData,
            label: { show: true, formatter: 'Max Drawdown', color: '#f43f5e', fontSize: 10, position: 'insideTop' as const },
          } : undefined,
        },
        {
          name: '回撤 (Drawdown)',
          type: 'line',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: times.map((t, i) => [t, -drawdowns[i]]), 
          // Note: we negate drawdown for visualization so it points downward from 0
          lineStyle: { color: '#f43f5e', width: 1.5, shadowColor: 'rgba(244,63,94,0.3)', shadowBlur: 4, shadowOffsetY: 1 },
          itemStyle: { color: '#f43f5e' },
          showSymbol: false,
          smooth: 0.1,
          areaStyle: { 
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(244,63,94,0.01)' },
              { offset: 1, color: 'rgba(244,63,94,0.2)' },
            ]) 
          },
        },
      ],
    };
  }, [equityCurve, maxDDStart, maxDDEnd]);

  if (!option) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500 text-sm border border-zinc-200 dark:border-zinc-800 rounded">
        暂无权益曲线数据
      </div>
    );
  }

  return <ReactEChartsCore echarts={echarts} option={option} style={{ height: 420 }} notMerge lazyUpdate />;
}

export default function RunDetail() {
  const { run_result_id } = useParams<{ run_result_id: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<ResearchRunResult | null>(null);
  const [report, setReport] = useState<ResearchRunReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showParams, setShowParams] = useState(true);
  const [candidate, setCandidate] = useState<CandidateRecord | null>(null);
  const [creatingCandidate, setCreatingCandidate] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!run_result_id) return;
    let active = true;
    setLoading(true);
    setError(false);
    Promise.all([getResearchRun(run_result_id), getResearchRunReport(run_result_id).catch(() => null)])
      .then(([runRes, reportRes]) => {
        if (!active) return;
        setRun(runRes);
        setReport(reportRes);
        setLoading(false);
      })
      .catch(() => {
        if (active) { setError(true); setLoading(false); }
      });
    return () => { active = false; };
  }, [run_result_id]);

  const positions = useMemo<ResearchPositionResult[]>(() => {
    const p = report?.positions ?? (run as unknown as Record<string, unknown> | null)?.positions;
    return Array.isArray(p) ? p : [];
  }, [report, run]);

  const closeEventsByPosition = useMemo(() => {
    const events = report?.close_events || [];
    const map = new Map<string, ResearchCloseEvent[]>();
    for (const e of events) {
      if (e.position_id) {
        if (!map.has(e.position_id)) map.set(e.position_id, []);
        map.get(e.position_id)!.push(e);
      }
    }
    for (const evts of map.values()) {
      evts.sort((a, b) => (toNumber(a.close_time) || 0) - (toNumber(b.close_time) || 0));
    }
    return map;
  }, [report?.close_events]);

  const chartRun = useMemo<ResearchRunResult | null>(() => {
    if (!run) return null;
    return {
      ...run,
      debug_equity_curve: report?.debug_equity_curve ?? run.debug_equity_curve,
      positions: report?.positions ?? run.positions,
    };
  }, [report, run]);

  const metricValue = (key: string, reportKey = key): unknown => (
    getRunMetric(run, key) ?? (report ? (report as Record<string, unknown>)[reportKey] : undefined)
  );

  const profitFactor = useMemo(() => computeProfitFactor(positions), [positions]);
  const maxConsecutiveLosses = useMemo(() => computeMaxConsecutiveLosses(positions), [positions]);

  const totalReturn = toNumber(metricValue('total_return'));
  const startMs = toNumber((run?.spec_snapshot as Record<string, unknown>)?.start_time_ms);
  const endMs = toNumber((run?.spec_snapshot as Record<string, unknown>)?.end_time_ms);
  const annualizedReturn = computeAnnualizedReturn(totalReturn, startMs, endMs);

  const resolvedRuntime = useMemo(() => getResolvedRuntime(run), [run]);
  const resolvedOrder = useMemo(() => getResolvedOrderStrategy(run), [run]);

  const promoteCandidate = async () => {
    if (!run || creatingCandidate) return;
    setCreatingCandidate(true);
    setCandidateError(null);
    try {
      const runSpec = run.spec_snapshot as Record<string, unknown>;
      const nameBase = String(runSpec?.name || run.source_profile || run.id)
        .replace(/[^a-zA-Z0-9_\-\u4e00-\u9fa5]/g, '_')
        .slice(0, 48);
      const created = await createCandidateRecord(
        run.id,
        `candidate_${nameBase || run.id}`,
        '从回测详情页手动晋升为候选策略',
      );
      setCandidate(created);
    } catch (err) {
      setCandidateError(err instanceof Error ? err.message : '晋升候选策略失败');
    } finally {
      setCreatingCandidate(false);
    }
  };

  const toggleRow = (idx: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-zinc-500" /></div>;
  if (error || !run) return <div className="flex h-64 items-center justify-center text-rose-500 gap-2 font-bold"><AlertCircle className="w-5 h-5" /><span>加载回测结果失败</span></div>;

  const spec = run.spec_snapshot || {};
  const specObj = spec as Record<string, unknown>;
  const costs = specObj.costs && typeof specObj.costs === 'object' ? specObj.costs as Record<string, unknown> : {};

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      {/* Top actions */}
      <div className="flex flex-wrap items-center gap-3 bg-zinc-50 dark:bg-zinc-900/40 p-2.5 rounded-sm border border-zinc-200 dark:border-zinc-800">
        <button type="button" onClick={() => navigate('/research/jobs')} className="inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 text-[11px] font-bold uppercase tracking-wider transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" /> BACK
        </button>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 tracking-widest uppercase border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800">已完成</Badge>
        
        <div className="flex items-center gap-2 ml-2 pl-2 border-l border-zinc-200 dark:border-zinc-800">
           <span className="text-sm font-bold tracking-tight">{String(specObj.name || '') || run.source_profile || '回测结果'}</span>
           <span className="text-[10px] text-zinc-500 font-mono hidden sm:inline-block">({String(specObj.symbol || '--')} · {String(specObj.timeframe || '--')})</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Link
            to={`/research/new?clone_run=${encodeURIComponent(run.id)}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm border border-zinc-300 dark:border-zinc-700 bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900 text-[11px] text-zinc-700 dark:text-zinc-300 font-bold uppercase tracking-wider transition-colors shadow-sm"
          >
            <CopyPlus className="w-4 h-4" /> 克隆配置
          </Link>
          <button
            type="button"
            onClick={promoteCandidate}
            disabled={creatingCandidate || candidate !== null}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-500 disabled:cursor-not-allowed text-white text-[11px] font-bold tracking-wider uppercase transition-colors shadow-sm"
            title="将此策略晋升为候选策略"
          >
            <Rocket className="w-3.5 h-3.5" /> {candidate ? '已加入候选' : creatingCandidate ? '加入中...' : '加入候选策略'}
          </button>
        </div>
      </div>

      {candidate && (
        <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-400 px-3 py-1.5 rounded-sm text-xs flex items-center gap-2">
          <Rocket className="w-4 h-4" />
          <span>已晋升为候选策略：<span className="font-mono font-bold tracking-tight">{candidate.candidate_name}</span></span>
        </div>
      )}
      {candidateError && (
        <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-400 px-3 py-1.5 rounded-sm text-xs">
          {candidateError}
        </div>
      )}

      {/* Meta string below if notes exist */}
      {specObj.notes && (
         <p className="text-xs text-zinc-500 px-2 py-1 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800/80 rounded-sm italic">
           {String(specObj.notes)}
         </p>
      )}

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-5 xl:grid-cols-11 gap-2">
        <KPITile label="最终权益" value={fmtMoney(metricValue('final_equity', 'final_balance'))} className="xl:col-span-2" />
        <KPITile label="总收益" value={fmtMoney(metricValue('total_pnl'))} className={signedMoneyClass(metricValue('total_pnl'))} />
        <KPITile label="收益率" value={fmtRatio(metricValue('total_return'))} className={signedMoneyClass(metricValue('total_return'))} />
        <KPITile label="年化(APR)" value={annualizedReturn !== null ? fmtRatio(annualizedReturn) : '--'} className={signedMoneyClass(annualizedReturn)} />
        <KPITile label="最大回撤" value={fmtRatio(metricValue('max_drawdown'))} className="text-rose-600 dark:text-rose-400" />
        <KPITile label="胜率" value={fmtRatio(metricValue('win_rate'))} />
        <KPITile label="交易数" value={fmtMetric(metricValue('total_trades'), 0)} />
        <KPITile label="夏普" value={fmtMetric(metricValue('sharpe_ratio'))} />
        <KPITile label="索提诺" value={fmtMetric(metricValue('sortino_ratio'))} />
        <KPITile label="盈亏比" value={profitFactor === null ? '--' : profitFactor === '∞' ? '∞' : fmtMetric(profitFactor)} />
      </div>

      {/* Equity + Drawdown chart */}
      <Card>
        <CardHeader><CardTitle>权益曲线与回撤</CardTitle></CardHeader>
        <CardContent>
          {chartRun ? <EquityDrawdownChart run={chartRun} /> : null}
        </CardContent>
      </Card>

      {/* Trade table */}
      <Card>
        <CardHeader className="bg-zinc-100/50 dark:bg-zinc-900/80 items-center justify-between border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
            <LayoutList className="w-4 h-4 text-zinc-500" />
            <CardTitle className="text-sm font-bold tracking-tight">逐笔交易 (Trade Log)</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] font-mono font-medium px-2 py-0.5 border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-500">
              {positions.length} TRADES
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {positions.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-zinc-500 text-[11px] font-mono">NO TRADES FOUND</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50/50 dark:bg-zinc-900/30">
                  <TableHead className="w-8 pl-4"></TableHead>
                  <TableHead>方向</TableHead>
                  <TableHead>入场时间</TableHead>
                  <TableHead className="text-right">入场价</TableHead>
                  <TableHead>出场时间</TableHead>
                  <TableHead className="text-right">出场价</TableHead>
                  <TableHead className="text-right">净盈亏</TableHead>
                  <TableHead>平仓原因</TableHead>
                  <TableHead className="text-right pr-4">手续费</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((pos, idx) => {
                  const events = pos.position_id ? closeEventsByPosition.get(pos.position_id) || [] : [];
                  const isExpanded = expandedRows.has(idx);
                  const hasSubRows = events.length > 0;
                  
                  return (
                    <React.Fragment key={idx}>
                      <TableRow 
                        className={cn("group transition-colors", hasSubRows ? "cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/30" : "")}
                        onClick={() => hasSubRows && toggleRow(idx)}
                      >
                        <TableCell className="pl-4">
                           {hasSubRows && (
                             <button type="button" className="p-1 rounded-sm text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors">
                                <ChevronRight className={cn("w-3.5 h-3.5 transition-transform duration-200", isExpanded && "rotate-90")} />
                             </button>
                           )}
                        </TableCell>
                        <TableCell><Badge variant={directionVariant(pos.direction)} className="text-[9px] px-1.5 py-0.5 font-semibold tracking-wider">{directionLabel(pos.direction)}</Badge></TableCell>
                        <TableCell className="text-[10px] font-mono text-zinc-500 tracking-tighter leading-snug">{fmtUtcMs(pos.entry_time_ms ?? pos.entry_time)}</TableCell>
                        <TableCell className="font-mono text-right text-[11px] tabular-nums font-bold tracking-tight">{fmtMoney(pos.entry_price)}</TableCell>
                        <TableCell className="text-[10px] font-mono text-zinc-500 tracking-tighter leading-snug">{fmtUtcMs(pos.exit_time_ms ?? pos.exit_time)}</TableCell>
                        <TableCell className="font-mono text-right text-[11px] tabular-nums font-bold tracking-tight">{fmtMoney(pos.exit_price)}</TableCell>
                        <TableCell className={`font-mono text-right text-[11px] font-bold tabular-nums tracking-tight ${pnlRatioClass(pos.realized_pnl)}`}>{fmtMoney(pos.realized_pnl)}</TableCell>
                        <TableCell className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider group-hover:text-zinc-800 dark:group-hover:text-zinc-200 transition-colors">{pos.exit_reason || '--'}</TableCell>
                        <TableCell className="font-mono text-right pr-4 text-[11px] text-zinc-400 dark:text-zinc-500 tabular-nums">{fmtMoney(pos.commission)}</TableCell>
                      </TableRow>
                      {isExpanded && events.map((ev, eIdx) => (
                        <TableRow key={`sub-${idx}-${eIdx}`} className="bg-zinc-50/80 dark:bg-zinc-900/40 hover:bg-zinc-100 dark:hover:bg-zinc-800/60 transition-colors">
                          <TableCell className="text-xs pl-6 relative">
                            {/* Visual tree connection line */}
                            <div className="absolute top-0 bottom-0 left-[26px] w-px bg-zinc-200 dark:bg-zinc-800"></div>
                            {eIdx === events.length - 1 && <div className="absolute bottom-0 left-[26px] w-[12px] h-[50%] bg-zinc-50/80 dark:bg-zinc-900/40"></div>}
                            <div className="absolute top-1/2 left-[26px] w-3 h-px bg-zinc-200 dark:bg-zinc-800"></div>
                          </TableCell>
                          <TableCell></TableCell>
                          <TableCell></TableCell>
                          <TableCell></TableCell>
                          <TableCell className="text-[10px] font-mono text-zinc-500">{fmtUtcMs(ev.close_time)}</TableCell>
                          <TableCell className="font-mono text-right text-[11px] text-zinc-600 dark:text-zinc-400 font-medium">
                            {fmtMoney(ev.close_price)}
                            {ev.close_qty != null && <span className="ml-1 text-[9px] text-zinc-400">x{ev.close_qty}</span>}
                          </TableCell>
                          <TableCell className={`font-mono text-right text-[11px] font-bold tabular-nums tracking-tight ${pnlRatioClass(ev.close_pnl)}`}>{fmtMoney(ev.close_pnl)}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant={closeEventVariant(ev)} className="scale-90 origin-left text-[9px] px-1 py-0 shadow-sm border-zinc-200 dark:border-zinc-800">
                              {closeEventLabel(ev)}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-right pr-4 text-[11px] text-zinc-500">{fmtMoney(ev.close_fee)}</TableCell>
                        </TableRow>
                      ))}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Resolved parameters */}
      <Card>
        <CardHeader className="py-2.5">
          <button type="button" className="flex items-center gap-2 w-full text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors" onClick={() => setShowParams(!showParams)}>
            {showParams ? <ChevronDown className="w-4 h-4 text-zinc-400" /> : <ChevronRight className="w-4 h-4 text-zinc-400" />}
            <CardTitle className="text-sm">实际生效参数</CardTitle>
          </button>
        </CardHeader>
        {showParams && (
          <CardContent className="space-y-4 pt-1">
            <div className="bg-zinc-50 dark:bg-zinc-900/40 rounded p-3 text-[11px] grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500 mb-2 border-b border-zinc-200 dark:border-zinc-800 pb-1">运行时配置</p>
                <div className="space-y-0.5">
                  {Object.keys(resolvedRuntime).length === 0 ? (
                    <p className="text-[10px] text-zinc-500 font-mono">-- EMPTY --</p>
                  ) : Object.entries(resolvedRuntime).map(([k, v]) => (
                    <ResolvedParamRow label={k} value={v} key={k} />
                  ))}
                </div>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500 mb-2 border-b border-zinc-200 dark:border-zinc-800 pb-1">订单策略</p>
                <div className="space-y-0.5">
                  {Object.keys(resolvedOrder).length === 0 ? (
                    <p className="text-[10px] text-zinc-500 font-mono">-- EMPTY --</p>
                  ) : Object.entries(resolvedOrder).map(([k, v]) => (
                    <ResolvedParamRow label={k} value={v} key={k} />
                  ))}
                </div>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500 mb-2 border-b border-zinc-200 dark:border-zinc-800 pb-1">交易摩擦 (Costs)</p>
                <div className="space-y-0.5">
                  <ResolvedParamRow label="初始资金" value={costs.initial_balance} />
                  <ResolvedParamRow label="开仓滑点" value={costs.slippage_rate} />
                  <ResolvedParamRow label="止盈滑点" value={costs.tp_slippage_rate} />
                  <ResolvedParamRow label="手续费率" value={costs.fee_rate} />
                </div>
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Debug info (collapsed) */}
      <details className="rounded border border-zinc-200 dark:border-zinc-800">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">
          调试信息（原始数据与文件路径）
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 space-y-3 text-xs font-mono text-zinc-500">
          <div>
            <span className="text-zinc-400">Run ID:</span> {run.id}
          </div>
          <div>
            <span className="text-zinc-400">Source Profile:</span> {run.source_profile}
          </div>
          <div>
            <span className="text-zinc-400">Artifact Path:</span> {run.artifact_path || '--'}
          </div>
          <div>
            <span className="text-zinc-400">Git Commit:</span> {run.git_commit || '--'}
          </div>
          <div>
            <span className="text-zinc-400">Spec Snapshot:</span>
            <pre className="mt-1 p-2 bg-zinc-100 dark:bg-zinc-900 rounded overflow-x-auto text-[11px] max-h-64">{JSON.stringify(run.spec_snapshot, null, 2)}</pre>
          </div>
          {report && (
            <div>
              <span className="text-zinc-400">Report JSON:</span>
              <pre className="mt-1 p-2 bg-zinc-100 dark:bg-zinc-900 rounded overflow-x-auto text-[11px] max-h-64">{JSON.stringify(report, null, 2)}</pre>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
