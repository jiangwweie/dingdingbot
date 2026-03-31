import useSWR from 'swr';
import { fetcher } from './api';
import type {
  OrderRequest,
  OrderResponse,
  OrderCancelResponse,
  CapitalProtectionCheckResult,
} from '../types/order';

/**
 * 订单列表查询参数
 */
export interface OrdersQueryParams {
  symbol?: string;
  status?: string;
  order_role?: string;
  strategy_name?: string;
  limit?: number;
  offset?: number;
}

/**
 * 订单列表响应
 */
export interface OrdersResponse {
  items: OrderResponse[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * 查询订单列表
 */
export async function fetchOrders(params?: OrdersQueryParams): Promise<OrdersResponse> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.status) queryParams.append('status', params.status);
  if (params?.order_role) queryParams.append('order_role', params.order_role);
  if (params?.strategy_name) queryParams.append('strategy_name', params.strategy_name);
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));

  const res = await fetch(`/api/v3/orders?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch orders');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 查询订单详情
 */
export async function fetchOrderDetails(orderId: string): Promise<OrderResponse> {
  const res = await fetch(`/api/v3/orders/${orderId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch order details');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 创建订单
 */
export async function createOrder(payload: OrderRequest): Promise<OrderResponse> {
  const res = await fetch('/api/v3/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to create order');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 取消订单
 */
export async function cancelOrder(orderId: string, symbol: string): Promise<OrderCancelResponse> {
  const res = await fetch(`/api/v3/orders/${orderId}?symbol=${encodeURIComponent(symbol)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to cancel order');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 下单前资金保护检查
 */
export async function checkOrder(payload: {
  symbol: string;
  order_type: string;
  quantity: string;
  price?: string;
  trigger_price?: string;
  stop_loss?: string;
}): Promise<CapitalProtectionCheckResult> {
  const res = await fetch('/api/v3/orders/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to check order');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 使用 SWR 获取订单列表
 */
export function useOrders(params?: OrdersQueryParams, refreshInterval = 10000) {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.status) queryParams.append('status', params.status);
  if (params?.order_role) queryParams.append('order_role', params.order_role);
  if (params?.strategy_name) queryParams.append('strategy_name', params.strategy_name);
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));

  const url = `/api/v3/orders?${queryParams}`;
  return useSWR<OrdersResponse>(url, fetcher, {
    refreshInterval,
    revalidateOnFocus: true,
  });
}

/**
 * 使用 SWR 获取订单详情
 */
export function useOrderDetails(orderId: string | null, refreshInterval = 5000) {
  const url = orderId ? `/api/v3/orders/${orderId}` : null;
  return useSWR<OrderResponse>(url, fetcher, {
    refreshInterval,
    revalidateOnFocus: true,
  });
}
