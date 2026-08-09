import type { Page, Route } from "@playwright/test";
import { ownerApiFixtures } from "../src/api/fixtures";

export interface ApiRequestCounts {
  candles: number;
  causality: number;
  login: number;
  logout: number;
  overview: number;
  review: number;
  session: number;
  signals: number;
  signalDetail: number;
  trades: number;
}

interface ApiRouteOptions {
  authenticated?: boolean;
  candleFailure?: boolean;
  expireSession?: boolean;
  failOverviewAfter?: number;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function installApiRoutes(page: Page, options: ApiRouteOptions = {}): Promise<ApiRequestCounts> {
  let authenticated = options.authenticated ?? false;
  const counts: ApiRequestCounts = { candles: 0, causality: 0, login: 0, logout: 0, overview: 0, review: 0, session: 0, signals: 0, signalDetail: 0, trades: 0 };

  await page.route("**/api/owner/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/owner/v1/auth/login") {
      counts.login += 1;
      const body = request.postDataJSON() as { password?: string; totp_code?: string; username?: string };
      if (body.username === "owner" && body.password === "correct horse" && body.totp_code === "123456") {
        authenticated = true;
        await route.fulfill({ status: 204, body: "" });
      } else {
        await json(route, { error: { code: "unauthorized", message: "Invalid credentials" } }, 401);
      }
      return;
    }
    if (path === "/api/owner/v1/auth/logout") {
      counts.logout += 1;
      authenticated = false;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (path === "/api/owner/v1/auth/session") {
      counts.session += 1;
      if (!authenticated || options.expireSession) {
        await json(route, { error: { code: "unauthorized", message: "Session expired" } }, 401);
      } else {
        await json(route, { authenticated: true });
      }
      return;
    }

    if (!authenticated) {
      await json(route, { error: { code: "unauthorized", message: "Authentication required" } }, 401);
      return;
    }
    if (path === "/api/owner/v1/overview") {
      counts.overview += 1;
      if (options.failOverviewAfter !== undefined && counts.overview > options.failOverviewAfter) {
        await json(route, { error: { code: "unavailable", message: "Fixture refresh failure" } }, 503);
      } else {
        await json(route, ownerApiFixtures.overviewFixture);
      }
      return;
    }
    if (path === "/api/owner/v1/signals") {
      counts.signals += 1;
      await json(route, ownerApiFixtures.signalListFixture);
      return;
    }
    if (path.startsWith("/api/owner/v1/signals/")) {
      counts.signalDetail += 1;
      await json(route, ownerApiFixtures.signalDetailFixture);
      return;
    }
    if (path === "/api/owner/v1/tickets") {
      counts.trades += 1;
      await json(route, ownerApiFixtures.tradeListFixture);
      return;
    }
    if (path.startsWith("/api/owner/v1/tickets/") && path.endsWith("/causality")) {
      counts.causality += 1;
      await json(route, ownerApiFixtures.tradeCausalityFixture);
      return;
    }
    if (path === "/api/owner/v1/market/candles") {
      counts.candles += 1;
      if (options.candleFailure) {
        await json(route, { error: { code: "public_market_unavailable", message: "Fixture candle failure" } }, 503);
      } else {
        await json(route, ownerApiFixtures.candleFixture);
      }
      return;
    }
    if (path === "/api/owner/v1/review") {
      counts.review += 1;
      await json(route, ownerApiFixtures.reviewFixture);
      return;
    }
    await json(route, { error: { code: "not_found", message: "Fixture route not found" } }, 404);
  });
  return counts;
}
