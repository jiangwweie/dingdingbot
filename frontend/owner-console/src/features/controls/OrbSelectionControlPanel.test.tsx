import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { OrbSelectionControlPanel } from './OrbSelectionControlPanel';
import { getOrbSelectionPreview } from './api';
vi.mock('./api',()=>({getOrbSelectionPreview:vi.fn(),submitOrbDynamicIntent:vi.fn()}));
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
