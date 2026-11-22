// @vitest-environment jsdom
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {ExitConfigurationPanel} from './ExitConfigurationPanel';
const api=vi.hoisted(()=>({preview:vi.fn(),activate:vi.fn(),receipt:vi.fn()}));
let queryData:unknown;
let queryError=false;
vi.mock('@tanstack/react-query',()=>({useQuery:()=>({data:queryData,isLoading:false,isError:queryError,isFetching:false,refetch:vi.fn()}),useQueryClient:()=>({invalidateQueries:vi.fn()})}));
vi.mock('../../api/exitConfigurationApi',()=>({fetchExitConfiguration:vi.fn(),previewExitConfiguration:api.preview,activateExitConfiguration:api.activate,fetchExitConfigurationReceipt:api.receipt,previewExitSizing:vi.fn()}));
vi.mock('../TotpActionModal',()=>({TotpActionModal:(props:{open:boolean,onConfirm:(x:{totp:string,reason:string})=>void})=>props.open?<button onClick={()=>props.onConfirm({totp:'123456',reason:'reviewed change'})}>提交模拟TOTP</button>:null}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
const events=['CPM-RO-001:CPM-LONG:v3','MI-001:MI-LONG:v3','MPG-001:MPG-LONG:v3','BRF2-001:BRF2-SHORT:v3','SOR-1H-001:SOR-1H-LONG:v1','SOR-1H-001:SOR-1H-SHORT:v1'].map((e,i)=>({event_spec_id:'event_spec:'+e,expected_binding_id:'binding'+i,expected_binding_revision:1,reward_multiple:i<4?'1':'1.2',target_fraction:i<4?'.05':'.5',minimum_lift:i<4,max_actual_fraction:i<4?'.5':'1',ma50_enabled:i<3}));
const intent={product_id:'brc-app-manual-v1',venue_id:'binance-usdm',account_id:'account',expected_revision:0,events};
const preview={intent,profiles:[],preview_digest:'sha256:'+'a'.repeat(64),valid_until_ms:9999999999999,source_configuration_revision:0};
let root:ReturnType<typeof createRoot>;let node:HTMLDivElement;
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks();queryError=false;queryData={current:null,intent,sources:[]};api.preview.mockResolvedValue(preview);});
afterEach(()=>{act(()=>root?.unmount());node?.remove();});
function render(){node=document.createElement('div');document.body.append(node);root=createRoot(node);act(()=>root.render(<ExitConfigurationPanel/>));}
async function click(text:string){const b=Array.from(node.querySelectorAll('button')).find(b=>b.textContent===text);expect(b).toBeDefined();await act(async()=>{b!.click();});}
describe('Owner exit configuration boundary',()=>{
 it('first activation shows six independent bindings and retains original SOR quantity',async()=>{render();expect(node.querySelectorAll('tbody tr')).toHaveLength(6);expect(node.querySelector<HTMLInputElement>('[aria-label="SOR-1H-001 · LONG 目标比例"]')?.disabled).toBe(true);await click('生成服务端预览');expect(api.preview.mock.calls[0][0].events).toHaveLength(6);expect(api.activate).not.toHaveBeenCalled();});
 it.each([true,false])('renders the saved SOR long MA50 choice (%s) and previews its opposite',async(enabled)=>{
  const split = events.map((e,i)=>i<4?e:{
   ...e,
   event_spec_id: i===4?'event_spec:SOR-1H-LONG-001:SOR-1H-LONG:v1':'event_spec:SOR-1H-SHORT-001:SOR-1H-SHORT:v1',
   ma50_enabled:i===4&&enabled,
  });
  const savedIntent={...intent,expected_revision:2,events:split};
  queryData={current:{revision:2,intent:savedIntent},intent:savedIntent,sources:[]};
  api.preview.mockImplementation(async submitted=>({...preview,intent:submitted,profiles:submitted.events.map((ev:typeof events[number])=>({event_spec_id:ev.event_spec_id,profile:{tp1:{reward_multiple:ev.reward_multiple,quantity_fraction:ev.target_fraction},execution:{quantity_policy:ev.minimum_lift?'target_floor_then_minimum':'floor_only'}}}))}));
  render();
  const rows=Array.from(node.querySelectorAll('tbody tr'));
  const gate=node.querySelector<HTMLInputElement>('[aria-label="SOR-多 MA50"]')!;
  expect(gate.checked).toBe(enabled);
  expect(gate.disabled).toBe(false);
  const mobileGate=node.querySelector<HTMLInputElement>('[aria-label="移动端 SOR-多 MA50"]')!;
  expect(mobileGate.checked).toBe(enabled);
  expect(mobileGate.disabled).toBe(false);
  act(()=>gate.click());
  await click('生成服务端预览');
  expect(mobileGate.checked).toBe(!enabled);
  expect(api.preview.mock.calls[0][0].events[4].ma50_enabled).toBe(!enabled);
  expect(api.preview.mock.calls[0][0].events[5].ma50_enabled).toBe(false);
  expect(node.textContent).toContain(`MA50 门槛: ${enabled?'开启 → 关闭':'关闭 → 开启'}`);

  expect(rows.find(r=>r.textContent?.includes('SOR-空'))?.textContent).toContain('不适用');
  expect(rows.find(r=>r.textContent?.includes('SOR-多'))?.querySelector<HTMLInputElement>('input[aria-label$="目标比例"]')?.disabled).toBe(true);
 });
 it('unknown submission preserves one request without storing TOTP or claiming success',async()=>{api.activate.mockRejectedValue(new Error('timeout'));api.receipt.mockResolvedValue(null);render();await click('生成服务端预览');await click('TOTP 确认激活');await click('提交模拟TOTP');const saved=sessionStorage.getItem('brc:exit-configuration:pending')!;expect(saved).toContain('idempotency_key');expect(saved).not.toContain('123456');expect(saved).not.toContain('totp_code');await click('核实原激活请求');expect(sessionStorage.getItem('brc:exit-configuration:pending')).toBe(saved);expect(api.activate).toHaveBeenCalledTimes(1);expect(node.textContent).toContain('尚无已提交结果');});
 it('shows percentage helper for decimals, locks SOR/MA50 scope, and clears preview on edit',async()=>{
  queryData={current:{revision:1},intent:{...intent,expected_revision:1},sources:[]};
  render();
  expect(node.textContent).toContain('(5%)');
  expect(node.textContent).toContain('不适用');
  expect(node.querySelector('[data-testid="exit-config-mobile-list"]')?.children).toHaveLength(6);
  expect(node.querySelector<HTMLInputElement>('[aria-label="移动端 SOR-1H-001 · LONG 目标比例"]')?.disabled).toBe(true);
  await click('生成服务端预览');
  expect(node.querySelector('[data-testid="exit-config-preview"]')).not.toBeNull();
  const tp1Input=node.querySelector<HTMLInputElement>('[aria-label="CPM-RO-001 · LONG TP1倍数"]')!;
  await act(async()=>{
   const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!;
   setter.call(tp1Input,'1.5');
   tp1Input.dispatchEvent(new Event('input',{bubbles:true}));
   tp1Input.dispatchEvent(new Event('change',{bubbles:true}));
  });
  expect(node.querySelector('[data-testid="exit-config-preview"]')).toBeNull();
 });
 it('disables expired preview activation and disables editing/preview when query fails with cached data',async()=>{
  queryData={current:{revision:1},intent:{...intent,expected_revision:1},sources:[]};
  api.preview.mockResolvedValueOnce({...preview,valid_until_ms:1000});
  render();
  await click('生成服务端预览');
  expect(node.textContent).toContain('预览已失效');
  const activateBtn=Array.from(node.querySelectorAll('button')).find(b=>b.textContent==='TOTP 确认激活')!;
  expect(activateBtn.disabled).toBe(true);

  queryError=true;
  render();
  expect(node.querySelector<HTMLInputElement>('[aria-label="CPM-RO-001 · LONG TP1倍数"]')?.disabled).toBe(true);
  const previewBtn=Array.from(node.querySelectorAll('button')).find(b=>b.textContent==='生成服务端预览')!;
  expect(previewBtn.disabled).toBe(true);
 });

 it('auto-locks when valid preview expires over time and blocks submission if expired',async()=>{
  vi.useFakeTimers();
  try{
   const baseNow=1700000000000;
   vi.setSystemTime(baseNow);
   queryData={current:{revision:1},intent:{...intent,expected_revision:1},sources:[]};
   api.preview.mockResolvedValueOnce({...preview,valid_until_ms:baseNow+5000});
   render();
   await click('生成服务端预览');
   const activateBtn=Array.from(node.querySelectorAll('button')).find(b=>b.textContent==='TOTP 确认激活')!;
   expect(activateBtn.disabled).toBe(false);

   await act(async()=>{vi.advanceTimersByTime(5100);});
   expect(activateBtn.disabled).toBe(true);
   expect(node.textContent).toContain('预览已失效');

   api.preview.mockResolvedValueOnce({...preview,valid_until_ms:Date.now()+2000});
   await click('生成服务端预览');
   await click('TOTP 确认激活');
   await act(async()=>{vi.advanceTimersByTime(2500);});
   await click('提交模拟TOTP');
   expect(api.activate).not.toHaveBeenCalled();
   expect(node.textContent).toContain('预览已失效');
  }finally{
   vi.useRealTimers();
  }
 });

 it('shows MA50 and max_actual_fraction diffs alongside unchanged binding summaries',async()=>{
  const changedEvents=events.map((ev,i)=>i===1?{...ev,ma50_enabled:false}:i===3?{...ev,max_actual_fraction:'0.4'}:ev);
  queryData={current:{revision:1},intent:{...intent,expected_revision:1},sources:[]};
  api.preview.mockResolvedValueOnce({
   ...preview,
   intent:{...intent,expected_revision:1,events:changedEvents},
   profiles:changedEvents.map(ev=>({
    event_spec_id:ev.event_spec_id,
    profile:{tp1:{reward_multiple:ev.reward_multiple,quantity_fraction:ev.target_fraction},execution:{quantity_policy:ev.minimum_lift?'target_floor_then_minimum':'floor_only'}},
   })),
  });
  render();
  await click('生成服务端预览');
  expect(node.textContent).toContain('MA50 门槛: 开启 → 关闭');
  expect(node.textContent).toContain('实际比例上限: .5 → 0.4');
  expect(node.textContent).toContain('参数未变化');
 });
});
