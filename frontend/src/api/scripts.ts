// ──────────────────────────────────────────────
// OpenVMA - 脚本 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";
import { mapDeleteImpact, type DeleteImpact, type RawDeleteImpact } from "./deletion";
import * as projectApi from "./projects";
import { formatRelativeTime } from "@/lib/utils";
import type {
  Script,
  ScriptUnit,
  Shot,
  Candidate,
  VisualConfig,
  Project,
  PaginatedResponse,
  ScriptStatus,
  ScriptFormat,
  ScriptSourceType,
  ScriptUnitStatus,
  ShotStatus,
  VisualMode,
  ThumbnailVariant,
  ShotGeneration,
} from "@/types/models";

export interface ScriptCreateInput {
  projectId: string;
  title: string;
  summary?: string;
  sourceType?: "blank" | "paste" | "spreadsheet" | "ai";
  units?: ScriptUnit[];
  format?: string;
}

export interface ScriptUpdateInput {
  title?: string;
  summary?: string;
  status?: string;
  visualConfig?: VisualConfig;
  format?: string;
}

export interface ScriptListParams {
  projectId?: string;
  search?: string;
  status?: string;
}

export interface ScriptParseInput {
  /** 粘贴文本模式 */
  text?: string;
  /** 上传表格模式 */
  file?: File;
}

export interface ScriptParseResult {
  units: ScriptUnit[];
  title?: string;
  summary?: string;
}

export interface RoughCutResult {
  project: Project;
  script: Script;
  jobId: string;
  versionId: string;
}

export interface LinkedCut {
  projectId: string;
  versionId: string;
  name: string;
  versionName: string;
  status: string;
  aspectRatio?: string;
  timelineVersion: number;
  currentUserRole: "owner" | "editor" | "viewer";
  updatedAt: string;
}

/* ── 后端原始类型（snake_case）── */

interface RawCandidate {
  id?: string;
  shot_id?: string | null;
  unit_id?: string | null;
  clip_id?: string | null;
  title?: string;
  source?: string;
  range_start?: string;
  range_end?: string;
  score?: number;
  reason?: string;
  variant?: string;
  low_confidence?: boolean;
  thumbnail_url?: string | null;
}

interface RawShotGeneration {
  id: string;
  shot_id: string;
  job_id?: string | null;
  kind: "image" | "video" | "effect";
  storage_path: string;
  media_url?: string | null;
  prompt: string;
  is_selected: boolean;
  created_at: string;
}

interface RawShot {
  id: string;
  unit_id: string;
  source_shot_id?: string | null;
  index: number;
  description: string;
  status: string;
  selected_clip_id: string | null;
  visual_mode: string | null;
  duration: number;
  notes: string;
  generated_image_path: string | null;
  generated_video_path: string | null;
  generated_effect_video_path: string | null;
  candidates: RawCandidate[];
  generations?: RawShotGeneration[];
}

interface RawScriptUnit {
  id: string;
  script_id: string;
  source_unit_id?: string | null;
  index: number;
  outline: string;
  text: string;
  intent: string;
  status: string;
  selected_clip_id: string | null;
  duration: number;
  notes: string;
  candidates: RawCandidate[];
  shots: RawShot[];
}

interface RawScript {
  id: string;
  project_id: string;
  title: string;
  summary: string;
  status: string;
  duration: string;
  unit_count: number;
  matched_count: number;
  progress: number;
  variant: string;
  format: string;
  visual_config: Record<string, unknown>;
  needs_initial_save: boolean;
  source_type: string;
  is_snapshot: boolean;
  parent_script_id: string | null;
  updated_at: string;
  units: RawScriptUnit[];
}

interface RawScriptList {
  items: RawScript[];
  total: number;
}

interface RawRoughCutResponse {
  project_id: string;
  script_id: string;
  job_id: string;
  version_id: string;
  message: string;
}

interface RawLinkedCut {
  project_id: string;
  version_id: string;
  name: string;
  version_name: string;
  status: string;
  aspect_ratio: string | null;
  timeline_version: number;
  current_user_role: "owner" | "editor" | "viewer";
  updated_at: string;
}

interface RawParseUnit {
  outline?: string;
  text?: string;
  intent?: string;
  duration?: number;
  notes?: string;
  status?: string;
  shots?: Array<{
    description?: string;
    duration?: number;
    notes?: string;
  }>;
}

/* ── 映射函数 ── */

function mapCandidate(raw: RawCandidate): Candidate {
  const score = raw.score ?? 0;
  return {
    id: raw.id ?? "",
    shotId: raw.shot_id ?? undefined,
    unitId: raw.unit_id ?? undefined,
    clipId: raw.clip_id ?? undefined,
    title: raw.title ?? "",
    source: raw.source ?? "",
    rangeStart: raw.range_start ? Number(raw.range_start) : undefined,
    rangeEnd: raw.range_end ? Number(raw.range_end) : undefined,
    // 后端持久化为 0-100 整数，界面组件内部统一使用 0-1。
    score: score > 1 ? score / 100 : score,
    reason: raw.reason ?? "",
    variant: (raw.variant ?? "stage") as ThumbnailVariant,
    lowConfidence: raw.low_confidence ?? false,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
    range: raw.range_start && raw.range_end ? `${raw.range_start}-${raw.range_end}` : undefined,
  };
}

function mapGeneration(raw: RawShotGeneration): ShotGeneration {
  return {
    id: raw.id,
    shotId: raw.shot_id,
    jobId: raw.job_id ?? undefined,
    kind: raw.kind,
    storagePath: raw.storage_path,
    mediaUrl: raw.media_url ?? undefined,
    prompt: raw.prompt ?? "",
    isSelected: raw.is_selected,
    createdAt: raw.created_at,
  };
}

function mapShot(raw: RawShot): Shot {
  return {
    id: raw.id,
    unitId: raw.unit_id,
    sourceShotId: raw.source_shot_id ?? undefined,
    index: raw.index,
    description: raw.description,
    status: raw.status as ShotStatus,
    selectedClipId: raw.selected_clip_id,
    visualMode: (raw.visual_mode as VisualMode) ?? null,
    duration: raw.duration,
    notes: raw.notes,
    generatedImagePath: raw.generated_image_path ?? undefined,
    generatedVideoPath: raw.generated_video_path ?? undefined,
    generatedEffectVideoPath: raw.generated_effect_video_path ?? undefined,
    generations: (raw.generations ?? []).map(mapGeneration),
    candidates: (raw.candidates ?? []).map(mapCandidate),
  };
}

function mapScriptUnit(raw: RawScriptUnit): ScriptUnit {
  return {
    id: raw.id,
    scriptId: raw.script_id,
    sourceUnitId: raw.source_unit_id ?? undefined,
    index: raw.index,
    outline: raw.outline,
    text: raw.text,
    intent: raw.intent,
    status: raw.status as ScriptUnitStatus,
    selectedClipId: raw.selected_clip_id,
    duration: raw.duration,
    notes: raw.notes,
    candidates: (raw.candidates ?? []).map(mapCandidate),
    shots: (raw.shots ?? []).map(mapShot),
  };
}

function mapScript(raw: RawScript): Script {
  return {
    id: raw.id,
    projectId: raw.project_id,
    title: raw.title,
    summary: raw.summary,
    status: raw.status as ScriptStatus,
    updatedAt: formatRelativeTime(raw.updated_at),
    duration: raw.duration,
    unitCount: raw.unit_count ?? 0,
    matchedCount: raw.matched_count ?? 0,
    progress: raw.progress ?? 0,
    variant: raw.variant as ThumbnailVariant,
    format: raw.format as ScriptFormat,
    visualConfig: raw.visual_config as unknown as VisualConfig,
    needsInitialSave: raw.needs_initial_save,
    sourceType: raw.source_type as ScriptSourceType,
    isSnapshot: raw.is_snapshot,
    parentScriptId: raw.parent_script_id ?? undefined,
    units: (raw.units ?? []).map(mapScriptUnit),
  };
}

function mapParseUnit(raw: RawParseUnit, index: number): ScriptUnit {
  return {
    id: `temp-${index}`,
    index,
    outline: raw.outline ?? "",
    text: raw.text ?? "",
    intent: raw.intent ?? "",
    status: (raw.status ?? "待编辑") as ScriptUnitStatus,
    selectedClipId: null,
    duration: raw.duration ?? 8,
    notes: raw.notes ?? "",
    candidates: [],
    shots: (raw.shots ?? []).map((s, sIdx) => ({
      id: `temp-shot-${index}-${sIdx}`,
      unitId: `temp-${index}`,
      index: sIdx,
      description: s.description ?? "",
      status: "待编辑" as ShotStatus,
      selectedClipId: null,
      visualMode: null,
      duration: s.duration ?? 8,
      notes: s.notes ?? "",
      candidates: [],
      generations: [],
    })),
  };
}

/* ── API 方法 ── */

/**
 * 获取脚本列表（可按项目筛选）
 * GET /api/projects/:projectId/scripts  或  GET /api/scripts
 */
export async function list(params?: ScriptListParams): Promise<PaginatedResponse<Script>> {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.search) query.set("search", params.search);
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  const raw = await http.get<RawScriptList>(`/scripts${qs ? `?${qs}` : ""}`);
  return {
    items: raw.items.map(mapScript),
    total: raw.total,
  };
}

/**
 * 创建脚本
 * POST /api/scripts
 */
export async function create(data: ScriptCreateInput): Promise<Script> {
  const raw = await http.post<RawScript>("/scripts", {
    project_id: data.projectId,
    title: data.title,
    summary: data.summary ?? "",
    source_type: data.sourceType ?? "blank",
    format: data.format ?? "横屏 16:9",
    visual_config: undefined,
    units: (data.units ?? []).map((unit) => ({
      outline: unit.outline,
      text: unit.text,
      intent: unit.intent,
      duration: unit.duration,
      notes: unit.notes,
    })),
  });
  return mapScript(raw);
}

/**
 * 获取脚本详情（含 units）
 * GET /api/scripts/:id
 */
export async function get(id: string): Promise<Script & { units: ScriptUnit[] }> {
  const raw = await http.get<RawScript>(`/scripts/${id}`);
  const mapped = mapScript(raw);
  return { ...mapped, units: mapped.units ?? [] };
}

/**
 * 获取剪辑项目创建初剪时保存的脚本基线
 * GET /api/scripts/snapshot?project_id=:projectId
 */
export async function getSnapshot(projectId: string): Promise<Script & { units: ScriptUnit[] }> {
  const query = new URLSearchParams({ project_id: projectId });
  const raw = await http.get<RawScript>(`/scripts/snapshot?${query.toString()}`);
  const mapped = mapScript(raw);
  return { ...mapped, units: mapped.units ?? [] };
}

/**
 * 更新脚本
 * PATCH /api/scripts/:id
 */
export async function update(id: string, data: ScriptUpdateInput): Promise<Script> {
  const raw = await http.patch<RawScript>(`/scripts/${id}`, {
    title: data.title,
    summary: data.summary,
    status: data.status,
    format: data.format,
    visual_config: data.visualConfig,
  });
  return mapScript(raw);
}

/**
 * 批量更新分镜单元
 * PATCH /api/scripts/:id/units
 */
export async function batchUpdateUnits(
  id: string,
  units: ScriptUnit[],
): Promise<{ units: ScriptUnit[] }> {
  await http.patch<{ status: string; progress: number; matched_count: number }>(
    `/scripts/${id}/units`,
    {
      units: units.map((unit) => ({
        id: unit.id,
        outline: unit.outline,
        text: unit.text,
        intent: unit.intent,
        status: unit.status,
        selected_clip_id: unit.selectedClipId,
        duration: unit.duration,
        notes: unit.notes,
        shots: unit.shots.map((shot) => ({
          id: shot.id,
          description: shot.description,
          status: shot.status,
          selected_clip_id: shot.selectedClipId,
          visual_mode: shot.visualMode,
          duration: shot.duration,
          notes: shot.notes,
        })),
      })),
    },
  );
  // 后端返回简化摘要，重新拉取脚本获取完整 units
  const fullScript = await get(id);
  return { units: fullScript.units ?? [] };
}

export async function saveEditorState(
  id: string,
  data: { title: string; visualConfig: VisualConfig; units: ScriptUnit[] },
): Promise<Script> {
  const raw = await http.patch<RawScript>(`/scripts/${id}/editor-state`, {
    title: data.title,
    visual_config: data.visualConfig,
    units: data.units.map((unit) => ({
      id: unit.id,
      outline: unit.outline,
      text: unit.text,
      intent: unit.intent,
      status: unit.status,
      selected_clip_id: unit.selectedClipId,
      duration: unit.duration,
      notes: unit.notes,
      shots: unit.shots.map((shot) => ({
        id: shot.id,
        description: shot.description,
        status: shot.status,
        selected_clip_id: shot.selectedClipId,
        visual_mode: shot.visualMode,
        duration: shot.duration,
        notes: shot.notes,
        sketch_data: undefined,
      })),
    })),
  });
  return mapScript(raw);
}

export async function selectGeneration(
  scriptId: string,
  shotId: string,
  generationId: string,
): Promise<Shot> {
  const raw = await http.post<RawShot>(
    `/scripts/${scriptId}/shots/${shotId}/generations/${generationId}/select`,
    {},
  );
  return mapShot(raw);
}

/**
 * 解析脚本文本/表格为分镜单元
 * POST /api/scripts/parse
 * 支持 text（粘贴文本）或 file（上传表格）两种模式
 */
export async function parse(data: ScriptParseInput): Promise<ScriptParseResult> {
  let rawUnits: RawParseUnit[];
  if (data.file) {
    const formData = new FormData();
    formData.append("file", data.file);
    rawUnits = await http.upload<RawParseUnit[]>("/scripts/parse", formData);
  } else {
    rawUnits = await http.post<RawParseUnit[]>("/scripts/parse", { text: data.text });
  }
  return {
    units: rawUnits.map((u, i) => mapParseUnit(u, i)),
  };
}

/**
 * 生成 AI 初剪项目
 * POST /api/scripts/:id/rough-cut
 */
export async function createRoughCut(
  id: string,
  options?: { title?: string; visualConfig?: VisualConfig },
): Promise<RoughCutResult> {
  const raw = await http.post<RawRoughCutResponse>(`/scripts/${id}/rough-cut`, {
    title: options?.title,
    visual_config: options?.visualConfig,
  });
  // 后端只返回 ID，需要分别拉取 project 和 script 详情
  const [project, scriptRaw] = await Promise.all([
    projectApi.get(raw.project_id),
    http.get<RawScript>(`/scripts/${raw.script_id}`),
  ]);
  return {
    project,
    script: mapScript(scriptRaw),
    jobId: raw.job_id,
    versionId: raw.version_id,
  };
}

export async function listLinkedCuts(id: string): Promise<LinkedCut[]> {
  const raw = await http.get<RawLinkedCut[]>(`/scripts/${id}/cuts`);
  return raw.map((cut) => ({
    projectId: cut.project_id,
    versionId: cut.version_id,
    name: cut.name,
    versionName: cut.version_name,
    status: cut.status,
    aspectRatio: cut.aspect_ratio ?? undefined,
    timelineVersion: cut.timeline_version ?? 0,
    currentUserRole: cut.current_user_role,
    updatedAt: formatRelativeTime(cut.updated_at),
  }));
}

/**
 * 删除脚本
 * DELETE /api/scripts/:id
 */
export function remove(id: string): Promise<void> {
  return http.delete<void>(`/scripts/${id}`);
}

export async function getDeleteImpact(id: string): Promise<DeleteImpact> {
  const raw = await http.get<RawDeleteImpact>(`/scripts/${id}/delete-impact`);
  return mapDeleteImpact(raw);
}

export async function exportFile(
  id: string,
  format: "json" | "csv" | "xlsx" | "pdf",
): Promise<void> {
  const { blob, filename } = await http.download(`/scripts/${id}/export?format=${format}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename ?? `script.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * 触发镜头匹配
 * POST /api/scripts/:id/match
 */
export async function matchClips(
  id: string,
  options?: { unitId?: string; shotIds?: string[]; visualMode?: string },
): Promise<{ jobId: string; units?: ScriptUnit[] }> {
  const body: Record<string, string | string[]> = {};
  if (options?.unitId) body.unit_id = options.unitId;
  if (options?.shotIds?.length) body.shot_ids = options.shotIds;
  if (options?.visualMode) body.visual_mode = options.visualMode;
  const raw = await http.post<{ job_id?: string; jobId?: string }>(`/scripts/${id}/match`, body);
  return {
    jobId: raw.job_id ?? raw.jobId ?? "",
  };
}

export async function completeShots(
  id: string,
  shotIds: string[],
): Promise<{ jobId: string; message: string }> {
  const raw = await http.post<{ job_id: string; message: string }>(
    `/scripts/${id}/complete-shots`,
    { shot_ids: shotIds },
  );
  return { jobId: raw.job_id, message: raw.message };
}
