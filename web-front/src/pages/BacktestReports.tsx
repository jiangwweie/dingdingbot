/**
 * Backtest Reports Page
 *
 * 回测报告列表页面 - 支持筛选、排序、分页
 */
import { useState, useCallback, useEffect } from 'react';
import { History, TrendingUp, AlertCircle, ExternalLink, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  fetchBacktestReports,
  deleteBacktestReport,
  type ListBacktestReportsRequest,
  type BacktestReportSummary,
} from '../lib/api';
import { BacktestReportsTable } from '../components/v3/backtest/BacktestReportsTable';
import { BacktestReportsFilters, type FilterValues } from '../components/v3/backtest/BacktestReportsFilters';
import { BacktestReportsPagination } from '../components/v3/backtest/BacktestReportsPagination';

type SortField = 'total_return' | 'win_rate' | 'created_at';
type SortOrder = 'asc' | 'desc';

export default function BacktestReports() {
  // Data state
  const [reports, setReports] = useState<BacktestReportSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Filter state
  const [filters, setFilters] = useState<FilterValues>({});

  // Sort state
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Fetch reports
  const fetchReports = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const params: ListBacktestReportsRequest = {
        strategyId: filters.strategyId,
        symbol: filters.symbol,
        startDate: filters.startDate,
        endDate: filters.endDate,
        page: currentPage,
        pageSize,
        sortBy: sortField,
        sortOrder,
      };

      const data = await fetchBacktestReports(params);
      setReports(data.reports);
      setTotal(data.total);
    } catch (err: any) {
      console.error('Failed to fetch backtest reports:', err);
      setError(err.info?.detail || err.message || '加载回测报告失败');
    } finally {
      setIsLoading(false);
    }
  }, [filters, currentPage, pageSize, sortField, sortOrder]);

  // Initial fetch
  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  // Handle filter submit
  const handleFilterSubmit = useCallback((newFilters: FilterValues) => {
    setFilters(newFilters);
    setCurrentPage(1); // Reset to first page when filters change
  }, []);

  // Handle filter reset
  const handleFilterReset = useCallback(() => {
    setFilters({});
    setCurrentPage(1);
  }, []);

  // Handle page change
  const handlePageChange = useCallback((newPage: number) => {
    setCurrentPage(newPage);
  }, []);

  // Handle page size change
  const handlePageSizeChange = useCallback((newPageSize: number) => {
    setPageSize(newPageSize);
    setCurrentPage(1); // Reset to first page when page size changes
  }, []);

  // Handle sort (click on table header - future enhancement)
  const handleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      // Toggle order
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      // Change sort field
      setSortField(field);
      setSortOrder('desc');
    }
  }, [sortField, sortOrder]);

  // Handle view details
  const handleViewDetails = useCallback(async (reportId: string) => {
    try {
      const { fetchBacktestReportDetail } = await import('../lib/api');
      const report = await fetchBacktestReportDetail(reportId);
      // Show report details in an alert for now (can be enhanced with a modal)
      alert(`回测报告详情：${reportId}\n\n策略：${report.strategy_name || 'N/A'}\n总收益：${report.total_return}%\n夏普比率：${report.sharpe_ratio || 'N/A'}\n最大回撤：${report.max_drawdown}%\n胜率：${report.win_rate}%`);
    } catch (err: any) {
      console.error('Failed to fetch report details:', err);
      alert(`获取报告详情失败：${err.message || '未知错误'}`);
    }
  }, []);

  // Handle delete
  const handleDelete = useCallback(async (reportId: string) => {
    if (!confirm(`确定要删除回测报告 ${reportId} 吗？\n\n此操作不可恢复。`)) {
      return;
    }

    setDeletingId(reportId);
    try {
      await deleteBacktestReport(reportId);
      // Refresh the list
      fetchReports();
    } catch (err: any) {
      console.error('Failed to delete backtest report:', err);
      alert(`删除失败：${err.message || '未知错误'}`);
    } finally {
      setDeletingId(null);
    }
  }, [fetchReports]);

  // Calculate total pages
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">回测报告</h1>
          <p className="text-sm text-gray-500 mt-1">
            查看和管理历史回测报告，支持筛选、排序和分页
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="/backtest"
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors text-sm"
          >
            <TrendingUp className="w-4 h-4" />
            执行回测
          </a>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-blue-900">回测报告说明</h3>
          <div className="mt-2 text-sm text-blue-700 space-y-1">
            <p>• 每次执行 PMS 回测后，报告会自动保存到此列表</p>
            <p>• 支持按策略、交易对、时间范围筛选</p>
            <p>• 点击表头可以按收益率、胜率、创建时间排序</p>
            <p>• 删除操作不可恢复，请谨慎操作</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <BacktestReportsFilters
        onSubmit={handleFilterSubmit}
        onReset={handleFilterReset}
        defaultFilters={filters}
      />

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-red-900">加载失败</p>
            <p className="mt-1 text-sm text-red-700">{error}</p>
            <button
              onClick={fetchReports}
              className="mt-2 text-sm text-red-600 hover:text-red-800 font-medium"
            >
              重新加载
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <BacktestReportsTable
        reports={reports}
        onViewDetails={handleViewDetails}
        onDelete={handleDelete}
        isLoading={isLoading}
      />

      {/* Pagination */}
      {total > 0 && (
        <BacktestReportsPagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={total}
          pageSize={pageSize}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      )}
    </div>
  );
}
