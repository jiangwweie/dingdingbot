// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { GoogleLogin, GoogleOwnerBinding } from './GoogleAuth';
import * as api from '../../api/authApi';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const roots: ReturnType<typeof createRoot>[] = [];
beforeEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ''; window.history.replaceState(null, '', '/trading/'); });
afterEach(() => { act(() => roots.splice(0).forEach(root => root.unmount())); });
async function render(node: React.ReactNode) {
  const element = document.createElement('div'); document.body.append(element);
  const root = createRoot(element); roots.push(root);
  await act(async () => { root.render(node); });
  return element;
}

it('shows Google login only when the server reports a pinned Owner', async () => {
  vi.spyOn(api, 'getAuthProviders').mockResolvedValue({ google_login: true, google_binding: false });
  const el = await render(<GoogleLogin />);
  expect(el.querySelector('a')?.getAttribute('href')).toBe('/api/owner/v1/auth/google/start');
  expect(el.textContent).toContain('敏感控制仍需 TOTP');
});

it('retains original login when Google is disabled or unavailable', async () => {
  vi.spyOn(api, 'getAuthProviders').mockRejectedValue(new Error('unavailable'));
  const el = await render(<GoogleLogin />);
  expect(el.querySelector('a')).toBeNull();
});

it('shows callback rejection without exposing provider token values', async () => {
  window.history.replaceState(null, '', '/trading/?google_result=error');
  vi.spyOn(api, 'getAuthProviders').mockResolvedValue({ google_login: true, google_binding: false });
  const el = await render(<GoogleLogin />);
  expect(el.querySelector('[role="alert"]')?.textContent).toContain('身份不匹配');
});

it('binding requires TOTP and is not described as already enabled', async () => {
  vi.spyOn(api, 'getAuthProviders').mockResolvedValue({ google_login: false, google_binding: true });
  const el = await render(<GoogleOwnerBinding />);
  expect((el.querySelector('button') as HTMLButtonElement).disabled).toBe(true);
  expect(el.textContent).toContain('不会改变交易控制');
});

it('verified binding presents only the server verified subject for explicit pinning', async () => {
  window.history.replaceState(null, '', '/trading/?google_result=binding');
  vi.spyOn(api, 'getAuthProviders').mockResolvedValue({ google_login: false, google_binding: true });
  vi.spyOn(api, 'getGoogleBinding').mockResolvedValue({ subject: 'verified-owner-subject', email: 'owner@example.com' });
  const el = await render(<GoogleOwnerBinding />);
  expect(el.textContent).toContain('verified-owner-subject');
  expect(el.textContent).toContain('尚未启用 Google 登录');
  expect(el.querySelector('input')).toBeNull();
});
