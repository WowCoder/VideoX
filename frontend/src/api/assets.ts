import { http } from "./client";
import { formatRelativeTime } from "@/lib/utils";

export type MediaType = "image" | "video" | "audio";
export type AssetSourceCategory = "ai" | "non-ai";
export type AssetContentType = "scene" | "role" | "object" | "event";

export interface AssetSegment {
  id: string;
  assetId: string;
  startMs: number;
  endMs: number;
  durationMs: number;
  title: string;
  transcript: string;
  ocrText: string;
  tags: string[];
  recognition: Record<string, unknown>;
  qualityScore: number;
  thumbnailUrl?: string;
}

export interface Asset {
  id: string;
  ownerId: string;
  name: string;
  mediaType: MediaType;
  sourceType: string;
  sourceCategory: AssetSourceCategory;
  contentTypes: AssetContentType[];
  status: string;
  processingStatus: string;
  mimeType?: string;
  durationMs: number;
  width?: number;
  height?: number;
  hasAudio: boolean;
  fileSizeMb: number;
  tags: string[];
  recognition: Record<string, unknown>;
  metadata: Record<string, unknown>;
  mediaUrl?: string;
  thumbnailUrl?: string;
  matchField?: string;
  matchExcerpt?: string;
  matchedSegmentId?: string;
  projectIds: string[];
  segments: AssetSegment[];
  createdAt: string;
  updatedAt: string;
  createdAtRelative: string;
}

export interface RawAssetSegment {
  id: string;
  asset_id: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  title: string;
  transcript: string;
  ocr_text: string;
  tags: unknown[];
  recognition: Record<string, unknown>;
  quality_score: number;
  thumbnail_url: string | null;
}

export interface RawAsset {
  id: string;
  owner_id: string;
  name: string;
  media_type: MediaType;
  source_type: string;
  source_category?: AssetSourceCategory;
  content_types?: AssetContentType[];
  status: string;
  processing_status: string;
  mime_type: string | null;
  duration_ms: number;
  width: number | null;
  height: number | null;
  has_audio: boolean;
  file_size_mb: number;
  tags: unknown[];
  recognition: Record<string, unknown>;
  asset_metadata?: Record<string, unknown>;
  media_url: string | null;
  thumbnail_url: string | null;
  match_field: string | null;
  match_excerpt: string | null;
  matched_segment_id: string | null;
  project_ids: string[];
  segments: RawAssetSegment[];
  created_at: string;
  updated_at: string;
}

export interface AssetListParams {
  cursor?: string;
  limit?: number;
  projectId?: string;
  mediaType?: MediaType;
  sourceType?: string;
  sourceCategory?: AssetSourceCategory;
  search?: string;
  status?: string;
}

export interface AssetPage {
  items: Asset[];
  nextCursor?: string;
  hasMore: boolean;
}

export interface UploadResponse {
  assetId: string;
  name: string;
  mediaType: MediaType;
  status: string;
  jobId?: string;
}

export interface AssetDeleteImpact {
  canDelete: boolean;
  projectCount: number;
  shotCount: number;
  compositionCount: number;
  blockers: string[];
}

function mapSegment(raw: RawAssetSegment): AssetSegment {
  return {
    id: raw.id,
    assetId: raw.asset_id,
    startMs: raw.start_ms,
    endMs: raw.end_ms,
    durationMs: raw.duration_ms,
    title: raw.title,
    transcript: raw.transcript,
    ocrText: raw.ocr_text,
    tags: (raw.tags ?? []).map(String),
    recognition: raw.recognition ?? {},
    qualityScore: raw.quality_score,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
  };
}

export function mapAsset(raw: RawAsset): Asset {
  return {
    id: raw.id,
    ownerId: raw.owner_id,
    name: raw.name,
    mediaType: raw.media_type,
    sourceType: raw.source_type,
    sourceCategory: raw.source_category ?? (raw.source_type === "ai_generated" || raw.source_type.startsWith("ai_") ? "ai" : "non-ai"),
    contentTypes: raw.content_types ?? [],
    status: raw.status,
    processingStatus: raw.processing_status,
    mimeType: raw.mime_type ?? undefined,
    durationMs: raw.duration_ms,
    width: raw.width ?? undefined,
    height: raw.height ?? undefined,
    hasAudio: raw.has_audio,
    fileSizeMb: raw.file_size_mb,
    tags: (raw.tags ?? []).map(String),
    recognition: raw.recognition ?? {},
    metadata: raw.asset_metadata ?? {},
    mediaUrl: raw.media_url ?? undefined,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
    matchField: raw.match_field ?? undefined,
    matchExcerpt: raw.match_excerpt ?? undefined,
    matchedSegmentId: raw.matched_segment_id ?? undefined,
    projectIds: raw.project_ids ?? [],
    segments: (raw.segments ?? []).map(mapSegment),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    createdAtRelative: formatRelativeTime(raw.created_at),
  };
}

export async function listPage(params: AssetListParams = {}): Promise<AssetPage> {
  const query = new URLSearchParams();
  if (params.cursor) query.set("cursor", params.cursor);
  query.set("limit", String(params.limit ?? 50));
  if (params.projectId) query.set("project_id", params.projectId);
  if (params.mediaType) query.set("media_type", params.mediaType);
  if (params.sourceType) query.set("source_type", params.sourceType);
  if (params.sourceCategory) query.set("source_category", params.sourceCategory);
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  const raw = await http.get<{ items: RawAsset[]; next_cursor: string | null; has_more: boolean }>(
    `/assets?${query.toString()}`,
  );
  return {
    items: raw.items.map(mapAsset),
    nextCursor: raw.next_cursor ?? undefined,
    hasMore: raw.has_more,
  };
}

export async function upload(file: File, projectId?: string): Promise<UploadResponse> {
  const data = new FormData();
  data.append("file", file);
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const raw = await http.upload<{
    asset_id: string;
    name: string;
    media_type: MediaType;
    status: string;
    job_id: string | null;
  }>(`/assets/upload${query}`, data);
  return {
    assetId: raw.asset_id,
    name: raw.name,
    mediaType: raw.media_type,
    status: raw.status,
    jobId: raw.job_id ?? undefined,
  };
}

export async function get(assetId: string): Promise<Asset> {
  return mapAsset(await http.get<RawAsset>(`/assets/${assetId}`));
}

export async function listSegments(
  assetId: string,
  params: { cursor?: string; limit?: number } = {},
): Promise<AssetSegment[]> {
  const query = new URLSearchParams();
  if (params.cursor) query.set("cursor", params.cursor);
  query.set("limit", String(params.limit ?? 100));
  const raw = await http.get<RawAssetSegment[]>(`/assets/${assetId}/segments?${query}`);
  return raw.map(mapSegment);
}

export async function getDeleteImpact(assetId: string): Promise<AssetDeleteImpact> {
  const raw = await http.get<{
    can_delete: boolean;
    project_count: number;
    shot_count: number;
    composition_count: number;
    blockers: string[];
  }>(`/assets/${assetId}/delete-impact`);
  return {
    canDelete: raw.can_delete,
    projectCount: raw.project_count,
    shotCount: raw.shot_count,
    compositionCount: raw.composition_count,
    blockers: raw.blockers,
  };
}

export function remove(assetId: string, options: { permanent?: boolean } = {}): Promise<void> {
  const permanent = options.permanent ? "true" : "false";
  return http.delete<void>(`/assets/${assetId}?confirmed=true&permanent=${permanent}`);
}

export async function restore(assetId: string): Promise<Asset> {
  return mapAsset(await http.post<RawAsset>(`/assets/${assetId}/restore`));
}
