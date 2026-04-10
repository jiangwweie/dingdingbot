/**
 * 策略卡片组件
 *
 * 用于策略列表展示，支持：
 * - 策略基本信息展示
 * - 启用/禁用切换
 * - 编辑/删除操作
 *
 * @package components/strategy
 */

import React, { useState } from 'react';
import { Card, Switch, Tag, Space, Button, Tooltip, Modal, Collapse, Typography, Descriptions, Divider } from 'antd';
import { EditOutlined, DeleteOutlined, CopyOutlined, EyeOutlined, ExperimentOutlined, UploadOutlined } from '@ant-design/icons';
import { cn } from '../../lib/utils';
import type { Strategy } from '../../api/config';

// ============================================================
// Props Interface
// ============================================================

export interface StrategyCardProps {
  strategy: Strategy;
  onEdit: (strategy: Strategy) => void;
  onToggleEnable: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onDuplicate?: (strategy: Strategy) => void;
  onPreview?: (strategy: Strategy) => void;
  onApply?: (strategy: Strategy) => void;
}

// ============================================================
// Helper Functions
// ============================================================

const TRIGGER_LABELS: Record<string, string> = {
  pinbar: 'Pinbar',
  engulfing: 'Engulfing',
  doji: 'Doji',
  hammer: 'Hammer',
};

const getTriggerColor = (type: string): string => {
  const colors: Record<string, string> = {
    pinbar: 'blue',
    engulfing: 'purple',
    doji: 'cyan',
    hammer: 'green',
  };
  return colors[type] || 'default';
};

// ============================================================
// StrategyCard Component
// ============================================================

export const StrategyCard: React.FC<StrategyCardProps> = ({
  strategy,
  onEdit,
  onToggleEnable,
  onDelete,
  onDuplicate,
  onPreview,
  onApply,
}) => {
  const {
    id,
    name,
    description,
    is_active,
    trigger_config,
    filter_configs,
    symbols,
    timeframes,
  } = strategy;

  const triggerType = trigger_config?.type || 'unknown';
  const filterCount = filter_configs?.length || 0;

  const [previewVisible, setPreviewVisible] = useState(false);

  const renderParams = (params: Record<string, any>) => {
    if (!params || Object.keys(params).length === 0) {
      return <span className="text-gray-400">无参数</span>;
    }
    return (
      <div className="space-y-1">
        {Object.entries(params).map(([key, value]) => (
          <div key={key} className="flex items-center gap-2 text-sm">
            <span className="text-gray-500 min-w-[80px]">{key}:</span>
            <span className="font-mono text-gray-800">{String(value)}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <>
    <Card
      className={cn(
        'strategy-card transition-all duration-200 hover:shadow-lg',
        !is_active && 'opacity-75'
      )}
      bordered={true}
      size="small"
      actions={[
        <Tooltip key="preview" title="查看详情">
          <Button
            type="text"
            icon={<EyeOutlined className="text-green-600" />}
            onClick={() => setPreviewVisible(true)}
            size="small"
          />
        </Tooltip>,
        onPreview ? (
          <Tooltip key="dryrun" title="Dry Run 预览">
            <Button
              type="text"
              icon={<ExperimentOutlined className="text-orange-600" />}
              onClick={() => onPreview(strategy)}
              size="small"
            />
          </Tooltip>
        ) : null,
        <Tooltip key="edit" title="编辑策略">
          <Button
            type="text"
            icon={<EditOutlined className="text-blue-600" />}
            onClick={() => onEdit(strategy)}
            size="small"
          />
        </Tooltip>,
        onApply ? (
          <Tooltip key="apply" title="应用到实盘">
            <Button
              type="text"
              icon={<UploadOutlined className="text-cyan-600" />}
              onClick={() => onApply(strategy)}
              size="small"
            />
          </Tooltip>
        ) : null,
        onDuplicate ? (
          <Tooltip key="duplicate" title="复制策略">
            <Button
              type="text"
              icon={<CopyOutlined className="text-gray-600" />}
              onClick={() => onDuplicate(strategy)}
              size="small"
            />
          </Tooltip>
        ) : null,
        <Tooltip key="delete" title="删除策略">
          <Button
            type="text"
            icon={<DeleteOutlined className="text-red-600" />}
            onClick={() => onDelete(id)}
            danger
            size="small"
          />
        </Tooltip>,
      ]}
    >
      <Card.Meta
        title={
          <div className="flex items-center justify-between">
            <span className="font-semibold text-gray-900">{name}</span>
            <Switch
              size="small"
              checked={is_active}
              onChange={(checked) => onToggleEnable(id, checked)}
              checkedChildren="启用"
              unCheckedChildren="禁用"
              className={is_active ? 'bg-green-500' : ''}
            />
          </div>
        }
        description={
          <div className="space-y-3">
            {/* 策略描述 */}
            {description && (
              <p className="text-sm text-gray-500 line-clamp-2">{description}</p>
            )}

            {/* 触发器和过滤器 */}
            <div className="flex items-center gap-2 flex-wrap">
              <Tag color={getTriggerColor(triggerType)}>
                {TRIGGER_LABELS[triggerType] || triggerType}
              </Tag>
              {filterCount > 0 && (
                <Tag color="purple" className="flex items-center gap-1">
                  <span>{filterCount} 过滤器</span>
                </Tag>
              )}
            </div>

            {/* 币种和周期 */}
            <div className="space-y-2">
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-gray-400 mr-1">币种:</span>
                {symbols?.slice(0, 3).map((symbol) => (
                  <Tag key={symbol} color="gray" className="text-xs">
                    {symbol.split('/')[0]}
                  </Tag>
                ))}
                {symbols && symbols.length > 3 && (
                  <Tag color="gray" className="text-xs">
                    +{symbols.length - 3}
                  </Tag>
                )}
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-gray-400 mr-1">周期:</span>
                {timeframes?.map((tf) => (
                  <Tag key={tf} color="green" className="text-xs">
                    {tf}
                  </Tag>
                ))}
              </div>
            </div>
          </div>
        }
      />
    </Card>

    {/* 策略详情预览 Modal */}
    <Modal
      title={
        <div className="flex items-center gap-2">
          <EyeOutlined className="text-green-600" />
          <span>策略详情 - {name}</span>
        </div>
      }
      open={previewVisible}
      onCancel={() => setPreviewVisible(false)}
      footer={null}
      width={640}
      destroyOnClose
    >
      <Collapse
        defaultActiveKey={['trigger', 'filters', 'scope']}
        items={[
          {
            key: 'trigger',
            label: (
              <span className="font-medium">
                触发器: <Tag color={getTriggerColor(triggerType)}>{TRIGGER_LABELS[triggerType] || triggerType}</Tag>
              </span>
            ),
            children: (
              <div className="space-y-2">
                <Typography.Text type="secondary" className="text-sm">
                  触发器参数
                </Typography.Text>
                {renderParams(trigger_config?.params || {})}
              </div>
            ),
          },
          {
            key: 'filters',
            label: (
              <span className="font-medium">
                过滤器链 ({filterCount} 个) - 逻辑: <Tag color={strategy.filter_logic === 'AND' ? 'blue' : 'orange'}>{strategy.filter_logic}</Tag>
              </span>
            ),
            children:
              filter_configs?.length > 0 ? (
                <div className="space-y-3">
                  {filter_configs.map((filter, index) => (
                    <div key={filter.type + index} className="border-l-2 border-purple-300 pl-3">
                      <div className="flex items-center gap-2 mb-1">
                        <Tag color="purple">{filter.type}</Tag>
                        <Tag color={filter.enabled ? 'green' : 'default'}>
                          {filter.enabled ? '已启用' : '已禁用'}
                        </Tag>
                      </div>
                      {renderParams(filter.params || {})}
                    </div>
                  ))}
                </div>
              ) : (
                <Typography.Text type="secondary">无过滤器</Typography.Text>
              ),
          },
          {
            key: 'scope',
            label: <span className="font-medium">作用域 (币种 & 周期)</span>,
            children: (
              <div className="space-y-3">
                <div>
                  <Typography.Text type="secondary" className="text-sm block mb-2">
                    交易对
                  </Typography.Text>
                  <div className="flex flex-wrap gap-1">
                    {symbols?.map((symbol) => (
                      <Tag key={symbol} color="gray">
                        {symbol}
                      </Tag>
                    ))}
                  </div>
                </div>
                <Divider className="my-2" />
                <div>
                  <Typography.Text type="secondary" className="text-sm block mb-2">
                    K 线周期
                  </Typography.Text>
                  <div className="flex flex-wrap gap-1">
                    {timeframes?.map((tf) => (
                      <Tag key={tf} color="green">
                        {tf}
                      </Tag>
                    ))}
                  </div>
                </div>
              </div>
            ),
          },
          {
            key: 'meta',
            label: <span className="font-medium">元信息</span>,
            children: (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="策略 ID">{id}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={is_active ? 'green' : 'default'}>
                    {is_active ? '已启用' : '已禁用'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">{strategy.created_at || '-'}</Descriptions.Item>
                <Descriptions.Item label="更新时间">{strategy.updated_at || '-'}</Descriptions.Item>
              </Descriptions>
            ),
          },
        ]}
      />
    </Modal>
    </>
  );
};

export default StrategyCard;
