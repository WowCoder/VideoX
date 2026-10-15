// ──────────────────────────────────────────────
// VideoX - Button 组件
// variant: primary / secondary / ghost / danger
// size: sm / md / lg
// ──────────────────────────────────────────────

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** 按钮图标（左侧） */
  leftIcon?: ReactNode;
  /** 按钮图标（右侧） */
  rightIcon?: ReactNode;
  children?: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-blue text-white hover:bg-blue-2 active:bg-blue-2 shadow-sm",
  secondary:
    "bg-surface text-text border border-line hover:bg-canvas active:bg-canvas",
  ghost: "text-text hover:bg-canvas active:bg-canvas",
  danger: "bg-red text-white hover:brightness-95 active:brightness-95 shadow-sm",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs gap-1",
  md: "px-4 py-2 text-sm gap-1.5",
  lg: "px-6 py-3 text-base gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      loading = false,
      leftIcon,
      rightIcon,
      children,
      className,
      disabled,
      ...rest
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-medium",
          "transition-all duration-fast ease-out",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-blue/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...rest}
      >
        {loading ? (
          <Spinner size={size === "lg" ? 20 : size === "sm" ? 14 : 16} />
        ) : (
          leftIcon
        )}
        {children}
        {!loading && rightIcon}
      </button>
    );
  },
);

Button.displayName = "Button";
