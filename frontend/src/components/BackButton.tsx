import { ArrowLeft } from "lucide-react";
import { useBackNavigation } from "@/router";

function routeLabel(path: string | null): string | null {
  if (!path) return null;
  const pathname = path.split(/[?#]/, 1)[0];
  if (pathname === "/workspace") return "综合工作台";
  if (pathname === "/workspace/scripts") return "脚本中心";
  if (pathname === "/workspace/projects") return "项目中心";
  if (pathname === "/workspace/library") return "素材库";
  if (pathname === "/workspace/notifications") return "通知中心";
  if (pathname === "/workspace/help") return "帮助中心";
  if (/^\/workspace\/projects\/[^/]+\/editor$/.test(pathname)) return "剪辑工作区";
  if (/^\/workspace\/projects\/[^/]+$/.test(pathname)) return "项目主页";
  if (/^\/workspace\/scripts\/[^/]+\/editor$/.test(pathname)) return "脚本编辑器";
  return "上一页";
}

export interface BackButtonProps {
  fallback: string;
  fallbackLabel: string;
  className?: string;
}

export function BackButton({ fallback, fallbackLabel, className }: BackButtonProps) {
  const { back, canGoBack, previousPath } = useBackNavigation();
  const destinationLabel = canGoBack ? routeLabel(previousPath) ?? "上一页" : fallbackLabel;

  return (
    <button
      type="button"
      onClick={() => back({ fallback })}
      className={className ?? "flex w-fit items-center gap-1.5 rounded-lg px-2 py-2 text-sm font-medium text-muted transition hover:bg-canvas hover:text-text"}
      title={`返回${destinationLabel}`}
    >
      <ArrowLeft className="h-4 w-4" />
      返回{destinationLabel}
    </button>
  );
}

export default BackButton;
