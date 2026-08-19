import type { CSSProperties } from "react";
import type { Asset } from "@/api/assets";
import type { Scene, Shot, TimelineItem, Workspace } from "@/api/projects";

export interface CompositionShot {
  id: string;
  scene: Scene;
  shot: Shot;
  item: TimelineItem;
  asset?: Asset;
  mediaUrl?: string;
  thumbnailUrl?: string;
  startMs: number;
  endMs: number;
  durationMs: number;
  sourceStartMs: number;
  sourceEndMs: number;
}

export interface CompositionModel {
  shots: CompositionShot[];
  durationMs: number;
}

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as UnknownRecord
    : {};
}

export function numeric(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function buildCompositionModel(workspace: Workspace): CompositionModel {
  const assets = new Map(workspace.linkedAssets.map((asset) => [asset.id, asset]));
  const scenesById = new Map(
    workspace.document.storyboard.scenes
      .filter((scene): scene is Scene & { id: string } => Boolean(scene.id))
      .map((scene) => [scene.id, scene]),
  );
  const shotsById = new Map<string, { scene: Scene; shot: Shot }>();
  workspace.document.storyboard.scenes.forEach((scene) => {
    scene.shots.forEach((shot) => {
      if (shot.id) shotsById.set(shot.id, { scene, shot });
    });
  });
  const mainTrack = workspace.document.timeline.tracks.find((track) => (
    track.id === "main-video" || track.role === "story"
  ));
  const items = [...(mainTrack?.items ?? [])].sort((left, right) => left.startMs - right.startMs);
  const shots = items.flatMap((item): CompositionShot[] => {
    const resolved = item.shotId ? shotsById.get(item.shotId) : undefined;
    const scene = resolved?.scene ?? (item.sceneId ? scenesById.get(item.sceneId) : undefined);
    const shot = resolved?.shot ?? scene?.shots.find((candidate) => candidate.id === item.shotId);
    if (!scene || !shot || !shot.id) return [];
    const selectedVersion = shot.mediaVersions.find((version) => version.id === shot.selectedMediaVersionId)
      ?? shot.mediaVersions.find((version) => version.isSelected);
    const assetId = selectedVersion?.assetId ?? item.assetId ?? shot.assetId;
    const asset = assetId ? assets.get(assetId) : undefined;
    const durationMs = Math.max(100, item.durationMs || shot.durationMs || 8000);
    const sourceStartMs = Math.max(0, item.sourceStartMs ?? shot.sourceStartMs ?? 0);
    const sourceEndMs = Math.max(
      sourceStartMs + 100,
      item.sourceEndMs || shot.sourceEndMs || sourceStartMs + durationMs,
    );
    return [{
      id: shot.id,
      scene,
      shot,
      item,
      asset,
      mediaUrl: selectedVersion?.mediaUrl ?? asset?.mediaUrl,
      thumbnailUrl: asset?.thumbnailUrl,
      startMs: Math.max(0, item.startMs),
      endMs: Math.max(0, item.startMs) + durationMs,
      durationMs,
      sourceStartMs,
      sourceEndMs,
    }];
  });
  return {
    shots,
    durationMs: Math.max(
      workspace.document.timeline.durationMs,
      ...shots.map((shot) => shot.endMs),
      1000,
    ),
  };
}

export function compositionShotAt(model: CompositionModel, playheadMs: number): CompositionShot | undefined {
  if (!model.shots.length) return undefined;
  const time = clamp(playheadMs, 0, model.durationMs);
  return model.shots.find((shot) => time >= shot.startMs && time < shot.endMs)
    ?? (time >= model.shots.at(-1)!.endMs ? model.shots.at(-1) : model.shots[0]);
}

export function nextCompositionShot(model: CompositionModel, current?: CompositionShot): CompositionShot | undefined {
  if (!current) return undefined;
  const index = model.shots.findIndex((shot) => shot.id === current.id);
  return index >= 0 ? model.shots[index + 1] : undefined;
}

export function transitionState(
  current: CompositionShot | undefined,
  next: CompositionShot | undefined,
  playheadMs: number,
): { type: string; progress: number; active: boolean; durationMs: number } {
  const transition = record(current?.shot.transition);
  const type = String(transition.type ?? transition.preset ?? "cut");
  const durationMs = clamp(numeric(transition.durationMs ?? transition.duration_ms, 500), 100, 3000);
  if (!current || !next || type === "cut" || type === "none") {
    return { type: "cut", progress: 0, active: false, durationMs };
  }
  const progress = clamp((playheadMs - (current.endMs - durationMs)) / durationMs, 0, 1);
  return { type, progress, active: progress > 0, durationMs };
}

export function transitionLayerStyle(
  type: string,
  progress: number,
  layer: "current" | "next",
): CSSProperties {
  const value = clamp(progress, 0, 1);
  if (type === "fade" || type === "dissolve") {
    return { opacity: layer === "current" ? 1 - value : value };
  }
  if (type === "slide-left") {
    return { transform: `translateX(${layer === "current" ? -value * 100 : (1 - value) * 100}%)` };
  }
  if (type === "slide-right") {
    return { transform: `translateX(${layer === "current" ? value * 100 : -(1 - value) * 100}%)` };
  }
  if (type === "zoom") {
    return layer === "current"
      ? { opacity: 1 - value, transform: `scale(${1 + value * 0.08})` }
      : { opacity: value, transform: `scale(${1.08 - value * 0.08})` };
  }
  return layer === "next" ? { opacity: value } : {};
}

export function shotVisualStyle(shot: Shot, localProgress: number): CSSProperties {
  const adjust = record(shot.adjust);
  const transform = record(shot.transform);
  const motion = record(shot.motion);
  const preset = String(adjust.filterPreset ?? adjust.filter ?? "original");
  const presetFilters: Record<string, string> = {
    original: "",
    cinematic: "contrast(1.12) saturate(0.9) sepia(0.08)",
    vivid: "contrast(1.08) saturate(1.3)",
    warm: "sepia(0.16) saturate(1.08)",
    cool: "hue-rotate(175deg) saturate(0.88)",
    monochrome: "grayscale(1) contrast(1.08)",
    vintage: "sepia(0.32) saturate(0.82) contrast(0.94)",
    cyber: "contrast(1.18) saturate(1.38) hue-rotate(12deg)",
  };
  const brightness = clamp(100 + numeric(adjust.brightness), 0, 200);
  const contrast = clamp(100 + numeric(adjust.contrast), 0, 200);
  const saturation = clamp(100 + numeric(adjust.saturation), 0, 250);
  const hue = clamp(numeric(adjust.hue), -180, 180);
  const temperature = clamp(numeric(adjust.temperature), -100, 100);
  const sepia = clamp(numeric(adjust.sepia), 0, 100);
  const grayscale = clamp(numeric(adjust.grayscale), 0, 100);
  const opacity = clamp(100 - numeric(adjust.fade), 10, 100) / 100;
  const progress = clamp(localProgress, 0, 1);
  const strength = clamp(numeric(motion.strength, 40), 0, 100) / 100;
  const motionType = String(motion.type ?? "none");
  let motionScale = 1;
  let motionX = 0;
  let motionY = 0;
  if (motionType === "push") motionScale += progress * 0.12 * strength;
  if (motionType === "pull") motionScale += (1 - progress) * 0.12 * strength;
  if (motionType === "pan-left") motionX = (0.5 - progress) * 10 * strength;
  if (motionType === "pan-right") motionX = (progress - 0.5) * 10 * strength;
  if (motionType === "tilt-up") motionY = (0.5 - progress) * 10 * strength;
  if (motionType === "tilt-down") motionY = (progress - 0.5) * 10 * strength;
  if (motionType === "handheld") {
    motionX = Math.sin(progress * Math.PI * 24) * 1.4 * strength;
    motionY = Math.cos(progress * Math.PI * 19) * 1.0 * strength;
  }
  const scale = Math.max(0.1, numeric(transform.scale, 100) / 100) * motionScale;
  const x = numeric(transform.x ?? transform.positionX) + motionX;
  const y = numeric(transform.y ?? transform.positionY) + motionY;
  const rotate = numeric(transform.rotate) + (motionType === "handheld" ? Math.sin(progress * Math.PI * 17) * 0.5 * strength : 0);
  const temperatureFilter = temperature > 0
    ? `sepia(${temperature * 0.22}%) saturate(${100 + temperature * 0.18}%)`
    : temperature < 0 ? `hue-rotate(${temperature * 0.18}deg) saturate(${100 + Math.abs(temperature) * 0.08}%)` : "";
  const presetFilter = presetFilters[preset] ?? "";
  return {
    filter: [
      presetFilter,
      `brightness(${brightness}%)`,
      `contrast(${contrast}%)`,
      `saturate(${saturation}%)`,
      `hue-rotate(${hue}deg)`,
      temperatureFilter,
      `sepia(${sepia}%)`,
      `grayscale(${grayscale}%)`,
    ].filter(Boolean).join(" "),
    opacity,
    objectFit: String(transform.fitMode ?? "cover") === "contain" ? "contain" : "cover",
    transform: `translate(${x}%, ${y}%) rotate(${rotate}deg) scale(${scale})`,
  };
}

export function subtitleStyle(shot: Shot): CSSProperties {
  const settings = record(shot.subtitleSettings);
  const position = String(settings.position ?? "bottom");
  return {
    top: position === "top" ? "10%" : position === "center" ? "50%" : undefined,
    bottom: position === "bottom" ? "10%" : undefined,
    transform: position === "center" ? "translateY(-50%)" : undefined,
    color: String(settings.color ?? "#ffffff"),
    fontSize: `${clamp(numeric(settings.fontSize, 16), 10, 48)}px`,
    textAlign: String(settings.align ?? "center") as CSSProperties["textAlign"],
  };
}
