import type { Job, JobStatus, JobType } from "@/types/models";

export interface RawJob {
  id: string;
  project_id: string | null;
  subject_type: string | null;
  subject_id: string | null;
  name: string;
  type: string;
  status: string;
  stage: string;
  stages: string[];
  stage_index: number;
  progress: number;
  detail: string;
  eta: string;
  logs: string[];
  result: string | null;
  result_detail: string;
  result_url: string | null;
  export_metadata: {
    format: string;
    resolution: string;
    aspect_ratio: string;
  } | null;
  is_simulated: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export function mapJob(raw: RawJob): Job {
  return {
    id: raw.id,
    projectId: raw.project_id ?? undefined,
    subjectType: raw.subject_type ?? undefined,
    subjectId: raw.subject_id ?? undefined,
    name: raw.name,
    type: raw.type as JobType,
    status: raw.status as JobStatus,
    stage: raw.stage,
    stages: raw.stages ?? [],
    stageIndex: raw.stage_index ?? 0,
    progress: raw.progress ?? 0,
    detail: raw.detail,
    eta: raw.eta,
    logs: (raw.logs ?? []).map((message) => ({ message, timestamp: "", level: "info" as const })),
    result: raw.result ?? undefined,
    resultDetail: raw.result_detail,
    resultUrl: raw.result_url ?? undefined,
    exportMetadata: raw.export_metadata ? {
      format: raw.export_metadata.format,
      resolution: raw.export_metadata.resolution,
      aspectRatio: raw.export_metadata.aspect_ratio,
    } : undefined,
    isSimulated: raw.is_simulated,
    createdAt: raw.created_at ?? "",
    updatedAt: raw.updated_at ?? raw.created_at ?? "",
  };
}
