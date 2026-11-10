// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { RecentAttentionSection } from './RecentAttentionSection';
import type { AttentionItem } from '../../types/overview';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

function render(props: {
  attentionList: AttentionItem[];
  incidentsCount: number;
  conclusion: 'no_action' | 'attention' | 'intervention';
}) {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<RecentAttentionSection {...props} />);
  });
}

describe('RecentAttentionSection Truthful Rendering', () => {
  it('renders attention item when global entry is paused even if conclusion is no_action and incidents is 0', () => {
    render({
      attentionList: [
        {
          id: 'global-entry-paused',
          type: 'warning',
          title: '全局 ENTRY 入场处于暂停状态',
          detail: '新入场被阻断，存量持仓继续受生命周期保护。',
        },
      ],
      incidentsCount: 0,
      conclusion: 'no_action',
    });

    expect(container.textContent).toContain('全局 ENTRY 入场处于暂停状态');
    expect(container.textContent).toContain('新入场被阻断，存量持仓继续受生命周期保护');
    expect(container.textContent).toContain('当前无需 Owner 操作');
    expect(container.textContent).not.toContain('一切正常');
    expect(container.textContent).not.toContain('全局准入畅通');
  });

  it('renders calm clear state only when attentionList is empty, incidents is 0, and conclusion is no_action', () => {
    render({
      attentionList: [],
      incidentsCount: 0,
      conclusion: 'no_action',
    });

    expect(container.textContent).toContain('运行平稳 · 暂无关注项');
    expect(container.textContent).toContain('当前快照暂无需 Owner 介入处置的提示');
    expect(container.textContent).not.toContain('全局准入畅通');
    // Regression check: Never make claims about protection completeness or generic everything-ok
    expect(container.textContent).not.toContain('保护策略处于健康状态');
    expect(container.textContent).not.toContain('一切正常，无需介入');
  });

  it('distinguishes intervention conclusion properly', () => {
    render({
      attentionList: [
        {
          id: 'manual-alert',
          type: 'alert',
          title: 'BTCUSDT 触发人工接管',
        },
      ],
      incidentsCount: 1,
      conclusion: 'intervention',
    });

    expect(container.textContent).toContain('需 Owner 紧急介入');
    expect(container.textContent).toContain('BTCUSDT 触发人工接管');
    expect(container.textContent).toContain('1 项异常 · 需关注');
  });
});

it('does not claim healthy current facts when the displayed snapshot is stale', () => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<RecentAttentionSection attentionList={[]} incidentsCount={0} conclusion="no_action" freshness="stale" />));
  expect(container.textContent).not.toContain('运行平稳 · 暂无关注项');
  expect(container.textContent).not.toContain('PostgreSQL 与只读事实核验无脱节');
  expect(container.textContent).toContain('当前快照已滞后');
});
