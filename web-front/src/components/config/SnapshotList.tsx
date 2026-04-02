import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Search, Filter, Clock, User, CheckCircle } from 'lucide-react';
import { fetchSnapshots, type ConfigSnapshotListItem, type SnapshotQueryParams } from '../../lib/api';
import { cn } from '../../lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface SnapshotListProps {
  onSnapshotSelect: (snapshot: ConfigSnapshotListItem) => void;
  onRefresh: () => void;
}

export default function SnapshotList({ onSnapshotSelect, onRefresh }: SnapshotListProps) {
  const [snapshots, setSnapshots] = useState<ConfigSnapshotListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterActive, setFilterActive] = useState<boolean | undefined>(undefined);

  // Pagination state
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  const fetchSnapshotsData = async () => {
    setLoading(true);
    setError(null);

    try {
      const params: SnapshotQueryParams = {
        limit,
        offset,
      };
      if (filterActive !== undefined) {
        params.is_active = filterActive;
      }

      const response = await fetchSnapshots(params);
      setSnapshots(response.data);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || '获取快照列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshotsData();
  }, [offset, filterActive]);

  const totalPages = Math.ceil(total / limit);

  const handlePreviousPage = () => {
    if (currentPage > 1) {
      setCurrentPage((prev) => prev - 1);
      setOffset((prev) => prev - limit);
    }
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage((prev) => prev + 1);
      setOffset((prev) => prev + limit);
    }
  };

  const filteredSnapshots = searchTerm
    ? snapshots.filter(
        (s) =>
          s.version.toLowerCase().includes(searchTerm.toLowerCase()) ||
          s.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
          s.created_by.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : snapshots;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex justify-between items-center">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">快照列表</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            共 {total} 条记录
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="搜索..."
              className="pl-9 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg outline-none focus:border-black transition-colors w-48"
            />
          </div>
          {/* Filter */}
          <button
            onClick={() => setFilterActive(filterActive === undefined ? true : filterActive === true ? false : undefined)}
            className={cn(
              'inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border transition-colors',
              filterActive !== undefined
                ? 'bg-black text-white border-black'
                : 'bg-white text-gray-700 border-gray-200 hover:border-gray-300'
            )}
          >
            <Filter className="w-4 h-4" />
            {filterActive === undefined ? '筛选' : filterActive ? '当前快照' : '历史快照'}
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="p-8 text-center text-gray-400">
          <div className="w-8 h-8 border-2 border-gray-200 border-t-black rounded-full animate-spin mx-auto mb-2" />
          加载中...
        </div>
      ) : error ? (
        <div className="p-8 text-center text-red-500">
          <p>{error}</p>
          <button
            onClick={fetchSnapshotsData}
            className="mt-3 px-4 py-2 bg-black text-white rounded-lg text-sm font-medium hover:bg-gray-800"
          >
            重试
          </button>
        </div>
      ) : filteredSnapshots.length === 0 ? (
        <div className="p-8 text-center text-gray-400">
          <Clock className="w-12 h-12 mx-auto mb-3 opacity-20" />
          <p>暂无快照记录</p>
        </div>
      ) : (
        <>
          <div className="divide-y divide-gray-100">
            {filteredSnapshots.map((snapshot) => (
              <div
                key={snapshot.id}
                onClick={() => onSnapshotSelect(snapshot)}
                className="p-4 hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-sm font-semibold text-gray-900">
                        {snapshot.version}
                      </span>
                      {snapshot.is_active && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium">
                          <CheckCircle className="w-3 h-3" />
                          当前生效
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 truncate">{snapshot.description || '无描述'}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {snapshot.created_by}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDistanceToNow(new Date(snapshot.created_at), {
                          addSuffix: true,
                          locale: zhCN,
                        })}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-gray-300" />
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="p-4 border-t border-gray-100 flex justify-center items-center gap-2">
              <button
                onClick={handlePreviousPage}
                disabled={currentPage === 1}
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-gray-600">
                第 {currentPage} 页，共 {totalPages} 页
              </span>
              <button
                onClick={handleNextPage}
                disabled={currentPage === totalPages}
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
