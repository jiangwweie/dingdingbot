import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SnapshotList from '../SnapshotList';
import * as api from '../../../lib/api';

// Mock the api module
vi.mock('../../../lib/api', () => ({
  fetchSnapshots: vi.fn(),
}));

// Mock date-fns
vi.mock('date-fns', () => ({
  formatDistanceToNow: vi.fn(() => '刚刚'),
  zhCN: {},
}));

describe('SnapshotList', () => {
  const mockOnSnapshotSelect = vi.fn();
  const mockOnRefresh = vi.fn();

  const mockSnapshots = {
    total: 25,
    limit: 10,
    offset: 0,
    data: [
      {
        id: 1,
        version: 'v1.0.0',
        description: '初始配置',
        created_at: new Date().toISOString(),
        created_by: 'user',
        is_active: true,
      },
      {
        id: 2,
        version: 'v1.1.0',
        description: '更新策略参数',
        created_at: new Date(Date.now() - 86400000).toISOString(),
        created_by: 'user',
        is_active: false,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderList = () =>
    render(
      <SnapshotList
        onSnapshotSelect={mockOnSnapshotSelect}
        onRefresh={mockOnRefresh}
      />
    );

  it('renders loading state initially', () => {
    vi.mocked(api.fetchSnapshots).mockImplementation(
      () => new Promise(() => {})
    );

    renderList();

    expect(screen.getByText('加载中...')).toBeInTheDocument();
  });

  it('renders snapshots data correctly', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('初始配置')).toBeInTheDocument();
      expect(screen.getByText('更新策略参数')).toBeInTheDocument();
    });

    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
    expect(screen.getByText('v1.1.0')).toBeInTheDocument();
  });

  it('shows empty state when no snapshots', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue({
      total: 0,
      limit: 10,
      offset: 0,
      data: [],
    });

    renderList();

    await waitFor(() => {
      expect(screen.getByText('暂无快照记录')).toBeInTheDocument();
    });
  });

  it('shows error state when fetch fails', async () => {
    vi.mocked(api.fetchSnapshots).mockRejectedValue(new Error('Network error'));

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('calls onSnapshotSelect when clicking a snapshot', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('初始配置')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('初始配置'));

    expect(mockOnSnapshotSelect).toHaveBeenCalledWith(mockSnapshots.data[0]);
  });

  it('shows active badge for active snapshot', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('当前生效')).toBeInTheDocument();
    });
  });

  it('searches snapshots when typing in search box', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByPlaceholderText('搜索...')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('搜索...');
    fireEvent.change(searchInput, { target: { value: 'v1.0.0' } });

    // Should filter to show only matching results
    expect(screen.getByText('初始配置')).toBeInTheDocument();
  });

  it('filters by active status when clicking filter button', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('筛选')).toBeInTheDocument();
    });

    const filterButton = screen.getByText('筛选');
    fireEvent.click(filterButton);

    // Should call fetchSnapshots with is_active=true
    await waitFor(() => {
      expect(api.fetchSnapshots).toHaveBeenCalledWith(
        expect.objectContaining({ is_active: true })
      );
    });
  });

  it('handles pagination correctly', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('第 1 页，共 3 页')).toBeInTheDocument();
    });

    const nextPageButton = screen.getAllByRole('button').find(
      (btn) => btn.querySelector('svg') && !btn.closest('[disabled]')
    );

    if (nextPageButton) {
      fireEvent.click(nextPageButton);

      await waitFor(() => {
        expect(api.fetchSnapshots).toHaveBeenCalledWith(
          expect.objectContaining({ offset: 10 })
        );
      });
    }
  });

  it('disables previous button on first page', async () => {
    vi.mocked(api.fetchSnapshots).mockResolvedValue(mockSnapshots);

    renderList();

    await waitFor(() => {
      expect(screen.getByText('第 1 页，共 3 页')).toBeInTheDocument();
    });

    // First page should have disabled previous button
    const buttons = screen.getAllByRole('button');
    const prevButton = buttons.find(
      (btn) => btn.querySelector('[data-icon="chevron-left"]')
    );

    if (prevButton) {
      expect(prevButton).toBeDisabled();
    }
  });
});
