import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Clapperboard,
  FileText,
  Film,
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

function ComposerPreview({ work }: { work: ShowcaseWork }) {
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
        <span>已自动保存</span>
        <em>导出影片</em>
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
          <header><div><i /><span><strong>成片预览</strong><small>随文档实时更新</small></span></div><em>16:9</em></header>
          <figure>
            <ShowcaseMedia work={work} />
            <button aria-label={playing ? "暂停成片示意" : "播放成片示意"} aria-pressed={playing} onClick={togglePreview} type="button">
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
}: Pick<SiteHomeProps, "isAuthenticated" | "onOpenAuth" | "onEnterWorkspace">) {
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  function openHelp() {
    if (isAuthenticated) onEnterWorkspace?.("help");
    else onOpenAuth?.("login");
  }

  return (
    <section className="ltx-site-help ltx-site-section" id="site-help" aria-labelledby="ltx-help-title">
      <div className="ltx-section-heading is-split">
        <div><span>QUESTIONS</span><h2 id="ltx-help-title">第一次做视频，<br />可以从这里开始。</h2></div>
        <p>{helpCenterCopy.description}</p>
      </div>
      <div className="ltx-help-layout">
        <div className="ltx-help-intro">
          <strong>不用先学会剪辑软件。</strong>
          <p>创建项目后，先把主题或文章交给 AI。每一个策划、分镜和剪辑结果都可以继续修改。</p>
          <button onClick={openHelp} type="button">打开完整帮助中心<ArrowRight size={15} /></button>
        </div>
        <div className="ltx-help-faq">
          {helpFaqs.slice(0, 5).map(([question, answer], index) => (
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

export function SiteHome({
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
      <a className="ltx-site-announcement" href="#site-capabilities">
        <span>OpenVMA 为第一次做视频的人而设计</span><ArrowRight size={16} />
      </a>

      <header className={`ltx-site-header ${mobileNavOpen ? "is-menu-open" : ""}`}>
        <button className="ltx-site-logo-button" onClick={goToSiteTop} aria-label="返回 OpenVMA 官网顶部" type="button">
          <SiteBrand decorative />
        </button>

        <nav className="ltx-site-nav" id="ltx-site-navigation" aria-label="官网导航">
          <a href="#site-capabilities" onClick={closeMobileNav}>如何工作</a>
          <a href="#site-workflow" onClick={closeMobileNav}>产品体验</a>
          <a href="#site-showcase" onClick={closeMobileNav}>太空案例</a>
          <a href="#site-start" onClick={closeMobileNav}>开始方式</a>
          <a href="#site-pricing" onClick={closeMobileNav}>价格</a>
          <a href="#site-help" onClick={closeMobileNav}>帮助</a>
        </nav>

        <div className="ltx-site-header-end">
          <AccountArea
            isAuthenticated={isAuthenticated}
            membership={membership}
            user={user}
            onOpenAuth={onOpenAuth}
            onEnterWorkspace={onEnterWorkspace}
          />
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
          <span className="ltx-kicker">AI 策划 · AI 导演 · AI 剪辑</span>
          <h1 id="ltx-hero-title">只会写文档，<br />也能完成一支影片。</h1>
          <p>你负责写下观点。OpenVMA 负责选题策划、影片导演和自动剪辑，把文章变成可以直接发布的视频。</p>
          <div className="ltx-hero-actions">
            <button className="ltx-site-button is-dark" onClick={() => startPath("ai-script")} type="button">写下第一个选题<ArrowRight size={17} /></button>
            <a className="ltx-site-button is-outline" href="#site-workflow">看看如何工作<Play size={15} /></a>
          </div>
          <small><Check size={14} />不需要会分镜、不需要会剪辑，也不需要先准备好全部素材。</small>
        </div>

        <figure className="ltx-hero-visual">
          <div><ShowcaseMedia work={heroWork} eager /></div>
          <figcaption><span>SPACE STORY / 电影级太空视觉参考</span><strong>{heroWork.title}</strong><small>真实影像只负责建立方向，故事仍然从你的文字开始。</small></figcaption>
        </figure>

        <div className="ltx-hero-proof" aria-label="OpenVMA 创作前提">
          <span><strong>01</strong>给一个主题</span>
          <span><strong>02</strong>粘贴一篇文章</span>
          <span><strong>03</strong>像改文档一样确认成片</span>
        </div>
      </section>

      <section className="ltx-agent-flow ltx-site-section" id="site-capabilities" aria-labelledby="ltx-capabilities-title">
        <div className="ltx-section-heading is-split">
          <div><span>ONE AGENT, FOUR JOBS</span><h2 id="ltx-capabilities-title">不是复杂的剪辑工具。<br />是替你完成制作的 Agent。</h2></div>
          <p>你不用在策划、脚本、素材库和剪辑软件之间来回切换。四个制作环节围绕同一份文档连续完成。</p>
        </div>

        <div className="ltx-agent-grid">
          {AGENT_STEPS.map((step) => {
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
            <div><p>脚本就是影片的控制台。修改段落、旁白或镜头说明，画面、声音和预览会跟着更新。</p><button className="ltx-site-button is-dark" onClick={() => startPath("write-script")} type="button">用一篇文档开始<ArrowRight size={16} /></button></div>
          </div>

          <ComposerPreview work={previewWork} />

          <div className="ltx-workflow-notes">
            {SIMPLE_PROMISES.map(([title, description], index) => (
              <article key={title}><span>0{index + 1}</span><div><strong>{title}</strong><p>{description}</p></div></article>
            ))}
          </div>
        </div>
      </section>

      <section className="ltx-showcase ltx-site-section" id="site-showcase" aria-labelledby="ltx-showcase-title">
        <div className="ltx-section-heading is-split">
          <div><span>SPACE REFERENCES</span><h2 id="ltx-showcase-title">先看见方向，<br />再让故事发生。</h2></div>
          <p>太空题材适合解释尺度、未知和未来。OpenVMA 会从镜头参考中提取构图与情绪，而不是堆叠无关图片。</p>
        </div>

        <div className="ltx-showcase-grid">
          {spaceCases.map((work, index) => (
            <article key={work.id}>
              <figure><ShowcaseMedia work={work} /></figure>
              <div><span>0{index + 1} / {work.eyebrow}</span><h3>{work.title}</h3><p>{work.description}</p><button onClick={() => startPath("ai-script")} type="button">用这个方向创作<ArrowRight size={15} /></button></div>
            </article>
          ))}
        </div>
      </section>

      <section className="ltx-start ltx-site-section" id="site-start" aria-labelledby="ltx-start-title">
        <div className="ltx-section-heading is-split">
          <div><span>START WITH WHAT YOU HAVE</span><h2 id="ltx-start-title">你有什么，<br />就从什么开始。</h2></div>
          <p>没有脚本也没关系。没有素材也没关系。所有入口最后都会回到一份可修改的影片文档。</p>
        </div>
        <div className="ltx-start-grid">
          {STARTING_POINTS.slice(0, 3).map((point) => {
            const Icon = START_ICON_BY_ID[point.id] ?? Sparkles;
            return (
              <button onClick={() => startPath(point.method)} type="button" key={point.id}>
                <header><span>{point.index}</span><Icon size={19} /></header>
                <small>{point.label}</small><strong>{point.title}</strong><p>{point.description}</p>
                <footer>以此开始<ArrowRight size={15} /></footer>
              </button>
            );
          })}
        </div>
      </section>

      <section className="ltx-pricing ltx-site-section" id="site-pricing" aria-labelledby="ltx-pricing-title">
        <div className="ltx-section-heading is-split">
          <div><span>PLANS</span><h2 id="ltx-pricing-title">先完成第一支，<br />再决定做多少。</h2></div>
          <div className="ltx-pricing-heading-end">
            <p>从免费体验开始。需要更多生成额度、更高画质或团队空间时再升级。</p>
            <div className="ltx-billing-toggle" role="group" aria-label="会员付费周期">
              <button className={billingCycle === "monthly" ? "is-active" : ""} onClick={() => setBillingCycle("monthly")} type="button">月付</button>
              <button className={billingCycle === "annual" ? "is-active" : ""} onClick={() => setBillingCycle("annual")} type="button">年付 <span>省 20%</span></button>
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
      </section>

      <SiteHelp isAuthenticated={isAuthenticated} onOpenAuth={onOpenAuth} onEnterWorkspace={onEnterWorkspace} />

      <section className="ltx-final-cta">
        <span>YOUR FIRST FILM</span>
        <h2>不用先成为剪辑师。<br />先把想表达的写下来。</h2>
        <p>OpenVMA 会从内容策划开始，陪你完成导演、剪辑和交付。</p>
        <div>
          <button className="ltx-site-button is-light" onClick={() => startPath("ai-script")} type="button">免费开始创作<ArrowRight size={16} /></button>
          <button className="ltx-site-button is-dark-outline" onClick={() => isAuthenticated ? onEnterWorkspace?.("projects") : onOpenAuth?.("login")} type="button">进入项目中心</button>
        </div>
      </section>

      <footer className="ltx-footer" id="site-footer">
        <div className="ltx-footer-brand"><SiteBrand /><p>为不会策划、导演和剪辑的内容创作者，完成从文字到影片的全过程。</p></div>
        <nav aria-label="页脚导航">
          <section><strong>产品</strong><a href="#site-capabilities">如何工作</a><a href="#site-workflow">产品体验</a><a href="#site-start">开始方式</a></section>
          <section><strong>探索</strong><a href="#site-showcase">太空案例</a><a href="#site-pricing">会员方案</a><a href="#site-help">帮助中心</a></section>
          <section><strong>OpenVMA</strong><a href="#site-footer">关于我们</a><a href="#site-footer">隐私政策</a><a href="#site-footer">服务条款</a></section>
        </nav>
        <div className="ltx-footer-bottom"><span>© 2026 OpenVMA. 保留所有权利。</span><span>FROM DOCUMENT TO FILM</span></div>
      </footer>
    </main>
  );
}

export default SiteHome;
