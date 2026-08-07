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

type JobAction = "retry" | "pause" | "resume" | "cancel";

const jobStatusLabels: Record<Job["status"], string> = {
  RUNNING: "处理中",
  QUEUED: "等待中",
  PAUSED: "已暂停",
  SUCCEEDED: "已完成",
  FAILED: "失败",
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

const jobPriority: Record<Job["status"], number> = {
  RUNNING: 0,
  QUEUED: 1,
  PAUSED: 2,
  FAILED: 3,
  SUCCEEDED: 4,
  CANCELLED: 5,
};

export function HomeDashboard() {
  const navigate = useNavigate();
  const { openUploadDrawer, openScriptCreate, openAIScript, openProjectCreate, notify } = useUIStore();
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const setCurrentScriptId = useScriptStore((state) => state.setCurrentScriptId);
  const queryClient = useQueryClient();
  const [downloadingJobId, setDownloadingJobId] = useState<string | null>(null);

  const projectsQuery = useQuery({ queryKey: ["projects", "dashboard"], queryFn: () => projectApi.list({ pageSize: 8 }), retry: false });
  const scriptsQuery = useQuery({ queryKey: ["scripts", "dashboard"], queryFn: () => scriptApi.list(), retry: false });
  const summaryQuery = useQuery({ queryKey: ["dashboard-summary"], queryFn: projectApi.getDashboardSummary, retry: false });
  const jobsQuery = useQuery({
    queryKey: ["jobs", "dashboard"],
    queryFn: () => jobApi.list({ pageSize: 30 }),
    retry: false,
    refetchInterval: (query) => query.state.data?.items.some((job) => ["QUEUED", "RUNNING"].includes(job.status)) ? 5_000 : false,
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: JobAction }) => {
      if (action === "retry") return jobApi.retry(id);
      if (action === "pause") return jobApi.pause(id);
      if (action === "resume") return jobApi.resume(id);
      return jobApi.cancel(id);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      notify("任务状态已更新");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "任务操作失败", "error"),
  });

  const projects = projectsQuery.data?.items ?? [];
  const scripts = scriptsQuery.data?.items ?? [];
  const summary = summaryQuery.data;
  const taskSummary = [...(jobsQuery.data?.items ?? [])]
    .sort((left, right) => jobPriority[left.status] - jobPriority[right.status])
    .slice(0, 3);
  const loadError = [projectsQuery, scriptsQuery, summaryQuery, jobsQuery].find((query) => query.isError)?.error;

  const openProject = (id: string) => {
    setCurrentProject(id);
    navigate(`/workspace/projects/${id}`);
  };
  const openScript = (id: string) => {
    setCurrentScriptId(id);
    navigate(`/workspace/scripts/${id}/editor`);
  };
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

  if (loadError) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="text-2xl font-bold text-text">综合工作台</h1>
        <div className="mt-6 rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">工作台数据加载失败</p>
          <p className="mt-1 text-xs text-muted">{loadError instanceof Error ? loadError.message : "请检查后端服务"}</p>
        </div>
      </div>
    );
  }

  const quickActions = [
    { label: "上传素材", copy: "导入视频并理解镜头", Icon: Upload, action: openUploadDrawer },
    { label: "AI 生成脚本", copy: "根据创作目标生成脚本", Icon: WandSparkles, action: () => openAIScript() },
    { label: "新建脚本", copy: "粘贴、表格或空白开始", Icon: Plus, action: openScriptCreate },
    { label: "新建项目", copy: "建立独立创作空间", Icon: FolderKanban, action: openProjectCreate },
  ];
  const materialMetrics: Array<{ label: string; count: number; Icon: typeof Library }> = [
    { label: "素材总数", count: summary?.assetCount ?? 0, Icon: Library },
    { label: "可搜索片段", count: summary?.clipCount ?? 0, Icon: Sparkles },
    { label: "处理中素材", count: summary?.processingAssetCount ?? 0, Icon: Clock3 },
  ];

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <section className="mb-7">
        <h1 className="text-2xl font-bold text-text">综合工作台</h1>
        <p className="mt-1.5 text-sm text-muted">从创作入口开始，并只关注当前最需要处理的任务。</p>
      </section>

      <div className="mb-6 grid min-w-0 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4">
            <h2 className="text-base font-semibold text-text">快速开始</h2>
            <p className="text-xs text-muted">选择一个入口开始创作</p>
          </header>
          <div className="grid gap-3 sm:grid-cols-2">
            {quickActions.map(({ label, copy, Icon, action }) => (
              <button
                key={label}
                type="button"
                onClick={action}
                className="group flex min-w-0 items-center gap-3 rounded-xl border border-line bg-white p-4 text-left transition hover:border-blue/40 hover:bg-blue-soft/35 hover:shadow-sm"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue transition group-hover:bg-blue group-hover:text-white">
                  <Icon size={19} />
                </span>
                <span className="min-w-0">
                  <strong className="block truncate text-sm text-text">{label}</strong>
                  <small className="mt-0.5 block truncate text-xs text-muted">{copy}</small>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="min-w-0 overflow-hidden rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-text">任务摘要</h2>
              <p className="truncate text-xs text-muted">优先显示运行、排队、暂停和失败任务</p>
            </div>
            <button type="button" onClick={() => navigate("/workspace/tasks")} className="flex shrink-0 items-center gap-1 whitespace-nowrap text-xs font-medium text-blue hover:underline">查看全部<ArrowUpRight size={13} /></button>
          </header>
          <div className="mb-3 grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
            {[
              ["运行", summary?.runningJobCount ?? 0],
              ["排队", summary?.queuedJobCount ?? 0],
              ["暂停", summary?.pausedJobCount ?? 0],
              ["失败", summary?.failedJobCount ?? 0],
            ].map(([label, count]) => <div key={label} className="rounded-lg bg-canvas px-2 py-2"><strong className="block text-base text-text">{count}</strong><span className="text-[11px] text-muted">{label}</span></div>)}
          </div>
          <ul className="space-y-2">
            {taskSummary.map((job) => (
              <li key={job.id} className="flex min-w-0 items-center gap-2 rounded-lg border border-line px-2.5 py-2">
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${jobStatusClass[job.status]}`}>{jobStatusLabels[job.status]}</span>
                <span className="min-w-0 flex-1"><strong className="block truncate text-xs text-text">{job.name}</strong><small className="block truncate text-[11px] text-muted">{job.detail}</small></span>
                <div className="flex shrink-0">
                  {job.type === "导出" && job.status === "SUCCEEDED" && <button type="button" onClick={() => void downloadExport(job)} className="p-1.5 text-muted hover:text-blue">{downloadingJobId === job.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}</button>}
                  {job.status === "FAILED" && <button type="button" onClick={() => actionMutation.mutate({ id: job.id, action: "retry" })} className="p-1.5 text-muted hover:text-blue"><RotateCcw size={14} /></button>}
                  {job.status === "RUNNING" && <button type="button" onClick={() => actionMutation.mutate({ id: job.id, action: "pause" })} className="p-1.5 text-muted hover:text-amber"><Pause size={14} /></button>}
                  {job.status === "PAUSED" && <button type="button" onClick={() => actionMutation.mutate({ id: job.id, action: "resume" })} className="p-1.5 text-muted hover:text-teal"><Play size={14} /></button>}
                  {["QUEUED", "RUNNING"].includes(job.status) && <button type="button" onClick={() => actionMutation.mutate({ id: job.id, action: "cancel" })} className="p-1.5 text-muted hover:text-red"><XCircle size={14} /></button>}
                </div>
              </li>
            ))}
            {!taskSummary.length && <li className="rounded-lg border border-dashed border-line py-7 text-center text-xs text-muted">暂无任务</li>}
          </ul>
        </section>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <section className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between"><h2 className="text-base font-semibold text-text">素材</h2><button type="button" onClick={() => navigate("/workspace/library")} className="text-xs text-blue hover:underline">全部素材</button></header>
          <div className="space-y-3">
            {materialMetrics.map(({ label, count, Icon }) => {
              return <div key={label} className="flex items-center gap-3 rounded-xl border border-line bg-canvas/40 px-3.5 py-3"><span className="grid h-9 w-9 place-items-center rounded-lg bg-blue-soft text-blue"><Icon size={17} /></span><span className="flex-1 text-sm text-text">{label}</span><strong className="text-lg text-text">{count}</strong></div>;
            })}
          </div>
        </section>

        <section className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between"><h2 className="text-base font-semibold text-text">脚本</h2><button type="button" onClick={() => navigate("/workspace/scripts")} className="text-xs text-blue hover:underline">全部脚本</button></header>
          <ul className="space-y-2.5">{scripts.slice(0, 4).map((script) => <li key={script.id}><button type="button" onClick={() => openScript(script.id)} className="flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3 text-left hover:border-blue/40 hover:bg-blue-soft/20"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-blue-soft text-blue"><Sparkles size={16} /></span><span className="min-w-0 flex-1"><strong className="block truncate text-sm text-text">{script.title}</strong><small className="text-xs text-muted">已有画面 {script.matchedCount}/{script.unitCount} 个分镜</small></span><span className="text-xs text-muted">{script.duration}</span></button></li>)}{!scripts.length && <li className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-muted">暂无脚本</li>}</ul>
        </section>

        <section className="min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <header className="mb-4 flex items-center justify-between"><h2 className="text-base font-semibold text-text">项目</h2><button type="button" onClick={() => navigate("/workspace/projects")} className="text-xs text-blue hover:underline">全部项目</button></header>
          <ul className="space-y-2.5">{projects.slice(0, 4).map((project) => <li key={project.id}><button type="button" onClick={() => openProject(project.id)} className="flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3 text-left hover:border-blue/40 hover:bg-blue-soft/20"><VideoThumb variant={project.variant} className="!h-11 !w-16" rounded="rounded-lg" showPlay={false} /><span className="min-w-0 flex-1"><strong className="block truncate text-sm text-text">{project.name}</strong><small className="text-xs text-muted">{project.assetCount} 素材 · {project.scriptCount} 脚本</small></span><ArrowUpRight size={14} className="text-muted" /></button></li>)}{!projects.length && <li className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-muted">暂无项目</li>}</ul>
        </section>
      </div>
    </div>
  );
}

export default HomeDashboard;
