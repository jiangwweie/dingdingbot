import { useState, useCallback, useMemo, useEffect } from 'react';
import { Plus, Filter, X, ChevronLeft, ChevronRight } from 'lucide-react';
import { OrderTreeNode, OrderStatus, OrderRole, OrderBatchDeleteRequest } from '../types/order';
import { OrderChainTreeTable } from '../components/v3/OrderChainTreeTable';
import { DeleteChainConfirmModal } from '../components/v3/DeleteChainConfirmModal';
import { CreateOrderModal } from '../components/v3/CreateOrderModal';
import { OrderDetailsDrawer } from '../components/v3/OrderDetailsDrawer';
import { fetchOrderTree, deleteOrderChain, cancelOrder } from '../lib/api';
import { useApi } from '../lib/api';

const symbolOptions = [
  { value: '', label: '全部币种' },
  { value: 'BTC/USDT:USDT', label: 'BTC' },
  { value: 'ETH/USDT:USDT', label: 'ETH' },
  { value: 'SOL/USDT:USDT', label: 'SOL' },
  { value: 'BNB/USDT:USDT', label: 'BNB' },
];

const timeframeOptions = [
  { value: '', label: '全部周期' },
  { value: '5m', label: '5 分钟' },
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
];

export default function Orders() {
  // Filters
  const [symbolFilter, setSymbolFilter] = useState('');
  const [timeframeFilter, setTimeframeFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Tree data state
  const [treeData, setTreeData] = useState<OrderTreeNode[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalCount, setTotalCount] = useState(0);

  // Modal & Drawer state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Delete confirm modal state
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [pendingDeleteOrderIds, setPendingDeleteOrderIds] = useState<string[]>([]);

  // Build URL for filter count display
  const filterCount = [symbolFilter, timeframeFilter, startDate, endDate].filter(Boolean).length;

  // Load order tree data
  const loadOrderTree = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
      };
      if (symbolFilter) params.symbol = symbolFilter;
      if (timeframeFilter) params.timeframe = timeframeFilter;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      const response = await fetchOrderTree(params as any);
      setTreeData(response.items || []);
      setTotalCount(response.total_count || 0);

      // Auto-expand all root nodes on load
      const rootIds = (response.items || []).map((item: OrderTreeNode) => item.order.order_id);
      setExpandedRowKeys(rootIds);
    } catch (error) {
      console.error('Failed to load order tree:', error);
      setTreeData([]);
      setTotalCount(0);
    } finally {
      setIsLoading(false);
    }
  }, [symbolFilter, timeframeFilter, startDate, endDate, page, pageSize]);

  // Reset page to 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [symbolFilter, timeframeFilter, startDate, endDate]);

  // Load data on mount and when page/pageSize/filters change
  useEffect(() => {
    const timer = setTimeout(() => {
      loadOrderTree();
    }, 300);
    return () => clearTimeout(timer);
  }, [loadOrderTree]);

  // Clear all filters
  const clearFilters = () => {
    setSymbolFilter('');
    setTimeframeFilter('');
    setStartDate('');
    setEndDate('');
    setExpandedRowKeys([]);
    setSelectedRowKeys([]);
    setPage(1); // Reset to first page when clearing filters
  };

  // Handle expand/collapse
  const handleExpand = useCallback((keys: string[]) => {
    setExpandedRowKeys(keys);
  }, []);

  // Handle row selection
  const handleSelectChange = useCallback((keys: string[]) => {
    setSelectedRowKeys(keys);
  }, []);

  // Handle cancel order
  const handleCancelOrder = useCallback(async (orderId: string, symbol: string) => {
    try {
      await cancelOrder(orderId, symbol);
      await loadOrderTree();
    } catch (error) {
      console.error('Failed to cancel order:', error);
      alert('取消订单失败，请重试');
      throw error;
    }
  }, [loadOrderTree]);

  // Handle delete chain click
  const handleDeleteChainClick = useCallback((orderIds: string[]) => {
    setPendingDeleteOrderIds(orderIds);
    setIsDeleteModalOpen(true);
  }, []);

  // Handle delete confirm
  const handleDeleteConfirm = useCallback(async () => {
    try {
      const request: OrderBatchDeleteRequest = {
        order_ids: pendingDeleteOrderIds,
        cancel_on_exchange: true,
      };

      await deleteOrderChain(request);
      setIsDeleteModalOpen(false);
      setPendingDeleteOrderIds([]);
      setSelectedRowKeys([]);
      await loadOrderTree();
    } catch (error) {
      console.error('Failed to delete order chain:', error);
      alert('删除订单链失败，请重试');
      throw error;
    }
  }, [pendingDeleteOrderIds, loadOrderTree]);

  // Handle delete cancel
  const handleDeleteCancel = useCallback(() => {
    setIsDeleteModalOpen(false);
    setPendingDeleteOrderIds([]);
  }, []);

  // Handle create order success
  const handleCreateOrderSuccess = useCallback(async () => {
    await loadOrderTree();
  }, [loadOrderTree]);

  // Handle order click for details drawer
  const handleOrderClick = useCallback((orderId: string) => {
    // Find the order from tree data
    const findOrder = (nodes: OrderTreeNode[]): OrderTreeNode | null => {
      for (const node of nodes) {
        if (node.order.order_id === orderId) {
          return node;
        }
        const found = findOrder(node.children);
        if (found) return found;
      }
      return null;
    };

    const node = findOrder(treeData);
    if (node) {
      setSelectedOrderId(orderId);
      setIsDrawerOpen(true);
    }
  }, [treeData]);

  // Get flat order list for drawer
  const selectedOrder = useMemo(() => {
    if (!selectedOrderId) return null;

    const findOrder = (nodes: OrderTreeNode[]): OrderTreeNode | null => {
      for (const node of nodes) {
        if (node.order.order_id === selectedOrderId) {
          return node;
        }
        const found = findOrder(node.children);
        if (found) return found;
      }
      return null;
    };

    const node = findOrder(treeData);
    return node ? node.order : null;
  }, [selectedOrderId, treeData]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">订单管理</h1>
          <p className="text-sm text-gray-500 mt-1">
            查看和管理所有交易订单链
            {filterCount > 0 && (
              <span className="ml-2 text-xs text-blue-600">（{filterCount} 个筛选条件生效）</span>
            )}
          </p>
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
            onChange={(e) => { setSymbolFilter(e.target.value); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            {symbolOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Timeframe Filter */}
          <select
            value={timeframeFilter}
            onChange={(e) => { setTimeframeFilter(e.target.value); }}
            className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
          >
            {timeframeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Date Range */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="开始日期"
            />
            <span className="text-gray-400 text-xs">-</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
              placeholder="结束日期"
            />
          </div>

          {/* Clear Filters */}
          {(symbolFilter || timeframeFilter || startDate || endDate) && (
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

      {/* Order Tree Table */}
      <OrderChainTreeTable
        data={treeData}
        expandedRowKeys={expandedRowKeys}
        selectedRowKeys={selectedRowKeys}
        onExpand={handleExpand}
        onSelectChange={handleSelectChange}
        onCancelOrder={handleCancelOrder}
        onDeleteChain={handleDeleteChainClick}
        isLoading={isLoading}
      />

      {/* Pagination */}
      {totalCount > 0 && (
        <div className="flex items-center justify-between bg-white rounded-xl shadow-sm border border-gray-100 px-4 py-3">
          <div className="text-sm text-gray-500">
            第 {page} / {Math.ceil(totalCount / pageSize)} 页，共 {totalCount} 条
          </div>
          <div className="flex items-center gap-2">
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1); // Reset to first page when page size changes
              }}
              className="bg-gray-50 border-none text-sm rounded-lg focus:ring-0 py-1.5 px-3 outline-none"
            >
              <option value={20}>20 条/页</option>
              <option value={50}>50 条/页</option>
              <option value={100}>100 条/页</option>
              <option value={200}>200 条/页</option>
            </select>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(Math.ceil(totalCount / pageSize), p + 1))}
              disabled={page >= Math.ceil(totalCount / pageSize)}
              className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Order Details Drawer */}
      {selectedOrder && (
        <OrderDetailsDrawer
          order={selectedOrder}
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

      {/* Delete Chain Confirm Modal */}
      <DeleteChainConfirmModal
        selectedOrderIds={pendingDeleteOrderIds}
        treeData={treeData}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
        isOpen={isDeleteModalOpen}
      />
    </div>
  );
}
