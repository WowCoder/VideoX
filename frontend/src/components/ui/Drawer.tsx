// ──────────────────────────────────────────────
// OpenVMA - Drawer 抽屉组件
// 从右侧滑出，open / onClose / children
// ──────────────────────────────────────────────

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  /** 抽屉宽度，默认 480px */
  width?: number | string;
  /** 点击遮罩是否关闭，默认 true */
  maskClosable?: boolean;
  children?: ReactNode;
  className?: string;
}

export function Drawer({
  open,
  onClose,
  title,
  width = 480,
  maskClosable = true,
  children,
  className,
}: DrawerProps) {
  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // 锁定滚动
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        style={{ animation: "ovma-fade-in 200ms ease-out" }}
        onClick={() => maskClosable && onClose()}
      />

      {/* 抽屉面板 */}
      <div
        className={cn(
          "absolute right-0 top-0 h-full bg-surface shadow-soft",
          "flex flex-col",
          className,
        )}
        style={{
          width: typeof width === "number" ? `${width}px` : width,
          animation: "ovma-drawer-in 280ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {/* 标题栏 */}
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-line shrink-0">
            <h2 className="text-base font-semibold text-text">{title}</h2>
            <button
              onClick={onClose}
              className="text-muted hover:text-text transition-colors p-1 rounded-lg hover:bg-canvas"
            >
              <X size={18} />
            </button>
          </div>
        )}

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>

      {/* 内联动画 keyframes */}
      <style>{`
        @keyframes ovma-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes ovma-drawer-in {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
      `}</style>
    </div>
  );
}
