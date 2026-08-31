import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlignLeft, ArrowDown, ArrowUp, AudioLines, ChevronDown, ChevronLeft, ChevronRight, Copy, Film, GripVertical, History, Image as ImageIcon, Library, Maximize2,
  Mic2, MoreHorizontal, Music2, Pause, Pencil, Play, Plus, RotateCcw, Scissors, Search, SlidersHorizontal, Sparkles,
  Trash2, Volume2, VolumeX, WandSparkles, X,
} from "lucide-react";
import type { CSSProperties } from "react";
import type { Asset } from "@/api/assets";
import type { ProjectOperation } from "@/api/generate";
import { getVoiceoverWorkspace } from "@/api/voiceover";
import type { GenerationKind } from "@/components/QuickAIGenerateModal";
import type { Project, ProjectAudioMix, ProjectDocumentSettings, Scene, ScopeAssetReference, Shot, Workspace } from "@/api/projects";
import { VideoThumb } from "@/components/VideoThumb";
import { Select } from "@/components/ui/Select";
import {
  buildCompositionModel, clamp, compositionShotAt, nextCompositionShot, numeric,
  effectiveShotAdjust, shotVisualStyle, subtitleStyle, transitionLayerStyle, transitionState,
  type CompositionShot,
} from "@/lib/compositionPreview";

type ResourceTab = "outline" | "assets" | "settings";
type InspectorTab = "visual" | "audio" | "caption";
type EditorPaneSide = "left" | "right";

const EDITOR_PANE_STORAGE_KEY = "openvma:project-editor-pane-widths:v1";
const EDITOR_PANE_DEFAULTS = { left: 260, right: 420 };
const EDITOR_PANE_MINIMUMS = { left: 200, center: 420, right: 340 };
const EDITOR_SPLITTER_WIDTH = 8;

interface Props {
  workspace: Workspace;
  selectedScene?: Scene;
  selectedShot?: Shot;
  operationPending: boolean;
  onSelectScene: (id: string | null) => void;
  onSelectShot: (id: string | null) => void;
  onUpdateDocumentSettings: (patch: Partial<ProjectDocumentSettings>) => void;
  onApplyGlobalColorGrade: (colorGrade: Record<string, unknown>, clearShotOverrides: boolean) => void;
  onUpdateProject: (patch: Partial<Project>) => void;
  onUpdateScene: (sceneId: string, patch: Partial<Scene>) => void;
  onMoveScene: (sceneId: string, direction: -1 | 1) => void;
  onUpdateShot: (sceneId: string, shotId: string, patch: Partial<Shot>) => void;
  onMoveShot: (sceneId: string, shotId: string, direction: -1 | 1) => void;
  onSplitShot: (sceneId: string, shotId: string, offsetMs: number) => void;
  onRemoveShotAsset: (sceneId: string, shotId: string) => void;
  onDuplicateShot: (sceneId: string, shotId: string) => void;
  onRestoreSubtitle: (sceneId: string, shotId: string) => void;
  onAddScene: () => void;
  onAddShot: (sceneId: string) => void;
  onDeleteScene: () => void;
  onDeleteShot: () => void;
  onRunOperation: (operation: ProjectOperation, parameters?: Record<string, unknown>, scope?: { type: "project" | "scene" | "shot"; sceneIds?: string[]; shotIds?: string[] }) => void;
  onOpenQuickAI: (scope: "project" | "scene" | "shot", kind?: GenerationKind) => void;
  onOpenVoiceover: () => void;
  onApplyVoiceoverMaster: (assetId: string) => Promise<void>;
}

const resources = [
  { id: "outline", label: "结构", icon: AlignLeft },
  { id: "assets", label: "素材", icon: Library },
  { id: "settings", label: "项目设置", icon: SlidersHorizontal },
] as const;

const inspectors = [
  { id: "visual", label: "画面" },
  { id: "audio", label: "音频" },
  { id: "caption", label: "字幕" },
] as const;

const filterPresets = [
  ["original", "原始"], ["cinematic", "电影"], ["vivid", "鲜明"],
  ["warm", "暖调"], ["cool", "冷调"], ["monochrome", "黑白"],
  ["vintage", "复古"], ["cyber", "赛博"],
] as const;
const motionPresets = [
  ["none", "无"], ["push", "推进"], ["pull", "拉远"], ["pan-left", "左摇"],
  ["pan-right", "右摇"], ["tilt-up", "上移"], ["tilt-down", "下移"], ["handheld", "手持"],
] as const;
const transitionPresets = [
  ["cut", "硬切"], ["dissolve", "叠化"], ["fade", "淡入淡出"],
  ["slide-left", "左滑"], ["slide-right", "右滑"], ["zoom", "缩放"],
] as const;

function formatTime(ms: number) {
  const seconds = Math.max(0, ms) / 1000;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}.${Math.floor((seconds % 1) * 10)}`;
}

function aspectRatioNumbers(aspectRatio: ProjectDocumentSettings["aspectRatio"]): [number, number] {
  const [width, height] = aspectRatio.split(":").map(Number);
  return [width || 16, height || 9];
}

function stageFrameStyle(aspectRatio: ProjectDocumentSettings["aspectRatio"], available: { width: number; height: number }): CSSProperties {
  const [width, height] = aspectRatioNumbers(aspectRatio);
  const ratio = width / height;
  const frameWidth = Math.max(1, Math.min(available.width || 1, (available.height || 1) * ratio));
  return { aspectRatio: `${width} / ${height}`, width: frameWidth, height: frameWidth / ratio };
}

function scopeReference(value: unknown): ScopeAssetReference | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const reference = value as Partial<ScopeAssetReference>;
  return reference.assetId ? reference as ScopeAssetReference : null;
}

function scopeReferenceList(value: unknown): ScopeAssetReference[] {
  return Array.isArray(value) ? value.map(scopeReference).filter((item): item is ScopeAssetReference => Boolean(item)) : [];
}

function seekMedia(element: HTMLMediaElement, seconds: number, toleranceSeconds = 0.12) {
  if (!Number.isFinite(seconds) || element.readyState === HTMLMediaElement.HAVE_NOTHING) return;
  const maximum = Number.isFinite(element.duration) ? Math.max(0, element.duration - 0.001) : seconds;
  const target = clamp(seconds, 0, maximum);
  if (Math.abs(element.currentTime - target) <= toleranceSeconds) return;
  try { element.currentTime = target; } catch { /* the media source is not seekable yet */ }
}

function CompositionAudioTrack({ asset, volume, playheadMs, playing, muted, startMs = 0, endMs, atMs = 0, loop = false }: {
  asset?: Asset; volume: number; playheadMs: number; playing: boolean; muted: boolean;
  startMs?: number; endMs?: number; atMs?: number; loop?: boolean;
}) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const active = Boolean(asset?.mediaUrl) && playheadMs >= startMs + atMs && (endMs === undefined || playheadMs < endMs);
  const elapsedMs = Math.max(0, playheadMs - startMs - atMs);
  const localSeconds = (loop && (asset?.durationMs ?? 0) > 0 ? elapsedMs % asset!.durationMs : elapsedMs) / 1000;
  const desiredSecondsRef = useRef(localSeconds);
  useEffect(() => { desiredSecondsRef.current = localSeconds; }, [localSeconds]);

  useEffect(() => {
    const audio = ref.current;
    if (!audio) return;
    audio.volume = clamp(volume, 0, 100) / 100;
    audio.muted = muted || volume <= 0;
  }, [muted, volume]);

  useEffect(() => {
    const audio = ref.current;
    if (!audio) return;
    if (!playing || !active) {
      audio.pause();
      return;
    }
    seekMedia(audio, desiredSecondsRef.current, 0.35);
    void audio.play().catch(() => undefined);
  }, [active, asset?.mediaUrl, atMs, loop, playing, startMs]);

  useEffect(() => {
    const audio = ref.current;
    if (!audio || playing || !active) return;
    seekMedia(audio, localSeconds);
  }, [active, localSeconds, playing]);

  if (!asset?.mediaUrl) return null;
  return <audio ref={ref} src={asset.mediaUrl} loop={loop} preload="auto" onLoadedMetadata={(event) => {
    seekMedia(event.currentTarget, desiredSecondsRef.current, 0);
    if (playing && active) void event.currentTarget.play().catch(() => undefined);
  }} />;
}

function CompositionAudioMix({ workspace, model, activeShot, playheadMs, playing, muted }: {
  workspace: Workspace; model: ReturnType<typeof buildCompositionModel>; activeShot?: CompositionShot;
  playheadMs: number; playing: boolean; muted: boolean;
}) {
  const assets = new Map(workspace.linkedAssets.map((asset) => [asset.id, asset]));
  const mix = workspace.document.settings.globalAudio;
  const film = workspace.document.globalScopes.film;
  const scene = activeShot?.scene.id ? workspace.document.globalScopes.scenes[activeShot.scene.id] ?? {} : {};
  const sceneShots = activeShot ? model.shots.filter((item) => item.scene.id === activeShot.scene.id) : [];
  const sceneStart = sceneShots[0]?.startMs ?? 0;
  const sceneEnd = sceneShots.at(-1)?.endMs ?? model.durationMs;
  const shotMusic = scopeReference(activeShot?.shot.audioSettings.backgroundMusic);
  const sceneMusic = scopeReference(scene.backgroundMusic);
  const filmMusic = scopeReference(film.backgroundMusic);
  const defaultMusic = mix.musicAssetId ? { assetId: mix.musicAssetId, volume: numeric(mix.musicVolume, 24), loop: true } : null;
  const music = shotMusic ?? sceneMusic ?? filmMusic ?? defaultMusic;
  const musicStart = shotMusic ? activeShot?.startMs ?? 0 : sceneMusic ? sceneStart : 0;
  const musicEnd = shotMusic ? activeShot?.endMs : sceneMusic ? sceneEnd : model.durationMs;
  const voice = mix.voiceAssetId ? assets.get(mix.voiceAssetId) : undefined;
  const voiceActive = Boolean(voice?.mediaUrl)
    && !mix.voiceMuted
    && numeric(mix.voiceVolume, 100) > 0
    && (numeric(voice?.durationMs) <= 0 || playheadMs < numeric(voice?.durationMs));
  const musicVolume = mix.musicMuted ? 0 : numeric(music?.volume, numeric(mix.musicVolume, 24));
  const duckedMusicVolume = mix.duckingEnabled !== false && voiceActive ? musicVolume * 0.52 : musicVolume;
  const effects = [
    ...scopeReferenceList(film.soundEffects).map((reference) => ({ reference, startMs: 0, endMs: model.durationMs })),
    ...scopeReferenceList(scene.soundEffects).map((reference) => ({ reference, startMs: sceneStart, endMs: sceneEnd })),
    ...scopeReferenceList(activeShot?.shot.audioSettings.soundEffects).map((reference) => ({ reference, startMs: activeShot?.startMs ?? 0, endMs: activeShot?.endMs })),
  ];
  return <div hidden aria-hidden="true">
    <CompositionAudioTrack asset={voice} volume={mix.voiceMuted ? 0 : numeric(mix.voiceVolume, 100)} playheadMs={playheadMs} playing={playing} muted={muted} endMs={model.durationMs} />
    <CompositionAudioTrack asset={music ? assets.get(music.assetId) : undefined} volume={duckedMusicVolume} playheadMs={playheadMs} playing={playing} muted={muted} startMs={musicStart} endMs={musicEnd} loop={music?.loop !== false} />
    {effects.map(({ reference, startMs, endMs }, index) => <CompositionAudioTrack key={`${reference.id ?? reference.assetId}-${startMs}-${index}`} asset={assets.get(reference.assetId)} volume={numeric(reference.volume, 72)} playheadMs={playheadMs} playing={playing} muted={muted} startMs={startMs} endMs={endMs} atMs={numeric(reference.atMs)} loop={Boolean(reference.loop)} />)}
  </div>;
}

function CompositionOverlayVideo({ asset, item, startMs, playheadMs, playing, style, className }: {
  asset: Asset; item: ScopeAssetReference; startMs: number; playheadMs: number; playing: boolean;
  style: CSSProperties; className: string;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const elapsed = Math.max(0, playheadMs - startMs);
  const localMs = item.loop !== false && asset.durationMs > 0 ? elapsed % asset.durationMs : elapsed;
  const desiredSecondsRef = useRef(localMs / 1000);
  useEffect(() => { desiredSecondsRef.current = localMs / 1000; }, [localMs]);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    if (!playing) {
      video.pause();
      seekMedia(video, desiredSecondsRef.current);
      return;
    }
    seekMedia(video, desiredSecondsRef.current, 0.35);
    void video.play().catch(() => undefined);
  }, [asset.mediaUrl, item.loop, playing, startMs]);

  useEffect(() => {
    const video = ref.current;
    if (!video || playing) return;
    seekMedia(video, localMs / 1000);
  }, [localMs, playing]);

  return <video ref={ref} src={asset.mediaUrl} muted loop={item.loop !== false} playsInline preload="auto" onLoadedMetadata={(event) => {
    seekMedia(event.currentTarget, desiredSecondsRef.current, 0);
    if (playing) void event.currentTarget.play().catch(() => undefined);
  }} style={style} className={className} />;
}

function CompositionOverlays({ workspace, model, activeShot, playheadMs, playing }: {
  workspace: Workspace; model: ReturnType<typeof buildCompositionModel>; activeShot?: CompositionShot; playheadMs: number; playing: boolean;
}) {
  const assets = new Map(workspace.linkedAssets.map((asset) => [asset.id, asset]));
  const film = scopeReferenceList(workspace.document.globalScopes.film.visualAssets);
  const scene = activeShot?.scene.id
    ? scopeReferenceList(workspace.document.globalScopes.scenes[activeShot.scene.id]?.visualAssets)
    : [];
  const sceneStart = activeShot
    ? model.shots.find((item) => item.scene.id === activeShot.scene.id)?.startMs ?? 0
    : 0;
  const timedLayers = [
    ...film.map((item) => ({ item, startMs: 0 })),
    ...scene.map((item) => ({ item, startMs: sceneStart })),
    ...workspace.document.visualLayers.items.filter((item) => {
    if (item.enabled === false) return false;
    if (item.scope === "scene" && item.sceneId !== activeShot?.scene.id) return false;
    const start = numeric(item.startMs);
    const end = start + numeric(item.durationMs, model.durationMs);
    return playheadMs >= start && playheadMs < end;
  }).map((item) => ({ item, startMs: numeric(item.startMs) })),
  ];
  return <>{timedLayers.filter(({ item }) => item.enabled !== false).map(({ item, startMs }, index) => {
    const asset = assets.get(item.assetId);
    const source = asset?.mediaUrl ?? asset?.thumbnailUrl;
    if (!asset || !source) return null;
    const style: CSSProperties = { opacity: clamp(numeric(item.opacity, 32), 0, 100) / 100, mixBlendMode: String(item.blendMode ?? "normal") as CSSProperties["mixBlendMode"] };
    const className = `pointer-events-none absolute inset-0 z-[5] h-full w-full ${item.fitMode === "contain" ? "object-contain" : "object-cover"}`;
    return asset.mediaType === "video"
      ? <CompositionOverlayVideo key={`${item.id ?? item.assetId}-${index}`} asset={asset} item={item} startMs={startMs} playheadMs={playheadMs} playing={playing} style={style} className={className} />
      : <img key={`${item.id ?? item.assetId}-${index}`} src={source} alt="" style={style} className={className} />;
  })}</>;
}

function CompositionMedia({ meta, playheadMs, playing, muted, globalVisualSettings }: {
  meta?: CompositionShot; playheadMs: number; playing: boolean; muted: boolean; globalVisualSettings?: Record<string, unknown>;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const localMs = meta ? clamp(playheadMs - meta.startMs, 0, meta.durationMs) : 0;
  const sourceMs = meta
    ? clamp(meta.sourceStartMs + localMs, meta.sourceStartMs, Math.max(meta.sourceStartMs, meta.sourceEndMs - 30))
    : 0;
  const progress = meta ? localMs / Math.max(1, meta.durationMs) : 0;
  const visualStyle = meta ? shotVisualStyle(meta.shot, progress, globalVisualSettings) : undefined;
  const originalVolume = clamp(numeric(meta?.shot.audioSettings.originalVolume, 100), 0, 100) / 100;
  const desiredSecondsRef = useRef(sourceMs / 1000);
  useEffect(() => { desiredSecondsRef.current = sourceMs / 1000; }, [sourceMs]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = originalVolume;
    video.muted = muted || originalVolume <= 0;
  }, [muted, originalVolume]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !meta) return;
    if (!playing) {
      video.pause();
      return;
    }
    // Continuous playback is owned by the browser decoder. Only align once when
    // playback starts or the active shot/source changes; per-frame seeking makes
    // long-GOP and remote media repeatedly decode from a keyframe.
    seekMedia(video, desiredSecondsRef.current, 0.35);
    void video.play().catch(() => undefined);
  }, [meta, playing]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !meta || playing) return;
    seekMedia(video, sourceMs / 1000);
  }, [meta, playing, sourceMs]);

  if (!meta) return <div className="absolute inset-0 grid place-items-center bg-[#111318] text-center text-sm text-white/55"><div><Film size={36} className="mx-auto mb-3 opacity-40" />时间线中还没有镜头</div></div>;
  if (meta.asset?.mediaType === "video" && meta.mediaUrl) {
    return <video ref={videoRef} src={meta.mediaUrl} poster={meta.thumbnailUrl} playsInline preload="auto" style={visualStyle} onLoadedMetadata={(event) => {
      seekMedia(event.currentTarget, desiredSecondsRef.current, 0);
      if (playing) void event.currentTarget.play().catch(() => undefined);
    }} className="absolute inset-0 h-full w-full object-cover will-change-transform" />;
  }
  if ((meta.asset?.mediaType === "image" || meta.thumbnailUrl) && (meta.mediaUrl || meta.thumbnailUrl)) {
    return <img src={meta.mediaUrl ?? meta.thumbnailUrl} alt="" style={visualStyle} className="absolute inset-0 h-full w-full object-cover will-change-transform" />;
  }
  return <div className="absolute inset-0 overflow-hidden bg-[radial-gradient(circle_at_25%_20%,#314b77_0%,#1b2334_32%,#111318_72%)]" style={visualStyle}><div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.06)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.06)_1px,transparent_1px)] [background-size:32px_32px]" /><div className="absolute inset-0 grid place-items-center px-8 text-center text-white/75"><div><Film size={32} className="mx-auto mb-3 opacity-60" /><strong className="block text-sm">{meta.shot.description || "镜头占位"}</strong><span className="mt-1 block text-[11px] text-white/45">{meta.asset ? "素材尚无可播放预览" : "等待匹配或生成素材"}</span></div></div></div>;
}

function RangeControl({ label, value, minimum, maximum, suffix = "", step = 1, formatValue, onChange }: {
  label: string; value: number; minimum: number; maximum: number; suffix?: string; step?: number;
  formatValue?: (value: number) => string;
  onChange: (value: number) => void;
}) {
  return <label className="block text-[11px] text-muted"><span className="flex justify-between"><span>{label}</span><strong className="font-medium text-text">{formatValue ? formatValue(value) : `${value}${suffix}`}</strong></span><input type="range" min={minimum} max={maximum} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} className="mt-1.5 w-full accent-blue" /></label>;
}

function SourceTrimControl({ shot, asset, onChange, onOpen, onReplace, onRemove }: {
  shot: Shot;
  asset?: Asset;
  onChange: (patch: Partial<Shot>) => void;
  onOpen: () => void;
  onReplace: () => void;
  onRemove: () => void;
}) {
  return <section className="rounded-xl border border-line p-3">
    <header className="flex items-start justify-between gap-3"><div className="min-w-0"><span className="block text-[10px] text-muted">当前画面素材</span><strong className="mt-1 block truncate text-xs text-text">{asset?.name ?? "尚未选择素材"}</strong></div><details className="relative shrink-0"><summary aria-label="更多素材操作" className="grid h-7 w-7 cursor-pointer list-none place-items-center rounded-md text-muted hover:bg-canvas"><MoreHorizontal size={14} /></summary><div className="absolute right-0 top-8 z-20 w-32 rounded-lg border border-line bg-white p-1 shadow-lg"><button type="button" onClick={onRemove} disabled={shot.locked || (!asset && !shot.selectedMediaVersionId)} className="w-full rounded-md px-2 py-1.5 text-left text-[10px] text-red hover:bg-red/5 disabled:opacity-35">移除当前素材</button></div></details></header>
    {!asset ? <p className="mt-3 text-[11px] text-muted">从项目素材中选择画面，应用后才会替换当前镜头。</p> : asset.mediaType === "image" ? <div className="mt-3 rounded-lg bg-canvas px-3 py-2 text-[11px] text-muted">静态图片没有可裁剪的源片段，当前展示时长为 {(shot.durationMs / 1000).toFixed(1)} 秒。</div> : <div className="mt-3 flex items-end justify-between gap-3"><div><span className="block text-[10px] text-muted">当前使用片段</span><strong className="mt-1 block text-xs tabular-nums text-text">{formatTime(shot.sourceStartMs)}–{formatTime(shot.sourceStartMs + shot.durationMs)}</strong></div><div className="text-right"><span className="block text-[10px] text-muted">片段长度</span><strong className="mt-1 block text-xs text-text">{(shot.durationMs / 1000).toFixed(1)} 秒</strong></div></div>}
    <div className="mt-3 grid grid-cols-2 gap-2"><button type="button" onClick={onReplace} disabled={shot.locked} className="rounded-lg bg-blue-soft py-2 text-[10px] font-semibold text-blue disabled:opacity-35">{asset ? "更换素材" : "选择素材"}</button><button type="button" onClick={onOpen} disabled={!asset || asset.mediaType !== "video" || shot.locked} className="rounded-lg border border-line py-2 text-[10px] font-medium text-text disabled:opacity-35">调整片段</button></div>
    <label className="mt-3 flex items-center gap-1 text-[10px] text-muted"><input type="checkbox" checked={shot.locked} onChange={(event) => onChange({ locked: event.target.checked })} />锁定画面素材，防止误替换或裁剪</label>
  </section>;
}

function ClipTrimModal({ open, shot, asset, onClose, onApply }: {
  open: boolean; shot?: Shot; asset?: Asset; onClose: () => void;
  onApply: (patch: Partial<Shot>) => void;
}) {
  const [startMs, setStartMs] = useState(0);
  const [durationMs, setDurationMs] = useState(1000);
  const [loopPreview, setLoopPreview] = useState(true);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  useEffect(() => {
    if (!open || !shot || !asset) return;
    const maximumDuration = Math.max(100, asset.durationMs - shot.sourceStartMs);
    setStartMs(clamp(shot.sourceStartMs, 0, Math.max(0, asset.durationMs - 100)));
    setDurationMs(clamp(shot.durationMs, 100, maximumDuration));
  }, [asset, open, shot]);
  function previewAt(nextStartMs: number) {
    setStartMs(nextStartMs);
    setDurationMs((current) => Math.min(current, Math.max(100, (asset?.durationMs ?? 100) - nextStartMs)));
    if (videoRef.current) seekMedia(videoRef.current, nextStartMs / 1000, 0);
  }
  if (!open || !shot || !asset || asset.mediaType !== "video") return null;
  const sourceDuration = Math.max(100, asset.durationMs);
  const maxStart = Math.max(0, sourceDuration - 100);
  const maxDuration = Math.max(100, sourceDuration - startMs);
  const endMs = startMs + durationMs;
  return <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="trim-dialog-title"><section className="flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-2xl"><header className="shrink-0 flex items-start justify-between border-b border-line px-5 py-4"><div><h2 id="trim-dialog-title" className="text-sm font-semibold text-text">调整素材片段</h2><p className="mt-1 text-[11px] text-muted">预览只播放当前使用范围；调整入点和镜头时长后会立即更新。</p></div><button type="button" aria-label="关闭片段调整" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={15} /></button></header><div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5"><div className="overflow-hidden rounded-xl bg-[#111318]">{asset.mediaUrl ? <video ref={videoRef} src={asset.mediaUrl} controls preload="metadata" className="aspect-video w-full object-contain" onLoadedMetadata={() => previewAt(startMs)} onPlay={(event) => { const currentMs = event.currentTarget.currentTime * 1000; if (currentMs < startMs || currentMs >= endMs) seekMedia(event.currentTarget, startMs / 1000, 0); }} onTimeUpdate={(event) => { if (event.currentTarget.currentTime * 1000 < endMs - 30) return; if (loopPreview) { seekMedia(event.currentTarget, startMs / 1000, 0); void event.currentTarget.play().catch(() => undefined); } else { event.currentTarget.pause(); seekMedia(event.currentTarget, endMs / 1000, 0); } }} /> : <div className="grid aspect-video place-items-center text-xs text-white/45">当前素材没有可播放预览</div>}</div><div><div className="flex items-center justify-between text-[11px]"><span className="text-muted">当前使用范围</span><strong className="tabular-nums text-text">{formatTime(startMs)}–{formatTime(endMs)} · {(durationMs / 1000).toFixed(1)} 秒</strong></div><div className="relative mt-3 h-3 overflow-hidden rounded-full bg-canvas"><span className="absolute inset-y-0 rounded-full bg-blue" style={{ left: `${startMs / sourceDuration * 100}%`, width: `${durationMs / sourceDuration * 100}%` }} /></div><div className="mt-1 flex justify-between text-[9px] text-muted"><span>00:00.0</span><span>{formatTime(sourceDuration)}</span></div></div><RangeControl label="素材入点" value={startMs} minimum={0} maximum={maxStart} step={100} formatValue={formatTime} onChange={previewAt} /><RangeControl label="镜头时长" value={durationMs} minimum={100} maximum={maxDuration} step={100} formatValue={(value) => `${(value / 1000).toFixed(1)} 秒`} onChange={(value) => { setDurationMs(value); if (videoRef.current) seekMedia(videoRef.current, startMs / 1000, 0); }} /><label className="flex items-center gap-2 rounded-lg bg-canvas px-3 py-2 text-[10px] text-muted"><input type="checkbox" checked={loopPreview} onChange={(event) => setLoopPreview(event.target.checked)} />循环预览裁剪后的片段</label><p className="rounded-lg bg-canvas px-3 py-2 text-[10px] leading-4 text-muted">最终使用范围始终等于“素材入点 + 镜头时长”，预览与导出会使用同一组时间参数。</p></div><footer className="shrink-0 flex justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-4"><button type="button" onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs text-text">取消</button><button type="button" onClick={() => { onApply({ sourceStartMs: startMs, sourceEndMs: endMs, durationMs }); onClose(); }} className="rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white">应用片段</button></footer></section></div>;
}

function MaterialHistoryModal({ open, shot, assets, onClose, onApply }: {
  open: boolean;
  shot?: Shot;
  assets: Asset[];
  onClose: () => void;
  onApply: (patch: Partial<Shot>) => void;
}) {
  const [previewVersionId, setPreviewVersionId] = useState<string | null>(null);
  const versions = useMemo(() => {
    if (!shot) return [];
    return [...shot.mediaVersions].sort((left, right) => {
      const leftMaterial = left.parameters.material_history;
      const rightMaterial = right.parameters.material_history;
      const leftRecord = leftMaterial && typeof leftMaterial === "object" ? leftMaterial as Record<string, unknown> : {};
      const rightRecord = rightMaterial && typeof rightMaterial === "object" ? rightMaterial as Record<string, unknown> : {};
      const leftTime = String(leftRecord.last_used_at ?? left.parameters.last_used_at ?? left.createdAt);
      const rightTime = String(rightRecord.last_used_at ?? right.parameters.last_used_at ?? right.createdAt);
      return new Date(rightTime).getTime() - new Date(leftTime).getTime();
    });
  }, [shot]);
  useEffect(() => {
    if (!open || !shot) return;
    setPreviewVersionId(shot.selectedMediaVersionId ?? versions[0]?.id ?? null);
  }, [open, shot, versions]);
  if (!open || !shot) return null;
  const selectedVersion = versions.find((version) => version.id === previewVersionId);
  const selectedAsset = assets.find((asset) => asset.id === selectedVersion?.assetId);
  const materialValue = selectedVersion?.parameters.material_history;
  const material = materialValue && typeof materialValue === "object" ? materialValue as Record<string, unknown> : {};
  const sourceStartMs = numeric(material.source_start_ms, 0);
  const recordedEndMs = numeric(material.source_end_ms, selectedAsset?.durationMs ?? 0);
  const availableDurationMs = selectedAsset?.mediaType === "video"
    ? Math.max(100, Math.min(recordedEndMs || selectedAsset.durationMs, selectedAsset.durationMs) - sourceStartMs)
    : shot.durationMs;
  const nextDurationMs = selectedAsset?.mediaType === "video"
    ? Math.min(shot.durationMs, availableDurationMs)
    : shot.durationMs;
  const originLabels: Record<string, string> = {
    library: "从素材库选择",
    match: "素材匹配",
    ai_image: "AI 生成图片",
    ai_video: "AI 生成视频",
    previous_selection: "之前使用的素材",
  };
  function versionOrigin(version: Shot["mediaVersions"][number]) {
    const value = version.parameters.material_history;
    const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
    const origin = String(record.origin ?? "");
    if (originLabels[origin]) return originLabels[origin];
    if (version.kind === "generated_image") return "AI 生成图片";
    if (["generated_video", "effect_video"].includes(version.kind)) return "AI 生成视频";
    if (version.kind === "matched_segment") return "素材匹配";
    return "从素材库选择";
  }
  return <div className="fixed inset-0 z-[80] grid place-items-center bg-ink/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="material-history-title">
    <section className="grid max-h-[calc(100vh-2rem)] w-full max-w-4xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-line px-5 py-4"><div><h2 id="material-history-title" className="text-sm font-semibold text-text">画面历史</h2><p className="mt-1 text-[11px] text-muted">保留这个镜头曾经选择、匹配或生成过的素材；应用时不改动描述、调色、构图和字幕。</p></div><button type="button" onClick={onClose} aria-label="关闭画面历史" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={16} /></button></header>
      <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_280px] max-md:grid-cols-1">
        <div className="min-h-0 overflow-y-auto p-4"><div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{versions.map((version) => { const asset = assets.find((item) => item.id === version.assetId); const value = version.parameters.material_history; const record = value && typeof value === "object" ? value as Record<string, unknown> : {}; const active = version.id === shot.selectedMediaVersionId; const previewing = version.id === previewVersionId; return <button type="button" key={version.id} onClick={() => setPreviewVersionId(version.id)} className={`overflow-hidden rounded-xl border text-left transition ${previewing ? "border-blue ring-2 ring-blue/10" : "border-line hover:border-blue/40"}`}><div className="relative"><VideoThumb imageUrl={asset?.thumbnailUrl ?? (asset?.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset?.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={asset?.mediaType === "video"} rounded="rounded-none" /><span className={`absolute left-2 top-2 rounded px-1.5 py-0.5 text-[9px] ${active ? "bg-blue text-white" : "bg-black/55 text-white"}`}>{active ? "当前使用" : versionOrigin(version)}</span></div><div className="p-2.5"><strong className="block truncate text-[11px] text-text">{asset?.name ?? "素材已不可用"}</strong><span className="mt-1 block text-[9px] text-muted">{record.segment_id ? `片段 ${formatTime(numeric(record.source_start_ms))}–${formatTime(numeric(record.source_end_ms))}` : versionOrigin(version)}</span><span className="mt-1 block text-[9px] text-muted">{new Date(String(record.last_used_at ?? version.parameters.last_used_at ?? version.createdAt)).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span></div></button>; })}</div>{!versions.length && <div className="grid min-h-64 place-items-center rounded-xl border border-dashed border-line text-center text-xs text-muted">这个镜头还没有历史素材</div>}</div>
        <aside className="min-h-0 overflow-y-auto border-l border-line bg-canvas/40 p-4 max-md:border-l-0 max-md:border-t"><strong className="text-xs text-text">选中素材预览</strong>{selectedVersion ? <><div className="mt-3 overflow-hidden rounded-xl border border-line bg-ink"><VideoThumb imageUrl={selectedAsset?.thumbnailUrl ?? (selectedAsset?.mediaType === "image" ? selectedAsset.mediaUrl : undefined)} videoUrl={selectedAsset?.mediaType === "video" ? selectedAsset.mediaUrl : undefined} showPlay={selectedAsset?.mediaType === "video"} rounded="rounded-none" /></div><strong className="mt-3 block text-xs text-text">{selectedAsset?.name ?? "素材已不可用"}</strong><p className="mt-1 text-[10px] leading-5 text-muted">{versionOrigin(selectedVersion)}{material.segment_id ? ` · ${formatTime(sourceStartMs)}–${formatTime(recordedEndMs)}` : ""}</p>{typeof selectedVersion.parameters.prompt === "string" && selectedVersion.parameters.prompt && <details className="mt-3 rounded-lg border border-line bg-white p-2.5"><summary className="cursor-pointer text-[10px] font-medium text-text">查看生成提示词</summary><p className="mt-2 whitespace-pre-wrap text-[10px] leading-5 text-muted">{selectedVersion.parameters.prompt}</p></details>}{selectedAsset?.mediaType === "video" && nextDurationMs < shot.durationMs && <p className="mt-3 rounded-lg bg-amber/10 p-2 text-[10px] leading-4 text-amber">源片段不足当前 {(shot.durationMs / 1000).toFixed(1)} 秒，应用后镜头将调整为 {(nextDurationMs / 1000).toFixed(1)} 秒。</p>}</> : <p className="mt-3 text-[10px] text-muted">选择左侧的历史素材查看详情。</p>}</aside>
      </div>
      <footer className="flex items-center justify-between gap-3 border-t border-line bg-canvas/60 px-5 py-4"><p className="text-[10px] text-muted">应用旧素材后，当前素材仍会保留在历史中。</p><div className="flex gap-2"><button type="button" onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs text-text">取消</button><button type="button" disabled={!selectedVersion || !selectedAsset} onClick={() => { if (!selectedVersion || !selectedAsset) return; onApply({ selectedMediaVersionId: selectedVersion.id, assetId: selectedVersion.assetId, segmentId: typeof material.segment_id === "string" ? material.segment_id : undefined, visualMode: selectedAsset.mediaType, sourceStartMs, sourceEndMs: sourceStartMs + nextDurationMs, durationMs: nextDurationMs }); onClose(); }} className="rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">应用到当前镜头</button></div></footer>
    </section>
  </div>;
}

function AudioAssetPicker({ role, assets, onClose, onSelect }: {
  role: "voice" | "music" | null; assets: Asset[]; onClose: () => void; onSelect: (assetId: string) => void;
}) {
  if (!role) return null;
  const compatible = assets.filter((asset) => {
    const purpose = String(asset.metadata.purpose ?? "");
    if (role === "voice") return purpose !== "voice_take" && !["music", "ai_music", "sound_effect"].includes(purpose);
    return purpose !== "voice_take" && purpose !== "voiceover_master" && asset.sourceType !== "ai_tts";
  });
  return <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="audio-picker-title"><section className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-2xl"><header className="flex items-start justify-between border-b border-line px-5 py-4"><div><h2 id="audio-picker-title" className="text-sm font-semibold text-text">选择{role === "voice" ? "项目旁白" : "默认背景音乐"}</h2><p className="mt-1 text-[11px] text-muted">{role === "voice" ? "仅显示整片旁白母带和可作为旁白使用的上传音频；单句生成版本不会出现在这里。" : "仅显示音乐和未分类的上传音频；AI 旁白不会出现在这里。"}</p></div><button type="button" aria-label="关闭音频选择" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={15} /></button></header><div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">{compatible.map((asset) => { const purpose = String(asset.metadata.purpose ?? ""); return <article key={asset.id} className="rounded-xl border border-line p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><strong className="block truncate text-xs text-text">{asset.name}</strong><span className="mt-1 block text-[10px] text-muted">{purpose === "voiceover_master" ? "AI 旁白母带" : purpose === "ai_music" ? "AI 音乐" : purpose === "music" ? "背景音乐" : "未分类上传音频"} · {formatTime(asset.durationMs)}</span></div><button type="button" onClick={() => onSelect(asset.id)} className="shrink-0 rounded-lg bg-blue-soft px-3 py-1.5 text-[10px] font-semibold text-blue">选择</button></div>{asset.mediaUrl && <audio controls preload="none" src={asset.mediaUrl} className="mt-3 h-8 w-full" />}</article>; })}{!compatible.length && <div className="rounded-xl border border-dashed border-line p-8 text-center text-xs text-muted">当前项目没有可用于{role === "voice" ? "旁白" : "背景音乐"}的音频，请先通过顶部“添加素材”加入。</div>}</div></section></div>;
}

export function MvpScriptComposer({
  workspace, selectedScene, selectedShot, operationPending, onSelectScene, onSelectShot,
  onUpdateDocumentSettings, onApplyGlobalColorGrade, onUpdateProject, onUpdateScene, onMoveScene, onUpdateShot, onMoveShot, onSplitShot, onRemoveShotAsset, onDuplicateShot, onRestoreSubtitle, onAddScene,
  onAddShot, onDeleteScene, onDeleteShot, onRunOperation, onOpenQuickAI, onOpenVoiceover, onApplyVoiceoverMaster,
}: Props) {
  const [resourceTab, setResourceTab] = useState<ResourceTab>("outline");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("visual");
  const [assetSearch, setAssetSearch] = useState("");
  const [selectedResourceAssetId, setSelectedResourceAssetId] = useState<string | null>(null);
  const [replacementPicking, setReplacementPicking] = useState(false);
  const [assetToApply, setAssetToApply] = useState<Asset | null>(null);
  const [editingSceneId, setEditingSceneId] = useState<string | null>(null);
  const [shotPickerOpen, setShotPickerOpen] = useState(false);
  const [arrangeMode, setArrangeMode] = useState(false);
  const [arrangeDrag, setArrangeDrag] = useState<{ type: "scene"; sceneId: string } | { type: "shot"; sceneId: string; shotId: string } | null>(null);
  const [arrangeDropTarget, setArrangeDropTarget] = useState<{ type: "scene"; id: string } | { type: "shot"; id: string } | null>(null);
  const [audioPickerRole, setAudioPickerRole] = useState<"voice" | "music" | null>(null);
  const [audioApplyPending, setAudioApplyPending] = useState(false);
  const [trimOpen, setTrimOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [globalColorDraft, setGlobalColorDraft] = useState<Record<string, unknown>>({});
  const [globalColorDirty, setGlobalColorDirty] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [previewMuted, setPreviewMuted] = useState(false);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [paneWidths, setPaneWidths] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(EDITOR_PANE_STORAGE_KEY) ?? "null") as Partial<typeof EDITOR_PANE_DEFAULTS> | null;
      return {
        left: typeof stored?.left === "number" ? stored.left : EDITOR_PANE_DEFAULTS.left,
        right: typeof stored?.right === "number" ? stored.right : EDITOR_PANE_DEFAULTS.right,
      };
    } catch {
      return EDITOR_PANE_DEFAULTS;
    }
  });
  const editorGridRef = useRef<HTMLDivElement | null>(null);
  const arrangeItemRefs = useRef(new Map<string, HTMLElement>());
  const arrangePreviousRects = useRef(new Map<string, DOMRect>());
  const shotPickerRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const stageHostRef = useRef<HTMLDivElement | null>(null);
  const [stageAvailable, setStageAvailable] = useState({ width: 1, height: 1 });
  const playheadRef = useRef(0);
  const scenes = workspace.document.storyboard.scenes;
  const model = useMemo(() => buildCompositionModel(workspace), [workspace]);
  const mainTrack = workspace.document.timeline.tracks.find((track) => track.id === "main-video" || track.role === "story");
  const activeShot = compositionShotAt(model, playheadMs);
  const nextShot = nextCompositionShot(model, activeShot);
  const transition = transitionState(activeShot, nextShot, playheadMs);
  const visibleAssets = useMemo(() => {
    const query = assetSearch.trim().toLowerCase();
    return workspace.linkedAssets.filter((asset) => asset.mediaType !== "audio" && (!query || asset.name.toLowerCase().includes(query)));
  }, [assetSearch, workspace.linkedAssets]);
  const matchableAssetCount = workspace.linkedAssets.filter((asset) => asset.mediaType !== "audio").length;
  const audioAssets = workspace.linkedAssets.filter((asset) => asset.mediaType === "audio");
  const audioMix = workspace.document.settings.globalAudio;
  const globalColorGrade = useMemo(() => {
    const value = workspace.document.settings.visualSettings.colorGrade;
    return value && typeof value === "object" ? value as Record<string, unknown> : {};
  }, [workspace.document.settings.visualSettings.colorGrade]);
  const selectedAsset = workspace.linkedAssets.find((asset) => asset.id === selectedShot?.assetId);
  const selectedEffectiveAdjust = selectedShot
    ? effectiveShotAdjust(selectedShot, workspace.document.settings.visualSettings)
    : {};
  const selectedAdjustIsOverride = selectedShot
    ? String(selectedShot.adjust.mode ?? (Object.keys(selectedShot.adjust).length ? "override" : "inherit")) === "override"
    : false;
  const shotAdjustCounts = useMemo(() => {
    const shots = scenes.flatMap((scene) => scene.shots);
    const overridden = shots.filter((shot) => {
      const values = Object.keys(shot.adjust).filter((key) => key !== "mode");
      return String(shot.adjust.mode ?? (values.length ? "override" : "inherit")) === "override";
    }).length;
    return { total: shots.length, overridden, inherited: shots.length - overridden };
  }, [scenes]);
  const previewVisualSettings = globalColorDirty
    ? { ...workspace.document.settings.visualSettings, colorGrade: globalColorDraft }
    : workspace.document.settings.visualSettings;
  const editingScene = scenes.find((scene) => scene.id === editingSceneId);
  const editingSceneIndex = editingScene ? scenes.findIndex((scene) => scene.id === editingScene.id) : -1;
  const editingSceneLastShot = editingScene?.shots.at(-1);
  const selectedVoiceAsset = audioAssets.find((asset) => asset.id === audioMix.voiceAssetId);
  const selectedMusicAsset = audioAssets.find((asset) => asset.id === audioMix.musicAssetId);
  const selectedShotMeta = selectedShot?.id ? model.shots.find((shot) => shot.id === selectedShot.id) : undefined;
  const selectedSceneScope = selectedScene?.id ? workspace.document.globalScopes.scenes[selectedScene.id] ?? {} : {};
  const selectedShotMusic = scopeReference(selectedShot?.audioSettings.backgroundMusic);
  const selectedSceneMusic = scopeReference(selectedSceneScope.backgroundMusic);
  const filmMusic = scopeReference(workspace.document.globalScopes.film.backgroundMusic);
  const projectMusic = audioMix.musicAssetId ? { assetId: audioMix.musicAssetId, volume: numeric(audioMix.musicVolume, 24) } : null;
  const effectiveMusic = selectedShotMusic ?? selectedSceneMusic ?? filmMusic ?? projectMusic;
  const effectiveMusicSource = selectedShotMusic ? "当前镜头覆盖" : selectedSceneMusic ? "继承自当前场景" : filmMusic ? "继承自全片设置" : projectMusic ? "继承自项目默认" : "未配置";

  useEffect(() => { playheadRef.current = playheadMs; }, [playheadMs]);
  useEffect(() => {
    if (!shotPickerOpen) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!shotPickerRef.current?.contains(event.target as Node)) setShotPickerOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShotPickerOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [shotPickerOpen]);
  useLayoutEffect(() => {
    if (!arrangePreviousRects.current.size) return;
    arrangeItemRefs.current.forEach((element, key) => {
      const previous = arrangePreviousRects.current.get(key);
      if (!previous) return;
      const current = element.getBoundingClientRect();
      const deltaX = previous.left - current.left;
      const deltaY = previous.top - current.top;
      if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) return;
      element.animate([
        { transform: `translate(${deltaX}px, ${deltaY}px)` },
        { transform: "translate(0, 0)" },
      ], {
        duration: 220,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      });
    });
    arrangePreviousRects.current.clear();
  }, [scenes]);
  useEffect(() => {
    localStorage.setItem(EDITOR_PANE_STORAGE_KEY, JSON.stringify(paneWidths));
  }, [paneWidths]);
  useEffect(() => {
    if (!globalColorDirty) setGlobalColorDraft(globalColorGrade);
  }, [globalColorDirty, globalColorGrade]);
  useEffect(() => {
    const host = stageHostRef.current;
    if (!host) return;
    const update = () => setStageAvailable({
      width: host.clientWidth,
      height: Math.min(460, Math.max(240, window.innerHeight * 0.46)),
    });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(host);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let previous = performance.now();
    let lastCommit = previous - 34;
    const tick = (now: number) => {
      const elapsed = Math.min(250, Math.max(0, now - previous));
      previous = now;
      const next = playheadRef.current + elapsed;
      if (next >= model.durationMs) {
        playheadRef.current = model.durationMs;
        setPlayheadMs(model.durationMs);
        setPlaying(false);
        return;
      }
      playheadRef.current = next;
      // The media decoder continues at native frame rate. React only needs a
      // 30 fps snapshot for subtitles, controls and the timeline playhead.
      if (now - lastCommit >= 1000 / 30) {
        lastCommit = now;
        setPlayheadMs(next);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [model.durationMs, playing]);
  useEffect(() => {
    if (playing || !selectedShot?.id) return;
    const selectedMeta = model.shots.find((shot) => shot.id === selectedShot.id);
    if (selectedMeta && activeShot?.id !== selectedShot.id) setPlayheadMs(selectedMeta.startMs);
  }, [activeShot?.id, model.shots, playing, selectedShot?.id]);

  function seek(nextMs: number, selectActiveShot = true) {
    const value = clamp(nextMs, 0, model.durationMs);
    playheadRef.current = value;
    setPlayheadMs(value);
    if (selectActiveShot) {
      const target = compositionShotAt(model, value);
      if (target?.id && target.id !== selectedShot?.id) onSelectShot(target.id);
    }
  }
  function selectShotForPreview(shotId: string | null) {
    setPlaying(false);
    const target = model.shots.find((shot) => shot.id === shotId);
    if (target) seek(target.startMs, false);
    onSelectShot(shotId);
  }
  function togglePlayback() {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (playheadRef.current >= model.durationMs) seek(0);
    setPlaying(true);
  }
  function applyAsset(asset?: Asset) {
    if (!selectedScene?.id || !selectedShot?.id) return;
    const durationMs = asset?.mediaType === "video" && asset.durationMs > 0
      ? Math.min(selectedShot.durationMs, asset.durationMs)
      : selectedShot.durationMs;
    onUpdateShot(selectedScene.id, selectedShot.id, {
      assetId: asset?.id,
      visualMode: asset?.mediaType === "image" ? "image" : asset ? "video" : undefined,
      selectedMediaVersionId: undefined,
      sourceStartMs: 0,
      sourceEndMs: durationMs,
      durationMs,
    });
    setAssetToApply(null);
    setReplacementPicking(false);
  }
  function chooseCandidate(candidateId: string) {
    const candidate = selectedShot?.candidates.find((item) => item.id === candidateId);
    if (!candidate) return;
    const segment = workspace.linkedAssets.flatMap((asset) => asset.segments.map((item) => ({ asset, segment: item }))).find(({ segment }) => segment.id === candidate.segmentId);
    if (!segment) return;
    const sourceStartMs = candidate.rangeStartMs || segment.segment.startMs;
    const requestedEndMs = candidate.rangeEndMs || segment.segment.endMs;
    const availableDurationMs = Math.max(100, requestedEndMs - sourceStartMs);
    const durationMs = segment.asset.mediaType === "video"
      ? Math.min(selectedShot?.durationMs ?? availableDurationMs, availableDurationMs)
      : selectedShot?.durationMs ?? availableDurationMs;
    patchSelectedShot({
      assetId: segment.asset.id,
      segmentId: segment.segment.id,
      visualMode: segment.asset.mediaType === "image" ? "image" : "video",
      selectedMediaVersionId: undefined,
      sourceStartMs,
      sourceEndMs: sourceStartMs + durationMs,
      durationMs,
    });
  }
  function patchSelectedShot(patch: Partial<Shot>) {
    if (selectedScene?.id && selectedShot?.id) onUpdateShot(selectedScene.id, selectedShot.id, patch);
  }
  function patchEditingSceneTransition(patch: Record<string, unknown>) {
    if (!editingScene?.id || !editingSceneLastShot?.id) return;
    onUpdateShot(editingScene.id, editingSceneLastShot.id, {
      transition: { ...editingSceneLastShot.transition, ...patch },
    });
  }
  function splitSelectedShot() {
    if (!selectedScene?.id || !selectedShot?.id || selectedShot.durationMs < 200) return;
    const meta = model.shots.find((shot) => shot.id === selectedShot.id);
    const offsetMs = meta ? playheadRef.current - meta.startMs : -1;
    if (offsetMs < 200 || offsetMs > selectedShot.durationMs - 200) return;
    setPlaying(false);
    onSplitShot(selectedScene.id, selectedShot.id, Math.round(offsetMs));
  }

  function selectMotionPreset(type: string) {
    patchRecord("motion", { type, ...(type === "none" ? {} : { strength: numeric(selectedShot?.motion.strength, 55) }) });
    if (type === "none" || !selectedShotMeta) return;
    seek(selectedShotMeta.startMs, false);
    setPlaying(true);
  }
  function patchRecord(field: "adjust" | "motion" | "transition" | "subtitleSettings" | "audioSettings", patch: Record<string, unknown>) {
    if (!selectedShot) return;
    patchSelectedShot({ [field]: { ...selectedShot[field], ...patch } });
  }
  function patchAudioMix(patch: Partial<ProjectAudioMix>) {
    onUpdateDocumentSettings({ globalAudio: { ...audioMix, ...patch } });
  }
  function patchGlobalColorGrade(patch: Record<string, unknown>) {
    setGlobalColorDraft((current) => ({ ...(globalColorDirty ? current : globalColorGrade), ...patch }));
    setGlobalColorDirty(true);
  }
  function resetGlobalColorDraft() {
    setGlobalColorDraft({});
    setGlobalColorDirty(true);
  }
  function discardGlobalColorDraft() {
    setGlobalColorDraft(globalColorGrade);
    setGlobalColorDirty(false);
  }
  function applyGlobalColorDraft(clearShotOverrides: boolean) {
    if (clearShotOverrides && shotAdjustCounts.overridden > 0 && !window.confirm(
      `覆盖全部镜头会清除 ${shotAdjustCounts.overridden} 个镜头的单独调色，是否继续？`,
    )) return;
    onApplyGlobalColorGrade(globalColorDraft, clearShotOverrides);
    setGlobalColorDirty(false);
  }
  async function setDefaultAudioAsset(role: "voice" | "music", assetId?: string) {
    const asset = audioAssets.find((item) => item.id === assetId);
    if (role === "voice" && assetId && asset?.metadata.purpose === "voiceover_master") {
      setAudioApplyPending(true);
      try {
        await onApplyVoiceoverMaster(assetId);
        setAudioPickerRole(null);
      } finally {
        setAudioApplyPending(false);
      }
      return;
    }
    patchAudioMix(role === "voice"
      ? { voiceAssetId: assetId, voiceMuted: assetId ? false : audioMix.voiceMuted }
      : { musicAssetId: assetId, musicMuted: assetId ? false : audioMix.musicMuted });
    setAudioPickerRole(null);
  }
  function toggleFullscreen() {
    if (!stageRef.current) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stageRef.current.requestFullscreen();
  }

  function moveSceneTo(sceneId: string, targetIndex: number) {
    const from = scenes.findIndex((scene) => scene.id === sceneId);
    if (from < 0 || from === targetIndex) return;
    const direction: -1 | 1 = targetIndex > from ? 1 : -1;
    for (let index = from; index !== targetIndex; index += direction) onMoveScene(sceneId, direction);
  }
  function setArrangeItemRef(key: string, element: HTMLElement | null) {
    if (element) arrangeItemRefs.current.set(key, element);
    else arrangeItemRefs.current.delete(key);
  }
  function showArrangeDropTarget(target: { type: "scene" | "shot"; id: string }) {
    setArrangeDropTarget((current) => current?.type === target.type && current.id === target.id ? current : target);
  }
  function captureArrangePositions(type: "scene" | "shot") {
    const prefix = `${type}:`;
    arrangePreviousRects.current = new Map(
      [...arrangeItemRefs.current.entries()]
        .filter(([key]) => key.startsWith(prefix))
        .map(([key, element]) => [key, element.getBoundingClientRect()]),
    );
  }
  function moveShotTo(sceneId: string, shotId: string, targetIndex: number) {
    const scene = scenes.find((item) => item.id === sceneId);
    const from = scene?.shots.findIndex((shot) => shot.id === shotId) ?? -1;
    if (from < 0 || from === targetIndex) return;
    const direction: -1 | 1 = targetIndex > from ? 1 : -1;
    for (let index = from; index !== targetIndex; index += direction) onMoveShot(sceneId, shotId, direction);
  }
  function dropScene(targetIndex: number, event: React.DragEvent) {
    event.preventDefault();
    if (arrangeDrag?.type === "scene") {
      const sourceIndex = scenes.findIndex((scene) => scene.id === arrangeDrag.sceneId);
      if (sourceIndex >= 0 && sourceIndex !== targetIndex) {
        captureArrangePositions("scene");
        moveSceneTo(arrangeDrag.sceneId, targetIndex);
      }
    }
    setArrangeDrag(null);
    setArrangeDropTarget(null);
  }
  function dropShot(sceneId: string, targetIndex: number, event: React.DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (arrangeDrag?.type === "shot" && arrangeDrag.sceneId === sceneId) {
      const scene = scenes.find((item) => item.id === sceneId);
      const sourceIndex = scene?.shots.findIndex((shot) => shot.id === arrangeDrag.shotId) ?? -1;
      if (sourceIndex >= 0 && sourceIndex !== targetIndex) {
        captureArrangePositions("shot");
        moveShotTo(sceneId, arrangeDrag.shotId, targetIndex);
      }
    }
    setArrangeDrag(null);
    setArrangeDropTarget(null);
  }

  function paneWidthLimit(side: EditorPaneSide) {
    const total = editorGridRef.current?.clientWidth ?? 1440;
    const reserved = EDITOR_SPLITTER_WIDTH * 2 + EDITOR_PANE_MINIMUMS.center;
    return side === "left"
      ? Math.max(EDITOR_PANE_MINIMUMS.left, total - paneWidths.right - reserved)
      : Math.max(EDITOR_PANE_MINIMUMS.right, total - paneWidths.left - reserved);
  }
  function adjustPaneWidth(side: EditorPaneSide, nextWidth: number) {
    const minimum = EDITOR_PANE_MINIMUMS[side];
    const maximum = paneWidthLimit(side);
    setPaneWidths((current) => ({ ...current, [side]: Math.round(clamp(nextWidth, minimum, maximum)) }));
  }
  function startPaneResize(side: EditorPaneSide, event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = paneWidths[side];
    const onPointerMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      adjustPaneWidth(side, startWidth + (side === "left" ? delta : -delta));
    };
    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }
  function paneSplitter(side: EditorPaneSide) {
    const label = side === "left" ? "调整场景与分镜编辑区域宽度" : "调整分镜编辑与全片预览区域宽度";
    return <button
      type="button"
      aria-label={label}
      title={`${label}；双击恢复默认宽度`}
      onPointerDown={(event) => startPaneResize(side, event)}
      onDoubleClick={() => adjustPaneWidth(side, EDITOR_PANE_DEFAULTS[side])}
      onKeyDown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        adjustPaneWidth(side, paneWidths[side] + direction * (side === "left" ? 16 : -16));
      }}
      className={`group relative z-20 row-[1/4] min-h-0 cursor-col-resize bg-line/80 outline-none transition hover:bg-blue/35 focus-visible:bg-blue/40 ${side === "left" ? "col-[2]" : "col-[4]"}`}
    ><span className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 rounded-full bg-transparent transition group-hover:inset-y-4 group-hover:bg-blue group-focus-visible:inset-y-4 group-focus-visible:bg-blue" /></button>;
  }

  const voiceoverQuery = useQuery({
    queryKey: ["voiceover", workspace.project.id, workspace.document.revision],
    queryFn: () => getVoiceoverWorkspace(workspace.project.id),
    enabled: workspace.project.id !== "__preview__",
    retry: false,
    staleTime: 15_000,
  });
  const timelineVoiceLines = useMemo(() => (voiceoverQuery.data?.lines ?? [])
    .filter((line) => line.captionEnabled || line.voiceEnabled)
    .map((line) => {
      const take = line.takes.find((item) => item.id === line.selectedTakeId) ?? line.takes.find((item) => item.isSelected);
      return {
        ...line,
        durationMs: Math.max(1, line.endMs - line.startMs),
        audioDurationMs: take?.durationMs ?? 0,
      };
    }), [voiceoverQuery.data?.lines]);
  const selectedShotVoiceLines = timelineVoiceLines.filter((line) => selectedShotMeta
    && line.startMs < selectedShotMeta.endMs
    && line.endMs > selectedShotMeta.startMs);
  const selectedShotVoiceStatus = selectedShotVoiceLines.some((line) => line.status === "stale")
    ? "存在过期旁白"
    : selectedShotVoiceLines.some((line) => line.status === "timing_conflict" || line.status === "failed")
      ? "需要处理"
      : selectedShotVoiceLines.some((line) => line.status === "generating")
        ? "生成中"
        : selectedShotVoiceLines.some((line) => line.status === "ready")
          ? "已生成"
          : "未生成";
  const projectVoiceStatus = timelineVoiceLines.some((line) => line.status === "stale")
    ? "存在过期旁白"
    : timelineVoiceLines.some((line) => line.status === "generating")
      ? "生成中"
      : timelineVoiceLines.some((line) => line.status === "ready")
        ? `已生成 ${timelineVoiceLines.filter((line) => line.status === "ready").length} 条`
        : selectedVoiceAsset ? "已选择旁白母带" : "尚未生成";
  const selectedSplitOffsetMs = selectedShotMeta ? playheadMs - selectedShotMeta.startMs : -1;
  const canSplitSelectedShot = Boolean(selectedShotMeta)
    && selectedSplitOffsetMs >= 200
    && selectedSplitOffsetMs <= (selectedShot?.durationMs ?? 0) - 200;
  const selectedSceneShotIndex = selectedScene?.shots.findIndex((shot) => shot.id === selectedShot?.id) ?? -1;
  const previousShot = selectedSceneShotIndex > 0 ? selectedScene?.shots[selectedSceneShotIndex - 1] : undefined;
  const nextEditingShot = selectedScene && selectedSceneShotIndex >= 0 && selectedSceneShotIndex < selectedScene.shots.length - 1
    ? selectedScene.shots[selectedSceneShotIndex + 1]
    : undefined;

  return <div
    ref={editorGridRef}
    className="grid min-h-0 flex-1 grid-rows-[auto_258px_minmax(0,1fr)] overflow-hidden bg-[#e9eaed]"
    style={{ gridTemplateColumns: `${paneWidths.left}px ${EDITOR_SPLITTER_WIDTH}px minmax(${EDITOR_PANE_MINIMUMS.center}px,1fr) ${EDITOR_SPLITTER_WIDTH}px ${paneWidths.right}px` }}
  >
    <div className="contents">
      <aside className="col-[1] row-[1/4] flex min-h-0 flex-col bg-white">
        <nav className="grid shrink-0 grid-cols-3 gap-1 border-b border-line p-2">{resources.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setResourceTab(id)} className={`flex min-w-0 items-center justify-center gap-1 rounded-lg px-1 py-2 text-[10px] ${resourceTab === id ? "bg-blue-soft font-semibold text-blue" : "text-muted hover:bg-canvas"}`}><Icon size={14} /><span className="truncate">{label}</span></button>)}</nav>
        <div className="min-w-0 flex-1 overflow-y-auto p-3">
          {resourceTab === "outline" && <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div><strong className="text-sm text-text">场景</strong><p className="text-[10px] text-muted">{scenes.length} 个场景 · {model.shots.length} 个镜头</p></div>
              <details className="group relative shrink-0">
                <summary
                  aria-label="更多场景操作"
                  title="更多操作"
                  className={`relative grid h-8 w-8 cursor-pointer list-none place-items-center rounded-md border transition ${arrangeMode ? "border-ink bg-ink text-white" : "border-line text-muted hover:border-blue hover:text-blue"}`}
                >
                  <MoreHorizontal size={15} />
                  {arrangeMode && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-white bg-blue" />}
                </summary>
                <div className="absolute right-0 top-9 z-30 w-36 rounded-lg border border-line bg-white p-1 shadow-lg">
                  <button
                    type="button"
                    disabled={arrangeMode}
                    onClick={(event) => {
                      onAddScene();
                      (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open");
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[10px] text-text hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-35"
                  ><Plus size={13} className="text-blue" />新增场景</button>
                  <button
                    type="button"
                    onClick={(event) => {
                      setArrangeMode((value) => !value);
                      setArrangeDrag(null);
                      setArrangeDropTarget(null);
                      arrangePreviousRects.current.clear();
                      (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open");
                    }}
                    className={`flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[10px] hover:bg-canvas ${arrangeMode ? "font-semibold text-blue" : "text-text"}`}
                  ><GripVertical size={13} className={arrangeMode ? "text-blue" : "text-muted"} />{arrangeMode ? "完成编排" : "编排顺序"}</button>
                </div>
              </details>
            </div>
            {arrangeMode && <p className="mb-3 rounded-lg bg-blue-soft/60 px-2.5 py-2 text-[9px] leading-4 text-muted">拖动场景可调整场景顺序；拖动镜头可在所属场景内调整顺序。镜头暂不支持跨场景移动。</p>}
            <div className="space-y-2">{scenes.map((scene, sceneIndex) => {
              const active = scene.id === selectedScene?.id;
              const dragging = arrangeDrag?.type === "scene" && arrangeDrag.sceneId === scene.id;
              const dropTarget = arrangeDropTarget?.type === "scene" && arrangeDropTarget.id === scene.id;
              return <article
                key={scene.id ?? sceneIndex}
                ref={(element) => { if (scene.id) setArrangeItemRef(`scene:${scene.id}`, element); }}
                onDragOver={(event) => {
                  if (arrangeMode && arrangeDrag?.type === "scene" && scene.id) {
                    event.preventDefault();
                    showArrangeDropTarget({ type: "scene", id: scene.id });
                  }
                }}
                onDrop={(event) => dropScene(sceneIndex, event)}
                className={`group overflow-hidden rounded-xl border transition-[border-color,background-color,box-shadow,opacity] duration-150 ${dragging ? "border-blue opacity-45" : dropTarget ? "border-blue bg-blue-soft/50 ring-1 ring-blue/20" : active ? "border-blue bg-blue-soft/30" : "border-line"} ${arrangeMode ? "will-change-transform" : ""}`}
              >
                <div
                  draggable={arrangeMode}
                  onDragStart={() => {
                    if (scene.id) {
                      setArrangeDrag({ type: "scene", sceneId: scene.id });
                      setArrangeDropTarget(null);
                    }
                  }}
                  onDragEnd={() => { setArrangeDrag(null); setArrangeDropTarget(null); }}
                  className={`flex items-start gap-1 p-2.5 ${arrangeMode ? "cursor-grab active:cursor-grabbing" : ""}`}
                >
                  {arrangeMode && <GripVertical size={14} className="mt-1 shrink-0 text-muted" />}
                  <button type="button" onClick={() => !arrangeMode && onSelectScene(scene.id ?? null)} className="min-w-0 flex-1 text-left"><span className="text-[10px] font-medium text-muted">场景 {sceneIndex + 1} · {scene.shots.length} 镜头</span><strong className="mt-1 block truncate text-xs text-text">{scene.outline || "未命名场景"}</strong></button>
                  {!arrangeMode && <button type="button" aria-label={`编辑场景 ${sceneIndex + 1}`} title="编辑场景" onClick={() => { if (!active) onSelectScene(scene.id ?? null); setEditingSceneId(scene.id ?? null); }} className={`grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted transition hover:bg-white hover:text-blue focus:opacity-100 ${active ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"}`}><Pencil size={13} /></button>}
                </div>
                {(active || arrangeMode) && <div className="border-t border-blue/10 px-2 pb-2 pt-1">{scene.shots.map((shot, index) => {
                  const shotDragging = arrangeDrag?.type === "shot" && arrangeDrag.shotId === shot.id;
                  const shotDropTarget = arrangeDropTarget?.type === "shot" && arrangeDropTarget.id === shot.id;
                  return <button
                    type="button"
                    draggable={arrangeMode}
                    key={shot.id ?? index}
                    ref={(element) => { if (shot.id) setArrangeItemRef(`shot:${shot.id}`, element); }}
                    onDragStart={(event) => {
                      event.stopPropagation();
                      if (scene.id && shot.id) {
                        setArrangeDrag({ type: "shot", sceneId: scene.id, shotId: shot.id });
                        setArrangeDropTarget(null);
                      }
                    }}
                    onDragEnd={() => { setArrangeDrag(null); setArrangeDropTarget(null); }}
                    onDragOver={(event) => {
                      if (arrangeMode && arrangeDrag?.type === "shot" && arrangeDrag.sceneId === scene.id && shot.id) {
                        event.preventDefault();
                        event.stopPropagation();
                        showArrangeDropTarget({ type: "shot", id: shot.id });
                      }
                    }}
                    onDrop={(event) => scene.id && dropShot(scene.id, index, event)}
                    onClick={() => !arrangeMode && selectShotForPreview(shot.id ?? null)}
                    className={`mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px] transition-[background-color,box-shadow,opacity] duration-150 ${shotDragging ? "opacity-40" : shotDropTarget ? "bg-blue-soft/70 text-blue ring-1 ring-blue/30" : shot.id === selectedShot?.id ? "bg-blue text-white" : "text-muted hover:bg-white"} ${arrangeMode ? "cursor-grab will-change-transform active:cursor-grabbing" : ""}`}
                  >
                    {arrangeMode && <GripVertical size={12} className="shrink-0" />}
                    <span>{index + 1}</span><span className="truncate">{shot.description || "空镜头"}</span>
                  </button>;
                })}</div>}
              </article>;
            })}</div>
          </>}
          {resourceTab === "assets" && <><div className="mb-3"><strong className="text-sm text-text">项目画面素材</strong><p className="mt-1 text-[10px] leading-4 text-muted">点击只查看素材，使用“应用”才会替换当前镜头。</p></div><label className="mb-3 flex items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-muted"><Search size={13} /><input value={assetSearch} onChange={(event) => setAssetSearch(event.target.value)} placeholder="搜索项目素材" className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><div className="grid grid-cols-2 gap-2">{visibleAssets.map((asset) => { const selected = asset.id === selectedResourceAssetId; const inUse = asset.id === selectedShot?.assetId; return <article key={asset.id} className={`overflow-hidden rounded-lg border ${selected ? "border-blue ring-1 ring-blue/20" : "border-line"}`}><button type="button" onClick={() => setSelectedResourceAssetId(asset.id)} className="w-full text-left"><div className="relative aspect-video bg-canvas"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={false} />{inUse && <span className="absolute left-1.5 top-1.5 rounded bg-blue px-1.5 py-0.5 text-[8px] text-white">当前镜头</span>}</div><span className="block truncate p-1.5 text-[10px] text-text">{asset.name}</span></button>{selected && <div className="border-t border-line p-1.5"><button type="button" disabled={inUse || !selectedShot} onClick={() => setAssetToApply(asset)} className="w-full rounded-md bg-blue-soft py-1.5 text-[9px] font-semibold text-blue disabled:opacity-40">{inUse ? "正在使用" : "应用到当前镜头"}</button></div>}</article>; })}</div>{!visibleAssets.length && <div className="py-12 text-center text-xs text-muted">当前项目没有匹配的画面素材，请从顶部“添加素材”加入。</div>}</>}
          {resourceTab === "settings" && <div>
            <div><strong className="text-sm text-text">项目设置</strong><p className="mt-1 text-[10px] text-muted">修改项目名称、默认声音和画幅。</p></div>
            <label className="mt-4 block text-[11px] font-medium text-muted">项目名称<input value={workspace.project.name} onChange={(event) => onUpdateProject({ name: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line p-2.5 text-sm text-text" /></label>
            <section className="mt-4 rounded-xl border border-line p-3"><div className="flex items-start justify-between gap-2"><div className="flex items-center gap-2"><Mic2 size={14} className="text-blue" /><strong className="text-xs">项目旁白</strong></div><span className={`rounded px-1.5 py-0.5 text-[9px] ${projectVoiceStatus.includes("过期") ? "bg-amber/10 text-amber" : selectedVoiceAsset ? "bg-teal/10 text-teal" : "bg-canvas text-muted"}`}>{projectVoiceStatus}</span></div>{selectedVoiceAsset ? <><div className="mt-3 rounded-lg bg-canvas p-2.5"><strong className="block truncate text-[11px] text-text">{selectedVoiceAsset.name}</strong><span className="mt-1 block text-[9px] text-muted">{selectedVoiceAsset.sourceType === "ai_tts" ? "AI 旁白母带" : "已有音频"} · {formatTime(selectedVoiceAsset.durationMs)}</span>{selectedVoiceAsset.mediaUrl && <audio controls preload="none" src={selectedVoiceAsset.mediaUrl} className="mt-2 h-8 w-full" />}</div><div className="mt-2 grid grid-cols-2 gap-2"><button type="button" onClick={() => setAudioPickerRole("voice")} className="rounded-lg border border-line py-1.5 text-[10px] text-text">替换</button><button type="button" onClick={() => setDefaultAudioAsset("voice", undefined)} className="rounded-lg border border-line py-1.5 text-[10px] text-red">移除</button></div></> : <button type="button" onClick={() => setAudioPickerRole("voice")} className="mt-3 w-full rounded-lg border border-dashed border-line py-3 text-[10px] text-muted hover:border-blue hover:text-blue">选择已有旁白音频</button>}<button type="button" onClick={onOpenVoiceover} className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg bg-ink py-2 text-xs font-semibold text-white"><Sparkles size={13} />生成 / 更新 AI 旁白</button><div className="mt-3"><RangeControl label="旁白音量" value={numeric(audioMix.voiceVolume, 100)} minimum={0} maximum={100} suffix="%" onChange={(voiceVolume) => patchAudioMix({ voiceVolume })} /></div><label className="mt-2 flex items-center gap-2 text-[10px] text-muted"><input type="checkbox" checked={!audioMix.voiceMuted} onChange={(event) => patchAudioMix({ voiceMuted: !event.target.checked })} />启用项目旁白</label></section>
            <section className="mt-3 rounded-xl border border-line p-3"><div className="flex items-center gap-2"><Music2 size={14} className="text-blue" /><strong className="text-xs">默认背景音乐</strong></div>{selectedMusicAsset ? <><div className="mt-3 rounded-lg bg-canvas p-2.5"><strong className="block truncate text-[11px] text-text">{selectedMusicAsset.name}</strong><span className="mt-1 block text-[9px] text-muted">背景音乐 · {formatTime(selectedMusicAsset.durationMs)}</span>{selectedMusicAsset.mediaUrl && <audio controls preload="none" src={selectedMusicAsset.mediaUrl} className="mt-2 h-8 w-full" />}</div><div className="mt-2 grid grid-cols-2 gap-2"><button type="button" onClick={() => setAudioPickerRole("music")} className="rounded-lg border border-line py-1.5 text-[10px] text-text">替换</button><button type="button" onClick={() => setDefaultAudioAsset("music", undefined)} className="rounded-lg border border-line py-1.5 text-[10px] text-red">移除</button></div></> : <button type="button" onClick={() => setAudioPickerRole("music")} className="mt-3 w-full rounded-lg border border-dashed border-line py-3 text-[10px] text-muted hover:border-blue hover:text-blue">选择项目音频作为背景音乐</button>}<div className="mt-3"><RangeControl label="音乐音量" value={numeric(audioMix.musicVolume, 24)} minimum={0} maximum={100} suffix="%" onChange={(musicVolume) => patchAudioMix({ musicVolume })} /></div><label className="mt-2 flex items-center gap-2 text-[10px] text-muted"><input type="checkbox" checked={!audioMix.musicMuted} onChange={(event) => patchAudioMix({ musicMuted: !event.target.checked })} />启用背景音乐</label><label className="mt-2 flex items-center gap-2 text-[10px] text-muted"><input type="checkbox" checked={audioMix.duckingEnabled !== false} onChange={(event) => patchAudioMix({ duckingEnabled: event.target.checked })} />旁白出现时自动压低音乐</label></section>
            <section className="mt-3 rounded-xl border border-line p-3">
              <header className="flex items-start justify-between gap-3"><div><strong className="text-xs text-text">全片滤镜与调色</strong><p className="mt-1 text-[9px] leading-4 text-muted">{shotAdjustCounts.inherited} 个镜头继承全片 · {shotAdjustCounts.overridden} 个单独调整</p></div><button type="button" onClick={resetGlobalColorDraft} className="shrink-0 text-[10px] text-muted"><RotateCcw size={11} className="inline" /> 重置草稿</button></header>
              <p className="mt-2 rounded-lg bg-canvas px-2.5 py-2 text-[9px] leading-4 text-muted">调整时只做实时预览，点击应用后才保存。默认保留已单独调色的镜头。</p>
              <div className="mt-3 grid grid-cols-4 gap-1">{filterPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchGlobalColorGrade({ filterPreset: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(globalColorDraft.filterPreset ?? "original") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>
              <div className="mt-3 space-y-2"><RangeControl label="亮度" value={numeric(globalColorDraft.brightness)} minimum={-100} maximum={100} onChange={(brightness) => patchGlobalColorGrade({ brightness })} /><RangeControl label="对比度" value={numeric(globalColorDraft.contrast)} minimum={-100} maximum={100} onChange={(contrast) => patchGlobalColorGrade({ contrast })} /><RangeControl label="饱和度" value={numeric(globalColorDraft.saturation)} minimum={-100} maximum={100} onChange={(saturation) => patchGlobalColorGrade({ saturation })} /><RangeControl label="色温" value={numeric(globalColorDraft.temperature)} minimum={-100} maximum={100} onChange={(temperature) => patchGlobalColorGrade({ temperature })} /></div>
              <div className="mt-3 space-y-2 border-t border-line pt-3"><div className="grid grid-cols-2 gap-2"><button type="button" disabled={!globalColorDirty} onClick={discardGlobalColorDraft} className="rounded-lg border border-line py-2 text-[10px] text-muted disabled:cursor-not-allowed disabled:opacity-35">取消更改</button><button type="button" disabled={!globalColorDirty} onClick={() => applyGlobalColorDraft(false)} className="rounded-lg bg-blue py-2 text-[10px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-35">应用并保留单独调色</button></div>{shotAdjustCounts.overridden > 0 && <button type="button" disabled={!globalColorDirty} onClick={() => applyGlobalColorDraft(true)} className="w-full rounded-lg border border-amber/30 py-2 text-[10px] font-medium text-amber disabled:cursor-not-allowed disabled:opacity-35">覆盖全部镜头（清除 {shotAdjustCounts.overridden} 个单独设置）</button>}{!globalColorDirty && <p className="text-center text-[9px] text-muted">当前设置已应用；调整任一参数后即可再次应用。</p>}</div>
            </section>
            <fieldset className="mt-4"><legend className="text-xs font-semibold text-text">画幅</legend><div className="mt-2 grid grid-cols-2 gap-2">{(["16:9", "9:16", "1:1", "4:3"] as const).map((value) => <button key={value} type="button" onClick={() => onUpdateDocumentSettings({ aspectRatio: value })} className={`rounded-lg border py-2 text-xs ${workspace.document.settings.aspectRatio === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value}</button>)}</div></fieldset>
          </div>}
        </div>
      </aside>
      {paneSplitter("left")}

      <main className="col-[5] row-[1] overflow-hidden bg-[#f5f5f6]">
        <header className="flex h-10 shrink-0 items-center justify-between border-b border-line bg-white px-3"><div><strong className="text-xs text-text">全片预览</strong><span className="ml-2 text-[10px] text-muted">播放时不会切换正在编辑的镜头</span></div><span className="rounded-md bg-canvas px-2 py-1 text-[9px] text-muted">{workspace.document.settings.aspectRatio} · 实时合成</span></header>
        <div className="p-3"><div ref={stageHostRef} className="flex w-full justify-center"><div ref={stageRef} style={stageFrameStyle(workspace.document.settings.aspectRatio, stageAvailable)} className="group relative shrink-0 overflow-hidden rounded-xl bg-[#111318] shadow-xl [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:max-w-none [&:fullscreen]:rounded-none"><div className="absolute inset-0" style={transition.active ? transitionLayerStyle(transition.type, transition.progress, "current") : undefined}><CompositionMedia meta={activeShot} playheadMs={playheadMs} playing={playing} muted={previewMuted} globalVisualSettings={previewVisualSettings} /></div>{transition.active && <div className="absolute inset-0" style={transitionLayerStyle(transition.type, transition.progress, "next")}><CompositionMedia meta={nextShot} playheadMs={nextShot?.startMs ?? 0} playing={false} muted globalVisualSettings={previewVisualSettings} /></div>}<CompositionOverlays workspace={workspace} model={model} activeShot={activeShot} playheadMs={playheadMs} playing={playing} /><CompositionAudioMix workspace={workspace} model={model} activeShot={activeShot} playheadMs={playheadMs} playing={playing} muted={previewMuted} /><div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-black/10" />{activeShot?.shot.subtitleText && <div className="pointer-events-none absolute inset-x-[7%] z-10" style={subtitleStyle(activeShot.shot)}><span className="inline-block rounded-md bg-black/60 px-3 py-1.5 leading-relaxed text-white shadow-sm backdrop-blur-sm">{activeShot.shot.subtitleText}</span></div>}<div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/45 px-2.5 py-1 text-[10px] text-white/80 backdrop-blur"><span>场景 {(activeShot?.scene.index ?? 0) + 1}</span><i className="h-1 w-1 rounded-full bg-white/35" /><span>镜头 {(activeShot?.shot.index ?? 0) + 1}</span>{transition.active && <><i className="h-1 w-1 rounded-full bg-white/35" /><span>{transition.type} {Math.round(transition.progress * 100)}%</span></>}</div><div className="absolute right-3 top-3 flex gap-1 opacity-0 transition group-hover:opacity-100"><button type="button" onClick={() => setPreviewMuted((value) => !value)} aria-label={previewMuted ? "打开声音" : "静音"} className="grid h-8 w-8 place-items-center rounded-lg bg-black/45 text-white backdrop-blur">{previewMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}</button><button type="button" onClick={toggleFullscreen} aria-label="全屏预览" className="grid h-8 w-8 place-items-center rounded-lg bg-black/45 text-white backdrop-blur"><Maximize2 size={14} /></button></div><button type="button" onClick={togglePlayback} aria-label={playing ? "暂停" : "播放"} className="absolute left-1/2 top-1/2 z-20 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/55 text-white opacity-0 backdrop-blur transition hover:bg-black/70 group-hover:opacity-100">{playing ? <Pause size={19} /> : <Play size={19} className="translate-x-px" />}</button></div></div></div>
        <div className="flex h-12 items-center gap-3 border-t border-line bg-white px-4"><button type="button" onClick={togglePlayback} className="grid h-8 w-8 place-items-center rounded-full bg-ink text-white">{playing ? <Pause size={14} /> : <Play size={14} />}</button><button type="button" onClick={() => seek(playheadMs - 5000)} aria-label="后退 5 秒" className="rounded-md px-1.5 py-1 text-[10px] text-muted hover:bg-canvas">−5s</button><span className="w-28 text-xs tabular-nums text-muted">{formatTime(playheadMs)} / {formatTime(model.durationMs)}</span><input type="range" min={0} max={model.durationMs} value={playheadMs} onChange={(event) => { setPlaying(false); seek(Number(event.target.value)); }} className="min-w-0 flex-1 accent-blue" /><button type="button" onClick={() => seek(playheadMs + 5000)} aria-label="前进 5 秒" className="rounded-md px-1.5 py-1 text-[10px] text-muted hover:bg-canvas">+5s</button><span className="rounded-md bg-canvas px-2 py-1 text-[10px] text-muted">实时预览</span></div>
      </main>

      <aside className="col-[3] row-[1/4] flex min-h-0 flex-col overflow-hidden bg-white">
        <section className="relative z-20 shrink-0 border-b border-line bg-[#fbfbfc] p-2.5">
          <div className="flex h-11 items-center gap-1.5">
            <button type="button" disabled={!previousShot?.id} onClick={() => previousShot?.id && selectShotForPreview(previousShot.id)} aria-label="上一个镜头" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-white text-muted hover:border-blue hover:text-blue disabled:cursor-not-allowed disabled:opacity-35"><ChevronLeft size={15} /></button>
            <div
              ref={shotPickerRef}
              className="relative min-w-0 flex-1"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setShotPickerOpen(false);
              }}
            >
              <button
                type="button"
                aria-haspopup="listbox"
                aria-expanded={shotPickerOpen}
                onClick={() => setShotPickerOpen((open) => !open)}
                className={`flex h-11 w-full items-center justify-between gap-2 rounded-lg border bg-white px-3 text-left transition ${shotPickerOpen ? "border-blue/40 ring-2 ring-blue/10" : "border-line hover:border-blue/40"}`}
              ><span className="min-w-0"><small className="block text-[9px] text-muted">分镜编辑{selectedScene ? ` · 场景 ${selectedScene.index + 1}` : ""}</small><strong className="block truncate text-[11px] text-text">{selectedShot && selectedSceneShotIndex >= 0 ? `镜头 ${selectedSceneShotIndex + 1} / ${selectedScene?.shots.length} · ${selectedShot.description || "空镜头"}` : "请选择镜头"}</strong></span><ChevronDown size={13} className={`shrink-0 text-muted transition ${shotPickerOpen ? "rotate-180" : ""}`} /></button>
              {shotPickerOpen && selectedScene && <div role="listbox" aria-label="选择分镜" className="absolute left-0 right-0 top-12 z-40 max-h-80 overflow-y-auto rounded-xl border border-line bg-white p-2 shadow-xl"><div className="mb-2 flex items-center justify-between px-1"><strong className="text-[10px] text-text">全部分镜</strong><span className="text-[9px] text-muted">{selectedScene.shots.length} 个镜头</span></div><div className="grid grid-cols-2 gap-2">{selectedScene.shots.map((shot, index) => { const asset = workspace.linkedAssets.find((item) => item.id === shot.assetId); const previewing = activeShot?.id === shot.id; const editing = selectedShot?.id === shot.id; return <button key={shot.id ?? index} type="button" role="option" aria-selected={editing} onClick={() => { selectShotForPreview(shot.id ?? null); setShotPickerOpen(false); }} className={`overflow-hidden rounded-lg border bg-white text-left transition ${editing ? "border-blue ring-1 ring-blue/20" : previewing ? "border-amber ring-1 ring-amber/20" : "border-line hover:border-blue/40"}`}><div className="relative aspect-video bg-canvas"><VideoThumb fill imageUrl={asset?.thumbnailUrl ?? (asset?.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset?.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={false} /><span className="absolute left-1 top-1 rounded bg-black/60 px-1 py-0.5 text-[8px] text-white">{index + 1}</span>{previewing && <span className="absolute right-1 top-1 rounded bg-amber px-1 py-0.5 text-[8px] font-semibold text-white">播放</span>}</div><div className="px-2 py-1.5"><span className="block truncate text-[9px] font-medium text-text">{shot.description || "空镜头"}</span><span className="mt-0.5 block text-[8px] text-muted">{(shot.durationMs / 1000).toFixed(1)}s{editing ? " · 正在编辑" : ""}</span></div></button>; })}</div>{!selectedScene.shots.length && <button type="button" onClick={() => { if (selectedScene.id) onAddShot(selectedScene.id); setShotPickerOpen(false); }} className="w-full rounded-lg border border-dashed border-line py-8 text-[10px] text-muted hover:border-blue hover:text-blue">当前场景没有镜头，点击新增</button>}</div>}
            </div>
            <button type="button" disabled={!nextEditingShot?.id} onClick={() => nextEditingShot?.id && selectShotForPreview(nextEditingShot.id)} aria-label="下一个镜头" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-white text-muted hover:border-blue hover:text-blue disabled:cursor-not-allowed disabled:opacity-35"><ChevronRight size={15} /></button>
            {selectedScene?.id && <button type="button" onClick={() => onAddShot(selectedScene.id!)} aria-label="新增镜头" title="新增镜头" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-blue-soft text-blue"><Plus size={13} /></button>}
          </div>
        </section>
        <div className="min-h-0 flex-1 overflow-y-auto">{!selectedShot || !selectedScene?.id ? <div className="grid min-h-[360px] place-items-center p-8 text-center text-xs text-muted">选择一个镜头查看属性</div> : <div><div className="sticky top-0 z-10 border-b border-line bg-white"><div className="flex items-center justify-between px-4 py-3"><div><span className="text-[10px] text-muted">当前选中</span><strong className="block text-sm text-text">场景 {selectedScene.index + 1} / 镜头 {selectedShot.index + 1}</strong></div><div className="flex gap-0.5"><button type="button" onClick={() => onDuplicateShot(selectedScene.id!, selectedShot.id!)} aria-label="复制镜头" className="rounded-lg p-2 text-muted hover:bg-canvas"><Copy size={14} /></button><button type="button" onClick={onDeleteShot} aria-label="删除镜头" className="rounded-lg p-2 text-muted hover:bg-red/10 hover:text-red"><Trash2 size={15} /></button></div></div><div className="grid grid-cols-3">{inspectors.map((item) => <button key={item.id} type="button" onClick={() => setInspectorTab(item.id)} className={`border-b-2 px-1 py-2.5 text-[11px] ${inspectorTab === item.id ? "border-blue font-semibold text-blue" : "border-transparent text-muted"}`}>{item.label}</button>)}</div></div><div className="space-y-4 p-4">
        {inspectorTab === "visual" && <SourceTrimControl shot={selectedShot} asset={selectedAsset} onChange={patchSelectedShot} onOpen={() => setTrimOpen(true)} onReplace={() => { setResourceTab("assets"); setSelectedResourceAssetId(selectedAsset?.id ?? null); setReplacementPicking(true); }} onRemove={() => selectedScene.id && selectedShot.id && onRemoveShotAsset(selectedScene.id, selectedShot.id)} />}
        {inspectorTab === "visual" && replacementPicking && <div className="rounded-lg border border-blue/20 bg-blue-soft px-3 py-2 text-[10px] leading-4 text-blue"><strong className="block">正在更换当前镜头素材</strong>在左侧选择素材后点击“应用到当前镜头”；仅查看不会替换。<button type="button" onClick={() => setReplacementPicking(false)} className="ml-1 font-semibold underline">取消</button></div>}
        {inspectorTab === "visual" && selectedShot.candidates.length > 0 && <section className="rounded-xl border border-line p-3"><header className="flex items-start justify-between gap-2"><div><strong className="text-xs text-text">素材匹配候选</strong><p className="mt-1 text-[9px] text-muted">匹配不会替换当前素材，点击候选才会应用。</p></div><span className="shrink-0 text-[9px] text-muted">{selectedShot.candidates.length} 个</span></header><div className="mt-2 space-y-1.5">{selectedShot.candidates.slice(0, 5).map((candidate) => { const available = workspace.linkedAssets.some((asset) => asset.segments.some((segment) => segment.id === candidate.segmentId)); return <button type="button" key={candidate.id} disabled={!available} onClick={() => chooseCandidate(candidate.id)} className="w-full rounded-lg border border-line p-2 text-left hover:border-blue/40 disabled:opacity-45"><span className="flex items-center justify-between gap-2"><strong className="truncate text-[10px] text-text">{candidate.title || "候选片段"}</strong><span className="flex shrink-0 items-center gap-2"><em className="text-[9px] not-italic text-teal">{candidate.score}%</em><b className="text-[9px] font-medium text-blue">应用</b></span></span><small className="mt-1 block line-clamp-2 text-[9px] leading-4 text-muted">{available ? candidate.reason || candidate.source : "源片段不可用，记录仍保留"}</small></button>; })}</div></section>}
        {inspectorTab === "visual" && <>
          <section className="rounded-xl border border-line p-3"><div className="flex items-start justify-between gap-2"><div><strong className="text-xs text-text">镜头画面描述</strong><p className="mt-1 text-[9px] leading-4 text-muted">用于素材匹配和 AI 生成；AI 完善只生成建议，确认后才会替换。</p></div><button type="button" disabled={operationPending} onClick={() => onRunOperation("complete_shots", undefined, { type: "shot", shotIds: selectedShot.id ? [selectedShot.id] : [] })} className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-blue disabled:opacity-40"><WandSparkles size={11} />AI 完善</button></div><textarea rows={7} value={selectedShot.description} onChange={(event) => patchSelectedShot({ description: event.target.value })} className="mt-2 min-h-36 max-h-80 w-full resize-y rounded-lg border border-line p-2.5 text-sm leading-5 text-text" /><div className="mt-2 grid grid-cols-3 gap-2"><button type="button" title={matchableAssetCount ? "为当前镜头搜索项目素材" : "请先向项目添加图片或视频素材"} disabled={operationPending || matchableAssetCount === 0} onClick={() => onRunOperation("match_assets", undefined, { type: "shot", shotIds: selectedShot.id ? [selectedShot.id] : [] })} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-[10px] hover:border-blue hover:text-blue disabled:cursor-not-allowed disabled:opacity-40"><Search size={12} />匹配素材</button><button type="button" disabled={operationPending} onClick={() => onOpenQuickAI("shot", "image")} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-[10px] hover:border-blue hover:text-blue"><ImageIcon size={12} />AI 图片</button><button type="button" disabled={operationPending} onClick={() => onOpenQuickAI("shot", "video")} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-[10px] hover:border-blue hover:text-blue"><Film size={12} />AI 视频</button></div>{matchableAssetCount === 0 && <p className="mt-2 text-[9px] leading-4 text-amber">项目中还没有可匹配的图片或视频，请先通过顶部“添加素材”加入。</p>}</section>
          <details className="rounded-xl border border-line p-3"><summary className="cursor-pointer text-xs font-semibold text-text">高级画面设置 <span className="ml-1 font-normal text-muted">构图 · 调色 · 运动 · 转场</span></summary><div className="mt-3 space-y-3">
          <section className="rounded-xl border border-line p-3"><header className="mb-2 flex items-center justify-between"><strong className="text-xs text-text">构图与位置</strong><button type="button" onClick={() => patchSelectedShot({ transform: {} })} className="flex items-center gap-1 text-[10px] text-muted"><RotateCcw size={11} />重置</button></header><div className="grid grid-cols-2 gap-1"><button type="button" onClick={() => patchSelectedShot({ transform: { ...selectedShot.transform, fitMode: "cover" } })} className={`rounded-md border py-1.5 text-[10px] ${String(selectedShot.transform.fitMode ?? "cover") === "cover" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>填充画面</button><button type="button" onClick={() => patchSelectedShot({ transform: { ...selectedShot.transform, fitMode: "contain" } })} className={`rounded-md border py-1.5 text-[10px] ${selectedShot.transform.fitMode === "contain" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>完整适应</button></div><div className="mt-3 space-y-2"><RangeControl label="缩放" value={numeric(selectedShot.transform.scale, 100)} minimum={25} maximum={300} suffix="%" onChange={(scale) => patchSelectedShot({ transform: { ...selectedShot.transform, scale } })} /><RangeControl label="水平位置" value={numeric(selectedShot.transform.x)} minimum={-100} maximum={100} suffix="%" onChange={(x) => patchSelectedShot({ transform: { ...selectedShot.transform, x } })} /><RangeControl label="垂直位置" value={numeric(selectedShot.transform.y)} minimum={-100} maximum={100} suffix="%" onChange={(y) => patchSelectedShot({ transform: { ...selectedShot.transform, y } })} /></div></section>
          <section className="rounded-xl border border-line p-3"><header className="mb-2 flex items-center justify-between"><div><strong className="text-xs text-text">滤镜与调色</strong><span className={`ml-2 rounded px-1.5 py-0.5 text-[9px] ${selectedAdjustIsOverride ? "bg-blue-soft text-blue" : "bg-canvas text-muted"}`}>{selectedAdjustIsOverride ? "当前镜头覆盖" : "继承全片"}</span></div><button type="button" onClick={() => patchSelectedShot({ adjust: selectedAdjustIsOverride ? { mode: "inherit" } : { ...selectedEffectiveAdjust, mode: "override" } })} className="flex items-center gap-1 text-[10px] text-muted">{selectedAdjustIsOverride ? <><RotateCcw size={11} />恢复全片</> : "单独调整"}</button></header><div className="grid grid-cols-4 gap-1">{filterPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", filterPreset: value } })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedEffectiveAdjust.filterPreset ?? "original") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div><div className="mt-3 space-y-2"><RangeControl label="亮度" value={numeric(selectedEffectiveAdjust.brightness)} minimum={-100} maximum={100} onChange={(brightness) => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", brightness } })} /><RangeControl label="对比度" value={numeric(selectedEffectiveAdjust.contrast)} minimum={-100} maximum={100} onChange={(contrast) => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", contrast } })} /><RangeControl label="饱和度" value={numeric(selectedEffectiveAdjust.saturation)} minimum={-100} maximum={100} onChange={(saturation) => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", saturation } })} /><RangeControl label="色相" value={numeric(selectedEffectiveAdjust.hue)} minimum={-180} maximum={180} onChange={(hue) => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", hue } })} /><RangeControl label="色温" value={numeric(selectedEffectiveAdjust.temperature)} minimum={-100} maximum={100} onChange={(temperature) => patchSelectedShot({ adjust: { ...selectedEffectiveAdjust, mode: "override", temperature } })} /></div></section>
          <section className="rounded-xl border border-line p-3"><div className="flex items-center justify-between"><strong className="text-xs text-text">镜头运动</strong>{String(selectedShot.motion.type ?? "none") !== "none" && <button type="button" onClick={() => { if (selectedShotMeta) { seek(selectedShotMeta.startMs, false); setPlaying(true); } }} className="flex items-center gap-1 text-[10px] font-medium text-blue"><Play size={10} />预览运动</button>}</div><div className="mt-2 grid grid-cols-4 gap-1">{motionPresets.map(([value, label]) => <button key={value} type="button" onClick={() => selectMotionPreset(value)} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedShot.motion.type ?? "none") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>{String(selectedShot.motion.type ?? "none") !== "none" && <div className="mt-3"><RangeControl label="运动强度" value={numeric(selectedShot.motion.strength, 55)} minimum={0} maximum={100} suffix="%" onChange={(value) => patchRecord("motion", { strength: value })} /></div>}</section>
          <section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">镜头转场</strong><div className="mt-2 grid grid-cols-3 gap-1">{transitionPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("transition", { type: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedShot.transition.type ?? "cut") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>{!["cut", "none"].includes(String(selectedShot.transition.type ?? "cut")) && <div className="mt-3"><RangeControl label="转场时长" value={numeric(selectedShot.transition.durationMs, 500)} minimum={100} maximum={3000} suffix="ms" onChange={(value) => patchRecord("transition", { durationMs: value })} /></div>}</section>
          </div></details>
          {selectedShot.mediaVersions.length > 0 && <button type="button" onClick={() => setHistoryOpen(true)} className="flex w-full items-center justify-between rounded-xl border border-line p-3 text-left hover:border-blue/40"><span className="flex items-center gap-2"><History size={14} className="text-blue" /><span><strong className="block text-xs text-text">画面历史</strong><small className="mt-1 block text-[9px] text-muted">查看曾经选择、匹配或生成过的素材</small></span></span><span className="rounded-full bg-canvas px-2 py-1 text-[9px] text-muted">{selectedShot.mediaVersions.length} 个</span></button>}
        </>}
        {inspectorTab === "audio" && <><section className="rounded-xl border border-line p-3"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2"><AudioLines size={15} className="text-blue" /><strong className="text-xs">镜头原声</strong></div><span className={`rounded px-1.5 py-0.5 text-[9px] ${selectedShot.audioSettings.originalVolume === undefined ? "bg-canvas text-muted" : "bg-blue-soft text-blue"}`}>{selectedShot.audioSettings.originalVolume === undefined ? "继承项目默认" : "当前镜头覆盖"}</span></div><div className="mt-3"><RangeControl label="音量" value={numeric(selectedShot.audioSettings.originalVolume, numeric(audioMix.originalVolume, 30))} minimum={0} maximum={100} suffix="%" onChange={(originalVolume) => patchRecord("audioSettings", { originalVolume })} /></div>{selectedShot.audioSettings.originalVolume !== undefined && <button type="button" onClick={() => patchRecord("audioSettings", { originalVolume: undefined })} className="mt-2 text-[10px] font-medium text-blue">恢复项目默认</button>}</section><section className="rounded-xl border border-line p-3"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2"><Mic2 size={15} className="text-blue" /><strong className="text-xs">当前镜头关联旁白</strong></div><span className={`rounded px-1.5 py-0.5 text-[9px] ${selectedShotVoiceStatus === "已生成" ? "bg-teal/10 text-teal" : selectedShotVoiceStatus === "存在过期旁白" || selectedShotVoiceStatus === "需要处理" ? "bg-amber/10 text-amber" : "bg-canvas text-muted"}`}>{selectedShotVoiceStatus}</span></div><p className="mt-2 text-[11px] leading-5 text-muted">{selectedShotVoiceLines.length ? `${selectedShotVoiceLines.length} 条旁白与当前镜头时间范围重叠` : "当前镜头时间范围内没有已生成旁白"}</p><p className="mt-1 truncate text-[10px] text-muted">项目母带：{audioAssets.find((asset) => asset.id === audioMix.voiceAssetId)?.name ?? "尚未生成或选择"}</p><button type="button" onClick={onOpenVoiceover} className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-2 text-xs font-semibold text-white"><Sparkles size={13} />生成 / 更新旁白</button><p className="mt-2 text-[9px] leading-4 text-muted">生成面板会默认展示全片，也可切换当前场景或当前镜头；母带和音量仍属于项目级配置。</p></section><section className="rounded-xl border border-line p-3"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2"><Music2 size={15} className="text-blue" /><strong className="text-xs">背景音乐</strong></div><span className={`rounded px-1.5 py-0.5 text-[9px] ${selectedShotMusic ? "bg-blue-soft text-blue" : "bg-canvas text-muted"}`}>{effectiveMusicSource}</span></div><p className="mt-2 truncate text-[10px] text-muted">当前生效：{effectiveMusic ? audioAssets.find((asset) => asset.id === effectiveMusic.assetId)?.name ?? "音频素材不可用" : "无背景音乐"}</p><Select aria-label="镜头背景音乐" value={String(selectedShotMusic?.assetId ?? "")} onChange={(event) => patchRecord("audioSettings", { backgroundMusic: event.target.value ? { assetId: event.target.value, volume: 28, loop: true } : null })} wrapperClassName="mt-2"><option value="">继承场景 / 全片 / 项目默认</option>{audioAssets.filter((asset) => asset.metadata.purpose !== "voice_take" && asset.metadata.purpose !== "voiceover_master" && asset.sourceType !== "ai_tts").map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</Select>{selectedShotMusic && <div className="mt-3"><RangeControl label="镜头覆盖音量" value={numeric(selectedShotMusic.volume, 28)} minimum={0} maximum={100} suffix="%" onChange={(volume) => patchRecord("audioSettings", { backgroundMusic: { ...selectedShotMusic, volume } })} /></div>}</section><button type="button" onClick={() => setResourceTab("settings")} className="w-full rounded-lg bg-blue-soft py-2 text-xs font-semibold text-blue">打开项目声音默认值</button></>}
        {inspectorTab === "caption" && <><label className="block text-xs font-medium text-muted">字幕<textarea rows={5} value={selectedShot.subtitleText} onChange={(event) => patchSelectedShot({ subtitleText: event.target.value, subtitleOverridden: event.target.value !== selectedScene.narrationText, subtitleOutdated: false })} className="mt-1.5 w-full resize-y rounded-lg border border-line p-2.5 text-sm leading-5 text-text" /></label>{selectedShot.subtitleOutdated && <div className="rounded-lg bg-amber/10 p-2.5 text-[11px] leading-5 text-amber">场景旁白已变化，当前手工字幕需要复核。<button type="button" onClick={() => onRestoreSubtitle(selectedScene.id!, selectedShot.id!)} className="ml-1 font-semibold underline">恢复跟随旁白</button></div>}<section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">字幕位置</strong><div className="mt-2 grid grid-cols-3 gap-1">{[["top", "顶部"], ["center", "居中"], ["bottom", "底部"]].map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("subtitleSettings", { position: value })} className={`rounded-md border py-1.5 text-[10px] ${String(selectedShot.subtitleSettings.position ?? "bottom") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div><div className="mt-3"><RangeControl label="字号" value={numeric(selectedShot.subtitleSettings.fontSize, 16)} minimum={10} maximum={48} suffix="px" onChange={(value) => patchRecord("subtitleSettings", { fontSize: value })} /></div></section><p className="text-xs leading-5 text-muted">{selectedShot.subtitleOverridden ? "当前字幕为手动覆盖；场景旁白变化时会提示复核。" : "字幕正在跟随场景旁白。"}</p></>}
        </div></div>}</div></aside>
      {paneSplitter("right")}
    </div>

    <section className="col-[5] row-[2] min-w-0 border-t border-line bg-[#f9f9fa]">
      <header className="flex h-10 items-center justify-between border-b border-line px-3">
        <div className="flex items-center gap-2"><strong className="text-xs text-text">主时间线</strong><span className="text-[10px] text-muted">{formatTime(model.durationMs)}</span></div>
        <div className="flex items-center gap-2">
          {selectedShot && <button type="button" onClick={splitSelectedShot} disabled={!canSplitSelectedShot} title={canSplitSelectedShot ? `在镜头内 ${formatTime(selectedSplitOffsetMs)} 处分割` : "将播放头移动到镜头内部，距离两端至少 0.2 秒"} className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1.5 text-[10px] font-semibold text-text hover:border-blue hover:text-blue disabled:cursor-not-allowed disabled:opacity-40"><Scissors size={11} />{canSplitSelectedShot ? `在 ${formatTime(selectedSplitOffsetMs)} 处分割` : "移动播放头后分割"}</button>}
          <button type="button" disabled={operationPending} onClick={() => onRunOperation("match_assets")} className="flex items-center gap-1 rounded-md bg-blue-soft px-2 py-1.5 text-[10px] font-semibold text-blue"><Sparkles size={11} />匹配全部镜头</button>
        </div>
      </header>
      <div className="grid h-[216px] grid-cols-[84px_1fr] overflow-hidden">
        <div className="border-r border-line bg-white pt-7"><div className="flex h-20 items-center gap-2 border-y border-line px-3 text-[10px] text-muted"><Film size={13} />主画面</div><div className="flex h-16 items-center gap-2 border-b border-line px-3 text-[10px] text-muted"><Mic2 size={13} />AI 旁白</div><div className="flex h-10 items-center gap-2 border-b border-line px-3 text-[10px] text-muted"><AudioLines size={13} />音乐/音效</div></div>
        <div className="min-w-0 overflow-x-auto">
          <div className="relative h-7 min-w-[720px] border-b border-line bg-white">{Array.from({ length: 9 }, (_, index) => <span key={index} className="absolute top-1 text-[9px] text-muted" style={{ left: `${index * 12.5}%` }}>{formatTime(model.durationMs * index / 8).slice(0, 5)}</span>)}</div>
          <div className="relative flex h-20 min-w-[720px] items-center gap-1 border-b border-line px-1">{mainTrack?.items.map((item, index) => <button key={item.id} type="button" onClick={() => { setPlaying(false); seek(item.startMs); }} className={`group relative h-14 min-w-[70px] overflow-hidden rounded-md border px-2 text-left ${item.shotId === selectedShot?.id ? "border-blue bg-blue text-white" : item.assetId ? "border-teal/40 bg-teal/10 text-text" : "border-dashed border-line bg-white text-muted"}`} style={{ width: `${Math.max(8, item.durationMs / Math.max(1, model.durationMs) * 100)}%` }}><span className="block truncate text-[10px] font-semibold">镜头 {index + 1}</span><span className="mt-1 block text-[9px] opacity-70">{(item.durationMs / 1000).toFixed(1)}s</span>{item.shotId && model.shots.find((shot) => shot.id === item.shotId)?.shot.transition.type && <span className="absolute bottom-0 right-0 rounded-tl bg-black/15 px-1 text-[8px]">转场</span>}</button>)}<div className="pointer-events-none absolute inset-y-0 w-px bg-red shadow-[0_0_0_1px_rgba(255,255,255,.6)]" style={{ left: `${playheadMs / Math.max(1, model.durationMs) * 100}%` }} /></div>
          <div className="relative h-16 min-w-[720px] border-b border-line bg-blue-soft/20">{timelineVoiceLines.map((line, index) => { const active = playheadMs >= line.startMs && playheadMs < line.startMs + line.durationMs; const stale = line.status === "stale"; return <button key={line.id} type="button" aria-label={`旁白 ${index + 1}，${line.text}，${(line.durationMs / 1000).toFixed(1)} 秒`} title={`${formatTime(line.startMs)} · ${(line.durationMs / 1000).toFixed(1)}s\n${line.text}`} onClick={() => { setPlaying(false); seek(line.startMs); }} className={`absolute top-2 h-12 min-w-8 overflow-hidden rounded-md border px-2 text-left shadow-sm transition ${stale ? "border-amber/50 bg-amber/15 text-amber" : active ? "z-10 border-blue bg-blue text-white ring-2 ring-blue/20" : "border-blue/30 bg-white text-blue hover:border-blue hover:bg-blue-soft"}`} style={{ left: `${line.startMs / Math.max(1, model.durationMs) * 100}%`, width: `${Math.max(1.5, line.durationMs / Math.max(1, model.durationMs) * 100)}%` }}><span className="block truncate text-[9px] font-semibold">{index + 1}. {line.text}</span><span className="mt-1 block truncate text-[8px] opacity-70">{formatTime(line.startMs)} · {(line.durationMs / 1000).toFixed(1)}s{stale ? " · 已过期" : ""}</span></button>; })}{voiceoverQuery.isLoading && <span className="absolute inset-0 grid place-items-center text-[10px] text-muted">正在加载旁白分段…</span>}{!voiceoverQuery.isLoading && !timelineVoiceLines.length && <button type="button" onClick={onOpenVoiceover} className="absolute inset-2 rounded-md border border-dashed border-blue/25 text-[10px] text-blue hover:bg-blue-soft">尚无 AI 旁白分段，点击生成</button>}<div className="pointer-events-none absolute inset-y-0 z-20 w-px bg-red shadow-[0_0_0_1px_rgba(255,255,255,.6)]" style={{ left: `${playheadMs / Math.max(1, model.durationMs) * 100}%` }} /></div>
          <div className="flex h-10 min-w-[720px] items-center gap-2 border-b border-line px-2 text-[10px] text-muted">{effectiveMusic && <span className="rounded bg-teal/10 px-1.5 py-0.5 text-teal">背景音乐</span>}<span>{audioAssets.length ? `${audioAssets.length} 个声音素材 · 支持项目与镜头分层混音` : "尚未添加音乐或音效"}</span></div>
        </div>
      </div>
    </section>

    <ClipTrimModal open={trimOpen} shot={selectedShot} asset={selectedAsset} onClose={() => setTrimOpen(false)} onApply={patchSelectedShot} />
    <MaterialHistoryModal open={historyOpen} shot={selectedShot} assets={workspace.linkedAssets} onClose={() => setHistoryOpen(false)} onApply={(patch) => { setPlaying(false); patchSelectedShot(patch); }} />
    <AudioAssetPicker role={audioPickerRole} assets={audioAssets} onClose={() => !audioApplyPending && setAudioPickerRole(null)} onSelect={(assetId) => { if (audioPickerRole) void setDefaultAudioAsset(audioPickerRole, assetId); }} />

    {assetToApply && selectedScene && selectedShot && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="replace-asset-title">
      <section className="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
        <header className="border-b border-line px-5 py-4"><h2 id="replace-asset-title" className="text-sm font-semibold text-text">替换当前镜头画面？</h2><p className="mt-1 text-[11px] text-muted">将“{assetToApply.name}”应用到场景 {selectedScene.index + 1} / 镜头 {selectedShot.index + 1}。</p></header>
        <div className="px-5 py-4"><p className="rounded-xl bg-canvas px-4 py-3 text-[11px] leading-5 text-muted">当前素材或媒体版本会从这个镜头中移除，并从新素材的开头开始使用；素材本身和已有历史版本不会被删除。</p></div>
        <footer className="flex justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-4"><button type="button" onClick={() => setAssetToApply(null)} className="rounded-lg border border-line bg-white px-4 py-2 text-xs text-text">取消</button><button type="button" onClick={() => applyAsset(assetToApply)} className="rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white">确认替换</button></footer>
      </section>
    </div>}

    {editingScene?.id && <div className="fixed inset-0 z-50 bg-ink/35 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="scene-settings-title" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditingSceneId(null); }}>
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-[420px] flex-col border-l border-line bg-white shadow-2xl">
        <header className="flex items-start justify-between border-b border-line px-5 py-4"><div><h2 id="scene-settings-title" className="text-sm font-semibold text-text">场景 {editingSceneIndex + 1} 设置</h2><p className="mt-1 text-[11px] text-muted">集中编辑场景信息、结束转场和结构操作。</p></div><button type="button" onClick={() => setEditingSceneId(null)} aria-label="关闭场景设置" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={15} /></button></header>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          <label className="block text-xs font-medium text-muted">场景标题<input value={editingScene.outline} onChange={(event) => onUpdateScene(editingScene.id!, { outline: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line p-2.5 text-sm text-text" /></label>
          <label className="block text-xs font-medium text-muted">场景旁白<textarea rows={7} value={editingScene.narrationText} onChange={(event) => onUpdateScene(editingScene.id!, { narrationText: event.target.value })} className="mt-1.5 w-full resize-y rounded-lg border border-line p-2.5 text-sm leading-6 text-text" /></label>
          <section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">场景结束转场</strong>{editingSceneLastShot ? <><div className="mt-3 grid grid-cols-3 gap-1">{transitionPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchEditingSceneTransition({ type: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(editingSceneLastShot.transition.type ?? "cut") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>{!["cut", "none"].includes(String(editingSceneLastShot.transition.type ?? "cut")) && <div className="mt-3"><RangeControl label="转场时长" value={numeric(editingSceneLastShot.transition.durationMs, 500)} minimum={100} maximum={3000} suffix="ms" onChange={(durationMs) => patchEditingSceneTransition({ durationMs })} /></div>}</> : <p className="mt-2 text-[10px] text-muted">场景中还没有镜头，添加镜头后可设置结束转场。</p>}</section>
          <section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">场景结构</strong><div className="mt-3 grid grid-cols-2 gap-2"><button type="button" disabled={editingSceneIndex <= 0} onClick={() => onMoveScene(editingScene.id!, -1)} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-xs text-text disabled:opacity-35"><ArrowUp size={13} />上移</button><button type="button" disabled={editingSceneIndex >= scenes.length - 1} onClick={() => onMoveScene(editingScene.id!, 1)} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-xs text-text disabled:opacity-35"><ArrowDown size={13} />下移</button></div><button type="button" onClick={() => onAddShot(editingScene.id!)} className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-blue-soft py-2 text-xs font-semibold text-blue"><Plus size={13} />新增镜头</button></section>
        </div>
        <footer className="flex items-center justify-between border-t border-line bg-canvas/60 px-5 py-4"><button type="button" onClick={() => { setEditingSceneId(null); onDeleteScene(); }} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-red hover:bg-red/10"><Trash2 size={13} />删除场景</button><button type="button" onClick={() => setEditingSceneId(null)} className="rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white">完成</button></footer>
      </aside>
    </div>}
  </div>;
}
