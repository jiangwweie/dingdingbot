import React, { useEffect, useState, useMemo } from 'react';
import { getEvents } from '@/src/services/mockApi';
import { AppEvent } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, Activity, PlayCircle, ShieldAlert, Cpu, AlertTriangle, AlertCircle, SignalHigh, CheckCircle2, Filter } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { format } from 'date-fns';

export default function Events() {
  const { refreshCount } = useRefreshContext();
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');

  useEffect(() => {
    let active = true;
    setLoading(true);
    getEvents().then(res => {
      if (active) {
        setEvents(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  const filteredEvents = useMemo(() => {
    return events.filter(evt => {
      if (categoryFilter !== 'ALL' && evt.category !== categoryFilter) return false;
      if (severityFilter !== 'ALL' && evt.severity !== severityFilter) return false;
      return true;
    });
  }, [events, categoryFilter, severityFilter]);

  if (loading && events.length === 0) {
    return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  }

  const getIcon = (category: string) => {
    switch (category) {
      case 'STARTUP': return <PlayCircle className="w-4 h-4" />;
      case 'RECONCILIATION': return <CheckCircle2 className="w-4 h-4" />;
      case 'BREAKER': return <ShieldAlert className="w-4 h-4" />;
      case 'RECOVERY': return <Cpu className="w-4 h-4" />;
      case 'WARNING': return <AlertTriangle className="w-4 h-4" />;
      case 'ERROR': return <AlertCircle className="w-4 h-4" />;
      case 'SIGNAL': return <SignalHigh className="w-4 h-4" />;
      case 'EXECUTION': return <Activity className="w-4 h-4" />;
      default: return <Activity className="w-4 h-4" />;
    }
  };

  const getColor = (severity: string) => {
    switch(severity) {
      case 'INFO': return 'text-blue-500 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-900/50';
      case 'WARN': return 'text-amber-500 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-900/50';
      case 'ERROR': return 'text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-900/50';
      case 'SUCCESS': return 'text-emerald-500 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-900/50';
      default: return 'text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-900/20 border-zinc-200 dark:border-zinc-800';
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight">操作日志 (Events Timeline)</h2>
        <p className="text-xs text-zinc-500 mt-1 max-w-xl">
          系统组件全生命周期内的操作摘要时间线。
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>最新事件流</CardTitle>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-zinc-400" />
              <select 
                value={categoryFilter} 
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="text-xs bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-zinc-600 dark:text-zinc-300"
              >
                <option value="ALL">全部类别</option>
                <option value="STARTUP">启动 (STARTUP)</option>
                <option value="RECONCILIATION">对账 (RECONCILIATION)</option>
                <option value="BREAKER">熔断 (BREAKER)</option>
                <option value="RECOVERY">恢复 (RECOVERY)</option>
                <option value="WARNING">警告 (WARNING)</option>
                <option value="ERROR">错误 (ERROR)</option>
                <option value="SIGNAL">信号 (SIGNAL)</option>
                <option value="EXECUTION">执行 (EXECUTION)</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <select 
                value={severityFilter} 
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="text-xs bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-zinc-600 dark:text-zinc-300"
              >
                <option value="ALL">全部等级</option>
                <option value="INFO">INFO</option>
                <option value="WARN">WARN</option>
                <option value="ERROR">ERROR</option>
                <option value="SUCCESS">SUCCESS</option>
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {filteredEvents.map((evt) => (
              <div key={evt.id} className="p-4 flex gap-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/30 transition-colors">
                <div className="flex-shrink-0 mt-0.5">
                  <div className={cn("w-8 h-8 rounded-full flex items-center justify-center border", getColor(evt.severity))}>
                    {getIcon(evt.category)}
                  </div>
                </div>
                <div className="flex-1 space-y-1">
                  <div className="flex justify-between items-start">
                    <div className="font-medium text-zinc-900 dark:text-zinc-200 text-sm">
                      {evt.message}
                    </div>
                    <div className="text-xs text-zinc-500 font-mono ml-4">
                      {format(new Date(evt.timestamp), 'yyyy-MM-dd HH:mm:ss')}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-zinc-500 bg-zinc-100 dark:bg-zinc-900 px-2 py-0.5 rounded border border-zinc-200 dark:border-zinc-800">
                      {evt.category}
                    </span>
                    {evt.related_entities && evt.related_entities.map((ent, i) => (
                      <span key={i} className="text-[10px] font-mono text-zinc-400">
                        🔗 {ent}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
            {filteredEvents.length === 0 && (
              <div className="p-8 text-center text-zinc-500">
                暂无符合条件的日志
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      
    </div>
  );
}
