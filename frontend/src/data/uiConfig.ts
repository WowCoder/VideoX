// ──────────────────────────────────────────────
// OpenVMA - UI 常量配置
// 导航项与样式映射（不包含业务 Mock 数据）
// ──────────────────────────────────────────────

export const navItems = [
  { id: "home", label: "工作台", path: "/workspace" },
  { id: "inspiration", label: "灵感岛", path: "/workspace/inspiration" },
  { id: "library", label: "素材库", path: "/workspace/library" },
] as const;

/** 缩略图渐变样式映射（避免外部图片依赖） */
export const variantGradient: Record<string, string> = {
  stage: "from-indigo-500 via-blue-500 to-cyan-400",
  robot: "from-slate-600 via-slate-500 to-zinc-400",
  interview: "from-amber-500 via-orange-500 to-rose-400",
  crowd: "from-emerald-500 via-teal-500 to-cyan-400",
  lights: "from-violet-600 via-purple-500 to-fuchsia-400",
  hall: "from-sky-600 via-blue-500 to-indigo-400",
  speaker: "from-rose-500 via-pink-500 to-orange-400",
};
