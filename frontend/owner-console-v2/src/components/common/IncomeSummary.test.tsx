// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IncomeSummary } from './IncomeSummary';
import type { PerformanceSummary } from '../../api/performanceApi';
import { incomeNavigationSearch, parseReviewSearchParams, parseStrategiesSearchParams } from '../../utils/urlParams';
import { useReviewData } from '../../hooks/useReviewData';
import { ApiError } from '../../api/errors';
const mocks=vi.hoisted(()=>({income:vi.fn(),review:vi.fn()}));
vi.mock('../../api/performanceApi',()=>({fetchPerformance:mocks.income}));
vi.mock('../../api/reviewApi',()=>({fetchReviewCenter:mocks.review,reviewInfiniteQueryKey:(p:unknown)=>['review','infinite',p]}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
const money=(value:string|null,unit:'R'|'USDT'='USDT')=>({value,unit,unavailable_reason:value===null?'funding_unavailable':null});
const totals={gross_pnl:money('25'),net_pnl:money('16.98'),net_r:money('3.6244','R'),fees:money('3'),funding:money('-0.5')};
const coverage=Object.fromEntries(Object.keys(totals).map(key=>[key,{available_count:key==='fees'||key==='gross_pnl'?72:60,total_count:72,missing_ticket_ids:[]} ]));
const part={sample_count:0,confirmed_count:0,unreviewed_count:0,win_count:0,loss_count:0,breakeven_count:0,verified_totals:totals,metric_coverage:coverage};
const full={...part,sample_count:72,confirmed_count:60,from_ms:1700000000000,to_ms:1700100000000,summary_scope:'full_window',time_basis:'terminal',view:'all',exit_scope:'all',snapshot_id:'profit:one',complete_review_count:60,incomplete_review_count:12,attention_count:0,breakdown:{strategy:part,owner:part,safety:part,unknown:part}} as PerformanceSummary;
let root:ReturnType<typeof createRoot>|undefined;
let container:HTMLDivElement;
afterEach(()=>{act(()=>root?.unmount());root=undefined;container?.remove();vi.resetAllMocks();});
function render(element:React.ReactNode){container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);act(()=>root!.render(element));}
function page(id:string,cursor:string|null){return {freshness:'fresh',data:{from_ms:full.from_ms,to_ms:full.to_ms,items:[{ticket_id:id,strategy_group_id:'BRF2-001',review:{review_status:'complete',execution_classification:'complete',exit_reason:'initial_stop_triggered',economic_summary:totals,evidence:[],attention_items:[]}}],next_cursor:cursor,strategy_group_samples:[]}};}
function Probe(){const data=useReviewData({from_ms:full.from_ms,to_ms:full.to_ms,view:'all',exit_scope:'all'});return <><IncomeSummary summary={data.performance} error={data.performanceError} onRefresh={()=>data.refetch()}/><div data-testid="loaded">{data.items.length}</div><button onClick={()=>data.fetchNextPage()} disabled={!data.hasNextPage}>next</button></>;}
describe('full-window income contract',()=>{
 it('displays full-window totals even when only a single detail page is loaded',async()=>{
  mocks.income.mockResolvedValue({data:full});mocks.review.mockImplementation(({cursor})=>Promise.resolve(cursor?page('b',null):page('a','next')));
  render(<QueryClientProvider client={new QueryClient()}><Probe/></QueryClientProvider>);
  await act(async()=>{await vi.waitFor(()=>expect(container.querySelector('[data-testid="loaded"]')?.textContent).toBe('1'));});
  expect(container.querySelector('[data-testid="income-net_pnl"]')?.textContent).toContain('+16.98 USDT');
  await act(async()=>{container.querySelector<HTMLButtonElement>('button:last-child')!.click();await vi.waitFor(()=>expect(container.querySelector('[data-testid="loaded"]')?.textContent).toBe('2'));});
  expect(container.querySelector('[data-testid="income-net_pnl"]')?.textContent).toContain('+16.98 USDT');
  expect(mocks.review.mock.calls[1][0].snapshot).toBe('profit:one');
 });
 it('blocks more pages when the server reports a changed statistics snapshot',async()=>{
  mocks.income.mockResolvedValue({data:full});mocks.review.mockImplementation(({cursor})=>cursor?Promise.reject(new ApiError(409,'statistics_snapshot_changed','统计事实已更新')):Promise.resolve(page('a','next')));
  render(<QueryClientProvider client={new QueryClient()}><Probe/></QueryClientProvider>);
  await act(async()=>{await vi.waitFor(()=>expect(container.querySelector('[data-testid="loaded"]')?.textContent).toBe('1'));});
  await act(async()=>{container.querySelector<HTMLButtonElement>('button:last-child')!.click();await vi.waitFor(()=>expect(container.textContent).toContain('刷新整组数据'));});
  expect([...container.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent==='next')!.disabled).toBe(true);
 });
 it('preserves fixed dates, exit scope and version scope when navigating or copying links',()=>{
  const source=`?tab=strategies&range=custom&from_ms=${full.from_ms}&to_ms=${full.to_ms}&view=current&exit_scope=owner&strategy_group_id=BRF2-001&strategy_version_id=v3`;
  const search=incomeNavigationSearch(source,'review');
  const parsed=parseReviewSearchParams(new URLSearchParams(search),9999999999999);
  expect(parsed.from_ms).toBe(full.from_ms);expect(parsed.to_ms).toBe(full.to_ms);expect(parsed.exit_scope).toBe('owner');expect(parsed.view).toBe('current');expect(parsed.strategy_version_id).toBe('v3');
  expect(parseStrategiesSearchParams(new URLSearchParams()).view).toBe('all');
 });
 it('never replaces a failed full summary with a favourable partial page sum',()=>{
  render(<IncomeSummary summary={full} error={new Error('unavailable')} onRefresh={vi.fn()}/>);
  expect(container.textContent).toContain('不能以已加载明细代替总额');
  expect(container.textContent).not.toContain('16.98');
 });
});
