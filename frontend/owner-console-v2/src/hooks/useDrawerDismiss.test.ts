// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleDrawerGlobalKeyDown, drawerStack } from './useDrawerDismiss';

describe('useDrawerDismiss handleDrawerGlobalKeyDown', () => {
  beforeEach(() => {
    drawerStack.length = 0;
    document.body.innerHTML = '';
  });

  it('pops and closes topmost drawer when Escape is pressed and no modal is open', () => {
    const closeDrawerSpy = vi.fn();
    drawerStack.push({
      id: 'strategy-detail-drawer',
      onClose: closeDrawerSpy,
      triggerElement: null,
    });

    const event = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });

    const handled = handleDrawerGlobalKeyDown(event);
    expect(handled).toBe(true);
    expect(closeDrawerSpy).toHaveBeenCalledTimes(1);
    expect(drawerStack.length).toBe(0);
  });

  it('does NOT close drawer when an overlay modal (TotpActionModal) is open in DOM', () => {
    const closeDrawerSpy = vi.fn();
    drawerStack.push({
      id: 'strategy-detail-drawer',
      onClose: closeDrawerSpy,
      triggerElement: null,
    });

    // Modal dialog is present in DOM
    const modalEl = document.createElement('div');
    modalEl.setAttribute('data-testid', 'totp-action-modal');
    modalEl.setAttribute('role', 'alertdialog');
    document.body.appendChild(modalEl);

    const event = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });

    const handled = handleDrawerGlobalKeyDown(event);

    // Must return false so the modal gets to handle Escape without drawer being dismissed
    expect(handled).toBe(false);
    expect(closeDrawerSpy).not.toHaveBeenCalled();
    expect(drawerStack.length).toBe(1);
  });
});
