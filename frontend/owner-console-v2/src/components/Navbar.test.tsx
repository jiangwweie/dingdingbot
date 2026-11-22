// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Navbar } from './Navbar';
import { ThemeProvider } from '../context/ThemeContext';
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;
beforeEach(() => { vi.stubGlobal('matchMedia', () => ({ matches: false })); localStorage.clear(); });
afterEach(() => { act(() => root?.unmount()); container?.remove(); vi.unstubAllGlobals(); });
function render(isRealData: boolean, onSelectTab = vi.fn(), isIsolatedMock = false) {
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  act(() => root.render(<ThemeProvider><Navbar activeTab="overview" onSelectTab={onSelectTab} isRealData={isRealData} isIsolatedMock={isIsolatedMock} /></ThemeProvider>));
  return onSelectTab;
}
it('keeps all five navigation destinations available on mobile without control submission', () => {
  const select=render(true);const nav=container.querySelector('nav[aria-label="移动主导航"]');
  expect(nav).not.toBeNull();expect(nav?.querySelectorAll('button')).toHaveLength(5);
  const controls=[...nav!.querySelectorAll('button')].find(b=>b.textContent==='主控中心')!;
  act(()=>controls.click());expect(select).toHaveBeenCalledExactlyOnceWith('controls');
});
it('does not label unavailable production data as a mock environment', () => {
  render(false);expect(container.textContent).toContain('数据未就绪');expect(container.textContent).not.toMatch(/MOCK|离线验证/);
});

it('explicitly identifies fixtures in the isolated browser preview', () => {
  render(false, vi.fn(), true);
  expect(container.textContent).toContain('ISOLATED MOCK');
  expect(container.querySelector('[aria-label="移动主导航"]')).not.toBeNull();
});
