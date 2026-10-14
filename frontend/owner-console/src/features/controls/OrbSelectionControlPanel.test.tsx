import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../../api/errors';
import { expect, it, vi } from 'vitest';
import { OrbSelectionControlPanel } from './OrbSelectionControlPanel';
import { getOrbSelectionPreview, submitOrbDynamicIntent, submitOrbStaticIntent, type OrbSelectionPreview } from './api';
vi.mock('./api',()=>({getOrbSelectionPreview:vi.fn(),submitOrbDynamicIntent:vi.fn(),submitOrbStaticIntent:vi.fn()}));
it('shows independent hourly preparation and the retired strategy boundary',async()=>{
  vi.mocked(getOrbSelectionPreview).mockResolvedValue({strategy_label:'SOR-1H（1h 入场 / 15m 退出）',installed:false,control:null,runtime:null,
    next_effective_period_anchor_ms:1704067200000,next_prepare_not_before_ms:1704070800000,next_eligibility_not_before_ms:1704074400000});
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OrbSelectionControlPanel/></QueryClientProvider>);
  expect(await screen.findByText('SOR-1H（1h 入场 / 15m 退出）')).toBeInTheDocument();
  expect(await screen.findByRole('button',{name:'启用 SOR-1H Dynamic'})).toBeDisabled();
  expect(screen.getByText(/01:00:00 UTC/)).toBeInTheDocument();
  expect(screen.getByText(/02:00:00 UTC/)).toBeInTheDocument();
  expect(screen.queryByText(/missed periods/)).not.toBeInTheDocument();
});

const installedPreview: OrbSelectionPreview = {
  strategy_label: 'SOR-1H（1h 入场 / 15m 退出）', installed: true, runtime: null,
  next_effective_period_anchor_ms: 1704067200000,
  next_prepare_not_before_ms: 1704070800000, next_eligibility_not_before_ms: 1704074400000,
  control: { strategy_group_id: 'SOR-1H-001', selection_spec_id: 'SOR_1H_OR_ATR_DYNAMIC_V1',
    selection_mode: 'static_baseline', pending_selection_mode: null,
    pending_effective_period_anchor_ms: null, pending_authorization_id: null,
    control_version: 7, rollback_baseline_id: 'baseline:orb', selection_epoch_id: null, updated_at_ms: 100 },
};
function showPanel() {
  return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><OrbSelectionControlPanel/></QueryClientProvider>);
}
it('retries an unknown Dynamic response with the same frozen intent and clears the code', async () => {
  const user = userEvent.setup();
  vi.mocked(getOrbSelectionPreview).mockResolvedValue(installedPreview);
  vi.mocked(submitOrbDynamicIntent).mockReset().mockRejectedValueOnce(new Error('network outcome unknown')).mockResolvedValue();
  showPanel();
  await user.click(await screen.findByRole('button', {name:'启用 SOR-1H Dynamic'}));
  await user.type(screen.getByLabelText('操作原因'),'hourly trial');
  await user.type(screen.getByLabelText('验证码'),'123456');
  await user.click(screen.getByRole('button',{name:'确认提交'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('同一意图重试');
  expect(screen.getByLabelText('验证码')).toHaveValue('');
  expect(screen.getByLabelText('操作原因')).toBeDisabled();
  await user.type(screen.getByLabelText('验证码'),'654321');
  await user.click(screen.getByRole('button',{name:'确认提交'}));
  await waitFor(()=>expect(submitOrbDynamicIntent).toHaveBeenCalledTimes(2));
  const [first, second] = vi.mocked(submitOrbDynamicIntent).mock.calls;
  expect(first![0]).toEqual(expect.objectContaining({expected_version:7,effective_session_start_ms:1704067200000,reason:'hourly trial'}));
  expect(second![0].idempotency_key).toBe(first![0].idempotency_key);
});
it('submits Static with the frozen hourly baseline and epoch', async () => {
  const user = userEvent.setup();
  vi.mocked(getOrbSelectionPreview).mockResolvedValue({...installedPreview,control:{...installedPreview.control!,selection_mode:'dynamic_selection',selection_epoch_id:'epoch:orb'}});
  vi.mocked(submitOrbStaticIntent).mockReset().mockResolvedValue();
  showPanel();
  await user.click(await screen.findByRole('button',{name:'回退 SOR-1H Static'}));
  await user.type(screen.getByLabelText('操作原因'),'restore static');
  await user.type(screen.getByLabelText('验证码'),'123456');
  await user.click(screen.getByRole('button',{name:'确认提交'}));
  await waitFor(()=>expect(submitOrbStaticIntent).toHaveBeenCalledOnce());
  expect(submitOrbStaticIntent).toHaveBeenCalledWith(expect.objectContaining({expected_version:7,rollback_baseline_id:'baseline:orb',selection_epoch_id:'epoch:orb',effective_period_anchor_ms:1704067200000}));
});
it('blocks submission after a version conflict without automatic reauthorization', async () => {
  const user = userEvent.setup();
  vi.mocked(getOrbSelectionPreview).mockResolvedValue(installedPreview);
  vi.mocked(submitOrbDynamicIntent).mockReset().mockRejectedValue(new ApiError(409,'control_conflict','changed'));
  showPanel();
  await user.click(await screen.findByRole('button',{name:'启用 SOR-1H Dynamic'}));
  await user.type(screen.getByLabelText('操作原因'),'trial');
  await user.type(screen.getByLabelText('验证码'),'123456');
  await user.click(screen.getByRole('button',{name:'确认提交'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('状态已变化');
  expect(screen.getByRole('button',{name:'确认提交'})).toBeDisabled();
  expect(submitOrbDynamicIntent).toHaveBeenCalledOnce();
});
