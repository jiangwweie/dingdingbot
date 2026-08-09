import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function Button({ className = "", type = "button", ...props }: ButtonProps) {
  const classes = ["owner-button", "h-8", className].filter(Boolean).join(" ");

  return <button className={classes} type={type} {...props} />;
}
