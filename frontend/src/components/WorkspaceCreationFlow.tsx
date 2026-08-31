import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  CheckCircle2,
  Clapperboard,
  Clock3,
  Copy,
  FileAudio,
  FileText,
  Film,
  Image as ImageIcon,
  Images,
  Loader2,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import * as assetApi from "@/api/assets";
import type { Asset } from "@/api/assets";
import * as generateApi from "@/api/generate";
import * as projectApi from "@/api/projects";
import type { AspectRatio, Workspace } from "@/api/projects";
import { useNavigate } from "@/router";
import {
  applyCreationUnits,
  creationPreviewToUnits,
  recognizePastedScript,
  type CreationUnit,
} from "@/lib/projectCreationFlow";
import {
  clearWorkspaceCreationDraft,
  createWorkspaceCreationDraft,
  deriveWorkspaceCreationTitle,
  hasWorkspaceCreationContent,
  loadWorkspaceCreationDraft,
  saveWorkspaceCreationDraft,
  type WorkspaceCreationDraft,
  type WorkspaceCreationSource,
  type WorkspaceProductionMode,
} from "@/lib/workspaceCreationDraft";
import { useUIStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { temporaryId } from "@/stores/workspaceTransforms";
import { VideoThumb } from "@/components/VideoThumb";

const sampleScript = `01 创作者有一份好文档，却常常卡在策划、分镜和剪辑之间。
画面：文档、素材目录和剪辑软件在桌面上来回切换。

02 OpenVMA 让脚本成为影片的控制台。
画面：一段文案被自动拆成场景、旁白和镜头说明。

03 修改文字，画面、声音和成片预览会一起更新。
画面：工作台中的脚本、分镜与成片预览同步变化。`;

const sourceMeta: Record<WorkspaceCreationSource, {
  label: string;
  shortLabel: string;
  description: string;
  icon: typeof Sparkles;
  projectType: string;
  variant: string;
}> = {
  "ai-script": {
    label: "描述想法，让 AI 起草脚本",
    shortLabel: "描述想法",
    description: "写下主题、受众和表达重点，先获得一份可以逐段修改的脚本草案。",
    icon: Sparkles,
    projectType: "AI 辅助脚本",
    variant: "robot",
  },
  "write-script": {
    label: "粘贴脚本或文案",
    shortLabel: "粘贴脚本",
    description: "导入文章、口播稿或视频脚本，先识别场景与镜头，再逐段确认。",
    icon: FileText,
    projectType: "脚本创作",
    variant: "stage",
  },
  "upload-assets": {
    label: "从已有素材整理故事",
    shortLabel: "选择素材",
    description: "选择图片、视频和音频，先分析内容并形成可编辑的叙事结构。",
    icon: Images,
    projectType: "素材编排",
    variant: "hall",
  },
};

const productionMeta: Record<WorkspaceProductionMode, {
  label: string;
  eyebrow: string;
  description: string;
  badge: string;
}> = {
  ai: {
    label: "AI 成片",
    eyebrow: "从 0 生成",
    description: "画面、旁白和音乐围绕已确认脚本继续生成。",
    badge: "最快完成",
  },
  hybrid: {
    label: "混合成片",
    eyebrow: "素材 + AI",
    description: "优先使用你的素材，缺少的画面再由 AI 补齐。",
    badge: "推荐",
  },
  owned: {
    label: "都用自有素材",
    eyebrow: "不生成画面",
    description: "只使用素材库内容，AI 负责理解、匹配和编排。",
    badge: "素材可控",
  },
};

const promptSuggestions = [
  "60 秒产品介绍",
  "面向第一次做视频的创作者",
  "先讲痛点，再展示解决方案",
  "专业克制，结尾有品牌愿景",
];

function formatSavedAt(value: Date | null) {
  if (!value) return "正在保存草稿";
  return `草稿已保存 · ${value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function CreationProgress({ stage }: { stage: WorkspaceCreationDraft["stage"] }) {
  const active = stage === "input" ? 0 : stage === "script" ? 1 : 2;
  const labels = ["整理内容", "确认脚本", "创作设置"];
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label="创建项目进度">
      {labels.map((label, index) => (
        <li key={label} className={`flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2.5 ${index === active ? "border-ink bg-ink text-white" : index < active ? "border-teal/25 bg-teal/5 text-teal" : "border-line bg-white text-muted"}`} aria-current={index === active ? "step" : undefined}>
          <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-semibold ${index === active ? "bg-white text-ink" : index < active ? "bg-teal text-white" : "bg-canvas text-muted"}`}>{index < active ? <Check size={11} /> : index + 1}</span>
          <strong className="truncate text-[11px] font-semibold sm:text-xs">{label}</strong>
        </li>
      ))}
    </ol>
  );
}

function AssetPicker({
  assets,
  selectedIds,
  onToggle,
  loading,
  error,
  onUpload,
}: {
  assets: Asset[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  loading: boolean;
  error: boolean;
  onUpload: () => void;
}) {
  const selected = new Set(selectedIds);
  if (loading) return <div className="grid min-h-40 place-items-center rounded-2xl border border-line bg-canvas/50 text-xs text-muted"><span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" />正在加载素材库…</span></div>;
  if (error) return <div className="rounded-2xl border border-red/20 bg-red/5 px-5 py-10 text-center text-xs text-red">素材库加载失败，请稍后重试。</div>;
  if (!assets.length) return (
    <div className="rounded-2xl border border-dashed border-line bg-canvas/40 px-5 py-10 text-center">
      <Images size={24} className="mx-auto text-muted" />
      <strong className="mt-3 block text-sm text-text">素材库还没有可用素材</strong>
      <p className="mt-1 text-xs text-muted">先上传图片、视频或音频，处理完成后即可在这里选择。</p>
      <button type="button" onClick={onUpload} className="workspace-secondary-button mt-4 !min-h-9 px-3 text-xs"><Upload size={14} />上传素材</button>
    </div>
  );
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
      {assets.map((asset) => {
        const active = selected.has(asset.id);
        const Icon = asset.mediaType === "image" ? ImageIcon : asset.mediaType === "audio" ? FileAudio : Film;
        const unavailable = asset.processingStatus !== "ready";
        return (
          <button key={asset.id} type="button" disabled={unavailable} aria-pressed={active} onClick={() => onToggle(asset.id)} className={`grid min-h-[86px] grid-cols-[62px_minmax(0,1fr)_22px] items-center gap-3 overflow-hidden rounded-xl border p-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-45 ${active ? "border-ink bg-blue-soft ring-1 ring-black/5" : "border-line bg-white hover:border-[#c4c4c8]"}`}>
            <span className="relative grid h-[62px] w-[62px] place-items-center overflow-hidden rounded-lg bg-canvas text-muted">
              {asset.mediaType !== "audio" && (asset.thumbnailUrl || asset.mediaUrl)
                ? <VideoThumb fill imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={false} />
                : <Icon size={20} />}
            </span>
            <span className="min-w-0"><strong className="block truncate text-xs text-text">{asset.name}</strong><small className="mt-1 block truncate text-[10px] text-muted">{asset.mediaType === "image" ? "图片" : asset.mediaType === "audio" ? "音频" : "视频"} · {asset.processingStatus}</small><small className="mt-1 block truncate text-[10px] text-muted">{asset.tags.slice(0, 2).join("、") || "内容待识别"}</small></span>
            <span className={`grid h-5 w-5 place-items-center rounded-full border ${active ? "border-ink bg-ink text-white" : "border-line bg-white"}`}>{active && <Check size={11} />}</span>
          </button>
        );
      })}
    </div>
  );
}

function ChoiceGroup({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <fieldset>
      <legend className="text-xs font-semibold text-text">{label}</legend>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        {options.map((option) => <button key={option} type="button" onClick={() => onChange(option)} className={`rounded-xl border px-3 py-2.5 text-xs transition ${value === option ? "border-ink bg-ink font-semibold text-white" : "border-line bg-white text-muted hover:border-[#c5c5c8] hover:text-text"}`}>{option}</button>)}
      </div>
    </fieldset>
  );
}

function sourceTitle(source: WorkspaceCreationSource) {
  return sourceMeta[source].shortLabel;
}

export function WorkspaceCreationFlow({
  initialSource,
  onSourceChange,
  onExit,
  previewAssets,
}: {
  initialSource: WorkspaceCreationSource;
  onSourceChange: (source: WorkspaceCreationSource) => void;
  onExit: () => void;
  previewAssets?: Asset[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify, openUploadDrawer } = useUIStore();
  const [restoredDraft] = useState<WorkspaceCreationDraft | null>(() => loadWorkspaceCreationDraft());
  const [draft, setDraft] = useState<WorkspaceCreationDraft>(() => {
    const restored = restoredDraft;
    return restored && restored.source === initialSource ? restored : createWorkspaceCreationDraft(initialSource);
  });
  const [processing, setProcessing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(() => restoredDraft ? new Date(restoredDraft.updatedAt) : null);

  const assetsQuery = useQuery({
    queryKey: ["assets", "workspace-creation-picker"],
    queryFn: () => assetApi.listPage({ limit: 100 }),
    enabled: !previewAssets,
    retry: false,
  });
  const assets = useMemo(() => previewAssets ?? assetsQuery.data?.items ?? [], [assetsQuery.data?.items, previewAssets]);
  const selectedAssets = useMemo(() => assets.filter((asset) => draft.selectedAssetIds.includes(asset.id)), [assets, draft.selectedAssetIds]);
  const totalDurationMs = useMemo(() => draft.units.reduce((sum, unit) => sum + unit.durationMs, 0), [draft.units]);
  const productionNeedsAssets = draft.productionMode === "hybrid" || draft.productionMode === "owned";
  const hasVisualAsset = selectedAssets.some((asset) => asset.mediaType !== "audio" && asset.processingStatus === "ready");
  const restored = Boolean(restoredDraft && restoredDraft.source === initialSource && hasWorkspaceCreationContent(restoredDraft));

  useEffect(() => {
    const timer = window.setTimeout(() => {
      saveWorkspaceCreationDraft(draft);
      setLastSavedAt(new Date());
    }, 260);
    return () => window.clearTimeout(timer);
  }, [draft]);

  useEffect(() => {
    if (draft.source === initialSource) return;
    setDraft(createWorkspaceCreationDraft(initialSource));
    setSubmitted(false);
    setError("");
  }, [draft.source, initialSource]);

  function patchDraft(patch: Partial<WorkspaceCreationDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function returnToStage(stage: "input" | "script") {
    patchDraft({ stage });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function selectSource(source: WorkspaceCreationSource) {
    if (source === draft.source) return;
    if (draft.units.length && !window.confirm("切换开始方式会清除当前生成的脚本结构，原始输入仍会保留。确认切换？")) return;
    setDraft((current) => ({
      ...createWorkspaceCreationDraft(source),
      prompt: current.prompt,
      pastedScript: current.pastedScript,
      selectedAssetIds: current.selectedAssetIds,
    }));
    onSourceChange(source);
    setSubmitted(false);
    setError("");
  }

  function toggleAsset(id: string) {
    setDraft((current) => {
      const selected = new Set(current.selectedAssetIds);
      if (selected.has(id)) selected.delete(id);
      else if (selected.size >= 50) {
        notify("一次最多选择 50 个素材", "error");
        return current;
      } else selected.add(id);
      return { ...current, selectedAssetIds: Array.from(selected) };
    });
  }

  function inputError() {
    if (draft.source === "ai-script" && draft.prompt.trim().length < 10) return "请至少用 10 个字符描述想制作的视频。";
    if (draft.source === "write-script" && draft.pastedScript.trim().length < 10) return "请至少粘贴 10 个字符的脚本或文案。";
    if (draft.source === "upload-assets" && !selectedAssets.length) return "请先选择至少一个素材。";
    if (draft.source === "upload-assets" && !hasVisualAsset) return "至少需要一项已处理完成的图片或视频；音频可以同时作为内容参考。";
    return "";
  }

  async function generatePreview({ replacing = false }: { replacing?: boolean } = {}) {
    setSubmitted(true);
    const validation = inputError();
    if (validation) { setError(validation); return; }
    if (replacing && draft.manuallyEdited && !window.confirm("重新生成会覆盖你对脚本草稿的手工修改。确认继续？")) return;
    setProcessing(true);
    setError("");
    try {
      let units: CreationUnit[];
      let title = "";
      let summary = "";
      if (draft.source === "write-script") {
        units = recognizePastedScript(draft.pastedScript);
        title = deriveWorkspaceCreationTitle(units, "脚本创作项目");
        summary = `从粘贴脚本识别出 ${units.length} 个场景和分镜。`;
      } else {
        const preview = draft.source === "ai-script"
          ? await generateApi.createScriptPreview({ prompt: draft.prompt.trim(), durationSeconds: draft.durationSeconds, tone: draft.tone })
          : await generateApi.createAssetPreview({ assetIds: selectedAssets.map((asset) => asset.id), brief: draft.prompt.trim() || undefined });
        units = creationPreviewToUnits(preview);
        title = preview.title.trim() || deriveWorkspaceCreationTitle(units);
        summary = preview.summary;
      }
      if (!units.length) throw new Error("未能识别出可用内容，请补充信息后重试。");
      setDraft((current) => ({
        ...current,
        stage: "script",
        units,
        previewTitle: title,
        projectName: current.projectName.trim() ? current.projectName : title,
        previewSummary: summary,
        manuallyEdited: false,
      }));
      setSubmitted(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "脚本草稿生成失败，请稍后重试。");
    } finally {
      setProcessing(false);
    }
  }

  function updateUnit(index: number, patch: Partial<CreationUnit>) {
    setDraft((current) => ({
      ...current,
      manuallyEdited: true,
      units: current.units.map((unit, unitIndex) => unitIndex === index ? { ...unit, ...patch } : unit),
    }));
  }

  function updateShot(index: number, shotIndex: number, patch: Partial<CreationUnit["shots"][number]>) {
    setDraft((current) => ({
      ...current,
      manuallyEdited: true,
      units: current.units.map((unit, unitIndex) => unitIndex === index ? {
        ...unit,
        shots: unit.shots.map((shot, currentShotIndex) => currentShotIndex === shotIndex ? { ...shot, ...patch } : shot),
      } : unit),
    }));
  }

  function moveUnit(index: number, direction: -1 | 1) {
    setDraft((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.units.length) return current;
      const units = [...current.units];
      [units[index], units[target]] = [units[target], units[index]];
      return { ...current, units, manuallyEdited: true };
    });
  }

  function duplicateUnit(index: number) {
    setDraft((current) => {
      const source = current.units[index];
      const duplicate = { ...source, title: `${source.title}副本`, shots: source.shots.map((shot) => ({ ...shot })) };
      const units = [...current.units];
      units.splice(index + 1, 0, duplicate);
      return { ...current, units, manuallyEdited: true };
    });
  }

  function removeUnit(index: number) {
    setDraft((current) => ({ ...current, units: current.units.filter((_, unitIndex) => unitIndex !== index), manuallyEdited: true }));
  }

  function addUnit() {
    const nextIndex = draft.units.length + 1;
    const unit: CreationUnit = {
      title: `段落 ${nextIndex}`,
      narration: "",
      visual: "",
      durationMs: 8_000,
      shots: [{ description: "", durationMs: 8_000 }],
    };
    setDraft((current) => ({ ...current, units: [...current.units, unit], manuallyEdited: true }));
  }

  function confirmScript() {
    if (!draft.units.length) { setError("脚本至少需要一个段落。"); return; }
    if (draft.units.some((unit) => !unit.title.trim() || !unit.narration.trim() || !unit.visual.trim())) {
      setError("请补齐每个段落的标题、旁白和画面意图后再继续。");
      return;
    }
    setError("");
    patchDraft({ stage: "settings", projectName: draft.projectName.trim() || draft.previewTitle.trim() || deriveWorkspaceCreationTitle(draft.units) });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function applyProductionSettings(workspace: Workspace): Workspace {
    const next = applyCreationUnits(
      workspace,
      draft.units,
      draft.source === "write-script" ? "script" : draft.source === "ai-script" ? "ai" : "asset-analysis",
      draft.previewSummary || `${sourceTitle(draft.source)}生成 ${draft.units.length} 个场景。`,
    );
    return {
      ...next,
      document: {
        ...next.document,
        settings: {
          ...next.document.settings,
          title: draft.projectName.trim(),
          aspectRatio: draft.aspectRatio,
          visualConfig: {
            ...next.document.settings.visualConfig,
            productionMode: draft.productionMode,
            productionModeLabel: productionMeta[draft.productionMode].label,
            visualStyle: draft.visualStyle,
            narrationMode: draft.narrationMode,
            aiCoverage: draft.aiCoverage,
            materialPriority: draft.materialPriority,
            ownedArrangement: draft.ownedArrangement,
            gapStrategy: draft.gapStrategy,
          },
        },
      },
    };
  }

  async function createProject() {
    if (creating) return;
    if (!draft.projectName.trim()) { setError("请填写项目名称。"); return; }
    if (productionNeedsAssets && !hasVisualAsset) { setError("当前创作方式至少需要一项已处理完成的图片或视频。"); return; }
    setCreating(true);
    setError("");
    try {
      const meta = sourceMeta[draft.source];
      const targetDurationSeconds = Math.round(totalDurationMs / 1_000);
      let workspace = await projectApi.create({
        name: draft.projectName.trim(),
        type: meta.projectType,
        description: draft.prompt.trim() || draft.previewSummary,
        variant: meta.variant,
        scriptTitle: draft.previewTitle.trim() || draft.projectName.trim(),
        aspectRatio: draft.aspectRatio,
        targetDurationSeconds,
        idempotencyKey: temporaryId("workspace-creation"),
      });
      if (selectedAssets.length) {
        await Promise.all(selectedAssets.map((asset) => projectApi.linkAsset(workspace.project.id, asset.id)));
        workspace = await projectApi.getWorkspace(workspace.project.id);
      }
      workspace = await projectApi.saveWorkspace(workspace.project.id, applyProductionSettings(workspace), "manual_save");
      useWorkspaceStore.getState().hydrate(workspace);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
        queryClient.invalidateQueries({ queryKey: ["assets"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
      ]);
      clearWorkspaceCreationDraft();
      notify(`项目“${workspace.project.name}”已创建，${draft.units.length} 个场景已写入`);
      navigate(`/workspace/projects/${workspace.project.id}?start=${draft.source}`);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "创建项目失败，请稍后重试。";
      setError(message);
      notify(message, "error");
    } finally {
      setCreating(false);
    }
  }

  function discardDraft() {
    if (hasWorkspaceCreationContent(draft) && !window.confirm("确认清除当前创建草稿？原始输入、脚本修改和创作设置都会被删除。")) return;
    clearWorkspaceCreationDraft();
    onExit();
  }

  const validationMessage = submitted ? inputError() : "";

  return (
    <section aria-labelledby="workspace-creation-title">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-4xl">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-soft px-2.5 py-1 text-[11px] font-semibold text-text"><Sparkles size={12} />创建前草稿</span>
          <h1 id="workspace-creation-title" className="mt-3 text-[32px] font-semibold leading-tight tracking-[-0.045em] text-text sm:text-[38px]">{draft.stage === "input" ? "先把内容整理好，再创建项目。" : draft.stage === "script" ? "先确认要说什么，再决定怎么拍。" : "脚本已经清楚，现在决定怎么完成。"}</h1>
          <p className="mt-2.5 max-w-3xl text-sm leading-6 text-muted">{draft.stage === "input" ? "这里的内容仍是草稿，不会占用项目数量。生成结构后可以逐段修改，最后一步才会正式创建项目。" : draft.stage === "script" ? "标题、旁白、画面意图和镜头描述都可以直接调整；所有修改会带入最终项目。" : "选择成片方式、素材与基础设置，确认后创建项目并进入同一个脚本编排工作台。"}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-[11px] text-muted"><Save size={13} />{formatSavedAt(lastSavedAt)}</span>
          <button type="button" onClick={onExit} className="workspace-secondary-button !min-h-9 px-3 text-xs"><X size={14} />退出创作</button>
        </div>
      </header>

      {restored && <div className="mt-5 flex items-center gap-2 rounded-xl border border-teal/20 bg-teal/5 px-4 py-3 text-xs text-teal"><CheckCircle2 size={15} />已恢复上次未完成的创建草稿，可以从当前步骤继续。</div>}

      <div className="mt-6"><CreationProgress stage={draft.stage} /></div>

      {draft.stage === "input" && (
        <div className="mt-5 overflow-hidden rounded-2xl border border-line bg-white shadow-[0_18px_50px_rgba(0,0,0,.05)]">
          <div className="grid gap-2 border-b border-line bg-canvas/50 p-3 md:grid-cols-3">
            {(Object.keys(sourceMeta) as WorkspaceCreationSource[]).map((source) => {
              const meta = sourceMeta[source];
              const Icon = meta.icon;
              const selected = draft.source === source;
              return <button key={source} type="button" onClick={() => selectSource(source)} aria-pressed={selected} className={`flex items-start gap-3 rounded-xl border p-3.5 text-left transition ${selected ? "border-ink bg-white shadow-sm" : "border-transparent text-muted hover:border-line hover:bg-white/70"}`}><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${selected ? "bg-ink text-white" : "bg-white text-muted"}`}><Icon size={17} /></span><span><strong className={`block text-xs ${selected ? "text-text" : "text-muted"}`}>{meta.shortLabel}</strong><small className="mt-1 block text-[10px] leading-4 text-muted">{meta.description}</small></span></button>;
            })}
          </div>

          <div className="p-5 sm:p-6 lg:p-7">
            <div className="mb-5"><h2 className="text-lg font-semibold tracking-[-0.02em] text-text">{sourceMeta[draft.source].label}</h2><p className="mt-1 text-xs leading-5 text-muted">{sourceMeta[draft.source].description}</p></div>

            {draft.source === "ai-script" && <div className="space-y-5">
              <label className="block"><span className="text-xs font-semibold text-text">告诉 AI 你想制作什么</span><textarea autoFocus rows={7} value={draft.prompt} onChange={(event) => patchDraft({ prompt: event.target.value })} placeholder="例如：制作一支 60 秒的 OpenVMA 产品介绍视频，先说明创作者从文档开始的痛点，再展示 AI 生成脚本、分镜和成片预览，最后以品牌愿景收束。" className={`mt-2 w-full resize-y rounded-2xl border bg-[#fcfcfd] p-4 text-sm leading-6 text-text transition focus:bg-white focus:ring-2 focus:ring-black/5 ${validationMessage ? "border-red" : "border-line focus:border-ink/40"}`} /></label>
              <div><span className="text-[11px] font-medium text-muted">快速补充</span><div className="mt-2 flex flex-wrap gap-2">{promptSuggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => patchDraft({ prompt: draft.prompt.trim() ? `${draft.prompt.trim()}；${suggestion}` : suggestion })} className="rounded-full border border-line bg-white px-3 py-1.5 text-[10px] text-muted transition hover:border-ink/30 hover:text-text">＋ {suggestion}</button>)}</div></div>
              <div className="grid gap-5 sm:grid-cols-2"><ChoiceGroup label="目标时长" value={`${draft.durationSeconds} 秒`} options={["30 秒", "60 秒", "90 秒"]} onChange={(value) => patchDraft({ durationSeconds: Number.parseInt(value, 10) })} /><ChoiceGroup label="表达语气" value={draft.tone} options={["专业克制", "科技感", "故事化"]} onChange={(tone) => patchDraft({ tone })} /></div>
            </div>}

            {draft.source === "write-script" && <div>
              <label className="block"><span className="text-xs font-semibold text-text">脚本、文章或口播文案</span><textarea autoFocus rows={13} value={draft.pastedScript} onChange={(event) => patchDraft({ pastedScript: event.target.value })} placeholder="粘贴文章、口播稿或视频脚本；可以使用“画面：”标记画面意图。" className={`mt-2 w-full resize-y rounded-2xl border bg-[#fcfcfd] p-4 text-sm leading-7 text-text transition focus:bg-white focus:ring-2 focus:ring-black/5 ${validationMessage ? "border-red" : "border-line focus:border-ink/40"}`} /></label>
              <div className="mt-2 flex items-center justify-between gap-3 text-[11px]"><button type="button" onClick={() => patchDraft({ pastedScript: sampleScript })} className="font-semibold text-text underline decoration-line underline-offset-4">填入示例脚本</button><span className="text-muted">{draft.pastedScript.length} 个字符</span></div>
            </div>}

            {draft.source === "upload-assets" && <div className="space-y-5">
              <label className="block"><span className="text-xs font-semibold text-text">希望素材讲述什么 <em className="font-normal not-italic text-muted">可选</em></span><textarea rows={4} value={draft.prompt} onChange={(event) => patchDraft({ prompt: event.target.value })} placeholder="例如：围绕新品发布会，突出产品亮相、三个核心能力和现场互动。" className="mt-2 w-full resize-y rounded-xl border border-line bg-[#fcfcfd] p-3.5 text-sm leading-6 text-text focus:border-ink/40 focus:bg-white focus:ring-2 focus:ring-black/5" /></label>
              <div className="flex items-end justify-between gap-3"><div><strong className="text-xs text-text">选择素材库内容</strong><p className="mt-1 text-[11px] text-muted">已选 {selectedAssets.length} 项，至少需要一项图片或视频。</p></div><button type="button" onClick={() => openUploadDrawer(null)} className="workspace-secondary-button !min-h-9 px-3 text-xs"><Upload size={14} />上传新素材</button></div>
              <AssetPicker assets={assets} selectedIds={draft.selectedAssetIds} onToggle={toggleAsset} loading={!previewAssets && assetsQuery.isLoading} error={!previewAssets && assetsQuery.isError} onUpload={() => openUploadDrawer(null)} />
            </div>}

            {(error || validationMessage) && <p className="mt-4 rounded-xl border border-red/15 bg-red/5 px-4 py-3 text-xs text-red">{error || validationMessage}</p>}

            <footer className="mt-6 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
              <button type="button" onClick={discardDraft} className="self-start text-xs font-medium text-muted underline decoration-line underline-offset-4 hover:text-red">清除草稿</button>
              <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center"><span className="text-[11px] text-muted">先生成并编辑脚本，确认后才会创建项目</span><button type="button" disabled={processing || assetsQuery.isLoading && draft.source === "upload-assets"} onClick={() => void generatePreview()} className="workspace-primary-button !min-h-10 px-4 text-xs">{processing ? <Loader2 size={15} className="animate-spin" /> : <WandSparkles size={15} />}{processing ? "正在整理内容…" : draft.source === "write-script" ? "识别脚本结构" : draft.source === "upload-assets" ? "分析素材并生成结构" : "生成脚本草案"}</button></div>
            </footer>
          </div>
        </div>
      )}

      {draft.stage === "script" && (
        <div className="mt-5 overflow-hidden rounded-2xl border border-line bg-white shadow-[0_18px_50px_rgba(0,0,0,.05)]">
          <header className="border-b border-line px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <label className="min-w-0 flex-1"><span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">脚本标题</span><textarea rows={2} maxLength={200} value={draft.previewTitle} onChange={(event) => setDraft((current) => ({ ...current, previewTitle: event.target.value, projectName: current.projectName === current.previewTitle ? event.target.value : current.projectName, manuallyEdited: true }))} className="mt-1 block w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-xl font-semibold leading-[1.35] tracking-[-0.035em] text-text sm:text-[23px]" /></label>
              <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted"><span className="flex items-center gap-1"><Clock3 size={13} />约 {Math.round(totalDurationMs / 1_000)} 秒</span><span>{draft.units.length} 个段落</span></div>
            </div>
            <p className="mt-2 text-xs text-muted">逐段检查旁白与画面意图；镜头描述会直接写入项目的脚本编排工作台。</p>
          </header>

          <div className="divide-y divide-line">
            {draft.units.map((unit, index) => (
              <article key={`${index}-${unit.title}`} className="p-4 sm:p-5">
                <div className="grid gap-4 xl:grid-cols-[86px_minmax(0,1.25fr)_minmax(260px,.9fr)]">
                  <div className="flex items-start justify-between xl:block"><div><span className="font-mono text-[10px] text-muted">{String(index + 1).padStart(2, "0")}</span><strong className="mt-1 block text-xs text-text">段落</strong></div><div className="flex gap-1 xl:mt-4"><button type="button" disabled={index === 0} onClick={() => moveUnit(index, -1)} aria-label={`上移第 ${index + 1} 段`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-canvas disabled:opacity-25"><ArrowUp size={13} /></button><button type="button" disabled={index === draft.units.length - 1} onClick={() => moveUnit(index, 1)} aria-label={`下移第 ${index + 1} 段`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-canvas disabled:opacity-25"><ArrowDown size={13} /></button><button type="button" onClick={() => duplicateUnit(index)} aria-label={`复制第 ${index + 1} 段`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-canvas"><Copy size={13} /></button><button type="button" disabled={draft.units.length <= 1} onClick={() => removeUnit(index)} aria-label={`删除第 ${index + 1} 段`} className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-red/5 hover:text-red disabled:opacity-25"><Trash2 size={13} /></button></div></div>
                  <div className="space-y-3">
                    <label className="block"><span className="text-[10px] font-medium text-muted">段落标题</span><input value={unit.title} onChange={(event) => updateUnit(index, { title: event.target.value })} className="mt-1 w-full rounded-lg border border-line bg-[#fcfcfd] px-3 py-2 text-xs font-semibold text-text focus:border-ink/40 focus:bg-white" /></label>
                    <label className="block"><span className="text-[10px] font-medium text-muted">旁白 / 文案</span><textarea rows={4} value={unit.narration} onChange={(event) => updateUnit(index, { narration: event.target.value })} className="mt-1 w-full resize-y rounded-lg border border-line bg-[#fcfcfd] px-3 py-2.5 text-xs leading-5 text-text focus:border-ink/40 focus:bg-white" /></label>
                  </div>
                  <div className="space-y-3">
                    <label className="block"><span className="text-[10px] font-medium text-muted">画面意图</span><textarea rows={3} value={unit.visual} onChange={(event) => updateUnit(index, { visual: event.target.value })} className="mt-1 w-full resize-y rounded-lg border border-line bg-[#fcfcfd] px-3 py-2.5 text-xs leading-5 text-text focus:border-ink/40 focus:bg-white" /></label>
                    <label className="block"><span className="text-[10px] font-medium text-muted">段落时长</span><span className="mt-1 flex items-center gap-2"><input type="number" min={1} max={300} value={Math.max(1, Math.round(unit.durationMs / 1_000))} onChange={(event) => updateUnit(index, { durationMs: Math.max(1, Number(event.target.value) || 1) * 1_000 })} className="w-24 rounded-lg border border-line bg-[#fcfcfd] px-3 py-2 text-xs text-text focus:border-ink/40" /><small className="text-[10px] text-muted">秒</small></span></label>
                  </div>
                </div>
                <details className="mt-4 rounded-xl border border-line bg-canvas/35 px-3 py-2.5" open={unit.shots.length <= 2}><summary className="cursor-pointer text-[10px] font-semibold text-muted">镜头描述 · {unit.shots.length || 0} 个镜头</summary><div className="mt-3 space-y-2">{unit.shots.length ? unit.shots.map((shot, shotIndex) => <div key={shotIndex} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_100px]"><input value={shot.description} onChange={(event) => updateShot(index, shotIndex, { description: event.target.value })} placeholder={`镜头 ${shotIndex + 1} 描述`} className="rounded-lg border border-line bg-white px-3 py-2 text-[11px] text-text focus:border-ink/40" /><label className="flex items-center gap-1 rounded-lg border border-line bg-white px-2"><input type="number" min={1} max={300} value={Math.max(1, Math.round(shot.durationMs / 1_000))} onChange={(event) => updateShot(index, shotIndex, { durationMs: Math.max(1, Number(event.target.value) || 1) * 1_000 })} className="min-w-0 flex-1 bg-transparent text-[11px] text-text" /><small className="text-[9px] text-muted">秒</small></label></div>) : <p className="text-[10px] text-muted">当前段落还没有镜头描述，创建项目后可在脚本编排中继续添加。</p>}</div></details>
              </article>
            ))}
          </div>

          <div className="border-t border-line px-5 py-4"><button type="button" onClick={addUnit} className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line py-3 text-xs font-medium text-muted transition hover:border-ink/30 hover:text-text"><Plus size={14} />添加一个段落</button></div>
          {error && <p className="mx-5 mb-4 rounded-xl border border-red/15 bg-red/5 px-4 py-3 text-xs text-red sm:mx-6">{error}</p>}
          <footer className="flex flex-col gap-3 border-t border-line bg-canvas/45 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <button type="button" onClick={() => returnToStage("input")} className="workspace-secondary-button !min-h-10 px-4 text-xs"><ArrowLeft size={14} />修改原始内容</button>
            <div className="flex flex-col gap-2 sm:flex-row"><button type="button" disabled={processing} onClick={() => void generatePreview({ replacing: true })} className="workspace-secondary-button !min-h-10 px-4 text-xs">{processing ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}重新生成</button><button type="button" onClick={confirmScript} className="workspace-primary-button !min-h-10 px-4 text-xs">确认脚本，选择创作方式<ArrowRight size={14} /></button></div>
          </footer>
        </div>
      )}

      {draft.stage === "settings" && (
        <div className="mt-5 space-y-5">
          <section className="rounded-2xl border border-line bg-white p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3"><div><h2 className="text-lg font-semibold text-text">选择创作方式</h2><p className="mt-1 text-xs leading-5 text-muted">脚本已经确认，接下来决定素材来源和生成范围。</p></div><span className="rounded-full bg-teal/10 px-2.5 py-1 text-[10px] font-semibold text-teal">{draft.units.length} 个段落 · 约 {Math.round(totalDurationMs / 1_000)} 秒</span></div>
            <div className="mt-5 grid gap-3 lg:grid-cols-3">{(Object.keys(productionMeta) as WorkspaceProductionMode[]).map((mode) => { const meta = productionMeta[mode]; const selected = draft.productionMode === mode; return <button key={mode} type="button" role="radio" aria-checked={selected} onClick={() => patchDraft({ productionMode: mode })} className={`relative min-h-[150px] rounded-2xl border p-4 text-left transition ${selected ? "border-ink bg-ink text-white shadow-lg" : "border-line bg-white text-text hover:border-[#bfc0c4]"}`}><small className={`text-[10px] font-semibold ${selected ? "text-white/55" : "text-muted"}`}>{meta.eyebrow}</small><strong className="mt-3 block text-lg">{meta.label}</strong><p className={`mt-2 text-xs leading-5 ${selected ? "text-white/65" : "text-muted"}`}>{meta.description}</p><span className={`absolute right-3 top-3 rounded-full px-2 py-1 text-[9px] font-semibold ${selected ? "bg-white/12 text-white" : "bg-canvas text-muted"}`}>{meta.badge}</span>{selected && <span className="absolute bottom-3 right-3 grid h-6 w-6 place-items-center rounded-full bg-white text-ink"><Check size={13} /></span>}</button>; })}</div>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 sm:p-6">
            <h2 className="text-lg font-semibold text-text">项目与成片设置</h2>
            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              <label className="block"><span className="text-xs font-semibold text-text">项目名称</span><input value={draft.projectName} maxLength={200} onChange={(event) => patchDraft({ projectName: event.target.value })} placeholder="自动从脚本标题生成，可继续修改" className="mt-2 w-full rounded-xl border border-line bg-[#fcfcfd] px-3.5 py-2.5 text-sm text-text focus:border-ink/40 focus:bg-white focus:ring-2 focus:ring-black/5" /></label>
              <ChoiceGroup label="成片画幅" value={draft.aspectRatio} options={["16:9", "9:16", "1:1"]} onChange={(value) => patchDraft({ aspectRatio: value as AspectRatio })} />
            </div>
            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              {draft.productionMode === "ai" && <><ChoiceGroup label="视觉风格" value={draft.visualStyle} options={["电影写实", "品牌商业", "插画动效"]} onChange={(visualStyle) => patchDraft({ visualStyle })} /><ChoiceGroup label="旁白方式" value={draft.narrationMode} options={["AI 自然旁白", "仅字幕", "无旁白"]} onChange={(narrationMode) => patchDraft({ narrationMode })} /></>}
              {draft.productionMode === "hybrid" && <><ChoiceGroup label="AI 补画比例" value={draft.aiCoverage} options={["少量补充", "均衡补充", "充分补充"]} onChange={(aiCoverage) => patchDraft({ aiCoverage })} /><ChoiceGroup label="素材使用策略" value={draft.materialPriority} options={["自有素材优先", "画面质量优先", "叙事完整优先"]} onChange={(materialPriority) => patchDraft({ materialPriority })} /></>}
              {draft.productionMode === "owned" && <><ChoiceGroup label="智能编排方式" value={draft.ownedArrangement} options={["按脚本匹配", "按素材微调脚本", "保留拍摄顺序"]} onChange={(ownedArrangement) => patchDraft({ ownedArrangement })} /><ChoiceGroup label="素材不足时" value={draft.gapStrategy} options={["保留缺口待补", "智能裁切与复用", "文字与图形包装"]} onChange={(gapStrategy) => patchDraft({ gapStrategy })} /></>}
            </div>
          </section>

          {productionNeedsAssets && <section className="rounded-2xl border border-line bg-white p-5 sm:p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-lg font-semibold text-text">选择自有素材</h2><p className="mt-1 text-xs text-muted">当前方式需要至少一项已处理完成的图片或视频；已选 {selectedAssets.length} 项。</p></div><button type="button" onClick={() => openUploadDrawer(null)} className="workspace-secondary-button !min-h-9 px-3 text-xs"><Upload size={14} />上传素材</button></div><div className="mt-4"><AssetPicker assets={assets} selectedIds={draft.selectedAssetIds} onToggle={toggleAsset} loading={!previewAssets && assetsQuery.isLoading} error={!previewAssets && assetsQuery.isError} onUpload={() => openUploadDrawer(null)} /></div></section>}

          {error && <p className="rounded-xl border border-red/15 bg-red/5 px-4 py-3 text-xs text-red">{error}</p>}
          <footer className="sticky bottom-3 z-10 flex flex-col gap-3 rounded-2xl border border-line bg-white/95 p-3.5 shadow-[0_18px_55px_rgba(0,0,0,.12)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
            <button type="button" disabled={creating} onClick={() => returnToStage("script")} className="workspace-secondary-button !min-h-10 px-4 text-xs"><ArrowLeft size={14} />返回脚本</button>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center"><span className="text-[11px] text-muted">点击后才会正式创建项目并写入脚本</span><button type="button" disabled={creating || assetsQuery.isLoading && productionNeedsAssets} onClick={() => void createProject()} className="workspace-primary-button !min-h-10 px-4 text-xs">{creating ? <Loader2 size={15} className="animate-spin" /> : <Clapperboard size={15} />}{creating ? "正在创建项目…" : "创建项目并进入脚本编排"}</button></div>
          </footer>
        </div>
      )}
    </section>
  );
}

export default WorkspaceCreationFlow;
