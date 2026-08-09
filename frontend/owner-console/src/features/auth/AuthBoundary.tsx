import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";
import { isUnauthorized } from "../../api/errors";
import { authSessionQueryKey, getAuthSession } from "./api";

export function AuthBoundary() {
  const session = useQuery({
    queryKey: authSessionQueryKey,
    queryFn: getAuthSession,
  });

  if (session.isPending) {
    return <main className="auth-status">正在验证会话…</main>;
  }
  if (session.isError) {
    return isUnauthorized(session.error) ? (
      <Navigate to="/login" replace />
    ) : (
      <main className="auth-status auth-status--error">认证状态不可用</main>
    );
  }

  return <Outlet />;
}
