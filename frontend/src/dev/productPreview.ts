import type { Asset } from "@/api/assets";
import type { InspirationRun, InspirationTask } from "@/api/inspiration";
import type { Project } from "@/api/projects";

const now = new Date().toISOString();

export const previewProjects: Project[] = [
  {
    id: "preview-project-1", name: "AI 创作工作流", initial: "A", type: "品牌内容", description: "产品功能短片",
    status: "editing", variant: "default", assetCount: 6, sceneCount: 2, shotCount: 4, durationMs: 31000,
    aspectRatio: "16:9", matchedPercent: 75, activeJobCount: 0, updatedAt: "刚刚", updatedAtIso: now, createdAt: now,
  },
  {
    id: "preview-project-2", name: "城市漫游短片", initial: "城", type: "旅行短片", description: "周末城市故事",
    status: "draft", variant: "default", assetCount: 3, sceneCount: 1, shotCount: 3, durationMs: 24000,
    aspectRatio: "9:16", matchedPercent: 40, activeJobCount: 0, updatedAt: "2 小时前", updatedAtIso: now, createdAt: now,
  },
];

function asset(
  id: string,
  name: string,
  mediaType: Asset["mediaType"],
  sourceCategory: Asset["sourceCategory"],
  contentTypes: Asset["contentTypes"],
  projectIds: string[],
  durationMs = 8000,
): Asset {
  return {
    id, ownerId: "preview-user", name, mediaType,
    sourceType: sourceCategory === "ai" ? "ai_generated" : "upload",
    sourceCategory, contentTypes, status: "ready", processingStatus: "可搜索",
    durationMs: mediaType === "image" ? 0 : durationMs, hasAudio: mediaType !== "image",
    fileSizeMb: mediaType === "image" ? 2.4 : mediaType === "audio" ? 8.7 : 18.6,
    tags: contentTypes.map((type) => ({ scene: "场景", role: "角色", object: "物品", event: "事件" })[type]),
    recognition: {}, metadata: {}, projectIds, segments: [], createdAt: now, updatedAt: now, createdAtRelative: "刚刚",
  };
}

export const previewAssets: Asset[] = [
  asset("preview-asset-1", "未来实验室 · 主视觉.mp4", "video", "ai", ["scene", "object"], ["preview-project-1"], 12000),
  asset("preview-asset-2", "创作者操作多窗口.mp4", "video", "non-ai", ["role", "event"], ["preview-project-1"], 9000),
  asset("preview-asset-3", "产品界面统一工作台.png", "image", "non-ai", ["object"], ["preview-project-1"]),
  asset("preview-asset-4", "霓虹城市入口.mp4", "video", "ai", ["scene", "event"], ["preview-project-2"], 7000),
  asset("preview-asset-5", "科技品牌配乐.wav", "audio", "non-ai", [], ["preview-project-1"], 31000),
  asset("preview-asset-6", "周末市场人物特写.mp4", "video", "non-ai", ["role", "scene", "event"], ["preview-project-2"], 11000),
];

export const previewInspirationTasks: InspirationTask[] = [
  {
    id: "preview-topic-task", name: "AI 视频创作选题", taskType: "topic-recommendation",
    topicBrief: "AI 视频创作与工具更新", topicCount: 5,
    discoveryConfig: { sourceStrategy: "preferred", monitorBrief: "", searchRecencyDays: 7 },
    schedule: { type: "daily", time: "09:00", weekday: 1, timeZone: "Asia/Shanghai" },
    outputFormat: "联网选题 + 真实参考外链", enabled: true,
    nextRunAt: new Date(Date.now() + 18 * 60 * 60 * 1000).toISOString(), lastRunAt: now,
    createdAt: now, updatedAt: now,
    sources: [
      { id: "preview-source-1", sourceType: "web", url: "https://openai.com/news/", enabled: true, consecutiveFailures: 0 },
      { id: "preview-source-2", sourceType: "web", url: "https://example.com/video-news", enabled: true, consecutiveFailures: 0 },
    ],
  },
  {
    id: "preview-link-task", name: "重点产品更新动态", taskType: "link-update",
    topicBrief: "", schedule: { type: "daily", time: "18:00", weekday: 1, timeZone: "Asia/Shanghai" },
    discoveryConfig: { sourceStrategy: "only", monitorBrief: "只关注产品能力和编辑工作流变化", searchRecencyDays: 7 },
    outputFormat: "有效变化摘要 + 原文证据", enabled: true,
    nextRunAt: new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString(), lastRunAt: now,
    createdAt: now, updatedAt: now,
    sources: [
      { id: "preview-source-3", sourceType: "web", url: "https://openai.com/news/", enabled: true, consecutiveFailures: 0 },
      { id: "preview-source-4", sourceType: "web", url: "https://example.com/changelog", enabled: true, consecutiveFailures: 0 },
    ],
  },
];

export const previewInspirationRuns: Record<string, InspirationRun> = {
  "preview-topic-task": {
    id: "preview-topic-run", taskId: "preview-topic-task", status: "SUCCEEDED", outcome: "CHANGED", metrics: {}, createdAt: now, finishedAt: now,
    results: [{
      id: "preview-topic-result", title: "AI 视频创作 · 最新选题", summary: "根据两个参考来源整理了 5 个可继续创作的方向。",
      topics: [
        { id: "topic-1", order: 1, title: "多模态模型如何改变视频预演", angle: "创作效率", summary: "从脚本理解、分镜预演到镜头替换，解释新工作流的真实变化。", whyNow: "近期产品更新正在把视频预演从概念变成可测试的工作流。", hook: "以前拍完才发现脚本不成立，现在能不能在生成前就看见问题？", references: [{ label: "OpenAI News", url: "https://openai.com/news/" }] },
        { id: "topic-2", order: 2, title: "AI 视频工具进入可控编辑阶段", angle: "产品观察", summary: "比较一次性生成与可继续编辑的差异，以及创作者需要保留的判断。", references: [{ label: "Video News", url: "https://example.com/video-news" }] },
        { id: "topic-3", order: 3, title: "从素材理解到自动初剪", angle: "工作流", summary: "拆解素材识别、镜头匹配和主时间线装配。", references: [{ label: "OpenAI News", url: "https://openai.com/news/" }] },
        { id: "topic-4", order: 4, title: "可追溯来源为何成为 AI 内容底座", angle: "内容可信度", summary: "讨论外链、快照与结构化结果如何帮助创作者核查信息。", references: [{ label: "Video News", url: "https://example.com/video-news" }] },
        { id: "topic-5", order: 5, title: "创作者需要保留哪些人工判断", angle: "人机协作", summary: "从选题、镜头选择和最终节奏三个环节说明人的价值。", references: [{ label: "OpenAI News", url: "https://openai.com/news/" }] },
      ], updates: [], citations: [], createdAt: now,
    }],
  },
  "preview-link-task": {
    id: "preview-link-run", taskId: "preview-link-task", status: "SUCCEEDED", outcome: "CHANGED", metrics: {}, createdAt: now, finishedAt: now,
    results: [{
      id: "preview-link-result", title: "重点产品 · 最新动态", summary: "已检查 2 个链接并整理本轮变化。", topics: [],
      updates: [
        { id: "update-1", source: "OpenAI News", title: "产品能力与发布说明更新", summary: "页面出现新的产品说明，重点补充了创作能力和使用边界。", url: "https://openai.com/news/" },
        { id: "update-2", source: "Product Changelog", title: "编辑工作流获得新能力", summary: "本轮更新强化了结构化编辑和结果追溯。", url: "https://example.com/changelog" },
      ], citations: [], createdAt: now,
    }],
  },
};
