import { describe, it, expect, vi, beforeEach } from 'vitest';
import { pauseStrategy, resumeStrategy } from './controlsApi';
import { apiClient } from './client';
import { ApiError } from './errors';

describe('controlsApi strategy controls', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('pauseStrategy', () => {
    it('submits pause request with correct strategy_group_id and parameters', async () => {
      const mockResult = {
        data: {
          strategy_group_id: 'CPM-RO-001',
          entry_state: 'paused',
          control_version: 3,
          last_event_id: 'event:123',
          reason: 'Owner 手动暂停新准入',
          updated_at_ms: 1800000000000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 2,
        reason: 'Owner 手动暂停新准入',
        idempotency_key: 'owner-request:test:123',
        totp_code: null,
      };

      const res = await pauseStrategy('CPM-RO-001', payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/strategies/{strategy_group_id}/pause',
        {
          params: { path: { strategy_group_id: 'CPM-RO-001' } },
          body: payload,
        }
      );
      expect(res.strategy_group_id).toBe('CPM-RO-001');
      expect(res.entry_state).toBe('paused');
      expect(res.control_version).toBe(3);
    });

    it('throws ApiError on conflict (409)', async () => {
      vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: undefined,
        error: { error: { code: 'control_conflict', message: 'strategy_control_version_conflict' } },
        response: { ok: false, status: 409 } as Response,
      } as any);

      await expect(
        pauseStrategy('CPM-RO-001', {
          expected_version: 1,
          reason: 'test',
          idempotency_key: 'idemp-1',
          totp_code: null,
        })
      ).rejects.toThrow(ApiError);
    });
  });

  describe('resumeStrategy', () => {
    it('submits resume request with valid TOTP code and expected_version', async () => {
      const mockResult = {
        data: {
          strategy_group_id: 'CPM-RO-001',
          entry_state: 'enabled',
          control_version: 4,
          last_event_id: 'event:456',
          reason: 'Owner 手动恢复新准入',
          updated_at_ms: 1800000005000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 3,
        reason: 'Owner 手动恢复新准入',
        idempotency_key: 'owner-request:test:456',
        totp_code: '123456',
      };

      const res = await resumeStrategy('CPM-RO-001', payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/strategies/{strategy_group_id}/resume',
        {
          params: { path: { strategy_group_id: 'CPM-RO-001' } },
          body: payload,
        }
      );
      expect(res.entry_state).toBe('enabled');
      expect(res.control_version).toBe(4);
    });

    it('throws ApiError on invalid step-up (403)', async () => {
      vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: undefined,
        error: { error: { code: 'step_up_invalid', message: 'Step-up proof is invalid' } },
        response: { ok: false, status: 403 } as Response,
      } as any);

      await expect(
        resumeStrategy('CPM-RO-001', {
          expected_version: 3,
          reason: 'test',
          idempotency_key: 'idemp-2',
          totp_code: '000000',
        })
      ).rejects.toThrow(ApiError);
    });

    it('throws ApiError on retired strategy rejection (422)', async () => {
      vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: undefined,
        error: { error: { code: 'control_blocked', message: 'strategy_retired' } },
        response: { ok: false, status: 422 } as Response,
      } as any);

      await expect(
        resumeStrategy('SOR-001', {
          expected_version: 1,
          reason: 'attempt resume',
          idempotency_key: 'idemp-3',
          totp_code: '123456',
        })
      ).rejects.toThrow(ApiError);
    });
  });
});
