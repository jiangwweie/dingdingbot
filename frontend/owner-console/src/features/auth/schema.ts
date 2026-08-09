import { z } from "zod";

export const loginSchema = z.object({
  username: z.string().min(1, "请输入用户名"),
  password: z.string().min(1, "请输入密码"),
  totp_code: z.string().regex(/^\d{6}$/, "请输入六位动态验证码"),
});

export type LoginCredentials = z.infer<typeof loginSchema>;
