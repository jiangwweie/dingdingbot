import React, { useEffect, useState } from 'react';
import { getCandidates } from '@/src/services/mockApi';
import { Candidate } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';

export default function Candidates() {
  const { refreshCount } = useRefreshContext();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getCandidates().then(res => {
      if (active) {
        setCandidates(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && candidates.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;

  const renderReviewStatus = (status: string) => {
    switch(status) {
      case 'PASS_STRICT': return <Badge variant="success">通过验证 (STRICT)</Badge>;
      case 'PASS_STRICT_WITH_WARNINGS': return <Badge variant="warning">通过 (带警告)</Badge>;
      case 'PASS_LOOSE': return <Badge variant="info">宽容通过</Badge>;
      case 'REJECT': return <Badge variant="danger">拒绝 (REJECT)</Badge>;
      default: return <Badge>{status}</Badge>;
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-xl font-bold tracking-tight">候选策略 (Research Candidates)</h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-xl">
            显示由 Optuna 为候选池生成的实验产物。注意：评审状态仅供展示，手动变更被禁止。
          </p>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>候选文件 (/reports/optuna_candidates)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>策略名称</TableHead>
                <TableHead>生成时间</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>严格检测结果</TableHead>
                <TableHead>评审状态</TableHead>
                <TableHead>警告</TableHead>
                <TableHead>逻辑</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.map(cand => (
                <TableRow key={cand.candidate_name}>
                  <TableCell className="font-mono text-sm text-blue-400 font-medium">
                    <Link to={`/research/candidates/${cand.candidate_name}`} className="hover:underline flex items-center gap-1.5 w-max">
                      {cand.candidate_name}
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  </TableCell>
                  <TableCell className="text-zinc-600 dark:text-zinc-400 text-xs">{format(new Date(cand.generated_at), 'yyyy-MM-dd HH:mm')}</TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-zinc-700 dark:text-zinc-300">{cand.source_profile}</span>
                      <span className="text-zinc-600 font-mono text-[10px]">{cand.git_commit}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                     {cand.strict_gate_result === 'PASSED' ? <Badge variant="success">通过</Badge> : <Badge variant="danger">未通过</Badge>}
                  </TableCell>
                  <TableCell>{renderReviewStatus(cand.review_status)}</TableCell>
                  <TableCell>
                    {cand.warnings.length === 0 ? <span className="text-zinc-600">-</span> : (
                      <span className="text-amber-500 text-xs bg-amber-950/30 px-2 py-1 rounded">
                        {cand.warnings.length} 个警告
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Link to={`/research/replay/${cand.candidate_name}`} className="text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:text-white transition-colors bg-zinc-100 dark:bg-zinc-800 py-1.5 px-3 rounded">
                      操作上下文
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
