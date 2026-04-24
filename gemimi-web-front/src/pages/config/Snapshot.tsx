import React, { useEffect, useState } from 'react';
import { getConfigSnapshot } from '@/src/services/mockApi';
import { ConfigSnapshot } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, Lock, Lightbulb, ShieldCheck, Layers, GitCommit, SearchCode } from 'lucide-react';

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

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end border-b border-zinc-200 dark:border-zinc-800 mb-6 pb-4">
        <div>
           <div className="flex items-center gap-3">
             <h2 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">配置快照 (Config Snapshot)</h2>
             {data.identity.is_frozen && (
               <Badge variant="outline" className="text-blue-500 border-blue-500/30 bg-blue-50 dark:bg-blue-500/10"><Lock className="w-3 h-3 mr-1" /> RUNTIME FROZEN</Badge>
             )}
           </div>
           <p className="text-xs text-zinc-500 mt-2 max-w-xl">
             系统当前有效配置的只读快照。这包含了运行时的硬编码值和覆盖参数提取出的静态映射。(不可编辑)
           </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><GitCommit className="w-4 h-4 mr-2"/> 运行时标识 (Identity)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">配置集 (Profile)</span><span className="font-mono">{data.identity.profile}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">版本标识 (Version)</span><span className="font-mono">{data.identity.version}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">生成签名 (Hash)</span><span className="font-mono text-zinc-400">{data.identity.hash}</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><SearchCode className="w-4 h-4 mr-2"/> 市场配置 (Market)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">目标资产 (Symbols)</span><span className="font-semibold text-blue-500 dark:text-blue-400">{data.market.symbols.join(', ')}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">使用周期 (Timeframes)</span><span className="font-mono">{data.market.timeframes.join(', ')}</span></div>
             <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">启用多时间重合 (MTF)</span><span className="font-mono">{data.market.mtf_enabled ? 'Yes' : 'No'}</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><Layers className="w-4 h-4 mr-2"/> 信号生成 (Strategy)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
             <div>
                <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2"><span className="text-zinc-500">主策略名 (Name)</span><span className="font-mono font-medium text-emerald-600 dark:text-emerald-400">{data.strategy.name}</span></div>
                <div className="flex justify-between border-b border-zinc-100 dark:border-zinc-800 pb-2 mt-2"><span className="text-zinc-500">方向偏移 (Bias)</span><span className="font-mono">{data.strategy.direction_bias}</span></div>
             </div>
             <div>
                <span className="text-zinc-500 text-xs mb-2 block">关键超参数 (Hyperparams)</span>
                <div className="bg-zinc-50 dark:bg-zinc-950 p-2 rounded border border-zinc-200 dark:border-zinc-800 font-mono text-zinc-600 dark:text-zinc-400 text-xs">
                   {Object.entries(data.strategy.key_parameters).map(([k, v]) => (
                     <div key={k} className="flex justify-between">
                       <span>{k}:</span>
                       <span>{String(v)}</span>
                     </div>
                   ))}
                </div>
             </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-zinc-500 flex items-center"><ShieldCheck className="w-4 h-4 mr-2"/> 执行风控与后端 (Risk & Backend)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
             <div className="grid grid-cols-2 gap-4">
                <div>
                   <span className="block text-zinc-500 text-[10px] uppercase mb-1">单笔容错限制</span>
                   <span className="font-mono text-zinc-900 dark:text-zinc-100">{(data.risk.max_loss_percent * 100).toFixed(1)}%</span>
                </div>
                <div>
                   <span className="block text-zinc-500 text-[10px] uppercase mb-1">日内最大回撤</span>
                   <span className="font-mono text-zinc-900 dark:text-zinc-100">{(data.risk.daily_max_loss_percent * 100).toFixed(1)}%</span>
                </div>
                <div>
                   <span className="block text-zinc-500 text-[10px] uppercase mb-1">最高有效杠杆</span>
                   <span className="font-mono text-zinc-900 dark:text-zinc-100">{data.risk.leverage}x</span>
                </div>
                <div>
                   <span className="block text-zinc-500 text-[10px] uppercase mb-1">策略单边执行方案</span>
                   <span className="font-mono text-zinc-900 dark:text-zinc-100">{data.execution.same_bar_policy}</span>
                </div>
             </div>
             <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3">
                 <span className="text-zinc-500 text-xs mb-2 block">路由与抽象 (Backends)</span>
                 <div className="space-y-1">
                   <div className="flex justify-between text-[11px]"><span className="text-zinc-400">意图管理库 (Intent):</span> <span className="font-mono">{data.backend.intent}</span></div>
                   <div className="flex justify-between text-[11px]"><span className="text-zinc-400">执行通道 (Order):</span> <span className="font-mono">{data.backend.order}</span></div>
                   <div className="flex justify-between text-[11px]"><span className="text-zinc-400">持仓记账管理 (Position):</span> <span className="font-mono">{data.backend.position}</span></div>
                 </div>
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
               {data.source_of_truth_hints.map((hint, i) => (
                 <li key={i}>{hint}</li>
               ))}
            </ul>
         </div>
      </div>
      
    </div>
  );
}
