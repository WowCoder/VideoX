// ──────────────────────────────────────────────
// OpenVMA - Toast 提示组件
// message, autoClose 3.2s
// ──────────────────────────────────────────────

import { useEffect, useState, useCallback, type ReactNode } from "react";
import { CheckCircle2, AlertCircle, Info, XCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface ToastProps {
  message: string;
  variant?: ToastVariant;
  /** 自动关闭时间（毫秒），默认 3200ms；设为 0 则不自动关闭 */
  autoClose?: number;
  onClose?: () => void;
  className?: string;
}

const variantConfig: Record<
  ToastVariant,
  { icon: typeof CheckCircle2; iconClass: string }
> = {
  success: { icon: CheckCircle2, iconClass: "text-teal" },
  error: { icon: XCircle, iconClass: "text-red" },
  warning: { icon: AlertCircle, iconClass: "text-amber" },
  info: { icon: Info, iconClass: "text-blue" },
};

export function Toast({
  message,
  variant = "info",
  autoClose = 3200,
  onClose,
  className,
}: ToastProps) {
  const [visible, setVisible] = useState(true);
  const config = variantConfig[variant];
  const Icon = config.icon;

  const handleClose = useCallback(() => {
    setVisible(false);
    // 等待退出动画后再回调
    setTimeout(() => onClose?.(), 200);
  }, [onClose]);

  useEffect(() => {
    if (autoClose <= 0) return;
    const timer = setTimeout(handleClose, autoClose);
    return () => clearTimeout(timer);
  }, [autoClose, handleClose]);

  return (
    <div
      className={cn(
        "flex items-start gap-3 bg-surface rounded-xl shadow-soft border border-line",
        "px-4 py-3 min-w-[280px] max-w-md",
        "transition-all duration-200",
        visible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-2",
        className,
      )}
    >
      <Icon size={18} className={cn("shrink-0 mt-0.5", config.iconClass)} />
      <p className="flex-1 text-sm text-text leading-relaxed">{message}</p>
      <button
        onClick={handleClose}
        className="shrink-0 text-muted hover:text-text transition-colors"
      >
        <X size={16} />
      </button>
    </div>
  );
}

/* ── Toast 容器（用于渲染多条 Toast）── */

export interface ToastItem {
  id: string;
  message: string;
  variant?: ToastVariant;
  autoClose?: number;
}

export interface ToastContainerProps {
  toasts: ToastItem[];
  onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed top-4 right-4 z-[60] flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast
            message={toast.message}
            variant={toast.variant}
            autoClose={toast.autoClose}
            onClose={() => onRemove(toast.id)}
          />
        </div>
      ))}
    </div>
  );
}

/* ── 便捷的 Toast 管理器（基于 React state）── */

export function useToastManager() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback(
    (message: string, variant: ToastVariant = "info", autoClose = 3200) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setToasts((prev) => [...prev, { id, message, variant, autoClose }]);
    },
    [],
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return {
    toasts,
    addToast,
    removeToast,
    toast: {
      success: (msg: string) => addToast(msg, "success"),
      error: (msg: string) => addToast(msg, "error"),
      warning: (msg: string) => addToast(msg, "warning"),
      info: (msg: string) => addToast(msg, "info"),
    },
  };
}

export type ToastManager = ReturnType<typeof useToastManager>;

/** 兼容 ReactNode 类型 */
export type { ReactNode };
