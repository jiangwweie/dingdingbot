import { PositionInfo } from '../../types/order';
import { DirectionBadge } from './DirectionBadge';
import { PnLBadge } from './PnLBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { format } from 'date-fns';
import { ArrowRight } from 'lucide-react';
import { cn } from '../../lib/utils';

interface PositionsTableProps {
  positions: PositionInfo[];
  isLoading?: boolean;
  onPositionClick?: (positionId: string) => void;
}

export function PositionsTable({ positions, isLoading, onPositionClick }: PositionsTableProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
            <tr>
              <th className="px-6 py-4 font-medium">仓位 ID</th>
              <th className="px-6 py-4 font-medium">币种</th>
              <th className="px-6 py-4 font-medium">方向</th>
              <th className="px-6 py-4 font-medium">入场价</th>
              <th className="px-6 py-4 font-medium">当前数量</th>
              <th className="px-6 py-4 font-medium">未实现盈亏</th>
              <th className="px-6 py-4 font-medium">杠杆</th>
              <th className="px-6 py-4 font-medium">开仓时间</th>
              <th className="px-6 py-4 font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {[...Array(10)].map((_, i) => (
              <tr key={i} className="animate-pulse">
                {[...Array(9)].map((_, j) => (
                  <td key={j} className="px-6 py-4">
                    <div className="h-4 bg-gray-100 rounded w-20" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-20 text-center text-gray-400">
          没有找到持仓记录
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
          <tr>
            <th className="px-6 py-4 font-medium">仓位 ID</th>
            <th className="px-6 py-4 font-medium">币种</th>
            <th className="px-6 py-4 font-medium">方向</th>
            <th className="px-6 py-4 font-medium">入场价</th>
            <th className="px-6 py-4 font-medium">当前数量</th>
            <th className="px-6 py-4 font-medium">未实现盈亏</th>
            <th className="px-6 py-4 font-medium">杠杆</th>
            <th className="px-6 py-4 font-medium">开仓时间</th>
            <th className="px-6 py-4 font-medium">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {positions.map((position) => (
            <tr
              key={position.position_id}
              onClick={() => onPositionClick?.(position.position_id)}
              className={cn(
                "hover:bg-gray-50/50 transition-colors cursor-pointer group",
                position.is_closed && "bg-gray-50"
              )}
            >
              <td className="px-6 py-4">
                <span className="font-mono text-xs text-gray-600">
                  {position.position_id.slice(0, 8)}...{position.position_id.slice(-4)}
                </span>
              </td>
              <td className="px-6 py-4">
                <span className="font-semibold text-gray-900">
                  {position.symbol.replace(':USDT', '')}
                </span>
              </td>
              <td className="px-6 py-4">
                <DirectionBadge direction={position.direction} />
              </td>
              <td className="px-6 py-4 text-right">
                <DecimalDisplay value={position.entry_price} decimals={2} />
              </td>
              <td className="px-6 py-4 text-right">
                <DecimalDisplay value={position.current_qty} decimals={4} />
              </td>
              <td className="px-6 py-4">
                <PnLBadge pnl={position.unrealized_pnl} />
              </td>
              <td className="px-6 py-4 text-right text-gray-500">
                {position.leverage}x
              </td>
              <td className="px-6 py-4 text-gray-500">
                {format(new Date(position.opened_at), 'MM-dd HH:mm')}
              </td>
              <td className="px-6 py-4">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onPositionClick?.(position.position_id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-xs text-apple-blue hover:underline"
                >
                  详情 <ArrowRight className="w-3 h-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
