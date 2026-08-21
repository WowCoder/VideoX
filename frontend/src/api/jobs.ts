// ──────────────────────────────────────────────
// OpenVMA - 异步任务 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";
import type { Job, JobStatus, PaginatedResponse } from "@/types/models";
import { mapJob, type RawJob } from "./jobMapper";

export { mapJob } from "./jobMapper";
export type { RawJob } from "./jobMapper";

export interface JobListParams {
  projectId?: string;
  status?: JobStatus;
  type?: string;
  page?: number;
  pageSize?: number;
}

interface RawJobList {
  items: RawJob[];
  total: number;
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

/** 删除非运行中的任务记录；不会删除任务已经生成的素材。 */
export async function remove(id: string): Promise<void> {
  return http.delete<void>(`/jobs/${id}`);
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
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
