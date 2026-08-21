import type { Asset } from "@/api/assets";
import type { CreationPreview } from "@/api/generate";
import type { Scene, Shot, Workspace } from "@/api/projects";
import { synchronizeTimeline } from "@/stores/workspaceTransforms";

export interface CreationShot {
  description: string;
  durationMs: number;
  assetId?: string;
  segmentId?: string;
  sourceStartMs?: number;
  sourceEndMs?: number;
}

export interface CreationUnit {
  title: string;
  narration: string;
  visual: string;
  durationMs: number;
  shots: CreationShot[];
}

const visualPrefix = /^(?:画面|分镜|镜头|视觉|visual|shot)\s*[:：]\s*(.+)$/i;
const narrationPrefix = /^(?:台词|旁白|文案|字幕|voiceover|vo)\s*[:：]\s*(.+)$/i;
const headingPrefix = /^(?:第?[一二三四五六七八九十百\d]+[章节场幕段、.．)）:-]|场景\s*[一二三四五六七八九十百\d]*\s*[:：-]?)\s*/i;

function cleanLine(value: string) {
  return value.replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
}

function clampDuration(ms: number) {
  return Math.max(3_000, Math.min(15_000, ms || 8_000));
}

function defaultVisual(narration: string) {
  const excerpt = narration.slice(0, 28);
  return `围绕“${excerpt}${narration.length > 28 ? "…" : ""}”建立主体、动作与场景，使用自然的景别变化推进叙事。`;
}

export function recognizePastedScript(rawText: string): CreationUnit[] {
  const units: CreationUnit[] = [];
  let pendingTitle = "";

  for (const rawLine of rawText.replace(/\r/g, "").split("\n")) {
    const line = cleanLine(rawLine);
    if (!line) continue;

    const visualMatch = line.match(visualPrefix);
    if (visualMatch) {
      if (!units.length) {
        units.push({
          title: pendingTitle || "开场",
          narration: "待补充旁白",
          visual: visualMatch[1],
          durationMs: 8_000,
          shots: [{ description: visualMatch[1], durationMs: 8_000 }],
        });
      } else {
        const current = units.at(-1)!;
        if (current.visual.startsWith("围绕“")) current.visual = visualMatch[1];
        else current.visual += `；${visualMatch[1]}`;
        current.shots[0].description = current.visual;
      }
      continue;
    }

    const narrationMatch = line.match(narrationPrefix);
    const headingMatch = line.match(headingPrefix);
    const stripped = cleanLine((narrationMatch?.[1] ?? line).replace(headingPrefix, ""));
    if (!stripped) {
      pendingTitle = line.replace(headingPrefix, "").trim();
      continue;
    }

    if (headingMatch && stripped.length < 28 && !/[。！？!?；;]/.test(stripped)) {
      pendingTitle = stripped;
      continue;
    }
    const lineTitle = headingMatch ? stripped.slice(0, 18) : "";
    const sentences = stripped.match(/[^。！？!?；;]+[。！？!?；;]?/g)?.map(cleanLine).filter(Boolean) ?? [stripped];
    let current = "";
    for (const sentence of sentences) {
      if (current && current.length + sentence.length > 78) {
        units.push({
          title: pendingTitle || lineTitle || `段落 ${units.length + 1}`,
          narration: current,
          visual: defaultVisual(current),
          durationMs: clampDuration(Math.round(current.length / 4.5) * 1_000),
          shots: [],
        });
        units.at(-1)!.shots = [{ description: units.at(-1)!.visual, durationMs: units.at(-1)!.durationMs }];
        current = sentence;
        pendingTitle = "";
      } else {
        current += sentence;
      }
    }
    if (current) {
      units.push({
        title: pendingTitle || lineTitle || `段落 ${units.length + 1}`,
        narration: current,
        visual: defaultVisual(current),
        durationMs: clampDuration(Math.round(current.length / 4.5) * 1_000),
        shots: [],
      });
      units.at(-1)!.shots = [{ description: units.at(-1)!.visual, durationMs: units.at(-1)!.durationMs }];
      pendingTitle = "";
    }
  }

  return units.slice(0, 30).map((unit, index) => ({ ...unit, title: unit.title || `段落 ${index + 1}` }));
}

export function creationPreviewToUnits(preview: CreationPreview): CreationUnit[] {
  return preview.scenes.map((scene) => ({
    title: scene.title,
    narration: scene.narration,
    visual: scene.visual,
    durationMs: scene.durationMs,
    shots: scene.shots.map((shot) => ({ ...shot })),
  }));
}

function shotFromUnit(
  unit: CreationUnit,
  creationShot: CreationShot,
  sceneIndex: number,
  shotIndex: number,
  assetsById: Map<string, Asset>,
): Shot {
  const referencedAsset = creationShot.assetId ? assetsById.get(creationShot.assetId) : undefined;
  const visualAsset = referencedAsset?.mediaType === "audio" ? undefined : referencedAsset;
  const segment = visualAsset?.segments.find((item) => item.id === creationShot.segmentId);
  const durationMs = Math.max(500, creationShot.durationMs || 5_000);
  const sourceStartMs = creationShot.sourceStartMs ?? segment?.startMs ?? 0;
  const sourceEndMs = creationShot.sourceEndMs ?? segment?.endMs ?? sourceStartMs + durationMs;
  return {
    index: shotIndex,
    description: creationShot.description || unit.visual,
    status: visualAsset ? "matched" : "editing",
    visualMode: visualAsset?.mediaType,
    assetId: visualAsset?.id,
    segmentId: visualAsset ? creationShot.segmentId : undefined,
    sourceStartMs,
    sourceEndMs,
    durationMs,
    locked: false,
    transform: {},
    adjust: {},
    audioSettings: {},
    subtitleSettings: {},
    transition: sceneIndex || shotIndex ? { type: "cut", durationMs: 0 } : {},
    motion: {},
    subtitleText: unit.narration,
    subtitleOverridden: false,
    subtitleSourceRevision: 0,
    subtitleOutdated: false,
    notes: visualAsset ? "由素材 AI 分析编排生成，可继续修改镜头与旁白。" : "由创建向导生成，可继续编辑。",
    revision: 0,
    candidates: segment && visualAsset ? [{
      id: `candidate-${sceneIndex}-${shotIndex}`,
      segmentId: segment.id,
      title: segment.title || visualAsset.name,
      source: visualAsset.name,
      rangeStartMs: sourceStartMs,
      rangeEndMs: sourceEndMs,
      score: Math.max(0, Math.min(100, Math.round(segment.qualityScore || 0))),
      reason: "来自本次选中的素材，已完成内容理解与叙事排序。",
      lowConfidence: false,
    }] : [],
    mediaVersions: [],
  };
}

export function applyCreationUnits(
  workspace: Workspace,
  units: CreationUnit[],
  sourceType: "script" | "ai" | "asset-analysis",
  summary: string,
): Workspace {
  const assetsById = new Map(workspace.linkedAssets.map((asset) => [asset.id, asset]));
  const scenes: Scene[] = units.map((unit, index) => ({
    index,
    outline: unit.title,
    narrationText: unit.narration,
    intent: unit.visual,
    status: unit.shots.some((shot) => shot.assetId) ? "matched" : "editing",
    estimatedDurationMs: Math.max(100, unit.durationMs),
    notes: "",
    revision: 0,
    shots: unit.shots.map((shot, shotIndex) => shotFromUnit(unit, shot, index, shotIndex, assetsById)),
  }));
  const estimatedDurationSeconds = Math.round(scenes.reduce((sum, scene) => sum + scene.estimatedDurationMs, 0) / 1_000);
  return {
    ...workspace,
    document: synchronizeTimeline({
      ...workspace.document,
      settings: {
        ...workspace.document.settings,
        summary,
        sourceType,
        targetDurationSeconds: workspace.document.settings.targetDurationSeconds || estimatedDurationSeconds,
        estimatedDurationSeconds,
      },
      storyboard: { scenes },
    }),
  };
}
