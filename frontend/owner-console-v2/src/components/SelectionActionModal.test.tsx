// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  SelectionActionModal,
  type SelectionActionModalProps,
} from './SelectionActionModal';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function setInputValue(input: HTMLInputElement, value: string) {
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value'
  )?.set;
  nativeInputValueSetter?.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function renderModal(props: Partial<SelectionActionModalProps> = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  const defaultProps: SelectionActionModalProps = {
    open: true,
    onClose: vi.fn(),
    groupId: 'CPM-RO-001',
    action: 'dynamic',
    expectedVersion: 3,
    cadenceHours: 4,
    effectivePeriodAnchorMs: 1800007200000,
    nextEligibilityNotBeforeMs: 1800010800000,
    rollbackBaselineId: 'baseline-v1',
    selectionEpochId: 'epoch-20261021',
    isSubmitting: false,
    isUnknownResult: false,
    isVerifying: false,
    errorMessage: null,
    onConfirm: vi.fn(),
    onVerifyStatus: vi.fn(),
    ...props,
  };

  act(() => {
    root.render(<SelectionActionModal {...defaultProps} />);
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

describe('SelectionActionModal', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders dynamic mode title, anchor, and enables submit when TOTP and reason are filled', () => {
    const onConfirm = vi.fn();
    renderModal({ action: 'dynamic', onConfirm });

    const modal = document.body.querySelector('[data-testid="selection-action-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('CPM-RO-001 激活动态选币授权');
    expect(modal?.textContent).toContain('DYNAMIC 动态打分轮动');
    expect(modal?.textContent).toContain('周期: 4h');

    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    expect(submitBtn.disabled).toBe(true);

    act(() => {
      setInputValue(totpInput, '123456');
    });

    expect(submitBtn.disabled).toBe(false);

    act(() => {
      submitBtn.click();
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        totp: '123456',
        reason: 'Owner 激活动态选币授权',
      })
    );
  });

  it('renders static mode with rollback baseline and blocks submit if baseline is missing', () => {
    renderModal({
      action: 'static',
      rollbackBaselineId: null,
      selectionEpochId: null,
    });

    const modal = document.body.querySelector('[data-testid="selection-action-modal"]');
    expect(modal?.textContent).toContain('CPM-RO-001 回退已认证静态基线');
    expect(modal?.textContent).toContain('缺少静态回退基线');

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
    expect(submitBtn.textContent).toContain('缺少回退基线，禁止提交');
  });

  it('renders unknown result lockdown banner and verification button', () => {
    const onVerifyStatus = vi.fn();
    renderModal({
      isUnknownResult: true,
      onVerifyStatus,
    });

    const modal = document.body.querySelector('[data-testid="selection-action-modal"]');
    expect(modal?.textContent).toContain('选币授权结果未知（闭锁保护）');

    const verifyBtn = Array.from(modal?.querySelectorAll('button') ?? []).find((b) =>
      b.textContent?.includes('核验权威状态 (GET)')
    );
    expect(verifyBtn).toBeDefined();

    act(() => {
      verifyBtn?.click();
    });

    expect(onVerifyStatus).toHaveBeenCalledTimes(1);

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
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
