// ──────────────────────────────────────────────
// OpenVMA - Modal 弹窗组件
// open / onClose / title / children，带遮罩和动画
// ──────────────────────────────────────────────

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  /** 自定义底部操作区 */
  footer?: ReactNode;
  /** 弹窗宽度，默认 md */
  size?: "sm" | "md" | "lg" | "xl";
  /** 点击遮罩是否关闭，默认 true */
  maskClosable?: boolean;
  children?: ReactNode;
  className?: string;
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

export function Modal({
  open,
  onClose,
  title,
  footer,
  size = "md",
  maskClosable = true,
  children,
  className,
}: ModalProps) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
        style={{ animation: "ovma-fade-in 200ms ease-out" }}
        onClick={() => maskClosable && onClose()}
      />

      {/* 弹窗主体 */}
      <div
        className={cn(
          "relative w-full mx-4 bg-surface rounded-xl shadow-soft",
          "flex flex-col max-h-[90vh]",
          sizeClasses[size],
          className,
        )}
        style={{ animation: "ovma-modal-in 240ms cubic-bezier(0.16, 1, 0.3, 1)" }}
      >
        {/* 标题栏 */}
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-line">
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
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {/* 底部操作区 */}
        {footer && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-line">
            {footer}
          </div>
        )}
      </div>

      {/* 内联动画 keyframes */}
      <style>{`
        @keyframes ovma-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes ovma-modal-in {
          from {
            opacity: 0;
            transform: scale(0.96) translateY(8px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
