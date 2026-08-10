import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { ownerQueryClient, sessionExpiredEvent } from "../../app/queryClient";
import { isUnauthorized } from "../../api/errors";
import { authSessionQueryKey, getAuthSession } from "./api";

export function AuthBoundary() {
  const navigate = useNavigate();
  const session = useQuery({
    queryKey: authSessionQueryKey,
    queryFn: getAuthSession,
  });

  useEffect(() => {
    const redirectExpiredSession = () => {
      ownerQueryClient.clear();
      navigate("/login?reason=session_expired", { replace: true });
    };
    window.addEventListener(sessionExpiredEvent, redirectExpiredSession);
    return () => window.removeEventListener(sessionExpiredEvent, redirectExpiredSession);
  }, [navigate]);

  if (session.isPending) {
    return <main className="auth-status">正在验证会话…</main>;
  }
  if (session.isError) {
    return isUnauthorized(session.error) ? (
      <Navigate to="/login?reason=sign_in_required" replace />
    ) : (
      <main className="auth-status auth-status--error">认证状态不可用</main>
    );
  }

  return <Outlet />;
}
