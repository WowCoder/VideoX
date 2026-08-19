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
