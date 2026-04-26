import React from 'react';
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
  });

  it('Execution 页面展示 raw_role, and handles missing price showing 市价(type)', async () => {
    (api.getRuntimeOrders as any).mockResolvedValue([
      {
        order_id: '1',
        role: 'TP',
        raw_role: 'TP2',
        symbol: 'BTC/USDT',
        type: 'MARKET',
        status: 'NEW',
        quantity: 1,
        price: null,
        updated_at: '2026-04-26T00:00:00Z'
      }
    ]);

    render(<Execution />);
    
    await waitFor(() => {
      expect(screen.getByText('TP2')).toBeInTheDocument();
      expect(screen.getByText('市价 (MARKET)')).toBeInTheDocument();
    });
  });

  it('Execution 页面展示 role if raw_role is not available, and formats price', async () => {
    (api.getRuntimeOrders as any).mockResolvedValue([
      {
        order_id: '2',
        role: 'ENTRY',
        raw_role: undefined,
        symbol: 'BTC/USDT',
        type: 'LIMIT',
        status: 'FILLED',
        quantity: 2,
        price: 50000.5,
        updated_at: '2026-04-26T00:00:00Z'
      }
    ]);

    render(<Execution />);
    
    await waitFor(() => {
      expect(screen.getByText('ENTRY')).toBeInTheDocument();
      expect(screen.getByText('50000.50')).toBeInTheDocument();
    });
  });
});
