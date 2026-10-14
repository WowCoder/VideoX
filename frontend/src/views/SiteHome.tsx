import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Clapperboard,
  FileText,
  Film,
  Github,
  LogIn,
  Menu,
  Play,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import type { User } from "@/types/models";
import {
  helpCenterCopy,
  helpFaqs,
  membershipPlanFeatures,
  membershipPlans,
  type MembershipPlan,
} from "./siteContent";
import {
  FEATURED_SHOWCASE_WORKS,
  STARTING_POINTS,
  type ShowcaseWork,
  type StartingPoint,
} from "./siteContent";
import "./SiteHome.css";

type AuthMode = "login" | "register";
type StartMethod = StartingPoint["method"];

interface SiteHomeProps {
  variant?: "application" | "open-source";
  isAuthenticated: boolean;
  membership?: { name?: string } | null;
  user?: User | null;
  onOpenAuth: (mode: AuthMode) => void;
  onEnterWorkspace: (view?: string, detail?: string) => void;
  onGoToSite: () => void;
  onStartPath: (method: StartMethod) => void;
}

const AGENT_STEPS = [
  {
    index: "01",
    label: "AI CONTENT PLANNER",
    title: "内容策划",
    description: "根据你的主题、受众和平台，补齐选题角度、开场钩子与内容结构。",
    output: "交付：可修改的内容大纲",
    icon: Sparkles,
  },
  {
    index: "02",
    label: "AI FILM DIRECTOR",
    title: "影片导演",
    description: "把文章拆成场景和镜头，说明每一句话应该出现什么画面、景别和节奏。",
    output: "交付：脚本、分镜与视觉方向",
    icon: Clapperboard,
  },
  {
    index: "03",
    label: "AI VIDEO EDITOR",
    title: "自动剪辑",
    description: "匹配或生成画面，自动组织旁白、字幕、转场、音效和背景音乐。",
    output: "交付：可继续微调的第一版影片",
    icon: Film,
  },
  {
    index: "04",
    label: "REAL-TIME DELIVERY",
    title: "预览成片",
    description: "你像修改文档一样调整内容，整支影片随脚本实时更新，满意后直接导出。",
    output: "交付：适配发布平台的成片",
    icon: Play,
  },
];

const SIMPLE_PROMISES = [
  ["不用学时间线", "镜头顺序跟着文档结构走，调整段落就能调整影片。"],
  ["不用会写分镜", "AI 导演给出镜头建议，你只需要判断是否符合表达。"],
  ["不用找全素材", "已有素材可以上传，缺少的图片、视频和声音可以直接生成。"],
  ["不会覆盖原文件", "AI 处理先成为候选版本，确认后才会进入当前影片。"],
];

const REPOSITORY = "https://github.com/WowCoder/OpenVMA";
const DOCUMENTATION = `${REPOSITORY}/blob/main/docs`;
const GETTING_STARTED = `${DOCUMENTATION}/getting-started.md`;
const IMAGE_SOURCES = {
  nasa: "https://science.nasa.gov/photojournal/nasas-asteroid-redirect-robotic-mission-artist-concept/",
  moon: "https://www.nasa.gov/image-article/crescent-moon-rising-earths-atmosphere/",
  alpine: "https://commons.wikimedia.org/wiki/File:Milky_Way_Galaxy_and_Kandersteg_viewed_from_the_Bl%C3%BCmlisalph%C3%BCtte_at_night.jpg",
};

const OPEN_SOURCE_STEPS = [
  { ...AGENT_STEPS[0], description: "结合检索来源探索选题，整理内容方向与结构。AI 服务按需配置，提案由你审阅。", output: "交付：带来源的灵感提案" },
  { ...AGENT_STEPS[1], title: "脚本与分镜", description: "手动编写场景、台词和镜头，也可以接入 AI 生成可修改的脚本草稿。", output: "交付：可编辑的脚本与分镜" },
  { ...AGENT_STEPS[2], label: "HUMAN-IN-THE-LOOP", title: "镜头素材", description: "上传自己的媒体，或接入生成服务获取候选画面，继续审阅和选择镜头素材。", output: "交付：已确认的镜头素材" },
  { ...AGENT_STEPS[3], label: "COMPOSITION & EXPORT", title: "编排与导出", description: "组织画面、旁白和字幕，检查主成片编排，再通过 FFmpeg 后台任务导出视频。", output: "交付：可下载的视频文件" },
];

const OPEN_SOURCE_PROMISES = [
  ["文档组织镜头", "脚本、分镜与素材各有明确的位置，创作过程可以逐步查看和修改。"],
  ["AI 提供候选", "策划、检索与生成按需接入，结果保留在项目中供继续审阅。"],
  ["创作者确认素材", "你可以手动选择镜头画面；异步生成结果会检查镜头修订版本。"],
  ["编排驱动导出", "镜头、旁白与字幕汇入编排文档，后台任务按时间线输出视频。"],
];

const OPEN_SOURCE_FAQS: Array<[string, string]> = [
  ["这是在线创作工具，还是项目展示页？", "这里介绍 OpenVMA 的创作流程。完整工作区需要自行部署，快速开始文档提供本地启动步骤。"],
  ["没有 AI 服务也能开始吗？", "可以。默认配置关闭 AI 供应商；你仍可上传媒体、手动编辑脚本与分镜、选择素材并导出视频。"],
  ["需要准备什么环境？", "本地快速开始使用 Docker Engine 或 Docker Desktop，以及 Docker Compose。模型与生成服务可以在基础流程跑通后按需接入。"],
  ["页面里的画面是真实生成结果吗？", "太空画面沿用官网原有的任务概念图与摄影参考，并非 OpenVMA 生成的成片。工作台是界面示意，播放按钮展示示意动画。"],
  ["可以参与开发或复用代码吗？", "可以。项目代码采用 MIT 许可，仓库提供贡献指南和架构文档。模型、外部服务与第三方素材遵循各自的许可。"],
];

function SiteAction({ href, onClick, className, children }: {
  href?: string;
  onClick?: () => void;
  className?: string;
  children: ReactNode;
}) {
  return href
    ? <a href={href} className={className}>{children}</a>
    : <button onClick={onClick} className={className} type="button">{children}</button>;
}

const START_ICON_BY_ID = {
  concept: Sparkles,
  script: FileText,
  assets: Upload,
};

function ShowcaseMedia({ work, eager = false, className = "" }: { work: ShowcaseWork; eager?: boolean; className?: string }) {
  const imageSource = work.mediaType === "video" ? work.poster : work.src;
  return (
    <img
      className={className}
      src={imageSource}
      alt=""
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      fetchPriority={eager ? "high" : "low"}
    />
  );
}

function SiteBrand({ decorative = false }: { decorative?: boolean } = {}) {
  return <BrandLogo variant="wordmark" tone="dark" height={16} className="ltx-site-brand" decorative={decorative} />;
}

function AccountArea({
  isAuthenticated,
  membership,
  user,
  onOpenAuth,
  onEnterWorkspace,
}: Pick<SiteHomeProps, "isAuthenticated" | "membership" | "user" | "onOpenAuth" | "onEnterWorkspace">) {
  if (isAuthenticated) {
    return (
      <button className="ltx-site-account" onClick={() => onEnterWorkspace("projects")} type="button">
        <span>{user?.initial || "U"}</span>
        <div><strong>{user?.name || "OpenVMA 用户"}</strong><small>{membership?.name || "Free"} · 进入项目中心</small></div>
        <ArrowRight size={14} />
      </button>
    );
  }
  return (
    <div className="ltx-site-auth-actions">
      <button className="ltx-site-login" onClick={() => onOpenAuth?.("login")} type="button">
        <LogIn size={15} aria-hidden="true" />
        登录
      </button>
      <button className="ltx-site-button is-compact is-dark" onClick={() => onOpenAuth?.("register")} type="button">
        免费注册
      </button>
    </div>
  );
}

function ComposerPreview({ work, isOpenSource = false }: { work: ShowcaseWork; isOpenSource?: boolean }) {
  const [playing, setPlaying] = useState(false);
  const previewTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (previewTimer.current) window.clearTimeout(previewTimer.current);
  }, []);

  function togglePreview() {
    if (previewTimer.current) {
      window.clearTimeout(previewTimer.current);
      previewTimer.current = null;
    }
    setPlaying((current) => {
      const next = !current;
      if (next) {
        previewTimer.current = window.setTimeout(() => {
          setPlaying(false);
          previewTimer.current = null;
        }, 5800);
      }
      return next;
    });
  }

  return (
    <div className={`ltx-composer-frame ${playing ? "is-playing" : ""}`} aria-label="OpenVMA 文档式脚本编排工作台示意">
      <header className="ltx-composer-topbar">
        <div><i /><strong>轨道档案：寻找第二个家园</strong></div>
        <span>{isOpenSource ? "界面示意 · 静态参考" : "已自动保存"}</span>
        <em>{isOpenSource ? "编排与导出" : "导出影片"}</em>
      </header>

      <div className="ltx-composer-body">
        <aside className="ltx-composer-scenes">
          <small>影片结构</small>
          {[
            ["01", "为什么要离开", "已完成"],
            ["02", "进入未知轨道", "正在编辑"],
            ["03", "看见第二个家园", "待确认"],
          ].map(([number, title, status], index) => (
            <div className={index === 1 ? "is-active" : ""} key={number}>
              <span>{number}</span>
              <p><strong>{title}</strong><small>{status}</small></p>
            </div>
          ))}
        </aside>

        <section className="ltx-composer-document">
          <header><small>SCENE 02 · 12 秒</small><strong>进入未知轨道</strong></header>
          <div className="ltx-composer-paragraph">
            <span>旁白</span>
            <p>当第一束信号穿过黑暗，我们第一次看见它真正的轮廓。</p>
          </div>
          <article className="is-selected">
            <span>镜头 01</span>
            <div><strong>探测器沿地表缓慢推进</strong><p>极远景，低角度。远处的微弱信号形成一条清晰光带。</p></div>
            <em><Check size={12} />画面已匹配</em>
          </article>
          <article>
            <span>镜头 02</span>
            <div><strong>信号进入控制舱</strong><p>屏幕波形亮起，人物面部被冷色光线逐渐照亮。</p></div>
            <em className="is-pending"><Sparkles size={12} />生成 3 个候选</em>
          </article>
        </section>

        <aside className="ltx-composer-preview">
          <header><div><i /><span><strong>{isOpenSource ? "预览示意" : "成片预览"}</strong><small>{isOpenSource ? "静态画面 · 示意动画" : "随文档实时更新"}</small></span></div><em>16:9</em></header>
          <figure>
            <ShowcaseMedia work={work} />
            <button aria-label={isOpenSource ? (playing ? "暂停界面示意动画" : "播放界面示意动画") : (playing ? "暂停成片示意" : "播放成片示意")} aria-pressed={playing} onClick={togglePreview} type="button">
              {playing ? <span className="ltx-preview-pause" aria-hidden="true"><i /><i /></span> : <Play size={17} fill="currentColor" />}
            </button>
            <figcaption>当第一束信号穿过黑暗，<br />我们第一次看见它真正的轮廓。</figcaption>
          </figure>
          <div className="ltx-composer-controls"><span>{playing ? "00:36" : "00:18"}</span><i><b /></i><span>00:58</span></div>
          <div className="ltx-composer-tools">
            <span>画面</span><span>旁白</span><span>字幕</span><span>音乐</span><span>转场</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

function SiteHelp({
  isAuthenticated,
  onOpenAuth,
  onEnterWorkspace,
  isOpenSource = false,
}: Pick<SiteHomeProps, "isAuthenticated" | "onOpenAuth" | "onEnterWorkspace"> & { isOpenSource?: boolean }) {
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  function openHelp() {
    if (isAuthenticated) onEnterWorkspace?.("help");
    else onOpenAuth?.("login");
  }

  return (
    <section className="ltx-site-help ltx-site-section" id="site-help" aria-labelledby="ltx-help-title">
      <div className="ltx-section-heading is-split">
        <div><span>QUESTIONS</span><h2 id="ltx-help-title">第一次做视频，<br />可以从这里开始。</h2></div>
        <p>{isOpenSource ? "从本地启动到接入 AI，先了解你需要准备什么，再开始第一支影片。" : helpCenterCopy.description}</p>
      </div>
      <div className="ltx-help-layout">
        <div className="ltx-help-intro">
          <strong>不用先学会剪辑软件。</strong>
          <p>{isOpenSource ? "先上传自己的素材，试着编写脚本与分镜，再完成编排和导出。熟悉基础流程后，按需接入 AI 服务。" : "创建项目后，先把主题或文章交给 AI。每一个策划、分镜和剪辑结果都可以继续修改。"}</p>
          <SiteAction href={isOpenSource ? GETTING_STARTED : undefined} onClick={openHelp}>{isOpenSource ? "阅读快速开始" : "打开完整帮助中心"}<ArrowRight size={15} /></SiteAction>
        </div>
        <div className="ltx-help-faq">
          {(isOpenSource ? OPEN_SOURCE_FAQS : helpFaqs).slice(0, 5).map(([question, answer], index) => (
            <article className={openFaq === index ? "is-open" : ""} key={question}>
              <button onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index} type="button">
                <strong>{question}</strong><ChevronDown size={17} />
              </button>
              {openFaq === index ? <p>{answer}</p> : null}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function OpenSourceDetails() {
  const cards = [
    { label: "MIT LICENSE", title: "开放源码", description: "查看、修改和分发项目代码，按自己的想法继续构建。", link: `${REPOSITORY}/blob/main/LICENSE`, action: "查看 MIT 许可", notes: ["代码采用 MIT 许可", "欢迎提交 Issue 与 Pull Request", "模型与素材遵循各自的许可"] },
    { label: "SELF-HOSTED", title: "自行部署", description: "用 Docker Compose 启动本地工作区，从自己的素材开始创作。", link: GETTING_STARTED, action: "阅读快速开始", notes: ["基础服务通过 Compose 启动", "支持人工编辑与媒体导出", "项目与媒体由自己管理"] },
    { label: "OPTIONAL AI", title: "AI 按需接入", description: "基础流程跑通后，再接入适合你的模型与媒体生成服务。", link: `${DOCUMENTATION}/configuration.md`, action: "查看配置指南", notes: ["默认关闭 AI 供应商", "策划、检索与生成按需配置", "服务费用按供应商规则计算"] },
  ];

  return (
    <section className="ltx-pricing ltx-site-section ltx-open-source" id="site-open-source" aria-labelledby="ltx-open-source-title">
      <div className="ltx-section-heading is-split">
        <div><span>OPEN SOURCE, YOUR WORKSPACE</span><h2 id="ltx-open-source-title">从源码开始，<br />按你的方式创作。</h2></div>
        <p>读懂工作流，运行自己的工作区，<br />再把需要的 AI 能力接进来。</p>
      </div>
      <div className="ltx-pricing-grid">
        {cards.map((card, index) => (
          <article className={index === 1 ? "is-featured" : ""} key={card.label}>
            <header><span>{card.label}</span>{index === 1 ? <em>从这里开始</em> : null}</header>
            <h3>{card.title}</h3><p>{card.description}</p>
            <a href={card.link}>{card.action}<ArrowRight size={14} /></a>
            <ul>{card.notes.map((note) => <li key={note}><Check size={13} />{note}</li>)}</ul>
          </article>
        ))}
      </div>
    </section>
  );
}

export function SiteHome({
  variant = "application",
  isAuthenticated,
  membership,
  user,
  onOpenAuth,
  onEnterWorkspace,
  onGoToSite,
  onStartPath,
}: SiteHomeProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [billingCycle, setBillingCycle] = useState("annual");
  const isOpenSource = variant === "open-source";
  const heroWork = FEATURED_SHOWCASE_WORKS.find((work) => work.id === "orbital-archive")
    ?? FEATURED_SHOWCASE_WORKS[0];
  const previewWork = FEATURED_SHOWCASE_WORKS.find((work) => work.id === "moonset-orbit")
    ?? FEATURED_SHOWCASE_WORKS[0];
  const spaceCases = ["orbital-archive", "milky-way-kandersteg"]
    .map((id) => FEATURED_SHOWCASE_WORKS.find((work) => work.id === id))
    .filter((work): work is ShowcaseWork => Boolean(work));

  useEffect(() => {
    if (!window.location.hash) return;
    let id: string;
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch {
      id = window.location.hash.slice(1);
    }
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function startPath(startMethod: StartMethod) {
    setMobileNavOpen(false);
    if (onStartPath) {
      onStartPath(startMethod);
      return;
    }
    if (!isAuthenticated) {
      onOpenAuth?.("register");
      return;
    }
    if (startMethod === "upload-assets") onEnterWorkspace?.("library");
    else onEnterWorkspace?.("script", "new");
  }

  function openPlan(planId: MembershipPlan["id"]) {
    if (isAuthenticated) onEnterWorkspace?.("account", "membership");
    else onOpenAuth?.(planId === "free" ? "register" : "login");
  }

  function closeMobileNav() {
    setMobileNavOpen(false);
  }

  function goToSiteTop() {
    closeMobileNav();
    onGoToSite();
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    });
  }

  return (
    <main className="ltx-site">
      <a className="ltx-site-announcement" href={isOpenSource ? REPOSITORY : "#site-capabilities"}>
        <span>{isOpenSource ? "OpenVMA · MIT 开源 · 在 GitHub 探索项目" : "OpenVMA 为第一次做视频的人而设计"}</span><ArrowRight size={16} />
      </a>

      <header className={`ltx-site-header ${mobileNavOpen ? "is-menu-open" : ""}`}>
        <button className="ltx-site-logo-button" onClick={goToSiteTop} aria-label="返回 OpenVMA 官网顶部" type="button">
          <SiteBrand decorative />
        </button>

        <nav className="ltx-site-nav" id="ltx-site-navigation" aria-label="官网导航">
          <a href="#site-capabilities" onClick={closeMobileNav}>如何工作</a>
          <a href="#site-workflow" onClick={closeMobileNav}>产品体验</a>
          <a href="#site-showcase" onClick={closeMobileNav}>{isOpenSource ? "视觉参考" : "太空案例"}</a>
          <a href="#site-start" onClick={closeMobileNav}>开始方式</a>
          <a href={isOpenSource ? "#site-open-source" : "#site-pricing"} onClick={closeMobileNav}>{isOpenSource ? "开源部署" : "价格"}</a>
          <a href="#site-help" onClick={closeMobileNav}>帮助</a>
        </nav>

        <div className="ltx-site-header-end">
          {isOpenSource ? <div className="ltx-site-auth-actions">
            <a className="ltx-site-login" href={GETTING_STARTED}>快速开始</a>
            <a className="ltx-site-button is-compact is-dark" href={REPOSITORY}><Github size={15} aria-hidden="true" />GitHub</a>
          </div> : <AccountArea
            isAuthenticated={isAuthenticated}
            membership={membership}
            user={user}
            onOpenAuth={onOpenAuth}
            onEnterWorkspace={onEnterWorkspace}
          />}
          <button
            className="ltx-site-menu-button"
            onClick={() => setMobileNavOpen((open) => !open)}
            aria-expanded={mobileNavOpen}
            aria-controls="ltx-site-navigation"
            aria-label={mobileNavOpen ? "关闭官网导航" : "打开官网导航"}
            type="button"
          >{mobileNavOpen ? <X size={19} /> : <Menu size={19} />}</button>
        </div>
      </header>

      <section className="ltx-hero" aria-labelledby="ltx-hero-title">
        <div className="ltx-hero-content">
          <span className="ltx-kicker">{isOpenSource ? "开源视频创作 · AI 策划 · 文档编排" : "AI 策划 · AI 导演 · AI 剪辑"}</span>
          <h1 id="ltx-hero-title">只会写文档，<br />也能完成一支影片。</h1>
          <p>{isOpenSource ? "把想法写成脚本，把素材组织成影片。OpenVMA 连接 AI 策划、分镜编辑和视频导出，让每一步都可以查看和修改。" : "你负责写下观点。OpenVMA 负责选题策划、影片导演和自动剪辑，把文章变成可以直接发布的视频。"}</p>
          <div className="ltx-hero-actions">
            <SiteAction href={isOpenSource ? GETTING_STARTED : undefined} className="ltx-site-button is-dark" onClick={() => startPath("ai-script")}>{isOpenSource ? "本地开始创作" : "写下第一个选题"}<ArrowRight size={17} /></SiteAction>
            <a className="ltx-site-button is-outline" href="#site-workflow">看看如何工作<Play size={15} /></a>
          </div>
          <small><Check size={14} />{isOpenSource ? "MIT 开源 · 支持本地部署 · AI 服务按需接入" : "不需要会分镜、不需要会剪辑，也不需要先准备好全部素材。"}</small>
        </div>

        <figure className="ltx-hero-visual">
          <div><ShowcaseMedia work={heroWork} eager /></div>
          <figcaption><span>{isOpenSource ? "SPACE STORY / 太空视觉参考" : "SPACE STORY / 电影级太空视觉参考"}</span><strong>{heroWork.title}</strong><small>{isOpenSource ? "任务概念图用于建立视觉方向，非 OpenVMA 生成结果。故事仍然从你的文字开始。" : "真实影像只负责建立方向，故事仍然从你的文字开始。"}</small></figcaption>
        </figure>

        <div className="ltx-hero-proof" aria-label="OpenVMA 创作前提">
          <span><strong>01</strong>给一个主题</span>
          <span><strong>02</strong>粘贴一篇文章</span>
          <span><strong>03</strong>{isOpenSource ? "确认素材，编排并导出" : "像改文档一样确认成片"}</span>
        </div>
      </section>

      <section className="ltx-agent-flow ltx-site-section" id="site-capabilities" aria-labelledby="ltx-capabilities-title">
        <div className="ltx-section-heading is-split">
          <div><span>{isOpenSource ? "ONE WORKFLOW, FOUR STAGES" : "ONE AGENT, FOUR JOBS"}</span><h2 id="ltx-capabilities-title">{isOpenSource ? <>从一个想法，<br />走到完整创作流程。</> : <>不是复杂的剪辑工具。<br />是替你完成制作的 Agent。</>}</h2></div>
          <p>{isOpenSource ? "在同一个工作区组织策划、脚本、素材和编排。AI 提供帮助，创作者保留审阅与修改的空间。" : "你不用在策划、脚本、素材库和剪辑软件之间来回切换。四个制作环节围绕同一份文档连续完成。"}</p>
        </div>

        <div className="ltx-agent-grid">
          {(isOpenSource ? OPEN_SOURCE_STEPS : AGENT_STEPS).map((step) => {
            const Icon = step.icon;
            return (
              <article key={step.index}>
                <header><span>{step.index}</span><Icon size={19} /></header>
                <small>{step.label}</small>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
                <footer>{step.output}</footer>
              </article>
            );
          })}
        </div>
      </section>

      <section className="ltx-workflow" id="site-workflow" aria-labelledby="ltx-workflow-title">
        <div className="ltx-workflow-inner">
          <div className="ltx-workflow-heading">
            <div><span>DOCUMENT FIRST</span><h2 id="ltx-workflow-title">会写，<br />就会做视频。</h2></div>
            <div><p>{isOpenSource ? "脚本、分镜与素材都有可修改的中间结果。确认镜头素材，检查主成片编排，再导出视频。" : "脚本就是影片的控制台。修改段落、旁白或镜头说明，画面、声音和预览会跟着更新。"}</p><SiteAction href={isOpenSource ? `${DOCUMENTATION}/architecture.md` : undefined} className="ltx-site-button is-dark" onClick={() => startPath("write-script")}>{isOpenSource ? "了解创作流程" : "用一篇文档开始"}<ArrowRight size={16} /></SiteAction></div>
          </div>

          <ComposerPreview work={previewWork} isOpenSource={isOpenSource} />
          {isOpenSource ? <p className="ltx-demo-caption">工作台界面示意 · 使用摄影参考，播放展示示意动画。</p> : null}

          <div className="ltx-workflow-notes">
            {(isOpenSource ? OPEN_SOURCE_PROMISES : SIMPLE_PROMISES).map(([title, description], index) => (
              <article key={title}><span>0{index + 1}</span><div><strong>{title}</strong><p>{description}</p></div></article>
            ))}
          </div>
        </div>
      </section>

      <section className="ltx-showcase ltx-site-section" id="site-showcase" aria-labelledby="ltx-showcase-title">
        <div className="ltx-section-heading is-split">
          <div><span>SPACE REFERENCES</span><h2 id="ltx-showcase-title">先看见方向，<br />再让故事发生。</h2></div>
          <p>{isOpenSource ? "用构图和情绪表达视觉方向，再为镜头选择合适的素材。以下沿用官网的概念图与摄影参考，展示的是静态画面。" : "太空题材适合解释尺度、未知和未来。OpenVMA 会从镜头参考中提取构图与情绪，而不是堆叠无关图片。"}</p>
        </div>

        <div className="ltx-showcase-grid">
          {spaceCases.map((work, index) => (
            <article key={work.id}>
              <figure><ShowcaseMedia work={work} /></figure>
              <div><span>0{index + 1} / {work.eyebrow}</span><h3>{work.title}</h3><p>{work.description}</p><SiteAction href={isOpenSource ? GETTING_STARTED : undefined} onClick={() => startPath("ai-script")}>{isOpenSource ? "了解如何开始" : "用这个方向创作"}<ArrowRight size={15} /></SiteAction></div>
            </article>
          ))}
        </div>
      </section>

      <section className="ltx-start ltx-site-section" id="site-start" aria-labelledby="ltx-start-title">
        <div className="ltx-section-heading is-split">
          <div><span>START WITH WHAT YOU HAVE</span><h2 id="ltx-start-title">你有什么，<br />就从什么开始。</h2></div>
          <p>{isOpenSource ? "从想法、脚本或自己的素材进入工作区，逐步整理成可修改的脚本、分镜与主成片编排。" : "没有脚本也没关系。没有素材也没关系。所有入口最后都会回到一份可修改的影片文档。"}</p>
        </div>
        <div className="ltx-start-grid">
          {STARTING_POINTS.slice(0, 3).map((point) => {
            const Icon = START_ICON_BY_ID[point.id] ?? Sparkles;
            return (
              <SiteAction href={isOpenSource ? GETTING_STARTED : undefined} onClick={() => startPath(point.method)} key={point.id}>
                <header><span>{point.index}</span><Icon size={19} /></header>
                <small>{point.label}</small><strong>{point.title}</strong><p>{isOpenSource ? ({ concept: "写下题材、观众和表达方向，配置 AI 服务后生成可修改的脚本草稿。", script: "手动整理已有文章、旁白或脚本，继续编写场景与镜头。", assets: "上传自己的图片、视频和声音，为镜头选择素材并组织主成片。" }[point.id]) : point.description}</p>
                <footer>{isOpenSource ? "查看开始指南" : "以此开始"}<ArrowRight size={15} /></footer>
              </SiteAction>
            );
          })}
        </div>
      </section>

      {isOpenSource ? <OpenSourceDetails /> : <section className="ltx-pricing ltx-site-section" id="site-pricing" aria-labelledby="ltx-pricing-title">
        <div className="ltx-section-heading is-split">
          <div><span>PLANS</span><h2 id="ltx-pricing-title">先完成第一支，<br />再决定做多少。</h2></div>
          <div className="ltx-pricing-heading-end">
            <p>从免费体验开始。需要更多生成额度、更高画质或团队空间时再升级。</p>
            <div className="ltx-billing-toggle" role="group" aria-label="会员付费周期">
              <button className={billingCycle === "monthly" ? "is-active" : ""} onClick={() => setBillingCycle("monthly")} type="button">月付</button>
              <button className={billingCycle === "annual" ? "is-active" : ""} onClick={() => setBillingCycle("annual")} type="button">年付 <span>年付优惠</span></button>
            </div>
          </div>
        </div>
        <div className="ltx-pricing-grid">
          {membershipPlans.map((plan) => {
            const price = billingCycle === "annual" ? plan.annualMonthlyPrice : plan.monthlyPrice;
            return (
              <article className={plan.recommended ? "is-featured" : ""} key={plan.id}>
                <header><span>{plan.id.toUpperCase()}</span>{plan.recommended ? <em>推荐</em> : null}</header>
                <h3>{plan.name}</h3><p>{plan.description}</p>
                <div className="ltx-plan-price"><strong>¥{price}</strong><span>/ 月</span></div>
                <small>{plan.id === "free" ? "永久免费" : billingCycle === "annual" ? `按年支付 ¥${plan.annualTotal}` : "按月支付，可随时取消"}</small>
                <button onClick={() => openPlan(plan.id)} type="button">{plan.id === "free" ? "免费开始" : "选择此方案"}<ArrowRight size={14} /></button>
                <ul>{membershipPlanFeatures(plan).map((feature) => <li key={feature}><Check size={13} />{feature}</li>)}</ul>
              </article>
            );
          })}
        </div>
      </section>}

      <SiteHelp isAuthenticated={isAuthenticated} onOpenAuth={onOpenAuth} onEnterWorkspace={onEnterWorkspace} isOpenSource={isOpenSource} />

      <section className="ltx-final-cta">
        <span>YOUR FIRST FILM</span>
        <h2>不用先成为剪辑师。<br />先把想表达的写下来。</h2>
        <p>{isOpenSource ? "从自己的素材和脚本开始，搭建可以持续修改的创作流程。" : "OpenVMA 会从内容策划开始，陪你完成导演、剪辑和交付。"}</p>
        <div>
          <SiteAction href={isOpenSource ? GETTING_STARTED : undefined} className="ltx-site-button is-light" onClick={() => startPath("ai-script")}>{isOpenSource ? "阅读快速开始" : "免费开始创作"}<ArrowRight size={16} /></SiteAction>
          <SiteAction href={isOpenSource ? REPOSITORY : undefined} className="ltx-site-button is-dark-outline" onClick={() => isAuthenticated ? onEnterWorkspace?.("projects") : onOpenAuth?.("login")}>{isOpenSource ? "查看 GitHub 源码" : "进入项目中心"}</SiteAction>
        </div>
      </section>

      <footer className="ltx-footer" id="site-footer">
        <div className="ltx-footer-brand"><SiteBrand /><p>{isOpenSource ? "开源视频创作工作流，让脚本、分镜、素材和导出连接在一起。" : "为不会策划、导演和剪辑的内容创作者，完成从文字到影片的全过程。"}</p></div>
        <nav aria-label="页脚导航">
          <section><strong>产品</strong><a href="#site-capabilities">如何工作</a><a href="#site-workflow">产品体验</a><a href="#site-start">开始方式</a></section>
          <section><strong>探索</strong><a href="#site-showcase">{isOpenSource ? "视觉参考" : "太空案例"}</a><a href={isOpenSource ? "#site-open-source" : "#site-pricing"}>{isOpenSource ? "开源部署" : "会员方案"}</a><a href="#site-help">{isOpenSource ? "常见问题" : "帮助中心"}</a></section>
          {isOpenSource ? <section><strong>OpenVMA</strong><a href={`${DOCUMENTATION}/architecture.md`}>架构文档</a><a href={`${DOCUMENTATION}/limitations.md`}>能力与限制</a><a href={`${REPOSITORY}/blob/main/CONTRIBUTING.md`}>参与贡献</a></section> : <section><strong>OpenVMA</strong><a href="#site-footer">关于我们</a><a href="#site-footer">隐私政策</a><a href="#site-footer">服务条款</a></section>}
        </nav>
        <div className="ltx-footer-bottom"><div><span>{isOpenSource ? "© 2026 OpenVMA · MIT License" : "© 2026 OpenVMA. 保留所有权利。"}</span><p className="ltx-image-credits">视觉参考：<a href={IMAGE_SOURCES.nasa}>NASA 概念图</a> · <a href={IMAGE_SOURCES.moon}>NASA 月球摄影</a> · <a href={IMAGE_SOURCES.alpine}>Deralpinbergsteiger</a>（<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>；已缩放、转码） · <a href={`${REPOSITORY}/blob/main/THIRD_PARTY_NOTICES.md`}>图片说明</a></p></div><span>FROM DOCUMENT TO FILM</span></div>
      </footer>
    </main>
  );
}

export default SiteHome;
