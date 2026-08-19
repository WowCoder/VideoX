import { http } from "./client";
import { formatRelativeTime } from "@/lib/utils";
import { mapAsset, type Asset, type RawAsset } from "./assets";
import { temporaryId } from "@/stores/workspaceTransforms";

export type ProjectStatus = "draft" | "editing" | "processing" | "ready" | "exporting" | "failed";
export type AspectRatio = "16:9" | "9:16" | "1:1" | "4:3";

export interface Project {
  id: string;
  name: string;
  initial: string;
  type: string;
  description: string;
  status: ProjectStatus;
  variant: string;
  coverAssetId?: string;
  masterOutputAssetId?: string;
  coverMediaType?: "image" | "video" | "audio";
  coverMediaUrl?: string;
  coverThumbnailUrl?: string;
  assetCount: number;
  sceneCount: number;
  shotCount: number;
  durationMs: number;
  aspectRatio: AspectRatio;
  matchedPercent: number;
  activeJobCount: number;
  updatedAt: string;
  updatedAtIso: string;
  createdAt: string;
}

export interface Candidate {
  id: string;
  segmentId?: string;
  title: string;
  source: string;
  rangeStartMs: number;
  rangeEndMs: number;
  score: number;
  reason: string;
  lowConfidence: boolean;
}

export interface ShotMediaVersion {
  id: string;
  assetId: string;
  jobId?: string;
  parentVersionId?: string;
  kind: string;
  operation: string;
  parameters: Record<string, unknown>;
  status: string;
  isSelected: boolean;
  mediaUrl?: string;
  createdAt: string;
}

export interface ShotAdjust extends Record<string, unknown> {
  filterPreset?: string;
  brightness?: number;
  contrast?: number;
  saturation?: number;
}

export interface ShotAudioSettings extends Record<string, unknown> {
  originalVolume?: number;
  backgroundMusic?: ScopeAssetReference | null;
  soundEffects?: ScopeAssetReference[];
}

export interface ShotSubtitleSettings extends Record<string, unknown> {
  position?: "top" | "center" | "bottom";
  fontSize?: number;
  color?: string;
}

export interface ShotTransition extends Record<string, unknown> {
  type?: string;
  durationMs?: number;
}

export interface ShotMotion extends Record<string, unknown> {
  type?: string;
  strength?: number;
}

export interface Shot {
  id?: string;
  index: number;
  description: string;
  status: string;
  visualMode?: string;
  assetId?: string;
  segmentId?: string;
  selectedMediaVersionId?: string;
  sourceStartMs: number;
  sourceEndMs: number;
  durationMs: number;
  locked: boolean;
  transform: Record<string, unknown>;
  adjust: ShotAdjust;
  audioSettings: ShotAudioSettings;
  subtitleSettings: ShotSubtitleSettings;
  transition: ShotTransition;
  motion: ShotMotion;
  subtitleText: string;
  subtitleOverridden: boolean;
  subtitleSourceRevision: number;
  subtitleOutdated: boolean;
  notes: string;
  sketchData?: string;
  revision: number;
  candidates: Candidate[];
  mediaVersions: ShotMediaVersion[];
}

export interface Scene {
  id?: string;
  index: number;
  outline: string;
  narrationText: string;
  intent: string;
  status: string;
  estimatedDurationMs: number;
  notes: string;
  revision: number;
  shots: Shot[];
}

export interface ProjectDocumentSettings {
  title: string;
  summary: string;
  status: string;
  targetDurationSeconds: number | null;
  estimatedDurationSeconds: number;
  sourceType: string;
  visualConfig: Record<string, unknown>;
  aspectRatio: AspectRatio;
  resolution: string;
  fps: number;
  visualSettings: Record<string, unknown>;
  globalAudio: ProjectAudioMix;
  globalOverlays: unknown[];
}

export interface ProjectAudioMix extends Record<string, unknown> {
  voiceAssetId?: string;
  musicAssetId?: string;
  voiceVolume?: number;
  musicVolume?: number;
  originalVolume?: number;
  voiceMuted?: boolean;
  musicMuted?: boolean;
  duckingEnabled?: boolean;
}

export interface ScopeAssetReference extends Record<string, unknown> {
  id?: string;
  assetId: string;
  volume?: number;
  loop?: boolean;
  enabled?: boolean;
  opacity?: number;
  blendMode?: string;
  fitMode?: "cover" | "contain";
  atMs?: number;
}

export interface GlobalScopeLayers extends Record<string, unknown> {
  backgroundMusic?: ScopeAssetReference | null;
  soundEffects?: ScopeAssetReference[];
  visualAssets?: ScopeAssetReference[];
}

export interface VisualLayerItem extends ScopeAssetReference {
  scope?: "film" | "scene";
  sceneId?: string;
  startMs?: number;
  durationMs?: number;
}

export interface TimelineItem {
  id: string;
  shotId?: string;
  sceneId?: string;
  assetId?: string;
  mediaType: "image" | "video" | "audio" | "gap";
  startMs: number;
  durationMs: number;
  sourceStartMs: number;
  sourceEndMs: number;
}

export interface TimelineTrack {
  id: string;
  kind: "video" | "audio" | "overlay";
  role: string;
  items: TimelineItem[];
}

export interface ProjectDocument {
  id: string;
  schemaVersion: number;
  revision: number;
  settings: ProjectDocumentSettings;
  storyboard: { scenes: Scene[] };
  timeline: { durationMs: number; tracks: TimelineTrack[] };
  visualLayers: { items: VisualLayerItem[] };
  globalScopes: { film: GlobalScopeLayers; scenes: Record<string, GlobalScopeLayers> };
  workflowGraph: { nodes: unknown[]; edges: unknown[] };
  renderSettings: Record<string, unknown>;
  currentRenderAssetId?: string;
}

export interface Workspace {
  project: Project;
  document: ProjectDocument;
  linkedAssets: Asset[];
}

export interface ProjectCreateInput {
  name: string;
  type: string;
  description: string;
  variant?: string;
  scriptTitle?: string;
  aspectRatio?: AspectRatio;
  targetDurationSeconds?: number;
  idempotencyKey?: string;
}

export interface ProjectUpdateInput {
  name?: string;
  type?: string;
  description?: string;
  status?: ProjectStatus;
}

export interface ProjectListParams {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface DashboardSummary {
  projectCount: number;
  assetCount: number;
  linkedAssetCount: number;
  queuedJobCount: number;
  runningJobCount: number;
  pausedJobCount: number;
  completedJobCount: number;
  failedJobCount: number;
}

export interface DeleteMutation {
  workspace: Workspace;
  undoToken: string;
  undoExpiresAt: string;
}

export interface ProjectRevision {
  id: string;
  revision: number;
  reason: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

interface RawProject {
  id: string;
  name: string;
  initial: string;
  type: string;
  description: string;
  status: ProjectStatus;
  variant: string;
  cover_asset_id: string | null;
  master_output_asset_id: string | null;
  cover_media_type: "image" | "video" | "audio" | null;
  cover_media_url: string | null;
  cover_thumbnail_url: string | null;
  asset_count: number;
  scene_count: number;
  shot_count: number;
  duration_ms: number;
  aspect_ratio: AspectRatio;
  matched_percent: number;
  active_job_count: number;
  updated_at: string;
  created_at: string;
}

interface RawCandidate {
  id: string;
  segment_id: string | null;
  title: string;
  source: string;
  range_start_ms: number;
  range_end_ms: number;
  score: number;
  reason: string;
  low_confidence: boolean;
}

interface RawMediaVersion {
  id: string;
  asset_id: string;
  job_id: string | null;
  parent_version_id: string | null;
  kind: string;
  operation: string;
  parameters: Record<string, unknown>;
  status: string;
  is_selected: boolean;
  media_url: string | null;
  created_at: string;
}

interface RawShot {
  id: string | null;
  index: number;
  description: string;
  status: string;
  visual_mode: string | null;
  asset_id: string | null;
  segment_id: string | null;
  selected_media_version_id: string | null;
  source_start_ms: number;
  source_end_ms: number;
  duration_ms: number;
  locked: boolean;
  transform: Record<string, unknown>;
  adjust: Record<string, unknown>;
  audio_settings: Record<string, unknown>;
  subtitle_settings: Record<string, unknown>;
  transition: Record<string, unknown>;
  motion: Record<string, unknown>;
  subtitle_text: string;
  subtitle_overridden: boolean;
  subtitle_source_revision: number;
  subtitle_outdated: boolean;
  notes: string;
  sketch_data: string | null;
  revision: number;
  candidates: RawCandidate[];
  media_versions: RawMediaVersion[];
}

interface RawScene {
  id: string | null;
  index: number;
  outline: string;
  narration_text: string;
  intent: string;
  status: string;
  estimated_duration_ms: number;
  notes: string;
  revision: number;
  shots: RawShot[];
}

interface RawDocumentSettings {
  title: string;
  summary: string;
  status: string;
  target_duration_seconds: number | null;
  estimated_duration_seconds: number;
  source_type: string;
  visual_config: Record<string, unknown>;
  aspect_ratio: AspectRatio;
  resolution: string;
  fps: number;
  visual_settings: Record<string, unknown>;
  global_audio: Record<string, unknown>;
  global_overlays: unknown[];
}

interface RawProjectDocument {
  id: string;
  schema_version: number;
  revision: number;
  settings: RawDocumentSettings;
  storyboard: { scenes: RawScene[] };
  timeline: { duration_ms: number; tracks: TimelineTrack[] };
  visual_layers: { items: VisualLayerItem[] };
  global_scopes: { film: GlobalScopeLayers; scenes: Record<string, GlobalScopeLayers> };
  workflow_graph: { nodes: unknown[]; edges: unknown[] };
  render_settings: Record<string, unknown>;
  current_render_asset_id: string | null;
}

interface RawWorkspace {
  project: RawProject;
  document: RawProjectDocument;
  linked_assets: RawAsset[];
}

function mapProject(raw: RawProject): Project {
  return {
    id: raw.id,
    name: raw.name,
    initial: raw.initial,
    type: raw.type,
    description: raw.description,
    status: raw.status,
    variant: raw.variant,
    coverAssetId: raw.cover_asset_id ?? undefined,
    masterOutputAssetId: raw.master_output_asset_id ?? undefined,
    coverMediaType: raw.cover_media_type ?? undefined,
    coverMediaUrl: raw.cover_media_url ?? undefined,
    coverThumbnailUrl: raw.cover_thumbnail_url ?? undefined,
    assetCount: raw.asset_count,
    sceneCount: raw.scene_count,
    shotCount: raw.shot_count,
    durationMs: raw.duration_ms ?? 0,
    aspectRatio: raw.aspect_ratio ?? "16:9",
    matchedPercent: raw.matched_percent ?? 0,
    activeJobCount: raw.active_job_count,
    updatedAt: formatRelativeTime(raw.updated_at),
    updatedAtIso: raw.updated_at,
    createdAt: raw.created_at,
  };
}

function mapShot(raw: RawShot): Shot {
  return {
    id: raw.id ?? undefined,
    index: raw.index,
    description: raw.description,
    status: raw.status,
    visualMode: raw.visual_mode ?? undefined,
    assetId: raw.asset_id ?? undefined,
    segmentId: raw.segment_id ?? undefined,
    selectedMediaVersionId: raw.selected_media_version_id ?? undefined,
    sourceStartMs: raw.source_start_ms,
    sourceEndMs: raw.source_end_ms,
    durationMs: raw.duration_ms,
    locked: raw.locked,
    transform: raw.transform ?? {},
    adjust: raw.adjust ?? {},
    audioSettings: raw.audio_settings ?? {},
    subtitleSettings: raw.subtitle_settings ?? {},
    transition: raw.transition ?? {},
    motion: raw.motion ?? {},
    subtitleText: raw.subtitle_text,
    subtitleOverridden: raw.subtitle_overridden,
    subtitleSourceRevision: raw.subtitle_source_revision,
    subtitleOutdated: raw.subtitle_outdated,
    notes: raw.notes,
    sketchData: raw.sketch_data ?? undefined,
    revision: raw.revision,
    candidates: (raw.candidates ?? []).map((item) => ({
      id: item.id,
      segmentId: item.segment_id ?? undefined,
      title: item.title,
      source: item.source,
      rangeStartMs: item.range_start_ms,
      rangeEndMs: item.range_end_ms,
      score: item.score,
      reason: item.reason,
      lowConfidence: item.low_confidence,
    })),
    mediaVersions: (raw.media_versions ?? []).map((item) => ({
      id: item.id,
      assetId: item.asset_id,
      jobId: item.job_id ?? undefined,
      parentVersionId: item.parent_version_id ?? undefined,
      kind: item.kind,
      operation: item.operation,
      parameters: item.parameters ?? {},
      status: item.status,
      isSelected: item.is_selected,
      mediaUrl: item.media_url ?? undefined,
      createdAt: item.created_at,
    })),
  };
}

function mapWorkspace(raw: RawWorkspace): Workspace {
  const document = raw.document;
  return {
    project: mapProject(raw.project),
    document: {
      id: document.id,
      schemaVersion: document.schema_version,
      revision: document.revision,
      settings: {
        title: document.settings.title,
        summary: document.settings.summary,
        status: document.settings.status,
        targetDurationSeconds: document.settings.target_duration_seconds,
        estimatedDurationSeconds: document.settings.estimated_duration_seconds,
        sourceType: document.settings.source_type,
        visualConfig: document.settings.visual_config ?? {},
        aspectRatio: document.settings.aspect_ratio,
        resolution: document.settings.resolution,
        fps: document.settings.fps,
        visualSettings: document.settings.visual_settings ?? {},
        globalAudio: document.settings.global_audio ?? {},
        globalOverlays: document.settings.global_overlays ?? [],
      },
      storyboard: {
        scenes: (document.storyboard?.scenes ?? []).map((scene) => ({
          id: scene.id ?? undefined,
          index: scene.index,
          outline: scene.outline,
          narrationText: scene.narration_text,
          intent: scene.intent,
          status: scene.status,
          estimatedDurationMs: scene.estimated_duration_ms,
          notes: scene.notes,
          revision: scene.revision,
          shots: (scene.shots ?? []).map(mapShot),
        })),
      },
      timeline: {
        durationMs: document.timeline?.duration_ms ?? 0,
        tracks: document.timeline?.tracks ?? [],
      },
      visualLayers: { items: document.visual_layers?.items ?? [] },
      globalScopes: {
        film: document.global_scopes?.film ?? {},
        scenes: document.global_scopes?.scenes ?? {},
      },
      workflowGraph: {
        nodes: document.workflow_graph?.nodes ?? [],
        edges: document.workflow_graph?.edges ?? [],
      },
      renderSettings: document.render_settings ?? {},
      currentRenderAssetId: document.current_render_asset_id ?? undefined,
    },
    linkedAssets: (raw.linked_assets ?? []).map(mapAsset),
  };
}

function rawShot(shot: Shot) {
  return {
    id: shot.id ?? null,
    index: shot.index,
    description: shot.description,
    status: shot.status,
    visual_mode: shot.visualMode ?? null,
    asset_id: shot.assetId ?? null,
    segment_id: shot.segmentId ?? null,
    selected_media_version_id: shot.selectedMediaVersionId ?? null,
    source_start_ms: shot.sourceStartMs,
    source_end_ms: shot.sourceEndMs,
    duration_ms: shot.durationMs,
    locked: shot.locked,
    transform: shot.transform,
    adjust: shot.adjust,
    audio_settings: shot.audioSettings,
    subtitle_settings: shot.subtitleSettings,
    transition: shot.transition,
    motion: shot.motion,
    subtitle_text: shot.subtitleText,
    subtitle_overridden: shot.subtitleOverridden,
    subtitle_source_revision: shot.subtitleSourceRevision,
    subtitle_outdated: shot.subtitleOutdated,
    notes: shot.notes,
    sketch_data: shot.sketchData ?? null,
    revision: shot.revision,
    candidates: shot.candidates.map((item) => ({
      id: item.id,
      segment_id: item.segmentId ?? null,
      title: item.title,
      source: item.source,
      range_start_ms: item.rangeStartMs,
      range_end_ms: item.rangeEndMs,
      score: item.score,
      reason: item.reason,
      low_confidence: item.lowConfidence,
    })),
    media_versions: shot.mediaVersions.map((item) => ({
      id: item.id,
      asset_id: item.assetId,
      job_id: item.jobId ?? null,
      parent_version_id: item.parentVersionId ?? null,
      kind: item.kind,
      operation: item.operation,
      parameters: item.parameters,
      status: item.status,
      is_selected: item.isSelected,
      media_url: item.mediaUrl ?? null,
      created_at: item.createdAt,
    })),
  };
}

function rawWorkspace(workspace: Workspace, reason: "autosave" | "manual_save" | "before_ai_operation") {
  return {
    expected_revision: workspace.document.revision,
    project: {
      name: workspace.project.name,
      type: workspace.project.type,
      description: workspace.project.description,
      status: workspace.project.status,
    },
    document: {
      id: workspace.document.id,
      schema_version: workspace.document.schemaVersion,
      revision: workspace.document.revision,
      settings: {
        title: workspace.document.settings.title,
        summary: workspace.document.settings.summary,
        status: workspace.document.settings.status,
        target_duration_seconds: workspace.document.settings.targetDurationSeconds,
        estimated_duration_seconds: workspace.document.settings.estimatedDurationSeconds,
        source_type: workspace.document.settings.sourceType,
        visual_config: workspace.document.settings.visualConfig,
        aspect_ratio: workspace.document.settings.aspectRatio,
        resolution: workspace.document.settings.resolution,
        fps: workspace.document.settings.fps,
        visual_settings: workspace.document.settings.visualSettings,
        global_audio: workspace.document.settings.globalAudio,
        global_overlays: workspace.document.settings.globalOverlays,
      },
      storyboard: {
        scenes: workspace.document.storyboard.scenes.map((scene) => ({
          id: scene.id ?? null,
          index: scene.index,
          outline: scene.outline,
          narration_text: scene.narrationText,
          intent: scene.intent,
          status: scene.status,
          estimated_duration_ms: scene.estimatedDurationMs,
          notes: scene.notes,
          revision: scene.revision,
          shots: scene.shots.map(rawShot),
        })),
      },
      timeline: {
        duration_ms: workspace.document.timeline.durationMs,
        tracks: workspace.document.timeline.tracks,
      },
      visual_layers: workspace.document.visualLayers,
      global_scopes: workspace.document.globalScopes,
      workflow_graph: workspace.document.workflowGraph,
      render_settings: workspace.document.renderSettings,
      current_render_asset_id: workspace.document.currentRenderAssetId ?? null,
    },
    reason,
  };
}

export async function list(params: ProjectListParams = {}): Promise<{ items: Project[]; total: number }> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));
  const raw = await http.get<{ items: RawProject[]; total: number }>(`/projects?${query}`);
  return { items: raw.items.map(mapProject), total: raw.total };
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const raw = await http.get<Record<string, number>>("/projects/dashboard-summary");
  return {
    projectCount: raw.project_count ?? 0,
    assetCount: raw.asset_count ?? 0,
    linkedAssetCount: raw.linked_asset_count ?? 0,
    queuedJobCount: raw.queued_job_count ?? 0,
    runningJobCount: raw.running_job_count ?? 0,
    pausedJobCount: raw.paused_job_count ?? 0,
    completedJobCount: raw.completed_job_count ?? 0,
    failedJobCount: raw.failed_job_count ?? 0,
  };
}

export async function create(data: ProjectCreateInput): Promise<Workspace> {
  const idempotencyKey = data.idempotencyKey ?? temporaryId("project-request");
  const raw = await http.post<RawWorkspace>(
    "/projects",
    {
      name: data.name,
      type: data.type,
      description: data.description,
      variant: data.variant ?? "stage",
      script_title: data.scriptTitle ?? data.name,
      aspect_ratio: data.aspectRatio ?? "16:9",
      target_duration_seconds: data.targetDurationSeconds ?? 0,
    },
    { headers: { "Idempotency-Key": idempotencyKey } },
  );
  return mapWorkspace(raw);
}

export async function get(id: string): Promise<Project> {
  return mapProject(await http.get<RawProject>(`/projects/${id}`));
}

export async function getWorkspace(id: string): Promise<Workspace> {
  return mapWorkspace(await http.get<RawWorkspace>(`/projects/${id}/workspace`));
}

export async function saveWorkspace(
  id: string,
  workspace: Workspace,
  reason: "autosave" | "manual_save" | "before_ai_operation" = "autosave",
): Promise<Workspace> {
  return mapWorkspace(
    await http.patch<RawWorkspace>(`/projects/${id}/workspace`, rawWorkspace(workspace, reason)),
  );
}

export async function update(id: string, data: ProjectUpdateInput): Promise<Project> {
  return mapProject(await http.patch<RawProject>(`/projects/${id}`, data));
}

export async function linkAsset(projectId: string, assetId: string, role = "source"): Promise<Asset> {
  return mapAsset(
    await http.post<RawAsset>(`/projects/${projectId}/assets/${assetId}`, { role }),
  );
}

export function unlinkAsset(projectId: string, assetId: string, role?: string): Promise<void> {
  const query = role ? `?role=${encodeURIComponent(role)}` : "";
  return http.delete<void>(`/projects/${projectId}/assets/${assetId}${query}`);
}

function mapDeleteMutation(raw: { workspace: RawWorkspace; undo_token: string; undo_expires_at: string }): DeleteMutation {
  return {
    workspace: mapWorkspace(raw.workspace),
    undoToken: raw.undo_token,
    undoExpiresAt: raw.undo_expires_at,
  };
}

export async function deleteScene(projectId: string, sceneId: string, revision: number): Promise<DeleteMutation> {
  const raw = await http.delete<{ workspace: RawWorkspace; undo_token: string; undo_expires_at: string }>(
    `/projects/${projectId}/scenes/${sceneId}?expected_revision=${revision}&confirmed=true`,
  );
  return mapDeleteMutation(raw);
}

export async function deleteShot(projectId: string, shotId: string, revision: number): Promise<DeleteMutation> {
  const raw = await http.delete<{ workspace: RawWorkspace; undo_token: string; undo_expires_at: string }>(
    `/projects/${projectId}/shots/${shotId}?expected_revision=${revision}&confirmed=true`,
  );
  return mapDeleteMutation(raw);
}

export async function undo(projectId: string, token: string): Promise<Workspace> {
  return mapWorkspace(await http.post<RawWorkspace>(`/projects/${projectId}/undo`, { token }));
}

export async function listRevisions(projectId: string): Promise<ProjectRevision[]> {
  const raw = await http.get<Array<{ id: string; revision: number; reason: string; metadata: Record<string, unknown>; created_at: string }>>(
    `/projects/${projectId}/revisions`,
  );
  return raw.map((item) => ({ ...item, createdAt: item.created_at }));
}

export function remove(id: string): Promise<void> {
  return http.delete<void>(`/projects/${id}?confirmed=true`);
}

export { mapProject, mapWorkspace };
