import { useState } from "react";
import { ArrowDown, ArrowRight, Check, ChevronRight, FileText, GitBranch, Github, Layers, Menu, Search, Terminal, X } from "lucide-react";
import { BrandLogo } from "../components/BrandLogo";

const repository = "https://github.com/WowCoder/OpenVMA";
const docs = `${repository}/blob/main/docs`;
const navigation = [
  ["能力", "#capabilities"],
  ["工作流", "#workflow"],
  ["架构", "#architecture"],
  ["开始使用", "#start"],
] as const;
const steps = [
  { title: "从依据开始", short: "灵感与脚本", icon: Search, detail: "灵感任务用受限的 LLM 检索规划收集来源，后端校验选题引用。脚本任务可结合提示词和素材摘要生成结构化场景与镜头。", artifact: "检索来源 → 选题建议；提示词/素材 → 脚本", boundary: "引用校验验证来源关系，内容真实性仍需人工审阅。" },
  { title: "把选择留给创作者", short: "素材与镜头", icon: Layers, detail: "用 pgvector 检索素材，按配置接入重排服务。候选素材进入镜头工作区，由你确认使用哪一份，而不是隐藏选择过程。", artifact: "素材库 → 候选集 → 已选镜头", boundary: "向量检索和重排需要相应模型服务配置。" },
  { title: "让任务有迹可循", short: "生成与版本", icon: GitBranch, detail: "供应商生成任务持久化保存状态；提交保护减少重复请求。修订号约束回写，避免旧任务覆盖新的脚本修改。", artifact: "修订号 → 持久化任务 → 结果回写", boundary: "外部生成服务需要自备账号与密钥，可能产生费用。" },
  { title: "按编排确定性导出", short: "编排与导出", icon: FileText, detail: "镜头、音频与字幕汇入编排文档，FFmpeg 按确定的时间线执行媒体处理和导出。AI 参与创作，导出由明确规则完成。", artifact: "编排文档 → 时间线 → 视频文件", boundary: "输出取决于输入素材与编排配置，需本地 FFmpeg 和工作进程。" },
];

function WorkflowIllustration() {
  return (
    <figure className="project-illustration">
      <div className="illustration-topbar">
        <span><BrandLogo variant="mark" tone="light" size={22} decorative /> 创作工作区</span>
        <span className="illustration-label">概念示意 / ILLUSTRATION</span>
      </div>
      <div className="illustration-body">
        <div className="illustration-script">
          <p className="panel-label">01 / IDEAS & EVIDENCE</p>
          <h3>在山与海之间</h3>
          <p className="script-copy">以镜头记录旅程，<br />让故事沿着时间展开。</p>
          <div className="script-note"><FileText size={14} aria-hidden="true" /><span>选题建议 ↔ 来源链接</span></div>
          <div className="script-lines" aria-hidden="true"><i /><i /><i /></div>
          <div className="revision-note"><GitBranch size={14} aria-hidden="true" /> 修订号约束结果回写</div>
        </div>
        <div className="illustration-preview">
          <svg className="landscape" viewBox="0 0 620 360" role="img" aria-labelledby="landscape-title">
            <title id="landscape-title">原创几何山海图形，表示镜头画面，不是真实视频</title>
            <defs>
              <linearGradient id="sky" x2="0" y2="1"><stop stopColor="#b7b9bb" /><stop offset="1" stopColor="#e6e5df" /></linearGradient>
              <linearGradient id="sea" x2="0" y2="1"><stop stopColor="#525b61" /><stop offset="1" stopColor="#262e34" /></linearGradient>
            </defs>
            <path fill="url(#sky)" d="M0 0h620v360H0z" />
            <circle cx="460" cy="100" r="40" fill="#ecece7" />
            <path fill="#8c9497" d="M0 218 100 120 172 182 278 76 392 227 488 184 620 249v111H0z" />
            <path fill="#59636a" d="m0 279 118-99 110 81 107-89 126 114 79-50 80 58v66H0z" />
            <path fill="url(#sea)" d="M0 280q130-20 310 0t310 0v80H0z" />
            <g stroke="#b8bcbc" fill="none" opacity=".36"><path d="M290 299h120m-60 10h170m-390 17h150m-58 15h190" /></g>
            <path fill="#d6d9d6" opacity=".3" d="m278 76-31 89 35-12 26 29z" />
          </svg>
          <div className="preview-caption"><span>镜头画面 / 原创示意图</span><strong>故事，由你来决定。</strong></div>
          <div className="illustration-timeline" aria-label="示意时间线：镜头、旁白和字幕三个轨道">
            <div><span>镜头</span><i className="track-shot">山</i><i className="track-shot">海</i><i className="track-shot">旅程</i></div>
            <div><span>旁白</span><i className="track-audio" /></div>
            <div><span>字幕</span><i className="track-subtitle">沿着时间展开</i></div>
          </div>
        </div>
        <div className="illustration-shots">
          <p className="panel-label">02 / SHOT SELECTION</p>
          <div className="shot-card is-selected"><div className="shot-thumb mountain-thumb" aria-hidden="true" /><span><strong>镜头 A</strong><small>手动确认素材</small></span><Check size={16} aria-hidden="true" /></div>
          <div className="shot-card"><div className="shot-thumb sea-thumb" aria-hidden="true" /><span><strong>镜头 B</strong><small>候选素材待审阅</small></span></div>
          <div className="shot-card"><div className="shot-thumb path-thumb" aria-hidden="true" /><span><strong>镜头 C</strong><small>候选素材待审阅</small></span></div>
          <div className="export-note"><span>03 / COMPOSITION</span><strong>编排文档 → FFmpeg</strong><small>确定的时间线，明确的导出规则。</small></div>
        </div>
      </div>
      <figcaption><span>WORKFLOW, MADE VISIBLE</span><strong>从资料到成片，每一步都有可审阅的中间结果。</strong><small>工作流示意，非产品截图或真实生成结果。</small></figcaption>
    </figure>
  );
}

export default function ProjectPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedStep, setSelectedStep] = useState(0);
  const currentStep = steps[selectedStep];
  return (
    <div className="project-page" id="top">
      <a className="skip-link" href="#main">跳到主要内容</a>
      <div className="project-announcement"><span>OPEN SOURCE · MIT LICENSE</span><a href={repository}>在 GitHub 探索 OpenVMA <ArrowRight size={13} aria-hidden="true" /></a></div>
      <header className="project-header">
        <a className="project-logo" href="#top" aria-label="OpenVMA 首页"><BrandLogo height={25} decorative /></a>
        <nav id="project-navigation" className={menuOpen ? "is-open" : ""} aria-label="页面导航">
          {navigation.map(([label, href]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</a>)}
        </nav>
        <a className="header-source" href={repository}><Github size={16} aria-hidden="true" /> GitHub <ArrowRight size={14} aria-hidden="true" /></a>
        <button className="mobile-menu" aria-expanded={menuOpen} aria-controls="project-navigation" aria-label={menuOpen ? "关闭导航" : "打开导航"} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
      </header>
      <main id="main">
        <section className="project-hero" aria-labelledby="hero-title">
          <span className="eyebrow">OPEN VIDEO MAKING ASSISTANT</span>
          <h1 id="hero-title">让创意成为<br /><span>可控的视频工作流。</span></h1>
          <p className="hero-description">OpenVMA 是一个开源视频创作项目。<br className="desktop-break" />连接带来源的灵感、可审阅的素材和可追踪的生成任务，<br className="desktop-break" />再用明确的编排规则，把故事导出为视频。</p>
          <div className="project-actions"><a className="project-button is-dark" href={repository}><Github size={16} aria-hidden="true" /> 查看源码 <ArrowRight size={16} aria-hidden="true" /></a><a className="project-button is-outline" href={`${docs}/getting-started.md`}>本地开始 <Terminal size={16} aria-hidden="true" /></a></div>
          <a className="hero-explore" href="#workflow">了解工作流 <ArrowDown size={13} aria-hidden="true" /></a>
          <WorkflowIllustration />
          <div className="project-principles"><span><b>01</b> 选题附带来源</span><span><b>02</b> 创作者确认素材</span><span><b>03</b> 确定性媒体导出</span></div>
        </section>
        <section className="project-section capability-section" id="capabilities" aria-labelledby="capability-title">
          <div className="section-heading"><div><span className="eyebrow">BUILT FOR CONTROL</span><h2 id="capability-title">不只生成。<br />让创作过程可见。</h2></div><p>把 AI 能力放进有边界的工作流，<br />把证据、选择和状态保留在项目里。</p></div>
          <div className="capability-grid">
            <article><Search size={24} strokeWidth={1.4} aria-hidden="true" /><span className="eyebrow">GROUNDED IDEAS</span><h3>有来源的灵感</h3><p>灵感任务通过受限的 LLM 检索规划与引用校验，为选题保留来源；pgvector 与可配置的重排帮助发现相关素材。</p><a href={`${docs}/architecture.md`}>了解检索与证据 <ChevronRight size={14} aria-hidden="true" /></a></article>
            <article><GitBranch size={24} strokeWidth={1.4} aria-hidden="true" /><span className="eyebrow">DURABLE WORKFLOWS</span><h3>可追踪的长任务</h3><p>保存供应商任务状态，保护重复提交。脚本与编排使用修订号控制更新，让异步结果与当前编辑保持一致。</p><a href={`${docs}/architecture.md`}>了解任务与修订 <ChevronRight size={14} aria-hidden="true" /></a></article>
            <article><Layers size={24} strokeWidth={1.4} aria-hidden="true" /><span className="eyebrow">DETERMINISTIC EXPORT</span><h3>由编排驱动导出</h3><p>手动确认镜头素材，将镜头、旁白和字幕收敛到编排文档。FFmpeg 按时间线处理媒体并输出文件。</p><a href={`${docs}/architecture.md`}>了解编排与导出 <ChevronRight size={14} aria-hidden="true" /></a></article>
          </div>
        </section>
        <section className="workflow-section" id="workflow" aria-labelledby="workflow-title">
          <div className="project-section">
            <div className="section-heading"><div><span className="eyebrow">FROM IDEA TO EXPORT</span><h2 id="workflow-title">四步，连接完整创作。</h2></div><p>每个阶段都有明确的输入与输出。<br />选择一个阶段，查看它在项目中的职责。</p></div>
            <div className="workflow-selector" aria-label="选择工作流阶段">
              {steps.map((step, index) => { const Icon = step.icon; return <button key={step.short} className={selectedStep === index ? "is-active" : ""} aria-pressed={selectedStep === index} aria-controls="workflow-detail" onClick={() => setSelectedStep(index)}><span className="step-index">0{index + 1} <Icon size={20} strokeWidth={1.4} aria-hidden="true" /></span><strong>{step.short}</strong><ArrowRight size={18} aria-hidden="true" /></button>; })}
            </div>
            <div className="workflow-detail" id="workflow-detail" aria-live="polite" aria-atomic="true"><div><span className="eyebrow">STEP 0{selectedStep + 1}</span><h3>{currentStep.title}</h3><p>{currentStep.detail}</p></div><div className="workflow-artifact"><span>输入与输出</span><strong>{currentStep.artifact}</strong><p>{currentStep.boundary}</p></div></div>
          </div>
        </section>
        <section className="architecture-section" id="architecture" aria-labelledby="architecture-title">
          <div className="project-section architecture-inner"><div><span className="eyebrow">OPEN BY DESIGN</span><h2 id="architecture-title">能看懂，<br />才能继续构建。</h2><p>React 工作区连接 FastAPI 服务；Celery 执行长任务，PostgreSQL / pgvector 保存项目与向量，Redis 支持队列，MinIO 保存媒体，FFmpeg 负责导出。</p><a className="project-button is-light" href={`${docs}/architecture.md`}>阅读架构文档 <ArrowRight size={16} aria-hidden="true" /></a></div><div className="architecture-diagram" aria-label="架构示意：React 工作区通过 FastAPI 连接数据与任务层，Celery 调用供应商和 FFmpeg，媒体存储在 MinIO"><div className="architecture-layer"><span>WORKSPACE</span><strong>React + TypeScript</strong></div><div className="architecture-connector" aria-hidden="true">↓</div><div className="architecture-layer"><span>APPLICATION</span><strong>FastAPI</strong></div><div className="architecture-connector" aria-hidden="true">↓</div><div className="architecture-split"><div><span>STATE & MEDIA</span><strong>PostgreSQL / pgvector</strong><small>Redis · MinIO</small></div><div><span>BACKGROUND TASKS</span><strong>Celery</strong><small>供应商服务 · FFmpeg</small></div></div><p>架构示意 · 供应商能力按需配置</p></div></div>
        </section>
        <section className="project-section start-section" id="start" aria-labelledby="start-title"><span className="eyebrow">MAKE IT YOUR OWN</span><h2 id="start-title">从源码开始，<br />构建你的创作流程。</h2><p>按快速开始文档配置本地环境，先了解媒体工作流，<br className="desktop-break" />再按需接入模型与生成服务。</p><div className="project-actions"><a className="project-button is-dark" href={`${docs}/getting-started.md`}>阅读快速开始 <ArrowRight size={16} aria-hidden="true" /></a><a className="project-button is-outline" href={repository}><Github size={16} aria-hidden="true" /> 获取源码</a></div><div className="start-notes"><span>MIT 许可</span><span>支持本地部署</span><span>模型与供应商需自行配置</span></div></section>
      </main>
      <footer className="project-footer"><a href="#top" aria-label="回到 OpenVMA 页首"><BrandLogo height={22} decorative /></a><p>开源视频创作工作流 · © WowCoder</p><div><a href={`${repository}/blob/main/LICENSE`}>MIT License</a><a href={`${docs}/limitations.md`}>能力与限制</a><a href={`${repository}/blob/main/CONTRIBUTING.md`}>参与贡献</a><a href={repository}>GitHub <ArrowRight size={12} aria-hidden="true" /></a></div></footer>
    </div>
  );
}
