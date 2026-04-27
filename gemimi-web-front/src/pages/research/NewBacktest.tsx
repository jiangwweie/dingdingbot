import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createResearchBacktestJob } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { AlertCircle, Loader2, PlayCircle } from 'lucide-react';

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
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">新建回测任务</h2>
          <p className="text-xs text-zinc-500 mt-1">Research-only job；不会修改 runtime profile，也不会触发实盘执行。</p>
        </div>
        <Badge variant="outline">candidate-only</Badge>
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
            <CardTitle>Backtest Spec</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="space-y-1.5">
                <span className={labelCls}>Name</span>
                <input className={inputCls} value={name} onChange={e => setName(e.target.value)} required maxLength={120} />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Profile</span>
                <input className={inputCls} value={profileName} onChange={e => setProfileName(e.target.value)} required />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Symbol</span>
                <input className={inputCls} value={symbol} onChange={e => setSymbol(e.target.value)} required />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Timeframe</span>
                <select className={inputCls} value={timeframe} onChange={e => setTimeframe(e.target.value)}>
                  {['15m', '1h', '4h', '1d'].map(tf => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Start</span>
                <input className={inputCls} type="datetime-local" value={start} onChange={e => setStart(e.target.value)} required />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>End</span>
                <input className={inputCls} type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} required />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Limit</span>
                <input className={inputCls} type="number" min={10} max={30000} value={limit} onChange={e => setLimit(Number(e.target.value))} />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Initial Balance</span>
                <input className={inputCls} value={initialBalance} onChange={e => setInitialBalance(e.target.value)} />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Slippage</span>
                <input className={inputCls} value={slippageRate} onChange={e => setSlippageRate(e.target.value)} />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>TP Slippage</span>
                <input className={inputCls} value={tpSlippageRate} onChange={e => setTpSlippageRate(e.target.value)} />
              </label>
              <label className="space-y-1.5">
                <span className={labelCls}>Fee Rate</span>
                <input className={inputCls} value={feeRate} onChange={e => setFeeRate(e.target.value)} />
              </label>
            </div>
            <label className="block space-y-1.5">
              <span className={labelCls}>Notes</span>
              <textarea className={inputCls} rows={4} value={notes} onChange={e => setNotes(e.target.value)} maxLength={5000} />
            </label>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                创建任务
              </button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
