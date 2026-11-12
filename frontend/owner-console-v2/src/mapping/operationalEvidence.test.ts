import {describe,expect,it} from 'vitest';
import {admissionReasonLabel,manualProtectionLabel} from './tradeTruth';
describe('operational facts stay separate',()=>{
 it('oversized existing stop is unknown coverage and never no stop',()=>{
  expect(manualProtectionLabel('manual_stop_quantity_exceeds_position',true,'unknown')).toContain('数量不匹配');
  expect(manualProtectionLabel('manual_stop_quantity_exceeds_position',true,'unknown')).not.toContain('未覆盖');
 });
 it('management and venue minimum are not mislabeled as budget shortage',()=>{
  expect(admissionReasonLabel('account_health_blocked')).toBe('账户管理或事实门禁');
  expect(admissionReasonLabel('margin_exhausted')).toBe('保证金额度不足');
  expect(admissionReasonLabel('venue_minimum_unmet')).toBe('交易所最小下单量不足');
  expect(admissionReasonLabel('budget_exhausted')).toContain('旧记录');
 });
});

it('distinguishes wallet allocation from actual funds and total margin',()=>{
 expect(admissionReasonLabel('dispatch_preflight:allocation_wallet_changed')).toBe('钱包余额变化，原单票分配已超限');
 expect(admissionReasonLabel('available_margin_insufficient')).toBe('账户实际可用保证金不足');
 expect(admissionReasonLabel('dispatch_preflight:gross_margin_limit')).toBe('账户总保证金额度不足');
});
