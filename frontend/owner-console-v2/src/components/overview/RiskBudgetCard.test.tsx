// @vitest-environment jsdom
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {afterEach,expect,it,vi} from 'vitest';
import {RiskBudgetCard} from './RiskBudgetCard';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),change:vi.fn(),preview:vi.fn(),receipt:vi.fn()}));
vi.mock('../../api/riskBudgetApi',()=>({fetchRiskBudget:mocks.fetch,changeRiskBudget:mocks.change,previewRiskBudget:mocks.preview,fetchRiskBudgetReceipt:mocks.receipt}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
let root: ReturnType<typeof createRoot>;let container:HTMLDivElement;
afterEach(()=>{act(()=>root?.unmount());container?.remove();vi.resetAllMocks();sessionStorage.clear();});
function render(){container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);act(()=>root.render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><RiskBudgetCard/></QueryClientProvider>));}
const state={venue_id:'binance-usdm',account_id:'a',policy_version:30,directional_version:6,baseline:'0.02',gross_limit:'0.06',long_limit:'0.02',short_limit:'0.04',minimum_risk:'0.01',view:'bearish',entry_enabled:true,pending_baseline:'0.03',pending_directional_view:null,updated_at_ms:1000,min_baseline:'0.02',max_baseline:'0.03',step:'0.001'};
it('shows effective 2% and pending 3% separately and blocks editing',async()=>{mocks.fetch.mockResolvedValue(state);render();await act(async()=>{await vi.waitFor(()=>expect(container.textContent).toContain('等待生效'));});expect(container.textContent).toContain('当前单笔上限：2%');expect(container.textContent).toContain('3%');expect(container.querySelector('input')?.disabled).toBe(true);expect(mocks.change).not.toHaveBeenCalled();});
it('does not fabricate defaults when reading fails',async()=>{mocks.fetch.mockRejectedValue(new Error('offline'));render();await act(async()=>{await vi.waitFor(()=>expect(container.textContent).toContain('无法读取'));});expect(container.textContent).not.toContain('当前单笔上限：2%');});

it('recovers a lost response by exact key without another mutation',async()=>{
 sessionStorage.setItem('brc-risk-budget-request',JSON.stringify({scopeKey:'binance-usdm:a',baseline:'0.030',expected_version:30,expected_directional_version:6,reason:'raise',idempotency_key:'lost-key'}));
 mocks.fetch.mockResolvedValue(state);mocks.receipt.mockResolvedValue({status:'pending',request_id:'receipt'});render();
 await act(async()=>{await vi.waitFor(()=>expect(container.textContent).toContain('当前单笔'));});
 const button=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent?.includes('核验权威状态'))!;
 await act(async()=>{button.click();await Promise.resolve();});
 expect(mocks.receipt).toHaveBeenCalledWith('lost-key');expect(mocks.change).not.toHaveBeenCalled();expect(sessionStorage.getItem('brc-risk-budget-request')).toBeNull();expect(container.textContent).toContain('等待生效');
});
it('keeps an unresolved request when its account does not match',async()=>{
 sessionStorage.setItem('brc-risk-budget-request',JSON.stringify({scopeKey:'binance-usdm:other',baseline:'0.030',expected_version:30,expected_directional_version:6,reason:'raise',idempotency_key:'other-key'}));
 mocks.fetch.mockResolvedValue(state);render();await act(async()=>{await vi.waitFor(()=>expect(container.textContent).toContain('当前单笔'));});
 const button=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent?.includes('核验权威状态'))!;
 await act(async()=>{button.click();await Promise.resolve();});
 expect(mocks.receipt).not.toHaveBeenCalled();expect(mocks.change).not.toHaveBeenCalled();expect(document.body.textContent).toContain('当前账户与原请求不同');expect(sessionStorage.getItem('brc-risk-budget-request')).not.toBeNull();
});
