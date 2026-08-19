import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Clock3,
  Compass,
  FileText,
  FolderPlus,
  Grid2X2,
  Images,
  List,
  Loader2,
  MoreHorizontal,
  Pencil,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useNavigate } from "@/router";
import * as projectApi from "@/api/projects";
import type { Project } from "@/api/projects";
import { useUIStore, type ProjectStartMethod } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { VideoThumb } from "@/components/VideoThumb";
import { formatTime } from "@/lib/utils";

const statusLabels: Record<string, string> = {
  draft: "草稿",
  editing: "编辑中",
  processing: "处理中",
  ready: "可导出",
  exporting: "导出中",
  failed: "失败",
};

const startPaths = [
  {
    id: "write-script" as const,
    eyebrow: "已有脚本 / 文案",
    title: ["从脚本开始，", "生成可编辑视频"],
    description: "导入文章、口播稿或视频脚本，在项目中整理场景与镜头，再匹配或生成合适画面。",
    scenarios: ["只会写文案", "没有素材", "不擅长拍摄"],
    action: "从脚本开始",
    icon: FileText,
    tone: "script",
  },
  {
    id: "upload-assets" as const,
    eyebrow: "已有拍摄素材",
    title: ["从素材开始，", "AI 辅助编排影片"],
    description: "导入已有图片、音频或视频，先完成素材理解，再围绕脚本场景组织可编辑主成片。",
    scenarios: ["素材太多", "缺少剪辑灵感", "不擅长剪辑"],
    action: "从素材开始",
    icon: Images,
    tone: "assets",
  },
] as const;

function ProjectCard({
  project,
  viewMode,
  recent,
  menuOpen,
  onOpen,
  onToggleMenu,
  onEdit,
  onDelete,
  deleting,
}: {
  project: Project;
  viewMode: "grid" | "list";
  recent: boolean;
  menuOpen: boolean;
  onOpen: () => void;
  onToggleMenu: () => void;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const list = viewMode === "list";
  const previewImage = project.coverThumbnailUrl
    ?? (project.coverMediaType === "image" ? project.coverMediaUrl : undefined);
  const previewVideo = !previewImage && project.coverMediaType === "video"
    ? project.coverMediaUrl
    : undefined;

  function openFromKeyboard(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onOpen();
  }

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={openFromKeyboard}
      className={`group relative cursor-pointer overflow-hidden rounded-2xl border border-line bg-white text-left transition hover:-translate-y-0.5 hover:border-[#c6c6c9] hover:shadow-[0_16px_42px_rgba(0,0,0,.09)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${list ? "grid min-h-[174px] grid-cols-[220px_minmax(0,1fr)] max-md:grid-cols-1" : ""}`}
      aria-label={`打开项目：${project.name}`}
    >
      <div className={`relative overflow-hidden bg-canvas ${list ? "h-full min-h-[174px] max-md:aspect-video max-md:min-h-0" : "aspect-[16/9]"}`}>
        <VideoThumb
          fill
          imageUrl={previewImage}
          videoUrl={previewVideo}
          showPlay={false}
          className="!rounded-none"
        />
        <span className="absolute inset-x-0 top-0 flex items-start justify-between p-3">
          <span className="rounded-md bg-black/65 px-2 py-1 text-[9px] font-semibold tracking-[0.08em] text-white backdrop-blur">
            {project.coverMediaType?.toUpperCase() ?? "PROJECT"}
          </span>
          {recent && <span className="rounded-full bg-black/65 px-2.5 py-1 text-[10px] font-medium text-white backdrop-blur">最近打开</span>}
        </span>
      </div>

      <div className={`relative min-w-0 ${list ? "grid grid-cols-[minmax(0,1fr)_310px] gap-6 p-5 max-xl:grid-cols-1" : "p-4"}`}>
        <div className="min-w-0">
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-[11px] font-medium text-muted">{project.type}</span>
            <div className="relative" onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                onClick={onToggleMenu}
                className={`grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-canvas hover:text-text ${menuOpen ? "bg-canvas text-text" : ""}`}
                aria-label={`更多项目操作：${project.name}`}
                aria-expanded={menuOpen}
              >
                <MoreHorizontal size={18} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-9 z-20 w-44 overflow-hidden rounded-xl border border-line bg-white py-1.5 shadow-soft" role="menu">
                  <button type="button" onClick={onEdit} className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-xs text-text transition hover:bg-canvas" role="menuitem"><Pencil size={14} />编辑项目信息</button>
                  <button type="button" onClick={onDelete} disabled={deleting} className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-xs text-red transition hover:bg-red/5 disabled:opacity-50" role="menuitem"><Trash2 size={14} />删除项目</button>
                </div>
              )}
            </div>
          </div>

          <h2 className="mt-2 flex items-center gap-1 text-[17px] font-semibold tracking-[-0.025em] text-text">
            <span className="truncate">{project.name}</span><ArrowRight size={15} className="shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-text" />
          </h2>
          <p className={`mt-1.5 text-xs leading-5 text-muted ${list ? "line-clamp-2" : "line-clamp-2 min-h-10"}`}>{project.description || "尚未填写项目说明"}</p>
        </div>

        <div className={list ? "flex min-w-0 flex-col justify-between" : ""}>
          <div className={`grid grid-cols-3 divide-x divide-line rounded-xl border border-line bg-[#fbfbfc] ${list ? "mt-0" : "mt-4"}`}>
            <span className="flex min-w-0 items-center gap-2 px-3 py-2.5"><Clock3 size={14} className="shrink-0 text-muted" /><span className="min-w-0"><strong className="block truncate text-xs text-text">{formatTime(project.durationMs / 1000)}</strong><small className="block text-[9px] text-muted">{project.aspectRatio}</small></span></span>
            <span className="px-3 py-2.5 text-center"><strong className="block text-xs text-text">{project.sceneCount}</strong><small className="text-[9px] text-muted">场景</small></span>
            <span className="px-3 py-2.5 text-center"><strong className="block text-xs text-text">{project.matchedPercent}%</strong><small className="text-[9px] text-muted">画面匹配</small></span>
          </div>
          <footer className={`flex items-center justify-between gap-3 border-t border-line text-[10px] text-muted ${list ? "mt-4 pt-3" : "mt-4 pt-3"}`}>
            <span className="flex min-w-0 items-center gap-1"><Clock3 size={12} className="shrink-0" /><span className="truncate">{project.updatedAt}</span></span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 font-medium ${project.status === "failed" ? "bg-red/10 text-red" : project.status === "ready" ? "bg-teal/10 text-teal" : "bg-canvas text-text"}`}>{statusLabels[project.status] ?? project.status}</span>
          </footer>
        </div>
      </div>
    </article>
  );
}

export default function HomeDashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { openProjectCreate, openProjectEdit, notify } = useUIStore();
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [openMenuProjectId, setOpenMenuProjectId] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!openMenuProjectId) return undefined;
    function closeMenu(event: PointerEvent) {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest('[aria-label^="更多项目操作："]')) return;
      if (target?.closest('[role="menu"]')) return;
      setOpenMenuProjectId(null);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenMenuProjectId(null);
    }
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [openMenuProjectId]);

  const projectsQuery = useQuery({
    queryKey: ["projects", "workbench", debouncedSearch],
    queryFn: () => projectApi.list({ search: debouncedSearch || undefined, pageSize: 100 }),
    retry: false,
  });
  const projects = useMemo(() => projectsQuery.data?.items ?? [], [projectsQuery.data?.items]);

  const deleteMutation = useMutation({
    mutationFn: projectApi.remove,
    onSuccess: async (_, projectId) => {
      setOpenMenuProjectId(null);
      if (currentProjectId === projectId) setCurrentProject(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
      ]);
      notify("项目已删除");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "项目删除失败", "error"),
  });

  function openProject(projectId: string) {
    setCurrentProject(projectId);
    navigate(`/workspace/projects/${projectId}`);
  }

  function startProject(intent: ProjectStartMethod) {
    openProjectCreate(intent);
  }

  function deleteProject(project: Project) {
    setOpenMenuProjectId(null);
    if (!window.confirm(`确认删除项目“${project.name}”？项目脚本、镜头和成片设置将一并删除，公共素材仍保留在素材库中。`)) return;
    deleteMutation.mutate(project.id);
  }

  return (
    <div className="mx-auto w-full max-w-[1280px] px-5 pb-16 pt-8 sm:px-7 lg:px-8 lg:pt-10">
      <section aria-labelledby="workspace-start-title">
        <header className="max-w-4xl">
          <h1 id="workspace-start-title" className="text-[32px] font-semibold leading-tight tracking-[-0.045em] text-text sm:text-[38px]">从你已经有的内容开始</h1>
          <p className="mt-2.5 max-w-4xl text-sm leading-6 text-muted">一个项目就是一支视频。无论已有脚本还是素材，都先填写项目信息，再进入同一个脚本编排工作台，边组织镜头、边处理素材、边实时预览成片。</p>
        </header>

        <div className="mt-7 grid gap-4 lg:grid-cols-2">
          {startPaths.map((path) => {
            const Icon = path.icon;
            const scriptTone = path.tone === "script";
            return (
              <button
                key={path.id}
                type="button"
                onClick={() => startProject(path.id)}
                className={`group grid min-h-[290px] grid-rows-[1fr_auto] rounded-[20px] border p-6 text-left transition hover:-translate-y-0.5 hover:shadow-[0_18px_46px_rgba(0,0,0,.08)] sm:p-7 ${scriptTone ? "border-[#d9cff7] bg-gradient-to-br from-[#fbf9ff] to-[#f4efff]" : "border-[#c7e4e8] bg-gradient-to-br from-[#f8fdfd] to-[#eaf8fa]"}`}
              >
                <span className="grid grid-cols-[52px_minmax(0,1fr)] items-start gap-4">
                  <span className={`grid h-[52px] w-[52px] place-items-center rounded-[14px] ${scriptTone ? "bg-[#e9e0ff] text-[#6845ce]" : "bg-[#d9f0f2] text-[#147f88]"}`}><Icon size={25} strokeWidth={1.8} /></span>
                  <span className="min-w-0">
                    <small className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${scriptTone ? "bg-[#e9e0ff] text-[#7653cc]" : "bg-[#d8eff1] text-[#237e85]"}`}>{path.eyebrow}</small>
                    <strong className="mt-4 block text-[23px] font-semibold leading-[1.25] tracking-[-0.035em] text-text sm:text-[26px]"><span>{path.title[0]}</span><span className={scriptTone ? "text-[#6545cb]" : "text-[#147f88]"}>{path.title[1]}</span></strong>
                    <span className="mt-3 block text-sm leading-6 text-muted">{path.description}</span>
                    <span className="mt-4 flex flex-wrap gap-2">{path.scenarios.map((scenario) => <span key={scenario} className={`rounded-full border px-2.5 py-1 text-[10px] font-medium ${scriptTone ? "border-[#ddd2f8] bg-white/50 text-[#7659bc]" : "border-[#c5e3e6] bg-white/50 text-[#317d83]"}`}>{scenario}</span>)}</span>
                  </span>
                </span>
                <span className={`mt-7 flex items-center justify-between border-t pt-4 text-sm font-semibold ${scriptTone ? "border-[#ddd3f3] text-[#6545cb]" : "border-[#c8e2e5] text-[#147f88]"}`}><span>{path.action}</span><span className={`grid h-9 w-9 place-items-center rounded-full transition group-hover:translate-x-0.5 ${scriptTone ? "bg-[#e8e0fb]" : "bg-[#d8eef0]"}`}><ArrowRight size={18} /></span></span>
              </button>
            );
          })}
        </div>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs font-medium text-muted">其他开始方式</span>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => startProject("ai-script")} className="workspace-secondary-button !min-h-10"><Sparkles size={15} />AI 辅助脚本</button>
            <button type="button" onClick={() => startProject("blank")} className="workspace-secondary-button !min-h-10"><FolderPlus size={15} />空白项目</button>
            <button type="button" onClick={() => navigate("/workspace/inspiration")} className="workspace-secondary-button !min-h-10"><Compass size={15} />去灵感岛</button>
          </div>
        </div>
      </section>

      <section className="mt-9 border-t border-line pt-9" aria-labelledby="workspace-projects-title">
        <header>
          <h2 id="workspace-projects-title" className="text-[25px] font-semibold tracking-[-0.035em] text-text">继续上次创作</h2>
          <p className="mt-1.5 text-sm text-muted">打开项目将直接进入脚本编排，继续完善同一支视频与主时间线。</p>
        </header>

        <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-line bg-white p-2.5 sm:flex-row sm:items-center">
          <label className="relative min-w-0 flex-1">
            <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索项目名称、内容类型或描述" aria-label="搜索项目" className="h-11 w-full rounded-[10px] border border-line bg-[#fafafb] pl-10 pr-4 text-sm text-text transition placeholder:text-[#999a9f] focus:border-[#b8b8bc] focus:bg-white focus:ring-2 focus:ring-black/5" />
            {projectsQuery.isFetching && <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-muted" />}
          </label>
          <span className="shrink-0 px-2 text-xs text-muted">共 {projectsQuery.data?.total ?? 0} 个项目</span>
          <div className="flex shrink-0 rounded-[10px] border border-line bg-[#fafafb] p-1" aria-label="项目视图">
            <button type="button" onClick={() => setViewMode("grid")} aria-label="宫格显示" aria-pressed={viewMode === "grid"} className={`grid h-9 w-9 place-items-center rounded-lg transition ${viewMode === "grid" ? "bg-white text-text shadow-sm" : "text-muted hover:text-text"}`}><Grid2X2 size={16} /></button>
            <button type="button" onClick={() => setViewMode("list")} aria-label="列表显示" aria-pressed={viewMode === "list"} className={`grid h-9 w-9 place-items-center rounded-lg transition ${viewMode === "list" ? "bg-white text-text shadow-sm" : "text-muted hover:text-text"}`}><List size={16} /></button>
          </div>
        </div>

        {projectsQuery.isLoading ? (
          <div className="flex justify-center py-28"><Loader2 className="animate-spin text-muted" /></div>
        ) : projectsQuery.error ? (
          <div className="mt-5 rounded-2xl border border-red/20 bg-red/5 py-20 text-center">
            <p className="text-sm font-medium text-red">项目加载失败</p>
            <p className="mt-1 text-xs text-muted">{projectsQuery.error instanceof Error ? projectsQuery.error.message : "请稍后重试"}</p>
            <button type="button" onClick={() => void projectsQuery.refetch()} className="mt-4 rounded-lg border border-red/20 bg-white px-4 py-2 text-xs font-semibold text-red">重新加载</button>
          </div>
        ) : !projects.length ? (
          <div className="mt-5 rounded-2xl border border-dashed border-[#d5d5d8] py-20 text-center">
            <Search size={24} className="mx-auto text-[#b4b4b8]" />
            <p className="mt-3 text-sm font-medium text-text">{debouncedSearch ? "没有找到相关项目" : "还没有项目"}</p>
            <p className="mt-1 text-xs text-muted">{debouncedSearch ? "尝试搜索其他名称、类型或说明。" : "先选择一种创作起点，创建你的第一支视频。"}</p>
            <button type="button" onClick={() => startProject("blank")} className="workspace-primary-button mt-4 !min-h-10"><FolderPlus size={15} />新建项目</button>
          </div>
        ) : (
          <div className={`mt-5 ${viewMode === "grid" ? "grid gap-5 md:grid-cols-2 xl:grid-cols-3" : "space-y-3"}`}>
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                viewMode={viewMode}
                recent={project.id === currentProjectId}
                menuOpen={openMenuProjectId === project.id}
                onOpen={() => openProject(project.id)}
                onToggleMenu={() => setOpenMenuProjectId((current) => current === project.id ? null : project.id)}
                onEdit={() => { setOpenMenuProjectId(null); openProjectEdit(project); }}
                onDelete={() => deleteProject(project)}
                deleting={deleteMutation.isPending && deleteMutation.variables === project.id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
