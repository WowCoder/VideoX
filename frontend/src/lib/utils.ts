// ──────────────────────────────────────────────
// OpenVMA - 通用工具函数
// ──────────────────────────────────────────────

import { clsx, type ClassValue } from "clsx";

/**
 * className 合并工具（clsx 封装）
 * 用法：cn("px-4", condition && "bg-blue", { "text-red": hasError })
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

/**
 * 将秒数格式化为 mm:ss 或 hh:mm:ss
 * @param seconds 秒数
 * @returns 格式化后的时间字符串
 */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(m)}:${pad(s)}`;
}

/**
 * 将秒数格式化为可读时长（如 "1时23分"、"5分30秒"、"12秒"）
 * @param seconds 秒数
 * @returns 中文可读时长字符串
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0秒";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}时`);
  if (m > 0) parts.push(`${m}分`);
  if (s > 0 || parts.length === 0) parts.push(`${s}秒`);
  return parts.join("");
}

/**
 * 将后端真实 ISO 时间格式化为相对时间；超过一天时显示具体日期时间。
 */
export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";

  const diff = Date.now() - date.getTime();
  if (diff < 0) {
    return date.toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.max(1, Math.floor(diff / 60_000))} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`;
  return date.toLocaleString("zh-CN", {
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * 根据状态文本返回对应的 Tailwind 颜色 class
 * 用于 Badge、状态标签等组件
 */
export function statusColor(status: string): string {
  const map: Record<string, string> = {
    // 通用状态
    处理中: "bg-amber/10 text-amber",
    "AI 处理中": "bg-amber/10 text-amber",
    处理完成: "bg-teal/10 text-teal",
    "全部可搜索": "bg-teal/10 text-teal",
    "素材已就绪": "bg-blue/10 text-blue",
    等待上传: "bg-muted/10 text-muted",
    失败: "bg-red/10 text-red",

    // 项目状态
    "脚本编辑中": "bg-blue/10 text-blue",
    "脚本已导入": "bg-blue/10 text-blue",
    "AI 初剪生成中": "bg-amber/10 text-amber",
    "AI 初剪可编辑": "bg-teal/10 text-teal",

    // 脚本状态
    编辑中: "bg-blue/10 text-blue",
    待匹配: "bg-amber/10 text-amber",
    待确认: "bg-amber/10 text-amber",
    已完成: "bg-teal/10 text-teal",
    "初剪生成中": "bg-amber/10 text-amber",
    "初剪可编辑": "bg-teal/10 text-teal",

    // 分镜单元状态
    已选择: "bg-teal/10 text-teal",
    有候选: "bg-blue/10 text-blue",
    待编辑: "bg-muted/10 text-muted",

    // Job 状态
    QUEUED: "bg-muted/10 text-muted",
    RUNNING: "bg-blue/10 text-blue",
    SUCCEEDED: "bg-teal/10 text-teal",
    FAILED: "bg-red/10 text-red",
    PAUSED: "bg-amber/10 text-amber",
  };
  return map[status] ?? "bg-muted/10 text-muted";
}
