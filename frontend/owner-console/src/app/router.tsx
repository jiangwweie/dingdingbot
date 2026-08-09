import { createBrowserRouter } from "react-router-dom";
import { AuthBoundary } from "../features/auth/AuthBoundary";
import { LoginRoute } from "../pages/LoginRoute";
import { OverviewRoute } from "../pages/OverviewRoute";
import { SignalsRoute } from "../pages/SignalsRoute";
import { TradeCausalityRoute } from "../pages/TradeCausalityRoute";
import { TradesRoute } from "../pages/TradesRoute";
import { App } from "./App";

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
        element: <TradeCausalityRoute />,
      },
      {
        path: "*",
        element: <App />,
      },
    ],
  },
]);
