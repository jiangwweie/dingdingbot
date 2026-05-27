// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import FixedTestnetRehearsal from './FixedTestnetRehearsal';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  operationCapabilities: vi.fn(),
  listWorkflows: vi.fn(),
  preflightOperation: vi.fn(),
  confirmOperation: vi.fn(),
  cancelOperation: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

function readinessPayload() {
  return {
    mode: 'testnet_ready',
    current_conclusion: 'Fixed testnet rehearsal is ready.',
    why: [],
    account_impact: 'testnet only',
    next_step: 'Operation Preflight',
    available_actions: [
      {
        action_id: 'create_workflow',
        title: 'Create technical carrier',
        description: '',
        enabled: true,
        button_label: '',
        what_happens: '',
        what_will_not_happen: '',
        account_impact: '',
        risk_level: 'controlled_testnet',
      },
      {
        action_id: 'run_controlled_testnet_workflow',
        title: 'Run fixed testnet rehearsal',
        description: '',
        enabled: true,
        button_label: '',
        what_happens: '',
        what_will_not_happen: '',
        account_impact: '',
        risk_level: 'controlled_testnet',
      },
    ],
    disabled_actions: [],
    environment_boundary: {},
    runtime_state: 'observe',
    risk_decision: 'ALLOW_READ',
    risk_account_summary: {},
    strategy_playbook_summary: {},
    action_cards: [],
    global_cutoff_controls: [],
    runtime_summary: {},
    review_summary: {},
    markets_summary: {},
    playbook_summary: {},
    parameter_summary: {},
    audit_summary: {},
    ai_investigator_summary: {},
    developer_details: {},
    live_ready: false,
  };
}

function preflightPayload() {
  return {
    operation_id: 'op_fixed',
    preflight_id: 'pre_fixed',
    operation_type: 'run_fixed_testnet_rehearsal',
    decision: 'allow',
    summary: 'Run the fixed ETH/BTC testnet rehearsal after Owner confirmation.',
    before: {},
    after: { workflow_carrier: 'internal_ref_only' },
    account_order_summary: { open_order_count: 0 },
    runtime_summary: { testnet: true },
    campaign_summary: { available: false },
    playbook_summary: {},
    risk_summary: { passed: ['operation_policy_enabled'], warnings: [], blockers: [] },
    confirmation_requirement: {
      required: true,
      phrase: 'CONFIRM_FIXED_TESTNET_REHEARSAL',
      expires_at_ms: Date.now() + 60_000,
      totp_freshness_required: false,
    },
    idempotency_key: 'idem_fixed',
    status: 'awaiting_confirmation',
  };
}

describe('FixedTestnetRehearsal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.operationCapabilities.mockResolvedValue({
      live_ready: false,
      capabilities: [
        {
          operation_type: 'run_fixed_testnet_rehearsal',
          status: 'enabled',
          display_name: 'Fixed Testnet Rehearsal',
          risk_level: 'high',
          allowed_env: ['testnet'],
          confirmation_required: true,
          backend_executor: 'brc_operation_fixed_testnet_rehearsal',
          current_reason: 'Operation-authorized fixed ETH/BTC testnet rehearsal.',
          requires_operation_layer: true,
          executable_through_operation: true,
        },
      ],
    });
    mockBrcApi.listWorkflows.mockResolvedValue({ workflows: [] });
    mockBrcApi.preflightOperation.mockResolvedValue(preflightPayload());
  });

  it('opens Operation Preflight as the primary fixed rehearsal path', async () => {
    render(<FixedTestnetRehearsal />);

    await screen.findByText('Operation Authorization');
    fireEvent.click(screen.getByRole('button', { name: /Operation Preflight/i }));

    await waitFor(() => {
      expect(mockBrcApi.preflightOperation).toHaveBeenCalledWith({
        operation_type: 'run_fixed_testnet_rehearsal',
        input_params: {
          source: 'fixed_testnet_rehearsal_page',
          fixed_request_text: '准备下一轮 testnet rehearsal',
        },
        source: { kind: 'fixed_testnet_rehearsal_page' },
      });
    });
    expect((await screen.findAllByText('run_fixed_testnet_rehearsal')).length).toBeGreaterThan(0);
    expect(screen.getByText('CONFIRM_FIXED_TESTNET_REHEARSAL')).toBeTruthy();
    expect(screen.queryByText('Confirm Fixed Rehearsal')).toBeNull();
  });
});
