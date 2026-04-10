/**
 * 配置备份恢复组件
 *
 * 支持 YAML 配置的导入导出功能，包含三步流程：
 * 1. 选择文件 - 上传 YAML 文件或导出当前配置
 * 2. 预览变更 - 显示变更摘要、冲突警告、重启提示
 * 3. 完成 - 导入结果展示
 *
 * 数据流：
 * - 导出：调用 POST /api/v1/config/export → 获取 yaml_content → Blob 下载
 * - 导入预览：读取文件内容 → POST /api/v1/config/import/preview → 获取 preview_token
 * - 确认导入：POST /api/v1/config/import/confirm { preview_token } → 完成
 * - preview_token TTL：5 分钟，过期需重新预览
 */

import React, { useState, useCallback } from 'react';
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
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  configApi,
  type ImportPreviewResult,
  type ImportConfirmResponse,
} from '../../api/config';

const { Title, Paragraph } = Typography;

// ============================================================
// Constants
// ============================================================

/** preview_token TTL（秒），与后端 TTLCache 保持一致 */
const PREVIEW_TOKEN_TTL_SECONDS = 5 * 60;

// ============================================================
// Component
// ============================================================

export const BackupTab: React.FC = () => {
  // 当前步骤 (0: 选择文件，1: 预览变更，2: 完成)
  const [currentStep, setCurrentStep] = useState(0);
  // 预览数据（来自后端 preview API）
  const [previewData, setPreviewData] = useState<ImportPreviewResult | null>(null);
  // 确认导入结果
  const [importResult, setImportResult] = useState<ImportConfirmResponse | null>(null);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // YAML 文件内容（用于导入流程）
  const [yamlContent, setYamlContent] = useState<string>('');
  // 上传的文件名
  const [fileName, setFileName] = useState<string>('');
  // preview_token 过期时间戳
  const [previewExpiresAt, setPreviewExpiresAt] = useState<number>(0);

  // 检查 preview_token 是否过期
  const isPreviewExpired = useCallback(() => {
    if (!previewData || previewExpiresAt === 0) return true;
    return Date.now() > previewExpiresAt;
  }, [previewData, previewExpiresAt]);

  // ============================================================
  // Step 1: 导出配置
  // ============================================================
  const handleExport = async () => {
    try {
      setLoading(true);

      const response = await configApi.exportConfig({
        include_strategies: true,
        include_risk: true,
        include_system: true,
        include_symbols: true,
        include_notifications: true,
      });

      const { yaml_content, filename } = response.data;

      // 创建 Blob 并触发浏览器下载
      const blob = new Blob([yaml_content], { type: 'application/x-yaml' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      message.success(`配置已导出：${filename}`);
    } catch (error: unknown) {
      console.error('Export error:', error);
      const errMessage =
        error instanceof Error ? error.message : '导出失败';
      message.error(errMessage);
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // Step 1: 上传 YAML 文件并调用预览 API
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

      setLoading(true);

      // 调用后端 preview API
      const response = await configApi.previewImport({
        yaml_content: content,
        filename: file.name || 'config.yaml',
      });

      const preview = response.data;

      // 设置预览数据和过期时间
      setPreviewData(preview);
      setPreviewExpiresAt(Date.now() + PREVIEW_TOKEN_TTL_SECONDS * 1000);

      // 如果预览无效（有 errors），展示错误并阻止进入下一步
      if (!preview.valid) {
        message.error(`YAML 验证失败，发现 ${preview.errors.length} 个错误`);
        // 仍然展示预览让用户看到错误，但禁用确认导入按钮
        setCurrentStep(1);
      } else {
        setCurrentStep(1);
        message.success('预览生成成功');
      }
    } catch (error: unknown) {
      console.error('Preview error:', error);
      const errMessage =
        error instanceof Error ? error.message : '预览生成失败';
      message.error(errMessage);
    } finally {
      setLoading(false);
    }

    return false; // 阻止自动上传
  };

  // ============================================================
  // Step 2: 确认导入（使用 preview_token）
  // ============================================================
  const handleConfirmImport = async () => {
    // 检查 preview_token 是否过期
    if (isPreviewExpired()) {
      message.warning('预览已过期（超过 5 分钟），请重新选择文件预览');
      setCurrentStep(0);
      setPreviewData(null);
      setPreviewExpiresAt(0);
      return;
    }

    if (!previewData?.preview_token) return;

    try {
      setLoading(true);

      const response = await configApi.confirmImport({
        preview_token: previewData.preview_token,
      });

      const result = response.data;
      setImportResult(result);
      setCurrentStep(2);

      let successMsg = '配置导入成功！';
      if (result.snapshot_id) {
        successMsg += `（快照 ID: ${result.snapshot_id}）`;
      }
      if (previewData.requires_restart) {
        successMsg += ' 请重启服务使配置生效。';
      }
      message.success(successMsg);
    } catch (error: unknown) {
      console.error('Confirm import error:', error);
      const errMessage =
        error instanceof Error
          ? error.message
          : '导入失败，preview_token 可能已过期';
      message.error(errMessage);

      // 如果是 400 错误（token 过期），重置到第一步
      if (error instanceof Error && error.message?.includes('400')) {
        setCurrentStep(0);
        setPreviewData(null);
        setPreviewExpiresAt(0);
        message.warning('请重新选择文件预览');
      }
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // 重置到第一步
  // ============================================================
  const handleReset = () => {
    setCurrentStep(0);
    setPreviewData(null);
    setImportResult(null);
    setYamlContent('');
    setFileName('');
    setPreviewExpiresAt(0);
  };

  // ============================================================
  // 渲染预览对比
  // ============================================================
  const renderPreview = () => {
    if (!previewData) return null;

    const { valid, summary, conflicts, requires_restart, errors } = previewData;

    return (
      <div>
        {/* 验证错误 */}
        {errors.length > 0 && (
          <Alert
            type="error"
            message={
              <Space>
                <ExclamationCircleOutlined />
                YAML 验证失败
              </Space>
            }
            description={
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {errors.map((err, idx) => (
                  <li key={idx}>{err}</li>
                ))}
              </ul>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}

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

        {/* Token 过期倒计时提示 */}
        <Alert
          type="info"
          message={
            <Space>
              <InfoCircleOutlined />
              预览 Token 将在 5 分钟内有效，请尽快确认导入
            </Space>
          }
          style={{ marginTop: 16 }}
          showIcon
        />

        {/* 策略详情 */}
        {previewData.preview_data.strategies.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Title level={5}>策略详情</Title>
            <Table
              dataSource={previewData.preview_data.strategies}
              size="small"
              pagination={false}
              scroll={{ y: 300 }}
              rowKey={(record) => record.name || record.id || Math.random()}
              columns={[
                {
                  title: '名称',
                  dataIndex: 'name',
                  key: 'name',
                  width: 200,
                  render: (value: string) => value || '-',
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
              rowKey={(record) => record.symbol || record.id || Math.random()}
              columns={[
                {
                  title: '交易对',
                  dataIndex: 'symbol',
                  key: 'symbol',
                  render: (value: string) => value || '-',
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
              <Button onClick={handleReset}>返回</Button>
              <Button
                type="primary"
                onClick={handleConfirmImport}
                loading={loading}
                icon={<CheckCircleOutlined />}
                disabled={!previewData?.valid || isPreviewExpired()}
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
              {importResult?.snapshot_id && (
                <>
                  <br />
                  快照 ID: {importResult.snapshot_id}
                </>
              )}
              {previewData?.requires_restart && (
                <>，请重启服务使配置生效</>
              )}
            </Paragraph>
            {fileName && (
              <Paragraph style={{ marginTop: 8 }}>
                <FileTextOutlined style={{ marginRight: 4 }} />
                文件：{fileName}
              </Paragraph>
            )}
          </div>
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Button onClick={handleReset} type="primary">
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
