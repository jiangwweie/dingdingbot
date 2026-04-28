// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import Execution from './Execution';
import * as api from '@/src/services/api';

vi.mock('@/src/services/api', () => ({
  getRuntimeExecutionIntents: vi.fn(),
  getRuntimeOrders: vi.fn(),
}));

vi.mock('@/src/components/layout/AppLayout', () => ({
  useRefreshContext: () => ({ refreshCount: 0 }),
}));

describe('Execution Page', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (api.getRuntimeExecutionIntents as any).mockResolvedValue([]);
    (api.getRuntimeOrders as any).mockResolvedValue([]);
  });

  it('shows loading state then renders order with raw_role and market type', async () => {
    (api.getRuntimeOrders as any).mockResolvedValue([
      {
        order_id: '1',
        role: 'TP',
        raw_role: 'TP2',
        symbol: 'BTC/USDT:USDT',
        type: 'MARKET',
        status: 'NEW',
        quantity: 1,
        price: null,
        updated_at: '2026-04-26T00:00:00Z',
      },
    ]);

    render(<Execution />);

    await waitFor(() => {
      expect(screen.getByText('TP2')).toBeInTheDocument();
      expect(screen.getByText('市价 (MARKET)')).toBeInTheDocument();
    });
  });

  it('shows role when raw_role is missing, and formats price', async () => {
    (api.getRuntimeOrders as any).mockResolvedValue([
      {
        order_id: '2',
        role: 'ENTRY',
        raw_role: undefined,
        symbol: 'BTC/USDT:USDT',
        type: 'LIMIT',
        status: 'FILLED',
        quantity: 2,
        price: 50000.5,
        updated_at: '2026-04-26T00:00:00Z',
      },
    ]);

    render(<Execution />);

    await waitFor(() => {
      expect(screen.getByText('ENTRY')).toBeInTheDocument();
      expect(screen.getByText('50000.50')).toBeInTheDocument();
    });
  });

  it('shows empty state when no intents and no orders', async () => {
    render(<Execution />);

    await waitFor(() => {
      const emptyTexts = screen.getAllByText(/暂无/);
      expect(emptyTexts.length).toBeGreaterThanOrEqual(2);
    });
  });
});
