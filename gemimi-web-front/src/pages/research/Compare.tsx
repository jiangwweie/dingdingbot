import React, { useEffect, useState } from 'react';
import { getCompareData } from '@/src/services/mockApi';
import { CompareRecord } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, ArrowUpRight, ArrowDownRight } from 'lucide-react';

export default function Compare() {
  const { refreshCount } = useRefreshContext();
  const [compareData, setCompareData] = useState<CompareRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getCompareData().then(res => {
      if (active) {
        setCompareData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && compareData.length === 0) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }

  const renderDiff = (diff?: number) => {
    if (diff === undefined) return <span className="text-zinc-500">-</span>;
    if (diff > 0) {
      return <span className="text-emerald-400 flex items-center text-xs justify-end"><ArrowUpRight className="w-3 h-3 mr-0.5" /> +{(diff * 100).toFixed(1)}%</span>;
    }
    if (diff < 0) {
      return <span className="text-rose-400 flex items-center text-xs justify-end"><ArrowDownRight className="w-3 h-3 mr-0.5" /> {(diff * 100).toFixed(1)}%</span>;
    }
    return <span className="text-zinc-500 text-xs justify-end flex">0.0%</span>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-xl font-bold tracking-tight">策略对比 (Compare)</h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-xl">
            对比多个候选策略与基准线（Base Line）的核心评价指标，评估实验差异。
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>多维度评估基准对比</CardTitle>
          <div className="flex items-center space-x-2 text-xs">
            <div className="flex items-center"><div className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5"></div> Better</div>
            <div className="flex items-center ml-2"><div className="w-2 h-2 rounded-full bg-rose-500 mr-1.5"></div> Worse</div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                <TableHead className="font-semibold text-zinc-700 dark:text-zinc-300">评价指标 (Metric)</TableHead>
                <TableHead className="font-semibold text-zinc-700 dark:text-zinc-300 border-r border-zinc-200 dark:border-zinc-800">基准 (Baseline)</TableHead>
                <TableHead className="font-semibold text-blue-400 text-right pr-4">Cand-Alpha-01</TableHead>
                <TableHead className="text-right text-xs pr-4 text-zinc-500 font-normal border-r border-zinc-200 dark:border-zinc-800">vs Base</TableHead>
                <TableHead className="font-semibold text-amber-500 text-right pr-4">Cand-Beta-14</TableHead>
                <TableHead className="text-right text-xs pr-4 text-zinc-500 font-normal">vs Base</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {compareData.map((row, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-medium text-zinc-700 dark:text-zinc-300">{row.metric}</TableCell>
                  <TableCell className="font-mono text-zinc-600 dark:text-zinc-400 border-r border-zinc-200 dark:border-zinc-800">{row.baseline}</TableCell>
                  <TableCell className="font-mono text-right pr-4">{row.candidateA}</TableCell>
                  <TableCell className="text-right border-r border-zinc-200 dark:border-zinc-800 pr-4">{renderDiff(row.diffA)}</TableCell>
                  <TableCell className="font-mono text-right pr-4">{row.candidateB || '-'}</TableCell>
                  <TableCell className="text-right pr-4">{renderDiff(row.diffB)}</TableCell>
                </TableRow>
              ))}
              {compareData.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center py-6 text-zinc-500">暂无对比数据</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-blue-950/20 border-blue-900/40">
          <CardHeader><CardTitle className="text-blue-400">总结: Cand-Alpha-01</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <p className="text-zinc-700 dark:text-zinc-300">收益和稳定性相较于基准有显著提升，夏普比率增长明显。<span className="text-emerald-400 ml-2">推荐进入下一阶段测试。</span></p>
          </CardContent>
        </Card>
        
        <Card className="bg-amber-950/20 border-amber-900/40">
          <CardHeader><CardTitle className="text-amber-500">总结: Cand-Beta-14</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <p className="text-zinc-700 dark:text-zinc-300">整体表现优于基准，但最大回撤改善有限，建议进一步观察震荡市表现。<span className="text-amber-400 ml-2">需保留观察。</span></p>
          </CardContent>
        </Card>
      </div>

    </div>
  );
}
