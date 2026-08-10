import { useForm } from "react-hook-form";
import { Button } from "../../components/ui/Button";
import { login } from "./api";
import { loginSchema, type LoginCredentials } from "./schema";

interface LoginPageProps {
  onAuthenticated: () => void;
  onError: (error: unknown) => void;
  notice?: string | null;
}

const defaultValues: LoginCredentials = {
  username: "",
  password: "",
  totp_code: "",
};

export function LoginPage({ onAuthenticated, onError, notice = null }: LoginPageProps) {
  const {
    clearErrors,
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
    setError,
  } = useForm<LoginCredentials>({ defaultValues });

  const submit = handleSubmit(async (values) => {
    clearErrors();
    const parsed = loginSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (field === "username" || field === "password" || field === "totp_code") {
          setError(field, { message: issue.message, type: "validate" });
        }
      }
      return;
    }

    try {
      await login(parsed.data);
      onAuthenticated();
    } catch (error) {
      onError(error);
    }
  });

  return (
    <main className="login-layout">
      <section className="login-panel" aria-labelledby="login-title">
        <header className="login-panel__header">
          <span className="brand-mark">BRC OWNER</span>
          <span className="login-panel__environment tabular-number">PROD</span>
        </header>
        <form className="login-form" onSubmit={submit} noValidate>
          <div className="login-form__heading">
            <h1 id="login-title">Owner 登录</h1>
            <p>输入 Owner 凭据与当前动态验证码。</p>
          </div>
          {notice ? <p className="login-form__notice" role="status">{notice}</p> : null}

          <div className="login-field">
            <label htmlFor="owner-username">用户名</label>
            <input
              id="owner-username"
              autoComplete="username"
              aria-invalid={errors.username ? "true" : "false"}
              {...register("username")}
            />
            <span className="login-field__error">{errors.username?.message ?? ""}</span>
          </div>

          <div className="login-field">
            <label htmlFor="owner-password">密码</label>
            <input
              id="owner-password"
              type="password"
              autoComplete="current-password"
              aria-invalid={errors.password ? "true" : "false"}
              {...register("password")}
            />
            <span className="login-field__error">{errors.password?.message ?? ""}</span>
          </div>

          <div className="login-field">
            <label htmlFor="owner-totp">动态验证码</label>
            <input
              id="owner-totp"
              className="tabular-number"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              aria-invalid={errors.totp_code ? "true" : "false"}
              {...register("totp_code")}
            />
            <span className="login-field__error">{errors.totp_code?.message ?? ""}</span>
          </div>

          <Button className="login-form__submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "登录中" : "登录"}
          </Button>
        </form>
      </section>
    </main>
  );
}
