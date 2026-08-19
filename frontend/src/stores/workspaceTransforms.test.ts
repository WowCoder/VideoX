import assert from "node:assert/strict";
import test from "node:test";

import type { ProjectDocument, Scene, Shot } from "../api/projects.ts";
import {
  moveScene,
  removeShotAsset,
  splitShot,
  synchronizeTimeline,
  temporaryId,
} from "./workspaceTransforms.ts";

function shot(id: string, overrides: Partial<Shot> = {}): Shot {
  return {
    id,
    index: 0,
    description: `镜头 ${id}`,
    status: "editing",
    visualMode: "video",
    assetId: `asset-${id}`,
    segmentId: `segment-${id}`,
    selectedMediaVersionId: `version-${id}`,
    sourceStartMs: 0,
    sourceEndMs: 7000,
    durationMs: 7000,
    locked: false,
    transform: {},
    adjust: {},
    audioSettings: {},
    subtitleSettings: {},
    transition: {},
    motion: {},
    subtitleText: `字幕 ${id}`,
    subtitleOverridden: true,
    subtitleSourceRevision: 2,
    subtitleOutdated: false,
    notes: `备注 ${id}`,
    revision: 3,
    candidates: [],
    mediaVersions: [],
    ...overrides,
  };
}

function scene(id: string, shots: Shot[]): Scene {
  return {
    id,
    index: 0,
    outline: `场景 ${id}`,
    narrationText: `旁白 ${id}`,
    intent: "测试",
    status: "editing",
    estimatedDurationMs: shots.reduce((total, item) => total + item.durationMs, 0),
    notes: "",
    revision: 1,
    shots,
  };
}

function documentWithScenes(scenes: Scene[]): ProjectDocument {
  return {
    id: "document-1",
    schemaVersion: 1,
    revision: 1,
    settings: {
      title: "测试项目",
      summary: "",
      status: "editing",
      targetDurationSeconds: null,
      estimatedDurationSeconds: 0,
      sourceType: "manual",
      visualConfig: {},
      aspectRatio: "16:9",
      resolution: "1080p",
      fps: 25,
      visualSettings: {},
      globalAudio: {},
      globalOverlays: [],
    },
    storyboard: { scenes },
    timeline: { durationMs: 0, tracks: [] },
    visualLayers: { items: [] },
    globalScopes: { film: {}, scenes: {} },
    workflowGraph: { nodes: [], edges: [] },
    renderSettings: {},
  };
}

test("7 秒镜头在 3.5 秒处拆分且总时长不变", () => {
  const original = scene("scene-1", [shot("shot-1")]);
  const result = splitShot(original, "shot-1", 3500, () => "new-shot-split");

  assert.equal(result.splitId, "new-shot-split");
  assert.deepEqual(result.scene.shots.map((item) => item.durationMs), [3500, 3500]);
  assert.deepEqual(result.scene.shots.map((item) => [item.sourceStartMs, item.sourceEndMs]), [
    [0, 3500],
    [3500, 7000],
  ]);
  assert.equal(result.scene.shots.reduce((total, item) => total + item.durationMs, 0), 7000);
  assert.equal(original.shots.length, 1, "转换不得修改原场景");
});

test("非等长素材源区间按镜头播放比例切分", () => {
  const original = scene("scene-1", [shot("shot-1", {
    durationMs: 8000,
    sourceStartMs: 1000,
    sourceEndMs: 5000,
  })]);
  const result = splitShot(original, "shot-1", 2000, () => "new-shot-split");

  assert.deepEqual(result.scene.shots.map((item) => [item.sourceStartMs, item.sourceEndMs]), [
    [1000, 2000],
    [2000, 5000],
  ]);
  assert.deepEqual(result.scene.shots.map((item) => item.durationMs), [2000, 6000]);
});

test("拆分后的第二段解析所选媒体版本并清空版本历史", () => {
  const original = scene("scene-1", [shot("shot-1", {
    assetId: "original-asset",
    selectedMediaVersionId: "version-selected",
    mediaVersions: [{
      id: "version-selected",
      assetId: "generated-asset",
      kind: "generated",
      operation: "image-to-video",
      parameters: {},
      status: "ready",
      isSelected: true,
      createdAt: "2026-08-19T00:00:00Z",
    }],
  })]);
  const second = splitShot(original, "shot-1", 3500, () => "new-shot-split").scene.shots[1];

  assert.equal(second.assetId, "generated-asset");
  assert.equal(second.selectedMediaVersionId, undefined);
  assert.deepEqual(second.mediaVersions, []);
  assert.deepEqual(second.candidates, []);
});

test("场景移动会重建场景、镜头和主时间线顺序", () => {
  const first = scene("scene-1", [shot("shot-1", { durationMs: 1000 })]);
  const second = scene("scene-2", [
    shot("shot-2", { index: 7, durationMs: 2000 }),
    shot("shot-3", { index: 8, durationMs: 3000 }),
  ]);
  const scenes = moveScene([first, second], "scene-2", -1);
  const document = synchronizeTimeline(documentWithScenes(scenes));
  const items = document.timeline.tracks[0].items;

  assert.deepEqual(scenes.map((item) => [item.id, item.index]), [["scene-2", 0], ["scene-1", 1]]);
  assert.deepEqual(scenes[0].shots.map((item) => item.index), [0, 1]);
  assert.deepEqual(items.map((item) => [item.shotId, item.startMs]), [
    ["shot-2", 0],
    ["shot-3", 2000],
    ["shot-1", 5000],
  ]);
  assert.equal(document.timeline.durationMs, 6000);
});

test("移除素材保留叙事、字幕和镜头本身", () => {
  const original = scene("scene-1", [shot("shot-1")]);
  const result = removeShotAsset(original, "shot-1");
  const retained = result.shots[0];

  assert.equal(retained.id, "shot-1");
  assert.equal(retained.description, "镜头 shot-1");
  assert.equal(retained.subtitleText, "字幕 shot-1");
  assert.equal(retained.notes, "备注 shot-1");
  assert.equal(retained.assetId, undefined);
  assert.equal(retained.segmentId, undefined);
  assert.equal(retained.selectedMediaVersionId, undefined);
  assert.deepEqual([retained.sourceStartMs, retained.sourceEndMs], [0, 7000]);
});

test("randomUUID 缺失时临时 ID 仍可由安全随机数生成且唯一", () => {
  let sequence = 0;
  const cryptoWithoutUuid = {
    getRandomValues<T extends ArrayBufferView>(values: T): T {
      const integers = values as unknown as Uint32Array;
      integers.fill(++sequence);
      return values;
    },
  } as Crypto;

  const first = temporaryId("new-shot", cryptoWithoutUuid);
  const second = temporaryId("new-shot", cryptoWithoutUuid);
  assert.match(first, /^new-shot-[0-9a-f]{32}$/);
  assert.notEqual(first, second);
});

test("无 Web Crypto 时临时 ID 使用时间与随机数安全降级", () => {
  const first = temporaryId("new-scene", undefined, () => 1000, () => 0.25);
  const second = temporaryId("new-scene", undefined, () => 1001, () => 0.75);
  assert.match(first, /^new-scene-/);
  assert.notEqual(first, second);
});
