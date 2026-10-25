// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { DirectionalRiskCard } from './DirectionalRiskCard';
const mocks = vi.hoisted(() => ({ fetch: vi.fn(), change: vi.fn(), receipt: vi.fn() }));
vi.mock('../../api/directionalRiskApi', () => ({ fetchDirectionalRisk: mocks.fetch, changeDirectionalRisk: mocks.change, fetchDirectionalReceipt: mocks.receipt }));
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;
afterEach(() => { act(() => root?.unmount()); container?.remove(); vi.resetAllMocks(); sessionStorage.clear(); });
function render() { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); act(() => root.render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DirectionalRiskCard /></QueryClientProvider>)); }
const state = { control: { venue_id: 'binance-usdm', account_id: 'test', version: 2, view: 'neutral', pending_view: 'bearish', effective_at_ms: 1000 }, long_limit: '0.04', short_limit: '0.04', long_risk_at_stop: '12', short_risk_at_stop: '0', review_due: true };
it('shows pending as pending and blocks another mutation', async () => {
  mocks.fetch.mockResolvedValue(state); render();
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toContain('切换中')); });
  expect(container.textContent).toContain('当前仍为中性');
  expect(container.textContent).toContain('建议复核');
  expect(container.textContent).toContain('已授权的 Crypto 新开仓');
  expect([...container.querySelectorAll('button')].filter(b => ['偏多','中性','偏空'].includes(b.textContent || '')).every(b => b.disabled)).toBe(true);
});
it('does not display neutral when the authority read fails', async () => {
  mocks.fetch.mockRejectedValue(new Error('unavailable')); render();
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toContain('无法读取方向风险控制')); });
  expect(container.textContent).not.toContain('当前：中性');
  expect(mocks.change).not.toHaveBeenCalled();
});

function unresolved() {
  sessionStorage.setItem('brc-directional-risk-pending', JSON.stringify({scopeKey:'binance-usdm:test', view:'bearish',expected_version:1,idempotency_key:'frozen-request',reason:'outlook'}));
}
async function verify() {
  await act(async () => { await vi.waitFor(() => expect(container.textContent).toContain('当前仍为中性')); });
  const button = [...document.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent?.includes('核验权威状态'))!;
  await act(async () => { button.click(); await Promise.resolve(); });
}
it('verifies the exact lost response without sending a second mutation', async () => {
  unresolved(); mocks.fetch.mockResolvedValue(state); mocks.receipt.mockResolvedValue({result:state.control,current:state.control});render();
  await verify();
  expect(mocks.receipt).toHaveBeenCalledWith('frozen-request');
  expect(mocks.change).not.toHaveBeenCalled();
  expect(sessionStorage.getItem('brc-directional-risk-pending')).toBeNull();
});
it('keeps the request frozen when no authoritative receipt exists yet', async () => {
  unresolved();mocks.fetch.mockResolvedValue(state);mocks.receipt.mockResolvedValue({result:null,current:{...state.control,version:1}});render();
  await verify();
  expect(sessionStorage.getItem('brc-directional-risk-pending')).toContain('frozen-request');
  expect(document.body.textContent).toContain('尚未查到原请求回执');
  expect(mocks.change).not.toHaveBeenCalled();
});
it('never reuses an unresolved mutation on another account', async () => {
  unresolved();mocks.fetch.mockResolvedValue(state);mocks.receipt.mockResolvedValue({result:state.control,current:{...state.control,account_id:'other'}});render();
  await verify();
  expect(sessionStorage.getItem('brc-directional-risk-pending')).toContain('frozen-request');
  expect(document.body.textContent).toContain('当前账户与原请求不同');
});
