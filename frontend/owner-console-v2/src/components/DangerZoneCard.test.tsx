// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DangerZoneCard, type DangerZoneCardProps } from './DangerZoneCard';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderCard(props: Partial<DangerZoneCardProps> = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  const defaultProps: DangerZoneCardProps = {
    activeTicketCount: 2,
    onTriggerFlatten: vi.fn(),
    isLoading: false,
    ...props,
  };

  act(() => {
    root.render(<DangerZoneCard {...defaultProps} />);
  });

  return {
    container,
    props: defaultProps,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

describe('DangerZoneCard', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders card title, ticket count, and button triggers flatten preview', () => {
    const onTriggerFlatten = vi.fn();
    const { container } = renderCard({ activeTicketCount: 3, onTriggerFlatten });

    expect(container.textContent).toContain('受控平仓全部仓位');
    expect(container.textContent).toContain('受控平仓全部仓位 (3)');

    const button = container.querySelector('[data-testid="danger-zone-flatten-btn"]') as HTMLButtonElement;
    expect(button).toBeDefined();
    expect(button.disabled).toBe(false);

    act(() => {
      button.click();
    });

    expect(onTriggerFlatten).toHaveBeenCalledTimes(1);
  });

  it('shows loading state when isLoading is true', () => {
    const { container } = renderCard({ isLoading: true });

    const button = container.querySelector('[data-testid="danger-zone-flatten-btn"]') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('读取权威快照...');
  });

  it('displays active operation state when currentOperation is provided', () => {
    const mockOperation: any = {
      authorization_id: 'auth-1',
      operation_kind: 'flatten_all',
      state: 'exits_requested',
      version: 2,
    };

    const { container } = renderCard({ currentOperation: mockOperation });

    expect(container.textContent).toContain('进行中: exits_requested');
    const button = container.querySelector('[data-testid="danger-zone-flatten-btn"]') as HTMLButtonElement;
    expect(button.textContent).toContain('平仓进行中 (exits_requested) · 查看进度');
  });
});
