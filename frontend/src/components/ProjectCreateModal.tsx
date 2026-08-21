import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Check, Clock3, FileAudio, Film, FolderPlus,
  Image as ImageIcon, Loader2, Sparkles, WandSparkles, X,
} from "lucide-react";
import { useNavigate } from "@/router";
import * as assetApi from "@/api/assets";
import * as generateApi from "@/api/generate";
import * as projectApi from "@/api/projects";
import type { Asset } from "@/api/assets";
import { useUIStore, type ProjectStartMethod } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { temporaryId } from "@/stores/workspaceTransforms";
import {
  applyCreationUnits, creationPreviewToUnits,
  recognizePastedScript, type CreationUnit,
} from "@/lib/projectCreationFlow";

type WizardStep = "input" | "processing" | "preview";

const sampleScript = `01 未来，不是遥远的想象，而是正在发生的协作。
画面：展馆灯光依次亮起，机器人从远处缓慢走向主舞台。

02 当机器开始理解环境，每一次行动都变得更自然。
画面：机器人识别工作人员手势，镜头切换至机械臂与传感器特写。

03 今天，我们让技术真正走进每一个工作现场。
画面：机器人与工作人员并肩完成任务，最后定格品牌主视觉。`;

const flowCopy: Record<Exclude<ProjectStartMethod, "blank">, {
  title: string; description: string; action: string; processing: string; projectType: string; variant: string;
}> = {
  "write-script": {
    title: "从脚本创建影片",
    description: "粘贴脚本，先识别台词与分镜；确认结构后再创建项目。",
    action: "识别脚本与分镜", processing: "正在识别脚本结构与画面描述", projectType: "脚本创作", variant: "stage",
  },
  "upload-assets": {
    title: "一键 AI 分析编排影片",
    description: "从素材库选择影片素材，AI 分析内容并生成可编辑的影片结构。",
    action: "开始 AI 分析编排", processing: "正在理解素材并编排影片结构", projectType: "素材编排", variant: "hall",
  },
  "ai-script": {
    title: "AI 辅助脚本",
    description: "描述想制作的视频，先生成脚本和分镜；确认后再创建项目。",
    action: "生成脚本与分镜", processing: "正在生成叙事结构与分镜", projectType: "AI 辅助脚本", variant: "robot",
  },
};

function ModalFrame({ title, description, busy, onClose, children, footer }: {
  title: string; description: string; busy: boolean; onClose: () => void; children: React.ReactNode; footer: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭弹窗" disabled={busy} onClick={onClose} className="absolute inset-0 cursor-default bg-ink/55 backdrop-blur-sm disabled:cursor-wait" />
      <section role="dialog" aria-modal="true" aria-labelledby="project-flow-title" className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_28px_80px_rgba(0,0,0,.22)]">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><Sparkles size={19} /></span>
          <div className="min-w-0 flex-1"><h2 id="project-flow-title" className="text-base font-semibold text-text">{title}</h2><p className="mt-1 text-xs leading-5 text-muted">{description}</p></div>
          <button type="button" aria-label="关闭" disabled={busy} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>
        <div className="overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-canvas/50 px-5 py-4 sm:px-6">{footer}</footer>
      </section>
    </div>
  );
}

function ProjectNameField({ name, onChange, submitted }: { name: string; onChange: (name: string) => void; submitted: boolean }) {
  return (
    <label className="block text-sm font-medium text-text">项目名称
      <input autoFocus value={name} maxLength={200} onChange={(event) => onChange(event.target.value)} placeholder="例如：2026 秋季新品发布" aria-invalid={submitted && !name.trim()} className={`mt-2 w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm text-text focus:ring-2 focus:ring-blue/10 ${submitted && !name.trim() ? "border-red" : "border-line focus:border-blue/50"}`} />
      {submitted && !name.trim() && <span className="mt-1.5 block text-xs font-normal text-red">请输入项目名称</span>}
    </label>
  );
}

function ScriptPreview({ units }: { units: CreationUnit[] }) {
  return <div className="space-y-2.5">{units.map((unit, index) => (
    <article key={`${unit.title}-${index}`} className="grid grid-cols-[32px_minmax(0,1fr)_auto] gap-3 rounded-xl border border-line bg-white p-3.5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-canvas text-[11px] font-semibold text-muted">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0"><strong className="block text-xs font-semibold text-text">{unit.title}</strong><p className="mt-1 text-xs leading-5 text-text">{unit.narration}</p><p className="mt-1.5 text-[11px] leading-5 text-muted"><Film size={12} className="mr-1 inline" />{unit.visual}</p><div className="mt-2 space-y-1">{unit.shots.map((shot, shotIndex) => <p key={`${shot.segmentId ?? "new"}-${shotIndex}`} className="rounded-md bg-canvas px-2 py-1 text-[10px] leading-4 text-muted">镜头 {shotIndex + 1} · {Math.round(shot.durationMs / 1000)} 秒 · {shot.description}</p>)}</div></div>
      <span className="flex items-center gap-1 self-start whitespace-nowrap text-[10px] text-muted"><Clock3 size={11} />约 {Math.round(unit.durationMs / 1000)} 秒</span>
    </article>
  ))}</div>;
}

function AssetPicker({ assets, selectedIds, onToggle }: { assets: Asset[]; selectedIds: Set<string>; onToggle: (id: string) => void }) {
  return <div className="grid gap-2 sm:grid-cols-2">{assets.map((asset) => {
    const selected = selectedIds.has(asset.id);
    const Icon = asset.mediaType === "image" ? ImageIcon : asset.mediaType === "audio" ? FileAudio : Film;
    const unavailable = asset.processingStatus !== "ready";
    return <button key={asset.id} type="button" disabled={unavailable} onClick={() => onToggle(asset.id)} aria-pressed={selected} className={`grid min-h-[78px] grid-cols-[38px_minmax(0,1fr)_22px] items-center gap-3 rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${selected ? "border-blue bg-blue-soft/50 shadow-[inset_0_0_0_1px_rgba(43,109,255,.18)]" : "border-line bg-white hover:border-[#bfc0c4]"}`}>
      <span className={`grid h-[38px] w-[38px] place-items-center rounded-[10px] ${selected ? "bg-blue text-white" : "bg-canvas text-muted"}`}><Icon size={17} /></span>
      <span className="min-w-0"><strong className="block truncate text-xs font-semibold text-text">{asset.name}</strong><small className="mt-1 block truncate text-[11px] text-muted">{asset.mediaType === "image" ? "图片" : asset.mediaType === "audio" ? "音频" : "视频"} · {asset.processingStatus} · {asset.tags.slice(0, 2).join("、") || "内容待识别"}</small></span>
      <span className={`grid h-5 w-5 place-items-center rounded-full border ${selected ? "border-blue bg-blue text-white" : "border-line"}`}>{selected && <Check size={12} />}</span>
    </button>;
  })}</div>;
}

function BlankProjectModal() {
  const { closeProjectCreate, notify } = useUIStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  async function createBlank(event: React.FormEvent) {
    event.preventDefault(); setSubmitted(true);
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const workspace = await projectApi.create({ name: name.trim(), type: "空白项目", description: "", variant: "stage", scriptTitle: name.trim(), idempotencyKey: temporaryId("project-request") });
      useWorkspaceStore.getState().hydrate(workspace);
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["projects"] }), queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] })]);
      closeProjectCreate(); notify(`空白项目“${workspace.project.name}”已创建`); navigate(`/workspace/projects/${workspace.project.id}?start=blank`);
    } catch (error) { notify(error instanceof Error ? error.message : "创建项目失败", "error"); }
    finally { setBusy(false); }
  }

  const footer = <><button type="button" disabled={busy} onClick={closeProjectCreate} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text">取消</button><button form="blank-project-form" type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? <Loader2 size={14} className="animate-spin" /> : <FolderPlus size={14} />}{busy ? "正在创建…" : "创建空白项目"}</button></>;
  return <ModalFrame title="创建空白项目" description="填写项目名称即可创建，不预设脚本、分镜或素材。" busy={busy} onClose={closeProjectCreate} footer={footer}><form id="blank-project-form" onSubmit={createBlank}><ProjectNameField name={name} onChange={setName} submitted={submitted} /></form></ModalFrame>;
}

function ProjectCreationWizard({ intent }: { intent: Exclude<ProjectStartMethod, "blank"> }) {
  const { closeProjectCreate, notify } = useUIStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const copy = flowCopy[intent];
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(60);
  const [tone, setTone] = useState("专业克制");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [step, setStep] = useState<WizardStep>("input");
  const [units, setUnits] = useState<CreationUnit[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flowError, setFlowError] = useState("");
  const [previewSummary, setPreviewSummary] = useState("");
  const assetsQuery = useQuery({ queryKey: ["assets", "project-creation-picker"], queryFn: () => assetApi.listPage({ limit: 100 }), enabled: intent === "upload-assets", retry: false });
  const assets = useMemo(() => assetsQuery.data?.items ?? [], [assetsQuery.data?.items]);
  const selectedAssets = useMemo(() => assets.filter((asset) => selectedIds.has(asset.id)), [assets, selectedIds]);

  function toggleAsset(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else if (next.size >= 50) {
        notify("一次最多分析 50 个素材，请先取消部分选择", "error");
      } else next.add(id);
      return next;
    });
  }

  async function beginPreview(event: React.FormEvent) {
    event.preventDefault(); setSubmitted(true); setFlowError("");
    const hasVisualAsset = selectedAssets.some((asset) => asset.mediaType !== "audio");
    if (!name.trim() || (intent === "write-script" && script.trim().length < 10) || (intent === "ai-script" && prompt.trim().length < 10) || (intent === "upload-assets" && (!selectedAssets.length || !hasVisualAsset))) return;
    setStep("processing");
    try {
      let nextUnits: CreationUnit[];
      if (intent === "write-script") {
        nextUnits = recognizePastedScript(script);
        setPreviewSummary(`从粘贴脚本识别出 ${nextUnits.length} 个场景和分镜。`);
      } else {
        const preview = intent === "ai-script"
          ? await generateApi.createScriptPreview({ prompt: prompt.trim(), durationSeconds: duration, tone })
          : await generateApi.createAssetPreview({ assetIds: selectedAssets.map((asset) => asset.id) });
        nextUnits = creationPreviewToUnits(preview);
        setPreviewSummary(preview.summary);
      }
      if (!nextUnits.length) { setFlowError("未能识别出可用内容，请补充后重试"); setStep("input"); return; }
      setUnits(nextUnits); setStep("preview");
    } catch (error) {
      setFlowError(error instanceof Error ? error.message : "AI 预览生成失败，请稍后重试");
      setStep("input");
    }
  }

  async function confirmCreate() {
    if (busy || !units.length) return;
    setBusy(true); setFlowError("");
    try {
      const targetDuration = Math.round(units.reduce((sum, unit) => sum + unit.durationMs, 0) / 1_000);
      let workspace = await projectApi.create({ name: name.trim(), type: copy.projectType, description: intent === "ai-script" ? prompt.trim() : "", variant: copy.variant, scriptTitle: name.trim(), targetDurationSeconds: targetDuration, idempotencyKey: temporaryId("project-request") });
      if (intent === "upload-assets") {
        await Promise.all(selectedAssets.map((asset) => projectApi.linkAsset(workspace.project.id, asset.id)));
        workspace = await projectApi.getWorkspace(workspace.project.id);
      }
      const sourceType = intent === "write-script" ? "script" : intent === "ai-script" ? "ai" : "asset-analysis";
      const summary = previewSummary || (intent === "write-script" ? `从粘贴脚本识别出 ${units.length} 个场景和分镜。` : intent === "ai-script" ? `AI 根据创作描述生成 ${units.length} 个场景和分镜：${prompt.trim()}` : `AI 已分析 ${selectedAssets.length} 个素材并完成叙事编排。`);
      workspace = await projectApi.saveWorkspace(workspace.project.id, applyCreationUnits(workspace, units, sourceType, summary), "manual_save");
      useWorkspaceStore.getState().hydrate(workspace);
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["projects"] }), queryClient.invalidateQueries({ queryKey: ["assets"] }), queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] })]);
      closeProjectCreate(); notify(`项目“${workspace.project.name}”已创建，${units.length} 个场景已写入`); navigate(`/workspace/projects/${workspace.project.id}?start=${intent}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "创建项目失败，请稍后重试"; setFlowError(message); notify(message, "error");
    } finally { setBusy(false); }
  }

  const inputInvalid = intent === "write-script" ? submitted && script.trim().length < 10 : intent === "ai-script" ? submitted && prompt.trim().length < 10 : submitted && (!selectedAssets.length || !selectedAssets.some((asset) => asset.mediaType !== "audio"));
  const footer = step === "preview"
    ? <><button type="button" disabled={busy} onClick={() => setStep("input")} className="flex items-center gap-1 rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text"><ArrowLeft size={13} />返回修改</button><button type="button" disabled={busy} onClick={() => void confirmCreate()} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}{busy ? "正在创建项目…" : "确认并创建项目"}</button></>
    : <><button type="button" disabled={step === "processing"} onClick={closeProjectCreate} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button form="project-creation-flow" type="submit" disabled={step === "processing" || (intent === "upload-assets" && assetsQuery.isLoading)} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{step === "processing" ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}{step === "processing" ? copy.processing : copy.action}</button></>;

  return <ModalFrame title={copy.title} description={step === "preview" ? `已生成 ${units.length} 个场景，确认后才会创建项目。` : copy.description} busy={busy || step === "processing"} onClose={closeProjectCreate} footer={footer}>
    {step === "processing" ? <ProcessingState intent={intent} label={copy.processing} /> : step === "preview" ? <><div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-teal/20 bg-teal/5 p-3"><span className="flex items-center gap-2 text-xs font-medium text-teal"><Check size={15} />{intent === "upload-assets" ? `${selectedAssets.length} 个素材分析完成` : "脚本与分镜已生成"}</span><span className="text-[11px] text-muted">总时长约 {Math.round(units.reduce((sum, unit) => sum + unit.durationMs, 0) / 1_000)} 秒</span></div><ScriptPreview units={units} />{flowError && <p className="mt-3 rounded-lg bg-red/5 p-3 text-xs text-red">{flowError}</p>}</> :
      <form id="project-creation-flow" onSubmit={beginPreview} className="space-y-5">
        <ProjectNameField name={name} onChange={setName} submitted={submitted} />
        {intent === "write-script" && <ScriptInput script={script} setScript={setScript} invalid={inputInvalid} />}
        {intent === "ai-script" && <AiBriefInput prompt={prompt} setPrompt={setPrompt} duration={duration} setDuration={setDuration} tone={tone} setTone={setTone} invalid={inputInvalid} />}
        {intent === "upload-assets" && <AssetInput assetsQuery={assetsQuery} assets={assets} selectedAssets={selectedAssets} selectedIds={selectedIds} toggleAsset={toggleAsset} invalid={inputInvalid} />}
        {flowError && <p className="rounded-lg bg-red/5 p-3 text-xs text-red">{flowError}</p>}
      </form>}
  </ModalFrame>;
}

function ProcessingState({ intent, label }: { intent: Exclude<ProjectStartMethod, "blank">; label: string }) {
  return <div className="py-16 text-center"><span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-blue-soft text-blue"><Loader2 size={28} className="animate-spin" /></span><h3 className="mt-5 text-base font-semibold text-text">{label}</h3><p className="mx-auto mt-2 max-w-md text-xs leading-5 text-muted">{intent === "upload-assets" ? "正在理解画面、对白与素材标签，提取叙事线索并安排镜头顺序。" : "正在拆分叙事段落、估算时长并为每段生成画面意图。"}</p><div className="mx-auto mt-6 flex max-w-md items-center justify-center gap-2 text-[11px] text-muted"><span className="rounded-full bg-teal/10 px-3 py-1.5 text-teal">理解内容</span><span>→</span><span className="rounded-full bg-blue-soft px-3 py-1.5 text-blue">生成分镜</span><span>→</span><span className="rounded-full bg-canvas px-3 py-1.5">准备预览</span></div></div>;
}

function ScriptInput({ script, setScript, invalid }: { script: string; setScript: (value: string) => void; invalid: boolean }) {
  return <label className="block text-sm font-medium text-text">粘贴脚本或文案<textarea rows={10} value={script} onChange={(event) => setScript(event.target.value)} placeholder="粘贴文章、口播稿或视频脚本；可使用“画面：”标记分镜描述。" className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 text-text focus:ring-2 focus:ring-blue/10 ${invalid ? "border-red" : "border-line focus:border-blue/50"}`} /><span className="mt-1.5 flex justify-between text-[11px]"><button type="button" onClick={() => setScript(sampleScript)} className="font-medium text-blue">填入示例脚本</button><span className={invalid ? "text-red" : "text-muted"}>{invalid ? "请至少输入 10 个字符" : `${script.length} 个字符`}</span></span></label>;
}

function AiBriefInput({ prompt, setPrompt, duration, setDuration, tone, setTone, invalid }: { prompt: string; setPrompt: (value: string) => void; duration: number; setDuration: (value: number) => void; tone: string; setTone: (value: string) => void; invalid: boolean }) {
  return <><label className="block text-sm font-medium text-text">简单描述你想制作的视频<textarea rows={6} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：制作一支 60 秒新品发布短片，先建立使用场景，再突出三个核心能力，最后以品牌愿景收束。" className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 text-text focus:ring-2 focus:ring-blue/10 ${invalid ? "border-red" : "border-line focus:border-blue/50"}`} /><span className={`mt-1.5 block text-[11px] ${invalid ? "text-red" : "text-muted"}`}>{invalid ? "请至少输入 10 个字符" : "AI 会先生成可检查的脚本、旁白和画面意图"}</span></label><div className="grid gap-4 sm:grid-cols-2"><fieldset><legend className="text-xs font-semibold text-text">目标时长</legend><div className="mt-2 grid grid-cols-3 gap-2">{[30, 60, 90].map((value) => <button key={value} type="button" onClick={() => setDuration(value)} className={`rounded-lg border py-2 text-xs ${duration === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value} 秒</button>)}</div></fieldset><fieldset><legend className="text-xs font-semibold text-text">表达语气</legend><div className="mt-2 grid grid-cols-3 gap-2">{["专业克制", "科技感", "故事化"].map((value) => <button key={value} type="button" onClick={() => setTone(value)} className={`rounded-lg border px-1 py-2 text-xs ${tone === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value}</button>)}</div></fieldset></div></>;
}

type AssetPickerQuery = ReturnType<typeof useQuery<assetApi.AssetPage>>;
function AssetInput({ assetsQuery, assets, selectedAssets, selectedIds, toggleAsset, invalid }: { assetsQuery: AssetPickerQuery; assets: Asset[]; selectedAssets: Asset[]; selectedIds: Set<string>; toggleAsset: (id: string) => void; invalid: boolean }) {
  return <section><div className="mb-3 flex items-center justify-between"><div><h3 className="text-sm font-medium text-text">选择素材库影片</h3><p className="mt-1 text-xs text-muted">可多选图片、视频或音频；音频用于提供叙事上下文，至少需要一项图片或视频。</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${selectedAssets.length ? "bg-blue-soft text-blue" : "bg-canvas text-muted"}`}>已选 {selectedAssets.length} 项</span></div>{assetsQuery.isLoading ? <div className="py-16 text-center text-xs text-muted"><Loader2 size={18} className="mx-auto mb-2 animate-spin" />正在加载素材库…</div> : assetsQuery.isError ? <div className="rounded-xl bg-red/5 py-10 text-center text-xs text-red">素材库加载失败，请关闭后重试</div> : !assets.length ? <div className="rounded-xl border border-dashed border-line py-12 text-center"><Film size={22} className="mx-auto text-muted" /><p className="mt-2 text-xs font-medium text-text">素材库还没有可用素材</p><p className="mt-1 text-[11px] text-muted">请先关闭弹窗并上传素材。</p></div> : <AssetPicker assets={assets} selectedIds={selectedIds} onToggle={toggleAsset} />}{invalid && <p className="mt-2 text-xs text-red">请选择至少一项已处理完成的图片或视频；可同时选择音频作为内容参考。</p>}</section>;
}

function ProjectEditModal() {
  const { projectEditing, closeProjectCreate, notify } = useUIStore();
  const queryClient = useQueryClient();
  const [name, setName] = useState(projectEditing?.name ?? "");
  const [description, setDescription] = useState(projectEditing?.description ?? "");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setName(projectEditing?.name ?? ""); setDescription(projectEditing?.description ?? ""); }, [projectEditing]);
  if (!projectEditing) return null;
  async function save(event: React.FormEvent) {
    event.preventDefault(); setSubmitted(true); if (!name.trim() || busy || !projectEditing) return; setBusy(true);
    try { await projectApi.update(projectEditing.id, { name: name.trim(), description: description.trim() }); await queryClient.invalidateQueries({ queryKey: ["projects"] }); closeProjectCreate(); notify(`项目“${name.trim()}”已更新`); }
    catch (error) { notify(error instanceof Error ? error.message : "项目信息保存失败", "error"); }
    finally { setBusy(false); }
  }
  const footer = <><button type="button" disabled={busy} onClick={closeProjectCreate} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text">取消</button><button form="project-edit-form" type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy && <Loader2 size={14} className="animate-spin" />}{busy ? "正在保存…" : "保存修改"}</button></>;
  return <ModalFrame title="编辑项目信息" description="更新影片名称和项目说明。" busy={busy} onClose={closeProjectCreate} footer={footer}><form id="project-edit-form" onSubmit={save} className="space-y-5"><ProjectNameField name={name} onChange={setName} submitted={submitted} /><label className="block text-sm font-medium text-text">项目说明 <span className="font-normal text-muted">可选</span><textarea rows={5} maxLength={5000} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="说明内容目标、素材范围或制作要求" className="mt-2 w-full resize-y rounded-xl border border-line p-3 text-sm leading-6 text-text focus:border-blue/50 focus:ring-2 focus:ring-blue/10" /></label></form></ModalFrame>;
}

export function ProjectCreateModal() {
  const { projectCreateOpen, projectCreateIntent, projectEditing } = useUIStore();
  if (!projectCreateOpen) return null;
  if (projectEditing) return <ProjectEditModal />;
  if (projectCreateIntent === "blank") return <BlankProjectModal />;
  return <ProjectCreationWizard key={projectCreateIntent} intent={projectCreateIntent} />;
}

export default ProjectCreateModal;
