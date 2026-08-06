// ──────────────────────────────────────────────
// OpenVMA - 帮助中心
// 分类导航 + 文章列表 + FAQ
// ──────────────────────────────────────────────

import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  Film,
  FolderKanban,
  HelpCircle,
  Library,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";

const helpIcons = {
  book: BookOpen,
  file: FileText,
  film: Film,
  help: CircleHelp,
  library: Library,
  project: FolderKanban,
  sparkles: Sparkles,
  upload: Upload,
} as const;

const helpCategories = [
  { id: "start", label: "快速开始", icon: "sparkles" as const },
  { id: "upload", label: "素材上传", icon: "upload" as const },
  { id: "script", label: "脚本与分镜", icon: "file" as const },
  { id: "library", label: "素材库", icon: "library" as const },
  { id: "project", label: "项目与初剪", icon: "project" as const },
  { id: "export", label: "导出与交付", icon: "film" as const },
];

interface HelpArticle {
  id: string;
  category: string;
  icon: keyof typeof helpIcons;
  title: string;
  summary: string;
  steps: string[];
}

const helpArticles: HelpArticle[] = [
  {
    id: "start",
    category: "start",
    icon: "sparkles",
    title: "5 分钟快速开始",
    summary: "从上传素材到生成第一版初剪的完整流程。",
    steps: [
      "上传几段视频素材，系统会自动转码、切片并理解画面与对白。",
      "在脚本中心新建脚本：粘贴文本、上传表格或使用 AI 生成。",
      "选择脚本单元，查看 AI 推荐的候选镜头并确认。",
      "缺失的镜头可由 AI 生图或图生视频补齐。",
      "点击「生成初剪」，AI 自动装配多轨时间线。",
    ],
  },
  {
    id: "upload",
    category: "upload",
    icon: "upload",
    title: "上传素材的格式与限制",
    summary: "支持 MP4 / MOV / MKV 等常见格式，单文件最大 5GB。",
    steps: [
      "在素材库或工作台点击「上传素材」。",
      "拖拽文件到上传区，或点击选择文件。",
      "上传完成后系统自动开始转码与理解。",
      "处理完成后素材会显示「处理完成」状态并生成可搜索片段。",
    ],
  },
  {
    id: "script-paste",
    category: "script",
    icon: "file",
    title: "用粘贴文本创建脚本",
    summary: "每行识别为一个脚本单元，支持序号 + 内容格式。",
    steps: [
      "在脚本中心点击「新建脚本」。",
      "选择「粘贴文本」模式。",
      "输入标题，在文本框中粘贴台词内容。",
      "点击「解析并预览」确认脚本单元、分镜意图与建议时长。",
      "确认后点击「创建脚本」进入编辑器。",
    ],
  },
  {
    id: "ai-script",
    category: "script",
    icon: "sparkles",
    title: "使用 AI 生成脚本",
    summary: "描述创作目标，AI 自动生成可编辑的分镜脚本。",
    steps: [
      "点击「AI 生成」打开需求设置面板。",
      "描述你的创作需求、目标受众与核心信息。",
      "选择目标时长与表达语气。",
      "点击「开始生成」，等待 AI 完成分镜撰写。",
      "在预览中确认后，应用到脚本编辑器继续调整。",
    ],
  },
  {
    id: "library-search",
    category: "library",
    icon: "library",
    title: "在素材库中搜索片段",
    summary: "用自然语言搜索素材中的具体片段。",
    steps: [
      "进入素材库，点击任意已处理完成的素材。",
      "在详情面板点击「搜索片段」。",
      "输入自然语言描述，如「机器人走向展台的镜头」。",
      "系统返回匹配的片段，包含置信度与匹配理由。",
    ],
  },
  {
    id: "rough-cut",
    category: "project",
    icon: "project",
    title: "生成 AI 初剪项目",
    summary: "从脚本一键创建初剪项目，自动匹配镜头并补齐缺失画面。",
    steps: [
      "在脚本编辑器中完成分镜配置。",
      "点击「生成初剪」按钮。",
      "系统创建新项目并开始匹配素材与生成缺失画面。",
      "处理完成后进入剪辑工作区继续精剪。",
    ],
  },
];

const helpFaqs: [string, string][] = [
  [
    "处理一段素材需要多长时间？",
    "通常为素材时长的 0.3—0.6 倍。一段 30 分钟的视频大约需要 10—18 分钟完成转码、语音识别、视觉理解与索引建立。",
  ],
  [
    "AI 生成的画面会和原有素材不一致吗？",
    "OpenVMA 会引用脚本中锁定的人物、物品、空间、画幅与色彩风格，让 AI 补齐镜头尽量保持视觉连续。你仍可在剪辑工作区替换任何不满意的镜头。",
  ],
  [
    "支持哪些导出格式？",
    "支持横屏 16:9、竖屏 9:16、方形 1:1 与 4:3 四种画幅，可导出 MP4 成片或导入 Premiere / Final Cut Pro / DaVinci 的剪辑工程文件。",
  ],
  [
    "Free 方案有什么限制？",
    "Free 方案每月 600 分钟处理时长、100 张 AI 生图、20 段 AI 生视频，导出带有 OpenVMA 水印。升级 Pro 可解锁无水印导出与更高额度。",
  ],
];

export function HelpCenterView() {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("start");
  const [selectedArticleId, setSelectedArticleId] = useState("start");
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const normalizedQuery = query.trim().toLowerCase();
  const visibleArticles = helpArticles.filter(
    (article) =>
      (activeCategory === "all" || article.category === activeCategory) &&
      (!normalizedQuery ||
        `${article.title}${article.summary}${article.steps.join("")}`
          .toLowerCase()
          .includes(normalizedQuery)),
  );
  const selectedArticle =
    visibleArticles.find((a) => a.id === selectedArticleId) ?? visibleArticles[0] ?? null;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* 页头 */}
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-text">帮助中心</h1>
        <p className="mt-1.5 text-sm text-muted">了解 OpenVMA 的功能与使用流程</p>
      </header>

      {/* 搜索 */}
      <div className="relative mb-6">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveCategory("all");
          }}
          placeholder="搜索帮助文档…"
          className="w-full rounded-xl border border-line bg-surface py-2.5 pl-9 pr-3 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
        />
      </div>

      {/* 分类导航 */}
      <nav className="mb-6 flex flex-wrap gap-2" aria-label="帮助分类">
        {helpCategories.map((category) => {
          const Icon = helpIcons[category.icon] ?? CircleHelp;
          const active = activeCategory === category.id;
          return (
            <button
              key={category.id}
              onClick={() => {
                setActiveCategory(category.id);
                setQuery("");
                setSelectedArticleId(
                  helpArticles.find((a) => a.category === category.id)?.id ?? helpArticles[0].id,
                );
              }}
              className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm transition ${
                active ? "bg-blue text-white" : "border border-line bg-surface text-muted hover:text-text"
              }`}
              type="button"
            >
              <Icon size={15} />{category.label}
            </button>
          );
        })}
      </nav>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        {/* 文章列表 */}
        <section className="rounded-2xl border border-line bg-surface p-4 shadow-soft">
          <header className="mb-3 flex items-center justify-between border-b border-line pb-2.5">
            <strong className="text-sm text-text">
              {activeCategory === "all"
                ? "搜索结果"
                : helpCategories.find((c) => c.id === activeCategory)?.label}
            </strong>
            <span className="text-xs text-muted">{visibleArticles.length} 篇</span>
          </header>
          <div className="space-y-1.5">
            {visibleArticles.map((article) => {
              const Icon = helpIcons[article.icon] ?? CircleHelp;
              return (
                <button
                  key={article.id}
                  onClick={() => setSelectedArticleId(article.id)}
                  className={`flex w-full items-start gap-2.5 rounded-xl p-3 text-left transition ${
                    selectedArticle?.id === article.id
                      ? "bg-blue-soft/50"
                      : "hover:bg-canvas/60"
                  }`}
                  type="button"
                >
                  <span className="mt-0.5 text-blue"><Icon size={16} /></span>
                  <div className="min-w-0 flex-1">
                    <strong className="block text-sm text-text">{article.title}</strong>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted">{article.summary}</p>
                  </div>
                  <ChevronRight size={14} className="mt-1 shrink-0 text-muted" />
                </button>
              );
            })}
            {visibleArticles.length === 0 && (
              <div className="py-8 text-center">
                <Search size={20} className="mx-auto text-line" />
                <p className="mt-2 text-sm text-muted">没有找到相关文档</p>
              </div>
            )}
          </div>
        </section>

        {/* 文章详情 + FAQ */}
        <div className="space-y-6">
          {selectedArticle ? (
            <article className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
              <header className="border-b border-line pb-3">
                <small className="text-xs text-blue">操作指南</small>
                <h2 className="mt-1 text-lg font-bold text-text">{selectedArticle.title}</h2>
                <p className="mt-1 text-sm text-muted">{selectedArticle.summary}</p>
              </header>
              <ol className="mt-4 space-y-3">
                {selectedArticle.steps.map((step, index) => (
                  <li key={index} className="flex items-start gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-soft text-xs font-semibold text-blue">
                      {index + 1}
                    </span>
                    <p className="pt-0.5 text-sm leading-relaxed text-text">{step}</p>
                  </li>
                ))}
              </ol>
            </article>
          ) : null}

          {/* FAQ */}
          <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
            <header className="mb-3 flex items-center gap-2 border-b border-line pb-2.5">
              <HelpCircle size={16} className="text-blue" />
              <strong className="text-sm text-text">常见问题</strong>
            </header>
            <div className="space-y-2">
              {helpFaqs.map(([question, answer], index) => (
                <div
                  key={question}
                  className={`overflow-hidden rounded-xl border transition ${
                    openFaq === index ? "border-blue/40 bg-blue-soft/20" : "border-line"
                  }`}
                >
                  <button
                    onClick={() => setOpenFaq(openFaq === index ? null : index)}
                    aria-expanded={openFaq === index}
                    className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left"
                    type="button"
                  >
                    <strong className="text-sm text-text">{question}</strong>
                    <ChevronDown
                      size={15}
                      className={`shrink-0 text-muted transition-transform ${openFaq === index ? "rotate-180" : ""}`}
                    />
                  </button>
                  {openFaq === index && (
                    <p className="px-3.5 pb-3 text-sm leading-relaxed text-muted">{answer}</p>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default HelpCenterView;
