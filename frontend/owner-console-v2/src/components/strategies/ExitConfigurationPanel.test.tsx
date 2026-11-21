// @vitest-environment jsdom
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {ExitConfigurationPanel} from './ExitConfigurationPanel';
const api=vi.hoisted(()=>({preview:vi.fn(),activate:vi.fn(),receipt:vi.fn()}));
let queryData:unknown;
vi.mock('@tanstack/react-query',()=>({useQuery:()=>({data:queryData,isLoading:false,isError:false,refetch:vi.fn()}),useQueryClient:()=>({invalidateQueries:vi.fn()})}));
vi.mock('../../api/exitConfigurationApi',()=>({fetchExitConfiguration:vi.fn(),previewExitConfiguration:api.preview,activateExitConfiguration:api.activate,fetchExitConfigurationReceipt:api.receipt,previewExitSizing:vi.fn()}));
vi.mock('../TotpActionModal',()=>({TotpActionModal:(props:{open:boolean,onConfirm:(x:{totp:string,reason:string})=>void})=>props.open?<button onClick={()=>props.onConfirm({totp:'123456',reason:'reviewed change'})}>提交模拟TOTP</button>:null}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
const events=['CPM-RO-001:CPM-LONG:v3','MI-001:MI-LONG:v3','MPG-001:MPG-LONG:v3','BRF2-001:BRF2-SHORT:v3','SOR-1H-001:SOR-1H-LONG:v1','SOR-1H-001:SOR-1H-SHORT:v1'].map((e,i)=>({event_spec_id:'event_spec:'+e,expected_binding_id:'binding'+i,expected_binding_revision:1,reward_multiple:i<4?'1':'1.2',target_fraction:i<4?'.05':'.5',minimum_lift:i<4,max_actual_fraction:i<4?'.5':'1',ma50_enabled:i<3}));
const intent={product_id:'brc-app-manual-v1',venue_id:'binance-usdm',account_id:'account',expected_revision:0,events};
const preview={intent,profiles:[],preview_digest:'sha256:'+'a'.repeat(64),valid_until_ms:9999999999999,source_configuration_revision:0};
let root:ReturnType<typeof createRoot>;let node:HTMLDivElement;
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks();queryData={current:null,intent,sources:[]};api.preview.mockResolvedValue(preview);});
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
  api.preview.mockImplementation(async submitted=>({...preview,intent:submitted}));
  render();
  const rows=Array.from(node.querySelectorAll('tbody tr'));
  const gate=node.querySelector<HTMLInputElement>('[aria-label="SOR-多 MA50"]')!;
  expect(gate.checked).toBe(enabled);
  expect(gate.disabled).toBe(false);
  act(()=>gate.click());
  await click('生成服务端预览');
  expect(api.preview.mock.calls[0][0].events[4].ma50_enabled).toBe(!enabled);
  expect(api.preview.mock.calls[0][0].events[5].ma50_enabled).toBe(false);
  expect(node.textContent).toContain(`SOR-多 MA50：${enabled?'关闭':'开启'}`);
  expect(rows.find(r=>r.textContent?.includes('SOR-空'))?.textContent).toContain('不适用');
  expect(rows.find(r=>r.textContent?.includes('SOR-多'))?.querySelector<HTMLInputElement>('input[aria-label$="目标比例"]')?.disabled).toBe(true);
 });
 it('unknown submission preserves one request without storing TOTP or claiming success',async()=>{api.activate.mockRejectedValue(new Error('timeout'));api.receipt.mockResolvedValue(null);render();await click('生成服务端预览');await click('TOTP 确认激活');await click('提交模拟TOTP');const saved=sessionStorage.getItem('brc:exit-configuration:pending')!;expect(saved).toContain('idempotency_key');expect(saved).not.toContain('123456');expect(saved).not.toContain('totp_code');await click('核实原激活请求');expect(sessionStorage.getItem('brc:exit-configuration:pending')).toBe(saved);expect(api.activate).toHaveBeenCalledTimes(1);expect(node.textContent).toContain('尚无已提交结果');});
});
