import React, { useEffect, useState } from 'react';
import { getConfigSnapshot } from '@/src/services/api';
import { ConfigSnapshot } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, AlertCircle, Download } from 'lucide-react';
import { fmtDash } from '@/src/lib/console-utils';

export default function Snapshot() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<ConfigSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getConfigSnapshot().then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && !data) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>配置快照加载失败</span></div>;
  if (!data) return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">配置快照</h2>
      <Card><CardContent className="py-10 text-center text-zinc-500">暂无配置快照</CardContent></Card>
    </div>
  );

  const handleExport = () => {
    const jsonString = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const profile = data.identity?.profile || 'unknown-profile';
    const hash = data.identity?.hash || 'unknown-hash';
    a.download = `config_snapshot_${profile}_${hash}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const renderJsonBlock = (obj: Record<string, unknown> | undefined) => {
    if (!obj || Object.keys(obj).length === 0) return <span className="text-zinc-500">{fmtDash(null)}</span>;
    return <pre className="whitespace-pre-wrap">{JSON.stringify(obj, null, 2)}</pre>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end border-b border-zinc-200 dark:border-zinc-800 mb-6 pb-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">配置快照</h2>
          <p className="text-xs text-zinc-500 mt-1">启动期冻结的 runtime 配置只读快照。真源为 runtime profile + RuntimeConfigResolver。</p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-300 rounded border border-zinc-200 dark:border-zinc-700 text-xs font-medium transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          导出 JSON
        </button>
      </div>

      {error && data && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>运行时标识</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">Profile</span><span className="font-mono">{fmtDash(data.identity?.profile)}</span></div>
            <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">版本</span><span className="font-mono">{fmtDash(data.identity?.version)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">Hash</span><span className="font-mono text-zinc-400">{fmtDash(data.identity?.hash)}</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>后端路由</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.keys(data.backend || {}).length > 0 ? (
              Object.entries(data.backend || {}).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2 last:border-0">
                  <span className="text-zinc-500">{k}</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{String(v)}</span>
                </div>
              ))
            ) : (
              <div className="text-zinc-500 text-xs">{fmtDash(null)}</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>市场配置</CardTitle></CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              {renderJsonBlock(data.market)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>策略配置</CardTitle></CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              {renderJsonBlock(data.strategy)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>风控参数</CardTitle></CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              {renderJsonBlock(data.risk)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>执行策略</CardTitle></CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              {renderJsonBlock(data.execution)}
            </div>
          </CardContent>
        </Card>
      </div>

      {(data.source_of_truth_hints && data.source_of_truth_hints.length > 0) && (
        <div className="bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-900/40 rounded p-4 flex gap-4">
          <div className="text-blue-500 text-sm font-bold">配置真源提示</div>
          <ul className="list-disc pl-4 space-y-1 text-xs text-blue-600 dark:text-blue-300">
            {data.source_of_truth_hints.map((hint, i) => (
              <li key={i}>{hint}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}