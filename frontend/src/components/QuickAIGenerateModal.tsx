import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Film,
  Image as ImageIcon,
  Layers3,
  Loader2,
  Sparkles,
  WandSparkles,
  X,
} from "lucide-react";
import type { OperationScope, ProjectOperation } from "@/api/generate";
import type { Scene, Shot } from "@/api/projects";

export type GenerationKind = "image" | "video" | "effect";
type ScopeKind = "project" | "scene" | "shot";

interface Props {
  open: boolean;
  projectName: string;
  scenes: Scene[];
  selectedScene?: Scene;
  selectedShot?: Shot;
  initialKind?: GenerationKind;
  initialScope?: ScopeKind;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onGenerate: (operation: ProjectOperation, scope: OperationScope, parameters: Record<string, unknown>) => void;
}

const generationTypes = [
  { id: "image", label: "AI 图片", copy: "为镜头生成可继续编辑的分镜图", icon: ImageIcon },
  { id: "video", label: "AI 视频", copy: "从文字或当前分镜生成动态画面", icon: Film },
  { id: "effect", label: "AI 特效", copy: "让已有示意图产生镜头运动与特效", icon: WandSparkles },
] as const;

function scopeDescription(scope: ScopeKind, scene?: Scene, shot?: Shot) {
  if (scope === "project") return "项目中的全部镜头将分别创建生成任务";
  if (scope === "scene") return scene ? `场景 ${scene.index + 1} · ${scene.outline || "未命名场景"}` : "请先选择一个场景";
  return shot ? `镜头 ${shot.index + 1} · ${shot.description || "未填写画面描述"}` : "请先选择一个镜头";
}

export function QuickAIGenerateModal({
  open,
  projectName,
  scenes,
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
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind(initialKind);
    setScope(initialScope);
    setPrompt(initialScope === "shot" ? selectedShot?.description ?? "" : "");
    setStyle("电影质感");
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
  const effectAvailable = Boolean(selectedShot?.sketchData);
  const targetCount = scope === "project"
    ? scenes.reduce((total, scene) => total + scene.shots.length, 0)
    : scope === "scene" ? selectedScene?.shots.length ?? 0 : selectedShot ? 1 : 0;
  const bulkGeneration = scope !== "shot";
  const valid = (bulkGeneration || prompt.trim().length >= 6) && targetCount > 0 && (kind !== "effect" || effectAvailable);
  const scopeCopy = useMemo(
    () => scopeDescription(scope, selectedScene, selectedShot),
    [scope, selectedScene, selectedShot],
  );

  if (!open) return null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!valid || pending) return;
    const operation: ProjectOperation = kind === "image" ? "generate_image" : kind === "video" ? "generate_video" : "generate_effect";
    const operationScope: OperationScope = scope === "project"
      ? { type: "project" }
      : scope === "scene" && selectedScene?.id
        ? { type: "scene", sceneIds: [selectedScene.id] }
        : selectedShot?.id
          ? { type: "shot", shotIds: [selectedShot.id] }
          : { type: "project" };
    const parameters: Record<string, unknown> = bulkGeneration
      ? {
          use_shot_descriptions: true,
          additional_instruction: prompt.trim(),
          style,
        }
      : kind === "effect"
        ? { motion_description: prompt.trim(), style }
        : { prompt: prompt.trim(), style };
    onGenerate(operation, operationScope, parameters);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
      <button type="button" aria-label="关闭快捷 AI 生成" onClick={() => !pending && onClose()} className="absolute inset-0 bg-ink/55 backdrop-blur-sm" />
      <form onSubmit={submit} className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-3xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl" aria-labelledby="quick-ai-title">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink text-white"><Sparkles size={20} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><h2 id="quick-ai-title" className="text-base font-semibold text-text">快捷 AI 生成</h2><span className="rounded-full bg-blue-soft px-2 py-0.5 text-[10px] font-semibold text-blue">直接应用到项目</span></div>
            <p className="mt-1 truncate text-xs text-muted">{projectName} · 生成结果会作为新素材与媒体版本保存，原内容不会被覆盖</p>
          </div>
          <button type="button" aria-label="关闭" disabled={pending} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>

        <div className="overflow-y-auto px-5 py-5 sm:px-6">
          <fieldset>
            <legend className="text-xs font-semibold text-text">1. 选择生成类型</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {generationTypes.map(({ id, label, copy, icon: Icon }) => (
                <button key={id} type="button" disabled={id === "effect" && !effectAvailable} onClick={() => { setKind(id); if (id === "effect") setScope("shot"); }} aria-pressed={kind === id} className={`rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-45 ${kind === id ? "border-blue bg-blue-soft/60 ring-1 ring-blue/20" : "border-line hover:border-blue/35"}`}>
                  <span className={`grid h-8 w-8 place-items-center rounded-lg ${kind === id ? "bg-blue text-white" : "bg-canvas text-muted"}`}><Icon size={16} /></span>
                  <strong className="mt-2 block text-xs text-text">{label}</strong><small className="mt-1 block text-[10px] leading-4 text-muted">{id === "effect" && !effectAvailable ? "当前镜头需先保存 Canvas 草图" : copy}</small>
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
                const disabled = kind === "effect" && value !== "shot" ? true : value === "scene" ? !selectedScene?.id : value === "shot" ? !selectedShot?.id : targetCount === 0 && value === "project";
                return <button key={value} type="button" disabled={disabled} onClick={() => { setScope(value); setPrompt(value === "shot" ? selectedShot?.description ?? "" : ""); }} className={`rounded-xl border px-3 py-2.5 text-left disabled:cursor-not-allowed disabled:opacity-40 ${scope === value ? "border-ink bg-ink text-white" : "border-line text-text hover:border-ink/30"}`}><strong className="block text-xs">{label}</strong><small className={`mt-1 block text-[10px] ${scope === value ? "text-white/60" : "text-muted"}`}>{count}</small></button>;
              })}
            </div>
            <div className="mt-2 flex items-start gap-2 rounded-lg bg-canvas px-3 py-2.5 text-[10px] leading-4 text-muted"><Layers3 size={13} className="mt-0.5 shrink-0" /><span><strong className="text-text">应用位置：</strong>{scopeCopy}。共会创建 {targetCount} 个生成任务。</span></div>
          </fieldset>

          <label className="mt-5 block text-xs font-semibold text-text">
            {bulkGeneration ? "3. 全局补充要求（可选）" : "3. 描述当前镜头的画面"}
            <textarea rows={5} maxLength={1000} value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-invalid={!bulkGeneration && submitted && prompt.trim().length < 6} placeholder={bulkGeneration ? "无需重复描述每个镜头。可补充所有镜头都要遵循的要求，例如：保持角色外观一致、统一使用冷蓝色科技光线…" : kind === "effect" ? "例如：镜头缓慢推进，光线从画面左侧扫过，金属装置逐渐展开…" : "描述主体、场景、动作、镜头语言、光线与整体氛围…"} className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 text-text outline-none transition focus:ring-2 ${!bulkGeneration && submitted && prompt.trim().length < 6 ? "border-red focus:ring-red/10" : "border-line focus:border-blue/50 focus:ring-blue/10"}`} />
            <span className="mt-1 flex justify-between text-[10px] font-normal text-muted"><em className="not-italic">{bulkGeneration ? `系统会读取 ${targetCount} 个镜头各自的画面描述，并分别生成${kind === "video" ? "视频" : "图片"}` : "至少输入 6 个字符；此描述只用于当前镜头"}</em><span>{prompt.length}/1000</span></span>
          </label>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-medium text-text">视觉风格<select value={style} onChange={(event) => setStyle(event.target.value)} className="mt-1.5 w-full rounded-lg border border-line bg-white p-2.5 text-xs text-text"><option>电影质感</option><option>真实纪实</option><option>科技未来</option><option>极简商业</option><option>二维插画</option></select></label>
            <div className="text-xs font-medium text-text">生成规格<div className="mt-1.5 rounded-lg border border-line bg-canvas/60 px-3 py-2.5 text-xs font-normal text-muted">沿用项目画幅 · 视频时长跟随对应镜头</div></div>
          </div>

          {(submitted && !valid) && <p className="mt-4 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{kind === "effect" && !effectAvailable ? "当前镜头还没有 Canvas 草图，暂时不能生成视觉特效" : targetCount === 0 ? "当前范围内没有可生成的镜头" : "请补充至少 6 个字符的当前镜头画面描述"}</p>}
          {error && <p className="mt-4 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{error}</p>}
        </div>

        <footer className="flex flex-col gap-3 border-t border-line bg-canvas/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="flex items-center gap-1.5 text-[10px] text-muted"><Check size={13} className="text-teal" />生成结果将进入项目素材库，并建立可回退的镜头版本</p>
          <div className="flex justify-end gap-2"><button type="button" disabled={pending} onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="submit" disabled={pending} className="flex min-w-[132px] items-center justify-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{pending ? <Loader2 size={14} className="animate-spin" /> : <selectedType.icon size={14} />}{pending ? "正在创建任务…" : `生成${selectedType.label.replace("AI ", "")}`}</button></div>
        </footer>
      </form>
    </div>
  );
}
