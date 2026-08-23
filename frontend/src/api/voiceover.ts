import { http } from "./client";

export interface VoiceOption { id: string; name: string; description: string }
export interface VoiceModelOption { id: string; name: string; description: string; voices: VoiceOption[] }
export interface VoiceTake {
  id: string; assetId: string; model: string; voiceId: string; durationMs: number;
  timeStretchRatio: number; isSelected: boolean; audioUrl?: string; createdAt: string;
}
export interface VoiceLine {
  id: string; sourceKey: string; sceneId: string; lineIndex: number; text: string; textSource: string;
  startShotId?: string; endShotId?: string;
  startMs: number; endMs: number; windowDurationMs: number; targetDurationMs: number;
  speechBudgetMs: number; pauseAfterMs: number; captionEnabled: boolean; voiceEnabled: boolean;
  status: "draft" | "generating" | "ready" | "stale" | "timing_conflict" | "failed";
  timingStatus: "pending" | "fit" | "conflict"; overflowMs: number;
  staleReasons: Array<"cue_removed" | "text_changed" | "start_changed" | "end_changed" | "source_key_changed">;
  expectedStartMs?: number; expectedEndMs?: number; expectedText?: string;
  selectedTakeId?: string; takes: VoiceTake[];
}
export interface VoiceoverWorkspace {
  enabled: boolean; provider: string; defaultModel: string; defaultVoice: string;
  models: VoiceModelOption[]; lines: VoiceLine[];
}

export function getVoiceoverWorkspace(projectId: string): Promise<VoiceoverWorkspace> {
  return http.get(`/voiceover/projects/${projectId}`);
}

export function estimateVoiceover(projectId: string, input: { source: string; model: string; sceneIds?: string[] }): Promise<{ lineCount: number; billableCharacters: number; estimatedCostYuan: number }> {
  return http.post(`/voiceover/projects/${projectId}/estimate`, {
    source: input.source,
    model: input.model,
    scene_ids: input.sceneIds ?? [],
  });
}

export function applyVoiceoverMaster(projectId: string, assetId: string, expectedRevision: number): Promise<{ assetId: string; revision: number; applied: boolean }> {
  return http.post(`/voiceover/projects/${projectId}/apply-master`, {
    asset_id: assetId,
    expected_revision: expectedRevision,
  });
}
