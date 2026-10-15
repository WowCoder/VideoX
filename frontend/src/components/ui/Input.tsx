// ──────────────────────────────────────────────
// VideoX - Input 输入框组件
// ──────────────────────────────────────────────

import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/* ── 单行输入框 ── */

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  /** 输入框前缀图标 */
  leftIcon?: ReactNode;
  /** 输入框后缀图标 */
  rightIcon?: ReactNode;
  containerClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    { label, error, hint, leftIcon, rightIcon, className, containerClassName, id, ...rest },
    ref,
  ) => {
    const inputId = id || rest.name;

    return (
      <div className={cn("w-full", containerClassName)}>
        {label && (
          <label
            htmlFor={inputId}
            className="block mb-1.5 text-sm font-medium text-text"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-text",
              "placeholder:text-muted/60",
              "transition-colors duration-fast",
              "focus:outline-none focus:border-blue focus:ring-2 focus:ring-blue/20",
              leftIcon && "pl-10",
              rightIcon && "pr-10",
              error
                ? "border-red/50 focus:border-red focus:ring-red/20"
                : "border-line",
              className,
            )}
            {...rest}
          />
          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted">
              {rightIcon}
            </div>
          )}
        </div>
        {error ? (
          <p className="mt-1 text-xs text-red">{error}</p>
        ) : hint ? (
          <p className="mt-1 text-xs text-muted">{hint}</p>
        ) : null}
      </div>
    );
  },
);

Input.displayName = "Input";

/* ── 多行文本框 ── */

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, hint, className, containerClassName, id, ...rest }, ref) => {
    const textareaId = id || rest.name;

    return (
      <div className={cn("w-full", containerClassName)}>
        {label && (
          <label
            htmlFor={textareaId}
            className="block mb-1.5 text-sm font-medium text-text"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={cn(
            "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-text",
            "placeholder:text-muted/60 resize-none",
            "transition-colors duration-fast",
            "focus:outline-none focus:border-blue focus:ring-2 focus:ring-blue/20",
            error ? "border-red/50 focus:border-red focus:ring-red/20" : "border-line",
            className,
          )}
          {...rest}
        />
        {error ? (
          <p className="mt-1 text-xs text-red">{error}</p>
        ) : hint ? (
          <p className="mt-1 text-xs text-muted">{hint}</p>
        ) : null}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
