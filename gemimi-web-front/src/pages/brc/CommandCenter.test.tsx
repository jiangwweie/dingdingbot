// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OperationPreflightModal } from './CommandCenter';
import type { OperationPreflightState } from './CommandCenter';

const mockBrcApi = vi.hoisted(() => ({
  confirmOperation: vi.fn(),
  cancelOperation: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

function planningState(operationType: 'emergency_flatten' | 'emergency_stop_runtime'): OperationPreflightState {
  return {
    loading: false,
    phrase: '',
    error: null,
    result: null,
    preflight: {
      operation_id: `op-${operationType}`,
      preflight_id: `pre-${operationType}`,
      operation_type: operationType,
      decision: 'unavailable',
      summary: operationType === 'emergency_flatten'
        ? 'Emergency flatten preflight planning only.'
        : 'Emergency stop runtime preflight planning only.',
      before: {},
      after: {
        planning_only: true,
        actual_execution_available: false,
        estimated_flatten_impact: operationType === 'emergency_flatten' ? { planned_result_status: 'noop' } : undefined,
        expected_stop_behavior: operationType === 'emergency_stop_runtime'
          ? { does_not_flatten: true, does_not_cancel_orders: true }
          : undefined,
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: {},
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: [],
        blockers: [`${operationType} executor unavailable; this preflight is planning only`],
      },
      confirmation_requirement: {
        required: false,
        phrase: null,
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: `idem-${operationType}`,
      status: 'blocked',
    },
  };
}

function executableStopState(): OperationPreflightState {
  return {
    loading: false,
    phrase: 'CONFIRM_STOP_RUNTIME',
    error: null,
    result: null,
    preflight: {
      operation_id: 'op-emergency_stop_runtime',
      preflight_id: 'pre-emergency_stop_runtime',
      operation_type: 'emergency_stop_runtime',
      decision: 'allow',
      summary: 'Plan emergency runtime stop through Operation authorization; it does not flatten or cancel orders.',
      before: { runtime_state: 'armed' },
      after: {
        planning_only: false,
        actual_execution_available: true,
        does_not_flatten: true,
        does_not_cancel_orders: true,
        expected_stop_behavior: {
          would_stop_runtime: true,
          would_pause_new_strategy_actions: true,
          does_not_flatten: true,
          does_not_cancel_orders: true,
        },
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: { current_runtime_state: 'armed' },
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: [],
        blockers: [],
      },
      confirmation_requirement: {
        required: true,
        phrase: 'CONFIRM_STOP_RUNTIME',
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: 'idem-emergency_stop_runtime',
      status: 'awaiting_confirmation',
    },
  };
}

function flattenDryRunState(): OperationPreflightState {
  return {
    loading: false,
    phrase: 'CONFIRM_FLATTEN_DRY_RUN',
    error: null,
    result: null,
    preflight: {
      operation_id: 'op-emergency_flatten',
      preflight_id: 'pre-emergency_flatten',
      operation_type: 'emergency_flatten',
      decision: 'warn',
      summary: 'Generate and confirm an emergency flatten dry-run record only.',
      before: {},
      after: {
        dry_run_only: true,
        actual_execution: false,
        actual_execution_available: false,
        dry_run_plan: {
          dry_run_id: 'flatdry-test',
          cancel_order_candidates: [
            {
              candidate_id: 'cancel_candidate_1',
              candidate_type: 'cancel_open_order',
              candidate_only: true,
              executable_order_request: false,
            },
          ],
          close_position_candidates: [
            {
              candidate_id: 'close_candidate_1',
              candidate_type: 'close_position',
              candidate_only: true,
              executable_order_request: false,
            },
          ],
          estimated_actions_count: 2,
        },
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: {},
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: ['actual flatten execution remains unavailable'],
        blockers: [],
      },
      confirmation_requirement: {
        required: true,
        phrase: 'CONFIRM_FLATTEN_DRY_RUN',
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: 'idem-emergency_flatten',
      status: 'awaiting_confirmation',
    },
  };
}

describe('OperationPreflightModal emergency planning', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders flatten dry-run honestly and does not show actual flatten execution', () => {
    render(
      <OperationPreflightModal
        state={flattenDryRunState()}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getAllByText('emergency_flatten').length).toBeGreaterThan(0);
    expect(screen.getByText(/Dry-run only. No orders will be cancelled/)).toBeTruthy();
    expect(screen.getByText(/No positions will be closed/)).toBeTruthy();
    expect(screen.getByText(/diagnostic candidates, not executable actions/)).toBeTruthy();
    expect(screen.getByText('actual_execution')).toBeTruthy();
    expect(screen.getAllByText('unavailable').length).toBeGreaterThan(0);
    expect(screen.getByText('Dry-run candidates')).toBeTruthy();
    expect((screen.getByText('Confirm dry-run record') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByRole('button', { name: /^Flatten$/i })).toBeNull();
  });

  it('renders stop runtime planning without flatten or cancel implication', () => {
    render(
      <OperationPreflightModal
        state={planningState('emergency_stop_runtime')}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getAllByText('emergency_stop_runtime').length).toBeGreaterThan(0);
    expect(screen.getByText(/Stop Runtime does not flatten or cancel orders by itself/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not flatten positions/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not cancel orders/)).toBeTruthy();
    expect((screen.getByText('Confirm once') as HTMLButtonElement).disabled).toBe(true);
  });

  it('enables stop runtime confirm only when backend preflight is executable and phrase matches', () => {
    render(
      <OperationPreflightModal
        state={executableStopState()}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getByText('actual_execution')).toBeTruthy();
    expect(screen.getByText('available')).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not flatten positions/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not cancel orders/)).toBeTruthy();
    expect((screen.getByText('Confirm once') as HTMLButtonElement).disabled).toBe(false);
  });
});
