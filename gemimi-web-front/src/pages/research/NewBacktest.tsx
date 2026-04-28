import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createResearchBacktestJob, getResearchRun } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { AlertCircle, Loader2, PlayCircle } from 'lucide-react';
import { fmtUtcMs } from '@/src/lib/research-format';

const inputCls = 'w-full bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500';
const labelCls = 'text-xs font-bold uppercase tracking-widest text-zinc-500';

function toDatetimeLocal(ms: number) {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

function fromDatetimeLocal(value: string) {
  const ms = new Date(`${value}${value.length === 16 ? ':00' : ''}Z`).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

export default function NewBacktest() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const now = useMemo(() => Date.now(), []);
  const [name, setName] = useState('eth-baseline-window');
  const [profileName, setProfileName] = useState('backtest_eth_baseline');
  const [symbol, setSymbol] = useState('ETH/USDT:USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [start, setStart] = useState(toDatetimeLocal(now - 30 * 24 * 60 * 60 * 1000));
  const [end, setEnd] = useState(toDatetimeLocal(now));
  const [limit, setLimit] = useState(9000);
  const [initialBalance, setInitialBalance] = useState('10000');
  const [slippageRate, setSlippageRate] = useState('0.0001');
  const [tpSlippageRate, setTpSlippageRate] = useState('0');
  const [feeRate, setFeeRate] = useState('0.000405');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [cloneSource, setCloneSource] = useState<string | null>(null);
  const [cloneSourceName, setCloneSourceName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const runId = searchParams.get('clone_run');
    if (!runId) return;
    let active = true;
    getResearchRun(runId)
      .then(run => {
        if (!active) return;
        const spec = run.spec_snapshot || {};
        const costs = spec.costs && typeof spec.costs === 'object' ? spec.costs as Record<string, unknown> : {};
        setCloneSource(run.id);
        setCloneSourceName(String(spec.name || run.source_profile || 'research-run'));
        setName(`${String(spec.name || run.source_profile || 'research-run')}-复用`);
        setProfileName(String(spec.profile_name || run.source_profile || 'backtest_eth_baseline'));
        setSymbol(String(spec.symbol || 'ETH/USDT:USDT'));
        setTimeframe(String(spec.timeframe || '1h'));
        if (typeof spec.start_time_ms === 'number') setStart(toDatetimeLocal(spec.start_time_ms));
        if (typeof spec.end_time_ms === 'number') setEnd(toDatetimeLocal(spec.end_time_ms));
        if (typeof spec.limit === 'number') setLimit(spec.limit);
        setInitialBalance(String(costs.initial_balance ?? '10000'));
        setSlippageRate(String(costs.slippage_rate ?? '0.0001'));
        setTpSlippageRate(String(costs.tp_slippage_rate ?? '0'));
        setFeeRate(String(costs.fee_rate ?? '0.000405'));
        setNotes(`复用自 ${String(spec.name || run.source_profile || 'research-run')}`);
      })
      .catch(err => setError(err instanceof Error ? err.message : '加载复用配置失败'));
    return () => { active = false; };
  }, [searchParams]);

  const applyWindowPreset = (preset: '1m' | '6m' | '2025') => {
    if (preset === '2025') {
      setStart('2025-01-01T00:00');
      setEnd('2026-01-01T00:00');
      return;
    }
    const days = preset === '1m' ? 30 : 183;
    const endMs = Date.now();
    setStart(toDatetimeLocal(endMs - days * 24 * 60 * 60 * 1000));
    setEnd(toDatetimeLocal(endMs));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await createResearchBacktestJob({
        name,
        profile_name: profileName,
        symbol,
        timeframe,
        start_time_ms: fromDatetimeLocal(start),
        end_time_ms: fromDatetimeLocal(end),
        limit,
        mode: 'v3_pms',
        costs: {
          initial_balance: initialBalance,
          slippage_rate: slippageRate,
          tp_slippage_rate: tpSlippageRate,
          fee_rate: feeRate,
        },
        notes: notes || null,
      });
      navigate(`/research/jobs?created=${encodeURIComponent(res.job_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建研究任务失败');
    } finally {
      setSubmitting(false);
    }
  };

  const startMs = fromDatetimeLocal(start);
  const endMs = fromDatetimeLocal(end);
  const canSubmit = !submitting && name.trim().length > 0 && profileName.trim().length > 0 && startMs > 0 && endMs > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">新建回测任务</h2>
          <p className="text-xs text-zinc-500 mt-1">只创建研究任务；不会修改模拟盘/实盘配置，也不会触发真实交易。</p>
        </div>
        <Badge variant="outline">研究专用</Badge>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-500 bg-rose-500/10 border border-rose-500/20 rounded px-3 py-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <form onSubmit={submit}>
        <Card>
          <CardHeader>
            <CardTitle>回测设置</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Clone source notice */}
            {cloneSource && (
              <div className="rounded border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20 px-4 py-3 text-sm text-blue-900 dark:text-blue-100">
                当前表单已从回测 <span className="font-semibold">{cloneSourceName || cloneSource}</span> 复用配置，你可以修改参数后重新提交。
              </div>
            )}

            {/* Default baseline notice */}
            {!cloneSource && (
              <div className="rounded border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20 px-4 py-3 text-sm text-blue-900 dark:text-blue-100">
                本次默认按 ETH 旧基线口径运行：只做多、EMA50、止盈 50% at 1R + 50% at 3.5R、手续费 0.0405%。提交后可在回测详情里查看"实际生效参数"。
              </div>
            )}

            {/* Section 1: 基础信息 */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold border-b border-zinc-200 dark:border-zinc-800 pb-2">基础信息</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="space-y-1.5">
                  <span className={labelCls}>回测名称</span>
                  <input className={inputCls} value={name} onChange={e => setName(e.target.value)} required maxLength={120} placeholder="如 eth-baseline-window" />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>交易对</span>
                  <input className={inputCls} value={symbol} onChange={e => setSymbol(e.target.value)} required placeholder="如 ETH/USDT:USDT" />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>K线周期</span>
                  <select className={inputCls} value={timeframe} onChange={e => setTimeframe(e.target.value)}>
                    {['15m', '1h', '4h', '1d'].map(tf => <option key={tf} value={tf}>{tf}</option>)}
                  </select>
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>研究备注</span>
                  <input className={inputCls} value={notes} onChange={e => setNotes(e.target.value)} maxLength={200} placeholder="本次回测的研究假设或目的" />
                </label>
              </div>
            </div>

            {/* Section 2: 时间窗口 */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 pb-2">
                <h3 className="text-sm font-semibold mr-auto">时间窗口</h3>
                <button type="button" className="text-xs px-2.5 py-1 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors" onClick={() => applyWindowPreset('1m')}>最近 1 个月</button>
                <button type="button" className="text-xs px-2.5 py-1 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors" onClick={() => applyWindowPreset('6m')}>最近半年</button>
                <button type="button" className="text-xs px-2.5 py-1 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors" onClick={() => applyWindowPreset('2025')}>2025 全年</button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="space-y-1.5">
                  <span className={labelCls}>开始时间 UTC</span>
                  <input className={inputCls} type="datetime-local" value={start} onChange={e => setStart(e.target.value)} required />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>结束时间 UTC</span>
                  <input className={inputCls} type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} required />
                </label>
              </div>
            </div>

            {/* Section 3: 策略与资金 */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold border-b border-zinc-200 dark:border-zinc-800 pb-2">策略与资金</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="space-y-1.5">
                  <span className={labelCls}>基线配置</span>
                  <input className={inputCls} value={profileName} onChange={e => setProfileName(e.target.value)} required placeholder="如 backtest_eth_baseline" />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>初始资金</span>
                  <input className={inputCls} type="number" value={initialBalance} onChange={e => setInitialBalance(e.target.value)} min={1} placeholder="10000" />
                </label>
              </div>
            </div>

            {/* Section 4: 高级设置 (collapsed) */}
            <details className="rounded border border-zinc-200 dark:border-zinc-800">
              <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">高级设置（交易摩擦与加载参数）</summary>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-zinc-200 dark:border-zinc-800 p-4">
                <label className="space-y-1.5">
                  <span className={labelCls}>最多加载K线数</span>
                  <input className={inputCls} type="number" min={10} max={30000} value={limit} onChange={e => setLimit(Number(e.target.value))} />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>开仓滑点</span>
                  <input className={inputCls} value={slippageRate} onChange={e => setSlippageRate(e.target.value)} />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>止盈滑点</span>
                  <input className={inputCls} value={tpSlippageRate} onChange={e => setTpSlippageRate(e.target.value)} />
                </label>
                <label className="space-y-1.5">
                  <span className={labelCls}>手续费率</span>
                  <input className={inputCls} value={feeRate} onChange={e => setFeeRate(e.target.value)} />
                </label>
              </div>
            </details>

            {/* Run summary */}
            <div className="rounded border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/30 px-4 py-3 text-sm">
              <p className="text-xs font-semibold text-zinc-500 mb-1">本次回测摘要</p>
              <p className="text-zinc-700 dark:text-zinc-300">
                将使用 <span className="font-mono font-medium">{symbol}</span>、<span className="font-mono">{timeframe}</span>、
                <span className="font-mono">{fmtUtcMs(startMs)}</span> 至 <span className="font-mono">{fmtUtcMs(endMs)}</span>、
                基线 <span className="font-mono">{profileName}</span>、初始资金 <span className="font-mono">{initialBalance}</span> 运行回测。
              </p>
            </div>

            {/* Submit */}
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                {submitting ? '正在提交...' : '创建回测任务'}
              </button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}