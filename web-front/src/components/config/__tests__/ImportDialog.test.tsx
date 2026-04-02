import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ImportDialog from '../ImportDialog';
import * as api from '../../../lib/api';

// Mock the api module
vi.mock('../../../lib/api', () => ({
  importConfig: vi.fn(),
}));

// Mock File
const createMockFile = (name: string, size: number, type = 'text/yaml') =>
  new File(['content'], name, { type });

describe('ImportDialog', () => {
  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderDialog = (open = true) =>
    render(
      <ImportDialog
        open={open}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />
    );

  it('renders correctly when open', () => {
    renderDialog();

    expect(screen.getByText('导入配置')).toBeInTheDocument();
    expect(screen.getByText('点击或拖拽文件到此处')).toBeInTheDocument();
  });

  it('calls onClose when cancel button clicked', async () => {
    renderDialog();

    fireEvent.click(screen.getByText('取消'));

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('validates file type when selecting file', async () => {
    renderDialog();

    const invalidFile = createMockFile('config.json', 1024, 'application/json');
    const fileInput = screen.getByRole('button');

    // Simulate file selection (would normally be through input)
    // For this test, we'll check the error message directly
    fireEvent.click(fileInput);

    // Trigger file drop with invalid type
    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [invalidFile] },
    });

    await waitFor(() => {
      expect(screen.getByText(/YAML 格式/)).toBeInTheDocument();
    });
  });

  it('validates file size when selecting file', async () => {
    renderDialog();

    // Create a file larger than 1MB
    const largeFile = new File([new Array(1024 * 1024 + 1).join('a')], 'config.yaml', {
      type: 'text/yaml',
    });

    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [largeFile] },
    });

    await waitFor(() => {
      expect(screen.getByText(/不能超过 1MB/)).toBeInTheDocument();
    });
  });

  it('shows file preview after selecting valid file', async () => {
    renderDialog();

    const validFile = createMockFile('config.yaml', 1024);

    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [validFile] },
    });

    await waitFor(() => {
      expect(screen.getByText('config.yaml')).toBeInTheDocument();
    });
  });

  it('calls importConfig API when import button clicked', async () => {
    renderDialog();

    const validFile = createMockFile('config.yaml', 1024);
    vi.mocked(api.importConfig).mockResolvedValue({
      status: 'success',
      config: {},
      created_at: new Date().toISOString(),
    });

    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [validFile] },
    });

    await waitFor(() => {
      expect(screen.getByText('config.yaml')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('导入并应用'));

    await waitFor(() => {
      expect(api.importConfig).toHaveBeenCalledWith(validFile, '配置导入');
    });
  });

  it('calls onSuccess after successful import', async () => {
    renderDialog();

    const validFile = createMockFile('config.yaml', 1024);
    vi.mocked(api.importConfig).mockResolvedValue({
      status: 'success',
      config: {},
      created_at: new Date().toISOString(),
    });

    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [validFile] },
    });

    await waitFor(() => {
      expect(screen.getByText('config.yaml')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('导入并应用'));

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalled();
    });
  });

  it('shows error message when import fails', async () => {
    renderDialog();

    const validFile = createMockFile('config.yaml', 1024);
    vi.mocked(api.importConfig).mockRejectedValue(new Error('Invalid configuration'));

    const dropzone = screen.getByText(/点击或拖拽文件到此处/);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [validFile] },
    });

    await waitFor(() => {
      expect(screen.getByText('config.yaml')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('导入并应用'));

    await waitFor(() => {
      expect(screen.getByText('Invalid configuration')).toBeInTheDocument();
    });
  });

  it('allows entering custom description', async () => {
    renderDialog();

    const descriptionInput = screen.getByPlaceholderText('例如：配置导入');
    fireEvent.change(descriptionInput, { target: { value: 'Test description' } });

    expect(descriptionInput).toHaveValue('Test description');
  });

  it('disables import button when no file selected', () => {
    renderDialog();

    const importButton = screen.getByText('导入并应用');
    expect(importButton).toBeDisabled();
  });
});
