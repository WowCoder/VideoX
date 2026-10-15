import type { AspectRatio } from "@/api/projects";
import type { CreationUnit } from "@/lib/projectCreationFlow";
import type { ProjectStartMethod } from "@/stores/uiStore";

export type WorkspaceCreationSource = Exclude<ProjectStartMethod, "blank">;
export type WorkspaceCreationStage = "input" | "script" | "settings";
export type WorkspaceProductionMode = "ai" | "hybrid" | "owned";

export interface WorkspaceCreationDraft {
  version: 1;
  source: WorkspaceCreationSource;
  stage: WorkspaceCreationStage;
  prompt: string;
  pastedScript: string;
  durationSeconds: number;
  tone: string;
  previewTitle: string;
  previewSummary: string;
  projectName: string;
  units: CreationUnit[];
  selectedAssetIds: string[];
  productionMode: WorkspaceProductionMode;
  aspectRatio: AspectRatio;
  visualStyle: string;
  narrationMode: string;
  aiCoverage: string;
  materialPriority: string;
  ownedArrangement: string;
  gapStrategy: string;
  manuallyEdited: boolean;
  updatedAt: string;
}

export const WORKSPACE_CREATION_DRAFT_KEY = "videox:workspace-creation-draft:v1";

const SOURCES = new Set<WorkspaceCreationSource>(["ai-script", "write-script", "upload-assets"]);
const STAGES = new Set<WorkspaceCreationStage>(["input", "script", "settings"]);
const PRODUCTION_MODES = new Set<WorkspaceProductionMode>(["ai", "hybrid", "owned"]);
const ASPECT_RATIOS = new Set<AspectRatio>(["16:9", "9:16", "1:1", "4:3"]);

export function createWorkspaceCreationDraft(
  source: WorkspaceCreationSource = "ai-script",
  now = new Date(),
): WorkspaceCreationDraft {
  return {
    version: 1,
    source,
    stage: "input",
    prompt: "",
    pastedScript: "",
    durationSeconds: 60,
    tone: "专业克制",
    previewTitle: "",
    previewSummary: "",
    projectName: "",
    units: [],
    selectedAssetIds: [],
    productionMode: source === "upload-assets" ? "hybrid" : "ai",
    aspectRatio: "16:9",
    visualStyle: "品牌商业",
    narrationMode: "AI 自然旁白",
    aiCoverage: "均衡补充",
    materialPriority: "自有素材优先",
    ownedArrangement: "按脚本匹配",
    gapStrategy: "保留缺口待补",
    manuallyEdited: false,
    updatedAt: now.toISOString(),
  };
}

function isCreationUnit(value: unknown): value is CreationUnit {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const unit = value as Partial<CreationUnit>;
  return typeof unit.title === "string"
    && typeof unit.narration === "string"
    && typeof unit.visual === "string"
    && typeof unit.durationMs === "number"
    && Array.isArray(unit.shots);
}

export function parseWorkspaceCreationDraft(value: unknown): WorkspaceCreationDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<WorkspaceCreationDraft>;
  if (candidate.version !== 1 || !candidate.source || !SOURCES.has(candidate.source)) return null;

  const fallback = createWorkspaceCreationDraft(candidate.source);
  return {
    ...fallback,
    ...candidate,
    version: 1,
    source: candidate.source,
    stage: candidate.stage && STAGES.has(candidate.stage) ? candidate.stage : "input",
    productionMode: candidate.productionMode && PRODUCTION_MODES.has(candidate.productionMode)
      ? candidate.productionMode
      : fallback.productionMode,
    aspectRatio: candidate.aspectRatio && ASPECT_RATIOS.has(candidate.aspectRatio)
      ? candidate.aspectRatio
      : fallback.aspectRatio,
    prompt: typeof candidate.prompt === "string" ? candidate.prompt : "",
    pastedScript: typeof candidate.pastedScript === "string" ? candidate.pastedScript : "",
    durationSeconds: typeof candidate.durationSeconds === "number"
      ? Math.max(15, Math.min(600, Math.round(candidate.durationSeconds)))
      : fallback.durationSeconds,
    tone: typeof candidate.tone === "string" ? candidate.tone : fallback.tone,
    previewTitle: typeof candidate.previewTitle === "string" ? candidate.previewTitle : "",
    previewSummary: typeof candidate.previewSummary === "string" ? candidate.previewSummary : "",
    projectName: typeof candidate.projectName === "string" ? candidate.projectName : "",
    units: Array.isArray(candidate.units) ? candidate.units.filter(isCreationUnit).slice(0, 60) : [],
    selectedAssetIds: Array.isArray(candidate.selectedAssetIds)
      ? candidate.selectedAssetIds.filter((id): id is string => typeof id === "string").slice(0, 50)
      : [],
    manuallyEdited: Boolean(candidate.manuallyEdited),
    updatedAt: typeof candidate.updatedAt === "string" ? candidate.updatedAt : fallback.updatedAt,
  };
}

export function loadWorkspaceCreationDraft(storage: Storage = window.localStorage): WorkspaceCreationDraft | null {
  try {
    const raw = storage.getItem(WORKSPACE_CREATION_DRAFT_KEY);
    if (!raw) return null;
    return parseWorkspaceCreationDraft(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveWorkspaceCreationDraft(
  draft: WorkspaceCreationDraft,
  storage: Storage = window.localStorage,
): WorkspaceCreationDraft {
  const saved = { ...draft, updatedAt: new Date().toISOString() };
  try {
    storage.setItem(WORKSPACE_CREATION_DRAFT_KEY, JSON.stringify(saved));
  } catch {
    // The creation flow remains usable when browser storage is unavailable.
  }
  return saved;
}

export function clearWorkspaceCreationDraft(storage: Storage = window.localStorage): void {
  try {
    storage.removeItem(WORKSPACE_CREATION_DRAFT_KEY);
  } catch {
    // Ignore storage failures; clearing a draft is a convenience, not a blocker.
  }
}

export function deriveWorkspaceCreationTitle(units: CreationUnit[], fallback = "未命名影片"): string {
  const first = units[0];
  if (!first) return fallback;
  const explicitTitle = first.title.trim();
  if (explicitTitle && !/^段落\s*\d+$/u.test(explicitTitle)) return explicitTitle.slice(0, 80);
  const narration = first.narration.trim().replace(/^[\d\s.,，。:：、)）-]+/u, "");
  const sentence = narration.split(/[。！？!?\n]/u)[0]?.trim();
  return (sentence || fallback).slice(0, 80);
}

export function hasWorkspaceCreationContent(draft: WorkspaceCreationDraft): boolean {
  return Boolean(
    draft.prompt.trim()
    || draft.pastedScript.trim()
    || draft.units.length
    || draft.selectedAssetIds.length,
  );
}
