// ──────────────────────────────────────────────
// OpenVMA - Spinner 加载动画组件
// ──────────────────────────────────────────────

import { cn } from "@/lib/utils";

export interface SpinnerProps {
  size?: number;
  className?: string;
  /** 颜色 class，默认 text-blue */
  colorClass?: string;
  strokeWidth?: number;
}

/**
 * SVG 旋转加载动画
 *
 * @example
 * <Spinner size={24} />
 * <Spinner size={16} colorClass="text-white" />
 */
export function Spinner({
  size = 20,
  className,
  colorClass = "text-blue",
  strokeWidth = 2.5,
}: SpinnerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={cn("animate-spin", colorClass, className)}
      role="status"
      aria-label="加载中"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeOpacity="0.2"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </svg>
  );
}
