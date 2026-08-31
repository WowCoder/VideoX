import { http } from "./client";

export type InspirationTaskType = "topic-recommendation" | "link-update";
export type InspirationScheduleType = "manual" | "daily" | "weekly";
export type InspirationSourceStrategy = "web" | "preferred" | "only";

export interface InspirationDiscoveryConfig {
  sourceStrategy: InspirationSourceStrategy;
  monitorBrief: string;
  searchRecencyDays: number;
}

export interface InspirationSchedule {
  type: InspirationScheduleType;
  time: string;
  /** 浏览器 weekday：周日 0，周一 1 ... 周六 6。 */
  weekday: number;
  timeZone: "Asia/Shanghai";
}

export interface InspirationSource {
  id: string;
  sourceType: "web" | "rss";
  url: string;
  enabled: boolean;
  lastSuccessAt?: string;
  lastError?: string;
  lastStatus?: string;
  consecutiveFailures: number;
}

export interface InspirationTask {
  id: string;
  name: string;
  taskType: InspirationTaskType;
  topicBrief: string;
  topicCount?: number;
  discoveryConfig: InspirationDiscoveryConfig;
  schedule: InspirationSchedule;
  outputFormat: string;
  enabled: boolean;
  nextRunAt?: string;
  lastRunAt?: string;
  createdAt: string;
  updatedAt: string;
  sources: InspirationSource[];
}

export interface InspirationReference {
  url: string;
  label: string;
}

export interface InspirationTopic {
  id: string;
  order: number;
  title: string;
  angle: string;
  summary: string;
  whyNow?: string;
  hook?: string;
  references: InspirationReference[];
}

export interface InspirationUpdate {
  id: string;
  source: string;
  title: string;
  summary: string;
  url: string;
  changeType?: string;
  evidence?: Array<{ type?: string; title?: string; text?: string; url?: string }>;
}

export interface InspirationResult {
  id: string;
  title: string;
  summary: string;
  topics: InspirationTopic[];
  updates: InspirationUpdate[];
  citations: InspirationReference[];
  modelProvider?: string;
  modelName?: string;
  projectId?: string;
  createdAt: string;
}

export interface InspirationRun {
  id: string;
  taskId: string;
  jobId?: string;
  status: string;
  error?: string;
  outcome?: string;
  metrics: Record<string, number | string | boolean>;
  startedAt?: string;
  finishedAt?: string;
  createdAt: string;
  results: InspirationResult[];
}

export interface InspirationTaskInput {
  name: string;
  taskType: InspirationTaskType;
  topicBrief: string;
  topicCount?: number;
  discoveryConfig: InspirationDiscoveryConfig;
  schedule: InspirationSchedule;
  enabled: boolean;
  sources: Array<{ sourceType: "web" | "rss"; url: string }>;
}

interface RawTask {
  id: string;
  name: string;
  task_type: InspirationTaskType;
  topic_brief: string;
  topic_count: number | null;
  discovery_config: { source_strategy: InspirationSourceStrategy; monitor_brief: string; search_recency_days: number };
  schedule: { type: InspirationScheduleType; time: string; weekday: number; time_zone: "Asia/Shanghai" };
  output_format: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
  sources: Array<{ id: string; source_type: "web" | "rss"; url: string; enabled: boolean; last_success_at: string | null; last_error: string | null; last_status: string | null; consecutive_failures: number }>;
}

interface RawRun {
  id: string;
  task_id: string;
  job_id: string | null;
  status: string;
  error: string | null;
  outcome: string | null;
  metrics: Record<string, number | string | boolean>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  results: Array<{
    id: string;
    title: string;
    summary: string;
    content: { topics?: InspirationTopic[]; updates?: InspirationUpdate[] };
    citations: InspirationReference[];
    model_provider: string | null;
    model_name: string | null;
    project_id: string | null;
    created_at: string;
  }>;
}

function mapTask(raw: RawTask): InspirationTask {
  return {
    id: raw.id,
    name: raw.name,
    taskType: raw.task_type,
    topicBrief: raw.topic_brief,
    topicCount: raw.topic_count ?? undefined,
    discoveryConfig: {
      sourceStrategy: raw.discovery_config.source_strategy,
      monitorBrief: raw.discovery_config.monitor_brief,
      searchRecencyDays: raw.discovery_config.search_recency_days,
    },
    schedule: {
      type: raw.schedule.type,
      time: raw.schedule.time,
      weekday: raw.schedule.weekday,
      timeZone: raw.schedule.time_zone,
    },
    outputFormat: raw.output_format,
    enabled: raw.enabled,
    nextRunAt: raw.next_run_at ?? undefined,
    lastRunAt: raw.last_run_at ?? undefined,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    sources: raw.sources.map((source) => ({
      id: source.id,
      sourceType: source.source_type,
      url: source.url,
      enabled: source.enabled,
      lastSuccessAt: source.last_success_at ?? undefined,
      lastError: source.last_error ?? undefined,
      lastStatus: source.last_status ?? undefined,
      consecutiveFailures: source.consecutive_failures,
    })),
  };
}

function mapRun(raw: RawRun): InspirationRun {
  return {
    id: raw.id,
    taskId: raw.task_id,
    jobId: raw.job_id ?? undefined,
    status: raw.status,
    error: raw.error ?? undefined,
    outcome: raw.outcome ?? undefined,
    metrics: raw.metrics ?? {},
    startedAt: raw.started_at ?? undefined,
    finishedAt: raw.finished_at ?? undefined,
    createdAt: raw.created_at,
    results: raw.results.map((result) => ({
      id: result.id,
      title: result.title,
      summary: result.summary,
      topics: result.content?.topics ?? [],
      updates: result.content?.updates ?? [],
      citations: result.citations ?? [],
      modelProvider: result.model_provider ?? undefined,
      modelName: result.model_name ?? undefined,
      projectId: result.project_id ?? undefined,
      createdAt: result.created_at,
    })),
  };
}

function taskPayload(input: InspirationTaskInput) {
  return {
    name: input.name,
    task_type: input.taskType,
    topic_brief: input.taskType === "topic-recommendation" ? input.topicBrief : "",
    topic_count: input.taskType === "topic-recommendation" ? input.topicCount ?? 5 : null,
    discovery_config: {
      source_strategy: input.taskType === "link-update" ? "only" : input.discoveryConfig.sourceStrategy,
      monitor_brief: input.taskType === "link-update" ? input.discoveryConfig.monitorBrief : "",
      search_recency_days: input.discoveryConfig.searchRecencyDays,
    },
    schedule: {
      type: input.schedule.type,
      time: input.schedule.time,
      weekday: input.schedule.weekday,
      time_zone: input.schedule.timeZone,
    },
    enabled: input.enabled,
    sources: input.sources.map((source) => ({ source_type: source.sourceType, url: source.url, fetch_config: {} })),
  };
}

export async function listTasks(page = 1, pageSize = 30): Promise<{ items: InspirationTask[]; total: number }> {
  const raw = await http.get<{ items: RawTask[]; total: number }>(`/inspiration/tasks?page=${page}&page_size=${pageSize}`);
  return { items: raw.items.map(mapTask), total: raw.total };
}

export async function createTask(input: InspirationTaskInput): Promise<InspirationTask> {
  return mapTask(await http.post<RawTask>("/inspiration/tasks", taskPayload(input)));
}

export async function updateTask(id: string, input: InspirationTaskInput): Promise<InspirationTask> {
  return mapTask(await http.patch<RawTask>(`/inspiration/tasks/${id}`, taskPayload(input)));
}

export async function setTaskEnabled(id: string, enabled: boolean): Promise<InspirationTask> {
  return mapTask(await http.patch<RawTask>(`/inspiration/tasks/${id}`, { enabled }));
}

export function removeTask(id: string): Promise<void> {
  return http.delete<void>(`/inspiration/tasks/${id}?confirmed=true`);
}

export async function runTask(id: string): Promise<InspirationRun> {
  return mapRun(await http.post<RawRun>(`/inspiration/tasks/${id}/run`));
}

export async function listRuns(id: string, page = 1, pageSize = 20): Promise<{ items: InspirationRun[]; total: number }> {
  const raw = await http.get<{ items: RawRun[]; total: number }>(`/inspiration/tasks/${id}/runs?page=${page}&page_size=${pageSize}`);
  return { items: raw.items.map(mapRun), total: raw.total };
}

export async function getRun(id: string): Promise<InspirationRun> {
  return mapRun(await http.get<RawRun>(`/inspiration/runs/${id}`));
}
