import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUpRight,
  CalendarClock,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileText,
  Link2,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import * as inspirationApi from "@/api/inspiration";
import { useUIStore } from "@/stores/uiStore";

const weekdays = [
  { value: 1, label: "周一" },
  { value: 2, label: "周二" },
  { value: 3, label: "周三" },
  { value: 4, label: "周四" },
  { value: 5, label: "周五" },
  { value: 6, label: "周六" },
  { value: 0, label: "周日" },
];

const TASK_PAGE_SIZE = 12;

const typeMeta: Record<inspirationApi.InspirationTaskType, { label: string; description: string; icon: typeof Sparkles }> = {
  "topic-recommendation": {
    label: "选题发现",
    description: "Agent 主动联网搜索；指定网站会被最高优先级使用。",
    icon: Sparkles,
  },
  "link-update": {
    label: "来源监控",
    description: "只盯住指定链接，建立基线后提取真正的新变化。",
    icon: Link2,
  },
};

interface EditorDraft extends inspirationApi.InspirationTaskInput {
  id?: string;
  sourceText: string;
}

function blankDraft(): EditorDraft {
  return {
    name: "",
    taskType: "topic-recommendation",
    topicBrief: "",
    topicCount: 5,
    discoveryConfig: { sourceStrategy: "web", monitorBrief: "", searchRecencyDays: 7 },
    schedule: { type: "daily", time: "09:00", weekday: 1, timeZone: "Asia/Shanghai" },
    enabled: true,
    sources: [],
    sourceText: "",
  };
}

function taskDraft(task: inspirationApi.InspirationTask): EditorDraft {
  return {
    id: task.id,
    name: task.name,
    taskType: task.taskType,
    topicBrief: task.topicBrief,
    topicCount: task.topicCount ?? 5,
    discoveryConfig: task.discoveryConfig,
    schedule: task.schedule,
    enabled: task.enabled,
    sources: task.sources.map((source) => ({ sourceType: source.sourceType, url: source.url })),
    sourceText: task.sources.map((source) => source.url).join("\n"),
  };
}

function formatTime(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "尚未运行";
}

function formatSchedule(schedule: inspirationApi.InspirationSchedule) {
  if (schedule.type === "manual") return "仅手动更新";
  if (schedule.type === "weekly") {
    return `每${weekdays.find((item) => item.value === schedule.weekday)?.label ?? "周一"} ${schedule.time}`;
  }
  return `每天 ${schedule.time}`;
}

function parseSourceText(value: string, required: boolean): { sources?: EditorDraft["sources"]; error?: string } {
  const lines = value.split(/\r?\n/u).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return required ? { error: "请至少填写一个 HTTPS 链接" } : { sources: [] };
  const seen = new Set<string>();
  const sources: EditorDraft["sources"] = [];
  for (const line of lines) {
    try {
      const url = new URL(line);
      if (url.protocol !== "https:") return { error: "真实采集只允许 HTTPS 链接" };
      const normalized = url.toString();
      if (seen.has(normalized)) return { error: "请移除重复链接" };
      seen.add(normalized);
      sources.push({ sourceType: /(?:rss|feed|atom|\.xml)(?:[/?#]|$)/iu.test(normalized) ? "rss" : "web", url: normalized });
    } catch {
      return { error: `链接格式无效：${line}` };
    }
  }
  return { sources };
}

function latestResult(run?: inspirationApi.InspirationRun) {
  return run?.results[0];
}

function emptyOutcomeCopy(run?: inspirationApi.InspirationRun) {
  if (!run) return "任务运行后，这里会显示格式化结果与外链。";
  if (run.outcome === "BASELINE_CREATED") return "首次采集已完成并建立基线；后续只展示真正的新变化。";
  if (run.outcome === "UNCHANGED") return "本轮抓取成功，没有检测到有效变化。";
  if (run.outcome === "STRUCTURE_CHANGED") return "来源可能发生改版，本轮已停止生成动态，请检查监控链接。";
  if (run.outcome === "PARTIAL") return "部分来源异常，其余来源已完成处理；可在编辑页检查来源状态。";
  return "任务运行后，这里会显示格式化结果与外链。";
}

function ResultPreview({ task, run }: { task: inspirationApi.InspirationTask; run?: inspirationApi.InspirationRun }) {
  const result = latestResult(run);
  if (run?.error) return <p className="flex items-start gap-2 rounded-xl bg-red/5 p-3 text-xs text-red"><AlertCircle size={14} className="mt-0.5 shrink-0" />{run.error}</p>;
  if (!result) return <div className="flex items-start gap-2 rounded-xl border border-dashed border-line p-4 text-xs leading-5 text-muted"><Clock3 size={15} className="mt-0.5 shrink-0" />{emptyOutcomeCopy(run)}</div>;

  if (task.taskType === "link-update") {
    return <div className="space-y-2">{result.updates.slice(0, 2).map((update) => <article key={update.id} className="flex items-start gap-3 rounded-xl bg-canvas p-3"><div className="min-w-0 flex-1"><span className="text-[10px] font-medium text-muted">{update.source}</span><strong className="mt-0.5 block truncate text-xs text-text">{update.title}</strong><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{update.summary}</p></div><a href={update.url} target="_blank" rel="noreferrer" aria-label={`打开 ${update.source}`} className="mt-1 text-muted hover:text-text"><ArrowUpRight size={14} /></a></article>)}</div>;
  }
  return <div className="space-y-2">{result.topics.slice(0, 2).map((topic) => <article key={topic.id} className="flex items-start gap-3 rounded-xl bg-canvas p-3"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ink text-[10px] font-semibold text-white">{String(topic.order).padStart(2, "0")}</span><div className="min-w-0"><span className="text-[10px] font-medium text-muted">{topic.angle}</span><strong className="mt-0.5 block truncate text-xs text-text">{topic.title}</strong><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{topic.summary}</p></div></article>)}</div>;
}

export default function InspirationView({
  previewTasks,
  previewRuns,
}: {
  previewTasks?: inspirationApi.InspirationTask[];
  previewRuns?: Record<string, inspirationApi.InspirationRun>;
} = {}) {
  const previewMode = Boolean(previewTasks);
  const queryClient = useQueryClient();
  const notify = useUIStore((state) => state.notify);
  const [editorDraft, setEditorDraft] = useState<EditorDraft | null>(null);
  const [editorError, setEditorError] = useState("");
  const [resultTaskId, setResultTaskId] = useState<string | null>(null);
  const [taskPage, setTaskPage] = useState(1);

  const tasksQuery = useQuery({
    queryKey: ["inspiration-tasks", taskPage],
    queryFn: () => inspirationApi.listTasks(taskPage, TASK_PAGE_SIZE),
    placeholderData: (previous) => previous,
    retry: false,
    refetchInterval: 15_000,
    enabled: !previewMode,
  });
  const tasks = useMemo(() => previewTasks ?? tasksQuery.data?.items ?? [], [previewTasks, tasksQuery.data]);
  const taskTotal = previewTasks?.length ?? tasksQuery.data?.total ?? 0;
  const taskTotalPages = Math.max(1, Math.ceil(taskTotal / TASK_PAGE_SIZE));

  useEffect(() => {
    if (!previewMode && taskPage > taskTotalPages) setTaskPage(taskTotalPages);
  }, [previewMode, taskPage, taskTotalPages]);
  const runQueries = useQueries({
    queries: tasks.map((task) => ({
      queryKey: ["inspiration-runs", task.id, "latest"],
      queryFn: () => inspirationApi.listRuns(task.id, 1, 10),
      retry: false,
      refetchInterval: 10_000,
      enabled: !previewMode,
    })),
  });
  const latestRuns = useMemo(
    () => new Map(tasks.map((task, index) => {
      const runs = runQueries[index]?.data?.items ?? [];
      const latest = runs[0];
      const visibleRun = latest;
      return [task.id, previewRuns?.[task.id] ?? visibleRun];
    })),
    [previewRuns, runQueries, tasks],
  );
  const resultTask = tasks.find((task) => task.id === resultTaskId);
  const resultRun = resultTask ? latestRuns.get(resultTask.id) : undefined;
  const activeCount = tasks.filter((task) => task.enabled).length;
  const recentOutputCount = [...latestRuns.values()].reduce((total, run) => {
    const result = latestResult(run);
    return total + (result?.topics.length ?? 0) + (result?.updates.length ?? 0);
  }, 0);

  const saveMutation = useMutation({
    mutationFn: ({ draft, sources }: { draft: EditorDraft; sources: EditorDraft["sources"] }) => {
      const input: inspirationApi.InspirationTaskInput = { ...draft, sources };
      return draft.id ? inspirationApi.updateTask(draft.id, input) : inspirationApi.createTask(input);
    },
    onSuccess: (task) => {
      setEditorDraft(null);
      setEditorError("");
      void queryClient.invalidateQueries({ queryKey: ["inspiration-tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["inspiration-runs", task.id] });
      notify(`“${task.name}”已保存`);
    },
    onError: (error) => setEditorError(error instanceof Error ? error.message : "保存失败"),
  });
  const runMutation = useMutation({
    mutationFn: inspirationApi.runTask,
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: ["inspiration-runs", run.taskId] });
      void queryClient.invalidateQueries({ queryKey: ["inspiration-tasks"] });
      notify("灵感更新任务已进入队列");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "运行失败", "error"),
  });
  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => inspirationApi.setTaskEnabled(id, enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["inspiration-tasks"] }),
    onError: (error) => notify(error instanceof Error ? error.message : "更新失败", "error"),
  });
  const deleteMutation = useMutation({
    mutationFn: inspirationApi.removeTask,
    onSuccess: () => {
      setEditorDraft(null);
      setResultTaskId(null);
      void queryClient.invalidateQueries({ queryKey: ["inspiration-tasks"] });
      notify("灵感任务已删除");
    },
    onError: (error) => setEditorError(error instanceof Error ? error.message : "删除失败"),
  });

  function saveEditor() {
    if (!editorDraft) return;
    if (!editorDraft.name.trim()) return setEditorError("请填写任务名称");
    if (editorDraft.taskType === "topic-recommendation" && !editorDraft.topicBrief.trim()) return setEditorError("请填写选题方向");
    if (editorDraft.taskType === "topic-recommendation" && (!Number.isInteger(editorDraft.topicCount) || (editorDraft.topicCount ?? 0) < 1 || (editorDraft.topicCount ?? 0) > 20)) return setEditorError("选题数量需为 1–20 个");
    const sourceRequired = editorDraft.taskType === "link-update" || editorDraft.discoveryConfig.sourceStrategy === "only";
    const parsed = editorDraft.taskType === "topic-recommendation" && editorDraft.discoveryConfig.sourceStrategy === "web"
      ? { sources: [] as EditorDraft["sources"] }
      : parseSourceText(editorDraft.sourceText, sourceRequired);
    if (parsed.error || !parsed.sources) return setEditorError(parsed.error ?? "来源无效");
    setEditorError("");
    const sourceStrategy = editorDraft.taskType === "topic-recommendation" && editorDraft.discoveryConfig.sourceStrategy === "preferred" && !parsed.sources.length ? "web" : editorDraft.discoveryConfig.sourceStrategy;
    saveMutation.mutate({ draft: { ...editorDraft, name: editorDraft.name.trim(), topicBrief: editorDraft.topicBrief.trim(), discoveryConfig: { ...editorDraft.discoveryConfig, sourceStrategy } }, sources: parsed.sources });
  }

  return (
    <div className="workspace-page max-w-[1360px]">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div><p className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-[0.12em] text-muted"><Sparkles size={13} />INSPIRATION ISLAND</p><h1 className="workspace-page-title">主动发现未知，持续守住已知。</h1><p className="workspace-page-copy">选题发现由 Agent 联网寻找机会；来源监控只追踪你指定的链接，所有结果保留真实证据。</p></div>
        <button type="button" onClick={() => { setEditorDraft(blankDraft()); setEditorError(""); }} className="workspace-primary-button"><Plus size={16} />设置任务</button>
      </header>

      <section className="mb-7 grid overflow-hidden rounded-2xl border border-line bg-surface md:grid-cols-[1fr_1fr_auto]">
        {(["topic-recommendation", "link-update"] as const).map((type) => { const meta = typeMeta[type]; const Icon = meta.icon; return <article key={type} className="flex gap-3 border-b border-line p-4 last:border-b-0 md:border-b-0 md:border-r"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-canvas text-text"><Icon size={18} /></span><div><strong className="text-sm text-text">{meta.label}</strong><p className="mt-1 text-xs leading-5 text-muted">{meta.description}</p></div></article>; })}
        <aside className="flex min-w-[210px] items-center justify-center gap-5 p-4 text-center"><div><strong className="block text-xl text-text">{activeCount}</strong><span className="text-[11px] text-muted">本页已启用</span></div><i className="h-8 w-px bg-line" /><div><strong className="block text-xl text-text">{recentOutputCount}</strong><span className="text-[11px] text-muted">本页最近结果</span></div></aside>
      </section>

      <section>
        <header className="mb-4 flex items-end justify-between gap-3"><div><h2 className="text-lg font-semibold text-text">我的任务</h2><p className="mt-1 text-xs text-muted">{tasks.length ? `共 ${taskTotal} 个真实任务。` : "创建第一项任务，开始持续收集灵感。"}</p></div><button type="button" onClick={() => { setEditorDraft(blankDraft()); setEditorError(""); }} className="workspace-secondary-button min-h-9 px-3 text-xs"><Plus size={14} />新建任务</button></header>

        {!previewMode && tasksQuery.isLoading ? <div className="flex justify-center py-24 text-muted"><Loader2 className="animate-spin" /></div>
          : !previewMode && tasksQuery.isError ? <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center text-sm text-red">{tasksQuery.error instanceof Error ? tasksQuery.error.message : "任务加载失败"}</div>
          : !tasks.length ? <div className="rounded-2xl border border-dashed border-line py-20 text-center"><Sparkles size={30} className="mx-auto text-line" /><h3 className="mt-3 text-sm font-semibold text-text">还没有任务</h3><p className="mt-1 text-xs text-muted">从全网选题发现或定点来源监控开始。</p></div>
          : <div className="grid gap-5 xl:grid-cols-2">{tasks.map((task) => {
            const meta = typeMeta[task.taskType];
            const Icon = meta.icon;
            const run = latestRuns.get(task.id);
            const running = run && ["QUEUED", "RUNNING"].includes(run.status);
            const result = latestResult(run);
            const outputCount = (result?.topics.length ?? 0) + (result?.updates.length ?? 0);
            return <article key={task.id} className="relative overflow-hidden rounded-2xl border border-line bg-surface p-5">
              <header className="flex items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-canvas text-text"><Icon size={18} /></span><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-[10px] font-semibold tracking-wide text-muted">{meta.label}</span><i className={`h-1.5 w-1.5 rounded-full ${task.enabled ? "bg-teal" : "bg-muted"}`} /><span className="text-[10px] text-muted">{running ? "更新中" : task.enabled ? "已启用" : "已暂停"}</span></div><h3 className="mt-1 truncate text-base font-semibold text-text">{task.name}</h3><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{task.taskType === "topic-recommendation" ? task.topicBrief : meta.description}</p></div><button type="button" role="switch" disabled={previewMode} aria-checked={task.enabled} aria-label={`${task.enabled ? "暂停" : "启用"}${task.name}`} onClick={() => toggleMutation.mutate({ id: task.id, enabled: !task.enabled })} className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition disabled:cursor-default ${task.enabled ? "bg-ink" : "bg-line"}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${task.enabled ? "left-6" : "left-1"}`} /></button></header>
              <div className="mt-4 grid gap-2 text-xs text-muted sm:grid-cols-3"><span className="flex items-center gap-1.5 rounded-lg bg-canvas px-2.5 py-2"><CalendarClock size={13} />{formatSchedule(task.schedule)}</span><span className="flex items-center gap-1.5 rounded-lg bg-canvas px-2.5 py-2"><FileText size={13} />{task.taskType === "topic-recommendation" ? `${task.topicCount ?? 5} 个选题 · ${task.sources.length ? `${task.sources.length} 个优先网站` : "全网搜索"}` : `${task.sources.length} 个监控链接`}</span><span className="flex items-center gap-1.5 rounded-lg bg-canvas px-2.5 py-2"><Clock3 size={13} />{task.enabled && task.nextRunAt ? `下次 ${formatTime(task.nextRunAt)}` : task.schedule.type === "manual" ? "仅手动" : "自动更新已暂停"}</span></div>
              <section className="mt-4"><header className="mb-2 flex items-center justify-between"><div><strong className="text-xs text-text">最近输出</strong><span className="ml-2 text-[10px] text-muted">{formatTime(task.lastRunAt)}</span></div>{outputCount ? <button type="button" onClick={() => setResultTaskId(task.id)} className="text-[11px] font-medium text-text">查看全部 {outputCount} 条</button> : null}</header><ResultPreview task={task} run={run} /></section>
              <footer className="mt-4 flex items-center justify-between border-t border-line pt-3"><span className="text-[10px] text-muted">{task.outputFormat}</span><div className="flex gap-2"><button type="button" onClick={() => { setEditorDraft(taskDraft(task)); setEditorError(""); }} className="flex items-center gap-1 rounded-lg px-2.5 py-2 text-xs text-muted hover:bg-canvas hover:text-text"><Pencil size={13} />编辑</button><button type="button" disabled={previewMode || Boolean(running) || runMutation.isPending} onClick={() => runMutation.mutate(task.id)} className="flex items-center gap-1 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white disabled:opacity-45">{running ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}{running ? "正在更新" : "立即更新"}</button></div></footer>
              {running && <span className="absolute inset-x-0 bottom-0 h-0.5 animate-pulse bg-ink" />}
            </article>;
          })}</div>}
        {!previewMode && taskTotalPages > 1 && <nav aria-label="灵感任务分页" className="mt-7 flex items-center justify-center gap-3">
          <button type="button" disabled={taskPage <= 1 || tasksQuery.isFetching} onClick={() => { setResultTaskId(null); setTaskPage((current) => Math.max(1, current - 1)); }} className="workspace-secondary-button min-h-9 px-3 text-xs disabled:opacity-40"><ChevronLeft size={14} />上一页</button>
          <span className="min-w-24 text-center text-xs text-muted">第 {taskPage} / {taskTotalPages} 页</span>
          <button type="button" disabled={taskPage >= taskTotalPages || tasksQuery.isFetching} onClick={() => { setResultTaskId(null); setTaskPage((current) => Math.min(taskTotalPages, current + 1)); }} className="workspace-secondary-button min-h-9 px-3 text-xs disabled:opacity-40">下一页<ChevronRight size={14} /></button>
        </nav>}
      </section>

      {editorDraft && <div className="fixed inset-0 z-[80] grid place-items-center overflow-y-auto bg-ink/50 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditorDraft(null); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="inspiration-editor-title" className="my-4 w-full max-w-2xl overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
          <header className="flex items-start justify-between border-b border-line px-6 py-5"><div><span className="text-[10px] font-semibold tracking-[0.12em] text-muted">{editorDraft.id ? "编辑任务" : "新建任务"}</span><h2 id="inspiration-editor-title" className="mt-1 text-lg font-semibold text-text">设置灵感任务</h2><p className="mt-1 text-xs text-muted">选择一种任务类型，填写它真正需要的信息。</p></div><button type="button" aria-label="关闭" onClick={() => setEditorDraft(null)} className="p-2 text-muted"><X size={18} /></button></header>
          <div className="max-h-[70vh] space-y-6 overflow-y-auto p-6">
            <section><div className="mb-3 flex items-start gap-3"><span className="text-xs font-semibold text-muted">01</span><div><h3 className="text-sm font-semibold text-text">任务类型</h3><p className="text-xs text-muted">一种负责探索，一种负责定点守候。</p></div></div><div className="grid gap-2 sm:grid-cols-2">{(["topic-recommendation", "link-update"] as const).map((type) => { const meta = typeMeta[type]; const Icon = meta.icon; const selected = editorDraft.taskType === type; return <button key={type} type="button" aria-pressed={selected} onClick={() => setEditorDraft({ ...editorDraft, taskType: type, discoveryConfig: { ...editorDraft.discoveryConfig, sourceStrategy: type === "link-update" ? "only" : (editorDraft.sourceText.trim() ? "preferred" : "web") } })} className={`flex items-start gap-3 rounded-xl border p-3 text-left ${selected ? "border-ink bg-canvas" : "border-line"}`}><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface"><Icon size={16} /></span><div className="min-w-0 flex-1"><strong className="text-xs text-text">{meta.label}</strong><p className="mt-1 text-[11px] leading-4 text-muted">{meta.description}</p></div><span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected ? "border-ink bg-ink text-white" : "border-line"}`}>{selected && <Check size={11} />}</span></button>; })}</div></section>
            <section>
              <div className="mb-3 flex items-start gap-3"><span className="text-xs font-semibold text-muted">02</span><div><h3 className="text-sm font-semibold text-text">任务内容</h3><p className="text-xs text-muted">{typeMeta[editorDraft.taskType].description}</p></div></div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-xs font-medium text-muted sm:col-span-2">任务名称<input value={editorDraft.name} maxLength={200} onChange={(event) => setEditorDraft({ ...editorDraft, name: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text" placeholder={editorDraft.taskType === "topic-recommendation" ? "例如：AI 视频创作选题" : "例如：重点产品更新动态"} /></label>
                {editorDraft.taskType === "topic-recommendation" ? <>
                  <label className="block text-xs font-medium text-muted">选题方向<input value={editorDraft.topicBrief} onChange={(event) => setEditorDraft({ ...editorDraft, topicBrief: event.target.value })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text" placeholder="AI 视频创作与工具更新" /></label>
                  <label className="block text-xs font-medium text-muted">每次数量<input type="number" min={1} max={20} value={editorDraft.topicCount ?? 5} onChange={(event) => setEditorDraft({ ...editorDraft, topicCount: Number(event.target.value) })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text" /></label>
                  <label className="block text-xs font-medium text-muted">来源范围<select value={editorDraft.discoveryConfig.sourceStrategy} onChange={(event) => setEditorDraft({ ...editorDraft, discoveryConfig: { ...editorDraft.discoveryConfig, sourceStrategy: event.target.value as inspirationApi.InspirationSourceStrategy } })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text"><option value="web">全网发现</option><option value="preferred">优先指定网站</option><option value="only">仅限指定网站</option></select></label>
                  <label className="block text-xs font-medium text-muted">搜索时间范围<select value={editorDraft.discoveryConfig.searchRecencyDays} onChange={(event) => setEditorDraft({ ...editorDraft, discoveryConfig: { ...editorDraft.discoveryConfig, searchRecencyDays: Number(event.target.value) } })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text"><option value={1}>最近 24 小时</option><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option></select></label>
                  {editorDraft.discoveryConfig.sourceStrategy !== "web" && <label className="block text-xs font-medium text-muted sm:col-span-2">{editorDraft.discoveryConfig.sourceStrategy === "only" ? "限定网站" : "最高优先级网站"}<span className="ml-2 font-normal">每行一个 HTTPS 网站或页面</span><textarea rows={4} value={editorDraft.sourceText} onChange={(event) => setEditorDraft({ ...editorDraft, sourceText: event.target.value })} className="mt-1.5 w-full resize-y rounded-lg border border-line px-3 py-2.5 text-sm leading-6 text-text" placeholder={"https://example.com/blog/\nhttps://example.com/changelog"} /><span className="mt-1.5 block text-[11px] font-normal leading-5">Agent 会优先做站点限定搜索并保留抓取预算；没有近期有效内容时不会强行推荐。</span></label>}
                </> : <>
                  <label className="block text-xs font-medium text-muted sm:col-span-2">需要监控的链接<span className="ml-2 font-normal">每行一个 HTTPS 链接</span><textarea rows={5} value={editorDraft.sourceText} onChange={(event) => setEditorDraft({ ...editorDraft, sourceText: event.target.value })} className="mt-1.5 w-full resize-y rounded-lg border border-line px-3 py-2.5 text-sm leading-6 text-text" placeholder={"https://example.com/feed.xml\nhttps://example.com/changelog"} /><span className="mt-1.5 block text-[11px] font-normal leading-5">首次运行只建立基线；首页会按新增条目比较，排序变化和页面噪声不会作为动态。</span></label>
                  <label className="block text-xs font-medium text-muted sm:col-span-2">关注重点<span className="ml-2 font-normal">可选</span><textarea rows={3} value={editorDraft.discoveryConfig.monitorBrief} onChange={(event) => setEditorDraft({ ...editorDraft, discoveryConfig: { ...editorDraft.discoveryConfig, monitorBrief: event.target.value } })} className="mt-1.5 w-full resize-y rounded-lg border border-line px-3 py-2.5 text-sm leading-6 text-text" placeholder="例如：只关注新版本、AI 视频功能和价格调整，忽略活动宣传。" /></label>
                </>}
                <div className="rounded-xl bg-canvas p-3 sm:col-span-2"><span className="text-[10px] text-muted">固定输出</span><strong className="mt-1 block text-xs text-text">{editorDraft.taskType === "topic-recommendation" ? "联网发现的可执行选题 + 真实参考外链" : "经过新旧差异验证的动态 + 原文证据"}</strong></div>
              </div>
            </section>
            <section><div className="mb-3 flex items-start gap-3"><span className="text-xs font-semibold text-muted">03</span><div><h3 className="text-sm font-semibold text-text">自动更新时间</h3><p className="text-xs text-muted">服务端按 Asia/Shanghai 调度，页面关闭后仍会执行。</p></div></div><div className="grid gap-3 sm:grid-cols-3"><label className="text-xs font-medium text-muted">更新频率<select value={editorDraft.schedule.type} onChange={(event) => setEditorDraft({ ...editorDraft, schedule: { ...editorDraft.schedule, type: event.target.value as inspirationApi.InspirationScheduleType } })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text"><option value="daily">每天</option><option value="weekly">每周</option><option value="manual">仅手动</option></select></label>{editorDraft.schedule.type === "weekly" && <label className="text-xs font-medium text-muted">更新日期<select value={editorDraft.schedule.weekday} onChange={(event) => setEditorDraft({ ...editorDraft, schedule: { ...editorDraft.schedule, weekday: Number(event.target.value) } })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text">{weekdays.map((day) => <option key={day.value} value={day.value}>{day.label}</option>)}</select></label>}{editorDraft.schedule.type !== "manual" && <label className="text-xs font-medium text-muted">更新时间<input type="time" value={editorDraft.schedule.time} onChange={(event) => setEditorDraft({ ...editorDraft, schedule: { ...editorDraft.schedule, time: event.target.value } })} className="mt-1.5 w-full rounded-lg border border-line px-3 py-2.5 text-sm text-text" /></label>}</div><div className="mt-3 flex items-center gap-3 rounded-xl bg-canvas p-3"><CalendarClock size={16} /><div><span className="block text-[10px] text-muted">保存后的执行计划</span><strong className="text-xs text-text">{formatSchedule(editorDraft.schedule)}</strong></div><span className="ml-auto text-[10px] text-muted">Asia/Shanghai</span></div></section>
            {editorError && <p role="alert" className="rounded-lg bg-red/5 px-3 py-2 text-xs text-red">{editorError}</p>}
          </div>
          <footer className="flex items-center justify-between border-t border-line px-6 py-4"><div>{editorDraft.id && <button type="button" disabled={previewMode || deleteMutation.isPending} onClick={() => window.confirm("确认删除该任务及其运行历史？") && deleteMutation.mutate(editorDraft.id!)} className="flex items-center gap-1.5 text-xs text-red disabled:opacity-45"><Trash2 size={14} />删除任务</button>}</div><div className="flex gap-2"><button type="button" onClick={() => setEditorDraft(null)} className="workspace-secondary-button min-h-10 px-4">取消</button><button type="button" disabled={previewMode || saveMutation.isPending} onClick={saveEditor} className="workspace-primary-button min-h-10 px-4">{saveMutation.isPending && <Loader2 size={14} className="animate-spin" />}{previewMode ? "预览模式" : "保存任务"}</button></div></footer>
        </section>
      </div>}

      {resultTask && <div className="fixed inset-0 z-[80] flex justify-end bg-ink/45 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) setResultTaskId(null); }}><aside role="dialog" aria-modal="true" aria-labelledby="inspiration-result-title" className="h-full w-full max-w-2xl overflow-y-auto bg-surface p-6 shadow-soft"><header className="flex items-start gap-3 border-b border-line pb-5"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-canvas">{resultTask.taskType === "topic-recommendation" ? <Sparkles size={18} /> : <Link2 size={18} />}</span><div className="min-w-0 flex-1"><span className="text-[10px] font-semibold text-muted">{typeMeta[resultTask.taskType].label} · {formatTime(resultTask.lastRunAt)}</span><h2 id="inspiration-result-title" className="mt-1 text-lg font-semibold text-text">{latestResult(resultRun)?.title ?? resultTask.name}</h2><p className="mt-1 text-xs leading-5 text-muted">{latestResult(resultRun)?.summary ?? emptyOutcomeCopy(resultRun)}</p></div><button type="button" aria-label="关闭" onClick={() => setResultTaskId(null)} className="p-2 text-muted"><X size={18} /></button></header><div className="space-y-3 py-5">{resultTask.taskType === "topic-recommendation" ? latestResult(resultRun)?.topics.map((topic) => <article key={topic.id} className="flex gap-3 rounded-xl border border-line p-4"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink text-xs font-semibold text-white">{String(topic.order).padStart(2, "0")}</span><div className="min-w-0"><span className="text-[10px] font-medium text-muted">{topic.angle}</span><h3 className="mt-1 text-sm font-semibold text-text">{topic.title}</h3><p className="mt-2 text-xs leading-5 text-muted">{topic.summary}</p>{topic.whyNow && <p className="mt-3 rounded-lg bg-canvas px-3 py-2 text-xs leading-5 text-text"><span className="font-semibold">为什么现在值得做：</span>{topic.whyNow}</p>}{topic.hook && <p className="mt-2 text-xs leading-5 text-muted"><span className="font-semibold text-text">开场建议：</span>{topic.hook}</p>}<div className="mt-3 flex flex-wrap gap-2">{topic.references.map((reference) => <a key={reference.url} href={reference.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-full bg-canvas px-2.5 py-1 text-[10px] text-text">{reference.label}<ArrowUpRight size={11} /></a>)}</div></div></article>) : latestResult(resultRun)?.updates.map((update) => <article key={update.id} className="rounded-xl border border-line p-4"><span className="flex items-center gap-1 text-[10px] font-medium text-muted"><Link2 size={12} />{update.source}{update.changeType ? ` · ${update.changeType}` : ""}</span><h3 className="mt-2 text-sm font-semibold text-text">{update.title}</h3><p className="mt-2 text-xs leading-5 text-muted">{update.summary}</p>{Boolean(update.evidence?.length) && <div className="mt-3 rounded-lg bg-canvas p-3"><span className="text-[10px] font-semibold text-muted">变化证据</span>{update.evidence?.slice(0, 3).map((item, index) => <p key={`${update.id}-evidence-${index}`} className="mt-1.5 text-xs leading-5 text-text">{item.title || item.text}</p>)}</div>}<a href={update.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-text">查看原文<ExternalLink size={12} /></a></article>)}{!latestResult(resultRun) && <div className="py-20 text-center text-sm text-muted">{emptyOutcomeCopy(resultRun)}</div>}</div></aside></div>}
    </div>
  );
}
