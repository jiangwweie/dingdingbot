import React, { useEffect, useState, useMemo } from 'react';
import { getRuntimeEvents } from '@/src/services/api';
import { AppEvent } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, AlertCircle, Filter } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { fmtDateTimeFull } from '@/src/lib/console-utils';
import { useTableSort, compareTimestamp, comparePrimitive, FilterSelect, emptyDataCard, SortOrder } from '@/src/lib/table-utils';

const CATEGORY_OPTIONS = [
  { value: 'ALL', label: '全部类别' },
  { value: 'STARTUP', label: 'STARTUP' },
  { value: 'RECONCILIATION', label: 'RECONCILIATION' },
  { value: 'BREAKER', label: 'BREAKER' },
  { value: 'RECOVERY', label: 'RECOVERY' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'SIGNAL', label: 'SIGNAL' },
  { value: 'EXECUTION', label: 'EXECUTION' },
];

const SEVERITY_OPTIONS = [
  { value: 'ALL', label: '全部等级' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARN', label: 'WARN' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'SUCCESS', label: 'SUCCESS' },
];

const SORT_OPTIONS = [
  { value: 'timestamp-desc', label: '时间降序' },
  { value: 'timestamp-asc', label: '时间升序' },
  { value: 'severity-desc', label: '等级降序' },
  { value: 'severity-asc', label: '等级升序' },
  { value: 'category-desc', label: '类别降序' },
  { value: 'category-asc', label: '类别升序' },
];

const severityScore = (s: string) => {
  switch (s) {
    case 'ERROR': return 4;
    case 'WARN': return 3;
    case 'SUCCESS': return 2;
    case 'INFO': return 1;
    default: return 0;
  }
};

const severityVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'default' => {
  switch (s) {
    case 'SUCCESS': return 'success';
    case 'WARN': return 'warning';
    case 'ERROR': return 'danger';
    case 'INFO': return 'info';
    default: return 'default';
  }
};

const severityColor = (s: string) => {
  switch(s) {
    case 'INFO': return 'text-blue-500 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-900/50';
    case 'WARN': return 'text-amber-500 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-900/50';
    case 'ERROR': return 'text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-900/50';
    case 'SUCCESS': return 'text-emerald-500 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-900/50';
    default: return 'text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-900/20 border-zinc-200 dark:border-zinc-800';
  }
};

const categoryIcon = (c: string) => {
  switch (c) {
    case 'STARTUP': return '▶';
    case 'RECONCILIATION': return '✓';
    case 'BREAKER': return '⚡';
    case 'RECOVERY': return '↻';
    case 'WARNING': return '⚠';
    case 'ERROR': return '✕';
    case 'SIGNAL': return '◈';
    case 'EXECUTION': return '→';
    default: return '·';
  }
};

export default function Events() {
  const { refreshCount } = useRefreshContext();
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const sort = useTableSort<AppEvent>('timestamp', 'desc');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeEvents().then(res => {
      if (active) { setEvents(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filtered = useMemo(() => {
    let rows = events;
    if (categoryFilter !== 'ALL') rows = rows.filter(evt => evt.category === categoryFilter);
    if (severityFilter !== 'ALL') rows = rows.filter(evt => evt.severity === severityFilter);
    return [...rows].sort((a, b) => {
      switch (sort.sortField) {
        case 'timestamp': return compareTimestamp(a.timestamp, b.timestamp, sort.sortOrder);
        case 'severity': {
          const cmp = severityScore(a.severity) - severityScore(b.severity);
          return sort.sortOrder === 'asc' ? cmp : -cmp;
        }
        case 'category': return comparePrimitive(a.category, b.category, sort.sortOrder);
        default: return 0;
      }
    });
  }, [events, categoryFilter, severityFilter, sort.sortField, sort.sortOrder]);

  if (loading && events.length === 0) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }
  if (error && events.length === 0) {
    return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>事件数据加载失败</span></div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight">事件日志</h2>
        <p className="text-xs text-zinc-500 mt-1">系统全生命周期操作事件时间线。</p>
      </div>

      {error && events.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>事件流</CardTitle>
          <div className="flex items-center gap-3">
            <FilterSelect
              value={`${sort.sortField}-${sort.sortOrder}`}
              onChange={v => {
                const [f, o] = v.split('-') as [string, SortOrder];
                sort.setSort(f, o);
              }}
              options={SORT_OPTIONS}
            />
            <Filter className="w-3.5 h-3.5 text-zinc-400" />
            <FilterSelect value={categoryFilter} onChange={setCategoryFilter} options={CATEGORY_OPTIONS} />
            <FilterSelect value={severityFilter} onChange={setSeverityFilter} options={SEVERITY_OPTIONS} />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {events.length === 0 ? (
            emptyDataCard('暂无事件记录')
          ) : filtered.length === 0 ? (
            emptyDataCard('筛选后无匹配结果')
          ) : (
            <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {filtered.map((evt) => (
                <div key={evt.id} className="p-4 flex gap-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors">
                  <div className="flex-shrink-0 mt-0.5">
                    <div className={cn("w-8 h-8 rounded-full flex items-center justify-center border text-sm", severityColor(evt.severity))}>
                      {categoryIcon(evt.category)}
                    </div>
                  </div>
                  <div className="flex-1 space-y-1">
                    <div className="flex justify-between items-start">
                      <div className="font-medium text-zinc-900 dark:text-zinc-200 text-sm">
                        {evt.message}
                      </div>
                      <div className="text-xs text-zinc-500 font-mono ml-4">
                        {fmtDateTimeFull(evt.timestamp)}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <Badge variant={severityVariant(evt.severity)}>{evt.severity}</Badge>
                      <Badge variant="outline">{evt.category}</Badge>
                      {evt.related_entities && evt.related_entities.map((ent, i) => (
                        <span key={i} className="text-[10px] font-mono text-zinc-400">
                          {ent}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}