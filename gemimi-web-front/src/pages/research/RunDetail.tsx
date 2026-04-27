import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { createCandidateRecord, getResearchRun } from '@/src/services/api';
import { CandidateRecord, ResearchRunResult } from '@/src/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { AlertCircle, ArrowLeft, Loader2, Star } from 'lucide-react';
import { fmtDash, fmtDateTime, fmtDec, fmtInt, fmtPct } from '@/src/lib/console-utils';

function metricNumber(run: ResearchRunResult | null, key: string): number | null {
  const value = run?.summary_metrics?.[key];
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export default function RunDetail() {
  const { run_result_id } = useParams<{ run_result_id: string }>();
  const [run, setRun] = useState<ResearchRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [candidateName, setCandidateName] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [candidate, setCandidate] = useState<CandidateRecord | null>(null);
  const [creating, setCreating] = useState(false);
  const [candidateError, setCandidateError] = useState<string | null>(null);

  useEffect(() => {
    if (!run_result_id) return;
    let active = true;
    setLoading(true);
    setError(false);
    getResearchRun(run_result_id).then(res => {
      if (!active) return;
      setRun(res);
      setCandidateName(`candidate-${res.id}`);
      setLoading(false);
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [run_result_id]);

  const spec = useMemo(() => run?.spec_snapshot || {}, [run]);

  const createCandidate = async () => {
    if (!run || !candidateName.trim()) return;
    setCreating(true);
    setCandidateError(null);
    try {
      const res = await createCandidateRecord(run.id, candidateName.trim(), reviewNotes);
      setCandidate(res);
    } catch (err) {
      setCandidateError(err instanceof Error ? err.message : '标记 candidate 失败');
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error || !run) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>Run result 加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start gap-4">
        <div>
          <Link to="/research/jobs" className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 mb-3">
            <ArrowLeft className="w-3.5 h-3.5" />
            返回研究任务
          </Link>
          <h2 className="text-xl font-bold tracking-tight font-mono">{run.id}</h2>
          <p className="text-xs text-zinc-500 mt-1">Job: <span className="font-mono">{run.job_id}</span></p>
        </div>
        <Badge variant="outline">candidate-only</Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader><CardTitle>Metrics</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-4">
            <div><p className="text-xs text-zinc-500">Return</p><p className="font-mono">{fmtPct(metricNumber(run, 'total_return'))}</p></div>
            <div><p className="text-xs text-zinc-500">Sharpe</p><p className="font-mono">{fmtDec(metricNumber(run, 'sharpe_ratio'))}</p></div>
            <div><p className="text-xs text-zinc-500">Drawdown</p><p className="font-mono">{fmtPct(metricNumber(run, 'max_drawdown'))}</p></div>
            <div><p className="text-xs text-zinc-500">Win Rate</p><p className="font-mono">{fmtPct(metricNumber(run, 'win_rate'))}</p></div>
            <div><p className="text-xs text-zinc-500">Trades</p><p className="font-mono">{fmtInt(metricNumber(run, 'total_trades'))}</p></div>
            <div><p className="text-xs text-zinc-500">Generated</p><p className="font-mono text-xs">{fmtDateTime(run.generated_at)}</p></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Spec Snapshot</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="flex justify-between gap-4"><span className="text-zinc-500">Profile</span><span className="font-mono">{fmtDash(run.source_profile)}</span></div>
            <div className="flex justify-between gap-4"><span className="text-zinc-500">Symbol</span><span className="font-mono">{fmtDash(spec.symbol)}</span></div>
            <div className="flex justify-between gap-4"><span className="text-zinc-500">Timeframe</span><span className="font-mono">{fmtDash(spec.timeframe)}</span></div>
            <div className="flex justify-between gap-4"><span className="text-zinc-500">Mode</span><span className="font-mono">{fmtDash(spec.mode)}</span></div>
            <div className="flex justify-between gap-4"><span className="text-zinc-500">Limit</span><span className="font-mono">{fmtDash(spec.limit)}</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Candidate</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {candidate ? (
              <div className="space-y-2">
                <Badge variant="success">created</Badge>
                <p className="font-mono text-sm text-blue-400">{candidate.id}</p>
                <p className="text-xs text-zinc-500">{candidate.candidate_name}</p>
              </div>
            ) : (
              <>
                <input className="w-full bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 text-sm" value={candidateName} onChange={e => setCandidateName(e.target.value)} />
                <textarea className="w-full bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 text-sm" rows={3} value={reviewNotes} onChange={e => setReviewNotes(e.target.value)} placeholder="review notes" />
                {candidateError && <p className="text-xs text-rose-400">{candidateError}</p>}
                <button
                  onClick={createCandidate}
                  disabled={creating || !candidateName.trim()}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium"
                >
                  {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Star className="w-4 h-4" />}
                  标记 Candidate
                </button>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Artifacts</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {Object.entries(run.artifact_index || {}).map(([key, value]) => (
            <div key={key} className="border border-zinc-200 dark:border-zinc-800 rounded p-3">
              <p className="text-xs text-zinc-500 uppercase">{key}</p>
              <p className="font-mono text-xs mt-1 break-all text-zinc-700 dark:text-zinc-300">{value}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
