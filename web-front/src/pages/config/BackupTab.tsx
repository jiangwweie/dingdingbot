/**
 * 配置备份恢复组件
 *
 * 支持 YAML 配置的导入导出功能，包含三步流程：
 * 1. 选择文件 - 上传 YAML 文件或导出当前配置
 * 2. 预览变更 - 显示变更摘要、冲突警告、重启提示
 * 3. 完成 - 导入结果展示
 */

import React, { useState } from 'react';
import {
  Card,
  Button,
  Upload,
  message,
  Table,
  Tag,
  Descriptions,
  Space,
  Alert,
  Steps,
  Typography,
} from 'antd';
import {
  UploadOutlined,
  DownloadOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import type { StepsProps } from 'antd';

const { Title, Paragraph } = Typography;

// ============================================================
// Type Definitions
// ============================================================

/**
 * 导入预览结果类型
 */
interface ImportPreview {
  /** 是否有效 */
  valid: boolean;
  /** 预览令牌（用于确认导入） */
  preview_token: string;
  /** 过期时间（ISO 8601 格式） */
  expires_at: string;
  /** 变更摘要 */
  summary: {
    /** 策略变更 */
    strategies: {
      /** 新增数量 */
      added: number;
      /** 修改数量 */
      modified: number;
      /** 删除数量 */
      deleted: number;
    };
    /** 风控配置变更 */
    risk: {
      /** 是否有修改 */
      modified: boolean;
    };
    /** 币种变更 */
    symbols: {
      /** 新增数量 */
      added: number;
    };
    /** 通知渠道变更 */
    notifications: {
      /** 新增数量 */
      added: number;
    };
  };
  /** 冲突列表 */
  conflicts: string[];
  /** 是否需要重启 */
  requires_restart: boolean;
  /** 预览详情数据 */
  preview_data: {
    /** 策略列表 */
    strategies: any[];
    /** 风控配置 */
    risk: any;
    /** 币种列表 */
    symbols: any[];
    /** 通知渠道列表 */
    notifications: any[];
  };
}

// ============================================================
// Component
// ============================================================

export const BackupTab: React.FC = () => {
  // 当前步骤 (0: 选择文件，1: 预览变更，2: 完成)
  const [currentStep, setCurrentStep] = useState(0);
  // 预览数据
  const [previewData, setPreviewData] = useState<ImportPreview | null>(null);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // YAML 文件内容
  const [yamlContent, setYamlContent] = useState<string>('');
  // 上传的文件名
  const [fileName, setFileName] = useState<string>('');

  // ============================================================
  // Step 1: 上传 YAML 文件
  // ============================================================
  const handleUpload = async (file: UploadFile) => {
    if (!file.originFileObj) {
      message.error('文件读取失败');
      return false;
    }

    try {
      const content = await file.originFileObj.text();
      setYamlContent(content);
      setFileName(file.name || 'unknown.yaml');

      // 调用预览 API
      setLoading(true);
      const response = await fetch('/api/v1/config/import/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          yaml_content: content,
          filename: file.name,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '预览失败');
      }

      const preview: ImportPreview = await response.json();
      setPreviewData(preview);
      setCurrentStep(1);
      message.success('预览生成成功');
    } catch (error: any) {
      console.error('Upload error:', error);
      message.error(error.message || '预览生成失败');
    } finally {
      setLoading(false);
    }

    return false; // 阻止自动上传
  };

  // ============================================================
  // Step 2: 确认导入
  // ============================================================
  const handleConfirmImport = async () => {
    if (!previewData) return;

    try {
      setLoading(true);
      const response = await fetch('/api/v1/config/import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preview_token: previewData.preview_token,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '导入失败');
      }

      const result = await response.json();
      message.success(
        '配置导入成功！' +
          (result.requires_restart ? '请重启服务。' : '')
      );
      setCurrentStep(2);
    } catch (error: any) {
      console.error('Import error:', error);
      message.error(error.message || '导入失败');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // 导出配置
  // ============================================================
  const handleExport = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/config/export', {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('导出失败');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `config_backup_${new Date().toISOString().slice(0, 10)}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      message.success('配置已导出');
    } catch (error: any) {
      console.error('Export error:', error);
      message.error(error.message || '导出失败');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // 渲染预览对比
  // ============================================================
  const renderPreview = () => {
    if (!previewData) return null;

    const { summary, conflicts, requires_restart } = previewData;

    return (
      <div>
        {/* 冲突警告 */}
        {conflicts.length > 0 && (
          <Alert
            type="warning"
            message={
              <Space>
                <WarningOutlined />
                发现冲突
              </Space>
            }
            description={conflicts.join(', ')}
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}

        {/* 重启提示 */}
        {requires_restart && (
          <Alert
            type="info"
            message={
              <Space>
                <InfoCircleOutlined />
                需要重启
              </Space>
            }
            description="此配置变更需要重启服务才能生效"
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}

        {/* 变更摘要 */}
        <Title level={5}>变更摘要</Title>
        <Descriptions bordered column={2} size="small">
          <Descriptions.Item label="策略变更" span={2}>
            <Space>
              {summary.strategies.added > 0 && (
                <Tag color="green">+{summary.strategies.added} 新增</Tag>
              )}
              {summary.strategies.modified > 0 && (
                <Tag color="blue">~{summary.strategies.modified} 修改</Tag>
              )}
              {summary.strategies.deleted > 0 && (
                <Tag color="red">-{summary.strategies.deleted} 删除</Tag>
              )}
              {summary.strategies.added === 0 &&
                summary.strategies.modified === 0 &&
                summary.strategies.deleted === 0 && (
                  <span style={{ color: '#999' }}>无变更</span>
                )}
            </Space>
          </Descriptions.Item>

          <Descriptions.Item label="风控配置">
            {summary.risk.modified ? (
              <Tag color="blue">有变更</Tag>
            ) : (
              <Tag>无变更</Tag>
            )}
          </Descriptions.Item>

          <Descriptions.Item label="币种">
            {summary.symbols.added > 0 ? (
              <Tag color="green">+{summary.symbols.added} 新增</Tag>
            ) : (
              <span style={{ color: '#999' }}>无变更</span>
            )}
          </Descriptions.Item>

          <Descriptions.Item label="通知渠道">
            {summary.notifications.added > 0 ? (
              <Tag color="green">+{summary.notifications.added} 新增</Tag>
            ) : (
              <span style={{ color: '#999' }}>无变更</span>
            )}
          </Descriptions.Item>
        </Descriptions>

        {/* 策略详情 */}
        {previewData.preview_data.strategies.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Title level={5}>策略详情</Title>
            <Table
              dataSource={previewData.preview_data.strategies}
              size="small"
              pagination={false}
              scroll={{ y: 300 }}
              columns={[
                {
                  title: '名称',
                  dataIndex: 'name',
                  key: 'name',
                  width: 200,
                },
                {
                  title: '触发器',
                  dataIndex: ['trigger_config', 'type'],
                  key: 'trigger_type',
                  width: 120,
                  render: (value: string) => value || '-',
                },
                {
                  title: '状态',
                  key: 'is_active',
                  width: 100,
                  render: (_: unknown, record: any) => (
                    <Tag color={record.is_active ? 'green' : 'red'}>
                      {record.is_active ? '启用' : '禁用'}
                    </Tag>
                  ),
                },
              ]}
            />
          </div>
        )}

        {/* 币种详情 */}
        {previewData.preview_data.symbols.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Title level={5}>币种列表</Title>
            <Table
              dataSource={previewData.preview_data.symbols}
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              columns={[
                {
                  title: '交易对',
                  dataIndex: 'symbol',
                  key: 'symbol',
                },
              ]}
            />
          </div>
        )}
      </div>
    );
  };

  // ============================================================
  // Steps Definition
  // ============================================================
  const steps = [
    {
      title: '选择文件',
      icon: <UploadOutlined />,
      content: (
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Paragraph type="secondary" style={{ marginBottom: 24 }}>
              请选择要导入的 YAML 配置文件，或导出当前配置
            </Paragraph>

            {/* 上传区域 */}
            <Upload
              accept=".yaml,.yml"
              beforeUpload={handleUpload}
              showUploadList={false}
              disabled={loading}
            >
              <Button
                type="primary"
                icon={<UploadOutlined />}
                size="large"
                loading={loading}
              >
                选择 YAML 文件
              </Button>
            </Upload>

            <div style={{ margin: '16px 0' }}>
              <Paragraph type="secondary">
                支持格式：.yaml, .yml
              </Paragraph>
            </div>

            {/* 分隔线 */}
            <div
              style={{
                margin: '24px 0',
                borderTop: '1px solid #e8e8e8',
                position: 'relative',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  top: '-10px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: '#fff',
                  padding: '0 8px',
                  color: '#999',
                  fontSize: '12px',
                }}
              >
                或
              </span>
            </div>

            {/* 导出按钮 */}
            <Button
              icon={<DownloadOutlined />}
              size="large"
              onClick={handleExport}
              loading={loading}
            >
              导出当前配置
            </Button>
          </div>
        </Card>
      ),
    },
    {
      title: '预览变更',
      icon: <FileTextOutlined />,
      content: (
        <Card>
          {renderPreview()}
          <div
            style={{
              marginTop: 24,
              borderTop: '1px solid #e8e8e8',
              paddingTop: 16,
              textAlign: 'right',
            }}
          >
            <Space>
              <Button
                onClick={() => {
                  setCurrentStep(0);
                  setPreviewData(null);
                  setYamlContent('');
                  setFileName('');
                }}
              >
                返回
              </Button>
              <Button
                type="primary"
                onClick={handleConfirmImport}
                loading={loading}
                icon={<CheckCircleOutlined />}
              >
                确认导入
              </Button>
            </Space>
          </div>
        </Card>
      ),
    },
    {
      title: '完成',
      icon: <CheckCircleOutlined />,
      content: (
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <CheckCircleOutlined
              style={{
                fontSize: 64,
                color: '#52c41a',
                marginBottom: 16,
              }}
            />
            <Title level={4}>导入成功</Title>
            <Paragraph type="secondary">
              配置已成功导入
              {previewData?.requires_restart && '，请重启服务使配置生效'}
            </Paragraph>
            {fileName && (
              <Paragraph style={{ marginTop: 8 }}>
                <FileTextOutlined style={{ marginRight: 4 }} />
                文件：{fileName}
              </Paragraph>
            )}
          </div>
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Button
              onClick={() => {
                setCurrentStep(0);
                setPreviewData(null);
                setYamlContent('');
                setFileName('');
              }}
              type="primary"
            >
              返回
            </Button>
          </div>
        </Card>
      ),
    },
  ];

  // ============================================================
  // Render
  // ============================================================
  return (
    <div>
      {/* 标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={3}>备份恢复</Title>
        <Paragraph type="secondary">
          管理配置的导入导出，支持版本化备份与恢复
        </Paragraph>
      </div>

      {/* 步骤条 */}
      <Steps
        current={currentStep}
        style={{ marginBottom: 24 }}
        items={steps.map((step, index) => ({
          key: index,
          title: step.title,
          icon: step.icon,
        }))}
      />

      {/* 步骤内容 */}
      {steps[currentStep].content}
    </div>
  );
};

export default BackupTab;
