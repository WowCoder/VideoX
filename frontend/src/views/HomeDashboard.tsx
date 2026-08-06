// ──────────────────────────────────────────────
// OpenVMA - 综合工作台
// 上区两列：快速开始 / 素材概览
// 下区三列网格：最近项目 / 活跃脚本 / 任务处理
// 使用 @tanstack/react-query 加载数据
// ──────────────────────────────────────────────

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@/router";
import {
  ArrowUpRight,
  Clock3,
  Download,
  FolderKanban,
  Library,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Upload,
  WandSparkles,
  XCircle,
} from "lucide-react";
import * as projectApi from "@/api/projects";
import * as scriptApi from "@/api/scripts";
import * as jobApi from "@/api/jobs";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { useScriptStore } from "@/stores/scriptStore";
import { VideoThumb } from "@/components/VideoThumb";
import type { Job } from "@/types/models";

type JobFilter = "ALL" | "ACTIVE" | "PAUSED" | "FAILED" | "SUCCEEDED";
type JobAction = "retry" | "pause" | "resume" | "cancel";

const jobActionLabels: Record<JobAction, string> = {
  retry: "任务已重新进入队列",
  pause: "任务已暂停",
  resume: "任务已恢复",
  cancel: "任务已取消",
};

const jobStatusLabels: Record<Job["status"], string> = {
  RUNNING: "处理中",
  QUEUED: "等待中",
  PAUSED: "待继续",
  SUCCEEDED: "已完成",
  FAILED: "处理失败",
  CANCELLED: "已取消",
};

const jobStatusClass: Record<Job["status"], string> = {
  RUNNING: "bg-blue-soft text-blue",
  QUEUED: "bg-canvas text-muted",
  PAUSED: "bg-amber/10 text-amber",
  SUCCEEDED: "bg-teal/10 text-teal",
  FAILED: "bg-red/10 text-red",
  CANCELLED: "bg-canvas text-muted",
};

export function HomeDashboard() {
  const navigate = useNavigate();
  const { openUploadDrawer, openScriptCreate, openAIScript, openProjectCreate, notify } = useUIStore();
  const { setCurrentProject } = useProjectStore();
  const setCurrentScriptId = useScriptStore((s) => s.setCurrentScriptId);
  const queryClient = useQueryClient();
  const [jobFilter, setJobFilter] = useState<JobFilter>("ALL");
  const [downloadingJobId, setDownloadingJobId] = useState<string | null>(null);
  const jobActionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: JobAction }) => {
      if (action === "retry") return jobApi.retry(id);
      if (action === "pause") return jobApi.pause(id);
      if (action === "resume") return jobApi.resume(id);
      return jobApi.cancel(id);
    },
    onSuccess: (_job, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      notify(jobActionLabels[variables.action]);
    },
    onError: (error) => notify(error instanceof Error ? error.message : "任务操作失败", "error"),
  });
  const downloadExport = async (job: Job) => {
    setDownloadingJobId(job.id);
    try {
      await jobApi.downloadResult(job.id);
      notify("成片下载已开始");
    } catch (error) {
      notify(error instanceof Error ? error.message : "成片下载失败", "error");
    } finally {
      setDownloadingJobId(null);
    }
  };

  // react-query 加载真实数据
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectApi.list(),
    retry: false,
  });
  const scriptsQuery = useQuery({
    queryKey: ["scripts"],
    queryFn: () => scriptApi.list(),
    retry: false,
  });
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: projectApi.getDashboardSummary,
    retry: false,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => jobApi.list({ pageSize: 100 }),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.items.some((job) => ["QUEUED", "RUNNING"].includes(job.status))
        ? 5_000
        : false,
  });

  const projects = projectsQuery.data?.items ?? [];
  const scripts = scriptsQuery.data?.items ?? [];
  const jobs = jobsQuery.data?.items ?? [];
  const summary = summaryQuery.data;
  const loadingProjects = projectsQuery.isLoading;

  const activeScripts = scripts.filter((s) => s.status !== "已完成").slice(0, 4);
  const recentProjects = projects.slice(0, 4);
  const processingCount = summary
    ? summary.runningJobCount + summary.queuedJobCount + summary.pausedJobCount
    : 0;
  const activeCount = summary ? summary.runningJobCount + summary.queuedJobCount : 0;
  const failedCount = summary?.failedJobCount ?? 0;
  const completedCount = summary?.completedJobCount ?? 0;
  const pausedCount = summary?.pausedJobCount ?? 0;
  const activity = jobs.filter((job) => {
    if (jobFilter === "ACTIVE") return job.status === "RUNNING" || job.status === "QUEUED";
    if (jobFilter === "PAUSED") return job.status === "PAUSED";
    if (jobFilter === "FAILED") return job.status === "FAILED";
    if (jobFilter === "SUCCEEDED") return job.status === "SUCCEEDED";
    return true;
  });
  const loadError = [projectsQuery, scriptsQuery, summaryQuery, jobsQuery].find((query) => query.isError)?.error;

  function openProject(projectId: string) {
    setCurrentProject(projectId);
    navigate(`/workspace/projects/${projectId}`);
  }

  function openScript(scriptId: string) {
    setCurrentScriptId(scriptId);
    navigate(`/workspace/scripts/${scriptId}/editor`);
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="text-2xl font-bold text-text">综合工作台</h1>
        <div className="mt-6 rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">工作台数据加载失败</p>
          <p className="mt-1 text-xs text-muted">{loadError instanceof Error ? loadError.message : "请检查后端服务"}</p>
          <button
            type="button"
            onClick={() => {
              void projectsQuery.refetch();
              void scriptsQuery.refetch();
              void summaryQuery.refetch();
              void jobsQuery.refetch();
            }}
            className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 页头 */}
      <section className="mb-8">
        <h1 className="text-2xl font-bold text-text">综合工作台</h1>
        <p className="mt-1.5 text-sm text-muted">
          把脚本和素材交给 AI，快速得到一版可继续替换镜头、细化剪辑并导出的初剪。
        </p>
      </section>

      {/* 上区：快速开始 + 素材概览 */}
      <div className="mb-6 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        {/* 快速开始 */}
        <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4">
            <h2 className="text-base font-semibold text-text">快速开始</h2>
            <p className="text-xs text-muted">从脚本和素材开始生成第一版初剪</p>
          </header>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={openUploadDrawer}
              className="group flex flex-col items-start gap-2 rounded-xl border border-line bg-canvas/40 p-4 text-left transition hover:border-blue/40 hover:bg-blue-soft/30"
              type="button"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-soft text-blue transition group-hover:bg-blue group-hover:text-white">
                <Upload size={20} />
              </span>
              <strong className="text-sm text-text">上传素材</strong>
              <small className="text-xs text-muted">导入视频并自动理解镜头</small>
            </button>
            <button
              onClick={() => openAIScript()}
              className="group flex flex-col items-start gap-2 rounded-xl border border-line bg-canvas/40 p-4 text-left transition hover:border-blue/40 hover:bg-blue-soft/30"
              type="button"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue to-teal text-white">
                <WandSparkles size={20} />
              </span>
              <strong className="text-sm text-text">AI 生成脚本</strong>
              <small className="text-xs text-muted">根据创作目标生成可编辑脚本</small>
            </button>
            <button
              onClick={openScriptCreate}
              className="group flex flex-col items-start gap-2 rounded-xl border border-line bg-canvas/40 p-4 text-left transition hover:border-blue/40 hover:bg-blue-soft/30"
              type="button"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-soft text-blue transition group-hover:bg-blue group-hover:text-white">
                <Plus size={20} />
              </span>
              <strong className="text-sm text-text">新建脚本</strong>
              <small className="text-xs text-muted">粘贴、上传表格或从空白开始</small>
            </button>
            <button
              onClick={openProjectCreate}
              className="group flex flex-col items-start gap-2 rounded-xl border border-line bg-canvas/40 p-4 text-left transition hover:border-blue/40 hover:bg-blue-soft/30"
              type="button"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-soft text-blue transition group-hover:bg-blue group-hover:text-white">
                <FolderKanban size={20} />
              </span>
              <strong className="text-sm text-text">新建项目</strong>
              <small className="text-xs text-muted">创建独立的素材、脚本与任务空间</small>
            </button>
          </div>
        </section>

        {/* 素材概览 */}
        <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">素材概览</h2>
            <button
              onClick={() => navigate("/workspace/library")}
              className="flex items-center gap-1 text-xs text-blue transition hover:underline"
              type="button"
            >
              查看全部<ArrowUpRight size={13} />
            </button>
          </header>
          <div className="space-y-2.5">
            <div className="flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 px-3.5 py-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-soft text-blue">
                <Library size={17} />
              </span>
              <span className="flex-1 text-sm text-text">视频素材</span>
              <strong className="text-lg font-semibold text-text">{summary?.assetCount ?? 0}</strong>
            </div>
            <div className="flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 px-3.5 py-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal/10 text-teal">
                <Sparkles size={17} />
              </span>
              <span className="flex-1 text-sm text-text">可搜索片段</span>
              <strong className="text-lg font-semibold text-text">{summary?.clipCount ?? 0}</strong>
            </div>
            <div className="flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 px-3.5 py-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber/10 text-amber">
                <Clock3 size={17} />
              </span>
              <span className="flex-1 text-sm text-text">处理中素材</span>
              <strong className="text-lg font-semibold text-text">{summary?.processingAssetCount ?? 0}</strong>
            </div>
          </div>
        </section>
      </div>

      {/* 下区三列 */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* 最近项目 */}
        <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">最近项目</h2>
            <button
              onClick={() => navigate("/workspace/projects")}
              className="flex items-center gap-1 text-xs text-blue transition hover:underline"
              type="button"
            >
              全部项目<ArrowUpRight size={13} />
            </button>
          </header>
          {loadingProjects ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-muted" /></div>
          ) : (
            <ul className="space-y-2.5">
              {recentProjects.map((project) => (
                <li key={project.id}>
                  <button
                    onClick={() => openProject(project.id)}
                    className="group flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3 text-left transition hover:border-blue/40 hover:bg-blue-soft/20"
                    type="button"
                  >
                    <VideoThumb variant={project.variant} className="!h-12 !w-20" rounded="rounded-lg" showPlay={false} />
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate text-sm text-text">{project.name}</strong>
                      <small className="text-xs text-muted">
                        {project.assetCount} 素材 · {project.scriptCount} 脚本
                      </small>
                      <span className="mt-1 inline-block rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">
                        {project.status}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 活跃脚本 */}
        <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">活跃脚本</h2>
            <button
              onClick={() => navigate("/workspace/scripts")}
              className="flex items-center gap-1 text-xs text-blue transition hover:underline"
              type="button"
            >
              全部脚本<ArrowUpRight size={13} />
            </button>
          </header>
          <ul className="max-h-[560px] space-y-2.5 overflow-y-auto pr-1">
            {activeScripts.map((script) => (
              <li key={script.id}>
                <button
                  onClick={() => openScript(script.id)}
                  className="group flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3 text-left transition hover:border-blue/40 hover:bg-blue-soft/20"
                  type="button"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-soft text-blue">
                    <Sparkles size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <strong className="block truncate text-sm text-text">{script.title}</strong>
                    <small className="text-xs text-muted">
                      {script.unitCount} 单元 · {script.matchedCount} 已匹配
                    </small>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-canvas">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-blue to-teal"
                        style={{ width: `${script.progress}%` }}
                      />
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-muted">{script.duration}</span>
                </button>
              </li>
            ))}
            {activeScripts.length === 0 && (
              <li className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-muted">
                暂无活跃脚本
              </li>
            )}
          </ul>
        </section>

        {/* 任务处理 */}
        <section className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-text">任务处理</h2>
              <p className="text-xs text-muted">{processingCount} 个待完成 · {failedCount} 个失败待处理</p>
            </div>
            <button
              type="button"
              onClick={() => {
                void Promise.all([jobsQuery.refetch(), summaryQuery.refetch()]).then((results) => {
                  const failed = results.some((result) => result.isError);
                  notify(failed ? "任务刷新失败，请稍后重试" : "任务状态已刷新", failed ? "error" : "info");
                });
              }}
              className="flex items-center gap-1 text-xs text-muted transition hover:text-text"
            >
              <RefreshCw size={13} />刷新
            </button>
          </header>
          <div className="mb-3 flex flex-wrap gap-1 rounded-lg bg-canvas p-1">
            {([
              ["ALL", "全部", jobsQuery.data?.total ?? jobs.length],
              ["ACTIVE", "处理中", activeCount],
              ["PAUSED", "已暂停", pausedCount],
              ["FAILED", "失败", failedCount],
              ["SUCCEEDED", "已完成", completedCount],
            ] as Array<[JobFilter, string, number]>).map(([value, label, count]) => (
              <button
                key={value}
                type="button"
                onClick={() => setJobFilter(value)}
                className={`rounded-md px-2.5 py-1.5 text-[11px] font-medium transition ${
                  jobFilter === value ? "bg-surface text-blue shadow-sm" : "text-muted hover:text-text"
                }`}
              >
                {label} {count}
              </button>
            ))}
          </div>
          <ul className="space-y-2.5">
            {activity.map((job) => (
              <li
                key={job.id}
                className="flex items-start gap-3 rounded-xl border border-line bg-canvas/40 p-3"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${jobStatusClass[job.status]}`}
                >
                  {jobStatusLabels[job.status]}
                </span>
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-sm text-text">{job.name}</strong>
                  <small className={`text-xs ${job.status === "FAILED" ? "text-red" : "text-muted"}`}>
                    {job.status === "FAILED" ? job.resultDetail || job.detail : job.detail}
                  </small>
                  {job.status === "RUNNING" && (
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-canvas">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-blue to-teal"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {job.type === "导出" && job.status === "SUCCEEDED" && (
                    <button
                      type="button"
                      title="下载成片"
                      aria-label={`下载导出结果 ${job.name}`}
                      onClick={() => void downloadExport(job)}
                      disabled={downloadingJobId === job.id}
                      className="rounded-lg p-1.5 text-muted transition hover:bg-blue-soft hover:text-blue disabled:opacity-40"
                    >
                      {downloadingJobId === job.id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                    </button>
                  )}
                  {job.status === "FAILED" && (
                    <button
                      type="button"
                      title="重试任务"
                      aria-label={`重试任务 ${job.name}`}
                      onClick={() => jobActionMutation.mutate({ id: job.id, action: "retry" })}
                      disabled={jobActionMutation.isPending}
                      className="rounded-lg p-1.5 text-muted transition hover:bg-blue-soft hover:text-blue disabled:opacity-40"
                    >
                      <RotateCcw size={15} />
                    </button>
                  )}
                  {job.status === "RUNNING" && (
                    <button
                      type="button"
                      title="暂停任务"
                      aria-label={`暂停任务 ${job.name}`}
                      onClick={() => jobActionMutation.mutate({ id: job.id, action: "pause" })}
                      disabled={jobActionMutation.isPending}
                      className="rounded-lg p-1.5 text-muted transition hover:bg-amber/10 hover:text-amber disabled:opacity-40"
                    >
                      <Pause size={15} />
                    </button>
                  )}
                  {job.status === "PAUSED" && (
                    <button
                      type="button"
                      title="继续任务"
                      aria-label={`继续任务 ${job.name}`}
                      onClick={() => jobActionMutation.mutate({ id: job.id, action: "resume" })}
                      disabled={jobActionMutation.isPending}
                      className="rounded-lg p-1.5 text-muted transition hover:bg-teal/10 hover:text-teal disabled:opacity-40"
                    >
                      <Play size={15} />
                    </button>
                  )}
                  {(job.status === "QUEUED" || job.status === "RUNNING") && (
                  <button
                    type="button"
                    title="取消任务"
                    aria-label={`取消任务 ${job.name}`}
                    onClick={() => {
                      if (window.confirm(`确定取消任务「${job.name}」吗？正在执行的处理会被终止。`)) {
                        jobActionMutation.mutate({ id: job.id, action: "cancel" });
                      }
                    }}
                    disabled={jobActionMutation.isPending}
                    className="shrink-0 rounded-lg p-1.5 text-muted transition hover:bg-red/10 hover:text-red disabled:opacity-40"
                  >
                    <XCircle size={16} />
                  </button>
                  )}
                  <button
                    type="button"
                    title="进入所属项目"
                    aria-label={`进入任务所属项目 ${job.name}`}
                    onClick={() => openProject(job.projectId)}
                    className="rounded-lg p-1.5 text-muted transition hover:bg-canvas hover:text-blue"
                  >
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              </li>
            ))}
            {activity.length === 0 && (
              <li className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-muted">
                当前筛选下没有任务
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}

export default HomeDashboard;
