import { useState, useCallback } from 'react';
import { useApi } from '../lib/api';
import { OrderResponse, OrderStatus, OrderRole } from '../types/order';
import { Filter, X, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { cn } from '../lib/utils';
import { OrdersTable } from '../components/v3/OrdersTable';
import { OrderDetailsDrawer } from '../components/v3/OrderDetailsDrawer';
import { CreateOrderModal } from '../components/v3/CreateOrderModal';
import { cancelOrder } from '../lib/api';

const symbolOptions = [
  { value: '', label: '全部币种' },
  { value: 'BTC/USDT:USDT', label: 'BTC' },
  { value: 'ETH/USDT:USDT', label: 'ETH' },
  { value: 'SOL/USDT:USDT', label: 'SOL' },
  { value: 'BNB/USDT:USDT', label: 'BNB' },
];

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'PENDING', label: '待处理' },
  { value: 'OPEN', label: '进行中' },
  { value: 'FILLED', label: '已成交' },
  { value: 'CANCELED', label: '已取消' },
  { value: 'REJECTED', label: '已拒绝' },
  { value: 'EXPIRED', label: '已过期' },
  { value: 'PARTIALLY_FILLED', label: '部分成交' },
];

const roleOptions = [
  { value: '', label: '全部角色' },
  { value: 'ENTRY', label: '开仓' },
  { value: 'TP1', label: '止盈 1' },
  { value: 'TP2', label: '止盈 2' },
  { value: 'TP3', label: '止盈 3' },
  { value: 'TP4', label: '止盈 4' },
  { value: 'TP5', label: '止盈 5' },
  { value: 'SL', label: '止损' },
];

export default function Orders() {
  const [page, setPage] = useState(1);
  const limit = 20;

  // Filters
  const [symbolFilter, setSymbolFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<OrderStatus | ''>('');
  const [roleFilter, setRoleFilter] = useState<OrderRole | ''>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Modal & Drawer
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const offset = (page - 1) * limit;

  // Build URL with all filters
  let url = `/api/v3/orders?limit=${limit}&offset=${offset}`;
  if (symbolFilter) url += `&symbol=${symbolFilter}`;
  if (statusFilter) url += `&status=${statusFilter}`;
  if (roleFilter) url += `&order_role=${roleFilter}`;

  const { data, error, mutate } = useApi<{ items: OrderResponse[]; total: number }>(url);

  const isLoading = !data && !error;
  const orders = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit);

  // Clear all filters
  const clearFilters = () => {
    setSymbolFilter('');
    setStatusFilter('');
    setRoleFilter('');
    setStartDate('');
    setEndDate('');
    setPage(1);
  };

  // Handle order click
  const handleOrderClick = useCallback((orderId: string) => {
    setSelectedOrderId(orderId);
    setIsDrawerOpen(true);
  }, []);

  // Handle cancel order
  const handleCancelOrder = useCallback(async (orderId: string, symbol: string) => {
    try {
      await cancelOrder(orderId, symbol);
      await mutate();
    } catch (error) {
      console.error('Failed to cancel order:', error);
      alert('取消订单失败，请重试');
      throw error;
    }
  }, [mutate]);

  // Handle create order success
  const handleCreateOrderSuccess = useCallback(async () => {
    await mutate();
  }, [mutate]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">订单管理</h1>
          <p className="text-sm text-gray-500 mt-1">查看和管理所有交易订单</p>
        </div>

        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-apple-blue text-white rounded-lg font-medium hover:bg-blue-600 transition-colors"
        >
          <Plus className="w-4 h-4" />
          创建订单
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
          <Filter className="w-3 h-3" />
          筛选
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Symbol Filter */}
          <select
            value={symbolFilter}
            onChange={(e) => { setSymbolFilter(e.target.value); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            {symbolOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value as OrderStatus | ''); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Role Filter */}
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value as OrderRole | ''); setPage(1); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            {roleOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Date Range */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="开始日期"
            />
            <span className="text-gray-400 text-xs">-</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setPage(1); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="结束日期"
            />
          </div>

          {/* Clear Filters */}
          {(symbolFilter || statusFilter || roleFilter || startDate || endDate) && (
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

      {/* Orders Table */}
      <OrdersTable
        orders={orders}
        isLoading={isLoading}
        onOrderClick={handleOrderClick}
      />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1 || isLoading}
            className="p-2 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="text-sm text-gray-600">
            第 <span className="font-medium">{page}</span> 页 / 共 <span className="font-medium">{totalPages}</span> 页
          </span>

          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || isLoading}
            className="p-2 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Order Details Drawer */}
      {selectedOrderId && (
        <OrderDetailsDrawer
          order={orders.find((o) => o.order_id === selectedOrderId) || null}
          isOpen={isDrawerOpen}
          onClose={() => {
            setIsDrawerOpen(false);
            setTimeout(() => setSelectedOrderId(null), 300);
          }}
          onCancelOrder={handleCancelOrder}
        />
      )}

      {/* Create Order Modal */}
      <CreateOrderModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={handleCreateOrderSuccess}
      />
    </div>
  );
}
