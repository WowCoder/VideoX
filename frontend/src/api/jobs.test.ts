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
