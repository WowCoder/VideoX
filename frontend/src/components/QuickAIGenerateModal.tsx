import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Film,
  Image as ImageIcon,
  Layers3,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { estimateProjectOperation, type OperationEstimate, type OperationScope, type ProjectOperation } from "@/api/generate";
import type { Asset } from "@/api/assets";
import type { Scene, Shot } from "@/api/projects";
import { Select } from "@/components/ui/Select";
import { VideoThumb } from "@/components/VideoThumb";

export type GenerationKind = "image" | "video";
type ScopeKind = "project" | "scene" | "shot";
type VideoGenerationMode = "text" | "keyframe" | "reference";

interface Props {
  open: boolean;
  projectName: string;
  projectId: string;
  expectedRevision: number;
  scenes: Scene[];
  assets: Asset[];
  selectedScene?: Scene;
  selectedShot?: Shot;
  initialKind?: GenerationKind;
  initialScope?: ScopeKind;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onGenerate: (operation: ProjectOperation, scope: OperationScope, parameters: Record<string, unknown>, pricingCatalogId?: string) => void;
}

const generationTypes = [
  { id: "image", label: "AI 图片", copy: "为镜头生成可继续编辑的分镜图", icon: ImageIcon },
  { id: "video", label: "AI 视频", copy: "从文字或当前分镜生成动态画面", icon: Film },
] as const;

function scopeDescription(scope: ScopeKind, scene?: Scene, shot?: Shot) {
  if (scope === "project") return "项目中的全部镜头将分别创建生成任务";
  if (scope === "scene") return scene ? `场景 ${scene.index + 1} · ${scene.outline || "未命名场景"}` : "请先选择一个场景";
  return shot ? `镜头 ${shot.index + 1} · ${shot.description || "未填写画面描述"}` : "请先选择一个镜头";
}

function userFacingGenerationError(message: string) {
  if (/agnes|dashscope|qwen|provider|model|api[_ -]?key|ai_[a-z_]+/i.test(message)) {
    return "AI 生成服务暂不可用，请稍后重试；如持续失败，请联系管理员。";
  }
  return message;
}

export function QuickAIGenerateModal({
  open,
  projectName,
  projectId,
  expectedRevision,
  scenes,
  assets,
  selectedScene,
  selectedShot,
  initialKind = "image",
  initialScope = "shot",
  pending,
  error,
  onClose,
  onGenerate,
}: Props) {
  const [kind, setKind] = useState<GenerationKind>("image");
  const [scope, setScope] = useState<ScopeKind>(initialScope);
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("电影质感");
  const [videoMode, setVideoMode] = useState<VideoGenerationMode>("text");
  const [durationSeconds, setDurationSeconds] = useState(5);
  const [firstFrameAssetId, setFirstFrameAssetId] = useState("");
  const [lastFrameAssetId, setLastFrameAssetId] = useState("");
  const [referenceImageAssetIds, setReferenceImageAssetIds] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [estimate, setEstimate] = useState<OperationEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState("");

  useEffect(() => {
    if (!open) return;
    setKind(initialKind);
    setScope(initialScope);
    setPrompt(initialScope === "shot" ? selectedShot?.description ?? "" : "");
    setStyle("电影质感");
    setVideoMode("text");
    setDurationSeconds(5);
    setFirstFrameAssetId("");
    setLastFrameAssetId("");
    setReferenceImageAssetIds([]);
    setSubmitted(false);
  }, [initialKind, initialScope, open, selectedShot?.description]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !pending) onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open, pending]);

  const selectedType = generationTypes.find((item) => item.id === kind) ?? generationTypes[0];
  const targetCount = scope === "project"
    ? scenes.reduce((total, scene) => total + scene.shots.length, 0)
    : scope === "scene" ? selectedScene?.shots.length ?? 0 : selectedShot ? 1 : 0;
  const bulkGeneration = scope !== "shot";
  const imageAssets = useMemo(
    () => assets.filter((asset) => asset.mediaType === "image" && asset.status === "ready" && asset.processingStatus === "ready"),
    [assets],
  );
  const videoInputsValid = kind !== "video"
    || videoMode === "text"
    || (videoMode === "keyframe" ? Boolean(firstFrameAssetId || lastFrameAssetId) : referenceImageAssetIds.length > 0);
  const valid = (bulkGeneration || prompt.trim().length >= 6) && targetCount > 0 && videoInputsValid;
  const scopeLockedToShot = kind === "video" && videoMode !== "text";
  const scopeCopy = useMemo(
    () => scopeDescription(scope, selectedScene, selectedShot),
    [scope, selectedScene, selectedShot],
  );
  const operationInput = useMemo(() => {
    const operation: ProjectOperation = kind === "image" ? "generate_image" : "generate_video";
    const operationScope: OperationScope = scope === "project"
      ? { type: "project" }
      : scope === "scene" && selectedScene?.id
        ? { type: "scene", sceneIds: [selectedScene.id] }
        : selectedShot?.id
          ? { type: "shot", shotIds: [selectedShot.id] }
          : { type: "project" };
    const parameters: Record<string, unknown> = bulkGeneration
      ? { use_shot_descriptions: true, additional_instruction: prompt.trim(), style }
      : { prompt: prompt.trim(), style };
    if (kind === "video") {
      parameters.generation_mode = videoMode;
      parameters.duration_seconds = durationSeconds;
      if (videoMode === "keyframe") {
        parameters.first_frame_asset_id = firstFrameAssetId || null;
        parameters.last_frame_asset_id = lastFrameAssetId || null;
      } else if (videoMode === "reference") parameters.reference_image_asset_ids = referenceImageAssetIds;
    }
    return { operation, scope: operationScope, parameters };
  }, [bulkGeneration, durationSeconds, firstFrameAssetId, kind, lastFrameAssetId, prompt, referenceImageAssetIds, scope, selectedScene, selectedShot, style, videoMode]);

  useEffect(() => {
    if (!open || !valid || !projectId || projectId === "__preview__") {
      setEstimate(null);
      setEstimateLoading(false);
      setEstimateError("");
      return;
    }
    let cancelled = false;
    setEstimateLoading(true); setEstimateError("");
    const timer = window.setTimeout(() => {
      void estimateProjectOperation(projectId, { ...operationInput, expectedRevision })
        .then((value) => { if (!cancelled) setEstimate(value); })
        .catch((reason) => { if (!cancelled) { setEstimate(null); setEstimateError(reason instanceof Error ? reason.message : "暂时无法计算费用"); } })
        .finally(() => { if (!cancelled) setEstimateLoading(false); });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [expectedRevision, open, operationInput, projectId, valid]);

  if (!open) return null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!valid || pending) return;
    if (!estimate || !estimate.sufficient) return;
    onGenerate(operationInput.operation, operationInput.scope, operationInput.parameters, estimate.catalogVersionId);
  }

  function selectVideoMode(nextMode: VideoGenerationMode) {
    if (nextMode !== "text" && (scope !== "shot" || !selectedShot?.id)) return;
    setVideoMode(nextMode);
    if (nextMode !== "text") setScope("shot");
  }

  function toggleReferenceImage(assetId: string) {
    setReferenceImageAssetIds((current) => current.includes(assetId)
      ? current.filter((id) => id !== assetId)
      : current.length < 5 ? [...current, assetId] : current);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
      <button type="button" aria-label="关闭快捷 AI 生成" onClick={() => !pending && onClose()} className="absolute inset-0 bg-ink/55 backdrop-blur-sm" />
      <form onSubmit={submit} className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl" aria-labelledby="quick-ai-title">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink text-white"><Sparkles size={20} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><h2 id="quick-ai-title" className="text-base font-semibold text-text">快捷 AI 生成</h2><span className="rounded-full bg-blue-soft px-2 py-0.5 text-[10px] font-semibold text-blue">直接应用到项目</span></div>
            <p className="mt-1 truncate text-xs text-muted">{projectName} · 生成结果会作为新素材写入画面历史，原内容不会被覆盖</p>
          </div>
          <button type="button" aria-label="关闭" disabled={pending} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>

        <div className="overflow-y-auto px-5 py-5 sm:px-6">
          <fieldset>
            <legend className="text-xs font-semibold text-text">1. 选择生成类型</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {generationTypes.map(({ id, label, copy, icon: Icon }) => (
                <button key={id} type="button" onClick={() => setKind(id)} aria-pressed={kind === id} className={`rounded-xl border p-3 text-left transition ${kind === id ? "border-blue bg-blue-soft/60 ring-1 ring-blue/20" : "border-line hover:border-blue/35"}`}>
                  <span className={`grid h-8 w-8 place-items-center rounded-lg ${kind === id ? "bg-blue text-white" : "bg-canvas text-muted"}`}><Icon size={16} /></span>
                  <strong className="mt-2 block text-xs text-text">{label}</strong><small className="mt-1 block text-[10px] leading-4 text-muted">{copy}</small>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="mt-5">
            <legend className="text-xs font-semibold text-text">2. 选择应用范围</legend>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {([
                ["project", "整个项目", `${scenes.length} 个场景`],
                ["scene", "当前场景", selectedScene ? `${selectedScene.shots.length} 个镜头` : "未选择"],
                ["shot", "当前镜头", selectedShot ? "1 个镜头" : "未选择"],
              ] as const).map(([value, label, count]) => {
                const missingTarget = value === "scene" ? !selectedScene?.id : value === "shot" ? !selectedShot?.id : scenes.length === 0;
                const incompatibleMode = scopeLockedToShot && value !== "shot";
                const disabled = missingTarget || incompatibleMode;
                const title = incompatibleMode ? "关键帧控制和图片参考生成只能应用到当前镜头" : undefined;
                return <button key={value} type="button" disabled={disabled} title={title} onClick={() => { setScope(value); setPrompt(value === "shot" ? selectedShot?.description ?? "" : ""); }} className={`rounded-xl border px-3 py-2.5 text-left disabled:cursor-not-allowed disabled:opacity-40 ${scope === value ? "border-ink bg-ink text-white" : "border-line text-text hover:border-ink/30"}`}><strong className="block text-xs">{label}</strong><small className={`mt-1 block text-[10px] ${scope === value ? "text-white/60" : "text-muted"}`}>{count}</small></button>;
              })}
            </div>
            <div className="mt-2 flex items-start gap-2 rounded-lg bg-canvas px-3 py-2.5 text-[10px] leading-4 text-muted"><Layers3 size={13} className="mt-0.5 shrink-0" /><span><strong className="text-text">应用位置：</strong>{scopeCopy}。共会创建 {targetCount} 个生成任务。</span></div>
            {scopeLockedToShot && <p className="mt-2 text-[10px] leading-4 text-muted">当前生成方式只适用于单个镜头。如需生成整个项目或当前场景，请先切换到“文生视频”。</p>}
          </fieldset>

          {kind === "video" && <fieldset className="mt-5">
            <legend className="text-xs font-semibold text-text">3. 视频生成方式</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">{([
              ["text", "文生视频", "只使用提示词；支持单镜头、场景和整个项目"],
              ["keyframe", "关键帧控制", "指定起始和/或结束画面，仅用于当前镜头"],
              ["reference", "图片参考生成", "参考 1–5 张图片生成当前镜头"],
            ] as const).map(([value, label, copy]) => { const disabled = value !== "text" && (scope !== "shot" || !selectedShot?.id); const title = disabled ? "请先将应用范围切换为当前镜头" : undefined; return <button key={value} type="button" disabled={disabled} title={title} onClick={() => selectVideoMode(value)} className={`rounded-xl border p-3 text-left disabled:cursor-not-allowed disabled:opacity-40 ${videoMode === value ? "border-blue bg-blue-soft/60 ring-1 ring-blue/20" : "border-line hover:border-blue/35"}`}><strong className="block text-xs text-text">{label}</strong><small className="mt-1 block text-[10px] leading-4 text-muted">{copy}</small></button>; })}</div>
            {scope !== "shot" && <p className="mt-2 rounded-lg bg-canvas px-3 py-2 text-[10px] leading-4 text-muted">当前范围支持文生视频。关键帧控制和图片参考生成需要先选择“当前镜头”。</p>}

            {videoMode === "keyframe" && <div className="mt-3 rounded-xl border border-line bg-canvas/40 p-3"><div className="mb-3 rounded-lg bg-blue-soft/60 px-3 py-2.5 text-[10px] leading-5 text-muted"><strong className="block text-[11px] text-text">如何使用关键帧</strong>只选首帧，视频会从这张图开始运动；只选尾帧，视频会最终到达这张图；首尾都选，可以控制从起点到终点的画面过渡。<span className="mt-1 block">示例：首帧选择人物站立，尾帧选择人物坐下，提示词描述“人物缓慢坐到椅子上”。</span></div><div className="grid gap-3 sm:grid-cols-2">
              {([[
                "首帧图片", firstFrameAssetId, setFirstFrameAssetId,
              ], [
                "尾帧图片", lastFrameAssetId, setLastFrameAssetId,
              ]] as const).map(([label, value, setter]) => { const asset = imageAssets.find((item) => item.id === value); return <label key={label} className="text-xs font-medium text-text">{label}<Select value={value} onChange={(event) => setter(event.target.value)} wrapperClassName="mt-1.5"><option value="">不设置</option>{imageAssets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>{asset && <div className="mt-2 flex items-center gap-2 rounded-lg border border-line bg-white p-2"><div className="relative h-10 w-16 shrink-0 overflow-hidden rounded bg-canvas"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? asset.mediaUrl} showPlay={false} rounded="rounded" /></div><span className="min-w-0 truncate text-[10px] font-normal text-muted">{asset.name}</span></div>}</label>; })}
              {!imageAssets.length && <p className="sm:col-span-2 text-[10px] text-amber">当前项目没有处理完成的图片，请先添加图片素材。</p>}
            </div></div>}

            {videoMode === "reference" && <div className="mt-3 rounded-xl border border-line bg-canvas/40 p-3"><div className="mb-3 rounded-lg bg-blue-soft/60 px-3 py-2.5 text-[10px] leading-5 text-muted"><strong className="block text-[11px] text-text">如何使用参考图片</strong>选择 1–5 张图片，帮助当前镜头保持人物、产品、场景或整体风格一致。参考图片不会固定成为视频的第一帧；如需固定开场画面，请使用“关键帧控制”。</div><div className="flex items-center justify-between"><strong className="text-[11px] text-text">选择参考图片</strong><span className={`text-[10px] ${referenceImageAssetIds.length >= 5 ? "font-semibold text-amber" : "text-muted"}`}>{referenceImageAssetIds.length}/5</span></div><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{imageAssets.map((asset) => { const selected = referenceImageAssetIds.includes(asset.id); const capped = referenceImageAssetIds.length >= 5 && !selected; return <button key={asset.id} type="button" disabled={capped} onClick={() => toggleReferenceImage(asset.id)} className={`overflow-hidden rounded-lg border bg-white text-left disabled:cursor-not-allowed disabled:opacity-40 ${selected ? "border-blue ring-1 ring-blue/20" : "border-line"}`}><div className="relative aspect-video bg-canvas"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? asset.mediaUrl} showPlay={false} />{selected && <span className="absolute right-1 top-1 grid h-4 w-4 place-items-center rounded-full bg-blue text-white"><Check size={10} /></span>}</div><span className="block truncate px-2 py-1.5 text-[9px] text-text">{asset.name}</span></button>; })}</div>{!imageAssets.length && <p className="py-4 text-center text-[10px] text-amber">当前项目没有处理完成的图片，请先添加图片素材。</p>}</div>}
          </fieldset>}

          <label className="mt-5 block text-xs font-semibold text-text">
            {bulkGeneration ? `${kind === "video" ? "4" : "3"}. 全局补充要求（可选）` : `${kind === "video" ? "4" : "3"}. 描述当前镜头的画面`}
            <textarea rows={5} maxLength={1000} value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-invalid={!bulkGeneration && submitted && prompt.trim().length < 6} placeholder={bulkGeneration ? "无需重复描述每个镜头。可补充所有镜头都要遵循的要求，例如：保持角色外观一致、统一使用冷蓝色科技光线…" : videoMode === "keyframe" ? "描述画面如何从起始关键帧运动到结束关键帧，例如：镜头缓慢推进，人物转身看向窗外…" : videoMode === "reference" ? "描述希望生成的镜头内容和动作，系统会参考所选图片中的人物、物体、场景或风格…" : "描述主体、场景、动作、镜头语言、光线与整体氛围…"} className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 text-text outline-none transition focus:ring-2 ${!bulkGeneration && submitted && prompt.trim().length < 6 ? "border-red focus:ring-red/10" : "border-line focus:border-blue/50 focus:ring-blue/10"}`} />
            <span className="mt-1 flex justify-between text-[10px] font-normal text-muted"><em className="not-italic">{bulkGeneration ? `系统会读取 ${targetCount} 个镜头各自的画面描述，并分别生成${kind === "video" ? "视频" : "图片"}` : "至少输入 6 个字符；此描述只用于当前镜头"}</em><span>{prompt.length}/1000</span></span>
          </label>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-medium text-text">视觉风格<Select value={style} onChange={(event) => setStyle(event.target.value)} wrapperClassName="mt-1.5"><option>电影质感</option><option>真实纪实</option><option>科技未来</option><option>极简商业</option><option>二维插画</option></Select></label>
            <div className="text-xs font-medium text-text">生成规格{kind === "video" ? <div className="mt-1.5 grid grid-cols-[92px_1fr] gap-2"><Select aria-label="视频时长" value={String(durationSeconds)} onChange={(event) => setDurationSeconds(Number(event.target.value))}>{[4, 5, 6, 8, 10, 12].map((seconds) => <option key={seconds} value={seconds}>{seconds} 秒</option>)}</Select><div className="rounded-lg border border-line bg-canvas/60 px-3 py-2.5 text-xs font-normal text-muted">沿用项目画幅</div></div> : <div className="mt-1.5 rounded-lg border border-line bg-canvas/60 px-3 py-2.5 text-xs font-normal text-muted">沿用项目画幅</div>}</div>
          </div>

          {(submitted && !valid) && <p className="mt-4 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{targetCount === 0 ? "当前范围内没有可生成的镜头" : !videoInputsValid ? videoMode === "keyframe" ? "关键帧模式至少选择首帧或尾帧" : "图片参考模式至少选择一张参考图片" : "请补充至少 6 个字符的当前镜头画面描述"}</p>}
          {error && <p className="mt-4 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{userFacingGenerationError(error)}</p>}
          <div className={`mt-4 rounded-xl border p-4 ${estimate && !estimate.sufficient ? "border-red/25 bg-red/5" : "border-line bg-canvas/50"}`}>
            <div className="flex items-center justify-between gap-3"><strong className="text-xs text-text">V-Credits 费用预估</strong><strong className="text-sm text-text">{estimateLoading ? "计算中…" : estimate ? `${estimate.estimatedCredits.toLocaleString("zh-CN")} V-Credits` : "—"}</strong></div>
            {estimate && <><p className="mt-1 text-[10px] text-muted">当前可用 {estimate.availableCredits.toLocaleString("zh-CN")} · 完成后预计剩余 {estimate.remainingAfter.toLocaleString("zh-CN")}</p>{estimate.lines.map((line) => <p key={line.sku} className="mt-1 text-[10px] text-muted">{line.quantity} {line.unit} × {line.unitCredits.toLocaleString("zh-CN")} = {line.credits.toLocaleString("zh-CN")}</p>)}</>}
            {estimate && !estimate.sufficient && <p className="mt-2 text-xs font-medium text-red">余额不足，请先前往个人中心充值 V-Credits。</p>}
            {estimateError && <p className="mt-2 text-xs text-red">{estimateError}</p>}
            <p className="mt-2 text-[10px] text-muted">这里只展示预计最多消耗；失败任务会自动释放，不会实际扣除。</p>
          </div>
        </div>

        <footer className="flex flex-col gap-3 border-t border-line bg-canvas/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="flex items-center gap-1.5 text-[10px] text-muted"><Check size={13} className="text-teal" />生成结果将进入项目素材库，并建立可回退的镜头版本</p>
          <div className="flex justify-end gap-2"><button type="button" disabled={pending} onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="submit" disabled={pending || estimateLoading || !estimate?.sufficient} className="flex min-w-[132px] items-center justify-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{pending ? <Loader2 size={14} className="animate-spin" /> : <selectedType.icon size={14} />}{pending ? "正在创建任务…" : `生成${selectedType.label.replace("AI ", "")}`}</button></div>
        </footer>
      </form>
    </div>
  );
}
