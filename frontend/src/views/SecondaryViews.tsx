// ──────────────────────────────────────────────
// OpenVMA - 项目中心列表 (ProjectsView)
// 页头 + 新建项目按钮 + 工具栏(搜索/视图切换) + 项目卡片
// ──────────────────────────────────────────────

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/router";
import {
  Clapperboard,
  Clock3,
  FileVideo,
  FolderKanban,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import * as projectApi from "@/api/projects";
import { useProjectStore } from "@/stores/projectStore";
import { useUIStore } from "@/stores/uiStore";
import { VideoThumb } from "@/components/VideoThumb";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";

export function ProjectsView() {
  const navigate = useNavigate();
  const { setCurrentProject } = useProjectStore();
  const { openProjectCreate } = useUIStore();
  const notify = useUIStore((state) => state.notify);
  const queryClient = useQueryClient();
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("search") ?? "";
  const view = searchParams.get("view") === "list" ? "list" : "grid";

  function updateQuery(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  }

  const projectsQuery = useQuery({
    queryKey: ["projects", search],
    queryFn: () => projectApi.list({ search: search || undefined }),
    retry: false,
  });
  const projects = projectsQuery.data?.items ?? [];
  const isLoading = projectsQuery.isLoading;

  function openProject(projectId: string) {
    setCurrentProject(projectId);
    navigate(`/workspace/projects/${projectId}`);
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 页头 */}
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">项目中心</h1>
          <p className="mt-1.5 text-sm text-muted">管理所有视频项目，组织素材、脚本与初剪</p>
        </div>
        <button
          onClick={openProjectCreate}
          className="flex items-center gap-2 rounded-lg bg-blue px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2"
          type="button"
        >
          <Plus size={16} />新建项目
        </button>
      </header>

      {/* 工具栏 */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-3 shadow-soft">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => updateQuery("search", e.target.value)}
            placeholder="搜索项目名称或描述…"
            className="w-full rounded-lg border border-line bg-canvas/40 py-2 pl-9 pr-3 text-sm text-text placeholder:text-muted transition focus:border-blue focus:bg-surface focus:ring-2 focus:ring-blue/10"
          />
        </div>
        <div className="flex gap-1 rounded-lg bg-canvas p-1">
          <button
            onClick={() => updateQuery("view", "")}
            className={`flex h-8 w-8 items-center justify-center rounded transition ${view === "grid" ? "bg-surface text-blue shadow-sm" : "text-muted"}`}
            aria-label="宫格视图"
            type="button"
          >
            <LayoutGrid size={16} />
          </button>
          <button
            onClick={() => updateQuery("view", "list")}
            className={`flex h-8 w-8 items-center justify-center rounded transition ${view === "list" ? "bg-surface text-blue shadow-sm" : "text-muted"}`}
            aria-label="列表视图"
            type="button"
          >
            <List size={16} />
          </button>
        </div>
      </div>

      {/* 项目列表 */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 size={24} className="animate-spin text-muted" /></div>
      ) : projectsQuery.isError ? (
        <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">项目列表加载失败</p>
          <p className="mt-1 text-xs text-muted">{projectsQuery.error instanceof Error ? projectsQuery.error.message : "请检查后端服务"}</p>
          <button type="button" onClick={() => void projectsQuery.refetch()} className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white">
            重试
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line py-20 text-center">
          <FolderKanban size={32} className="mx-auto text-line" />
          <p className="mt-3 text-sm text-muted">还没有项目，点击右上角创建</p>
        </div>
      ) : view === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <article
              key={project.id}
              onClick={() => openProject(project.id)}
              onKeyDown={(event) => event.key === "Enter" && openProject(project.id)}
              className="group overflow-hidden rounded-2xl border border-line bg-surface text-left shadow-soft transition hover:-translate-y-0.5 hover:border-blue/40"
              role="button"
              tabIndex={0}
            >
              <div className="relative">
                <VideoThumb variant={project.variant} rounded="rounded-none" />
                <span className="absolute left-3 top-3 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-sm">
                  {project.status}
                </span>
                <span className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-sm font-semibold text-white backdrop-blur-sm">
                  {project.initial}
                </span>
                {project.currentUserRole === "owner" && (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setDeleteProjectId(project.id);
                    }}
                    className="absolute bottom-3 right-3 rounded-lg bg-ink/65 p-2 text-white/80 opacity-0 backdrop-blur-sm transition hover:bg-red hover:text-white group-hover:opacity-100"
                    aria-label={`删除项目 ${project.name}`}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              <div className="p-4">
                <strong className="block text-sm font-semibold text-text">{project.name}</strong>
                <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">{project.description}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-lg bg-canvas/60 py-1.5">
                    <FileVideo size={13} className="mx-auto text-blue" />
                    <span className="mt-0.5 block text-xs font-medium text-text">{project.assetCount}</span>
                  </div>
                  <div className="rounded-lg bg-canvas/60 py-1.5">
                    <Sparkles size={13} className="mx-auto text-teal" />
                    <span className="mt-0.5 block text-xs font-medium text-text">{project.clipCount}</span>
                  </div>
                  <div className="rounded-lg bg-canvas/60 py-1.5">
                    <Clapperboard size={13} className="mx-auto text-amber" />
                    <span className="mt-0.5 block text-xs font-medium text-text">{project.scriptCount}</span>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <div className="flex items-center">
                    {project.members.slice(0, 3).map((m, idx) => (
                      <span
                        key={idx}
                        className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-[11px] font-medium text-white"
                        style={{ marginLeft: idx > 0 ? -8 : 0 }}
                      >
                        {m}
                      </span>
                    ))}
                    {project.members.length > 3 && (
                      <span className="ml-1 text-[11px] text-muted">+{project.members.length - 3}</span>
                    )}
                  </div>
                  <span className="flex items-center gap-1 text-[11px] text-muted">
                    <Clock3 size={11} />{project.updatedAt}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-canvas/40 text-left text-xs text-muted">
                <th className="px-4 py-3 font-medium">项目名称</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">素材</th>
                <th className="px-4 py-3 font-medium">片段</th>
                <th className="px-4 py-3 font-medium">成员</th>
                <th className="px-4 py-3 font-medium">更新时间</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr
                  key={project.id}
                  onClick={() => openProject(project.id)}
                  className="cursor-pointer border-b border-line/60 transition hover:bg-canvas/40"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal text-xs font-semibold text-white">
                        {project.initial}
                      </span>
                      <span className="font-medium text-text">{project.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted">{project.type}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">
                      {project.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted">{project.assetCount}</td>
                  <td className="px-4 py-3 text-muted">{project.clipCount}</td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1 text-muted">
                      <Users size={13} />{project.members.length}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted">{project.updatedAt}</td>
                  <td className="px-4 py-3">
                    {project.currentUserRole === "owner" && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setDeleteProjectId(project.id);
                        }}
                        className="rounded-lg p-1.5 text-muted hover:bg-red/10 hover:text-red"
                        aria-label={`删除项目 ${project.name}`}
                      ><Trash2 size={14} /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <DeleteConfirmModal
        open={Boolean(deleteProjectId)}
        entityLabel="项目"
        requireName
        loadImpact={() => projectApi.getDeleteImpact(deleteProjectId!)}
        onDelete={() => projectApi.remove(deleteProjectId!)}
        onClose={() => setDeleteProjectId(null)}
        onDeleted={() => {
          void queryClient.invalidateQueries({ queryKey: ["projects"] });
          notify("项目已删除");
        }}
      />
    </div>
  );
}

export default ProjectsView;
