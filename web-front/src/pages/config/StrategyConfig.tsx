/**
 * 策略配置页面
 *
 * 功能:
 * - 策略列表展示 (卡片式 + 搜索/筛选)
 * - 策略启用/禁用切换
 * - 抽屉式策略编辑器
 * - 自动保存机制 (防抖 1 秒)
 *
 * @route /config/strategies
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Input, Select, Empty, Spin, Alert, Space, Popconfirm, message } from 'antd';
import { PlusOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { configApi, type Strategy, type CreateStrategyRequest, type UpdateStrategyRequest } from '../../api/config';
import { StrategyCard } from '../../components/strategy/StrategyCard';
import { StrategyEditorDrawer } from '../../components/strategy/StrategyEditor';

// ============================================================
// Type Definitions
// ============================================================

interface FilterState {
  searchQuery: string;
  filterTimeframe: string | null;
  filterStatus: 'all' | 'active' | 'inactive' | null;
}

// ============================================================
// Options Constants
// ============================================================

const TIMEFRAME_OPTIONS = [
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
  { value: '1w', label: '1 周' },
];

// Simple Empty Image Component (must be defined before use)
const SimpleImage = () => (
  <svg
    width="64"
    height="64"
    viewBox="0 0 64 64"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <circle cx="32" cy="32" r="30" fill="#F5F5F5" />
    <path
      d="M32 18V32L42 42"
      stroke="#D9D9D9"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

// ============================================================
// Main Component
// ============================================================

const StrategyConfigPage: React.FC = () => {
  // 策略列表状态
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 编辑器状态
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null);
  const [saving, setSaving] = useState(false);

  // 筛选状态
  const [filters, setFilters] = useState<FilterState>({
    searchQuery: '',
    filterTimeframe: null,
    filterStatus: 'all',
  });

  // 加载策略列表
  const loadStrategies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await configApi.getStrategies();
      // 新 API (/api/v1/config/strategies) 直接返回数组
      const strategiesArray = response.data || [];
      setStrategies(strategiesArray);
    } catch (err: any) {
      console.error('加载策略列表失败:', err);
      const errorMsg = err.response?.data?.detail || err.message || '加载失败';
      setError(errorMsg);
      message.error('加载策略列表失败：' + errorMsg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  // 处理启用/禁用策略
  const handleToggleEnable = useCallback(async (id: string, enabled: boolean) => {
    const originalStrategies = [...strategies];
    try {
      // 乐观更新 UI
      setStrategies((prev) =>
        prev.map((s) => (s.id === id ? { ...s, is_active: enabled } : s))
      );

      await configApi.toggleStrategy(id, enabled);
      message.success(enabled ? '策略已启用' : '策略已禁用');
    } catch (err: any) {
      console.error('切换策略状态失败:', err);
      // 回滚
      setStrategies(originalStrategies);
      const errorMsg = err.response?.data?.detail || err.message || '操作失败';
      message.error('切换策略状态失败：' + errorMsg);
    }
  }, [strategies]);

  // 处理删除策略
  const handleDelete = useCallback(async (id: string) => {
    const originalStrategies = [...strategies];
    try {
      // 乐观删除 UI
      setStrategies((prev) => prev.filter((s) => s.id !== id));

      await configApi.deleteStrategy(id);
      message.success('策略已删除');
    } catch (err: any) {
      console.error('删除策略失败:', err);
      // 回滚
      setStrategies(originalStrategies);
      const errorMsg = err.response?.data?.detail || err.message || '删除失败';
      message.error('删除策略失败：' + errorMsg);
    }
  }, [strategies]);

  // 处理编辑策略
  const handleEdit = useCallback((strategy: Strategy) => {
    setEditingStrategy(strategy);
    setEditorOpen(true);
  }, []);

  // 处理创建策略
  const handleCreate = useCallback(() => {
    setEditingStrategy(null);
    setEditorOpen(true);
  }, []);

  // 处理复制策略
  const handleDuplicate = useCallback((strategy: Strategy) => {
    // 复制模式：创建一个新策略，数据为原策略的副本
    setEditingStrategy(null);
    // 在实际实现中，应该打开编辑器并填充副本数据
    message.info('复制功能开发中...');
  }, []);

  // 处理保存策略
  const handleSave = useCallback(async (data: CreateStrategyRequest | UpdateStrategyRequest) => {
    setSaving(true);
    try {
      if (editingStrategy) {
        // 更新策略
        await configApi.updateStrategy(editingStrategy.id, data as UpdateStrategyRequest);
        message.success('策略更新成功');
      } else {
        // 创建策略
        await configApi.createStrategy(data as CreateStrategyRequest);
        message.success('策略创建成功');
      }

      setEditorOpen(false);
      setEditingStrategy(null);
      loadStrategies();
    } catch (err: any) {
      console.error('策略提交失败:', err);
      const errorMsg = err.response?.data?.detail || err.message || '操作失败';
      message.error('操作失败：' + errorMsg);
    } finally {
      setSaving(false);
    }
  }, [editingStrategy, loadStrategies]);

  // 处理编辑器关闭
  const handleCloseEditor = useCallback(() => {
    setEditorOpen(false);
    setEditingStrategy(null);
  }, []);

  // 筛选后的策略列表
  const filteredStrategies = strategies.filter((strategy) => {
    // 搜索筛选
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      const matchesName = strategy.name.toLowerCase().includes(query);
      const matchesDesc = strategy.description?.toLowerCase().includes(query);
      if (!matchesName && !matchesDesc) return false;
    }

    // 周期筛选
    if (filters.filterTimeframe) {
      if (!strategy.timeframes?.includes(filters.filterTimeframe)) return false;
    }

    // 状态筛选
    if (filters.filterStatus === 'active' && !strategy.is_active) return false;
    if (filters.filterStatus === 'inactive' && strategy.is_active) return false;

    return true;
  });

  return (
    <div className="strategy-config-page">
      {/* 页面头部 */}
      <div className="page-header mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">策略配置</h1>
            <p className="text-sm text-gray-500 mt-1">
              配置策略参数、触发器、过滤器和风控设置
            </p>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreate}
            size="large"
          >
            创建策略
          </Button>
        </div>

        {/* 筛选工具栏 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <Space size="middle" wrap>
            <Input
              placeholder="搜索策略名称或描述..."
              prefix={<SearchOutlined />}
              value={filters.searchQuery}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, searchQuery: e.target.value }))
              }
              style={{ width: 240 }}
              allowClear
            />

            <Select
              placeholder="全部周期"
              value={filters.filterTimeframe || undefined}
              onChange={(value) =>
                setFilters((prev) => ({ ...prev, filterTimeframe: value || null }))
              }
              style={{ width: 120 }}
              allowClear
            >
              {TIMEFRAME_OPTIONS.map((opt) => (
                <Select.Option key={opt.value} value={opt.value}>
                  {opt.label}
                </Select.Option>
              ))}
            </Select>

            <Select
              placeholder="全部状态"
              value={filters.filterStatus || 'all'}
              onChange={(value) =>
                setFilters((prev) => ({ ...prev, filterStatus: value || 'all' }))
              }
              style={{ width: 120 }}
            >
              <Select.Option value="all">全部状态</Select.Option>
              <Select.Option value="active">已启用</Select.Option>
              <Select.Option value="inactive">已禁用</Select.Option>
            </Select>

            <Button icon={<ReloadOutlined />} onClick={loadStrategies} loading={loading}>
              刷新
            </Button>
          </Space>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={error}
          action={
            <Button type="primary" size="small" onClick={loadStrategies}>
              重新加载
            </Button>
          }
          className="mb-4"
        />
      )}

      {/* 策略列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Spin size="large" tip="加载策略列表..." />
        </div>
      ) : filteredStrategies.length === 0 ? (
        <Empty
          description={
            strategies.length === 0
              ? '暂无策略，点击右上角"创建策略"开始配置'
              : '没有符合条件的策略'
          }
          image={<SimpleImage />}
        >
          {strategies.length === 0 && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              创建第一个策略
            </Button>
          )}
        </Empty>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredStrategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onEdit={handleEdit}
              onToggleEnable={handleToggleEnable}
              onDelete={handleDelete}
              onDuplicate={handleDuplicate}
            />
          ))}
        </div>
      )}

      {/* 策略编辑器抽屉 */}
      <StrategyEditorDrawer
        visible={editorOpen}
        strategy={editingStrategy}
        onClose={handleCloseEditor}
        onSave={handleSave}
        loading={saving}
      />
    </div>
  );
};

export default StrategyConfigPage;
