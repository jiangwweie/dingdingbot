import React from 'react';
import { SignalStatus } from '../lib/api';

interface SignalStatusBadgeProps {
  status: SignalStatus;
}

const statusConfig: Record<SignalStatus, { label: string; color: string }> = {
  [SignalStatus.GENERATED]: { label: '已生成', color: '#6b7280' },      // 灰色
  [SignalStatus.PENDING]: { label: '等待成交', color: '#eab308' },       // 黄色
  [SignalStatus.FILLED]: { label: '已成交', color: '#22c55e' },         // 绿色
  [SignalStatus.CANCELLED]: { label: '已取消', color: '#3b82f6' },      // 蓝色
  [SignalStatus.REJECTED]: { label: '被拒绝', color: '#ef4444' },       // 红色
};

export function SignalStatusBadge({ status }: SignalStatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
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
