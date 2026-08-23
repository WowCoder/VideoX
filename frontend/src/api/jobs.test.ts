import assert from "node:assert/strict";
import test from "node:test";
import { mapJob, type RawJob } from "./jobMapper.ts";

test("任务映射保留镜头目标和更新时间，供项目任务面板定位镜头", () => {
  const raw: RawJob = {
    id: "job-video-1",
    project_id: "project-1",
    subject_type: "shot",
    subject_id: "shot-2",
    name: "分镜图 AI 生视频",
    type: "分镜图 AI 生视频",
    status: "RUNNING",
    stage: "等待结果",
    stages: ["提交生成", "等待结果", "保存素材"],
    stage_index: 1,
    progress: 46,
    detail: "正在生成镜头视频",
    eta: "预计 1 分钟",
    logs: [],
    result: null,
    result_detail: "",
    result_url: null,
    export_metadata: null,
    is_simulated: false,
    created_at: "2026-08-20T08:00:00Z",
    updated_at: "2026-08-20T08:01:00Z",
  };

  const job = mapJob(raw);

  assert.equal(job.projectId, "project-1");
  assert.equal(job.subjectType, "shot");
  assert.equal(job.subjectId, "shot-2");
  assert.equal(job.progress, 46);
  assert.equal(job.updatedAt, "2026-08-20T08:01:00Z");
});

test("任务映射保留可审核的 AI 镜头描述建议", () => {
  const raw: RawJob = {
    id: "job-review",
    project_id: "project-1",
    subject_type: "shot",
    subject_id: "shot-1",
    name: "AI 完善分镜",
    type: "AI 分镜完善",
    status: "SUCCEEDED",
    stage: "等待确认",
    stages: ["完善描述", "等待确认"],
    stage_index: 1,
    progress: 100,
    detail: "已生成建议",
    eta: "",
    logs: [],
    result: "审核建议",
    result_detail: "请确认",
    result_url: null,
    export_metadata: null,
    review_proposal: {
      type: "shot_description",
      status: "pending",
      base_revision: 9,
      items: [{
        shot_id: "shot-1",
        original_description: "原描述",
        proposed_description: "AI 建议",
      }],
    },
    is_simulated: false,
    created_at: "2026-08-22T08:00:00Z",
    updated_at: "2026-08-22T08:00:01Z",
  };
  const mapped = mapJob(raw);

  assert.deepEqual(mapped.reviewProposal, {
    type: "shot_description",
    status: "pending",
    baseRevision: 9,
    items: [{
      shotId: "shot-1",
      originalDescription: "原描述",
      proposedDescription: "AI 建议",
    }],
  });
});
