import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ownerQueryClient } from "../app/queryClient";
import { authSessionQueryKey } from "../features/auth/api";
import { LoginPage } from "../features/auth/LoginPage";

export function LoginRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loginFailed, setLoginFailed] = useState(false);

  const handleAuthenticated = () => {
    ownerQueryClient.removeQueries({ queryKey: authSessionQueryKey });
    navigate("/", { replace: true });
  };

  return (
    <>
      <LoginPage
        onAuthenticated={handleAuthenticated}
        onError={() => setLoginFailed(true)}
        notice={searchParams.get("reason") === "session_expired" ? "登录已超时，请重新进行 Google Authenticator 验证。" : null}
      />
      {loginFailed ? (
        <div className="login-route-error" role="alert">
          登录失败
        </div>
      ) : null}
    </>
  );
}
