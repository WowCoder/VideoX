// ──────────────────────────────────────────────
// OpenVMA - 官网首页
// 顶部导航 + Hero + 四步能力区 + 工作流演示区 + 页脚
// ──────────────────────────────────────────────

import { useState } from "react";
import { useNavigate } from "@/router";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Clapperboard,
  Film,
  Layers3,
  LogIn,
  Play,
  ScanSearch,
  Sparkles,
  Upload,
  WandSparkles,
} from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";

const capabilities = [
  {
    id: "understand",
    icon: ScanSearch,
    number: "01",
    title: "读懂脚本与素材",
    copy: "交付一份脚本和一些素材视频，AI 自动理解台词、人物、物品、空间与镜头质量。",
    detail:
      "系统将脚本拆成可执行的多分镜结构，并同步完成素材转写、画面理解和镜头切分，建立脚本意图与素材语义之间的连接。",
    tags: ["多分镜脚本", "素材理解", "统一视觉设定"],
  },
  {
    id: "match",
    icon: Layers3,
    number: "02",
    title: "自动找好镜头",
    copy: "几分钟内围绕每个分镜搜索、排序并锁定素材中最合适的片段。",
    detail:
      "AI 综合人物、动作、场景、对白、画面质量和上下镜头连续性选择镜头；创作者仍可随时查看候选并替换不合适的片段。",
    tags: ["语义匹配", "候选解释", "一键替换"],
  },
  {
    id: "generate",
    icon: WandSparkles,
    number: "03",
    title: "生成缺失画面",
    copy: "素材里没有合适镜头时，直接生成 AI 分镜图、视频或示意特效画面。",
    detail:
      "AI 生成会引用脚本中锁定的人物、物品、空间、画幅和色彩风格，让补拍镜头与原有素材尽量保持视觉连续。",
    tags: ["AI 生图分镜", "图生视频", "一致性控制"],
  },
  {
    id: "rough-cut",
    icon: Film,
    number: "04",
    title: "拼出可改初剪",
    copy: "自动把选定与生成的镜头装配成一版可继续拖拽、修剪和替换的多轨初剪。",
    detail:
      "创作者只需改几个不合适的镜头、细化节奏或继续处理 AI 素材，即可导出横屏、竖屏、方形成片或剪辑工程。",
    tags: ["多轨时间线", "继续精剪", "多格式导出"],
  },
] as const;

const workflowTasks = [
  { icon: Upload, title: "脚本与素材理解", detail: "1 份脚本 · 128 个视频 · 392 个片段", status: "已完成", progress: 100 },
  { icon: WandSparkles, title: "统一人物与场景设定", detail: "2 个人物 · 3 个物品 · 2 个空间", status: "已完成", progress: 100 },
  { icon: ScanSearch, title: "镜头匹配", detail: "12 个脚本单元 · 48 个候选镜头", status: "处理中", progress: 76 },
  { icon: Sparkles, title: "缺失镜头 AI 补齐", detail: "3 个分镜等待生成画面", status: "排队中", progress: 28 },
  { icon: Clapperboard, title: "多轨初剪装配", detail: "横屏主版 · 竖屏社媒版", status: "等待中", progress: 0 },
] as const;

function BrandMark() {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal">
      <Sparkles size={17} className="text-white" />
    </span>
  );
}

export function SiteHome() {
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuthStore();
  const { openAuth } = useUIStore();
  const [selectedCapability, setSelectedCapability] = useState<string>("match");

  const activeCapability =
    capabilities.find((c) => c.id === selectedCapability) ?? capabilities[1];
  const ActiveIcon = activeCapability.icon;

  function startCreating() {
    if (isAuthenticated) {
      navigate("/workspace");
    } else {
      openAuth("register");
    }
  }

  return (
    <main className="min-h-screen bg-surface">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <button
            className="flex items-center gap-2.5"
            onClick={() => navigate("/")}
            type="button"
          >
            <BrandMark />
            <span className="text-lg font-semibold tracking-wide text-text">OpenVMA</span>
          </button>
          <nav className="hidden items-center gap-8 text-sm text-muted md:flex">
            <a href="#capabilities" className="transition hover:text-text">产品能力</a>
            <a href="#workflow" className="transition hover:text-text">工作流程</a>
            <a href="#help" className="transition hover:text-text">帮助中心</a>
          </nav>
          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <button
                onClick={() => navigate("/workspace")}
                className="flex items-center gap-2 rounded-lg bg-blue px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-2"
                type="button"
              >
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/20 text-xs">
                  {user?.initial || "U"}
                </span>
                进入工作区
              </button>
            ) : (
              <>
                <button
                  onClick={() => openAuth("login")}
                  className="flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium text-muted transition hover:bg-canvas hover:text-text"
                  type="button"
                >
                  <LogIn size={15} />登录
                </button>
                <button
                  onClick={() => openAuth("register")}
                  className="rounded-lg bg-blue px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-2"
                  type="button"
                >
                  免费注册
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero 区 */}
      <section className="relative overflow-hidden bg-gradient-to-b from-canvas to-surface px-6 py-20 lg:py-28">
        <div className="absolute -top-20 left-1/2 h-72 w-[42rem] -translate-x-1/2 rounded-full bg-blue/10 blur-3xl" />
        <div className="relative mx-auto max-w-4xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-blue/20 bg-blue-soft/60 px-3 py-1 text-xs font-medium text-blue">
            <Sparkles size={13} />AI 视频剪辑工作流 · 从脚本到初剪
          </span>
          <h1 className="mt-6 text-3xl font-bold leading-tight text-text lg:text-5xl lg:leading-tight">
            把脚本和素材交给 AI，<br />
            几分钟得到一版<span className="bg-gradient-to-r from-blue to-teal bg-clip-text text-transparent">可改的初剪</span>。
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted lg:text-lg">
            OpenVMA 自动理解脚本与素材、找好合适镜头；缺失画面可生成 AI 素材，并装配成一版能继续替换镜头、细化剪辑和多格式导出的初剪。
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={startCreating}
              className="flex items-center gap-2 rounded-xl bg-blue px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-blue-2"
              type="button"
            >
              {isAuthenticated ? "进入工作区" : "立即体验"}<ArrowRight size={16} />
            </button>
            <a
              href="#capabilities"
              className="flex items-center gap-2 rounded-xl border border-line bg-surface px-6 py-3 text-sm font-medium text-text transition hover:bg-canvas"
            >
              <Play size={15} />了解工作流
            </a>
          </div>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted">
            <span className="flex items-center gap-1"><Check size={13} className="text-teal" />无需安装，浏览器直接使用</span>
            <span className="flex items-center gap-1"><Check size={13} className="text-teal" />Free 方案永久免费</span>
            <span className="flex items-center gap-1"><Check size={13} className="text-teal" />支持横屏 / 竖屏 / 方形</span>
          </div>
        </div>
      </section>

      {/* 四步能力区 */}
      <section id="capabilities" className="bg-surface px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 text-center">
            <h2 className="text-2xl font-bold text-text lg:text-3xl">从一份脚本，直接走到可编辑初剪</h2>
            <p className="mx-auto mt-3 max-w-2xl text-muted">
              同一份脚本连接素材理解、镜头选择、AI 画面生成与时间线，创作者只处理真正需要判断的部分。
            </p>
          </div>

          {/* 能力卡片 */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {capabilities.map((item) => {
              const Icon = item.icon;
              const isActive = item.id === selectedCapability;
              return (
                <button
                  key={item.id}
                  onClick={() => setSelectedCapability(item.id)}
                  className={`group rounded-2xl border p-5 text-left transition ${
                    isActive
                      ? "border-blue bg-blue-soft/40 shadow-soft"
                      : "border-line bg-surface hover:border-blue/40 hover:shadow-soft"
                  }`}
                  type="button"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`flex h-11 w-11 items-center justify-center rounded-xl transition ${
                        isActive ? "bg-blue text-white" : "bg-canvas text-blue"
                      }`}
                    >
                      <Icon size={20} />
                    </span>
                    <span className="text-xs font-semibold text-muted">{item.number}</span>
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-text">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">{item.copy}</p>
                </button>
              );
            })}
          </div>

          {/* 能力详情 */}
          <div className="mt-8 grid gap-6 rounded-2xl border border-line bg-canvas/40 p-6 lg:grid-cols-[1.2fr_1fr] lg:p-8">
            <div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue text-white">
                  <ActiveIcon size={20} />
                </span>
                <span className="text-xs font-semibold text-muted">
                  {activeCapability.number} / 04
                </span>
              </div>
              <h3 className="mt-4 text-xl font-bold text-text">{activeCapability.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{activeCapability.detail}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {activeCapability.tags.map((tag) => (
                  <span
                    key={tag}
                    className="flex items-center gap-1 rounded-full bg-surface px-3 py-1 text-xs text-text shadow-sm"
                  >
                    <Check size={12} className="text-teal" />{tag}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-xl bg-gradient-to-br from-ink to-ink-2 p-5 text-white">
              <div className="flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-sm">
                <Sparkles size={15} className="text-teal" />
                <span className="flex-1">
                  {activeCapability.id === "understand"
                    ? "上传：发布会脚本.xlsx + 现场素材文件夹"
                    : activeCapability.id === "match"
                      ? "为「产品首次亮相」自动找到最有冲击力的镜头"
                      : activeCapability.id === "generate"
                        ? "按统一机器人和舞台设定生成缺失近景"
                        : "将第 4 个片段替换，并导出 16:9 与 9:16 两个版本"}
                </span>
                <ArrowRight size={14} className="text-white/40" />
              </div>
              <div className="mt-4 space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2">
                    <span className="h-6 w-10 rounded bg-white/10" />
                    <div className="flex-1">
                      <span className="block h-2 w-3/4 rounded bg-white/20" />
                      <span className="mt-1 block h-2 w-1/2 rounded bg-white/10" />
                    </div>
                    <Check size={14} className="text-teal" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 工作流演示区 */}
      <section id="workflow" className="bg-canvas px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-12 text-center">
            <h2 className="text-2xl font-bold text-text lg:text-3xl">处理状态，回到每一份内容上</h2>
            <p className="mx-auto mt-3 max-w-2xl text-muted">
              脚本解析、镜头匹配、AI 素材生成和初剪装配都持续同步到对应脚本与项目，离开页面也能继续处理。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {workflowTasks.map((task, idx) => {
              const Icon = task.icon;
              return (
                <div
                  key={task.title}
                  className="rounded-2xl border border-line bg-surface p-5 shadow-soft transition hover:-translate-y-0.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-soft text-blue">
                      <Icon size={18} />
                    </span>
                    <span className="text-xs font-semibold text-muted">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-text">{task.title}</h3>
                  <p className="mt-1 text-xs text-muted">{task.detail}</p>
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted">{task.status}</span>
                      <span className="font-medium text-text">{task.progress}%</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-canvas">
                      <div
                        className={`h-full rounded-full transition-all ${
                          task.progress === 100
                            ? "bg-teal"
                            : task.progress > 0
                              ? "bg-gradient-to-r from-blue to-teal"
                              : "bg-line"
                        }`}
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-10 text-center">
            <button
              onClick={startCreating}
              className="inline-flex items-center gap-2 rounded-xl bg-blue px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-blue-2"
              type="button"
            >
              {isAuthenticated ? "返回工作区" : "免费开始创作"}<ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>

      {/* 页脚 */}
      <footer id="help" className="border-t border-line bg-surface px-6 py-12">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-8 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <BrandMark />
                <span className="text-lg font-semibold text-text">OpenVMA</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                从脚本和素材到可编辑初剪的 AI 视频工作流。
              </p>
            </div>
            <div>
              <strong className="block text-sm font-semibold text-text">产品</strong>
              <ul className="mt-3 space-y-2 text-sm text-muted">
                <li><a href="#capabilities" className="transition hover:text-text">产品能力</a></li>
                <li><a href="#workflow" className="transition hover:text-text">工作流程</a></li>
                <li><a href="#capabilities" className="transition hover:text-text">会员方案</a></li>
              </ul>
            </div>
            <div>
              <strong className="block text-sm font-semibold text-text">支持</strong>
              <ul className="mt-3 space-y-2 text-sm text-muted">
                <li><button onClick={() => navigate("/workspace/help")} className="transition hover:text-text" type="button">帮助中心</button></li>
                <li><a href="#capabilities" className="transition hover:text-text">快速开始</a></li>
                <li><a href="#capabilities" className="transition hover:text-text">账号与用量</a></li>
              </ul>
            </div>
            <div>
              <strong className="block text-sm font-semibold text-text">关于</strong>
              <ul className="mt-3 space-y-2 text-sm text-muted">
                <li><a href="#" className="transition hover:text-text">关于 OpenVMA</a></li>
                <li><a href="#" className="transition hover:text-text">隐私政策</a></li>
                <li><a href="#" className="transition hover:text-text">服务条款</a></li>
              </ul>
            </div>
          </div>
          <div className="mt-10 flex items-center justify-between border-t border-line pt-6">
            <small className="text-xs text-muted">© 2026 OpenVMA. 保留所有权利。</small>
            <button
              onClick={() => navigate("/workspace/help")}
              className="flex items-center gap-1 text-xs text-blue transition hover:underline"
              type="button"
            >
              查看帮助中心<ChevronRight size={13} />
            </button>
          </div>
        </div>
      </footer>
    </main>
  );
}

export default SiteHome;
