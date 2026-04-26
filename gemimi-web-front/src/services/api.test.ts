import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getRuntimeOrders } from './api';

describe('getRuntimeOrders', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('maps order_role=ENTRY -> role=ENTRY, raw_role=ENTRY, keeps type, default type is undefined', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          {
            order_id: '1',
            order_role: 'ENTRY',
            symbol: 'BTC/USDT',
            type: 'LIMIT',
            status: 'NEW',
            qty: 1,
            price: 50000,
            created_at: '2026-04-26T00:00:00Z'
          }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({
      role: 'ENTRY',
      raw_role: 'ENTRY',
      type: 'LIMIT'
    }));
  });

  it('maps order_role=TP1/TP2/TP5 -> role=TP, raw_role preserves original value', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'TP1', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '2', order_role: 'TP2', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '3', order_role: 'TP5', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP1' }));
    expect(orders[1]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP2' }));
    expect(orders[2]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP5' }));
  });

  it('maps order_role=SL -> role=SL, raw_role=SL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'SL', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'SL', raw_role: 'SL' }));
  });

  it('defaults to ENTRY if order_role is missing', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'ENTRY', raw_role: 'ENTRY' }));
  });

  it('does not depend on side to map TP/SL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        orders: [
          { order_id: '1', order_role: 'TP1', side: 'SELL', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 },
          { order_id: '2', order_role: 'SL', side: 'BUY', symbol: 'BTC/USDT', status: 'NEW', qty: 1, price: 50000 }
        ]
      })
    });

    const orders = await getRuntimeOrders();
    expect(orders[0]).toEqual(expect.objectContaining({ role: 'TP', raw_role: 'TP1' }));
    expect(orders[1]).toEqual(expect.objectContaining({ role: 'SL', raw_role: 'SL' }));
  });
});
