import { useState, useCallback } from 'react';
import { useApi, fetchPositions, closePosition as closePositionApi } from '../lib/api';
import { PositionInfo, PositionResponse, ClosePositionRequest } from '../types/order';
import { PositionsTable } from '../components/v3/PositionsTable';
import { PositionDetailsDrawer } from '../components/v3/PositionDetailsDrawer';
import { ClosePositionModal } from '../components/v3/ClosePositionModal';
import { PnLBadge } from '../components/v3/PnLBadge';
import { Filter, X, RefreshCw, DollarSign, TrendingUp, Shield } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Positions() {
  // 筛选状态
  const [symbolFilter, setSymbolFilter] = useState('');
  const [isClosedFilter, setIsClosedFilter] = useState(false); // false=未平仓，true=已平仓

  // 详情抽屉状态
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<PositionInfo | null>(null);

  // 平仓对话框状态
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  // 构建 API URL
  let url = '/api/v3/positions?limit=100&offset=0';
  if (symbolFilter) url += `&symbol=${encodeURIComponent(symbolFilter)}`;
  url += `&is_closed=${isClosedFilter}`;

  const { data, error, mutate } = useApi<PositionResponse>(url, 10000); // 10 秒刷新

  const isLoading = !data && !error;
  const positions = data?.positions || [];
  const totalUnrealizedPnl = data?.total_unrealized_pnl || '0';
  const totalRealizedPnl = data?.total_realized_pnl || '0';
  const totalMarginUsed = data?.total_margin_used || '0';
  const accountEquity = data?.account_equity;

  // 打开详情抽屉
  const handlePositionClick = useCallback(async (positionId: string) => {
    setSelectedPositionId(positionId);
    setIsDrawerOpen(true);
    // 可以在这里调用 fetchPositionDetails 获取更详细的信息
    const position = positions.find(p => p.position_id === positionId);
    setSelectedPosition(position || null);
  }, [positions]);

  // 关闭详情抽屉
  const closeDrawer = () => {
    setIsDrawerOpen(false);
    setTimeout(() => {
      setSelectedPositionId(null);
      setSelectedPosition(null);
    }, 300);
  };

  // 打开平仓对话框
  const openCloseModal = () => {
    setIsCloseModalOpen(true);
  };

  // 关闭平仓对话框
  const closeCloseModal = () => {
    setIsCloseModalOpen(false);
  };

  // 执行平仓
  const handleClosePosition = async (payload: ClosePositionRequest) => {
    if (!selectedPositionId) return;

    setIsClosing(true);
    try {
      await closePositionApi(selectedPositionId, payload);
      await mutate(); // 刷新列表
      closeCloseModal();
      closeDrawer();
      alert('平仓成功！');
    } catch (err: any) {
      const errorMsg = err?.info?.message || err?.message || '平仓失败，请重试';
      alert(`平仓失败：${errorMsg}`);
    } finally {
      setIsClosing(false);
    }
  };

  // 清空筛选
  const clearFilters = () => {
    setSymbolFilter('');
    setIsClosedFilter(false);
  };

  // 判断是否有活跃筛选
  const hasActiveFilters = symbolFilter || isClosedFilter;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">仓位管理</h1>
          <p className="text-sm text-gray-500 mt-1">查看和管理当前持仓仓位</p>
        </div>

        <button
          onClick={() => mutate()}
          disabled={isLoading}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
          刷新
        </button>
      </div>

      {/* 账户概览卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-2xl p-5 border border-blue-100">
          <div className="flex items-center gap-2 text-blue-700 mb-2">
            <DollarSign className="w-5 h-5" />
            <span className="text-sm font-medium">账户权益</span>
          </div>
          <div className="text-2xl font-bold text-blue-900 font-mono">
            ${accountEquity ? parseFloat(accountEquity).toFixed(2) : '-'}
          </div>
        </div>

        <div className="bg-gradient-to-br from-green-50 to-green-100/50 rounded-2xl p-5 border border-green-100">
          <div className="flex items-center gap-2 text-green-700 mb-2">
            <TrendingUp className="w-5 h-5" />
            <span className="text-sm font-medium">未实现盈亏</span>
          </div>
          <div className="text-2xl font-bold font-mono">
            <PnLBadge pnl={totalUnrealizedPnl} className="text-xl" />
          </div>
        </div>

        <div className="bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-2xl p-5 border border-purple-100">
          <div className="flex items-center gap-2 text-purple-700 mb-2">
            <Shield className="w-5 h-5" />
            <span className="text-sm font-medium">保证金占用</span>
          </div>
          <div className="text-2xl font-bold text-purple-900 font-mono">
            ${parseFloat(totalMarginUsed).toFixed(2)}
          </div>
        </div>

        <div className="bg-gradient-to-br from-orange-50 to-orange-100/50 rounded-2xl p-5 border border-orange-100">
          <div className="flex items-center gap-2 text-orange-700 mb-2">
            <DollarSign className="w-5 h-5" />
            <span className="text-sm font-medium">已实现盈亏</span>
          </div>
          <div className="text-2xl font-bold font-mono">
            <PnLBadge pnl={totalRealizedPnl} className="text-xl" />
          </div>
        </div>
      </div>

      {/* 筛选器 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
            <Filter className="w-3 h-3" />
            筛选
          </div>

          <div className="h-4 w-px bg-gray-200" />

          {/* 币种筛选 */}
          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            <option value="">全部币种</option>
            <option value="BTC/USDT:USDT">BTC</option>
            <option value="ETH/USDT:USDT">ETH</option>
            <option value="SOL/USDT:USDT">SOL</option>
            <option value="BNB/USDT:USDT">BNB</option>
          </select>

          {/* 仓位状态筛选 */}
          <div className="flex items-center gap-2 bg-gray-50 rounded-lg p-1">
            <button
              onClick={() => setIsClosedFilter(false)}
              className={cn(
                "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
                !isClosedFilter
                  ? "bg-white text-gray-900 shadow-sm border border-gray-200"
                  : "text-gray-500 hover:text-gray-700"
              )}
            >
              持仓中
            </button>
            <button
              onClick={() => setIsClosedFilter(true)}
              className={cn(
                "px-3 py-1.5 text-sm font-medium rounded-md transition-colors",
                isClosedFilter
                  ? "bg-white text-gray-900 shadow-sm border border-gray-200"
                  : "text-gray-500 hover:text-gray-700"
              )}
            >
              已平仓
            </button>
          </div>

          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-2 py-1.5 text-xs text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              清空筛选
            </button>
          )}
        </div>
      </div>

      {/* 仓位列表 */}
      <PositionsTable
        positions={positions}
        isLoading={isLoading}
        onPositionClick={handlePositionClick}
      />

      {/* 详情抽屉 */}
      <PositionDetailsDrawer
        position={selectedPosition}
        isOpen={isDrawerOpen}
        onClose={closeDrawer}
        onQuickClose={openCloseModal}
      />

      {/* 平仓确认对话框 */}
      <ClosePositionModal
        position={selectedPosition}
        isOpen={isCloseModalOpen}
        onClose={closeCloseModal}
        onSubmit={handleClosePosition}
        isLoading={isClosing}
      />
    </div>
  );
}
