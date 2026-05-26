import { useEffect, useState } from 'react';
import { GitBranch, Layers3 } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function StrategyPlaybook() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness().then(setReadiness).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">正在读取打法状态...</div>;

  const summary = readiness.strategy_playbook_summary || readiness.playbook_summary || {};
  const catalog = Array.isArray(summary.catalog) ? summary.catalog as Array<Record<string, unknown>> : [];

  return (
    <div className="space-y-4">
      <StageStrip
        current="Strategy / Playbook 打法"
        next="先看当前打法是什么，再确认它不会自动执行。"
        global="策略池 Strategy Pool 后续单独建设；当前只是控制台展示。"
      />
      <OwnerSummary
        conclusion="这里展示打法状态，不是自动交易面板"
        why={whyText(readiness)}
        canDo="查看当前 playbook、打法目录和自动执行是否关闭。"
        cannotDo="不能在这里切换打法、启用策略池、启动自动策略或授权 live。"
        accountImpact="只读展示，不影响真实账户。"
        next="如果需要解释某个打法，进入 LLM Copilot 提问。"
        tone="info"
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-3.5 w-3.5 text-blue-500" />
              当前打法
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="Playbook" value={String(summary.current_playbook_id || 'PB-000-OBSERVE-ONLY')} />
            <Row label="说明" value={String(summary.current_playbook_meaning || 'Playbook 是人工打法/治理框架。')} />
            <Row label="Live" value={<StatusBadge state="unauthorized" />} />
            <Row label="页面操作" value={<StatusBadge state="display only" />} />
            <p className="pt-2 text-[11px] leading-4 text-zinc-500">
              当前版本只展示状态，不提供切换按钮。以后切换打法必须走确认和审计。
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers3 className="h-3.5 w-3.5 text-purple-500" />
              自动执行
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="是否启用" value={summary.strategy_execution_enabled ? 'enabled' : '未启用'} />
            <Row label="说明" value={String(summary.strategy_execution_status || '当前没有启用可执行 Strategy。')} />
            <Row label="Strategy Pool" value="后续独立阶段" />
            <Row label="自动交易" value={<StatusBadge state="deferred" />} />
            <p className="pt-2 text-[11px] leading-4 text-zinc-500">
              Playbook 是打法框架；真正自动执行必须单独验证和授权。
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>打法目录</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {catalog.map((item) => (
              <div key={String(item.playbook_id)} className="rounded-sm border border-zinc-200 p-3 text-xs leading-5 dark:border-zinc-800">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{String(item.playbook_id)}</span>
                  <StatusBadge state={item.status} />
                </div>
                <p className="mt-1 text-zinc-500">{String(item.label || '')}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <DeveloperDetails data={summary} label="展开打法技术数据" />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[60%] text-right font-medium">{value}</span>
    </div>
  );
}
