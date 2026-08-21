import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock3, Download, ListChecks, ListTodo, Loader2, Pause, Play, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import * as jobApi from "@/api/jobs";
import type { Scene } from "@/api/projects";
import type { Job, JobStatus } from "@/types/models";
import { useUIStore } from "@/stores/uiStore";
import { latestTaskIsFailed, taskCanDelete, taskCanDownload, taskIsRunning, taskMatchesFilter, type ProjectTaskFilter } from "@/lib/projectTaskRules";

const statusMeta: Record<JobStatus, { label: string; tone: string }> = {
  QUEUED: { label: "排队中", tone: "bg-amber/10 text-amber" },
  RUNNING: { label: "进行中", tone: "bg-blue-soft text-blue" },
  SUCCEEDED: { label: "已完成", tone: "bg-teal/10 text-teal" },
  FAILED: { label: "已失败", tone: "bg-red/10 text-red" },
  PAUSED: { label: "已暂停", tone: "bg-canvas text-muted" },
  CANCELLED: { label: "已取消", tone: "bg-canvas text-muted" },
};

type TaskAction = "pause" | "resume" | "retry" | "delete";
const filters: Array<{ id: ProjectTaskFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "running", label: "进行中" },
  { id: "succeeded", label: "已完成" },
  { id: "failed", label: "已失败" },
  { id: "paused", label: "已暂停" },
];

interface BaseProps { projectId: string; submittedJobs: Job[] }
interface PanelProps extends BaseProps {
  projectName: string;
  scenes: Scene[];
  open: boolean;
  focusJobId?: string;
  onClose: () => void;
  onTerminalUpdate: () => void;
}
interface ButtonProps extends BaseProps { open: boolean; onOpen: () => void }
interface ProjectJobList { items: Job[]; total: number }

function useProjectJobs(projectId: string, submittedJobs: Job[]) {
  const query = useQuery({
    queryKey: ["jobs", projectId],
    queryFn: () => jobApi.list({ projectId, pageSize: 100 }),
    refetchInterval: (state) => state.state.data?.items.some((job) => taskIsRunning(job.status)) ? 2_000 : false,
    retry: false,
    enabled: projectId !== "__preview__",
  });
  return { ...query, jobs: query.data?.items ?? submittedJobs };
}

function replaceJobs(current: ProjectJobList | undefined, updates: Job[], deletedIds: string[]): ProjectJobList {
  const deleted = new Set(deletedIds);
  const changed = new Map(updates.map((job) => [job.id, job]));
  const original = current?.items ?? [];
  const items = original.filter((job) => !deleted.has(job.id)).map((job) => changed.get(job.id) ?? job);
  updates.forEach((job) => { if (!items.some((item) => item.id === job.id)) items.unshift(job); });
  return { items, total: Math.max(0, (current?.total ?? original.length) - deleted.size) };
}

function jobTime(value: string) {
  if (!value) return "刚刚";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "刚刚" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
function progressFor(job: Job) { return job.status === "SUCCEEDED" ? 100 : Math.max(0, Math.min(100, Number(job.progress) || 0)); }
export function ProjectTaskButton({ projectId, submittedJobs, open, onOpen }: ButtonProps) {
  const { jobs } = useProjectJobs(projectId, submittedJobs);
  const running = jobs.filter((job) => taskIsRunning(job.status));
  const latestFailed = latestTaskIsFailed(jobs);
  const progress = running.length ? Math.round(running.reduce((total, job) => total + progressFor(job), 0) / running.length) : 0;
  return (
    <button type="button" onClick={onOpen} aria-expanded={open} aria-label={`项目任务${running.length ? `，${running.length} 个进行中` : latestFailed ? "，最新任务失败" : ""}`} className={`relative flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition ${open ? "border-ink bg-ink text-white" : latestFailed ? "border-red/25 bg-red/5 text-red" : "border-line bg-white text-text hover:bg-canvas"}`}>
      {running.length ? <Loader2 size={13} className="animate-spin" /> : <ListTodo size={13} />}<span>任务</span>
      {running.length > 0 ? <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${open ? "bg-white/15 text-white" : "bg-blue-soft text-blue"}`}>{running.length} · {progress}%</span> : latestFailed ? <span className="rounded-full bg-red/10 px-1.5 py-0.5 text-[9px] font-semibold">失败</span> : null}
    </button>
  );
}

export function ProjectTaskPanel({ projectId, projectName, scenes, open, submittedJobs, focusJobId, onClose, onTerminalUpdate }: PanelProps) {
  const notify = useUIStore((state) => state.notify);
  const queryClient = useQueryClient();
  const previousStatuses = useRef(new Map<string, JobStatus>());
  const [filter, setFilter] = useState<ProjectTaskFilter>("all");
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { jobs: rawJobs, isLoading, error, refetch } = useProjectJobs(projectId, submittedJobs);
  const jobs = useMemo(() => [...rawJobs].sort((left, right) => {
    if (left.id === focusJobId) return -1;
    if (right.id === focusJobId) return 1;
    return new Date(right.updatedAt || right.createdAt).getTime() - new Date(left.updatedAt || left.createdAt).getTime();
  }), [focusJobId, rawJobs]);

  const shotLabels = useMemo(() => {
    const labels = new Map<string, string>();
    scenes.forEach((scene) => scene.shots.forEach((shot) => {
      if (shot.id) labels.set(shot.id, `场景 ${scene.index + 1} · 镜头 ${shot.index + 1} · ${shot.description?.trim() || "未填写画面描述"}`);
    }));
    return labels;
  }, [scenes]);
  const counts = useMemo(() => ({
    all: jobs.length,
    running: jobs.filter((job) => taskMatchesFilter(job.status, "running")).length,
    succeeded: jobs.filter((job) => taskMatchesFilter(job.status, "succeeded")).length,
    failed: jobs.filter((job) => taskMatchesFilter(job.status, "failed")).length,
    paused: jobs.filter((job) => taskMatchesFilter(job.status, "paused")).length,
  }), [jobs]);
  const visibleJobs = useMemo(() => jobs.filter((job) => taskMatchesFilter(job.status, filter)), [filter, jobs]);
  const selectedJobs = jobs.filter((job) => selectedIds.has(job.id));
  const pauseableSelected = selectedJobs.filter((job) => taskIsRunning(job.status));
  const deletableSelected = selectedJobs.filter((job) => taskCanDelete(job.status));
  const allVisibleSelected = visibleJobs.length > 0 && visibleJobs.every((job) => selectedIds.has(job.id));

  useEffect(() => { setSelectedIds((current) => new Set([...current].filter((id) => jobs.some((job) => job.id === id)))); }, [jobs]);
  useEffect(() => {
    const previous = previousStatuses.current;
    const becameTerminal = jobs.some((job) => { const old = previous.get(job.id); return old && taskIsRunning(old) && !taskIsRunning(job.status); });
    previousStatuses.current = new Map(jobs.map((job) => [job.id, job.status]));
    if (becameTerminal) onTerminalUpdate();
  }, [jobs, onTerminalUpdate]);

  const actionMutation = useMutation({
    mutationFn: async ({ action, targets }: { action: TaskAction; targets: Job[] }) => {
      const results = await Promise.allSettled(targets.map(async (job) => {
        if (action === "delete") { await jobApi.remove(job.id); return { id: job.id, job: null }; }
        const changed = action === "pause" ? await jobApi.pause(job.id) : action === "resume" ? await jobApi.resume(job.id) : await jobApi.retry(job.id);
        return { id: job.id, job: changed };
      }));
      return {
        action,
        requested: targets.length,
        succeeded: results.flatMap((result) => result.status === "fulfilled" ? [result.value] : []),
        failed: results.flatMap((result) => result.status === "rejected" ? [result.reason] : []),
      };
    },
    onSuccess: ({ action, succeeded, failed, requested }) => {
      const updates = succeeded.flatMap((item) => item.job ? [item.job] : []);
      const deletedIds = succeeded.flatMap((item) => item.job ? [] : [item.id]);
      queryClient.setQueryData<ProjectJobList>(["jobs", projectId], (current) => replaceJobs(current, updates, deletedIds));
      setSelectedIds((current) => new Set([...current].filter((id) => !succeeded.some((item) => item.id === id))));
      const actionLabel = { pause: "暂停", resume: "继续", retry: "重试", delete: "删除" }[action];
      if (failed.length) notify(`${actionLabel}成功 ${succeeded.length}/${requested} 个任务，${failed.length} 个操作失败`, "error"); else notify(`已${actionLabel} ${succeeded.length} 个任务`);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
    },
  });
  const downloadMutation = useMutation({
    mutationFn: jobApi.downloadResult,
    onSuccess: () => notify("导出成片已开始下载"),
    onError: (downloadError) => notify(downloadError instanceof Error ? downloadError.message : "导出文件下载失败", "error"),
  });

  function runAction(action: TaskAction, targets: Job[]) {
    if (!targets.length || actionMutation.isPending) return;
    if (action === "delete" && !window.confirm(`确认删除选中的 ${targets.length} 条任务记录？已经生成的素材和镜头版本会保留。`)) return;
    actionMutation.mutate({ action, targets });
  }
  function toggleOne(id: string) { setSelectedIds((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); }
  function toggleAllVisible() { setSelectedIds((current) => { const next = new Set(current); if (allVisibleSelected) visibleJobs.forEach((job) => next.delete(job.id)); else visibleJobs.forEach((job) => next.add(job.id)); return next; }); }
  function leaveBatchMode() { setBatchMode(false); setSelectedIds(new Set()); }
  function closePanel() { leaveBatchMode(); onClose(); }

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90]">
      <button type="button" className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" aria-label="关闭项目任务" onClick={closePanel} />
      <aside className="absolute bottom-0 right-0 top-0 flex w-full max-w-[540px] flex-col border-l border-line bg-white shadow-2xl" aria-label="项目任务">
        <header className="border-b border-line px-5 py-4">
          <div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ink text-white"><Sparkles size={18} /></span><div className="min-w-0 flex-1"><h2 className="text-sm font-semibold text-text">项目任务</h2><p className="mt-1 truncate text-[11px] text-muted">{projectName} · 关闭面板后任务仍会在后台继续</p></div>{jobs.length > 0 && <button type="button" onClick={() => { if (batchMode) leaveBatchMode(); else setBatchMode(true); }} className={`mr-1 flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[10px] font-semibold transition ${batchMode ? "bg-ink text-white" : "border border-line text-text hover:bg-canvas"}`}><ListChecks size={13} />{batchMode ? "完成" : "批量管理"}</button>}<button type="button" onClick={closePanel} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas" aria-label="关闭"><X size={17} /></button></div>
          <nav className="mt-4 flex gap-1 overflow-x-auto rounded-xl bg-canvas p-1" aria-label="任务状态筛选">
            {filters.map((item) => <button key={item.id} type="button" onClick={() => { setFilter(item.id); setSelectedIds(new Set()); }} aria-pressed={filter === item.id} className={`flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-2 text-[10px] font-medium ${filter === item.id ? "bg-white text-text shadow-sm" : "text-muted hover:text-text"}`}>{item.label}<span className="rounded-full bg-canvas px-1.5 py-0.5 text-[9px]">{counts[item.id]}</span></button>)}
          </nav>
        </header>

        {batchMode && visibleJobs.length > 0 && <div className="flex min-h-12 items-center gap-2 border-b border-line bg-[#fbfbfc] px-4 py-2.5"><label className="flex cursor-pointer items-center gap-2 text-[10px] font-medium text-text"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} className="h-3.5 w-3.5 rounded border-line accent-ink" />全选当前筛选</label><span className="text-[10px] text-muted">已选 {selectedJobs.length} 个</span><div className="ml-auto flex gap-1.5">{pauseableSelected.length > 0 && <button type="button" disabled={actionMutation.isPending} onClick={() => runAction("pause", pauseableSelected)} className="flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[10px] font-semibold text-text disabled:opacity-40"><Pause size={11} />暂停 {pauseableSelected.length}</button>}{deletableSelected.length > 0 && <button type="button" disabled={actionMutation.isPending} onClick={() => runAction("delete", deletableSelected)} className="flex items-center gap-1 rounded-lg border border-red/20 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-red disabled:opacity-40"><Trash2 size={11} />删除 {deletableSelected.length}</button>}</div></div>}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {isLoading && !jobs.length ? <div className="grid min-h-52 place-items-center text-xs text-muted"><span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" />正在读取项目任务…</span></div> : error && !jobs.length ? <div className="rounded-xl bg-red/5 p-5 text-center"><AlertTriangle size={20} className="mx-auto text-red" /><p className="mt-2 text-xs text-red">{error.message}</p><button type="button" onClick={() => void refetch()} className="mt-3 text-xs font-semibold text-text underline">重新加载</button></div> : !visibleJobs.length ? <div className="grid min-h-52 place-items-center text-center"><div><Clock3 size={22} className="mx-auto text-muted" /><strong className="mt-3 block text-sm text-text">当前分类没有任务</strong><p className="mt-1 text-xs text-muted">切换其他状态分类，或提交新的 AI 生成任务。</p></div></div> : <div className="space-y-3">
            {visibleJobs.map((job) => {
              const meta = statusMeta[job.status]; const running = taskIsRunning(job.status); const progress = progressFor(job); const target = job.subjectType === "shot" && job.subjectId ? shotLabels.get(job.subjectId) : undefined; const selected = selectedIds.has(job.id); const busy = actionMutation.isPending && actionMutation.variables?.targets.some((item) => item.id === job.id); const downloading = downloadMutation.isPending && downloadMutation.variables === job.id;
              return <article key={job.id} className={`rounded-xl border bg-white p-4 ${selected || focusJobId === job.id ? "border-blue/40 ring-1 ring-blue/10" : "border-line"}`}>
                <div className="flex items-start gap-3">{batchMode && <input type="checkbox" checked={selected} onChange={() => toggleOne(job.id)} aria-label={`选择任务：${job.name}`} className="mt-2 h-3.5 w-3.5 shrink-0 rounded border-line accent-ink" />}<span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${job.status === "FAILED" ? "bg-red/10 text-red" : job.status === "SUCCEEDED" ? "bg-teal/10 text-teal" : "bg-blue-soft text-blue"}`}>{running ? <Loader2 size={14} className={job.status === "RUNNING" ? "animate-spin" : ""} /> : job.status === "SUCCEEDED" ? <CheckCircle2 size={14} /> : job.status === "PAUSED" ? <Pause size={14} /> : <AlertTriangle size={14} />}</span><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><strong className="truncate text-xs text-text">{job.name}</strong><span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-semibold ${meta.tone}`}>{meta.label}</span></div>{target && <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted">{target}</p>}{job.type === "导出" && job.exportMetadata && <p className="mt-1 text-[10px] font-medium text-text">{job.exportMetadata.format.toUpperCase()} · {job.exportMetadata.resolution.toUpperCase()} · {job.exportMetadata.aspectRatio}</p>}<p className={`mt-1 text-[10px] leading-4 ${job.status === "FAILED" ? "text-red" : "text-muted"}`}>{job.resultDetail || job.detail || job.stage || "任务已加入队列"}</p></div><time className="shrink-0 text-[9px] text-muted">{jobTime(job.updatedAt || job.createdAt)}</time></div>
                <div className={`${batchMode ? "ml-[58px]" : "ml-11"} mt-3`}><div className="flex items-center justify-between text-[9px] text-muted"><span>{job.stage || meta.label}</span><span>{progress}%</span></div><div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-canvas"><div className={`h-full rounded-full transition-all ${job.status === "FAILED" ? "bg-red" : job.status === "SUCCEEDED" ? "bg-teal" : "bg-blue"}`} style={{ width: `${progress}%` }} /></div></div>
                {!batchMode && <footer className="mt-3 flex justify-end gap-1.5 border-t border-line/70 pt-3">{running && <button type="button" disabled={busy} onClick={() => runAction("pause", [job])} className="flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-[10px] font-semibold text-text disabled:opacity-40"><Pause size={11} />暂停</button>}{job.status === "PAUSED" && <button type="button" disabled={busy} onClick={() => runAction("resume", [job])} className="flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-[10px] font-semibold text-text disabled:opacity-40"><Play size={11} />继续</button>}{job.status === "FAILED" && <button type="button" disabled={busy} onClick={() => runAction("retry", [job])} className="flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-[10px] font-semibold text-text disabled:opacity-40"><RefreshCw size={11} />重试</button>}{taskCanDownload(job.type, job.status) && <button type="button" disabled={downloading} onClick={() => downloadMutation.mutate(job.id)} className="flex items-center gap-1 rounded-lg bg-blue px-2.5 py-1.5 text-[10px] font-semibold text-white hover:bg-blue/90 disabled:opacity-40">{downloading ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}{downloading ? "正在下载…" : "下载成片"}</button>}{!running && <button type="button" disabled={busy || downloading} onClick={() => runAction("delete", [job])} className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[10px] font-medium text-red hover:bg-red/5 disabled:opacity-40"><Trash2 size={11} />删除</button>}</footer>}
              </article>;
            })}
          </div>}
        </div>
      </aside>
    </div>
  );
}
