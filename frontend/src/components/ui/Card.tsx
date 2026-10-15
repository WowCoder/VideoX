// ──────────────────────────────────────────────
// VideoX - Card 组件
// shadow-soft, rounded-xl
// ──────────────────────────────────────────────

import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** 是否去掉默认内边距 */
  noPadding?: boolean;
  /** 卡片标题 */
  title?: ReactNode;
  /** 卡片右上角操作区 */
  action?: ReactNode;
  children?: ReactNode;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ noPadding = false, title, action, children, className, ...rest }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "bg-surface rounded-xl shadow-soft border border-line/60",
          !noPadding && "p-6",
          className,
        )}
        {...rest}
      >
        {(title || action) && (
          <div className="mb-4 flex items-center justify-between">
            {title && (
              <h3 className="text-sm font-semibold text-text">{title}</h3>
            )}
            {action && <div>{action}</div>}
          </div>
        )}
        {children}
      </div>
    );
  },
);

Card.displayName = "Card";
