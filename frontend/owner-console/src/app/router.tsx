import { lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";
import { AuthBoundary } from "../features/auth/AuthBoundary";
import { LoginRoute } from "../pages/LoginRoute";
import { OverviewRoute } from "../pages/OverviewRoute";
import { SignalsRoute } from "../pages/SignalsRoute";
import { TradesRoute } from "../pages/TradesRoute";
import { ControlsRoute } from "../pages/ControlsRoute";
import { StrategiesRoute } from "../pages/StrategiesRoute";
import { App } from "./App";

const TradeCausalityRoute = lazy(() => import("../pages/TradeCausalityRoute").then((module) => ({ default: module.TradeCausalityRoute })));
const ReviewRoute = lazy(() => import("../pages/ReviewRoute").then((module) => ({ default: module.ReviewRoute })));

function RouteFallback() {
  return <main className="auth-status">正在加载页面…</main>;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginRoute />,
  },
  {
    element: <AuthBoundary />,
    children: [
      {
        path: "/",
        element: <App />,
      },
      {
        path: "/overview",
        element: <OverviewRoute />,
      },
      {
        path: "/signals",
        element: <SignalsRoute />,
      },
      {
        path: "/trades",
        element: <TradesRoute />,
      },
      {
        path: "/trades/:ticketId",
        element: <Suspense fallback={<RouteFallback />}><TradeCausalityRoute /></Suspense>,
      },
      {
        path: "/controls",
        element: <ControlsRoute />,
      },
      {
        path: "/review",
        element: <Suspense fallback={<RouteFallback />}><ReviewRoute /></Suspense>,
      },
      {
        path: "/strategies",
        element: <StrategiesRoute />,
      },
      {
        path: "*",
        element: <App />,
      },
    ],
  },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, "") || "/" });
