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
  pricingCatalogId?: string;
}

export interface OperationEstimate {
  estimateId?: string;
  catalogVersionId?: string;
  estimatedCredits: number;
  availableCredits: number;
  remainingAfter: number;
  sufficient: boolean;
  expiresAt?: string;
  lines: Array<{
    sku: string;
    unit: string;
    quantity: number;
    unitCredits: number;
    credits: number;
  }>;
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
  pricingCatalogId?: string;
}): Promise<CreationPreview> {
  const raw = await http.post<RawCreationPreview>("/generate/creation-previews/script", {
    prompt: input.prompt,
    duration_seconds: input.durationSeconds,
    tone: input.tone,
    pricing_catalog_id: input.pricingCatalogId ?? null,
  });
  return mapCreationPreview(raw);
}

export async function createAssetPreview(input: {
  assetIds: string[];
  brief?: string;
  pricingCatalogId?: string;
}): Promise<CreationPreview> {
  const raw = await http.post<RawCreationPreview>("/generate/creation-previews/assets", {
    asset_ids: input.assetIds,
    brief: input.brief ?? "",
    pricing_catalog_id: input.pricingCatalogId ?? null,
  });
  return mapCreationPreview(raw);
}

export async function estimateCreationPreview(source: "ai-script" | "upload-assets"): Promise<OperationEstimate> {
  const raw = await http.post<{
    estimate_id?: string | null; catalog_version_id?: string | null; estimated_credits: number;
    available_credits: number; remaining_after: number; sufficient: boolean; expires_at?: string | null;
    lines: Array<{ sku: string; unit: string; quantity: number; unit_credits: number; credits: number }>;
  }>("/generate/creation-previews/estimate", { source });
  return {
    estimateId: raw.estimate_id ?? undefined,
    catalogVersionId: raw.catalog_version_id ?? undefined,
    estimatedCredits: raw.estimated_credits,
    availableCredits: raw.available_credits,
    remainingAfter: raw.remaining_after,
    sufficient: raw.sufficient,
    expiresAt: raw.expires_at ?? undefined,
    lines: raw.lines.map((line) => ({ sku: line.sku, unit: line.unit, quantity: line.quantity, unitCredits: line.unit_credits, credits: line.credits })),
  };
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
    pricing_catalog_id: request.pricingCatalogId ?? null,
  });
  return raw.jobs.map(mapJob);
}

export async function estimateProjectOperation(
  projectId: string,
  request: ProjectOperationRequest,
): Promise<OperationEstimate> {
  const raw = await http.post<{
    estimate_id?: string | null;
    catalog_version_id?: string | null;
    estimated_credits: number;
    available_credits: number;
    remaining_after: number;
    sufficient: boolean;
    expires_at?: string | null;
    lines: Array<{ sku: string; unit: string; quantity: number; unit_credits: number; credits: number }>;
  }>(`/generate/projects/${projectId}/operations/estimate`, {
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
  return {
    estimateId: raw.estimate_id ?? undefined,
    catalogVersionId: raw.catalog_version_id ?? undefined,
    estimatedCredits: raw.estimated_credits,
    availableCredits: raw.available_credits,
    remainingAfter: raw.remaining_after,
    sufficient: raw.sufficient,
    expiresAt: raw.expires_at ?? undefined,
    lines: raw.lines.map((line) => ({
      sku: line.sku,
      unit: line.unit,
      quantity: line.quantity,
      unitCredits: line.unit_credits,
      credits: line.credits,
    })),
  };
}
