// ──────────────────────────────────────────────
// OpenVMA - 项目 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";
import type { Asset, Project, PaginatedResponse, ProjectStatus, ThumbnailVariant } from "@/types/models";
import { formatRelativeTime } from "@/lib/utils";
import { mapAsset, type RawAsset } from "./assets";
import { mapDeleteImpact, type DeleteImpact, type RawDeleteImpact } from "./deletion";

export type { DeleteImpact } from "./deletion";

export interface ProjectCreateInput {
  name: string;
  type: string;
  description: string;
  variant?: string;
}

export interface ProjectUpdateInput {
  name?: string;
  description?: string;
  status?: string;
  variant?: string;
}

export interface ProjectListParams {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface ProjectStats {
  assetCount: number;
  clipCount: number;
  scriptCount: number;
  totalDuration: number;
  storageUsedMb: number;
}

export interface DashboardSummary {
  projectCount: number;
  assetCount: number;
  processingAssetCount: number;
  clipCount: number;
  scriptCount: number;
  queuedJobCount: number;
  runningJobCount: number;
  pausedJobCount: number;
  completedJobCount: number;
  failedJobCount: number;
}

export type ProjectRole = "owner" | "editor" | "viewer";

export interface ProjectMember {
  id: string;
  userId: string;
  name: string;
  email: string;
  avatarInitial: string;
  role: ProjectRole;
  joinedAt: string;
}

export interface ProjectInvitation {
  id: string;
  email: string;
  role: Exclude<ProjectRole, "owner">;
  status: string;
  expiresAt: string;
  createdAt: string;
  invitationUrl?: string;
  delivery: string;
  deliveryMessage: string;
}

export interface ProjectCollaboration {
  projectId: string;
  currentUserRole: ProjectRole;
  members: ProjectMember[];
  invitations: ProjectInvitation[];
  seatsUsed: number;
  seatQuota: number;
  canManageMembers: boolean;
  managementMessage: string;
}

export interface InvitationPreview {
  projectId: string;
  projectName: string;
  inviterName: string;
  role: Exclude<ProjectRole, "owner">;
  recipient: string;
  status: string;
  expiresAt: string;
}

export type TimelineTrack = "video" | "audio" | "subtitle";

export interface ProjectTimelineClip {
  id: string;
  track: TimelineTrack;
  start: number;
  duration: number;
  name: string;
  variant: ThumbnailVariant;
  assetId?: string;
  sourceClipId?: string;
  sourceStart: number;
  sourceScriptId?: string;
  sourceUnitId?: string;
  sourceShotId?: string;
  snapshotScriptId?: string;
  snapshotUnitId?: string;
  snapshotShotId?: string;
  generatedMediaPath?: string;
  generatedMediaUrl?: string;
  generatedMediaType?: "image" | "video";
  origin?: "script_match" | "script_generated" | "script_placeholder" | "script_subtitle" | "manual_asset" | "manual_generated";
  syncStatus?: "synced" | "script_changed" | "timeline_changed" | "detached";
  text?: string;
  transform: {
    scale: number;
    x: number;
    y: number;
    rotation: number;
    opacity: number;
    crop: { l: number; t: number; r: number; b: number };
  };
  adjust: { brightness: number; contrast: number; saturation: number };
  audio: {
    volume: number;
    muted: boolean;
    denoise: boolean;
    fadeIn: number;
    fadeOut: number;
  };
  transition: { type: "none" | "fade_black" | "fade_white"; duration: number };
}

export interface ProjectTimeline {
  projectId: string;
  cutVersionId?: string;
  cutVersionName?: string;
  version: number;
  aspectRatio: string;
  clips: ProjectTimelineClip[];
  updatedAt?: string;
}

export interface ProjectTimelineSaveInput {
  version: number;
  aspectRatio: string;
  clips: ProjectTimelineClip[];
}

export interface CutVersion {
  id: string;
  projectId: string;
  snapshotScriptId?: string;
  name: string;
  status: string;
  aspectRatio: string;
  timelineVersion: number;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMediaItem {
  id: string;
  projectId: string;
  kind: "source_asset" | "ai_image" | "ai_video" | "ai_effect_video";
  assetId?: string;
  storagePath?: string;
  mediaType: "image" | "video" | "audio";
  sourceProjectId?: string;
  sourceScriptId?: string;
  sourceShotId?: string;
  name: string;
  duration: number;
  mediaUrl?: string;
  thumbnailUrl?: string;
  asset?: Asset;
  createdAt: string;
}

/* ── 后端原始类型（snake_case）── */

interface RawProject {
  id: string;
  name: string;
  initial: string;
  type: string;
  description: string;
  status: string;
  asset_count: number;
  clip_count: number;
  script_count: number;
  variant: string;
  members: string[];
  current_user_role: ProjectRole;
  is_new: boolean;
  source_script_id: string | null;
  visual_style: string | null;
  aspect_ratio: string | null;
  ai_shot_count: number;
  updated_at: string;
  created_at: string | null;
}

interface RawProjectList {
  items: RawProject[];
  total: number;
}

interface RawProjectStats {
  asset_count: number;
  clip_count: number;
  script_count: number;
  total_duration: number;
  storage_used_mb: number;
}

interface RawDashboardSummary {
  project_count: number;
  asset_count: number;
  processing_asset_count: number;
  clip_count: number;
  script_count: number;
  queued_job_count: number;
  running_job_count: number;
  paused_job_count: number;
  completed_job_count: number;
  failed_job_count: number;
}

interface RawTimelineClip {
  id: string;
  track: TimelineTrack;
  start: number;
  duration: number;
  name: string;
  variant: string;
  asset_id: string | null;
  source_clip_id: string | null;
  source_start: number;
  source_script_id?: string | null;
  source_unit_id?: string | null;
  source_shot_id?: string | null;
  snapshot_script_id?: string | null;
  snapshot_unit_id?: string | null;
  snapshot_shot_id?: string | null;
  generated_media_path?: string | null;
  generated_media_url?: string | null;
  generated_media_type?: ProjectTimelineClip["generatedMediaType"] | null;
  origin?: ProjectTimelineClip["origin"];
  sync_status?: ProjectTimelineClip["syncStatus"];
  text: string | null;
  transform: ProjectTimelineClip["transform"];
  adjust: ProjectTimelineClip["adjust"];
  audio: {
    volume: number;
    muted?: boolean;
    denoise: boolean;
    fade_in?: number;
    fade_out?: number;
  };
  transition?: ProjectTimelineClip["transition"];
}

interface RawProjectTimeline {
  project_id: string;
  cut_version_id?: string | null;
  cut_version_name?: string | null;
  version: number;
  aspect_ratio: string;
  clips: RawTimelineClip[];
  updated_at: string | null;
}

interface RawCutVersion {
  id: string;
  project_id: string;
  snapshot_script_id?: string | null;
  name: string;
  status: string;
  aspect_ratio: string;
  timeline_version: number;
  created_at: string;
  updated_at: string;
}

interface RawProjectMediaItem {
  id: string;
  project_id: string;
  kind: ProjectMediaItem["kind"];
  asset_id: string | null;
  storage_path: string | null;
  media_type: ProjectMediaItem["mediaType"];
  source_project_id: string | null;
  source_script_id: string | null;
  source_shot_id: string | null;
  name: string;
  duration: number;
  media_url: string | null;
  thumbnail_url: string | null;
  asset: RawAsset | null;
  created_at: string;
}

interface RawProjectMediaList {
  items: RawProjectMediaItem[];
  total: number;
}

/* ── 映射函数 ── */

function mapProject(raw: RawProject): Project {
  return {
    id: raw.id,
    name: raw.name,
    initial: raw.initial,
    type: raw.type,
    description: raw.description,
    updatedAt: formatRelativeTime(raw.updated_at),
    status: raw.status as ProjectStatus,
    assetCount: raw.asset_count ?? 0,
    clipCount: raw.clip_count ?? 0,
    scriptCount: raw.script_count ?? 0,
    variant: raw.variant as ThumbnailVariant,
    members: raw.members ?? [],
    currentUserRole: raw.current_user_role ?? "owner",
    isNew: raw.is_new,
    sourceScriptId: raw.source_script_id ?? undefined,
    visualStyle: raw.visual_style ?? undefined,
    aspectRatio: raw.aspect_ratio ?? undefined,
    aiShotCount: raw.ai_shot_count ?? 0,
  };
}

function mapProjectStats(raw: RawProjectStats): ProjectStats {
  return {
    assetCount: raw.asset_count ?? 0,
    clipCount: raw.clip_count ?? 0,
    scriptCount: raw.script_count ?? 0,
    totalDuration: raw.total_duration ?? 0,
    storageUsedMb: raw.storage_used_mb ?? 0,
  };
}

function mapTimelineClip(raw: RawTimelineClip): ProjectTimelineClip {
  return {
    id: raw.id,
    track: raw.track,
    start: raw.start,
    duration: raw.duration,
    name: raw.name,
    variant: raw.variant as ThumbnailVariant,
    assetId: raw.asset_id ?? undefined,
    sourceClipId: raw.source_clip_id ?? undefined,
    sourceStart: raw.source_start ?? 0,
    sourceScriptId: raw.source_script_id ?? undefined,
    sourceUnitId: raw.source_unit_id ?? undefined,
    sourceShotId: raw.source_shot_id ?? undefined,
    snapshotScriptId: raw.snapshot_script_id ?? undefined,
    snapshotUnitId: raw.snapshot_unit_id ?? undefined,
    snapshotShotId: raw.snapshot_shot_id ?? undefined,
    generatedMediaPath: raw.generated_media_path ?? undefined,
    generatedMediaUrl: raw.generated_media_url ?? undefined,
    generatedMediaType: raw.generated_media_type ?? undefined,
    origin: raw.origin ?? "manual_asset",
    syncStatus: raw.sync_status ?? "detached",
    text: raw.text ?? undefined,
    transform: raw.transform,
    adjust: raw.adjust,
    audio: {
      volume: raw.audio?.volume ?? 100,
      muted: raw.audio?.muted ?? false,
      denoise: raw.audio?.denoise ?? false,
      fadeIn: raw.audio?.fade_in ?? 0,
      fadeOut: raw.audio?.fade_out ?? 0,
    },
    transition: raw.transition ?? { type: "none", duration: 0.5 },
  };
}

function mapTimeline(raw: RawProjectTimeline): ProjectTimeline {
  return {
    projectId: raw.project_id,
    cutVersionId: raw.cut_version_id ?? undefined,
    cutVersionName: raw.cut_version_name ?? undefined,
    version: raw.version,
    aspectRatio: raw.aspect_ratio,
    clips: raw.clips.map(mapTimelineClip),
    updatedAt: raw.updated_at ?? undefined,
  };
}

function mapProjectMediaItem(raw: RawProjectMediaItem): ProjectMediaItem {
  return {
    id: raw.id,
    projectId: raw.project_id,
    kind: raw.kind,
    assetId: raw.asset_id ?? undefined,
    storagePath: raw.storage_path ?? undefined,
    mediaType: raw.media_type,
    sourceProjectId: raw.source_project_id ?? undefined,
    sourceScriptId: raw.source_script_id ?? undefined,
    sourceShotId: raw.source_shot_id ?? undefined,
    name: raw.name,
    duration: raw.duration ?? 0,
    mediaUrl: raw.media_url ?? undefined,
    thumbnailUrl: raw.thumbnail_url ?? undefined,
    asset: raw.asset ? mapAsset(raw.asset) : undefined,
    createdAt: raw.created_at,
  };
}

/* ── API 方法 ── */

/**
 * 获取项目列表
 * GET /api/projects
 */
export async function list(params?: ProjectListParams): Promise<PaginatedResponse<Project>> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.status) query.set("status", params.status);
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const qs = query.toString();
  const raw = await http.get<RawProjectList>(`/projects${qs ? `?${qs}` : ""}`);
  return {
    items: raw.items.map(mapProject),
    total: raw.total,
  };
}

/**
 * 创建项目
 * POST /api/projects
 */
export async function create(data: ProjectCreateInput): Promise<Project> {
  const raw = await http.post<RawProject>("/projects", data);
  return mapProject(raw);
}

/**
 * 获取项目详情
 * GET /api/projects/:id
 */
export async function get(id: string): Promise<Project> {
  const raw = await http.get<RawProject>(`/projects/${id}`);
  return mapProject(raw);
}

/**
 * 更新项目
 * PATCH /api/projects/:id
 */
export async function update(id: string, data: ProjectUpdateInput): Promise<Project> {
  const raw = await http.patch<RawProject>(`/projects/${id}`, data);
  return mapProject(raw);
}

/**
 * 删除项目
 * DELETE /api/projects/:id
 */
export function remove(id: string): Promise<void> {
  return http.delete<void>(`/projects/${id}`);
}

export async function getDeleteImpact(id: string): Promise<DeleteImpact> {
  const raw = await http.get<RawDeleteImpact>(`/projects/${id}/delete-impact`);
  return mapDeleteImpact(raw);
}

/**
 * 获取项目统计数据
 * GET /api/projects/:id/stats
 */
export async function getStats(id: string): Promise<ProjectStats> {
  const raw = await http.get<RawProjectStats>(`/projects/${id}/stats`);
  return mapProjectStats(raw);
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const raw = await http.get<RawDashboardSummary>("/projects/dashboard-summary");
  return {
    projectCount: raw.project_count,
    assetCount: raw.asset_count,
    processingAssetCount: raw.processing_asset_count,
    clipCount: raw.clip_count,
    scriptCount: raw.script_count,
    queuedJobCount: raw.queued_job_count,
    runningJobCount: raw.running_job_count,
    pausedJobCount: raw.paused_job_count,
    completedJobCount: raw.completed_job_count,
    failedJobCount: raw.failed_job_count,
  };
}

export async function getTimeline(id: string, cutVersionId?: string): Promise<ProjectTimeline> {
  const query = cutVersionId ? `?cut_version_id=${encodeURIComponent(cutVersionId)}` : "";
  const raw = await http.get<RawProjectTimeline>(`/projects/${id}/timeline${query}`);
  return mapTimeline(raw);
}

export async function saveTimeline(
  id: string,
  data: ProjectTimelineSaveInput,
  cutVersionId?: string,
): Promise<ProjectTimeline> {
  const body = {
    version: data.version,
    aspect_ratio: data.aspectRatio,
    clips: data.clips.map((clip) => ({
      id: clip.id,
      track: clip.track,
      start: clip.start,
      duration: clip.duration,
      name: clip.name,
      variant: clip.variant,
      asset_id: clip.assetId,
      source_clip_id: clip.sourceClipId,
      source_start: clip.sourceStart,
      source_script_id: clip.sourceScriptId,
      source_unit_id: clip.sourceUnitId,
      source_shot_id: clip.sourceShotId,
      snapshot_script_id: clip.snapshotScriptId,
      snapshot_unit_id: clip.snapshotUnitId,
      snapshot_shot_id: clip.snapshotShotId,
      generated_media_path: clip.generatedMediaPath,
      generated_media_type: clip.generatedMediaType,
      origin: clip.origin ?? "manual_asset",
      sync_status: clip.syncStatus ?? "detached",
      text: clip.text,
      transform: clip.transform,
      adjust: clip.adjust,
      audio: {
        volume: clip.audio.volume,
        muted: clip.audio.muted,
        denoise: clip.audio.denoise,
        fade_in: clip.audio.fadeIn,
        fade_out: clip.audio.fadeOut,
      },
      transition: clip.transition,
    })),
  };
  const query = cutVersionId ? `?cut_version_id=${encodeURIComponent(cutVersionId)}` : "";
  const raw = await http.put<RawProjectTimeline>(`/projects/${id}/timeline${query}`, body);
  return mapTimeline(raw);
}

/** 为历史空剪辑项目按初剪快照补装完整时间线。 */
export async function assembleTimelineFromScript(id: string, cutVersionId?: string): Promise<ProjectTimeline> {
  const query = cutVersionId ? `?cut_version_id=${encodeURIComponent(cutVersionId)}` : "";
  const raw = await http.post<RawProjectTimeline>(`/projects/${id}/timeline/assemble-from-script${query}`, {});
  return mapTimeline(raw);
}

export async function listVersions(id: string): Promise<CutVersion[]> {
  const raw = await http.get<RawCutVersion[]>(`/projects/${id}/versions`);
  return raw.map((version) => ({
    id: version.id,
    projectId: version.project_id,
    snapshotScriptId: version.snapshot_script_id ?? undefined,
    name: version.name,
    status: version.status,
    aspectRatio: version.aspect_ratio,
    timelineVersion: version.timeline_version,
    createdAt: version.created_at,
    updatedAt: version.updated_at,
  }));
}

export async function importAssets(id: string, assetIds: string[]): Promise<Asset[]> {
  const raw = await http.post<RawAsset[]>(`/projects/${id}/assets/import`, { asset_ids: assetIds });
  return raw.map(mapAsset);
}

export async function listMedia(id: string): Promise<PaginatedResponse<ProjectMediaItem>> {
  const raw = await http.get<RawProjectMediaList>(`/projects/${id}/media`);
  return { items: raw.items.map(mapProjectMediaItem), total: raw.total };
}

export async function syncMedia(id: string): Promise<PaginatedResponse<ProjectMediaItem>> {
  const raw = await http.post<RawProjectMediaList>(`/projects/${id}/media/sync`, {});
  return { items: raw.items.map(mapProjectMediaItem), total: raw.total };
}

interface RawProjectMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  avatar_initial: string;
  role: ProjectRole;
  joined_at: string;
}

interface RawProjectInvitation {
  id: string;
  email: string;
  role: "editor" | "viewer";
  status: string;
  expires_at: string;
  created_at: string;
  invitation_url?: string | null;
  delivery: string;
  delivery_message: string;
}

function mapMember(raw: RawProjectMember): ProjectMember {
  return {
    id: raw.id,
    userId: raw.user_id,
    name: raw.name,
    email: raw.email,
    avatarInitial: raw.avatar_initial,
    role: raw.role,
    joinedAt: raw.joined_at,
  };
}

function mapInvitation(raw: RawProjectInvitation): ProjectInvitation {
  return {
    id: raw.id,
    email: raw.email,
    role: raw.role,
    status: raw.status,
    expiresAt: raw.expires_at,
    createdAt: raw.created_at,
    invitationUrl: raw.invitation_url ?? undefined,
    delivery: raw.delivery,
    deliveryMessage: raw.delivery_message,
  };
}

export async function getCollaboration(projectId: string): Promise<ProjectCollaboration> {
  const raw = await http.get<{
    project_id: string;
    current_user_role: ProjectRole;
    members: RawProjectMember[];
    invitations: RawProjectInvitation[];
    seats_used: number;
    seat_quota: number;
    can_manage_members: boolean;
    management_message: string;
  }>(`/projects/${projectId}/collaboration`);
  return {
    projectId: raw.project_id,
    currentUserRole: raw.current_user_role,
    members: raw.members.map(mapMember),
    invitations: raw.invitations.map(mapInvitation),
    seatsUsed: raw.seats_used,
    seatQuota: raw.seat_quota,
    canManageMembers: raw.can_manage_members,
    managementMessage: raw.management_message,
  };
}

export async function inviteMember(
  projectId: string,
  data: { email: string; role: "editor" | "viewer" },
): Promise<ProjectInvitation> {
  return mapInvitation(
    await http.post<RawProjectInvitation>(`/projects/${projectId}/invitations`, data),
  );
}

export async function updateMemberRole(
  projectId: string,
  memberId: string,
  role: "editor" | "viewer",
): Promise<ProjectMember> {
  return mapMember(
    await http.patch<RawProjectMember>(`/projects/${projectId}/members/${memberId}`, { role }),
  );
}

export function removeMember(projectId: string, memberId: string): Promise<void> {
  return http.delete<void>(`/projects/${projectId}/members/${memberId}`);
}

export function revokeInvitation(projectId: string, invitationId: string): Promise<void> {
  return http.delete<void>(`/projects/${projectId}/invitations/${invitationId}`);
}

export async function previewInvitation(token: string): Promise<InvitationPreview> {
  const raw = await http.get<{
    project_id: string;
    project_name: string;
    inviter_name: string;
    role: "editor" | "viewer";
    recipient: string;
    status: string;
    expires_at: string;
  }>(`/projects/invitations/${encodeURIComponent(token)}`, { skipAuth: true });
  return {
    projectId: raw.project_id,
    projectName: raw.project_name,
    inviterName: raw.inviter_name,
    role: raw.role,
    recipient: raw.recipient,
    status: raw.status,
    expiresAt: raw.expires_at,
  };
}

export async function acceptInvitation(token: string): Promise<{
  projectId: string;
  projectName: string;
  role: "editor" | "viewer";
  message: string;
}> {
  const raw = await http.post<{
    project_id: string;
    project_name: string;
    role: "editor" | "viewer";
    message: string;
  }>(`/projects/invitations/${encodeURIComponent(token)}/accept`);
  return {
    projectId: raw.project_id,
    projectName: raw.project_name,
    role: raw.role,
    message: raw.message,
  };
}
