import { http } from "./client";
import type { Job } from "@/types/models";
import { mapJob, type RawJob } from "./jobs";

export type ProjectOperation =
  | "match_assets"
  | "complete_shots"
  | "generate_image"
  | "generate_video"
  | "generate_effect"
  | "generate_script"
  | "generate_voiceover"
  | "compose"
  | "export";

export interface OperationScope {
  type: "project" | "scene" | "shot" | "asset";
  sceneIds?: string[];
  shotIds?: string[];
  assetIds?: string[];
}

export interface ProjectOperationRequest {
  scope: OperationScope;
  operation: ProjectOperation;
  parameters?: Record<string, unknown>;
  expectedRevision: number;
}

export interface CreationPreviewShot {
  description: string;
  durationMs: number;
  assetId?: string;
  segmentId?: string;
  sourceStartMs: number;
  sourceEndMs: number;
}

export interface CreationPreviewScene {
  title: string;
  narration: string;
  visual: string;
  durationMs: number;
  shots: CreationPreviewShot[];
}

export interface CreationPreview {
  title: string;
  summary: string;
  scenes: CreationPreviewScene[];
}

interface RawCreationPreview {
  title: string;
  summary: string;
  scenes: Array<{
    title: string;
    narration: string;
    visual: string;
    duration_ms: number;
    shots: Array<{
      description: string;
      duration_ms: number;
      asset_id: string | null;
      segment_id: string | null;
      source_start_ms: number;
      source_end_ms: number;
    }>;
  }>;
}

function mapCreationPreview(raw: RawCreationPreview): CreationPreview {
  return {
    title: raw.title,
    summary: raw.summary,
    scenes: raw.scenes.map((scene) => ({
      title: scene.title,
      narration: scene.narration,
      visual: scene.visual,
      durationMs: scene.duration_ms,
      shots: scene.shots.map((shot) => ({
        description: shot.description,
        durationMs: shot.duration_ms,
        assetId: shot.asset_id ?? undefined,
        segmentId: shot.segment_id ?? undefined,
        sourceStartMs: shot.source_start_ms,
        sourceEndMs: shot.source_end_ms,
      })),
    })),
  };
}

export async function createScriptPreview(input: {
  prompt: string;
  durationSeconds: number;
  tone: string;
}): Promise<CreationPreview> {
  const raw = await http.post<RawCreationPreview>("/generate/creation-previews/script", {
    prompt: input.prompt,
    duration_seconds: input.durationSeconds,
    tone: input.tone,
  });
  return mapCreationPreview(raw);
}

export async function createAssetPreview(input: {
  assetIds: string[];
  brief?: string;
}): Promise<CreationPreview> {
  const raw = await http.post<RawCreationPreview>("/generate/creation-previews/assets", {
    asset_ids: input.assetIds,
    brief: input.brief ?? "",
  });
  return mapCreationPreview(raw);
}

export async function executeProjectOperation(
  projectId: string,
  request: ProjectOperationRequest,
): Promise<Job[]> {
  const raw = await http.post<{ jobs: RawJob[] }>(`/generate/projects/${projectId}/operations`, {
    scope: {
      type: request.scope.type,
      scene_ids: request.scope.sceneIds ?? [],
      shot_ids: request.scope.shotIds ?? [],
      asset_ids: request.scope.assetIds ?? [],
    },
    operation: request.operation,
    parameters: request.parameters ?? {},
    expected_revision: request.expectedRevision,
  });
  return raw.jobs.map(mapJob);
}
