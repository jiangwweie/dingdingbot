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

import React from 'react';
import { Card, Switch, Tag, Space, Button, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined, CopyOutlined } from '@ant-design/icons';
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

  return (
    <Card
      className={cn(
        'strategy-card transition-all duration-200 hover:shadow-lg',
        !is_active && 'opacity-75'
      )}
      bordered={true}
      size="small"
      actions={[
        <Tooltip key="edit" title="编辑策略">
          <Button
            type="text"
            icon={<EditOutlined className="text-blue-600" />}
            onClick={() => onEdit(strategy)}
            size="small"
          />
        </Tooltip>,
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
  );
};

export default StrategyCard;
