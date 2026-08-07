// ──────────────────────────────────────────────
// OpenVMA - AI 生成 API
// ──────────────────────────────────────────────

import { http } from "./client";

export interface GenerateScriptInput {
  brief: string;
  duration?: number;
  tone?: "专业克制" | "科技感" | "故事化";
  referenceDialogue?: boolean;
  projectId?: string;
}

/** 后端返回的原始脚本单元（list[dict]） */
export interface RawScriptUnit {
  outline: string;
  text: string;
  intent: string;
  duration: number;
}

export interface GenerateScriptResult {
  title: string;
  summary: string;
  units: RawScriptUnit[];
  jobId?: string;
}

export interface GenerateImageInput {
  projectId: string;
  shotId: string;
  description: string;
}

export interface GenerateJobResult {
  jobId: string;
  message: string;
}

export interface GenerationCapability {
  available: boolean;
  model: string;
  reason: string;
}

export interface GenerationCapabilities {
  image: GenerationCapability;
  imageToVideo: GenerationCapability;
  effectVideo: GenerationCapability;
}

interface RawGenerationCapabilities {
  image: GenerationCapability;
  image_to_video: GenerationCapability;
  effect_video: GenerationCapability;
}

export interface GenerateVideoInput {
  projectId: string;
  shotId: string;
  motionPrompt?: string;
}

export interface GenerateEffectInput {
  projectId: string;
  shotId: string;
  sketchData?: string;
  motionDescription?: string;
}

export interface ExportProjectInput {
  projectId: string;
  cutVersionId?: string;
  format?: "mp4" | "mov" | "prores";
  resolution?: "480p" | "720p" | "1080p" | "4k";
}

export interface ExportProjectResult {
  jobId: string;
  message: string;
}

interface RawExportProjectResult {
  job_id: string;
  message: string;
}

interface RawGenerateJobResult {
  job_id: string;
  message: string;
}

/**
 * AI 生成脚本
 * POST /api/generate/script
 *
 * 将前端 camelCase 字段映射为后端 snake_case：
 *   projectId        → project_id
 *   duration         → target_duration
 *   referenceDialogue → reference_dialogue
 */
export function generateScript(data: GenerateScriptInput): Promise<GenerateScriptResult> {
  const body = {
    project_id: data.projectId,
    brief: data.brief,
    target_duration: data.duration,
    tone: data.tone,
    reference_dialogue: data.referenceDialogue,
  };
  return http.post<GenerateScriptResult>("/generate/script", body);
}

/**
 * AI 生图分镜
 * POST /api/generate/image
 */
export async function generateImage(data: GenerateImageInput): Promise<GenerateJobResult> {
  const raw = await http.post<RawGenerateJobResult>("/generate/image", {
    project_id: data.projectId,
    shot_id: data.shotId,
    prompt: data.description,
  });
  return { jobId: raw.job_id, message: raw.message };
}

/**
 * 图生视频
 * POST /api/generate/video
 */
export async function generateVideo(data: GenerateVideoInput): Promise<GenerateJobResult> {
  const raw = await http.post<RawGenerateJobResult>("/generate/video", {
    project_id: data.projectId,
    shot_id: data.shotId,
    prompt: data.motionPrompt ?? "",
  });
  return { jobId: raw.job_id, message: raw.message };
}

/**
 * 示意特效生成
 * POST /api/generate/effect
 */
export async function generateEffect(data: GenerateEffectInput): Promise<GenerateJobResult> {
  const raw = await http.post<RawGenerateJobResult>("/generate/effect", {
    project_id: data.projectId,
    shot_id: data.shotId,
    sketch_data: data.sketchData ?? "",
    motion_description: data.motionDescription ?? "",
  });
  return { jobId: raw.job_id, message: raw.message };
}

export async function getCapabilities(): Promise<GenerationCapabilities> {
  const raw = await http.get<RawGenerationCapabilities>("/generate/capabilities");
  return {
    image: raw.image,
    imageToVideo: raw.image_to_video,
    effectVideo: raw.effect_video,
  };
}

export async function exportProject(data: ExportProjectInput): Promise<ExportProjectResult> {
  const raw = await http.post<RawExportProjectResult>("/generate/export", {
    project_id: data.projectId,
    cut_version_id: data.cutVersionId,
    format: data.format ?? "mp4",
    resolution: data.resolution ?? "1080p",
  });
  return { jobId: raw.job_id, message: raw.message };
}
