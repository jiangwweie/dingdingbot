import { useEffect, useState } from 'react';
import { TerminalSquare } from 'lucide-react';
import { brcApi, ReadinessResponse, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, OwnerSummary, StageStrip } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function DeveloperDetail() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [safety, setSafety] = useState<RuntimeSafetyResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([brcApi.readiness(), brcApi.runtimeSafety()])
      .then(([readinessPayload, safetyPayload]) => {
        setReadiness(readinessPayload);
        setSafety(safetyPayload);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">加载 Developer Detail...</div>;

  return (
    <div className="space-y-4">
      <StageStrip
        current="BRC-R4.1 developer detail"
        next="这里用于排查配置，不作为 Owner 的主操作入口。"
        global="生产化前云部署、飞书审批、CSRF/idempotency/secret manager 仍需单独阶段。"
      />
      <OwnerSummary
        conclusion="这是技术详情页，不是操作入口"
        why={whyText(readiness)}
        canDo="查看 readiness、runtime control、developer detail 原始数据。"
        cannotDo="不能在这里触发下单、提现、转账、testnet 演练或复盘写入。"
        accountImpact="不会影响真实账户。"
        next="Owner 日常操作请回到 Guide 操作向导。"
        tone="info"
      />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TerminalSquare className="h-3.5 w-3.5 text-blue-500" />
            Raw State（原始状态）
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeveloperDetails data={readiness} label="Readiness JSON" />
          <DeveloperDetails data={safety} label="Runtime Control JSON" />
        </CardContent>
      </Card>
    </div>
  );
}
