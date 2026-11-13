import { describe, it, expect } from 'vitest';
import { mapManagementHealth } from './managementHealthMapping';

describe('management receiver readiness', () => {
  it('shows an ENTRY blocker and elapsed time despite live processes and zero incidents', () => {
    const result=mapManagementHealth({required:true,ready:false,connection_state:'gap',
      blocker_code:'management_stream_protocol_invalid',blocked_since_ms:1000,last_successful_at_ms:999,
      lease_until_ms:4000000,epoch_id:'epoch',persisted_watermark:35,applied_watermark:35},3601000);
    expect(result.blocked).toBe(true);
    expect(result.summary).toContain('新开仓受阻');
    expect(result.details).toContain('60 分钟');
    expect(result.details).toContain('management_stream_protocol_invalid');
    expect(result.details).toContain('35 / 35');
  });
  it('does not equate a ready receiver with all trading gates passing', () => {
    const result=mapManagementHealth({required:true,ready:true,connection_state:'ready',blocker_code:null,
      blocked_since_ms:null,last_successful_at_ms:1000,lease_until_ms:16000,epoch_id:'epoch',
      persisted_watermark:35,applied_watermark:35},1001);
    expect(result.blocked).toBe(false);
    expect(result.details).toContain('其他准入门禁');
  });
});
