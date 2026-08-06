// ──────────────────────────────────────────────
// OpenVMA - 素材 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";
import { formatRelativeTime } from "@/lib/utils";
import { mapDeleteImpact, type DeleteImpact, type RawDeleteImpact } from "./deletion";
import type {
  Asset,
  Clip,
  PaginatedResponse,
  AssetStatus,
  ThumbnailVariant,
  SceneType,
  ShotType,
  CameraMotion,
} from "@/types/models";

export interface AssetListParams {
  projectId?: string;
  mediaType?: "video" | "audio";
  search?: string;
  status?: string;
}

/** 上传响应（对应后端 UploadResponse，snake_case） */
interface RawUploadResponse {
  asset_id: string;
  name: string;
  status: string;
  job_id: string;
}

export interface UploadResponse {
  assetId: string;
  name: string;
  status: string;
  jobId: string;
}

/* ── 后端原始类型（snake_case）── */

interface RawClip {
  id: string;
  asset_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  title: string;
  transcript_segment: string;
  ocr_segment: string;
  scene_type: string | null;
  shot_type: string | null;
  camera_motion: string | null;
  persons: unknown[];
  objects: unknown[];
  thumbnail_path: string | null;
  thumbnail_url: string | null;
  variant: string;
  quality_score: number;
}

export interface RawAsset {
  id: string;
  project_id: string;
  name: string;
  media_type: "video" | "audio";
  has_audio: boolean;
  duration: number;
  status: string;
  source: string;
  variant: string;
  media_url: string | null;
  thumbnail_url: string | null;
  file_size_mb: number;
  resolution: string | null;
  fps: number;
  codec: string | null;
  audio_codec: string | null;
  sample_rate: number | null;
  channels: number | null;
  bitrate: number | null;
  transcript: string | null;
  ocr_text: string | null;
  tags: unknown[];
  match_field: Asset["matchField"] | null;
  match_excerpt: string | null;
  matched_clip_id: string | null;
  uploaded_at: string;
  created_at: string | null;
  clips: RawClip[];
}

interface RawAssetList {
  items: RawAsset[];
  total: number;
}

/* ── 映射函数 ── */

function fmtTimecode(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function mapClip(raw: RawClip): Clip {
  return {
    id: raw.id,
    assetId: raw.asset_id,
    startTime: raw.start_time,
    endTime: raw.end_time,
    duration: raw.duration,
    title: raw.title,
    transcriptSegment: raw.transcript_segment,
    ocrSegment: raw.ocr_segment,
    sceneType: (raw.scene_type as SceneType) ?? null,
    shotType: (raw.shot_type as ShotType) ?? null,
    cameraMotion: (raw.camera_motion as CameraMotion) ?? null,
    persons: (raw.persons as string[]) ?? [],
    objects: (raw.objects as string[]) ?? [],
    thumbnailPath: raw.thumbnail_path ?? undefined,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
    variant: raw.variant as ThumbnailVariant,
    qualityScore: raw.quality_score,
    range: `${fmtTimecode(raw.start_time)}-${fmtTimecode(raw.end_time)}`,
    tags: [],
    transcript: raw.transcript_segment,
  };
}

export function mapAsset(raw: RawAsset): Asset {
  return {
    id: raw.id,
    projectId: raw.project_id,
    name: raw.name,
    mediaType: raw.media_type ?? "video",
    hasAudio: raw.has_audio ?? false,
    duration: String(raw.duration),
    status: raw.status as AssetStatus,
    source: raw.source,
    variant: raw.variant as ThumbnailVariant,
    mediaUrl: raw.media_url ?? undefined,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
    fileSizeMb: raw.file_size_mb,
    resolution: raw.resolution ?? undefined,
    fps: raw.fps,
    codec: raw.codec ?? undefined,
    audioCodec: raw.audio_codec ?? undefined,
    sampleRate: raw.sample_rate ?? undefined,
    channels: raw.channels ?? undefined,
    bitrate: raw.bitrate ?? undefined,
    transcript: raw.transcript ?? undefined,
    ocrText: raw.ocr_text ?? undefined,
    tags: (raw.tags as string[]) ?? [],
    matchField: raw.match_field ?? undefined,
    matchExcerpt: raw.match_excerpt ?? undefined,
    matchedClipId: raw.matched_clip_id ?? undefined,
    uploadedAt: formatRelativeTime(raw.uploaded_at),
    clips: (raw.clips ?? []).map(mapClip),
  };
}

function mapUploadResponse(raw: RawUploadResponse): UploadResponse {
  return {
    assetId: raw.asset_id,
    name: raw.name,
    status: raw.status,
    jobId: raw.job_id,
  };
}

/* ── API 方法 ── */

/**
 * 获取素材列表（可按项目筛选）
 * GET /api/assets?project_id=xxx
 */
export async function list(params?: AssetListParams): Promise<PaginatedResponse<Asset>> {
  const query = new URLSearchParams();
  if (params?.projectId) query.set("project_id", params.projectId);
  if (params?.mediaType) query.set("media_type", params.mediaType);
  if (params?.search) query.set("search", params.search);
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  const raw = await http.get<RawAssetList>(`/assets${qs ? `?${qs}` : ""}`);
  return {
    items: raw.items.map(mapAsset),
    total: raw.total,
  };
}

/**
 * 上传素材文件
 * POST /api/assets/upload?project_id=xxx  (multipart/form-data, field: "file")
 */
export async function upload(
  projectId: string,
  file: File,
  name?: string,
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);
  const raw = await http.upload<RawUploadResponse>(
    `/assets/upload?project_id=${encodeURIComponent(projectId)}`,
    formData,
  );
  return mapUploadResponse(raw);
}

/**
 * 获取素材详情
 * GET /api/assets/:id
 */
export async function get(assetId: string): Promise<Asset> {
  const raw = await http.get<RawAsset>(`/assets/${assetId}`);
  return mapAsset(raw);
}

/**
 * 获取素材的片段列表
 * GET /api/assets/:id/clips
 */
export async function listClips(assetId: string): Promise<Clip[]> {
  const raw = await http.get<RawClip[]>(`/assets/${assetId}/clips`);
  return raw.map(mapClip);
}

/** @deprecated 使用 listClips 代替 */
export const getClips = listClips;

/**
 * 删除素材
 * DELETE /api/assets/:id
 */
export function remove(assetId: string): Promise<void> {
  return http.delete<void>(`/assets/${assetId}`);
}

export async function getDeleteImpact(assetId: string): Promise<DeleteImpact> {
  const raw = await http.get<RawDeleteImpact>(`/assets/${assetId}/delete-impact`);
  return mapDeleteImpact(raw);
}
