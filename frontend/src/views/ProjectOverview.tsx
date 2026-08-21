import { useState } from "react";
import {
  ArrowLeft,
  ChevronRight,
  Clock3,
  CloudUpload,
  FileText,
  Film,
  Image as ImageIcon,
  Play,
  Scissors,
  SlidersHorizontal,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Workspace } from "@/api/projects";
import { VideoThumb } from "@/components/VideoThumb";

type Tab = "overview" | "assets" | "script" | "timeline";

interface Props {
  workspace: Workspace;
  onBack: () => void;
  onEnterEditor: () => void;
  onEditProject: () => void;
  onUpload: () => void;
  onOpenQuickAI: () => void;
  onOpenTasks: () => void;
}

const statusLabels = {
  draft: "草稿",
  editing: "编辑中",
  processing: "处理中",
  ready: "可导出",
  exporting: "导出中",
  failed: "处理失败",
} as const;

function formatDuration(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function ProjectOverview({ workspace, onBack, onEnterEditor, onEditProject, onUpload, onOpenQuickAI, onOpenTasks }: Props) {
  const [tab, setTab] = useState<Tab>("overview");
  const { project, document, linkedAssets } = workspace;
  const scenes = document.storyboard.scenes;
  const shots = scenes.flatMap((scene) => scene.shots);
  const matchedShots = shots.filter((shot) => Boolean(shot.assetId || shot.selectedMediaVersionId)).length;
  const visualAssets = linkedAssets.filter((asset) => asset.mediaType !== "audio");
  const cover = visualAssets.find((asset) => asset.id === project.coverAssetId) ?? visualAssets[0];
  const title = document.settings.title || project.name;
  const summary = document.settings.summary || project.description || "围绕同一支影片组织脚本、镜头、素材与 AI 生成结果。";
  const timelineReady = document.timeline.durationMs > 0 && shots.length > 0;
  const metrics: Array<{ icon: LucideIcon; value: number; label: string; copy: string; onClick?: () => void }> = [
    { icon: Film, value: linkedAssets.length, label: "项目素材", copy: `${visualAssets.length} 个画面素材` },
    { icon: FileText, value: scenes.length, label: "脚本场景", copy: `共 ${shots.length} 个镜头` },
    { icon: Scissors, value: timelineReady ? 1 : 0, label: "主剪辑", copy: timelineReady ? "主时间线已保存" : "等待生成主时间线" },
    { icon: Sparkles, value: project.activeJobCount, label: "处理任务", copy: project.activeJobCount ? `${project.activeJobCount} 个正在进行` : "查看项目任务记录", onClick: onOpenTasks },
  ];

  const assetSection = (
    <section className="overflow-hidden rounded-2xl border border-line bg-white">
      <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4"><div><h2 className="text-sm font-semibold text-text">项目素材</h2><p className="mt-1 text-[11px] text-muted">项目内上传、匹配和 AI 生成的素材</p></div><button type="button" onClick={onUpload} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-medium text-text"><CloudUpload size={14} />添加素材</button></header>
      {linkedAssets.length ? <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">{linkedAssets.slice(0, tab === "overview" ? 4 : undefined).map((asset) => <article key={asset.id} className="overflow-hidden rounded-xl border border-line bg-canvas/40"><div className="relative aspect-video overflow-hidden bg-[#17191f]"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={asset.mediaType === "video"} /><span className="absolute bottom-2 right-2 rounded bg-black/65 px-1.5 py-0.5 text-[9px] text-white">{asset.mediaType === "audio" ? "音频" : asset.mediaType === "image" ? "图片" : formatDuration(asset.durationMs)}</span></div><div className="p-3"><strong className="block truncate text-xs text-text">{asset.name}</strong><p className="mt-1 flex items-center justify-between text-[10px] text-muted"><span>{asset.sourceCategory === "ai" ? "AI 生成" : "项目素材"}</span><span>{asset.processingStatus === "ready" ? "可用" : asset.processingStatus}</span></p></div></article>)}</div> : <div className="grid min-h-52 place-items-center p-8 text-center"><div><ImageIcon size={24} className="mx-auto text-muted" /><strong className="mt-3 block text-sm text-text">项目还没有素材</strong><p className="mt-1 text-xs text-muted">上传素材，或使用快捷 AI 生成创建第一组画面。</p><div className="mt-4 flex justify-center gap-2"><button type="button" onClick={onUpload} className="rounded-lg border border-line px-3 py-2 text-xs text-text">上传素材</button><button type="button" onClick={onOpenQuickAI} className="rounded-lg bg-blue px-3 py-2 text-xs font-semibold text-white">AI 生成</button></div></div></div>}
      {tab === "overview" && linkedAssets.length > 4 && <footer className="flex items-center justify-between border-t border-line px-5 py-3 text-[11px] text-muted"><span>共 {linkedAssets.length} 个项目素材</span><button type="button" onClick={() => setTab("assets")} className="flex items-center gap-1 font-medium text-text">查看全部<ChevronRight size={13} /></button></footer>}
    </section>
  );

  const scriptSection = (
    <section className="overflow-hidden rounded-2xl border border-line bg-white">
      <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4"><div><h2 className="text-sm font-semibold text-text">脚本编排</h2><p className="mt-1 text-[11px] text-muted">脚本、分镜和素材共同驱动唯一主时间线</p></div><button type="button" onClick={onEnterEditor} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white"><FileText size={14} />打开脚本</button></header>
      {scenes.length ? <div className="divide-y divide-line px-5">{scenes.slice(0, tab === "overview" ? 3 : undefined).map((scene) => <button type="button" onClick={onEnterEditor} key={scene.id ?? scene.index} className="grid w-full grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 py-4 text-left"><span className="grid h-9 w-9 place-items-center rounded-lg bg-canvas text-xs font-semibold text-muted">{scene.index + 1}</span><span className="min-w-0"><strong className="block truncate text-xs text-text">{scene.outline || `场景 ${scene.index + 1}`}</strong><small className="mt-1 block truncate text-[10px] text-muted">{scene.shots.length} 个镜头 · {formatDuration(scene.estimatedDurationMs)} · {scene.intent || "等待完善叙事意图"}</small></span><ChevronRight size={15} className="text-muted" /></button>)}</div> : <div className="grid min-h-48 place-items-center p-8 text-center"><div><FileText size={22} className="mx-auto text-muted" /><strong className="mt-3 block text-sm text-text">还没有项目脚本</strong><p className="mt-1 text-xs text-muted">进入创作工作区，粘贴脚本或使用 AI 生成初稿。</p><button type="button" onClick={onEnterEditor} className="mt-4 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white">开始写脚本</button></div></div>}
      {tab === "overview" && scenes.length > 3 && <footer className="flex items-center justify-between border-t border-line px-5 py-3 text-[11px] text-muted"><span>共 {scenes.length} 个场景</span><button type="button" onClick={() => setTab("script")} className="flex items-center gap-1 font-medium text-text">查看完整脚本<ChevronRight size={13} /></button></footer>}
    </section>
  );

  const timelineSection = (
    <section className="overflow-hidden rounded-2xl border border-line bg-white">
      <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4"><div><h2 className="text-sm font-semibold text-text">主剪辑</h2><p className="mt-1 text-[11px] text-muted">项目只保留一条主时间线和一个主画幅</p></div><button type="button" onClick={onEnterEditor} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white"><Scissors size={14} />{timelineReady ? "继续剪辑" : "生成主剪辑"}</button></header>
      <button type="button" onClick={onEnterEditor} className="grid w-full gap-5 p-4 text-left sm:grid-cols-[220px_minmax(0,1fr)]"><div className="relative aspect-video overflow-hidden rounded-xl bg-[#17191f]"><VideoThumb fill imageUrl={cover?.thumbnailUrl ?? (cover?.mediaType === "image" ? cover.mediaUrl : undefined)} videoUrl={cover?.mediaType === "video" ? cover.mediaUrl : undefined} showPlay={false} /><span className="absolute inset-0 grid place-items-center bg-black/15"><i className="grid h-11 w-11 place-items-center rounded-full bg-white text-ink shadow-lg"><Play size={17} className="translate-x-px" /></i></span><em className="absolute bottom-2 right-2 rounded bg-black/65 px-2 py-1 text-[9px] not-italic text-white">{document.settings.aspectRatio}</em></div><div className="self-center"><span className="rounded-full bg-teal/10 px-2 py-1 text-[10px] font-semibold text-teal">{timelineReady ? "主时间线已建立" : "等待生成"}</span><h3 className="mt-3 text-sm font-semibold text-text">{title} · 主剪辑</h3><p className="mt-2 text-xs leading-5 text-muted">{timelineReady ? "主时间线已经保存，可以继续调整镜头、声音、字幕和全局视觉层。" : "完善脚本与镜头后，系统会把它们编排为可持续编辑的主时间线。"}</p><div className="mt-4 flex flex-wrap gap-4 text-[10px] text-muted"><span>{formatDuration(document.timeline.durationMs)}</span><span>{document.timeline.tracks.length} 条轨道</span><span>{document.settings.resolution}</span><span>{document.settings.fps} fps</span></div></div></button>
    </section>
  );

  return (
    <main className="h-full overflow-y-auto bg-[#f5f5f6]">
      <div className="mx-auto w-full max-w-[1440px] px-4 pb-14 pt-5 sm:px-7 lg:px-8">
        <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex min-w-0 items-center gap-2 text-xs text-muted" aria-label="项目导航"><button type="button" onClick={onBack} className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 font-medium text-text"><ArrowLeft size={14} />工作台</button><ChevronRight size={14} /><span className="truncate">{project.name}</span></nav>
          <div className="flex flex-wrap gap-2"><button type="button" onClick={onOpenQuickAI} className="flex items-center gap-1.5 rounded-lg border border-blue/20 bg-blue-soft px-3 py-2 text-xs font-semibold text-blue"><Sparkles size={14} />快捷 AI 生成</button><button type="button" onClick={onEditProject} className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-xs font-medium text-text"><SlidersHorizontal size={14} />编辑项目信息</button><button type="button" onClick={onEnterEditor} className="flex items-center gap-1.5 rounded-lg bg-ink px-4 py-2 text-xs font-semibold text-white"><Scissors size={14} />进入创作</button></div>
        </header>

        <section className="grid gap-7 overflow-hidden rounded-[20px] border border-line bg-white p-5 shadow-[0_12px_34px_rgba(20,20,24,0.05)] sm:p-7 lg:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
          <div className="min-w-0 self-center py-2 lg:pl-1"><div className="flex flex-wrap gap-2"><span className="flex items-center gap-1.5 rounded-full border border-line bg-canvas px-2.5 py-1.5 text-[10px] font-semibold text-muted"><i className="h-1.5 w-1.5 rounded-full bg-teal" />{statusLabels[project.status]}</span><span className="rounded-full border border-line bg-canvas px-2.5 py-1.5 text-[10px] font-semibold text-muted">{project.type}</span></div><h1 className="mt-5 text-3xl font-semibold tracking-[-0.035em] text-text sm:text-4xl lg:text-[44px] lg:leading-[1.1]">{project.name}</h1><p className="mt-4 max-w-2xl text-sm leading-7 text-muted">{summary}</p><div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-muted"><span className="flex items-center gap-1.5"><Clock3 size={13} />最近更新 {project.updatedAt}</span><span className="flex items-center gap-1.5"><Film size={13} />{linkedAssets.length} 个项目素材</span><span className="flex items-center gap-1.5"><FileText size={13} />{scenes.length ? "脚本编排已建立" : "等待脚本编排"}</span><span className="flex items-center gap-1.5"><Scissors size={13} />{timelineReady ? "主剪辑已生成" : "等待主剪辑"}</span></div></div>
          <button type="button" onClick={onEnterEditor} className="group relative min-h-[250px] overflow-hidden rounded-2xl bg-[#111318] text-left"><VideoThumb fill imageUrl={cover?.thumbnailUrl ?? (cover?.mediaType === "image" ? cover.mediaUrl : undefined)} videoUrl={cover?.mediaType === "video" ? cover.mediaUrl : undefined} showPlay={false} /><span className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/5 to-transparent" /><span className="absolute bottom-5 left-5 right-5 grid grid-cols-[42px_minmax(0,1fr)] items-center gap-x-3 text-white"><i className="row-span-2 grid h-10 w-10 place-items-center rounded-full bg-white text-ink transition group-hover:scale-105"><Play size={16} className="translate-x-px" /></i><strong className="text-xs">{timelineReady ? "继续主剪辑" : "进入创作工作区"}</strong><small className="mt-1 truncate text-[10px] text-white/65">{formatDuration(document.timeline.durationMs)} · {document.settings.aspectRatio} · {matchedShots}/{shots.length} 个镜头已有画面</small></span></button>
        </section>

        <section className="my-4 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="项目概览数据">
          {metrics.map(({ icon: Icon, value, label, copy, onClick }) => onClick ? <button type="button" onClick={onClick} key={label} className="grid min-w-0 grid-cols-[38px_minmax(0,1fr)] gap-x-3 rounded-xl border border-line bg-white p-3.5 text-left transition hover:border-ink/25 hover:bg-canvas/40"><span className="row-span-2 grid h-9 w-9 place-items-center rounded-lg bg-canvas text-text"><Icon size={16} /></span><div className="flex items-baseline gap-1.5"><strong className="text-lg leading-none text-text">{value}</strong><small className="text-[10px] font-semibold text-muted">{label}</small></div><em className="mt-1 truncate text-[9px] not-italic text-muted">{copy}</em></button> : <article key={label} className="grid min-w-0 grid-cols-[38px_minmax(0,1fr)] gap-x-3 rounded-xl border border-line bg-white p-3.5"><span className="row-span-2 grid h-9 w-9 place-items-center rounded-lg bg-canvas text-text"><Icon size={16} /></span><div className="flex items-baseline gap-1.5"><strong className="text-lg leading-none text-text">{value}</strong><small className="text-[10px] font-semibold text-muted">{label}</small></div><em className="mt-1 truncate text-[9px] not-italic text-muted">{copy}</em></article>)}
        </section>

        <nav className="flex gap-1 overflow-x-auto border-b border-line" role="tablist" aria-label="项目内容">{([['overview', '项目概览'], ['assets', '项目素材'], ['script', '项目脚本'], ['timeline', '主时间线']] as const).map(([id, label]) => <button type="button" role="tab" aria-selected={tab === id} key={id} onClick={() => setTab(id)} className={`border-b-2 px-4 py-3 text-xs font-medium ${tab === id ? "border-ink text-text" : "border-transparent text-muted hover:text-text"}`}>{label}</button>)}</nav>

        {tab === "overview" ? <div className="mt-4 grid gap-4 xl:grid-cols-2"><div className="space-y-4">{assetSection}{scriptSection}</div><div className="space-y-4"><section className="relative overflow-hidden rounded-2xl bg-ink p-5 text-white"><div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-blue/30 blur-3xl" /><div className="relative"><span className="grid h-10 w-10 place-items-center rounded-xl bg-white/10"><WandSparkles size={19} /></span><h2 className="mt-4 text-base font-semibold">快捷 AI 生成</h2><p className="mt-2 max-w-md text-xs leading-5 text-white/60">直接为整个项目、当前场景或单个镜头生成图片、视频和动态特效。结果会自动归入项目素材，并保留可回退版本。</p><button type="button" onClick={onOpenQuickAI} className="mt-5 flex items-center gap-1.5 rounded-lg bg-white px-4 py-2.5 text-xs font-semibold text-ink"><Sparkles size={14} />开始生成</button></div></section>{timelineSection}</div></div> : <div className="mt-4">{tab === "assets" ? assetSection : tab === "script" ? scriptSection : timelineSection}</div>}
      </div>
    </main>
  );
}
