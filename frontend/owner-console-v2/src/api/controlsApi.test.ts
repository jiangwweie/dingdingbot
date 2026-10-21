import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  pauseStrategy,
  resumeStrategy,
  fetchFlattenPreview,
  submitFlatten,
  fetchControlOperation,
  pauseGlobalEntry,
  resumeGlobalEntry,
  activateDynamicSelection,
  activateStaticSelection,
} from './controlsApi';
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

  describe('fetchFlattenPreview', () => {
    it('requests flatten preview with empty body and returns FlattenPreview', async () => {
      const mockPreview = {
        venue_id: 'binance-usdm',
        account_id: 'owner-main',
        owner_policy_version: 5,
        global_entry_enabled: true,
        ticket_ids: ['ticket:btc-long', 'ticket:eth-short'],
        ticket_states: {
          'ticket:btc-long': 'eligible',
          'ticket:eth-short': 'eligible',
        },
        snapshot_digest: 'sha256:' + 'a'.repeat(64),
        first_blocker: null,
        runtime_profile_id: 'account-wide',
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: mockPreview,
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      } as any);

      const preview = await fetchFlattenPreview();

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/exposure/flatten-all/preview',
        { body: {} }
      );
      expect(preview.owner_policy_version).toBe(5);
      expect(preview.ticket_ids).toHaveLength(2);
      expect(preview.snapshot_digest).toBe('sha256:' + 'a'.repeat(64));
    });

    it('throws ApiError when server returns 502/503/422', async () => {
      vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: undefined,
        error: { error: { code: 'control_unavailable', message: 'Service unavailable' } },
        response: { ok: false, status: 503 } as Response,
      } as any);

      await expect(fetchFlattenPreview()).rejects.toThrow(ApiError);
    });
  });

  describe('submitFlatten', () => {
    it('submits flatten request with valid parameters and returns OwnerControlOperation', async () => {
      const mockOperation = {
        authorization_id: 'owner-auth:123',
        operation_kind: 'flatten_all',
        state: 'pending',
        version: 2,
        runtime_profile_id: 'account-wide',
        venue_id: 'binance-usdm',
        account_id: 'owner-main',
        target_ticket_ids: ['ticket:btc-long'],
        snapshot_digest: 'sha256:' + 'b'.repeat(64),
        first_blocker: null,
        created_at_ms: 1800000000000,
        updated_at_ms: 1800000000000,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: mockOperation,
        error: undefined,
        response: { ok: true, status: 201 } as Response,
      } as any);

      const payload = {
        expected_version: 5,
        reason: 'owner_flatten_all',
        idempotency_key: 'owner-req:flatten:1',
        totp_code: '654321',
        snapshot_digest: 'sha256:' + 'b'.repeat(64),
        confirmation_text: '确认平仓全部持仓' as const,
      };

      const op = await submitFlatten(payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/exposure/flatten-all',
        { body: payload }
      );
      expect(op.authorization_id).toBe('owner-auth:123');
      expect(op.operation_kind).toBe('flatten_all');
      expect(op.state).toBe('pending');
    });

    it('throws ApiError on snapshot conflict (409)', async () => {
      vi.spyOn(apiClient, 'POST').mockResolvedValue({
        data: undefined,
        error: { error: { code: 'control_conflict', message: 'flatten_snapshot_conflict' } },
        response: { ok: false, status: 409 } as Response,
      } as any);

      await expect(
        submitFlatten({
          expected_version: 5,
          reason: 'owner_flatten_all',
          idempotency_key: 'owner-req:flatten:2',
          totp_code: '654321',
          snapshot_digest: 'sha256:' + 'c'.repeat(64),
          confirmation_text: '确认平仓全部持仓',
        })
      ).rejects.toThrow(ApiError);
    });
  });

  describe('fetchControlOperation', () => {
    it('fetches control operation by authorization_id', async () => {
      const mockOperation = {
        authorization_id: 'owner-auth:999',
        operation_kind: 'flatten_all',
        state: 'completed',
        version: 5,
        runtime_profile_id: 'account-wide',
        venue_id: 'binance-usdm',
        account_id: 'owner-main',
        target_ticket_ids: ['ticket:btc-long'],
        snapshot_digest: 'sha256:' + 'd'.repeat(64),
        first_blocker: null,
        created_at_ms: 1800000000000,
        updated_at_ms: 1800000010000,
      };

      const getSpy = vi.spyOn(apiClient, 'GET').mockResolvedValue({
        data: mockOperation,
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      } as any);

      const op = await fetchControlOperation('owner-auth:999');

      expect(getSpy).toHaveBeenCalledWith(
        '/api/owner/v1/control-operations/{authorization_id}',
        { params: { path: { authorization_id: 'owner-auth:999' } } }
      );
      expect(op).not.toBeNull();
      expect(op?.state).toBe('completed');
    });

    it('returns null if server responds with not_found status', async () => {
      vi.spyOn(apiClient, 'GET').mockResolvedValue({
        data: { status: 'not_found' },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      } as any);

      const op = await fetchControlOperation('nonexistent-auth');
      expect(op).toBeNull();
    });
  });

  describe('global entry controls', () => {
    it('pauseGlobalEntry sends POST to /controls/entry/pause without requiring TOTP', async () => {
      const mockResult = {
        data: {
          configured_state: 'paused',
          effective_state: 'paused',
          version: 7,
          updated_at_ms: 1800000000000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 6,
        reason: 'Owner 手动暂停全局新开仓',
        idempotency_key: 'owner-request:global-entry-pause:123',
        totp_code: null,
      };

      const res = await pauseGlobalEntry(payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/entry/pause',
        { body: payload }
      );
      expect(res.configured_state).toBe('paused');
      expect(res.version).toBe(7);
    });

    it('resumeGlobalEntry sends POST to /controls/entry/resume with TOTP code', async () => {
      const mockResult = {
        data: {
          configured_state: 'enabled',
          effective_state: 'enabled',
          version: 8,
          updated_at_ms: 1800000005000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 7,
        reason: 'Owner 手动恢复全局新开仓',
        idempotency_key: 'owner-request:global-entry-resume:456',
        totp_code: '123456',
      };

      const res = await resumeGlobalEntry(payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/entry/resume',
        { body: payload }
      );
      expect(res.configured_state).toBe('enabled');
      expect(res.version).toBe(8);
    });
  });

  describe('selection controls', () => {
    it('activateDynamicSelection sends POST with generic payload', async () => {
      const mockResult = {
        data: {
          strategy_group_id: 'CPM-RO-001',
          selection_spec_id: 'generic-spec-1',
          selection_mode: 'static_baseline',
          pending_selection_mode: 'dynamic_selection',
          pending_effective_period_anchor_ms: 1800003600000,
          control_version: 2,
          rollback_baseline_id: 'baseline-1',
          updated_at_ms: 1800000000000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 1,
        reason: 'Owner 激活动态选币',
        idempotency_key: 'owner-request:selection-dynamic:cpm:1',
        totp_code: '654321',
        effective_period_anchor_ms: 1800003600000,
      };

      const res = await activateDynamicSelection('CPM-RO-001', payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/strategies/{strategy_group_id}/selection/dynamic/activate',
        {
          params: { path: { strategy_group_id: 'CPM-RO-001' } },
          body: payload,
        }
      );
      expect(res.pending_selection_mode).toBe('dynamic_selection');
    });

    it('activateStaticSelection sends POST with rollback baseline and epoch', async () => {
      const mockResult = {
        data: {
          strategy_group_id: 'CPM-RO-001',
          selection_spec_id: 'generic-spec-1',
          selection_mode: 'dynamic_selection',
          pending_selection_mode: 'static_baseline',
          pending_effective_period_anchor_ms: 1800003600000,
          control_version: 3,
          rollback_baseline_id: 'baseline-certified-v1',
          selection_epoch_id: 'epoch-20261021',
          updated_at_ms: 1800000000000,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      };

      const postSpy = vi.spyOn(apiClient, 'POST').mockResolvedValue(mockResult as any);

      const payload = {
        expected_version: 2,
        reason: 'Owner 回退静态基线',
        idempotency_key: 'owner-request:selection-static:cpm:2',
        totp_code: '654321',
        effective_period_anchor_ms: 1800003600000,
        rollback_baseline_id: 'baseline-certified-v1',
        selection_epoch_id: 'epoch-20261021',
      };

      const res = await activateStaticSelection('CPM-RO-001', payload);

      expect(postSpy).toHaveBeenCalledWith(
        '/api/owner/v1/controls/strategies/{strategy_group_id}/selection/static/activate',
        {
          params: { path: { strategy_group_id: 'CPM-RO-001' } },
          body: payload,
        }
      );
      expect(res.pending_selection_mode).toBe('static_baseline');
    });
  });
});
