import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlignLeft, ArrowDown, ArrowUp, AudioLines, CloudUpload, Copy, Film, Image as ImageIcon, Library, Maximize2,
  Mic2, Music2, Pause, Play, Plus, RotateCcw, Search, SlidersHorizontal, Sparkles,
  Trash2, Volume2, VolumeX, WandSparkles,
} from "lucide-react";
import type { CSSProperties } from "react";
import type { Asset } from "@/api/assets";
import type { ProjectOperation } from "@/api/generate";
import type { GlobalScopeLayers, ProjectAudioMix, ProjectDocumentSettings, Scene, ScopeAssetReference, Shot, Workspace } from "@/api/projects";
import { VideoThumb } from "@/components/VideoThumb";
import {
  buildCompositionModel, clamp, compositionShotAt, nextCompositionShot, numeric,
  shotVisualStyle, subtitleStyle, transitionLayerStyle, transitionState,
  type CompositionShot,
} from "@/lib/compositionPreview";

type ResourceTab = "outline" | "assets" | "audio" | "global";
type InspectorTab = "visual" | "audio" | "caption" | "process";

interface Props {
  workspace: Workspace;
  selectedScene?: Scene;
  selectedShot?: Shot;
  operationPending: boolean;
  onSelectScene: (id: string | null) => void;
  onSelectShot: (id: string | null) => void;
  onUpdateDocumentSettings: (patch: Partial<ProjectDocumentSettings>) => void;
  onUpdateGlobalScope: (scope: "film" | "scene", sceneId: string | undefined, patch: Partial<GlobalScopeLayers>) => void;
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
  onUpload: () => void;
  onRunOperation: (operation: ProjectOperation) => void;
}

const resources = [
  { id: "outline", label: "结构", icon: AlignLeft },
  { id: "assets", label: "素材", icon: Library },
  { id: "audio", label: "声音", icon: AudioLines },
  { id: "global", label: "全局", icon: SlidersHorizontal },
] as const;

const inspectors = [
  { id: "visual", label: "画面" },
  { id: "audio", label: "声音" },
  { id: "caption", label: "字幕" },
  { id: "process", label: "处理" },
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

function aspectRatioStyle(aspectRatio: ProjectDocumentSettings["aspectRatio"]): CSSProperties {
  const [width, height] = aspectRatio.split(":").map(Number);
  return { aspectRatio: `${width} / ${height}` };
}

function stageSizeClass(aspectRatio: ProjectDocumentSettings["aspectRatio"]): string {
  const [width, height] = aspectRatio.split(":").map(Number);
  return width < height ? "h-full w-auto max-w-full" : "h-auto w-full max-h-full max-w-4xl";
}

function scopeReference(value: unknown): ScopeAssetReference | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const reference = value as Partial<ScopeAssetReference>;
  return reference.assetId ? reference as ScopeAssetReference : null;
}

function scopeReferenceList(value: unknown): ScopeAssetReference[] {
  return Array.isArray(value) ? value.map(scopeReference).filter((item): item is ScopeAssetReference => Boolean(item)) : [];
}

function CompositionAudioTrack({ asset, volume, playheadMs, playing, muted, startMs = 0, endMs, atMs = 0, loop = false }: {
  asset?: Asset; volume: number; playheadMs: number; playing: boolean; muted: boolean;
  startMs?: number; endMs?: number; atMs?: number; loop?: boolean;
}) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const active = Boolean(asset?.mediaUrl) && playheadMs >= startMs + atMs && (endMs === undefined || playheadMs < endMs);
  useEffect(() => {
    const audio = ref.current;
    if (!audio) return;
    const localSeconds = Math.max(0, playheadMs - startMs - atMs) / 1000;
    if (Math.abs(audio.currentTime - localSeconds) > 0.2) {
      try { audio.currentTime = localSeconds; } catch { /* metadata is not ready yet */ }
    }
    audio.volume = clamp(volume, 0, 100) / 100;
    audio.muted = muted || volume <= 0;
    if (playing && active) void audio.play().catch(() => undefined);
    else audio.pause();
  }, [active, atMs, muted, playheadMs, playing, startMs, volume]);
  if (!asset?.mediaUrl) return null;
  return <audio ref={ref} src={asset.mediaUrl} loop={loop} preload="metadata" />;
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
  const voiceActive = Boolean(voice?.mediaUrl) && !mix.voiceMuted && numeric(mix.voiceVolume, 100) > 0;
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

function CompositionOverlayVideo({ asset, item, startMs, playheadMs, style, className }: {
  asset: Asset; item: ScopeAssetReference; startMs: number; playheadMs: number;
  style: CSSProperties; className: string;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const previousPlayhead = useRef(playheadMs);
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const elapsed = Math.max(0, playheadMs - startMs);
    const localMs = item.loop !== false && asset.durationMs > 0 ? elapsed % asset.durationMs : elapsed;
    if (Math.abs(video.currentTime - localMs / 1000) > 0.2) {
      try { video.currentTime = localMs / 1000; } catch { /* metadata is not ready yet */ }
    }
    const delta = playheadMs - previousPlayhead.current;
    previousPlayhead.current = playheadMs;
    if (delta > 0 && delta < 500) void video.play().catch(() => undefined);
    const pauseTimer = window.setTimeout(() => video.pause(), 180);
    return () => window.clearTimeout(pauseTimer);
  }, [asset.durationMs, item.loop, playheadMs, startMs]);
  return <video ref={ref} src={asset.mediaUrl} muted loop={item.loop !== false} playsInline preload="metadata" style={style} className={className} />;
}

function CompositionOverlays({ workspace, model, activeShot, playheadMs }: {
  workspace: Workspace; model: ReturnType<typeof buildCompositionModel>; activeShot?: CompositionShot; playheadMs: number;
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
      ? <CompositionOverlayVideo key={`${item.id ?? item.assetId}-${index}`} asset={asset} item={item} startMs={startMs} playheadMs={playheadMs} style={style} className={className} />
      : <img key={`${item.id ?? item.assetId}-${index}`} src={source} alt="" style={style} className={className} />;
  })}</>;
}

function CompositionMedia({ meta, playheadMs, playing, muted }: {
  meta?: CompositionShot; playheadMs: number; playing: boolean; muted: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const localMs = meta ? clamp(playheadMs - meta.startMs, 0, meta.durationMs) : 0;
  const sourceMs = meta
    ? clamp(meta.sourceStartMs + localMs, meta.sourceStartMs, Math.max(meta.sourceStartMs, meta.sourceEndMs - 30))
    : 0;
  const progress = meta ? localMs / Math.max(1, meta.durationMs) : 0;
  const visualStyle = meta ? shotVisualStyle(meta.shot, progress) : undefined;
  const originalVolume = clamp(numeric(meta?.shot.audioSettings.originalVolume, 100), 0, 100) / 100;

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !meta) return;
    const seconds = sourceMs / 1000;
    if (Math.abs(video.currentTime - seconds) > 0.16) {
      try { video.currentTime = seconds; } catch { /* metadata is not ready yet */ }
    }
    video.volume = originalVolume;
    video.muted = muted || originalVolume <= 0;
    if (playing) void video.play().catch(() => undefined);
    else video.pause();
  }, [meta, muted, originalVolume, playing, sourceMs]);

  if (!meta) return <div className="absolute inset-0 grid place-items-center bg-[#111318] text-center text-sm text-white/55"><div><Film size={36} className="mx-auto mb-3 opacity-40" />时间线中还没有镜头</div></div>;
  if (meta.asset?.mediaType === "video" && meta.mediaUrl) {
    return <video ref={videoRef} src={meta.mediaUrl} poster={meta.thumbnailUrl} playsInline preload="metadata" style={visualStyle} onLoadedMetadata={(event) => { event.currentTarget.currentTime = sourceMs / 1000; }} className="absolute inset-0 h-full w-full object-cover will-change-transform" />;
  }
  if ((meta.asset?.mediaType === "image" || meta.thumbnailUrl) && (meta.mediaUrl || meta.thumbnailUrl)) {
    return <img src={meta.mediaUrl ?? meta.thumbnailUrl} alt="" style={visualStyle} className="absolute inset-0 h-full w-full object-cover will-change-transform" />;
  }
  return <div className="absolute inset-0 overflow-hidden bg-[radial-gradient(circle_at_25%_20%,#314b77_0%,#1b2334_32%,#111318_72%)]" style={visualStyle}><div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.06)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.06)_1px,transparent_1px)] [background-size:32px_32px]" /><div className="absolute inset-0 grid place-items-center px-8 text-center text-white/75"><div><Film size={32} className="mx-auto mb-3 opacity-60" /><strong className="block text-sm">{meta.shot.description || "镜头占位"}</strong><span className="mt-1 block text-[11px] text-white/45">{meta.asset ? "素材尚无可播放预览" : "等待匹配或生成素材"}</span></div></div></div>;
}

function RangeControl({ label, value, minimum, maximum, suffix = "", onChange }: {
  label: string; value: number; minimum: number; maximum: number; suffix?: string;
  onChange: (value: number) => void;
}) {
  return <label className="block text-[11px] text-muted"><span className="flex justify-between"><span>{label}</span><strong className="font-medium text-text">{value}{suffix}</strong></span><input type="range" min={minimum} max={maximum} value={value} onChange={(event) => onChange(Number(event.target.value))} className="mt-1.5 w-full accent-blue" /></label>;
}

function SourceTrimControl({ shot, assetDurationMs, onChange }: {
  shot: Shot; assetDurationMs: number; onChange: (patch: Partial<Shot>) => void;
}) {
  const duration = Math.max(100, assetDurationMs);
  return <section className="rounded-xl border border-line p-3">
    <header className="flex items-center justify-between"><strong className="text-xs text-text">素材裁切</strong><label className="flex items-center gap-1 text-[10px] text-muted"><input type="checkbox" checked={shot.locked} onChange={(event) => onChange({ locked: event.target.checked })} />锁定镜头</label></header>
    <div className="mt-3 grid grid-cols-2 gap-2"><label className="text-[10px] text-muted">入点（秒）<input aria-label="素材入点" type="number" min={0} max={Math.max(0, shot.sourceEndMs - 100) / 1000} step={0.1} value={(shot.sourceStartMs / 1000).toFixed(1)} disabled={!shot.assetId || shot.locked} onChange={(event) => onChange({ sourceStartMs: clamp(Math.round(Number(event.target.value) * 1000), 0, Math.max(0, shot.sourceEndMs - 100)) })} className="mt-1 w-full rounded-lg border border-line p-2 text-xs text-text disabled:opacity-50" /></label><label className="text-[10px] text-muted">出点（秒）<input aria-label="素材出点" type="number" min={(shot.sourceStartMs + 100) / 1000} max={duration / 1000} step={0.1} value={(shot.sourceEndMs / 1000).toFixed(1)} disabled={!shot.assetId || shot.locked} onChange={(event) => onChange({ sourceEndMs: clamp(Math.round(Number(event.target.value) * 1000), shot.sourceStartMs + 100, duration) })} className="mt-1 w-full rounded-lg border border-line p-2 text-xs text-text disabled:opacity-50" /></label></div>
    <div className="relative mt-3 h-1.5 overflow-hidden rounded-full bg-canvas"><span className="absolute inset-y-0 rounded-full bg-blue" style={{ left: `${shot.sourceStartMs / duration * 100}%`, right: `${100 - shot.sourceEndMs / duration * 100}%` }} /></div>
  </section>;
}

export function MvpScriptComposer({
  workspace, selectedScene, selectedShot, operationPending, onSelectScene, onSelectShot,
  onUpdateDocumentSettings, onUpdateGlobalScope, onUpdateScene, onMoveScene, onUpdateShot, onMoveShot, onSplitShot, onRemoveShotAsset, onDuplicateShot, onRestoreSubtitle, onAddScene,
  onAddShot, onDeleteScene, onDeleteShot, onUpload, onRunOperation,
}: Props) {
  const [resourceTab, setResourceTab] = useState<ResourceTab>("outline");
  const [globalScopeMode, setGlobalScopeMode] = useState<"film" | "scene">("film");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("visual");
  const [assetSearch, setAssetSearch] = useState("");
  const [playing, setPlaying] = useState(false);
  const [previewMuted, setPreviewMuted] = useState(false);
  const [playheadMs, setPlayheadMs] = useState(0);
  const stageRef = useRef<HTMLDivElement | null>(null);
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
  const audioAssets = workspace.linkedAssets.filter((asset) => asset.mediaType === "audio");
  const visualAssets = workspace.linkedAssets.filter((asset) => asset.mediaType !== "audio");
  const audioMix = workspace.document.settings.globalAudio;
  const activeGlobalScope = globalScopeMode === "scene" && selectedScene?.id
    ? workspace.document.globalScopes.scenes[selectedScene.id] ?? {}
    : workspace.document.globalScopes.film;
  const selectedAsset = workspace.linkedAssets.find((asset) => asset.id === selectedShot?.assetId);
  const selectedAssetDurationMs = Math.max(selectedShot?.sourceEndMs ?? 0, selectedAsset?.durationMs ?? 0, selectedShot?.durationMs ?? 100);
  const selectedSceneIndex = scenes.findIndex((scene) => scene.id === selectedScene?.id);
  const selectedSceneLastShot = selectedScene?.shots.at(-1);

  useEffect(() => { playheadRef.current = playheadMs; }, [playheadMs]);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let previous = performance.now();
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
      playheadRef.current = next; setPlayheadMs(next); frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [model.durationMs, playing]);
  useEffect(() => {
    if (playing && activeShot?.id && activeShot.id !== selectedShot?.id) onSelectShot(activeShot.id);
  }, [activeShot?.id, onSelectShot, playing, selectedShot?.id]);
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
  function chooseAsset(asset?: Asset) {
    if (!selectedScene?.id || !selectedShot?.id) return;
    onUpdateShot(selectedScene.id, selectedShot.id, { assetId: asset?.id, visualMode: asset?.mediaType === "image" ? "image" : asset ? "video" : undefined, selectedMediaVersionId: undefined, sourceStartMs: 0, sourceEndMs: asset?.durationMs || selectedShot.durationMs });
  }
  function chooseCandidate(candidateId: string) {
    const candidate = selectedShot?.candidates.find((item) => item.id === candidateId);
    if (!candidate) return;
    const segment = workspace.linkedAssets.flatMap((asset) => asset.segments.map((item) => ({ asset, segment: item }))).find(({ segment }) => segment.id === candidate.segmentId);
    if (!segment) return;
    patchSelectedShot({
      assetId: segment.asset.id,
      segmentId: segment.segment.id,
      visualMode: segment.asset.mediaType === "image" ? "image" : "video",
      selectedMediaVersionId: undefined,
      sourceStartMs: candidate.rangeStartMs || segment.segment.startMs,
      sourceEndMs: candidate.rangeEndMs || segment.segment.endMs,
    });
  }
  function patchSelectedShot(patch: Partial<Shot>) {
    if (selectedScene?.id && selectedShot?.id) onUpdateShot(selectedScene.id, selectedShot.id, patch);
  }
  function patchSceneTransition(patch: Record<string, unknown>) {
    if (!selectedScene?.id || !selectedSceneLastShot?.id) return;
    onUpdateShot(selectedScene.id, selectedSceneLastShot.id, {
      transition: { ...selectedSceneLastShot.transition, ...patch },
    });
  }
  function splitSelectedShot() {
    if (!selectedScene?.id || !selectedShot?.id || selectedShot.durationMs < 200) return;
    const meta = model.shots.find((shot) => shot.id === selectedShot.id);
    const localOffset = meta ? playheadRef.current - meta.startMs : selectedShot.durationMs / 2;
    const offsetMs = localOffset > 100 && localOffset < selectedShot.durationMs - 100
      ? localOffset
      : selectedShot.durationMs / 2;
    setPlaying(false);
    onSplitShot(selectedScene.id, selectedShot.id, Math.round(offsetMs));
  }
  function selectMediaVersion(versionId: string) {
    const version = selectedShot?.mediaVersions.find((item) => item.id === versionId);
    if (!version) return;
    setPlaying(false);
    patchSelectedShot({ selectedMediaVersionId: version.id, assetId: version.assetId });
  }
  function restoreMediaVersionSource() {
    if (!selectedShot?.selectedMediaVersionId) return;
    const current = selectedShot.mediaVersions.find((item) => item.id === selectedShot.selectedMediaVersionId);
    if (!current) return;
    const snapshot = current.parameters.source_snapshot && typeof current.parameters.source_snapshot === "object"
      ? current.parameters.source_snapshot as Record<string, unknown>
      : {};
    const parent = current.parentVersionId
      ? selectedShot.mediaVersions.find((item) => item.id === current.parentVersionId)
      : undefined;
    setPlaying(false);
    patchSelectedShot({
      selectedMediaVersionId: parent?.id,
      assetId: String(snapshot.asset_id ?? parent?.assetId ?? "") || undefined,
      visualMode: typeof snapshot.visual_mode === "string" ? snapshot.visual_mode : selectedShot.visualMode,
      sourceStartMs: numeric(snapshot.source_start_ms, selectedShot.sourceStartMs),
      sourceEndMs: numeric(snapshot.source_end_ms, selectedShot.sourceEndMs),
      transform: snapshot.transform && typeof snapshot.transform === "object" ? snapshot.transform as Record<string, unknown> : selectedShot.transform,
      adjust: snapshot.adjust && typeof snapshot.adjust === "object" ? snapshot.adjust as Shot["adjust"] : selectedShot.adjust,
      motion: snapshot.motion && typeof snapshot.motion === "object" ? snapshot.motion as Shot["motion"] : selectedShot.motion,
    });
  }
  function patchRecord(field: "adjust" | "motion" | "transition" | "subtitleSettings" | "audioSettings", patch: Record<string, unknown>) {
    if (!selectedShot) return;
    patchSelectedShot({ [field]: { ...selectedShot[field], ...patch } });
  }
  function patchAudioMix(patch: Partial<ProjectAudioMix>) {
    onUpdateDocumentSettings({ globalAudio: { ...audioMix, ...patch } });
  }
  function patchGlobalScope(patch: Partial<GlobalScopeLayers>) {
    onUpdateGlobalScope(globalScopeMode, globalScopeMode === "scene" ? selectedScene?.id : undefined, patch);
  }
  function setDefaultAudioAsset(role: "voice" | "music", assetId?: string) {
    patchAudioMix(role === "voice" ? { voiceAssetId: assetId } : { musicAssetId: assetId });
  }
  function setGlobalMusic(assetId?: string) {
    patchGlobalScope({ backgroundMusic: assetId ? { assetId, volume: numeric(activeGlobalScope.backgroundMusic?.volume, 28), loop: true } : null });
  }
  function toggleGlobalAsset(field: "soundEffects" | "visualAssets", asset: Asset) {
    const current = scopeReferenceList(activeGlobalScope[field]);
    const selected = current.some((item) => item.assetId === asset.id);
    patchGlobalScope({
      [field]: selected
        ? current.filter((item) => item.assetId !== asset.id)
        : [...current, field === "soundEffects"
          ? { id: `sfx-${globalScopeMode}-${asset.id}`, assetId: asset.id, volume: 72, atMs: 0 }
          : { id: `visual-${globalScopeMode}-${asset.id}`, assetId: asset.id, opacity: 32, blendMode: "normal", fitMode: "cover", enabled: true }],
    });
  }
  function toggleFullscreen() {
    if (!stageRef.current) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stageRef.current.requestFullscreen();
  }

  return <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_218px] overflow-hidden bg-[#e9eaed]">
    <div className="grid min-h-0 grid-cols-[264px_minmax(480px,1fr)_320px] gap-px overflow-hidden bg-line">
      <aside className="flex min-h-0 bg-white">
        <nav className="flex w-[58px] shrink-0 flex-col items-center gap-1 border-r border-line py-3">{resources.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setResourceTab(id)} className={`flex w-12 flex-col items-center gap-1 rounded-lg py-2 text-[10px] ${resourceTab === id ? "bg-blue-soft text-blue" : "text-muted hover:bg-canvas"}`}><Icon size={16} /><span>{label}</span></button>)}</nav>
        <div className="min-w-0 flex-1 overflow-y-auto p-3">
          {resourceTab === "outline" && <><div className="mb-3 flex items-center justify-between"><div><strong className="text-sm text-text">影片结构</strong><p className="text-[10px] text-muted">{scenes.length} 个场景 · {model.shots.length} 个镜头</p></div><button type="button" onClick={onAddScene} className="rounded-md bg-blue-soft p-1.5 text-blue"><Plus size={14} /></button></div><div className="space-y-2">{scenes.map((scene, sceneIndex) => <div key={scene.id ?? sceneIndex} className={`rounded-xl border ${scene.id === selectedScene?.id ? "border-blue bg-blue-soft/30" : "border-line"}`}><button type="button" onClick={() => onSelectScene(scene.id ?? null)} className="w-full p-3 text-left"><span className="text-[10px] font-medium text-muted">场景 {sceneIndex + 1} · {scene.shots.length} 镜头</span><strong className="mt-1 block truncate text-xs text-text">{scene.outline || "未命名场景"}</strong></button>{scene.id === selectedScene?.id && <div className="border-t border-blue/10 px-2 pb-2 pt-1">{scene.shots.map((shot, index) => <button type="button" key={shot.id ?? index} onClick={() => selectShotForPreview(shot.id ?? null)} className={`mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px] ${shot.id === selectedShot?.id ? "bg-blue text-white" : "text-muted hover:bg-white"}`}><span>{index + 1}</span><span className="truncate">{shot.description || "空镜头"}</span></button>)}</div>}</div>)}</div></>}
          {resourceTab === "assets" && <><div className="mb-3 flex items-center justify-between"><strong className="text-sm text-text">项目素材</strong><button type="button" onClick={onUpload} className="rounded-md bg-blue-soft p-1.5 text-blue"><CloudUpload size={14} /></button></div><label className="mb-3 flex items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-muted"><Search size={13} /><input value={assetSearch} onChange={(event) => setAssetSearch(event.target.value)} placeholder="搜索素材" className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><div className="grid grid-cols-2 gap-2">{visibleAssets.map((asset) => <button key={asset.id} type="button" onClick={() => chooseAsset(asset)} className={`overflow-hidden rounded-lg border text-left ${asset.id === selectedShot?.assetId ? "border-blue ring-1 ring-blue" : "border-line"}`}><div className="relative aspect-video bg-canvas"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={false} /></div><span className="block truncate p-1.5 text-[10px] text-text">{asset.name}</span></button>)}</div>{!visibleAssets.length && <div className="py-12 text-center text-xs text-muted">暂无匹配素材</div>}</>}
          {resourceTab === "audio" && <div>
            <div className="flex items-center justify-between"><div><strong className="text-sm text-text">项目默认声音</strong><p className="mt-1 text-[10px] text-muted">场景或镜头没有覆盖时生效</p></div><button type="button" onClick={onUpload} className="rounded-md bg-blue-soft p-1.5 text-blue"><CloudUpload size={14} /></button></div>
            <section className="mt-3 rounded-xl border border-line p-3"><div className="flex items-center gap-2 text-xs"><Mic2 size={14} className="text-blue" /><strong>项目旁白</strong></div><select aria-label="项目旁白" value={String(audioMix.voiceAssetId ?? "")} onChange={(event) => setDefaultAudioAsset("voice", event.target.value || undefined)} className="mt-2 w-full rounded-lg border border-line p-2 text-xs"><option value="">尚未选择</option>{audioAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select><div className="mt-2"><RangeControl label="旁白音量" value={numeric(audioMix.voiceVolume, 100)} minimum={0} maximum={100} suffix="%" onChange={(voiceVolume) => patchAudioMix({ voiceVolume })} /></div><label className="mt-2 flex items-center gap-2 text-[10px] text-muted"><input type="checkbox" checked={!audioMix.voiceMuted} onChange={(event) => patchAudioMix({ voiceMuted: !event.target.checked })} />启用旁白</label></section>
            <section className="mt-2 rounded-xl border border-line p-3"><div className="flex items-center gap-2 text-xs"><Music2 size={14} className="text-blue" /><strong>默认背景音乐</strong></div><select aria-label="默认背景音乐" value={String(audioMix.musicAssetId ?? "")} onChange={(event) => setDefaultAudioAsset("music", event.target.value || undefined)} className="mt-2 w-full rounded-lg border border-line p-2 text-xs"><option value="">尚未选择</option>{audioAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select><div className="mt-2"><RangeControl label="音乐音量" value={numeric(audioMix.musicVolume, 24)} minimum={0} maximum={100} suffix="%" onChange={(musicVolume) => patchAudioMix({ musicVolume })} /></div><label className="mt-2 flex items-center gap-2 text-[10px] text-muted"><input type="checkbox" checked={audioMix.duckingEnabled !== false} onChange={(event) => patchAudioMix({ duckingEnabled: event.target.checked })} />旁白出现时自动压低音乐</label></section>
            {!audioAssets.length && <p className="mt-3 text-center text-xs text-muted">上传音频后可指定角色</p>}
          </div>}
          {resourceTab === "global" && <div>
            <strong className="text-sm text-text">全局层</strong><p className="mt-1 text-[11px] leading-5 text-muted">全片设置默认生效，场景层可覆盖背景音乐并叠加音效和画面。</p>
            <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg bg-canvas p-1"><button type="button" onClick={() => setGlobalScopeMode("film")} className={`rounded-md py-1.5 text-[10px] ${globalScopeMode === "film" ? "bg-white font-semibold text-blue shadow-sm" : "text-muted"}`}>全片</button><button type="button" disabled={!selectedScene?.id} onClick={() => setGlobalScopeMode("scene")} className={`rounded-md py-1.5 text-[10px] ${globalScopeMode === "scene" ? "bg-white font-semibold text-blue shadow-sm" : "text-muted"}`}>当前场景</button></div>
            <div className="mt-3 rounded-xl border border-line p-3"><strong className="text-xs">背景音乐</strong><select aria-label="当前范围背景音乐" value={String(activeGlobalScope.backgroundMusic?.assetId ?? "")} onChange={(event) => setGlobalMusic(event.target.value || undefined)} className="mt-2 w-full rounded-lg border border-line p-2 text-xs"><option value="">继承项目默认</option>{audioAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select>{activeGlobalScope.backgroundMusic && <div className="mt-2"><RangeControl label="音乐音量" value={numeric(activeGlobalScope.backgroundMusic.volume, 28)} minimum={0} maximum={100} suffix="%" onChange={(volume) => patchGlobalScope({ backgroundMusic: { ...activeGlobalScope.backgroundMusic!, volume } })} /></div>}</div>
            <div className="mt-2 rounded-xl border border-line p-3"><strong className="text-xs">音效层</strong><div className="mt-2 flex flex-wrap gap-1">{audioAssets.map((asset) => { const active = scopeReferenceList(activeGlobalScope.soundEffects).some((item) => item.assetId === asset.id); return <button key={asset.id} type="button" onClick={() => toggleGlobalAsset("soundEffects", asset)} className={`max-w-full truncate rounded-full border px-2 py-1 text-[9px] ${active ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{asset.name}</button>; })}</div></div>
            <div className="mt-2 rounded-xl border border-line p-3"><strong className="text-xs">共享视觉素材</strong><div className="mt-2 grid grid-cols-2 gap-1">{visualAssets.slice(0, 8).map((asset) => { const active = scopeReferenceList(activeGlobalScope.visualAssets).some((item) => item.assetId === asset.id); return <button key={asset.id} type="button" onClick={() => toggleGlobalAsset("visualAssets", asset)} className={`truncate rounded-md border px-2 py-1.5 text-[9px] ${active ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{asset.name}</button>; })}</div></div>
            <label className="mt-3 block text-[11px] text-muted">画幅<select value={workspace.document.settings.aspectRatio} onChange={(event) => onUpdateDocumentSettings({ aspectRatio: event.target.value as ProjectDocumentSettings["aspectRatio"] })} className="mt-1.5 w-full rounded-lg border border-line p-2.5 text-sm text-text"><option value="16:9">横屏 16:9</option><option value="9:16">竖屏 9:16</option><option value="1:1">方形 1:1</option><option value="4:3">经典 4:3</option></select></label><div className="mt-3 rounded-xl border border-line p-3"><span className="text-[10px] text-muted">分辨率 / 帧率</span><strong className="mt-1 block text-sm">{workspace.document.settings.resolution} · {workspace.document.settings.fps}fps</strong></div>
          </div>}
        </div>
      </aside>

      <main className="flex min-h-0 flex-col overflow-hidden bg-[#f5f5f6]">
        <div className="flex min-h-0 flex-1 items-center justify-center p-5"><div ref={stageRef} style={aspectRatioStyle(workspace.document.settings.aspectRatio)} className={`group relative max-h-full overflow-hidden rounded-xl bg-[#111318] shadow-xl [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:max-w-none [&:fullscreen]:rounded-none ${stageSizeClass(workspace.document.settings.aspectRatio)}`}><div className="absolute inset-0" style={transition.active ? transitionLayerStyle(transition.type, transition.progress, "current") : undefined}><CompositionMedia meta={activeShot} playheadMs={playheadMs} playing={playing} muted={previewMuted} /></div>{transition.active && <div className="absolute inset-0" style={transitionLayerStyle(transition.type, transition.progress, "next")}><CompositionMedia meta={nextShot} playheadMs={nextShot?.startMs ?? 0} playing={false} muted /></div>}<CompositionOverlays workspace={workspace} model={model} activeShot={activeShot} playheadMs={playheadMs} /><CompositionAudioMix workspace={workspace} model={model} activeShot={activeShot} playheadMs={playheadMs} playing={playing} muted={previewMuted} /><div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-black/10" />{activeShot?.shot.subtitleText && <div className="pointer-events-none absolute inset-x-[7%] z-10" style={subtitleStyle(activeShot.shot)}><span className="inline-block rounded-md bg-black/60 px-3 py-1.5 leading-relaxed text-white shadow-sm backdrop-blur-sm">{activeShot.shot.subtitleText}</span></div>}<div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/45 px-2.5 py-1 text-[10px] text-white/80 backdrop-blur"><span>场景 {(activeShot?.scene.index ?? 0) + 1}</span><i className="h-1 w-1 rounded-full bg-white/35" /><span>镜头 {(activeShot?.shot.index ?? 0) + 1}</span>{transition.active && <><i className="h-1 w-1 rounded-full bg-white/35" /><span>{transition.type} {Math.round(transition.progress * 100)}%</span></>}</div><div className="absolute right-3 top-3 flex gap-1 opacity-0 transition group-hover:opacity-100"><button type="button" onClick={() => setPreviewMuted((value) => !value)} aria-label={previewMuted ? "打开声音" : "静音"} className="grid h-8 w-8 place-items-center rounded-lg bg-black/45 text-white backdrop-blur">{previewMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}</button><button type="button" onClick={toggleFullscreen} aria-label="全屏预览" className="grid h-8 w-8 place-items-center rounded-lg bg-black/45 text-white backdrop-blur"><Maximize2 size={14} /></button></div><button type="button" onClick={togglePlayback} aria-label={playing ? "暂停" : "播放"} className="absolute left-1/2 top-1/2 z-20 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/55 text-white opacity-0 backdrop-blur transition hover:bg-black/70 group-hover:opacity-100">{playing ? <Pause size={19} /> : <Play size={19} className="translate-x-px" />}</button></div></div>
        <div className="flex h-12 items-center gap-3 border-t border-line bg-white px-4"><button type="button" onClick={togglePlayback} className="grid h-8 w-8 place-items-center rounded-full bg-ink text-white">{playing ? <Pause size={14} /> : <Play size={14} />}</button><button type="button" onClick={() => seek(playheadMs - 5000)} className="text-[10px] text-muted">−5s</button><span className="w-28 text-xs tabular-nums text-muted">{formatTime(playheadMs)} / {formatTime(model.durationMs)}</span><input type="range" min={0} max={model.durationMs} value={playheadMs} onChange={(event) => { setPlaying(false); seek(Number(event.target.value)); }} className="min-w-0 flex-1 accent-blue" /><button type="button" onClick={() => seek(playheadMs + 5000)} className="text-[10px] text-muted">+5s</button><span className="rounded-md bg-canvas px-2 py-1 text-[10px] text-muted">Composition 实时预览</span></div>
      </main>

      <aside className="min-h-0 overflow-y-auto bg-white"><div className="sticky top-0 z-10 grid grid-cols-4 border-b border-line bg-white">{inspectors.map((item) => <button key={item.id} type="button" onClick={() => setInspectorTab(item.id)} className={`border-b-2 px-1 py-3 text-xs ${inspectorTab === item.id ? "border-blue font-semibold text-blue" : "border-transparent text-muted"}`}>{item.label}</button>)}</div>{!selectedShot || !selectedScene?.id ? <div className="grid min-h-[360px] place-items-center p-8 text-center text-xs text-muted">选择一个镜头查看属性</div> : <div className="space-y-4 p-4"><div className="flex items-center justify-between"><div><span className="text-[10px] text-muted">当前镜头</span><strong className="block text-sm text-text">场景 {selectedScene.index + 1} · 镜头 {selectedShot.index + 1}</strong></div><div className="flex gap-0.5"><button type="button" disabled={selectedShot.index <= 0} onClick={() => onMoveShot(selectedScene.id!, selectedShot.id!, -1)} aria-label="镜头上移" className="rounded-lg p-2 text-muted hover:bg-canvas disabled:opacity-25"><ArrowUp size={14} /></button><button type="button" disabled={selectedShot.index >= selectedScene.shots.length - 1} onClick={() => onMoveShot(selectedScene.id!, selectedShot.id!, 1)} aria-label="镜头下移" className="rounded-lg p-2 text-muted hover:bg-canvas disabled:opacity-25"><ArrowDown size={14} /></button><button type="button" onClick={() => onDuplicateShot(selectedScene.id!, selectedShot.id!)} aria-label="复制镜头" className="rounded-lg p-2 text-muted hover:bg-canvas"><Copy size={14} /></button><button type="button" onClick={onDeleteShot} aria-label="删除镜头" className="rounded-lg p-2 text-muted hover:bg-red/10 hover:text-red"><Trash2 size={15} /></button></div></div>
        {inspectorTab === "visual" && <><SourceTrimControl shot={selectedShot} assetDurationMs={selectedAssetDurationMs} onChange={patchSelectedShot} /><div className="grid grid-cols-2 gap-2"><button type="button" onClick={splitSelectedShot} disabled={!selectedShot.assetId || selectedShot.durationMs <= 200} className="rounded-lg border border-line py-2 text-xs text-muted hover:border-blue hover:text-blue disabled:opacity-35">拆分片段</button><button type="button" onClick={() => selectedScene.id && selectedShot.id && onRemoveShotAsset(selectedScene.id, selectedShot.id)} disabled={!selectedShot.assetId && !selectedShot.selectedMediaVersionId} className="rounded-lg border border-red/20 py-2 text-xs text-red disabled:opacity-35">移除素材</button></div></>}
        {inspectorTab === "visual" && selectedShot.candidates.length > 0 && <section className="rounded-xl border border-line p-3"><header className="flex items-center justify-between"><strong className="text-xs text-text">素材匹配候选</strong><span className="text-[9px] text-muted">{selectedShot.candidates.length} 个</span></header><div className="mt-2 space-y-1.5">{selectedShot.candidates.slice(0, 5).map((candidate) => { const available = workspace.linkedAssets.some((asset) => asset.segments.some((segment) => segment.id === candidate.segmentId)); return <button type="button" key={candidate.id} disabled={!available} onClick={() => chooseCandidate(candidate.id)} className="w-full rounded-lg border border-line p-2 text-left disabled:opacity-45"><span className="flex items-center justify-between gap-2"><strong className="truncate text-[10px] text-text">{candidate.title || "候选片段"}</strong><em className="text-[9px] not-italic text-teal">{candidate.score}%</em></span><small className="mt-1 block line-clamp-2 text-[9px] leading-4 text-muted">{available ? candidate.reason || candidate.source : "源片段不可用，记录仍保留"}</small></button>; })}</div></section>}
        {inspectorTab === "visual" && <><label className="block text-xs font-medium text-muted">画面描述<textarea rows={3} value={selectedShot.description} onChange={(event) => patchSelectedShot({ description: event.target.value })} className="mt-1.5 w-full resize-y rounded-lg border border-line p-2.5 text-sm leading-5 text-text" /></label><div className="grid grid-cols-2 gap-2"><label className="block text-[11px] text-muted">镜头时长（秒）<input type="number" min={0.1} step={0.1} value={selectedShot.durationMs / 1000} onChange={(event) => patchSelectedShot({ durationMs: Math.max(100, Math.round(Number(event.target.value) * 1000)) })} className="mt-1.5 w-full rounded-lg border border-line p-2 text-sm text-text" /></label><label className="block text-[11px] text-muted">使用素材<select value={selectedShot.assetId ?? ""} onChange={(event) => chooseAsset(workspace.linkedAssets.find((asset) => asset.id === event.target.value))} className="mt-1.5 w-full rounded-lg border border-line p-2 text-sm text-text"><option value="">未选择</option>{workspace.linkedAssets.filter((asset) => asset.mediaType !== "audio").map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select></label></div><section className="rounded-xl border border-line p-3"><header className="mb-2 flex items-center justify-between"><strong className="text-xs text-text">构图与位置</strong><button type="button" onClick={() => patchSelectedShot({ transform: {} })} className="flex items-center gap-1 text-[10px] text-muted"><RotateCcw size={11} />重置</button></header><div className="grid grid-cols-2 gap-1"><button type="button" onClick={() => patchSelectedShot({ transform: { ...selectedShot.transform, fitMode: "cover" } })} className={`rounded-md border py-1.5 text-[10px] ${String(selectedShot.transform.fitMode ?? "cover") === "cover" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>填充画面</button><button type="button" onClick={() => patchSelectedShot({ transform: { ...selectedShot.transform, fitMode: "contain" } })} className={`rounded-md border py-1.5 text-[10px] ${selectedShot.transform.fitMode === "contain" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>完整适应</button></div><div className="mt-3 space-y-2"><RangeControl label="缩放" value={numeric(selectedShot.transform.scale, 100)} minimum={25} maximum={300} suffix="%" onChange={(scale) => patchSelectedShot({ transform: { ...selectedShot.transform, scale } })} /><RangeControl label="水平位置" value={numeric(selectedShot.transform.x)} minimum={-100} maximum={100} suffix="%" onChange={(x) => patchSelectedShot({ transform: { ...selectedShot.transform, x } })} /><RangeControl label="垂直位置" value={numeric(selectedShot.transform.y)} minimum={-100} maximum={100} suffix="%" onChange={(y) => patchSelectedShot({ transform: { ...selectedShot.transform, y } })} /></div></section><section className="rounded-xl border border-line p-3"><header className="mb-2 flex items-center justify-between"><strong className="text-xs text-text">滤镜与调色</strong><button type="button" onClick={() => patchSelectedShot({ adjust: {} })} className="flex items-center gap-1 text-[10px] text-muted"><RotateCcw size={11} />重置</button></header><div className="grid grid-cols-4 gap-1">{filterPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("adjust", { filterPreset: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedShot.adjust.filterPreset ?? "original") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div><div className="mt-3 space-y-2"><RangeControl label="亮度" value={numeric(selectedShot.adjust.brightness)} minimum={-100} maximum={100} onChange={(value) => patchRecord("adjust", { brightness: value })} /><RangeControl label="对比度" value={numeric(selectedShot.adjust.contrast)} minimum={-100} maximum={100} onChange={(value) => patchRecord("adjust", { contrast: value })} /><RangeControl label="饱和度" value={numeric(selectedShot.adjust.saturation)} minimum={-100} maximum={100} onChange={(value) => patchRecord("adjust", { saturation: value })} /><RangeControl label="色相" value={numeric(selectedShot.adjust.hue)} minimum={-180} maximum={180} onChange={(value) => patchRecord("adjust", { hue: value })} /><RangeControl label="色温" value={numeric(selectedShot.adjust.temperature)} minimum={-100} maximum={100} onChange={(value) => patchRecord("adjust", { temperature: value })} /></div></section><section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">镜头运动</strong><div className="mt-2 grid grid-cols-4 gap-1">{motionPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("motion", { type: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedShot.motion.type ?? "none") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>{String(selectedShot.motion.type ?? "none") !== "none" && <div className="mt-3"><RangeControl label="运动强度" value={numeric(selectedShot.motion.strength, 40)} minimum={0} maximum={100} suffix="%" onChange={(value) => patchRecord("motion", { strength: value })} /></div>}</section><section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">镜头转场</strong><div className="mt-2 grid grid-cols-3 gap-1">{transitionPresets.map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("transition", { type: value })} className={`rounded-md border px-1 py-1.5 text-[10px] ${String(selectedShot.transition.type ?? "cut") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div>{!["cut", "none"].includes(String(selectedShot.transition.type ?? "cut")) && <div className="mt-3"><RangeControl label="转场时长" value={numeric(selectedShot.transition.durationMs, 500)} minimum={100} maximum={3000} suffix="ms" onChange={(value) => patchRecord("transition", { durationMs: value })} /></div>}</section><div className="grid grid-cols-2 gap-2"><button type="button" disabled={operationPending} onClick={() => onRunOperation("generate_image")} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-xs hover:border-blue hover:text-blue"><ImageIcon size={13} />AI 图片</button><button type="button" disabled={operationPending} onClick={() => onRunOperation("generate_video")} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2 text-xs hover:border-blue hover:text-blue"><Film size={13} />AI 视频</button></div></>}
        {inspectorTab === "audio" && <><div className="rounded-xl border border-line p-3"><div className="flex items-center gap-2"><AudioLines size={15} className="text-blue" /><strong className="text-xs">镜头原声</strong></div><div className="mt-3"><RangeControl label="音量" value={numeric(selectedShot.audioSettings.originalVolume, numeric(audioMix.originalVolume, 30))} minimum={0} maximum={100} suffix="%" onChange={(value) => patchRecord("audioSettings", { originalVolume: value })} /></div></div><div className="rounded-xl border border-line p-3"><div className="flex items-center gap-2"><Mic2 size={15} className="text-blue" /><strong className="text-xs">项目旁白</strong></div><p className="mt-2 truncate text-[11px] text-muted">{audioAssets.find((asset) => asset.id === audioMix.voiceAssetId)?.name ?? "尚未选择旁白"}</p><div className="mt-3"><RangeControl label="旁白音量" value={numeric(audioMix.voiceVolume, 100)} minimum={0} maximum={100} suffix="%" onChange={(voiceVolume) => patchAudioMix({ voiceVolume })} /></div></div><div className="rounded-xl border border-line p-3"><div className="flex items-center gap-2"><Music2 size={15} className="text-blue" /><strong className="text-xs">当前镜头音乐覆盖</strong></div><select aria-label="镜头背景音乐覆盖" value={String(selectedShot.audioSettings.backgroundMusic?.assetId ?? "")} onChange={(event) => patchRecord("audioSettings", { backgroundMusic: event.target.value ? { assetId: event.target.value, volume: 28, loop: true } : null })} className="mt-2 w-full rounded-lg border border-line p-2 text-xs"><option value="">继承场景 / 全片</option>{audioAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select>{selectedShot.audioSettings.backgroundMusic && <div className="mt-3"><RangeControl label="覆盖音量" value={numeric(selectedShot.audioSettings.backgroundMusic.volume, 28)} minimum={0} maximum={100} suffix="%" onChange={(volume) => patchRecord("audioSettings", { backgroundMusic: { ...selectedShot.audioSettings.backgroundMusic!, volume } })} /></div>}</div><button type="button" onClick={() => setResourceTab("audio")} className="w-full rounded-lg bg-blue-soft py-2 text-xs font-semibold text-blue">管理项目默认声音</button></>}
        {inspectorTab === "caption" && <><label className="block text-xs font-medium text-muted">字幕<textarea rows={5} value={selectedShot.subtitleText} onChange={(event) => patchSelectedShot({ subtitleText: event.target.value, subtitleOverridden: event.target.value !== selectedScene.narrationText, subtitleOutdated: false })} className="mt-1.5 w-full resize-y rounded-lg border border-line p-2.5 text-sm leading-5 text-text" /></label>{selectedShot.subtitleOutdated && <div className="rounded-lg bg-amber/10 p-2.5 text-[11px] leading-5 text-amber">场景旁白已变化，当前手工字幕需要复核。<button type="button" onClick={() => onRestoreSubtitle(selectedScene.id!, selectedShot.id!)} className="ml-1 font-semibold underline">恢复跟随旁白</button></div>}<section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">字幕位置</strong><div className="mt-2 grid grid-cols-3 gap-1">{[["top", "顶部"], ["center", "居中"], ["bottom", "底部"]].map(([value, label]) => <button key={value} type="button" onClick={() => patchRecord("subtitleSettings", { position: value })} className={`rounded-md border py-1.5 text-[10px] ${String(selectedShot.subtitleSettings.position ?? "bottom") === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>{label}</button>)}</div><div className="mt-3"><RangeControl label="字号" value={numeric(selectedShot.subtitleSettings.fontSize, 16)} minimum={10} maximum={48} suffix="px" onChange={(value) => patchRecord("subtitleSettings", { fontSize: value })} /></div></section><p className="text-xs leading-5 text-muted">{selectedShot.subtitleOverridden ? "当前字幕为手动覆盖；场景旁白变化时会提示复核。" : "字幕正在跟随场景旁白。"}</p></>}
        {inspectorTab === "process" && <><section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">非破坏性 AI 处理</strong><p className="mt-1 text-[10px] leading-4 text-muted">每次生成都会创建新的 Asset 和媒体版本，原素材及镜头参数不会被覆盖。</p><div className="mt-3 grid grid-cols-2 gap-2">{(["complete_shots", "generate_effect"] as ProjectOperation[]).map((operation) => <button key={operation} type="button" disabled={operationPending} onClick={() => onRunOperation(operation)} className="flex items-center justify-center gap-1 rounded-lg border border-line py-2.5 text-xs hover:border-blue hover:text-blue"><WandSparkles size={13} />{operation === "complete_shots" ? "完善镜头" : "视觉特效"}</button>)}</div></section><section className="rounded-xl border border-line p-3"><strong className="text-xs text-text">版本状态</strong><div className="mt-2 space-y-2">{selectedShot.selectedMediaVersionId && <button type="button" onClick={restoreMediaVersionSource} aria-label="恢复上一个媒体版本" className="flex w-full items-center gap-2 rounded-lg border border-line p-2 text-left text-xs text-muted hover:border-blue hover:text-blue"><RotateCcw size={13} /><span><strong className="block text-text">恢复处理前版本</strong><small>同时恢复素材、入出点、构图、调色和运镜</small></span></button>}{selectedShot.mediaVersions.map((version) => { const active = selectedShot.selectedMediaVersionId === version.id; return <button key={version.id} type="button" onClick={() => selectMediaVersion(version.id)} aria-pressed={active} className={`w-full rounded-lg border p-2 text-left text-xs ${active ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}><strong className="block">{version.operation || version.kind}</strong><small>{active ? `${version.status} · 当前正在使用` : `${version.status} · 点击切换`}</small></button>; })}{!selectedShot.mediaVersions.length && <div className="rounded-lg border border-dashed border-line p-3 text-center text-[10px] text-muted">暂无处理版本</div>}</div></section></>}
        <div className="border-t border-line pt-4"><div className="flex items-center justify-between"><strong className="text-xs text-text">场景设置</strong><div className="flex gap-1"><button type="button" aria-label="场景上移" disabled={selectedSceneIndex <= 0} onClick={() => onMoveScene(selectedScene.id!, -1)} className="grid h-7 w-7 place-items-center rounded border border-line text-muted disabled:opacity-30"><ArrowUp size={12} /></button><button type="button" aria-label="场景下移" disabled={selectedSceneIndex < 0 || selectedSceneIndex >= scenes.length - 1} onClick={() => onMoveScene(selectedScene.id!, 1)} className="grid h-7 w-7 place-items-center rounded border border-line text-muted disabled:opacity-30"><ArrowDown size={12} /></button></div></div><label className="mt-3 block text-xs font-medium text-muted">场景标题<input value={selectedScene.outline} onChange={(event) => onUpdateScene(selectedScene.id!, { outline: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line p-2.5 text-sm text-text" /></label><label className="mt-3 block text-xs font-medium text-muted">场景旁白<textarea rows={3} value={selectedScene.narrationText} onChange={(event) => onUpdateScene(selectedScene.id!, { narrationText: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line p-2.5 text-sm text-text" /></label>{selectedSceneIndex < scenes.length - 1 && selectedSceneLastShot && <section className="mt-3 rounded-xl border border-line p-3"><strong className="text-xs text-text">场景结束转场</strong><select aria-label="场景结束转场" value={String(selectedSceneLastShot.transition.type ?? "cut")} onChange={(event) => patchSceneTransition({ type: event.target.value })} className="mt-2 w-full rounded-lg border border-line p-2 text-xs text-text">{transitionPresets.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>{!["cut", "none"].includes(String(selectedSceneLastShot.transition.type ?? "cut")) && <div className="mt-2"><RangeControl label="转场时长" value={numeric(selectedSceneLastShot.transition.durationMs, 800)} minimum={100} maximum={3000} suffix="ms" onChange={(durationMs) => patchSceneTransition({ durationMs })} /></div>}<p className="mt-2 text-[10px] leading-4 text-muted">直接使用本场景最后一个镜头的转场，不保存重复状态。</p></section>}<div className="mt-3 flex gap-2"><button type="button" onClick={() => onAddShot(selectedScene.id!)} className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-blue-soft py-2 text-xs font-semibold text-blue"><Plus size={13} />新增镜头</button><button type="button" onClick={onDeleteScene} className="rounded-lg border border-line px-3 text-muted hover:text-red"><Trash2 size={14} /></button></div></div></div>}</aside>
    </div>

    <section className="border-t border-line bg-[#f9f9fa]"><header className="flex h-10 items-center justify-between border-b border-line px-3"><div className="flex items-center gap-2"><strong className="text-xs text-text">主时间线</strong><span className="text-[10px] text-muted">{formatTime(model.durationMs)}</span></div><button type="button" disabled={operationPending} onClick={() => onRunOperation("match_assets")} className="flex items-center gap-1 rounded-md bg-blue-soft px-2 py-1.5 text-[10px] font-semibold text-blue"><Sparkles size={11} />匹配全部镜头</button></header><div className="grid h-[176px] grid-cols-[84px_1fr] overflow-hidden"><div className="border-r border-line bg-white pt-7"><div className="flex h-20 items-center gap-2 border-y border-line px-3 text-[10px] text-muted"><Film size={13} />主画面</div><div className="flex h-12 items-center gap-2 border-b border-line px-3 text-[10px] text-muted"><AudioLines size={13} />声音</div></div><div className="min-w-0 overflow-x-auto"><div className="relative h-7 min-w-[720px] border-b border-line bg-white">{Array.from({ length: 9 }, (_, index) => <span key={index} className="absolute top-1 text-[9px] text-muted" style={{ left: `${index * 12.5}%` }}>{formatTime(model.durationMs * index / 8).slice(0, 5)}</span>)}</div><div className="relative flex h-20 min-w-[720px] items-center gap-1 border-b border-line px-1">{mainTrack?.items.map((item, index) => <button key={item.id} type="button" onClick={() => { setPlaying(false); seek(item.startMs); }} className={`group relative h-14 min-w-[70px] overflow-hidden rounded-md border px-2 text-left ${item.shotId === selectedShot?.id ? "border-blue bg-blue text-white" : item.assetId ? "border-teal/40 bg-teal/10 text-text" : "border-dashed border-line bg-white text-muted"}`} style={{ width: `${Math.max(8, item.durationMs / model.durationMs * 100)}%` }}><span className="block truncate text-[10px] font-semibold">镜头 {index + 1}</span><span className="mt-1 block text-[9px] opacity-70">{(item.durationMs / 1000).toFixed(1)}s</span>{item.shotId && model.shots.find((shot) => shot.id === item.shotId)?.shot.transition.type && <span className="absolute bottom-0 right-0 rounded-tl bg-black/15 px-1 text-[8px]">转场</span>}</button>)}<div className="pointer-events-none absolute inset-y-0 w-px bg-red shadow-[0_0_0_1px_rgba(255,255,255,.6)]" style={{ left: `${playheadMs / model.durationMs * 100}%` }} /></div><div className="flex h-12 min-w-[720px] items-center gap-2 border-b border-line px-2 text-[10px] text-muted">{audioMix.voiceAssetId && <span className="rounded bg-blue-soft px-1.5 py-0.5 text-blue">旁白</span>}{(selectedShot?.audioSettings.backgroundMusic?.assetId || activeGlobalScope.backgroundMusic?.assetId || audioMix.musicAssetId) && <span className="rounded bg-teal/10 px-1.5 py-0.5 text-teal">背景音乐</span>}<span>{audioAssets.length ? `${audioAssets.length} 个声音素材 · 支持全片、场景、镜头三级混音` : "尚未添加声音素材"}</span></div></div></div></section>
  </div>;
}
