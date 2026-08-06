// ──────────────────────────────────────────────
// OpenVMA - Badge 标签组件
// variant: default / success / warning / danger / info
// ──────────────────────────────────────────────

import { type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type BadgeVariant = "default" | "success" | "warning" | "danger" | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  /** 是否使用描边样式（而非填充） */
  outline?: boolean;
  children?: ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-muted/10 text-muted",
  success: "bg-teal/10 text-teal",
  warning: "bg-amber/10 text-amber",
  danger: "bg-red/10 text-red",
  info: "bg-blue/10 text-blue",
};

const outlineClasses: Record<BadgeVariant, string> = {
  default: "border border-line text-muted",
  success: "border border-teal/30 text-teal",
  warning: "border border-amber/30 text-amber",
  danger: "border border-red/30 text-red",
  info: "border border-blue/30 text-blue",
};

export function Badge({
  variant = "default",
  outline = false,
  children,
  className,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-xs font-medium",
        outline ? outlineClasses[variant] : variantClasses[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
