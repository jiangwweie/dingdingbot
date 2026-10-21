// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopStatusBar } from './TopStatusBar';
import { TotpActionModal } from './TotpActionModal';
import { useGlobalEntryControl, _resetInFlightGlobalEntryRegistry } from '../hooks/useGlobalEntryControl';
import * as controlsApi from '../api/controlsApi';
import type { GlobalEntryState } from '../types/controls';

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

const TestGlobalEntryContainer: React.FC<{
  initialGlobalEntry: GlobalEntryState;
  activeFlattenOperation?: any;
  onSuccess?: (msg: string) => void;
}> = ({ initialGlobalEntry, activeFlattenOperation, onSuccess }) => {
  const globalControl = useGlobalEntryControl({
    onSuccess,
    activeFlattenOperation,
  });

  return (
    <div>
      <TopStatusBar
        globalEntry={initialGlobalEntry}
        pausedStrategyCount={1}
        totalActiveStrategies={4}
        onRequestAction={globalControl.requestAction}
        isActionDisabled={Boolean(
          activeFlattenOperation &&
          activeFlattenOperation.state !== 'completed' &&
          activeFlattenOperation.state !== 'blocked'
        )}
        disabledReason={
          activeFlattenOperation &&
          activeFlattenOperation.state !== 'completed' &&
          activeFlattenOperation.state !== 'blocked'
            ? '受控平仓正在执行中，禁止操作全局新开仓准入'
            : undefined
        }
      />
      <TotpActionModal {...globalControl.modalProps} />
    </div>
  );
};

describe('TopStatusBarGlobalEntry Integration', () => {
  let queryClient: QueryClient;

  const createWrapper = () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    _resetInFlightGlobalEntryRegistry();
    document.body.innerHTML = '';
  });

  it('triggers Pause flow: opens modal, TOTP not required, submits and updates status', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseGlobalEntry').mockResolvedValue({
      configured_state: 'paused',
      effective_state: 'paused',
      version: 7,
      updated_at_ms: 1800000000000,
    });

    const initialEntry: GlobalEntryState = {
      configured_state: 'enabled',
      effective_state: 'enabled',
      policy_version: 6,
      active_ticket_count: 2,
    };

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const Wrapper = createWrapper();

    const onSuccess = vi.fn();

    act(() => {
      root.render(
        <Wrapper>
          <TestGlobalEntryContainer initialGlobalEntry={initialEntry} onSuccess={onSuccess} />
        </Wrapper>
      );
    });

    // 1. Click Pause button in TopStatusBar
    const pauseBtn = Array.from(document.body.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('暂停全局新准入')
    );
    expect(pauseBtn).toBeDefined();

    act(() => {
      pauseBtn?.click();
    });

    // 2. Modal opens
    const modal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('暂停全局新交易准入');
    expect(modal?.textContent).toContain('当前基线版本: v6');

    // TOTP input should NOT be present for pause!
    const totpInput = modal?.querySelector('input[placeholder="000000"]');
    expect(totpInput).toBeNull();

    // 3. Confirm Pause
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);

    await act(async () => {
      submitBtn.click();
    });

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    expect(pauseSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version: 6,
        totp_code: null,
      })
    );
    expect(onSuccess).toHaveBeenCalledWith(expect.stringContaining('全局 ENTRY 已成功暂停 [v7]'));
  });

  it('triggers Resume flow: opens modal, requires 6-digit TOTP, submits step-up', async () => {
    const resumeSpy = vi.spyOn(controlsApi, 'resumeGlobalEntry').mockResolvedValue({
      configured_state: 'enabled',
      effective_state: 'enabled',
      version: 8,
      updated_at_ms: 1800000005000,
    });

    const initialEntry: GlobalEntryState = {
      configured_state: 'paused',
      effective_state: 'paused',
      policy_version: 7,
      active_ticket_count: 0,
    };

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const Wrapper = createWrapper();

    act(() => {
      root.render(
        <Wrapper>
          <TestGlobalEntryContainer initialGlobalEntry={initialEntry} />
        </Wrapper>
      );
    });

    // 1. Click Resume button
    const resumeBtn = Array.from(document.body.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('恢复全局新准入')
    );
    expect(resumeBtn).toBeDefined();

    act(() => {
      resumeBtn?.click();
    });

    const modal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modal?.textContent).toContain('恢复全局新交易准入');

    // TOTP input MUST be present for resume
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    expect(totpInput).not.toBeNull();

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);

    // Enter 6-digit TOTP
    act(() => {
      setInputValue(totpInput, '654321');
    });
    expect(submitBtn.disabled).toBe(false);

    await act(async () => {
      submitBtn.click();
    });

    expect(resumeSpy).toHaveBeenCalledTimes(1);
    expect(resumeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version: 7,
        totp_code: '654321',
      })
    );
  });

  it('disables toggle button when an active flatten operation is in progress', () => {
    const initialEntry: GlobalEntryState = {
      configured_state: 'paused',
      effective_state: 'paused',
      policy_version: 7,
      active_ticket_count: 2,
    };

    const activeFlatten = {
      authorization_id: 'owner-auth:flat-run',
      state: 'pending',
    };

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const Wrapper = createWrapper();

    act(() => {
      root.render(
        <Wrapper>
          <TestGlobalEntryContainer
            initialGlobalEntry={initialEntry}
            activeFlattenOperation={activeFlatten}
          />
        </Wrapper>
      );
    });

    const resumeBtn = Array.from(document.body.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('恢复全局新准入')
    );
    expect(resumeBtn?.disabled).toBe(true);
    expect(resumeBtn?.title).toContain('受控平仓正在执行中');
  });
});
