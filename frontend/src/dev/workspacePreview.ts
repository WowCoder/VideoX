import type { Workspace } from "@/api/projects";

export function workspacePreviewFixture(): Workspace {
  const now = "2026-08-18T10:00:00Z";
  return {
    project: {
      id: "__preview__",
      name: "VideoX 产品发布片",
      initial: "V",
      type: "AI 科技 / 产品讲解",
      description: "工作台视觉验收数据",
      status: "editing",
      variant: "stage",
      assetCount: 4,
      sceneCount: 2,
      shotCount: 4,
      durationMs: 28000,
      aspectRatio: "16:9",
      matchedPercent: 75,
      activeJobCount: 0,
      updatedAt: "刚刚",
      updatedAtIso: now,
      createdAt: now,
    },
    document: {
      id: "document-preview",
      schemaVersion: 1,
      revision: 7,
      settings: {
        title: "VideoX 产品发布片",
        summary: "",
        status: "editing",
        targetDurationSeconds: 30,
        estimatedDurationSeconds: 28,
        sourceType: "blank",
        visualConfig: {},
        aspectRatio: "16:9",
        resolution: "1920x1080",
        fps: 25,
        visualSettings: {},
        globalAudio: { voiceVolume: 100, musicVolume: 24, originalVolume: 30, duckingEnabled: true },
        globalOverlays: [],
      },
      storyboard: {
        scenes: [
          {
            id: "scene-preview-1", index: 0, outline: "问题与机会", narrationText: "创作工具很多，但素材、脚本和剪辑仍然彼此割裂。", intent: "建立痛点", status: "editing", estimatedDurationMs: 14000, notes: "", revision: 1,
            shots: [
              { id: "shot-preview-1", index: 0, description: "创作者在多个窗口之间来回切换", status: "ready", visualMode: "video", assetId: "asset-preview-video", sourceStartMs: 0, sourceEndMs: 7000, durationMs: 7000, locked: false, transform: {}, adjust: { filterPreset: "cinematic", contrast: 8 }, audioSettings: { originalVolume: 45 }, subtitleSettings: { position: "bottom", fontSize: 17 }, transition: { type: "dissolve", durationMs: 800 }, motion: { type: "push", strength: 35 }, subtitleText: "创作工具很多，但流程仍然彼此割裂。", subtitleOverridden: false, subtitleSourceRevision: 1, subtitleOutdated: false, notes: "", revision: 1, candidates: [{ id: "candidate-preview-1", segmentId: "segment-preview-video", title: "多窗口工作流片段", source: "多窗口创作.mp4", rangeStartMs: 1000, rangeEndMs: 8000, score: 92, reason: "与镜头描述和旁白语义高度一致", lowConfidence: false }], mediaVersions: [{ id: "media-version-preview-1", assetId: "asset-preview-generated", kind: "generated_video", operation: "智能重构图", parameters: { source_snapshot: { asset_id: "asset-preview-video", visual_mode: "video", source_start_ms: 0, source_end_ms: 7000, transform: {}, adjust: { filterPreset: "cinematic", contrast: 8 }, motion: { type: "push", strength: 35 } } }, status: "ready", isSelected: false, createdAt: now }] },
              { id: "shot-preview-2", index: 1, description: "素材散落在不同目录的俯视画面", status: "editing", sourceStartMs: 0, sourceEndMs: 7000, durationMs: 7000, locked: false, transform: {}, adjust: { saturation: -18 }, audioSettings: {}, subtitleSettings: { position: "center", fontSize: 16 }, transition: { type: "slide-left", durationMs: 600 }, motion: { type: "pan-left", strength: 30 }, subtitleText: "素材、脚本和剪辑无法共享上下文。", subtitleOverridden: true, subtitleSourceRevision: 1, subtitleOutdated: false, notes: "", revision: 1, candidates: [], mediaVersions: [] },
            ],
          },
          {
            id: "scene-preview-2", index: 1, outline: "统一创作工作台", narrationText: "VideoX 让脚本、素材、时间线与 AI 围绕同一支影片协作。", intent: "展示方案", status: "editing", estimatedDurationMs: 14000, notes: "", revision: 1,
            shots: [
              { id: "shot-preview-3", index: 0, description: "统一工作台界面由远及近", status: "ready", visualMode: "image", assetId: "asset-preview-image", sourceStartMs: 0, sourceEndMs: 8000, durationMs: 8000, locked: false, transform: {}, adjust: { filterPreset: "vivid", brightness: 4 }, audioSettings: {}, subtitleSettings: { position: "bottom", fontSize: 17 }, transition: { type: "zoom", durationMs: 700 }, motion: { type: "pull", strength: 25 }, subtitleText: "一支影片，一份可以持续演进的项目文档。", subtitleOverridden: true, subtitleSourceRevision: 1, subtitleOutdated: false, notes: "", revision: 1, candidates: [], mediaVersions: [] },
              { id: "shot-preview-4", index: 1, description: "品牌标志与产品口号收尾", status: "editing", sourceStartMs: 0, sourceEndMs: 6000, durationMs: 6000, locked: false, transform: {}, adjust: {}, audioSettings: {}, subtitleSettings: {}, transition: {}, motion: {}, subtitleText: "VideoX，让创作真正连成一体。", subtitleOverridden: true, subtitleSourceRevision: 1, subtitleOutdated: false, notes: "", revision: 1, candidates: [], mediaVersions: [] },
            ],
          },
        ],
      },
      timeline: { durationMs: 28000, tracks: [] },
      visualLayers: { items: [] },
      globalScopes: { film: { backgroundMusic: null, soundEffects: [], visualAssets: [] }, scenes: {} },
      workflowGraph: { nodes: [], edges: [] },
      renderSettings: {},
    },
    linkedAssets: [
      { id: "asset-preview-video", ownerId: "preview", name: "多窗口创作.mp4", mediaType: "video", sourceType: "upload", sourceCategory: "non-ai", contentTypes: ["scene", "event"], status: "ready", processingStatus: "ready", durationMs: 12000, hasAudio: true, fileSizeMb: 12, tags: ["工作流"], recognition: {}, metadata: {}, projectIds: ["__preview__"], segments: [{ id: "segment-preview-video", assetId: "asset-preview-video", startMs: 1000, endMs: 8000, durationMs: 7000, title: "多窗口工作流片段", transcript: "", ocrText: "", tags: ["工作流"], recognition: {}, qualityScore: 92 }], createdAt: now, updatedAt: now, createdAtRelative: "刚刚" },
      { id: "asset-preview-image", ownerId: "preview", name: "统一工作台.png", mediaType: "image", sourceType: "upload", sourceCategory: "non-ai", contentTypes: ["object"], status: "ready", processingStatus: "ready", durationMs: 0, hasAudio: false, fileSizeMb: 2, tags: ["产品"], recognition: {}, metadata: {}, projectIds: ["__preview__"], segments: [], createdAt: now, updatedAt: now, createdAtRelative: "刚刚" },
      { id: "asset-preview-music", ownerId: "preview", name: "科技品牌配乐.wav", mediaType: "audio", sourceType: "upload", sourceCategory: "non-ai", contentTypes: [], status: "ready", processingStatus: "ready", durationMs: 30000, hasAudio: true, fileSizeMb: 8, tags: ["音乐"], recognition: {}, metadata: { purpose: "music" }, projectIds: ["__preview__"], segments: [], createdAt: now, updatedAt: now, createdAtRelative: "刚刚" },
      { id: "asset-preview-generated", ownerId: "preview", name: "智能重构图版本.mp4", mediaType: "video", sourceType: "ai_generated", sourceCategory: "ai", contentTypes: ["scene"], status: "ready", processingStatus: "ready", durationMs: 7000, hasAudio: false, fileSizeMb: 7, tags: ["AI 处理"], recognition: {}, metadata: {}, projectIds: ["__preview__"], segments: [], createdAt: now, updatedAt: now, createdAtRelative: "刚刚" },
    ],
  };
}
