import { render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProviders } from "../../app/providers";
import { ownerQueryClient } from "../../app/queryClient";
import { AuthBoundary } from "./AuthBoundary";
import { LoginPage } from "./LoginPage";
import { ApiError } from "../../api/errors";

const apiClientMock = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}));

vi.mock("../../api/client", () => ({ apiClient: apiClientMock }));

beforeEach(() => {
  ownerQueryClient.clear();
  apiClientMock.GET.mockReset();
  apiClientMock.POST.mockReset();
});

afterEach(() => {
  ownerQueryClient.clear();
});

it("submits only valid username, password, and exact six-digit TOTP to login", async () => {
  const user = userEvent.setup();
  apiClientMock.POST.mockResolvedValue({
    error: undefined,
    response: new Response(null, { status: 204 }),
  });
  const authenticated = vi.fn();

  render(<LoginPage onAuthenticated={authenticated} onError={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(screen.getByText("请输入用户名")).toBeInTheDocument();
  expect(screen.getByText("请输入密码")).toBeInTheDocument();
  expect(screen.getByText("请输入六位动态验证码")).toBeInTheDocument();
  expect(apiClientMock.POST).not.toHaveBeenCalled();

  await user.type(screen.getByLabelText("用户名"), "owner-01");
  await user.type(screen.getByLabelText("密码"), "  exact password  ");
  await user.type(screen.getByLabelText("动态验证码"), "12345");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(screen.getByText("请输入六位动态验证码")).toBeInTheDocument();
  expect(apiClientMock.POST).not.toHaveBeenCalled();

  await user.type(screen.getByLabelText("动态验证码"), "6");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(apiClientMock.POST).toHaveBeenCalledTimes(1);
  expect(apiClientMock.POST).toHaveBeenCalledWith("/api/owner/v1/auth/login", {
    body: {
      username: "owner-01",
      password: "  exact password  ",
      totp_code: "123456",
    },
  });
  expect(authenticated).toHaveBeenCalledTimes(1);
});

it("queries the session once on protected navigation without focus or reconnect polling", async () => {
  apiClientMock.GET.mockResolvedValue({
    data: { authenticated: true },
    error: undefined,
    response: new Response(JSON.stringify({ authenticated: true }), { status: 200 }),
  });
  const router = createMemoryRouter(
    [
      {
        element: <AuthBoundary />,
        children: [{ path: "/", element: <div>protected content</div> }],
      },
      { path: "/login", element: <div>login route</div> },
    ],
    { initialEntries: ["/"] },
  );

  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );

  expect(await screen.findByText("protected content")).toBeInTheDocument();
  window.dispatchEvent(new Event("focus"));
  window.dispatchEvent(new Event("online"));
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(apiClientMock.GET).toHaveBeenCalledTimes(1);
  expect(apiClientMock.GET).toHaveBeenCalledWith("/api/owner/v1/auth/session");
});

it("redirects a protected navigation to login on 401", async () => {
  apiClientMock.GET.mockResolvedValue({
    data: undefined,
    error: { error: { code: "unauthorized", message: "Authentication required" } },
    response: new Response(null, { status: 401 }),
  });
  const router = createMemoryRouter(
    [
      {
        element: <AuthBoundary />,
        children: [{ path: "/", element: <div>protected content</div> }],
      },
      { path: "/login", element: <div>login route</div> },
    ],
    { initialEntries: ["/"] },
  );

  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );

  expect(await screen.findByText("login route")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/login");
});

it("redirects an already authenticated page to an explicit session-expired login after a later 401", async () => {
  apiClientMock.GET.mockResolvedValue({
    data: { authenticated: true },
    error: undefined,
    response: new Response(JSON.stringify({ authenticated: true }), { status: 200 }),
  });
  function ProtectedQuery() {
    useQuery({ queryKey: ["owner", "expired"], queryFn: async () => { throw new ApiError(401, "unauthorized", "Authentication required"); } });
    return <div>protected content</div>;
  }
  const router = createMemoryRouter(
    [
      { element: <AuthBoundary />, children: [{ path: "/", element: <ProtectedQuery /> }] },
      { path: "/login", element: <div>login route</div> },
    ],
    { initialEntries: ["/"] },
  );

  render(<AppProviders><RouterProvider router={router} /></AppProviders>);

  expect(await screen.findByText("login route")).toBeInTheDocument();
  expect(router.state.location.search).toBe("?reason=session_expired");
});
