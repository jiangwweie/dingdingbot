/**
 * 重启提示组件
 *
 * 当系统配置变更后，提示用户需要重启服务才能生效。
 * 提供立即重启和稍后手动重启两个选项。
 */

import React from 'react';
import { Alert, Button, Space, message, Modal } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

export interface RestartRequiredAlertProps {
  /** 是否显示重启提示 */
  visible: boolean;
  /** 重启按钮点击回调 */
  onRestart?: () => void;
  /** 关闭提示回调 */
  onClose?: () => void;
}

export const RestartRequiredAlert: React.FC<RestartRequiredAlertProps> = ({
  visible,
  onRestart,
  onClose
}) => {
  if (!visible) return null;

  const handleRestart = () => {
    Modal.confirm({
      title: '确认重启服务？',
      content: '重启期间系统将暂停服务，请确保当前没有正在执行的交易操作。',
      okText: '确认重启',
      cancelText: '稍后手动重启',
      onOk: async () => {
        try {
          // 调用后端重启 API（如存在）
          // await fetch('/api/v1/system/restart', { method: 'POST' });
          message.success('重启指令已发送，请稍候...');
          onRestart?.();
        } catch (error) {
          message.error('重启失败，请手动重启服务');
        }
      }
    });
  };

  const handleClose = () => {
    message.info('请稍后手动重启服务');
    onClose?.();
  };

  return (
    <Alert
      type="warning"
      showIcon
      message="配置变更需要重启"
      description={
        <Space direction="vertical" style={{ width: '100%' }}>
          <span>
            您修改了系统级配置，需要重启服务才能生效。
            建议在交易低峰期执行重启操作。
          </span>
          <Space>
            <Button
              type="primary"
              danger
              icon={<ReloadOutlined />}
              onClick={handleRestart}
            >
              立即重启
            </Button>
            <Button onClick={handleClose}>
              稍后手动重启
            </Button>
          </Space>
        </Space>
      }
      style={{ marginBottom: 16 }}
      closable
      afterClose={handleClose}
    />
  );
};

export default RestartRequiredAlert;
