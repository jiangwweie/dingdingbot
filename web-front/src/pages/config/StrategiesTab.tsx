import React, { useState, useEffect } from 'react';
import { Button, Table, Space, Tag, Popconfirm, message, Switch } from 'antd';
import { Plus, Edit, Delete, Copy } from 'lucide-react';
import type { ColumnsType } from 'antd/es/table';
import { configApi, type Strategy, type CreateStrategyRequest, type UpdateStrategyRequest } from '../../api/config';
import { StrategyForm } from './StrategyForm';
import { AdvancedStrategyForm } from './AdvancedStrategyForm';
import './StrategiesTab.css';

// 前端展示用的简化接口（从完整 Strategy 派生）
interface StrategyDisplay extends Strategy {
  trigger_type: string;
  filter_count: number;
}

interface StrategyFormData {
  name: string;
  description?: string;
  trigger_type: string;
  symbols: string[];
  timeframes: string[];
}

const TRIGGER_OPTIONS = [
  { value: 'pinbar', label: 'Pinbar 形态' },
  { value: 'engulfing', label: '吞没形态' },
  { value: 'doji', label: '十字星' },
  { value: 'hammer', label: '锤头线' },
];

const SYMBOL_OPTIONS = [
  { value: 'BTC/USDT:USDT', label: 'BTC/USDT' },
  { value: 'ETH/USDT:USDT', label: 'ETH/USDT' },
  { value: 'SOL/USDT:USDT', label: 'SOL/USDT' },
  { value: 'BNB/USDT:USDT', label: 'BNB/USDT' },
];

const TIMEFRAME_OPTIONS = [
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
  { value: '1w', label: '1 周' },
];

export const StrategiesTab: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyDisplay[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [advancedModalVisible, setAdvancedModalVisible] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 加载策略列表
  const loadStrategies = async () => {
    setLoading(true);
    try {
      const response = await configApi.getStrategies();
      // 将后端 Strategy 转换为前端展示用的 StrategyDisplay
      const displayStrategies: StrategyDisplay[] = response.data.map((s) => ({
        ...s,
        trigger_type: s.trigger_config?.type || 'unknown',
        filter_count: s.filter_configs?.length || 0,
      }));
      setStrategies(displayStrategies);
    } catch (error: any) {
      console.error('加载策略列表失败:', error);
      const errorMsg = error.response?.data?.detail || error.message || '加载失败';
      message.error('加载策略列表失败：' + errorMsg);
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStrategies();
  }, []);

  // 处理启用/禁用策略
  const handleToggle = async (id: string, enabled: boolean) => {
    const originalStrategies = [...strategies];
    try {
      // 乐观更新 UI
      setStrategies((prev) =>
        prev.map((s) => (s.id === id ? { ...s, is_active: enabled } : s))
      );

      await configApi.toggleStrategy(id, enabled);
      message.success(enabled ? '策略已启用' : '策略已禁用');
    } catch (error: any) {
      console.error('切换策略状态失败:', error);
      // 回滚
      setStrategies(originalStrategies);
      const errorMsg = error.response?.data?.detail || error.message || '操作失败';
      message.error('切换策略状态失败：' + errorMsg);
    }
  };

  // 处理删除策略
  const handleDelete = async (id: string) => {
    const originalStrategies = [...strategies];
    try {
      // 乐观删除 UI
      setStrategies((prev) => prev.filter((s) => s.id !== id));

      await configApi.deleteStrategy(id);
      message.success('策略已删除');
    } catch (error: any) {
      console.error('删除策略失败:', error);
      // 回滚
      setStrategies(originalStrategies);
      const errorMsg = error.response?.data?.detail || error.message || '删除失败';
      message.error('删除策略失败：' + errorMsg);
    }
  };

  // 处理编辑策略 - 高级编辑模式
  const handleEdit = (record: StrategyDisplay) => {
    setEditingStrategy(record);
    setAdvancedModalVisible(true);
  };

  // 处理创建策略 - 高级创建模式
  const handleCreate = () => {
    setEditingStrategy(null);
    setAdvancedModalVisible(true);
  };

  // 处理表单提交
  const handleSubmit = async (values: CreateStrategyRequest | UpdateStrategyRequest) => {
    setSubmitting(true);
    try {
      if (editingStrategy) {
        // 更新策略
        await configApi.updateStrategy(editingStrategy.id, values as UpdateStrategyRequest);
        message.success('策略更新成功');
      } else {
        // 创建策略
        await configApi.createStrategy(values as CreateStrategyRequest);
        message.success('策略创建成功');
      }

      setAdvancedModalVisible(false);
      setEditingStrategy(null);
      loadStrategies();
    } catch (error: any) {
      console.error('策略提交失败:', error);
      const errorMsg = error.response?.data?.detail || error.message || '操作失败';
      message.error('操作失败：' + errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  // 处理复制策略
  const handleDuplicate = (record: StrategyDisplay) => {
    setEditingStrategy(null);
    // 复制模式：在表单中填充副本数据（由 AdvancedStrategyForm 内部处理）
    message.info('复制功能开发中...');
  };

  const columns: ColumnsType<StrategyDisplay> = [
    {
      title: '策略名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, record: StrategyDisplay) => (
        <div>
          <div className="strategy-name">{name}</div>
          {record.description && (
            <div className="strategy-description">{record.description}</div>
          )}
        </div>
      ),
    },
    {
      title: '触发器',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      width: 120,
      render: (triggerType: string) => {
        const trigger = TRIGGER_OPTIONS.find((t) => t.value === triggerType);
        return <Tag color="blue">{trigger?.label || triggerType}</Tag>;
      },
    },
    {
      title: '过滤器数',
      dataIndex: 'filter_count',
      key: 'filter_count',
      width: 100,
      align: 'center',
      render: (count: number) => <Tag color="purple">{count} 个</Tag>,
    },
    {
      title: '币种',
      dataIndex: 'symbols',
      key: 'symbols',
      width: 200,
      render: (symbols: string[]) => (
        <div className="symbols-tags">
          {symbols.slice(0, 3).map((symbol) => (
            <Tag key={symbol} color="gray">
              {symbol.split('/')[0]}
            </Tag>
          ))}
          {symbols.length > 3 && <Tag>+{symbols.length - 3}</Tag>}
        </div>
      ),
    },
    {
      title: '周期',
      dataIndex: 'timeframes',
      key: 'timeframes',
      width: 150,
      render: (timeframes: string[]) => (
        <div className="timeframes-tags">
          {timeframes.map((tf) => (
            <Tag key={tf} color="green">
              {tf}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      align: 'center',
      render: (isActive: boolean, record: StrategyDisplay) => (
        <Space size="small">
          <Tag color={isActive ? 'green' : 'default'}>
            {isActive ? '已启用' : '已禁用'}
          </Tag>
          <Switch
            checked={isActive}
            onChange={(checked) => handleToggle(record.id, checked)}
            size="small"
          />
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small" wrap>
          <Button
            type="primary"
            size="small"
            icon={<Edit size={14} />}
            onClick={() => handleEdit(record)}
          >
            高级编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<Copy size={14} />}
            onClick={() => handleDuplicate(record)}
          >
            复制
          </Button>
          <Popconfirm
            title="确定要删除此策略吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<Delete size={14} />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="strategies-tab">
      <div className="strategies-header">
        <div className="header-title">
          <h3>策略管理</h3>
          <p className="header-subtitle">创建、编辑和管理交易策略配置</p>
        </div>
        <Button
          type="primary"
          icon={<Plus size={16} />}
          onClick={handleCreate}
          size="large"
        >
          创建策略
        </Button>
      </div>

      <Table
        dataSource={strategies}
        loading={loading}
        rowKey="id"
        columns={columns}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条策略`,
        }}
        scroll={{ x: 1200 }}
      />

      {/* 高级策略创建/编辑表单 */}
      <AdvancedStrategyForm
        visible={advancedModalVisible}
        initialData={editingStrategy}
        onCancel={() => {
          setAdvancedModalVisible(false);
          setEditingStrategy(null);
        }}
        onSubmit={handleSubmit}
        loading={submitting}
      />
    </div>
  );
};
