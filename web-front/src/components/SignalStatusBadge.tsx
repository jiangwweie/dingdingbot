import React from 'react';
import { SignalStatus } from '../lib/api';
import { cn } from '../lib/utils';

interface SignalStatusBadgeProps {
  status: SignalStatus;
}

const statusConfig: Record<SignalStatus, { label: string; color: string }> = {
  [SignalStatus.GENERATED]: { label: '已生成', color: '#6b7280' },      // 灰色
  [SignalStatus.PENDING]: { label: '等待成交', color: '#eab308' },       // 黄色
  [SignalStatus.ACTIVE]: { label: '监控中', color: '#22c55e' },         // 绿色
  [SignalStatus.SUPERSEDED]: { label: '已替代', color: '#6b7280' },     // 灰色
  [SignalStatus.FILLED]: { label: '已成交', color: '#22c55e' },         // 绿色
  [SignalStatus.CANCELLED]: { label: '已取消', color: '#3b82f6' },      // 蓝色
  [SignalStatus.REJECTED]: { label: '被拒绝', color: '#ef4444' },       // 红色
  [SignalStatus.WON]: { label: '止盈', color: '#22c55e' },              // 绿色
  [SignalStatus.LOST]: { label: '止损', color: '#ef4444' },             // 红色
};

export function SignalStatusBadge({ status }: SignalStatusBadgeProps) {
  const config = statusConfig[status];

  // 未知状态或配置缺失时的降级处理
  if (!config) {
    return (
      <span
        className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
        style={{
          backgroundColor: '#6b728020',
          color: '#6b7280',
        }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full mr-1.5"
          style={{ backgroundColor: '#6b7280' }}
        />
        {status || '未知'}
      </span>
    );
  }

  // SUPERSEDED 状态需要视觉降级
  const isSuperseded = status === SignalStatus.SUPERSEDED;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
        isSuperseded && "opacity-50 grayscale"
      )}
      style={{
        backgroundColor: `${config.color}20`,  // 20% 透明度背景
        color: config.color,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full mr-1.5"
        style={{ backgroundColor: config.color }}
      />
      {config.label}
    </span>
  );
}
