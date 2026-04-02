import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ExportButton from '../ExportButton';
import * as api from '../../../lib/api';

// Mock the api module
vi.mock('../../../lib/api', () => ({
  exportConfig: vi.fn(),
}));

// Mock Blob
class MockBlob {
  constructor() {}
}
global.Blob = MockBlob as any;

// Mock URL
const mockCreateObjectURL = vi.fn(() => 'blob:test-url');
const mockRevokeObjectURL = vi.fn();
global.URL.createObjectURL = mockCreateObjectURL;
global.URL.revokeObjectURL = mockRevokeObjectURL;

// Mock document.createElement for download link
const mockClick = vi.fn();
const mockRemove = vi.fn();
const mockAppendChild = vi.fn();

describe('ExportButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock link element
    const mockLink = {
      click: mockClick,
      remove: mockRemove,
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
    };
    vi.spyOn(document, 'createElement').mockReturnValue(mockLink as any);
    vi.spyOn(document.body, 'appendChild').mockImplementation(mockAppendChild);
    vi.spyOn(document.body, 'removeChild').mockImplementation(mockRemove);
  });

  it('renders correctly', () => {
    render(<ExportButton />);

    expect(screen.getByText('导出配置')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('shows loading state when exporting', async () => {
    vi.mocked(api.exportConfig).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(new Blob()), 100))
    );

    render(<ExportButton />);

    const button = screen.getByRole('button');
    fireEvent.click(button);

    expect(screen.getByText('导出中...')).toBeInTheDocument();
    expect(button).toBeDisabled();

    await waitFor(() => {
      expect(screen.getByText('导出配置')).toBeInTheDocument();
    });
  });

  it('calls exportConfig API when clicked', async () => {
    vi.mocked(api.exportConfig).mockResolvedValue(new Blob());

    render(<ExportButton />);

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(api.exportConfig).toHaveBeenCalledTimes(1);
    });
  });

  it('triggers file download after successful export', async () => {
    vi.mocked(api.exportConfig).mockResolvedValue(new Blob());

    render(<ExportButton />);

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalled();
      expect(mockClick).toHaveBeenCalled();
      expect(mockRevokeObjectURL).toHaveBeenCalled();
    });
  });

  it('shows error message when export fails', async () => {
    vi.mocked(api.exportConfig).mockRejectedValue(new Error('Network error'));

    render(<ExportButton />);

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('disables button while loading', async () => {
    vi.mocked(api.exportConfig).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<ExportButton />);

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeDisabled();
    });
  });
});
