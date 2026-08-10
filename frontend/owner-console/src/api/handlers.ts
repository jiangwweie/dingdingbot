import { http, HttpResponse } from "msw";
import { ownerApiFixtures } from "./fixtures";

export const ownerApiHandlers = [
  http.get("/api/owner/v1/auth/session", () => HttpResponse.json({ authenticated: true })),
  http.post("/api/owner/v1/auth/login", () => new HttpResponse(null, { status: 204 })),
  http.post("/api/owner/v1/auth/logout", () => new HttpResponse(null, { status: 204 })),
  http.get("/api/owner/v1/overview", () => HttpResponse.json(ownerApiFixtures.overviewFixture)),
  http.get("/api/owner/v1/signals", () => HttpResponse.json(ownerApiFixtures.signalListFixture)),
  http.get("/api/owner/v1/signals/:signalEventId", () => HttpResponse.json(ownerApiFixtures.signalDetailFixture)),
  http.get("/api/owner/v1/tickets", () => HttpResponse.json(ownerApiFixtures.tradeListFixture)),
  http.get("/api/owner/v1/tickets/:ticketId/causality", () => HttpResponse.json(ownerApiFixtures.tradeCausalityFixture)),
  http.get("/api/owner/v1/market/candles", () => HttpResponse.json(ownerApiFixtures.candleFixture)),
  http.get("/api/owner/v1/review", () => HttpResponse.json(ownerApiFixtures.reviewFixture)),
  http.get("/api/owner/v1/strategies", () => HttpResponse.json(ownerApiFixtures.strategyFixture)),
  http.get("/api/owner/v1/strategies/:strategyVersionId/tickets", () => HttpResponse.json(ownerApiFixtures.strategyTicketFixture)),
  http.get("/api/owner/v1/controls", () => HttpResponse.json({
    generated_at_ms: 1800000000000,
    global_entry: { configured_state: "enabled", effective_state: "enabled", policy_version: 5, active_ticket_count: 2, first_blocker: null },
    strategies: [
      { strategy_group_id: "SOR-001", entry_state: "enabled", control_version: 1, last_event_id: "strategy-control-event:seed:SOR-001", reason: "seed_enabled", updated_at_ms: 1800000000000, configured_state: "enabled", effective_state: "enabled" },
      { strategy_group_id: "BRF2-001", entry_state: "enabled", control_version: 1, last_event_id: "strategy-control-event:seed:BRF2-001", reason: "seed_enabled", updated_at_ms: 1800000000000, configured_state: "enabled", effective_state: "enabled" },
    ],
    current_operation: null,
    recent_operations: [],
    events: [],
  })),
  http.post("/api/owner/v1/controls/exposure/flatten-all/preview", () => HttpResponse.json({
    runtime_profile_id: "tiny-live-v1", venue_id: "binance-usdm", account_id: "owner-account", owner_policy_version: 5, global_entry_enabled: true,
    ticket_ids: ["ticket:ada-short", "ticket:btc-long"], ticket_states: { "ticket:ada-short": "eligible", "ticket:btc-long": "eligible" }, snapshot_digest: `sha256:${"a".repeat(64)}`, first_blocker: null,
  })),
  http.post("/api/owner/v1/controls/strategies/:strategyGroupId/pause", () => HttpResponse.json({})),
  http.post("/api/owner/v1/controls/strategies/:strategyGroupId/resume", () => HttpResponse.json({})),
  http.post("/api/owner/v1/controls/entry/pause", () => HttpResponse.json({})),
  http.post("/api/owner/v1/controls/entry/resume", () => HttpResponse.json({})),
  http.post("/api/owner/v1/controls/exposure/flatten-all", () => HttpResponse.json({
    authorization_id: "owner-authorization:test", operation_kind: "flatten_all", state: "pending", version: 2, runtime_profile_id: "tiny-live-v1", venue_id: "binance-usdm", account_id: "owner-account", target_ticket_ids: ["ticket:ada-short", "ticket:btc-long"], snapshot_digest: `sha256:${"a".repeat(64)}`, first_blocker: null, claimed_by: null, lease_until_ms: null, created_at_ms: 1800000000000, updated_at_ms: 1800000000000,
  }, { status: 201 })),
];
