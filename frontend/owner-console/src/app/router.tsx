import { createBrowserRouter } from "react-router-dom";
import { AuthBoundary } from "../features/auth/AuthBoundary";
import { LoginRoute } from "../pages/LoginRoute";
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
        path: "*",
        element: <App />,
      },
    ],
  },
]);
