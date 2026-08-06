// ──────────────────────────────────────────────
// OpenVMA - 项目详情（overview 模式）
// 返回按钮 + 项目头(状态/类型/名称/描述/元信息/成员)
// 统计卡 + 项目脚本区 + 进入剪辑工作区按钮
// ──────────────────────────────────────────────

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "@/router";
import {
  Clapperboard,
  Clock3,
  FileVideo,
  Film,
  FolderKanban,
  Loader2,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import * as projectApi from "@/api/projects";
import * as scriptApi from "@/api/scripts";
import * as assetApi from "@/api/assets";
import { useProjectStore } from "@/stores/projectStore";
import { useScriptStore } from "@/stores/scriptStore";
import { VideoThumb } from "@/components/VideoThumb";
import { ProjectCollaborationModal } from "@/components/ProjectCollaborationModal";
import { BackButton } from "@/components/BackButton";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";
import { useUIStore } from "@/stores/uiStore";

export function ProjectDetailView() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);
  const setCurrentScriptId = useScriptStore((s) => s.setCurrentScriptId);
  const notify = useUIStore((s) => s.notify);
  const queryClient = useQueryClient();
  const [collaborationOpen, setCollaborationOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    if (projectId) setCurrentProject(projectId);
  }, [projectId, setCurrentProject]);

  // 获取项目详情
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectApi.get(projectId!),
    retry: false,
    enabled: !!projectId,
  });

  // 获取项目下的脚本
  const scriptsQuery = useQuery({
    queryKey: ["scripts", projectId],
    queryFn: () => scriptApi.list({ projectId: projectId! }),
    retry: false,
    enabled: !!projectId,
  });
  const scripts = scriptsQuery.data?.items ?? [];

  // 获取项目下的素材
  const assetsQuery = useQuery({
    queryKey: ["assets", projectId],
    queryFn: () => assetApi.list({ projectId: projectId! }),
    retry: false,
    enabled: !!projectId,
  });
  const assets = assetsQuery.data?.items ?? [];
  const project = projectQuery.data;
  const isLoading = projectQuery.isLoading || scriptsQuery.isLoading || assetsQuery.isLoading;
  const loadError = projectQuery.error ?? scriptsQuery.error ?? assetsQuery.error;
  const coverAsset = assets.find((asset) => asset.thumbnailUrl || asset.mediaUrl);

  const stats = [
    { icon: FileVideo, label: "素材", value: project?.assetCount ?? 0, color: "text-blue" },
    { icon: Sparkles, label: "可搜索片段", value: project?.clipCount ?? 0, color: "text-teal" },
    { icon: Clapperboard, label: "脚本", value: project?.scriptCount ?? 0, color: "text-amber" },
  ];

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 返回按钮 */}
      <BackButton
        fallback="/workspace/projects"
        fallbackLabel="项目中心"
        className="mb-5 flex items-center gap-1.5 text-sm text-muted transition hover:text-text"
      />

      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 size={24} className="animate-spin text-muted" /></div>
      ) : loadError ? (
        <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">项目数据加载失败</p>
          <p className="mt-1 text-xs text-muted">{loadError instanceof Error ? loadError.message : "请检查后端服务"}</p>
          <button
            type="button"
            onClick={() => {
              void projectQuery.refetch();
              void scriptsQuery.refetch();
              void assetsQuery.refetch();
            }}
            className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white"
          >
            重试
          </button>
        </div>
      ) : !project ? (
        <div className="rounded-2xl border border-dashed border-line py-20 text-center">
          <FolderKanban size={32} className="mx-auto text-line" />
          <p className="mt-3 text-sm text-muted">未找到项目，请先创建或选择一个项目</p>
        </div>
      ) : (
        <>
          {/* 项目头 */}
          <header className="mb-6 overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
            <div className="relative h-32">
              <VideoThumb
                variant={project.variant}
                imageUrl={coverAsset?.thumbnailUrl}
                videoUrl={coverAsset?.mediaUrl}
                rounded="rounded-none"
                showPlay={false}
                fill
              />
              <div className="absolute inset-0 bg-gradient-to-t from-ink/60 to-transparent" />
              <div className="absolute bottom-4 left-5 flex items-center gap-3">
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface text-lg font-semibold text-blue shadow-soft">
                  {project.initial}
                </span>
                <div className="text-white">
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px] backdrop-blur-sm">
                      {project.status}
                    </span>
                    <span className="text-xs text-white/80">{project.type}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="p-5">
              <div className="flex items-center justify-between gap-4">
                <h1 className="text-xl font-bold text-text">{project.name}</h1>
                {project.currentUserRole === "owner" && (
                  <button
                    type="button"
                    onClick={() => setDeleteOpen(true)}
                    className="flex items-center gap-1.5 rounded-lg border border-red/30 px-3 py-1.5 text-xs font-medium text-red transition hover:bg-red/10"
                  ><Trash2 size={14} />删除项目</button>
                )}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-muted">{project.description}</p>
              <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Clock3 size={13} />更新于 {project.updatedAt}
                </span>
                <span className="flex items-center gap-1">
                  <Users size={13} />{project.members.length} 位成员
                </span>
                <div className="flex items-center gap-1.5">
                  {project.members.map((m, idx) => (
                    <span
                      key={idx}
                      className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-[11px] font-medium text-white"
                      style={{ marginLeft: idx > 0 ? -8 : 0 }}
                    >
                      {m}
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => setCollaborationOpen(true)}
                  className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted transition hover:border-blue/40 hover:text-blue"
                  type="button"
                >
                  {project.currentUserRole === "owner" ? "+ 管理成员" : "查看成员"}
                </button>
                <span className="rounded-full bg-canvas px-2.5 py-0.5 text-[11px] text-muted">
                  当前角色：{{ owner: "所有者", editor: "编辑者", viewer: "查看者" }[project.currentUserRole]}
                </span>
              </div>
            </div>
          </header>

          {/* 统计卡 */}
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div
                  key={stat.label}
                  className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft"
                >
                  <span className={`flex h-11 w-11 items-center justify-center rounded-xl bg-canvas ${stat.color}`}>
                    <Icon size={20} />
                  </span>
                  <div>
                    <strong className="text-xl font-semibold text-text">{stat.value}</strong>
                    <small className="block text-xs text-muted">{stat.label}</small>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 项目脚本区 */}
          <section className="mb-6 rounded-2xl border border-line bg-surface p-5 shadow-soft">
            <header className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clapperboard size={18} className="text-blue" />
                <h2 className="text-base font-semibold text-text">项目脚本</h2>
                <span className="text-xs text-muted">({scripts.length})</span>
              </div>
              <button
                onClick={() => navigate("/workspace/scripts")}
                className="text-xs text-blue transition hover:underline"
                type="button"
              >
                查看全部
              </button>
            </header>
            {scripts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-line py-10 text-center text-sm text-muted">
                暂无脚本，前往脚本中心创建
              </div>
            ) : (
              <ul className="space-y-2.5">
                {scripts.slice(0, 4).map((script) => (
                  <li key={script.id}>
                    <button
                      onClick={() => {
                        setCurrentScriptId(script.id);
                        navigate(`/workspace/scripts/${script.id}/editor`);
                      }}
                      className="group flex w-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3 text-left transition hover:border-blue/40 hover:bg-blue-soft/20"
                      type="button"
                    >
                      <VideoThumb variant={script.variant} className="!h-10 !w-16" rounded="rounded-lg" showPlay={false} />
                      <div className="min-w-0 flex-1">
                        <strong className="block truncate text-sm text-text">{script.title}</strong>
                        <small className="text-xs text-muted">
                          {script.unitCount} 单元 · {script.matchedCount} 已匹配 · {script.duration}
                        </small>
                        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-canvas">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-blue to-teal"
                            style={{ width: `${script.progress}%` }}
                          />
                        </div>
                      </div>
                      <span className="shrink-0 rounded-full bg-blue-soft px-2 py-0.5 text-[11px] text-blue">
                        {script.status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 进入剪辑工作区按钮 */}
          <section className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-blue/20 bg-gradient-to-r from-blue-soft/60 to-teal/10 p-6 sm:flex-row">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue text-white">
                <Film size={22} />
              </span>
              <div>
                <strong className="block text-sm font-semibold text-text">{project.currentUserRole === "viewer" ? "查看剪辑工作区" : "进入剪辑工作区"}</strong>
                <small className="text-xs text-muted">
                  {project.currentUserRole === "viewer" ? "你拥有只读权限，可查看项目内容和时间线" : "在多轨时间线上替换镜头、细化剪辑并导出成片"}
                </small>
              </div>
            </div>
            <button
              onClick={() => navigate(`/workspace/projects/${projectId}/editor`)}
              className="flex items-center gap-2 rounded-xl bg-blue px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-blue-2"
              type="button"
            >
              <FolderKanban size={16} />{project.currentUserRole === "viewer" ? "只读查看" : "打开剪辑工作区"}
            </button>
          </section>
        </>
      )}
      {projectId && (
        <ProjectCollaborationModal
          projectId={projectId}
          open={collaborationOpen}
          onClose={() => setCollaborationOpen(false)}
        />
      )}
      {projectId && (
        <DeleteConfirmModal
          open={deleteOpen}
          entityLabel="项目"
          requireName
          loadImpact={() => projectApi.getDeleteImpact(projectId)}
          onDelete={() => projectApi.remove(projectId)}
          onClose={() => setDeleteOpen(false)}
          onDeleted={() => {
            setCurrentProject(null);
            void queryClient.invalidateQueries({ queryKey: ["projects"] });
            notify("项目已删除");
            navigate("/workspace/projects", { replace: true });
          }}
        />
      )}
    </div>
  );
}

export default ProjectDetailView;
