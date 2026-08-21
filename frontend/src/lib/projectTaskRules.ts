import type { Job, JobStatus } from "@/types/models";

export type ProjectTaskFilter = "all" | "running" | "succeeded" | "failed" | "paused";

export function taskIsRunning(status: JobStatus): boolean {
  return status === "QUEUED" || status === "RUNNING";
}

export function taskCanDelete(status: JobStatus): boolean {
  return !taskIsRunning(status);
}

export function taskCanDownload(type: string, status: JobStatus): boolean {
  return type === "导出" && status === "SUCCEEDED";
}

export function latestTaskIsFailed(tasks: Array<Pick<Job, "status" | "createdAt" | "updatedAt">>): boolean {
  const latest = tasks.reduce<(typeof tasks)[number] | undefined>((current, task) => {
    if (!current) return task;
    const currentTime = Date.parse(current.updatedAt || current.createdAt);
    const taskTime = Date.parse(task.updatedAt || task.createdAt);
    return (Number.isNaN(taskTime) ? -1 : taskTime) > (Number.isNaN(currentTime) ? -1 : currentTime) ? task : current;
  }, undefined);
  return latest?.status === "FAILED";
}

export function taskMatchesFilter(status: JobStatus, filter: ProjectTaskFilter): boolean {
  if (filter === "running") return taskIsRunning(status);
  if (filter === "succeeded") return status === "SUCCEEDED";
  if (filter === "failed") return status === "FAILED";
  if (filter === "paused") return status === "PAUSED";
  return true;
}
