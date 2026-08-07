import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/router";
import { ArrowUpRight, Download, Loader2, Pause, Play, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import * as jobApi from "@/api/jobs";
import * as projectApi from "@/api/projects";
import { BackButton } from "@/components/BackButton";
import { useUIStore } from "@/stores/uiStore";
import type { Job, JobStatus } from "@/types/models";

const statusOptions: Array<{ value: "" | JobStatus; label: string }> = [
  { value: "", label: "全部" },
  { value: "RUNNING", label: "处理中" },
  { value: "QUEUED", label: "排队中" },
  { value: "PAUSED", label: "已暂停" },
  { value: "FAILED", label: "失败" },
  { value: "SUCCEEDED", label: "已完成" },
  { value: "CANCELLED", label: "已取消" },
];

const statusClass: Record<JobStatus, string> = {
  RUNNING: "bg-blue-soft text-blue",
  QUEUED: "bg-canvas text-muted",
  PAUSED: "bg-amber/10 text-amber",
  FAILED: "bg-red/10 text-red",
  SUCCEEDED: "bg-teal/10 text-teal",
  CANCELLED: "bg-canvas text-muted",
};

export default function TasksCenterView() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const notify = useUIStore((state) => state.notify);
  const [downloading, setDownloading] = useState<string | null>(null);
  const status = (searchParams.get("status") ?? "") as "" | JobStatus;
  const projectId = searchParams.get("project") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") ?? 1));
  const pageSize = 20;

  const jobsQuery = useQuery({
    queryKey: ["jobs", "center", status, projectId, page],
    queryFn: () => jobApi.list({ status: status || undefined, projectId: projectId || undefined, page, pageSize }),
    refetchInterval: (query) => query.state.data?.items.some((job) => ["QUEUED", "RUNNING"].includes(job.status)) ? 5_000 : false,
  });
  const projectsQuery = useQuery({ queryKey: ["projects", "tasks"], queryFn: () => projectApi.list({ pageSize: 100 }) });
  const projectNames = new Map((projectsQuery.data?.items ?? []).map((project) => [project.id, project.name]));
  const totalPages = Math.max(1, Math.ceil((jobsQuery.data?.total ?? 0) / pageSize));

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setSearchParams(next, { replace: true });
  };
  const goPage = (nextPage: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(nextPage));
    setSearchParams(next);
  };

  const actionMutation = useMutation({
    mutationFn: ({ job, action }: { job: Job; action: "retry" | "pause" | "resume" | "cancel" }) => {
      if (action === "retry") return jobApi.retry(job.id);
      if (action === "pause") return jobApi.pause(job.id);
      if (action === "resume") return jobApi.resume(job.id);
      return jobApi.cancel(job.id);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      notify("任务状态已更新");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "任务操作失败", "error"),
  });

  const download = async (job: Job) => {
    setDownloading(job.id);
    try {
      await jobApi.downloadResult(job.id);
      notify("成片下载已开始");
    } catch (error) {
      notify(error instanceof Error ? error.message : "下载失败", "error");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <BackButton
        fallback="/workspace"
        fallbackLabel="综合工作台"
        className="mb-4 flex w-fit items-center gap-1.5 rounded-lg px-2 py-2 text-sm font-medium text-muted transition hover:bg-white hover:text-text"
      />
      <header className="flex items-start justify-between gap-4">
        <div><h1 className="text-2xl font-bold text-text">全部任务</h1><p className="mt-1.5 text-sm text-muted">工作台任务摘要的完整列表，可在这里处理失败、暂停、取消和导出下载。</p></div>
        <button type="button" onClick={() => void jobsQuery.refetch()} className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-sm text-text hover:bg-canvas"><RefreshCw size={15} />刷新</button>
      </header>

      <section className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
        <div className="flex flex-wrap gap-1 rounded-lg bg-canvas p-1">{statusOptions.map((option) => <button key={option.value || "all"} type="button" onClick={() => updateFilter("status", option.value)} className={`rounded-md px-3 py-1.5 text-xs font-medium ${status === option.value ? "bg-white text-blue shadow-sm" : "text-muted hover:text-text"}`}>{option.label}</button>)}</div>
        <select value={projectId} onChange={(event) => updateFilter("project", event.target.value)} className="h-9 rounded-lg border border-line bg-white px-3 text-xs text-text"><option value="">全部项目</option>{(projectsQuery.data?.items ?? []).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
        <span className="ml-auto text-xs text-muted">共 {jobsQuery.data?.total ?? 0} 个任务</span>
      </section>

      <section className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        {jobsQuery.isLoading ? <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-blue" /></div> : jobsQuery.isError ? <div className="py-20 text-center text-sm text-red">{jobsQuery.error instanceof Error ? jobsQuery.error.message : "任务加载失败"}</div> : jobsQuery.data?.items.length ? (
          <ul className="divide-y divide-line">{jobsQuery.data.items.map((job) => (
            <li key={job.id} className="grid gap-3 px-5 py-4 md:grid-cols-[100px_minmax(0,1.4fr)_minmax(180px,.8fr)_140px_auto] md:items-center">
              <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${statusClass[job.status]}`}>{statusOptions.find((option) => option.value === job.status)?.label ?? job.status}</span>
              <div className="min-w-0"><strong className="block truncate text-sm text-text">{job.name}</strong><p className={`mt-0.5 truncate text-xs ${job.status === "FAILED" ? "text-red" : "text-muted"}`}>{job.status === "FAILED" ? job.resultDetail || job.detail : job.detail}</p>{job.status === "RUNNING" && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-canvas"><div className="h-full rounded-full bg-blue" style={{ width: `${job.progress}%` }} /></div>}</div>
              <div className="min-w-0 text-xs text-muted"><span className="block truncate">{projectNames.get(job.projectId) ?? "所属项目"}</span><span className="mt-1 block">{job.type} · {job.stage}</span></div>
              <div className="text-xs text-muted">{job.status === "RUNNING" ? `${job.progress}% · ${job.eta || "处理中"}` : job.createdAt || ""}</div>
              <div className="flex items-center justify-end gap-1">
                {job.type === "导出" && job.status === "SUCCEEDED" && <button type="button" title="下载" onClick={() => void download(job)} className="rounded-lg p-2 text-muted hover:bg-blue-soft hover:text-blue">{downloading === job.id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}</button>}
                {job.status === "FAILED" && <button type="button" title="重试" onClick={() => actionMutation.mutate({ job, action: "retry" })} className="rounded-lg p-2 text-muted hover:bg-blue-soft hover:text-blue"><RotateCcw size={15} /></button>}
                {job.status === "RUNNING" && <button type="button" title="暂停" onClick={() => actionMutation.mutate({ job, action: "pause" })} className="rounded-lg p-2 text-muted hover:bg-amber/10 hover:text-amber"><Pause size={15} /></button>}
                {job.status === "PAUSED" && <button type="button" title="继续" onClick={() => actionMutation.mutate({ job, action: "resume" })} className="rounded-lg p-2 text-muted hover:bg-teal/10 hover:text-teal"><Play size={15} /></button>}
                {["QUEUED", "RUNNING"].includes(job.status) && <button type="button" title="取消" onClick={() => window.confirm(`确定取消「${job.name}」吗？`) && actionMutation.mutate({ job, action: "cancel" })} className="rounded-lg p-2 text-muted hover:bg-red/10 hover:text-red"><XCircle size={15} /></button>}
                <button type="button" title="进入项目" onClick={() => navigate(`/workspace/projects/${job.projectId}`)} className="rounded-lg p-2 text-muted hover:bg-canvas hover:text-blue"><ArrowUpRight size={15} /></button>
              </div>
            </li>
          ))}</ul>
        ) : <div className="py-20 text-center text-sm text-muted">当前筛选条件下没有任务</div>}
      </section>

      <footer className="mt-4 flex items-center justify-between text-xs text-muted"><span>第 {Math.min(page, totalPages)} / {totalPages} 页</span><div className="flex gap-2"><button type="button" disabled={page <= 1} onClick={() => goPage(page - 1)} className="rounded-lg border border-line bg-white px-3 py-2 disabled:opacity-40">上一页</button><button type="button" disabled={page >= totalPages} onClick={() => goPage(page + 1)} className="rounded-lg border border-line bg-white px-3 py-2 disabled:opacity-40">下一页</button></div></footer>
    </div>
  );
}
