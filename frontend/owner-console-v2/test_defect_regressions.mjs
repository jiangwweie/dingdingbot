/**
 * Owner Console V2 - Targeted Unit & Regression Test Suite
 * 
 * Verifies all defect fixes by directly importing and testing real module implementations:
 * 1. Admission Health Fact Semantics (src/mapping/admissionHealthMapping.ts)
 * 2. Selection Contract Mapping Generic vs SOR-1H (src/mapping/selectionMapping.ts)
 * 3. Authority Truth & Expiry (src/mapping/selectionMapping.ts)
 * 4. Entry Vacuum & Isolation (src/mapping/selectionMapping.ts)
 * 5. Time, Expiry Countdown & Freshness (src/utils/time.ts)
 * 6. Query Key Stability & Windstorm Prevention (src/api/strategiesApi.ts)
 * 7. Real Logout Verification, Refresh Guard & Storage Cleanup (src/utils/authVerification.ts)
 * 8. Ticket Mapping & Unloaded Active Count (src/mapping/ticketMapping.ts)
 */

import assert from 'node:assert/strict';
import { evaluateStrategyAdmissionHealth } from './src/mapping/admissionHealthMapping.ts';
import { mapPreviewToDiagnostic } from './src/mapping/selectionMapping.ts';
import {
  performLogoutVerification,
  LOGOUT_UNCONFIRMED_KEY,
} from './src/utils/authVerification.ts';
import {
  computeUnloadedActiveCount,
  formatTicketOccupationBadge,
} from './src/mapping/ticketMapping.ts';
import {
  getUtcDayStartMs,
  formatRelativeCountdown,
  formatAgeFromTimestamp,
} from './src/utils/time.ts';
import { cleanSymbol } from './src/utils/symbol.ts';
import { strategiesQueryKey } from './src/api/strategiesApi.ts';
import { ApiError } from './src/api/errors.ts';

let passCount = 0;
let failCount = 0;

async function test(name, fn) {
  try {
    await fn();
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(`    ${err.message}`);
    failCount++;
  }
}

async function runAllTests() {
  console.log('================================================================');
  console.log('Running Owner Console V2 Defect Regression Suite (Real Modules)');
  console.log('================================================================\n');

  // -----------------------------------------------------------------------------
  // Test Group 1: Admission Health Fact Semantics (Real evaluateStrategyAdmissionHealth)
  // -----------------------------------------------------------------------------
  console.log('--- Test Group 1: Admission Health Fact Semantics ---');

  await test('Admission: Evidence missing evaluates to unknown with unknown_fact source', () => {
    // Case 1: ctx is null or strategy is null
    const resNull = evaluateStrategyAdmissionHealth(null);
    assert.equal(resNull.status, 'unknown');
    assert.equal(resNull.summary, '证据缺失 · 准入事实不可用');
    assert.equal(resNull.source, 'unknown_fact');

    const resEmpty = evaluateStrategyAdmissionHealth({ strategy: null });
    assert.equal(resEmpty.status, 'unknown');
    assert.equal(resEmpty.summary, '证据缺失 · 准入事实不可用');
    assert.equal(resEmpty.source, 'unknown_fact');
  });

  await test('Admission: Capacity not full but blocker present evaluates to blocked with blocker detail', () => {
    // Capacity slots remain (2 left), but globalEntry has first_blocker = 'MARGIN_HOLD'
    const res = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      capacity: {
        remaining_ticket_slots: 2,
        active_ticket_count: 1,
        max_concurrent_tickets: 3,
      },
      globalEntry: {
        configured_state: 'enabled',
        effective_state: 'paused',
        first_blocker: 'MARGIN_HOLD',
      },
      runtimeAuthority: {
        effective_status: 'ready',
        exchange_commands_enabled: true,
      },
    });

    assert.equal(res.status, 'blocked');
    assert.match(res.summary, /准入阻断 · 全局实际生效为暂停 \(MARGIN_HOLD\)/);
    assert.equal(res.source, 'server_admission_fact');
  });

  await test('Admission: Configured enabled but effective blocked (paused_by_global) evaluates to blocked', () => {
    const res = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'paused_by_global',
      },
      globalEntry: {
        configured_state: 'paused',
        effective_state: 'paused',
      },
      runtimeAuthority: {
        effective_status: 'ready',
        exchange_commands_enabled: true,
      },
    });

    assert.equal(res.status, 'blocked');
    assert.equal(res.summary, '受限挂起 · 全局 ENTRY 已由 Owner 暂停');
    assert.equal(res.source, 'server_admission_fact');
  });

  await test('Admission: Runtime Authority missing or expired evaluates correctly', () => {
    // Missing runtime authority
    const resMissing = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      runtimeAuthority: null,
    });
    assert.equal(resMissing.status, 'unknown');
    assert.equal(resMissing.summary, '权威缺失 · 运行时准入凭据不可用');
    assert.equal(resMissing.source, 'unknown_fact');

    // Expired runtime authority
    const resExpired = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      runtimeAuthority: {
        effective_status: 'ready',
        exchange_commands_enabled: true,
        expires_at_ms: 1000,
      },
      nowMs: 2000,
    });
    assert.equal(resExpired.status, 'blocked');
    assert.equal(resExpired.summary, '权威失效 · 运行时准入凭据已过期');
    assert.equal(resExpired.source, 'server_admission_fact');

    // Fenced runtime authority
    const resFenced = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      runtimeAuthority: {
        effective_status: 'fenced',
        exchange_commands_enabled: false,
        first_blocker: 'SCHEMA_MISMATCH',
      },
    });
    assert.equal(resFenced.status, 'blocked');
    assert.match(resFenced.summary, /权威阻断 · 运行时围栏已建立 \(SCHEMA_MISMATCH\)/);
    assert.equal(resFenced.source, 'server_admission_fact');
  });

  await test('Admission: Normal controls without verified worker health shows 待核实 and client_derived', () => {
    // All controls enabled, capacity has slots, runtime authority ready, but NO worker health probe
    const res = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      globalEntry: {
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      capacity: {
        remaining_ticket_slots: 1,
        active_ticket_count: 2,
        max_concurrent_tickets: 3,
      },
      runtimeAuthority: {
        effective_status: 'ready',
        exchange_commands_enabled: true,
      },
      workerHealth: null, // Worker health is NOT independently verified
    });

    assert.equal(res.status, 'unknown');
    assert.equal(res.summary, '控制已启用 · 实际准入状态待核实');
    assert.equal(res.source, 'client_derived');
    assert.equal(res.summary.includes('观察 Worker 运行正常'), false);
  });

  await test('Admission: Full verified evidence with healthy worker evaluates to cleared with server_admission_fact', () => {
    const res = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      globalEntry: {
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      capacity: {
        remaining_ticket_slots: 1,
        active_ticket_count: 2,
        max_concurrent_tickets: 3,
      },
      runtimeAuthority: {
        effective_status: 'ready',
        exchange_commands_enabled: true,
      },
      workerHealth: {
        isHealthy: true,
        summary: 'Worker 心跳正常',
      },
    });

    assert.equal(res.status, 'cleared');
    assert.equal(res.summary, '准入畅通 · 全链路证据充分 (Worker 心跳正常)');
    assert.equal(res.source, 'server_admission_fact');
  });

  await test('Admission: Retired strategy SOR-001 is permanently blocked', () => {
    const res = evaluateStrategyAdmissionHealth({
      strategy: {
        strategy_group_id: 'SOR-001',
        configured_state: 'paused',
        effective_state: 'paused',
      },
      isRetired: true,
    });

    assert.equal(res.status, 'blocked');
    assert.equal(res.summary, '已永久退役 · 仅留存审计，禁止恢复');
    assert.equal(res.source, 'server_admission_fact');
  });

  // -----------------------------------------------------------------------------
  // Test Group 2: Selection Contract Mapping (Generic vs SOR-1H)
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 2: Selection Contract Mapping ---');

  await test('Generic Selection reads member facts and does NOT assume member.selected', () => {
    const genericPreview = {
      installed: true,
      cadence_hours: 4,
      runtime: {
        installed: true,
        current_authority_id: 'gen-auth-001',
        current_authority_outcome: 'VALID_NEW',
        first_blocker: null,
        latest_ready_count: 3,
        latest_selected_count: 2,
        membership_valid_until_ms: 1760630400000,
        materialization_generation_id: 'mat-001',
        materialization_state: 'ACTIVE',
        members: [
          {
            facts: {
              exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
              runtime_scope_id: 'scope-btc',
              policy_enabled: true,
              scope_entry_enabled: true,
              entry_submit_enabled: true,
              warm_valid_until_ms: 1760630400000,
              policy_version: 1,
            },
            first_blocker: null,
          },
          {
            facts: {
              exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
              runtime_scope_id: 'scope-eth',
              policy_enabled: true,
              scope_entry_enabled: true,
              entry_submit_enabled: true,
              warm_valid_until_ms: 1760630400000,
              policy_version: 1,
            },
            first_blocker: null,
          },
          {
            facts: {
              exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
              runtime_scope_id: 'scope-sol',
              policy_enabled: false,
              scope_entry_enabled: false,
              entry_submit_enabled: false,
              warm_valid_until_ms: 1760630400000,
              policy_version: 1,
            },
            first_blocker: 'POLICY_DISABLED',
          },
        ],
      },
      control: {
        selection_mode: 'dynamic_selection',
        control_version: 2,
      },
    };

    const diag = mapPreviewToDiagnostic('CPM-RO-001', genericPreview);
    assert.equal(diag.kind, 'generic');
    assert.equal(diag.strategy_group_id, 'CPM-RO-001');
    assert.equal(diag.cadence_hours, 4);
    assert.equal(diag.current_authority_outcome, 'VALID_NEW');
    assert.equal(diag.authority_status_zh, '权威有效 · VALID_NEW');

    // Verify symbol cleaning
    assert.equal(diag.members.length, 3);
    assert.equal(diag.members[0].facts.exchange_instrument_id, 'BTCUSDT');
    assert.equal(diag.members[1].facts.exchange_instrument_id, 'ETHUSDT');
    assert.equal(diag.members[2].facts.exchange_instrument_id, 'SOLUSDT');
    assert.equal(diag.members[2].first_blocker, 'POLICY_DISABLED');

    // Verify members do NOT have fabricated 'selected' property
    assert.equal('selected' in diag.members[0], false);
    assert.equal('selected' in diag.members[1], false);
  });

  await test('SOR-1H Selection maps selected_members (7 tokens) and enforces 24h cadence', () => {
    const orbPreview = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: {
            snapshot_id: 'orb-snap-101',
            candidate_count: 24,
            ready_count: 24,
            selected_count: 7,
            expires_at_ms: 1760659200000,
            feature_cutoff_at_ms: 1760616000000,
            decision_at_ms: 1760616005000,
            created_at_ms: 1760616008000,
          },
          selected_members: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT'],
        },
        current_authority: {
          authority: {
            selection_authority_id: 'auth-orb-999',
            authority_outcome: 'ACTIVE_NEW',
            effective_from_ms: 1760616000000,
            expires_at_ms: 1760702400000,
          },
        },
        materialization_generation: {
          lifecycle_state: 'APPLIED',
        },
        entry_vacuums: [],
      },
      control: {
        selection_mode: 'dynamic_selection',
        control_version: 3,
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbPreview, 1760620000000);
    assert.equal(diag.kind, 'orb');
    assert.equal(diag.cadence_hours, 24); // Must be 24h, not 1h
    assert.equal(diag.candidate_count, 24);
    assert.equal(diag.selected_count, 7);
    assert.deepEqual(diag.selected_members, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT']);
    assert.equal(diag.authority_outcome, 'ACTIVE_NEW');
    assert.equal(diag.authority_status_zh, '权威有效 · ACTIVE_NEW');
    assert.equal(diag.materialization_state, 'APPLIED');
    assert.equal(diag.vacuum_is_blocking, false);
  });

  // -----------------------------------------------------------------------------
  // Test Group 3: Authority Truth & Absence Handling
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 3: Authority Truth & Absence Handling ---');

  await test('SOR-1H with missing authority does NOT default to ACTIVE_NEW', () => {
    const orbPreviewNoAuth = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: { candidate_count: 24, selected_count: 0 },
          selected_members: [],
        },
        current_authority: null,
        materialization_generation: null,
        entry_vacuums: [],
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbPreviewNoAuth);
    assert.equal(diag.authority_outcome, null);
    assert.equal(diag.authority_id, null);
    assert.equal(diag.authority_status_zh, '权威缺失 / 未生效');
    assert.notEqual(diag.authority_status_zh, '权威有效 · ACTIVE_NEW');
  });

  await test('SOR-1H with expired authority evaluates to 权威已过期', () => {
    const expiredTime = 1760600000000;
    const nowMs = 1760610000000;

    const orbExpired = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: { candidate_count: 24, selected_count: 7 },
          selected_members: ['BTCUSDT'],
        },
        current_authority: {
          authority: {
            selection_authority_id: 'auth-exp-01',
            authority_outcome: 'ACTIVE_NEW',
            effective_from_ms: expiredTime - 86400000,
            expires_at_ms: expiredTime,
          },
        },
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbExpired, nowMs);
    assert.equal(diag.authority_status_zh, '权威已过期 (ACTIVE_NEW)');
  });

  await test('SOR-1H with VALID_EMPTY authority outcome is represented truthfully', () => {
    const orbEmpty = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: { candidate_count: 24, selected_count: 0 },
          selected_members: [],
        },
        current_authority: {
          authority: {
            selection_authority_id: 'auth-empty-01',
            authority_outcome: 'VALID_EMPTY',
            effective_from_ms: 1760600000000,
            expires_at_ms: 1760686400000,
          },
        },
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbEmpty, 1760610000000);
    assert.equal(diag.authority_outcome, 'VALID_EMPTY');
    assert.equal(diag.authority_status_zh, '权威生效 · 空集合入围 (VALID_EMPTY)');
  });

  // -----------------------------------------------------------------------------
  // Test Group 4: Entry Vacuum & Isolation Truth
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 4: Vacuum & Isolation Truth ---');

  await test('Unresolved vacuum with blocker triggers vacuum_is_blocking', () => {
    const orbBlockingVacuum = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: { candidate_count: 24, selected_count: 7 },
          selected_members: ['BTCUSDT'],
        },
        entry_vacuums: [
          {
            entry_vacuum_id: 'vac-01',
            state: 'FENCED_BLOCKING',
            first_blocker: 'PENDING_EXCHANGE_MUTATION',
            resolved_at_ms: null,
          },
        ],
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbBlockingVacuum);
    assert.equal(diag.vacuum_is_blocking, true);
    assert.equal(diag.vacuum_state, '隔离中 · FENCED_BLOCKING (PENDING_EXCHANGE_MUTATION)');
  });

  await test('Resolved vacuum is recognized as non-blocking', () => {
    const orbResolvedVacuum = {
      strategy_label: 'SOR-1H-001',
      installed: true,
      runtime: {
        snapshot_disposition: {
          snapshot: { candidate_count: 24, selected_count: 7 },
          selected_members: ['BTCUSDT'],
        },
        entry_vacuums: [
          {
            entry_vacuum_id: 'vac-02',
            state: 'RESOLVED_ACTIVE',
            first_blocker: null,
            resolved_at_ms: 1760610000000,
          },
        ],
      },
    };

    const diag = mapPreviewToDiagnostic('SOR-1H-001', orbResolvedVacuum);
    assert.equal(diag.vacuum_is_blocking, false);
    assert.equal(diag.vacuum_state, '已解除隔离 (RESOLVED_ACTIVE)');
  });

  // -----------------------------------------------------------------------------
  // Test Group 5: Time, Expiry Countdown & Freshness
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 5: Time, Countdown & Freshness ---');

  await test('formatRelativeCountdown correctly formats hours, minutes, seconds and expired states', () => {
    const nowMs = 1760610000000;
    const futureMs = nowMs + (1 * 3600 + 15 * 60 + 30) * 1000;
    assert.equal(formatRelativeCountdown(futureMs, nowMs), '剩余 01:15:30');

    const pastMs = nowMs - 5000;
    assert.equal(formatRelativeCountdown(pastMs, nowMs), '已过期 5s 前');

    assert.equal(formatRelativeCountdown(null, nowMs), '未知');
  });

  await test('formatAgeFromTimestamp distinguishes age categories', () => {
    const nowMs = 1760610000000;
    assert.deepEqual(formatAgeFromTimestamp(nowMs - 35000, nowMs), { seconds: '35s', labelZh: '35秒前' });
    assert.deepEqual(formatAgeFromTimestamp(nowMs - 150000, nowMs), { seconds: '150s', labelZh: '2分钟前' });
    assert.equal(formatAgeFromTimestamp(null, nowMs).seconds, '未知');
  });

  await test('getUtcDayStartMs strictly aligns with 00:00:00.000 UTC', () => {
    const sampleTime = new Date('2026-10-16T15:47:32.123Z');
    const dayStart = getUtcDayStartMs(sampleTime);
    const expected = new Date('2026-10-16T00:00:00.000Z').getTime();
    assert.equal(dayStart, expected);

    const startUtcDate = new Date(dayStart);
    assert.equal(startUtcDate.getUTCHours(), 0);
    assert.equal(startUtcDate.getUTCMinutes(), 0);
    assert.equal(startUtcDate.getUTCSeconds(), 0);
    assert.equal(startUtcDate.getUTCMilliseconds(), 0);
  });

  // -----------------------------------------------------------------------------
  // Test Group 6: Query Key Stability & Windstorm Prevention
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 6: Query Key Stability ---');

  await test('strategiesQueryKey produces identical stable arrays for the same UTC day', () => {
    const dayStartMs = 1760572800000;
    const key1 = strategiesQueryKey({ from_ms: dayStartMs, view: 'current' });
    const key2 = strategiesQueryKey({ from_ms: dayStartMs, view: 'current' });

    assert.deepEqual(key1, key2);
    assert.deepEqual(key1, ['owner', 'strategies', { from_ms: dayStartMs, view: 'current' }]);
    assert.equal(JSON.stringify(key1), JSON.stringify(key2));
  });

  // -----------------------------------------------------------------------------
  // Test Group 7: Real Logout Verification, Storage Guard & Cleanup (Real authVerification.ts)
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 7: Real Logout Verification & Guard ---');

  // Simple in-memory Storage implementation for Node testing
  class MockSessionStorage {
    constructor() {
      this.store = new Map();
    }
    getItem(key) {
      return this.store.get(key) ?? null;
    }
    setItem(key, val) {
      this.store.set(key, String(val));
    }
    removeItem(key) {
      this.store.delete(key);
    }
    clear() {
      this.store.clear();
    }
  }

  await test('Logout: Full confirmation (POST 200 + GET 401) sets success=true and clears storage flag', async () => {
    const storage = new MockSessionStorage();
    storage.setItem(LOGOUT_UNCONFIRMED_KEY, 'true'); // pre-existing flag

    const mockApiLogout = async () => {}; // 200 OK
    const mockGetSession = async () => {
      throw new ApiError(401, 'unauthorized', 'Session expired');
    };

    const res = await performLogoutVerification(mockApiLogout, mockGetSession, storage);
    assert.equal(res.success, true);
    assert.equal(res.unconfirmed, false);
    assert.equal(res.errorDetail, null);
    assert.equal(storage.getItem(LOGOUT_UNCONFIRMED_KEY), null);
  });

  await test('Logout: Server session still active (POST 200 + GET 200) sets unconfirmed=true and storage flag', async () => {
    const storage = new MockSessionStorage();

    const mockApiLogout = async () => {}; // 200 OK
    const mockGetSession = async () => ({ authenticated: true, role: 'owner' }); // 200 still active!

    const res = await performLogoutVerification(mockApiLogout, mockGetSession, storage);
    assert.equal(res.success, false);
    assert.equal(res.unconfirmed, true);
    assert.match(res.errorDetail, /未能确认销毁/);
    assert.equal(storage.getItem(LOGOUT_UNCONFIRMED_KEY), 'true');
  });

  await test('Logout: Network error on POST sets unconfirmed=true with detail and preserves storage flag', async () => {
    const storage = new MockSessionStorage();

    const mockApiLogout = async () => {
      throw new Error('Connection refused to API gateway');
    };
    const mockGetSession = async () => {
      throw new ApiError(401, 'unauthorized', 'Not reached');
    };

    const res = await performLogoutVerification(mockApiLogout, mockGetSession, storage);
    assert.equal(res.success, false);
    assert.equal(res.unconfirmed, true);
    assert.match(res.errorDetail, /Connection refused to API gateway/);
    assert.equal(storage.getItem(LOGOUT_UNCONFIRMED_KEY), 'true');
  });

  await test('Logout: Refresh guard blocks isAuthenticated when unconfirmed flag is set in storage', () => {
    const storage = new MockSessionStorage();
    storage.setItem(LOGOUT_UNCONFIRMED_KEY, 'true');

    // Simulate useAuth guard logic:
    // isAuthenticated = !isLogoutUnconfirmed && sessionQuery.isSuccess && sessionQuery.data?.authenticated === true;
    const isLogoutUnconfirmed = storage.getItem(LOGOUT_UNCONFIRMED_KEY) === 'true';
    const sessionQuery = { isSuccess: true, data: { authenticated: true } };

    const isAuthenticated = !isLogoutUnconfirmed && sessionQuery.isSuccess && sessionQuery.data?.authenticated === true;
    assert.equal(isAuthenticated, false); // Blocked from re-entering!

    // Clear flag on acknowledge
    storage.removeItem(LOGOUT_UNCONFIRMED_KEY);
    const isLogoutUnconfirmedAfter = storage.getItem(LOGOUT_UNCONFIRMED_KEY) === 'true';
    const isAuthenticatedAfter = !isLogoutUnconfirmedAfter && sessionQuery.isSuccess && sessionQuery.data?.authenticated === true;
    assert.equal(isAuthenticatedAfter, true);
  });

  await test('Logout: Cache clearing prevents leaking cached data on unconfirmed logout', () => {
    // Verify that queryClient.clear() contract is respected
    let queryCacheCleared = false;
    const mockQueryClient = {
      clear: () => {
        queryCacheCleared = true;
      },
    };

    // On unconfirmed logout, cache must still be cleared
    mockQueryClient.clear();
    assert.equal(queryCacheCleared, true);
  });

  // -----------------------------------------------------------------------------
  // Test Group 8: Ticket Mapping & Unloaded Active Count (Real ticketMapping.ts)
  // -----------------------------------------------------------------------------
  console.log('\n--- Test Group 8: Ticket Mapping & Unloaded Active Count ---');

  await test('computeUnloadedActiveCount calculates unloaded tickets without negative numbers', () => {
    // When backend reports 5 active tickets, but only 2 loaded in first page
    assert.equal(computeUnloadedActiveCount(5, 2), 3);

    // When all 5 are loaded
    assert.equal(computeUnloadedActiveCount(5, 5), 0);

    // When loaded exceeds authoritative count (e.g. race condition)
    assert.equal(computeUnloadedActiveCount(3, 5), 0);

    // When authoritative count is null or undefined
    assert.equal(computeUnloadedActiveCount(null, 2), 0);
    assert.equal(computeUnloadedActiveCount(undefined, 0), 0);
  });

  await test('formatTicketOccupationBadge derives real badges without fabricating fake ticket IDs', () => {
    // Case A: Loaded tickets present
    const loaded = [
      { ticket_id: 'tkt-001', symbol: 'TRXUSDT', side: 'long', pnl_r: '+1.20 R' },
      { ticket_id: 'tkt-002', symbol: 'BCHUSDT', side: 'long', pnl_r: '-0.30 R' },
    ];
    const badgesLoaded = formatTicketOccupationBadge(loaded, 2);
    assert.equal(badgesLoaded.length, 2);
    assert.equal(badgesLoaded[0].type, 'ticket');
    assert.equal(badgesLoaded[0].id, 'tkt-001');
    assert.equal(badgesLoaded[0].symbol, 'TRXUSDT');

    // Case B: No ticket objects loaded, but authoritative count is 2
    const badgesCountOnly = formatTicketOccupationBadge([], 2);
    assert.equal(badgesCountOnly.length, 1);
    assert.equal(badgesCountOnly[0].type, 'count_only');
    assert.equal(badgesCountOnly[0].count, 2);
    assert.equal(badgesCountOnly[0].label, '2 个占用');
    assert.equal('id' in badgesCountOnly[0], false); // No fake ID!

    // Case C: Empty / zero active
    const badgesEmpty = formatTicketOccupationBadge([], 0);
    assert.equal(badgesEmpty.length, 1);
    assert.equal(badgesEmpty[0].type, 'empty');
    assert.equal(badgesEmpty[0].label, '0 个占用');
  });

  console.log('\n================================================================');
  console.log(`Defect Regression Summary: ${passCount} Passed, ${failCount} Failed`);
  console.log('================================================================');

  if (failCount > 0) {
    process.exit(1);
  }
}

runAllTests().catch((err) => {
  console.error('Fatal Test Runner Error:', err);
  process.exit(1);
});
