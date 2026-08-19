// ──────────────────────────────────────────────
// OpenVMA - 异步任务 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";
import type { Job, JobStatus, JobType, PaginatedResponse } from "@/types/models";

export interface JobListParams {
  projectId?: string;
  status?: JobStatus;
  type?: string;
  page?: number;
  pageSize?: number;
}

/* ── 后端原始类型（snake_case）── */

export interface RawJob {
  id: string;
  project_id: string | null;
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

interface RawJobList {
  items: RawJob[];
  total: number;
}

/* ── 映射函数 ── */

export function mapJob(raw: RawJob): Job {
  return {
    id: raw.id,
    projectId: raw.project_id ?? undefined,
    name: raw.name,
    type: raw.type as JobType,
    status: raw.status as JobStatus,
    stage: raw.stage,
    stages: raw.stages ?? [],
    stageIndex: raw.stage_index ?? 0,
    progress: raw.progress ?? 0,
    detail: raw.detail,
    eta: raw.eta,
    logs: (raw.logs ?? []).map((msg) => ({
      message: msg,
      timestamp: "",
      level: "info" as const,
    })),
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
  };
}

/* ── API 方法 ── */

/**
 * 获取任务列表
 * GET /api/jobs
 */
export async function list(params?: JobListParams): Promise<PaginatedResponse<Job>> {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.status) query.set("status", params.status);
  if (params?.type) query.set("type", params.type);
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const qs = query.toString();
  const raw = await http.get<RawJobList>(`/jobs${qs ? `?${qs}` : ""}`);
  return {
    items: raw.items.map(mapJob),
    total: raw.total,
  };
}

/**
 * 获取任务详情
 * GET /api/jobs/:id
 */
export async function get(id: string): Promise<Job> {
  const raw = await http.get<RawJob>(`/jobs/${id}`);
  return mapJob(raw);
}

/**
 * 重试失败任务
 * POST /api/jobs/:id/retry
 */
export async function retry(id: string): Promise<Job> {
  const raw = await http.post<RawJob>(`/jobs/${id}/retry`);
  return mapJob(raw);
}

export async function cancel(id: string): Promise<Job> {
  const raw = await http.post<RawJob>(`/jobs/${id}/cancel`);
  return mapJob(raw);
}

/**
 * 暂停任务
 * POST /api/jobs/:id/pause
 */
export async function pause(id: string): Promise<Job> {
  const raw = await http.post<RawJob>(`/jobs/${id}/pause`);
  return mapJob(raw);
}

/**
 * 恢复任务
 * POST /api/jobs/:id/resume
 */
export async function resume(id: string): Promise<Job> {
  const raw = await http.post<RawJob>(`/jobs/${id}/resume`);
  return mapJob(raw);
}

export async function downloadResult(id: string): Promise<void> {
  const { blob, filename } = await http.download(`/jobs/${id}/download`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename ?? `OpenVMA-${id}.mp4`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
