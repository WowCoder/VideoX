import { ChevronDown } from "lucide-react";
import type { SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  wrapperClassName?: string;
}

export function Select({ className = "", wrapperClassName = "", ...props }: SelectProps) {
  return (
    <span className={`relative block ${wrapperClassName}`}>
      <select
        {...props}
        className={`w-full appearance-none rounded-lg border border-line bg-white py-2.5 pl-3 pr-10 text-xs text-text outline-none transition focus:border-blue/50 focus:ring-2 focus:ring-blue/10 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      />
      <ChevronDown
        aria-hidden="true"
        size={14}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted"
      />
    </span>
  );
}
