import { useEffect, useState } from "react";

interface DataAgeProps {
  generatedAt: string | null;
}

function formatAge(generatedAt: string | null, nowMs: number): string {
  if (!generatedAt) return "数据时间 --";
  const generatedMs = Date.parse(generatedAt);
  if (!Number.isFinite(generatedMs)) return "数据时间不可用";
  const ageMinutes = Math.max(0, Math.floor((nowMs - generatedMs) / 60_000));
  if (ageMinutes === 0) return "数据 刚刚";
  if (ageMinutes < 60) return `数据 ${ageMinutes} 分钟前`;
  return `数据 ${Math.floor(ageMinutes / 60)} 小时前`;
}

export function DataAge({ generatedAt }: DataAgeProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  return <>{formatAge(generatedAt, nowMs)}</>;
}
