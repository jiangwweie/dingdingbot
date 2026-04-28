import React, { useEffect, useState, useMemo } from 'react';
import { getCandidates } from '@/src/services/api';
import { Candidate } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/src/components/ui/Table';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDateTime } from '@/src/lib/console-utils';
import { useTableSort, compareTimestamp, comparePrimitive, FilterSelect, EmptyFilterRow, emptyDataCard } from '@/src/lib/table-utils';
import { reviewLabel, warningLabel, shortResearchName } from '@/src/lib/research-format';

function reviewVariant(status: string | null | undefined): 'success' | 'warning' | 'info' | 'danger' | 'default' {
  switch (status) {
    case 'PASS_STRICT': return 'success';
    case 'PASS_STRICT_WITH_WARNINGS': return 'warning';
    case 'PASS_LOOSE': return 'info';
    case 'REJECT': return 'danger';
    case 'PENDING': return 'default';
    default: return 'default';
  }
}

function gateLabel(result: string | null | undefined): string {
  switch (result) {
    case 'PASSED': return '通过';
    case 'FAILED': return '未通过';
    default: return '--';
  }
}

const STATUS_OPTIONS = [
  { value: 'ALL', label: '全部状态' },
  { value: 'PASS_STRICT', label: '严格通过' },
  { value: 'PASS_STRICT_WITH_WARNINGS', label: '通过但有警告' },
  { value: 'PASS_LOOSE', label: '初步达标' },
  { value: 'REJECT', label: '不建议' },
  { value: 'PENDING', label: '待评审' },
];

export default function Candidates() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const sort = useTableSort<Candidate>('generated_at', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getCandidates().then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filtered = useMemo(() => {
    let rows = data;
    if (statusFilter !== 'ALL') rows = rows.filter(c => c.review_status === statusFilter);
    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'generated_at': return compareTimestamp(a.generated_at, b.generated_at, sort.sortOrder);
        case 'candidate_name': return comparePrimitive(a.candidate_name, b.candidate_name, sort.sortOrder);
        case 'review_status': return comparePrimitive(a.review_status, b.review_status, sort.sortOrder);
        default: return 0;
      }
    });
  }, [data, statusFilter, sort.sortField, sort.sortOrder]);

  if (loading && data.length === 0) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && data.length === 0) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>候选策略加载失败</span></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">候选策略</h2>
          <p className="text-xs text-zinc-500 mt-1">经过风控校验的策略资产池，可进入策略对比或回测复用。</p>
        </div>
        <span className="text-sm text-zinc-500">{data.length} 条</span>
      </div>

      {error && data.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {data.length === 0 ? (
        <Card><CardContent>{emptyDataCard('暂无候选策略')}</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800">
              <span className="text-xs text-zinc-500">审核状态</span>
              <FilterSelect value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} />
            </div>
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50 dark:bg-zinc-900/50">
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('candidate_name')}>名称{sort.sortIndicator('candidate_name')}</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('generated_at')}>生成时间{sort.sortIndicator('generated_at')}</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>目标</TableHead>
                  <TableHead className="cursor-pointer select-none" onClick={() => sort.toggleSort('review_status')}>审核{sort.sortIndicator('review_status')}</TableHead>
                  <TableHead>风控门</TableHead>
                  <TableHead>警告</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <EmptyFilterRow colSpan={7} />
                ) : filtered.map(c => (
                  <TableRow key={c.candidate_name}>
                    <TableCell>
                      <span className="font-medium text-sm" title={c.candidate_name}>{shortResearchName(c.candidate_name)}</span>
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500">{fmtDateTime(c.generated_at)}</TableCell>
                    <TableCell className="text-xs">{c.source_profile || '--'}</TableCell>
                    <TableCell className="text-xs">{c.objective || '--'}</TableCell>
                    <TableCell><Badge variant={reviewVariant(c.review_status)}>{reviewLabel(c.review_status)}</Badge></TableCell>
                    <TableCell className="text-xs">{gateLabel(c.strict_gate_result)}</TableCell>
                    <TableCell className="text-xs text-zinc-500">
                      {c.warnings && c.warnings.length > 0
                        ? c.warnings.map(w => warningLabel(w)).join('、')
                        : '--'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}