import assert from "node:assert/strict";
import test from "node:test";
import { latestTaskIsFailed, taskCanDelete, taskCanDownload, taskIsRunning, taskMatchesFilter } from "./projectTaskRules.ts";

test("排队中和运行中任务只能暂停，不能直接删除", () => {
  for (const status of ["QUEUED", "RUNNING"] as const) {
    assert.equal(taskIsRunning(status), true);
    assert.equal(taskCanDelete(status), false);
    assert.equal(taskMatchesFilter(status, "running"), true);
  }
});

test("完成、失败、暂停和取消任务可以删除", () => {
  for (const status of ["SUCCEEDED", "FAILED", "PAUSED", "CANCELLED"] as const) {
    assert.equal(taskCanDelete(status), true);
  }
});

test("任务状态筛选严格匹配进行中、已完成、已失败和已暂停", () => {
  assert.equal(taskMatchesFilter("SUCCEEDED", "succeeded"), true);
  assert.equal(taskMatchesFilter("FAILED", "failed"), true);
  assert.equal(taskMatchesFilter("PAUSED", "paused"), true);
  assert.equal(taskMatchesFilter("CANCELLED", "paused"), false);
  assert.equal(taskMatchesFilter("FAILED", "succeeded"), false);
});

test("只有已完成的导出任务可以下载成片", () => {
  assert.equal(taskCanDownload("导出", "SUCCEEDED"), true);
  assert.equal(taskCanDownload("导出", "RUNNING"), false);
  assert.equal(taskCanDownload("分镜图 AI 生视频", "SUCCEEDED"), false);
});

test("任务按钮只在时间最新的一条任务失败时提示失败", () => {
  const oldFailure = { status: "FAILED" as const, createdAt: "2026-08-20T08:00:00Z", updatedAt: "2026-08-20T08:01:00Z" };
  const latestSuccess = { status: "SUCCEEDED" as const, createdAt: "2026-08-20T09:00:00Z", updatedAt: "2026-08-20T09:05:00Z" };
  assert.equal(latestTaskIsFailed([oldFailure, latestSuccess]), false);
  assert.equal(latestTaskIsFailed([latestSuccess, { ...oldFailure, updatedAt: "2026-08-20T10:00:00Z" }]), true);
  assert.equal(latestTaskIsFailed([]), false);
});
