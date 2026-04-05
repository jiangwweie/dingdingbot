/**
 * BackupTab 组件测试 - 核心功能验证
 */
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { message } from 'antd';
import { BackupTab } from '../BackupTab';

// Setup mocks at module level
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(() => ({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  })),
});

const mockCreateObjectURL = vi.fn(() => 'blob:url');
const mockRevokeObjectURL = vi.fn();
class MockBlob { constructor() {} }

describe('BackupTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    message.destroy(); // 清理 Ant Design message 组件
    global.URL.createObjectURL = mockCreateObjectURL;
    global.URL.revokeObjectURL = mockRevokeObjectURL;
    global.Blob = MockBlob as any;
  });

  afterEach(() => {
    cleanup(); // 清理 DOM
    message.destroy(); // 清理 Ant Design message 组件
  });

  const setup = (fetchMock: any) => { global.fetch = fetchMock; };
  const getFileInput = () => screen.getByRole('button', { name: /选择 YAML 文件/ }).parentElement?.querySelector('input[type="file"]');

  describe('Initial Render', () => {
    it('renders title', () => {
      setup(vi.fn(() => Promise.resolve({ ok: true })) as any);
      render(<BackupTab />);
      expect(screen.getByText('备份恢复')).toBeInTheDocument();
    });

    it('renders export button', () => {
      setup(vi.fn(() => Promise.resolve({ ok: true })) as any);
      render(<BackupTab />);
      expect(screen.getByText('导出当前配置')).toBeInTheDocument();
    });

    it('renders three steps', () => {
      setup(vi.fn(() => Promise.resolve({ ok: true })) as any);
      render(<BackupTab />);
      expect(screen.getByText('选择文件')).toBeInTheDocument();
      expect(screen.getByText('预览变更')).toBeInTheDocument();
      expect(screen.getByText('完成')).toBeInTheDocument();
    });
  });

  describe('Export', () => {
    it('shows loading state', async () => {
      setup(vi.fn(() => new Promise(r => setTimeout(() => r({ ok: true, blob: () => new Blob() }), 50))) as any);
      render(<BackupTab />);
      fireEvent.click(screen.getByText('导出当前配置'));
      await waitFor(() => expect(screen.getByRole('button', { name: /导出当前配置/ })).toHaveClass('ant-btn-loading'));
    });

    it('shows error on failure', async () => {
      setup(vi.fn(() => Promise.resolve({ ok: false, status: 500 })) as any);
      render(<BackupTab />);
      fireEvent.click(screen.getByText('导出当前配置'));
      await waitFor(() => expect(screen.getByText('导出失败')).toBeInTheDocument());
    });
  });

  describe('Import - Upload', () => {
    it('shows preview after upload', async () => {
      const resp = { valid: true, preview_token: 't', expires_at: new Date().toISOString(), summary: { strategies: { added: 0, modified: 0, deleted: 0 }, risk: { modified: false }, symbols: { added: 0 }, notifications: { added: 0 } }, conflicts: [], requires_restart: false, preview_data: { strategies: [], risk: {}, symbols: [], notifications: [] } };
      setup(vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(resp) })) as any);
      render(<BackupTab />);
      const fi = getFileInput();
      if (fi) fireEvent.change(fi, { target: { files: [new File(['c'], 't.yaml', { type: 'text/yaml' })] } });
      await waitFor(() => expect(screen.getByText('预览变更')).toBeInTheDocument());
    });
  });

  describe('Import - Preview', () => {
    it('shows strategy changes', async () => {
      const resp = { valid: true, preview_token: 't', expires_at: new Date().toISOString(), summary: { strategies: { added: 1, modified: 1, deleted: 1 }, risk: { modified: true }, symbols: { added: 2 }, notifications: { added: 0 } }, conflicts: [], requires_restart: false, preview_data: { strategies: [], risk: {}, symbols: [], notifications: [] } };
      setup(vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(resp) })) as any);
      render(<BackupTab />);
      const fi = getFileInput();
      if (fi) fireEvent.change(fi, { target: { files: [new File(['c'], 't.yaml', { type: 'text/yaml' })] } });
      await waitFor(() => {
        expect(screen.getByText('+1 新增')).toBeInTheDocument();
        expect(screen.getByText('~1 修改')).toBeInTheDocument();
        expect(screen.getByText('-1 删除')).toBeInTheDocument();
      });
    });
  });

  describe('Import - Confirm', () => {
    it('calls confirm API', async () => {
      const previewResp = { valid: true, preview_token: 't123', expires_at: new Date().toISOString(), summary: { strategies: { added: 1, modified: 0, deleted: 0 }, risk: { modified: false }, symbols: { added: 0 }, notifications: { added: 0 } }, conflicts: [], requires_restart: false, preview_data: { strategies: [], risk: {}, symbols: [], notifications: [] } };
      const confirmResp = { requires_restart: false };
      const fetchMock = vi.fn();
      fetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(previewResp) });
      fetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(confirmResp) });
      setup(fetchMock as any);
      render(<BackupTab />);
      const fi = getFileInput();
      if (fi) fireEvent.change(fi, { target: { files: [new File(['c'], 't.yaml', { type: 'text/yaml' })] } });
      await waitFor(() => expect(screen.getByText('确认导入')).toBeInTheDocument());
      fireEvent.click(screen.getByText('确认导入'));
      await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/config/import/confirm', expect.any(Object)));
    });
  });

  describe('Completion', () => {
    it('shows success', async () => {
      const previewResp = { valid: true, preview_token: 't', expires_at: new Date().toISOString(), summary: { strategies: { added: 0, modified: 0, deleted: 0 }, risk: { modified: false }, symbols: { added: 0 }, notifications: { added: 0 } }, conflicts: [], requires_restart: false, preview_data: { strategies: [], risk: {}, symbols: [], notifications: [] } };
      const fetchMock = vi.fn();
      fetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(previewResp) });
      fetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ requires_restart: false }) });
      setup(fetchMock as any);
      render(<BackupTab />);
      const fi = getFileInput();
      if (fi) fireEvent.change(fi, { target: { files: [new File(['c'], 't.yaml', { type: 'text/yaml' })] } });
      await waitFor(() => expect(screen.getByText('确认导入')).toBeInTheDocument());
      fireEvent.click(screen.getByText('确认导入'));
      await waitFor(() => expect(screen.getByText('导入成功')).toBeInTheDocument());
    });
  });

  describe('Empty State', () => {
    it('shows no change', async () => {
      const resp = { valid: true, preview_token: 't', expires_at: new Date().toISOString(), summary: { strategies: { added: 0, modified: 0, deleted: 0 }, risk: { modified: false }, symbols: { added: 0 }, notifications: { added: 0 } }, conflicts: [], requires_restart: false, preview_data: { strategies: [], risk: {}, symbols: [], notifications: [] } };
      setup(vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(resp) })) as any);
      render(<BackupTab />);
      const fi = getFileInput();
      if (fi) fireEvent.change(fi, { target: { files: [new File(['c'], 't.yaml', { type: 'text/yaml' })] } });
      await waitFor(() => expect(screen.getByText('变更摘要')).toBeInTheDocument());
      expect(screen.getAllByText('无变更').length).toBeGreaterThan(0);
    });
  });
});
