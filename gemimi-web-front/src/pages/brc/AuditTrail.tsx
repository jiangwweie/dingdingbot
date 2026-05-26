import { useEffect, useState } from 'react';
import { History, Link2 } from 'lucide-react';
import { brcApi, AuditTrailResponse, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, EmptyState, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function AuditTrail() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [data, setData] = useState<AuditTrailResponse | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([brcApi.readiness(), brcApi.auditTrail()])
      .then(([ready, payload]) => {
        setReadiness(ready);
        setData(payload);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!data) return <div className="text-xs text-zinc-500">加载审计链路...</div>;

  return (
    <div className="space-y-4">
      <StageStrip
        current="Audit Trail 审计链路"
        next="按时间线查看发生了什么，按对象链路追踪为什么发生。"
        global="飞书审批、云部署和策略池都应复用这条审计事实链。"
      />
      <OwnerSummary
        conclusion={data.conclusion}
        why={readiness ? whyText(readiness) : '读取 BRC operator actions、workflow runs 和 review decisions。'}
        canDo="查看时间线、选择记录、展开证据 JSON。"
        cannotDo="不能重放 workflow、修改历史、补写交易记录或授权实盘。"
        accountImpact={data.account_impact}
        next="如果想知道某条记录为什么发生，进入 LLM Copilot 或展开对象链路。"
        tone="info"
      />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="h-3.5 w-3.5 text-blue-500" />
              Timeline（时间线）
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.timeline.length === 0 ? (
              <EmptyState title="暂无审计事件" body="生成计划、创建 workflow 或写入 review 后，这里会出现时间线。" />
            ) : (
              <div className="space-y-2">
                {data.timeline.map((item, index) => (
                  <button
                    key={`${String(item.type)}-${String(item.id)}-${index}`}
                    className="block w-full rounded-sm border border-zinc-200 p-3 text-left hover:border-blue-500 dark:border-zinc-800"
                    onClick={() => setSelected(item)}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">{String(item.title || item.type)}</span>
                      <StatusBadge state={item.result} />
                    </div>
                    <p className="mt-1 text-xs leading-5 text-zinc-500">{String(item.summary || '已记录的治理事件')}</p>
                    <p className="mt-1 text-[11px] leading-4 text-zinc-500">{String(item.account_impact || '只读审计记录')}</p>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="h-3.5 w-3.5 text-emerald-500" />
              Object Trace（对象链路）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            {selected ? (
              <>
                <p>当前选择：{String(selected.title || selected.type)}</p>
                <p>ID：<span className="font-mono">{String(selected.id || 'unknown')}</span></p>
                <p>结果：<StatusBadge state={selected.result} /></p>
                <p>账户影响：{String(selected.account_impact || '只读记录')}</p>
                <JsonDetails data={selected} label="展开对象链路详情" />
              </>
            ) : (
              <p className="text-zinc-500">选择左侧一条时间线记录后，这里会显示对象链路摘要。</p>
            )}
          </CardContent>
        </Card>
      </div>

      <DeveloperDetails data={data.developer_details} />
    </div>
  );
}
