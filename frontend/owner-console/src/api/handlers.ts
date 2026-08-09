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
];
