// @vitest-environment jsdom
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {ReviewEnrichmentPanel} from './ReviewEnrichmentPanel';
const api=vi.hoisted(()=>({GET:vi.fn(),POST:vi.fn()}));
vi.mock('../../api/client',()=>({apiClient:api}));
vi.mock('../TotpActionModal',()=>({TotpActionModal:(p:{open:boolean,onConfirm:(x:{totp:string,reason:string})=>void})=>p.open?<button onClick={()=>p.onConfirm({totp:'123456',reason:'reviewed preview'})}>提交批准</button>:null}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
let root:ReturnType<typeof createRoot>;let node:HTMLDivElement;
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();});
afterEach(()=>{act(()=>root?.unmount());node?.remove();});
function render(){node=document.createElement('div');document.body.append(node);root=createRoot(node);act(()=>root.render(<ReviewEnrichmentPanel ticketId="ticket" revision={1}/>));}
async function click(text:string){const button=Array.from(node.querySelectorAll('button')).find(b=>b.textContent===text);expect(button).toBeDefined();await act(async()=>{button!.click();});}
const preview={request_id:'request',ticket_id:'ticket',expected_review_id:'old',state:'preview_ready',preview_digest:'sha256:'+'a'.repeat(64),
 preview:{entry_quantity:'32811',exit_quantity:'32811',old_metrics:{economics_completeness:'external_exit_unavailable'},metrics:{economics_completeness:'complete',net_pnl_quote:'36'}}};
it('unknown approval preserves one exact request and never stores TOTP',async()=>{
 api.POST.mockResolvedValueOnce({response:{ok:true},data:{request_id:'request'}}).mockRejectedValueOnce(new Error('timeout'));
 api.GET.mockResolvedValue({response:{ok:true},data:preview});render();
 await click('生成核算补齐预览');expect(node.textContent).toContain('32811');
 await click('复核差异并通过 TOTP 批准');await click('提交批准');
 const saved=sessionStorage.getItem('brc:review-enrichment:ticket')!;expect(saved).toContain('idempotency_key');expect(saved).not.toContain('123456');
 await click('核实原批准请求');expect(sessionStorage.getItem('brc:review-enrichment:ticket')).toBe(saved);expect(api.POST).toHaveBeenCalledTimes(2);
});
it('wrong Ticket preview cannot be approved',async()=>{
 api.POST.mockResolvedValue({response:{ok:true},data:{request_id:'request'}});
 api.GET.mockResolvedValue({response:{ok:true},data:{...preview,ticket_id:'other'}});render();await click('生成核算补齐预览');
 expect(node.textContent).toContain('身份不一致');expect(node.textContent).not.toContain('通过 TOTP 批准');
});
