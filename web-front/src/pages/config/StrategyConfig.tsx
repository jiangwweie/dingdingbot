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
import { Button, Input, Select, Empty, Spin, Alert, Space, Popconfirm, message, Modal } from 'antd';
import { PlusOutlined, SearchOutlined, ReloadOutlined, ExperimentOutlined, UploadOutlined } from '@ant-design/icons';
import { configApi, type Strategy, type CreateStrategyRequest, type UpdateStrategyRequest } from '../../api/config';
import { StrategyCard } from '../../components/strategy/StrategyCard';
import { StrategyEditorDrawer } from '../../components/strategy/StrategyEditor';
import TraceTreeViewer from '../../components/TraceTreeViewer';
import type { TraceNode, PreviewResponse } from '../../lib/api';
import { cn } from '../../lib/utils';

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

  // Dry Run 预览状态
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewingStrategy, setPreviewingStrategy] = useState<Strategy | null>(null);
  const [previewStatus, setPreviewStatus] = useState<'idle' | 'previewing' | 'previewed' | 'error'>('idle');
  const [previewResult, setPreviewResult] = useState<PreviewResponse | null>(null);
  const [previewSymbol, setPreviewSymbol] = useState('BTC/USDT:USDT');
  const [previewTimeframe, setPreviewTimeframe] = useState('15m');
  const [previewError, setPreviewError] = useState<string | null>(null);

  // 应用到实盘状态
  const [applyModalOpen, setApplyModalOpen] = useState(false);
  const [applyingStrategy, setApplyingStrategy] = useState<Strategy | null>(null);
  const [applying, setApplying] = useState(false);

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

  // 编辑器加载中状态
  const [editLoading, setEditLoading] = useState(false);

  // 处理编辑策略 — 先调用详情接口获取完整数据
  const handleEdit = useCallback(async (strategy: Strategy) => {
    setEditLoading(true);
    try {
      const response = await configApi.getStrategy(strategy.id);
      setEditingStrategy(response.data);
      setEditorOpen(true);
    } catch (error: any) {
      console.error('加载策略详情失败:', error);
      const errorMsg = error.response?.data?.detail || error.message || '加载失败';
      message.error('加载策略详情失败：' + errorMsg);
    } finally {
      setEditLoading(false);
    }
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

  // 处理 Dry Run 预览
  const handlePreview = useCallback((strategy: Strategy) => {
    setPreviewingStrategy(strategy);
    setPreviewModalOpen(true);
    setPreviewStatus('idle');
    setPreviewResult(null);
    setPreviewError(null);
  }, []);

  // 执行 Dry Run 预览
  const executePreview = useCallback(async () => {
    if (!previewingStrategy) return;

    setPreviewStatus('previewing');
    setPreviewResult(null);
    setPreviewError(null);

    try {
      // 构建 logic tree
      const logicTree = {
        gate: 'AND' as const,
        children: [
          {
            type: 'trigger' as const,
            id: previewingStrategy.trigger_config.type,
            config: {
              type: previewingStrategy.trigger_config.type,
              params: previewingStrategy.trigger_config.params,
            },
          },
          ...previewingStrategy.filter_configs.map((f: { type: string; enabled: boolean; params: Record<string, any> }) => ({
            type: 'filter' as const,
            id: f.type,
            config: f,
          })),
        ],
      };

      const result = await configApi.previewStrategy({
        logic_tree: logicTree,
        symbol: previewSymbol,
        timeframe: previewTimeframe,
      });
      setPreviewResult(result);
      setPreviewStatus('previewed');
    } catch (err: any) {
      console.error('Preview failed:', err);
      setPreviewError(err.info?.detail || err.message || '预览失败，请重试');
      setPreviewStatus('error');
    }
  }, [previewingStrategy, previewSymbol, previewTimeframe]);

  // 处理应用到实盘
  const handleApply = useCallback((strategy: Strategy) => {
    setApplyingStrategy(strategy);
    setApplyModalOpen(true);
  }, []);

  // 执行应用到实盘
  const executeApply = useCallback(async () => {
    if (!applyingStrategy) return;

    setApplying(true);
    try {
      await configApi.applyStrategy(applyingStrategy.id);
      message.success(`策略 "${applyingStrategy.name}" 已应用到实盘引擎`);
      setApplyModalOpen(false);
      setApplyingStrategy(null);
      // 刷新策略列表
      loadStrategies();
    } catch (err: any) {
      console.error('Apply strategy failed:', err);
      const errorMsg = err.info?.detail || err.message || '应用策略失败，请重试';
      message.error('应用策略失败：' + errorMsg);
    } finally {
      setApplying(false);
    }
  }, [applyingStrategy, loadStrategies]);

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
              onPreview={handlePreview}
              onApply={handleApply}
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

      {/* Dry Run 预览 Modal */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <ExperimentOutlined className="text-orange-600" />
            <span>Dry Run 预览 - {previewingStrategy?.name}</span>
          </div>
        }
        open={previewModalOpen}
        onCancel={() => {
          setPreviewModalOpen(false);
          setPreviewingStrategy(null);
          setPreviewResult(null);
          setPreviewStatus('idle');
          setPreviewError(null);
        }}
        footer={null}
        width={720}
        destroyOnClose
      >
        {/* 预览控制区 */}
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <label className="text-sm font-medium text-gray-700">币种:</label>
            <Select
              value={previewSymbol}
              onChange={setPreviewSymbol}
              style={{ width: 180 }}
              options={[
                { value: 'BTC/USDT:USDT', label: 'BTC/USDT' },
                { value: 'ETH/USDT:USDT', label: 'ETH/USDT' },
                { value: 'SOL/USDT:USDT', label: 'SOL/USDT' },
                { value: 'BNB/USDT:USDT', label: 'BNB/USDT' },
              ]}
            />

            <label className="text-sm font-medium text-gray-700">周期:</label>
            <Select
              value={previewTimeframe}
              onChange={setPreviewTimeframe}
              style={{ width: 100 }}
              options={[
                { value: '5m', label: '5m' },
                { value: '15m', label: '15m' },
                { value: '1h', label: '1h' },
                { value: '4h', label: '4h' },
                { value: '1d', label: '1d' },
              ]}
            />

            <Button
              type="primary"
              icon={<ExperimentOutlined />}
              onClick={executePreview}
              loading={previewStatus === 'previewing'}
              disabled={previewStatus === 'previewing'}
            >
              {previewStatus === 'previewing' ? '预览中...' : previewStatus === 'previewed' ? '重新测试' : '立即测试'}
            </Button>
          </div>

          {/* 提示信息 */}
          {previewStatus === 'previewed' && (
            <Alert
              type="info"
              showIcon
              message="关于 Dry Run 预览"
              description="仅评估当前最新一根 K 线，如果未检测到信号属于正常现象。Pinbar 等形态在市场中较为稀缺，通常需要等待合适的 K 线形态出现。"
              className="mb-2"
            />
          )}

          {/* 错误提示 */}
          {previewError && (
            <Alert
              type="error"
              showIcon
              message="预览失败"
              description={previewError}
              className="mb-2"
            />
          )}

          {/* 预览结果 */}
          {previewStatus === 'previewed' && previewResult && (
            <div className="space-y-4">
              {/* 结果状态 */}
              <div className={cn(
                "rounded-lg p-3 border",
                previewResult.signal_fired
                  ? "bg-green-50 border-green-200"
                  : "bg-gray-50 border-gray-200"
              )}>
                <p className={cn(
                  "text-sm font-medium",
                  previewResult.signal_fired ? "text-green-800" : "text-gray-600"
                )}>
                  {previewResult.signal_fired
                    ? "当前 K 线满足策略条件，信号触发！"
                    : "当前 K 线不满足策略条件，未检测到信号"}
                </p>
                {!previewResult.signal_fired && (
                  <p className="text-xs text-gray-500 mt-1">
                    原因：{previewResult.trace_tree?.reason || '未知'}
                  </p>
                )}
              </div>

              {/* 评估报告 */}
              {previewResult.evaluation_summary && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">评估报告</h4>
                  <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-700 whitespace-pre-wrap font-sans">
                    {previewResult.evaluation_summary}
                  </pre>
                </div>
              )}

              {/* Trace Tree */}
              <TraceTreeViewer
                traceTree={previewResult.trace_tree}
                signalFired={previewResult.signal_fired}
              />
            </div>
          )}

          {/* 空状态 */}
          {previewStatus === 'idle' && (
            <Empty description="选择币种和周期后，点击「立即测试」进行 Dry Run 预览" />
          )}
        </div>
      </Modal>

      {/* 应用到实盘确认 Modal */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <UploadOutlined className="text-cyan-600" />
            <span>确认应用到实盘</span>
          </div>
        }
        open={applyModalOpen}
        onCancel={() => {
          setApplyModalOpen(false);
          setApplyingStrategy(null);
        }}
        footer={null}
        width={480}
      >
        {applyingStrategy && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              确定要将策略 <span className="font-medium text-gray-900">"{applyingStrategy.name}"</span> 应用到实盘引擎吗？
            </p>
            <Alert
              type="warning"
              showIcon
              message="注意"
              description="此操作会将策略配置下发到实盘引擎，策略将立即对配置的币种和周期生效。"
            />
            <div className="flex justify-end gap-2">
              <Button
                onClick={() => {
                  setApplyModalOpen(false);
                  setApplyingStrategy(null);
                }}
                disabled={applying}
              >
                取消
              </Button>
              <Button
                type="primary"
                danger
                icon={<UploadOutlined />}
                onClick={executeApply}
                loading={applying}
                disabled={applying}
              >
                {applying ? '应用中...' : '确认应用'}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default StrategyConfigPage;
