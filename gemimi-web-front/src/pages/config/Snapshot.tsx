import React, { useEffect, useState } from 'react';
import { getConfigSnapshot } from '@/src/services/api';
import { ConfigSnapshot } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, Lock, Lightbulb, ShieldCheck, Layers, GitCommit, SearchCode, Download } from 'lucide-react';

export default function Snapshot() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<ConfigSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getConfigSnapshot().then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }

  if (!data) return null;

  const handleExport = () => {
    const jsonString = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `config_snapshot_${data.identity.profile}_${data.identity.hash}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end border-b border-zinc-200 dark:border-zinc-800 mb-6 pb-4">
        <div>
           <div className="flex items-center gap-3">
             <h2 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">配置快照 (Config Snapshot)</h2>
           </div>
           <p className="text-xs text-zinc-500 mt-2 max-w-xl">
             系统当前有效配置的只读快照。这包含了运行时的硬编码值和覆盖参数提取出的静态映射。(不可编辑)
           </p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-300 rounded border border-zinc-200 dark:border-zinc-700 text-xs font-medium transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          导出 JSON
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><GitCommit className="w-4 h-4 mr-2"/> 运行时标识 (Identity)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">配置集 (Profile)</span><span className="font-mono">{data.identity?.profile}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">版本标识 (Version)</span><span className="font-mono">{data.identity?.version}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">生成签名 (Hash)</span><span className="font-mono text-zinc-400">{data.identity?.hash}</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><SearchCode className="w-4 h-4 mr-2"/> 后端路由抽象 (Backend)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
             {Object.keys(data.backend || {}).length > 0 ? (
               Object.entries(data.backend || {}).map(([k, v]) => (
                 <div key={k} className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2 last:border-0">
                   <span className="text-zinc-500">{k}</span>
                   <span className="font-mono text-zinc-700 dark:text-zinc-300">{String(v)}</span>
                 </div>
               ))
             ) : (
               <div className="text-zinc-500 text-xs">--</div>
             )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 text-sm flex items-center"><Layers className="w-4 h-4 mr-2"/> 市场配置 (Market)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              <pre>{Object.keys(data.market || {}).length > 0 ? JSON.stringify(data.market, null, 2) : '--'}</pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 text-sm flex items-center"><Layers className="w-4 h-4 mr-2"/> 信号策略 (Strategy)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              <pre>{Object.keys(data.strategy || {}).length > 0 ? JSON.stringify(data.strategy, null, 2) : '--'}</pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 text-sm flex items-center"><ShieldCheck className="w-4 h-4 mr-2"/> 风控参数 (Risk)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              <pre>{Object.keys(data.risk || {}).length > 0 ? JSON.stringify(data.risk, null, 2) : '--'}</pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-zinc-500 text-sm flex items-center"><ShieldCheck className="w-4 h-4 mr-2"/> 执行策略 (Execution)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-xs overflow-auto">
              <pre>{Object.keys(data.execution || {}).length > 0 ? JSON.stringify(data.execution, null, 2) : '--'}</pre>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-900/40 rounded p-4 flex gap-4">
         <div>
           <Lightbulb className="text-blue-500 w-5 h-5"/>
         </div>
         <div>
            <h4 className="font-semibold text-blue-800 dark:text-blue-400 text-sm mb-2">配置加载原则警告 (Source of Truth)</h4>
            <ul className="list-disc pl-4 space-y-1 text-xs text-blue-600 dark:text-blue-300">
               {(data.source_of_truth_hints || []).map((hint, i) => (
                 <li key={i}>{hint}</li>
               ))}
            </ul>
         </div>
      </div>
      
    </div>
  );
}
