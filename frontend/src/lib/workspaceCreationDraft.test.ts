import assert from "node:assert/strict";
import test from "node:test";
import {
  createWorkspaceCreationDraft,
  deriveWorkspaceCreationTitle,
  parseWorkspaceCreationDraft,
} from "./workspaceCreationDraft.ts";

test("创建草稿会根据来源选择合理的默认成片方式", () => {
  assert.equal(createWorkspaceCreationDraft("ai-script").productionMode, "ai");
  assert.equal(createWorkspaceCreationDraft("write-script").productionMode, "ai");
  assert.equal(createWorkspaceCreationDraft("upload-assets").productionMode, "hybrid");
});

test("无效或过期草稿不会进入工作台创建流程", () => {
  assert.equal(parseWorkspaceCreationDraft(null), null);
  assert.equal(parseWorkspaceCreationDraft({ version: 2, source: "ai-script" }), null);
  assert.equal(parseWorkspaceCreationDraft({ version: 1, source: "unknown" }), null);
});

test("草稿恢复会过滤无效场景并收紧基础数值", () => {
  const restored = parseWorkspaceCreationDraft({
    ...createWorkspaceCreationDraft("ai-script"),
    durationSeconds: 9999,
    units: [
      { title: "开场", narration: "第一句。", visual: "工作台画面", durationMs: 8000, shots: [] },
      { title: "损坏数据" },
    ],
  });
  assert.equal(restored?.durationSeconds, 600);
  assert.equal(restored?.units.length, 1);
});

test("项目名称优先使用明确场景标题，否则从旁白提取", () => {
  assert.equal(deriveWorkspaceCreationTitle([
    { title: "产品开场", narration: "旁白内容。", visual: "画面", durationMs: 8000, shots: [] },
  ]), "产品开场");
  assert.equal(deriveWorkspaceCreationTitle([
    { title: "段落 1", narration: "创作者从一份文档开始。后续内容", visual: "画面", durationMs: 8000, shots: [] },
  ]), "创作者从一份文档开始");
});
