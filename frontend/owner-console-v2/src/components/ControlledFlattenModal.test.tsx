// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  ControlledFlattenModal,
  type ControlledFlattenModalProps,
} from './ControlledFlattenModal';
import type { FlattenPreview } from '../api/controlsApi';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

const mockPreview: FlattenPreview = {
  venue_id: 'binance-usdm',
  account_id: 'owner-main',
  owner_policy_version: 7,
  global_entry_enabled: true,
  ticket_ids: ['ticket:btc-long', 'ticket:eth-short'],
  ticket_states: {
    'ticket:btc-long': 'eligible',
    'ticket:eth-short': 'eligible',
  },
  snapshot_digest: 'sha256:' + 'e'.repeat(64),
  first_blocker: null,
  runtime_profile_id: 'account-wide',
};

function renderModal(props: Partial<ControlledFlattenModalProps> = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  const defaultProps: ControlledFlattenModalProps = {
    open: true,
    onClose: vi.fn(),
    preview: mockPreview,
    isSubmitting: false,
    isVerifying: false,
    errorMessage: null,
    isUnknownResult: false,
    onConfirm: vi.fn(),
    onVerifyStatus: vi.fn(),
    onRefreshPreview: vi.fn(),
    ...props,
  };

  act(() => {
    root.render(<ControlledFlattenModal {...defaultProps} />);
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

describe('ControlledFlattenModal', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders modal content, affected tickets, and disables submit initially', () => {
    renderModal();

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('确认受控平仓全部仓位');
    expect(modal?.textContent).toContain('ticket:btc-long');
    expect(modal?.textContent).toContain('ticket:eth-short');

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn).toBeDefined();
    expect(submitBtn?.disabled).toBe(true);
  });

  it('enables submit button only when TOTP has 6 digits and exact confirmation text is entered', () => {
    renderModal();

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    // Enter partial TOTP
    act(() => {
      setInputValue(totpInput, '123');
    });
    expect(submitBtn?.disabled).toBe(true);

    // Enter full TOTP
    act(() => {
      setInputValue(totpInput, '123456');
    });
    expect(submitBtn?.disabled).toBe(true);

    // Enter matching confirmation text
    act(() => {
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    expect(submitBtn?.disabled).toBe(false);
  });

  it('disables submit and displays blocker warning when first_blocker is present', () => {
    const blockedPreview: FlattenPreview = {
      ...mockPreview,
      first_blocker: 'ticket_not_flattenable:ticket:btc:entry_pending',
    };
    renderModal({ preview: blockedPreview });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(modal?.textContent).toContain('存在不可平仓的中间态持仓');
    expect(modal?.textContent).toContain('ticket_not_flattenable:ticket:btc:entry_pending');

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn?.disabled).toBe(true);
  });

  it('renders unknown result lockdown banner and verification button when isUnknownResult is true', () => {
    const onVerifyStatus = vi.fn();
    renderModal({
      isUnknownResult: true,
      onVerifyStatus,
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(modal?.textContent).toContain('平仓结果未知（闭锁保护）');
    expect(modal?.textContent).toContain('核验权威状态 (GET)');

    const verifyBtn = Array.from(modal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态 (GET)')
    );
    expect(verifyBtn).toBeDefined();

    act(() => {
      verifyBtn?.click();
    });
    expect(onVerifyStatus).toHaveBeenCalledTimes(1);

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn?.disabled).toBe(true);
  });

  it('handles Escape key to close modal when not submitting', () => {
    const onClose = vi.fn();
    renderModal({ onClose });

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT close on Escape when isSubmitting is true', () => {
    const onClose = vi.fn();
    renderModal({ onClose, isSubmitting: true });

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    expect(onClose).not.toHaveBeenCalled();
  });
});
