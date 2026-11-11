// @vitest-environment jsdom
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {TicketExitPlan} from './TicketExitPlan';
let state:unknown;
vi.mock('@tanstack/react-query',()=>({useQuery:()=>state}));
(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
let root:ReturnType<typeof createRoot>;let node:HTMLDivElement;
afterEach(()=>{act(()=>root?.unmount());node?.remove();});
function render(mode='AUTO',filled='.0004'){
 state={data:{management_mode:mode,aggregate_status:'position_protected',tp1_filled_quantity:filled,tp1_target_quantity:'.001',current_quantity:'.0066',protected_quantity:'.0066',active_stop_price:'64000',plan:{target_fraction:'.05',quantities:{actual_fraction:'0.142857142857142857',minimum_lifted:true},entry_price:'65000',initial_stop:'64000',tp_price:'66000',actual_multiple:'1'}}};
 node=document.createElement('div');document.body.append(node);root=createRoot(node);act(()=>root.render(<TicketExitPlan ticketId="ticket:one"/>));return node.textContent;
}
describe('actual exit plan truth',()=>{
 it('displays lifted actual fraction and incomplete TP without claiming BE',()=>{const text=render();expect(text).toContain('目标 5%');expect(text).toContain('实际 14.286%');expect(text).toContain('未启动保本');expect(text).not.toContain('95%');});
 it('permanent manual overrides an old TP full fill',()=>{const text=render('MANUAL','.001');expect(text).toContain('自动计划已停止执行');expect(text).not.toContain('Runner 保护已确认');});
 it('review is not a confirmed manual handover',()=>{const text=render('REVIEW_REQUIRED');expect(text).toContain('归属待核实');expect(text).not.toContain('自动计划已停止执行');});
});
