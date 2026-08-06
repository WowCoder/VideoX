// ──────────────────────────────────────────────
// OpenVMA - 脚本中心（列表态）
// 页头 + 新建脚本按钮 + 工具栏(搜索/项目筛选/状态tab/视图切换)
// 脚本卡片列表
// ──────────────────────────────────────────────

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/router";
import {
  Clapperboard,
  Clock3,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  Search,
  Sparkles,
  Trash2,
  WandSparkles,
} from "lucide-react";
import * as scriptApi from "@/api/scripts";
import * as projectApi from "@/api/projects";
import { useUIStore } from "@/stores/uiStore";
import { useScriptStore } from "@/stores/scriptStore";
import { VideoThumb } from "@/components/VideoThumb";
import type { Script, ScriptStatus } from "@/types/models";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";

const statusTabs: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "编辑中", label: "编辑中" },
  { value: "待匹配", label: "待匹配" },
  { value: "待确认", label: "待确认" },
  { value: "已完成", label: "已完成" },
];

const statusBadgeClass: Record<ScriptStatus, string> = {
  编辑中: "bg-blue-soft text-blue",
  待匹配: "bg-amber/10 text-amber",
  待确认: "bg-violet-100 text-violet-600",
  已完成: "bg-teal/10 text-teal",
  初剪生成中: "bg-blue-soft text-blue",
  初剪可编辑: "bg-teal/10 text-teal",
};

export function ScriptCenterView() {
  const navigate = useNavigate();
  const { openScriptCreate, openAIScript, notify } = useUIStore();
  const queryClient = useQueryClient();
  const [deleteScriptId, setDeleteScriptId] = useState<string | null>(null);
  const setCurrentScriptId = useScriptStore((s) => s.setCurrentScriptId);
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("search") ?? "";
  const projectFilter = searchParams.get("project") ?? "";
  const statusFilter = searchParams.get("status") ?? "";
  const view = searchParams.get("view") === "list" ? "list" : "grid";

  function updateQuery(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  }

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectApi.list(),
    retry: false,
  });
  const projects = projectsQuery.data?.items ?? [];

  const scriptsQuery = useQuery({
    queryKey: ["scripts", projectFilter, search, statusFilter],
    queryFn: () =>
      scriptApi.list({
        projectId: projectFilter || undefined,
        search: search || undefined,
        status: statusFilter || undefined,
      }),
    retry: false,
  });
  const scripts = scriptsQuery.data?.items ?? [];
  const isLoading = scriptsQuery.isLoading;
  const loadError = scriptsQuery.error ?? projectsQuery.error;

  function openScript(script: Script) {
    setCurrentScriptId(script.id);
    notify(`已打开脚本"${script.title}"`);
    navigate(`/workspace/scripts/${script.id}/editor`);
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 页头 */}
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">脚本中心</h1>
          <p className="mt-1.5 text-sm text-muted">管理所有项目的脚本，连接素材匹配与初剪生成</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => openAIScript()}
            className="flex items-center gap-2 rounded-lg border border-blue bg-blue-soft px-4 py-2.5 text-sm font-semibold text-blue transition hover:bg-blue hover:text-white"
            type="button"
          >
            <WandSparkles size={16} />AI 生成
          </button>
          <button
            onClick={openScriptCreate}
            className="flex items-center gap-2 rounded-lg bg-blue px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2"
            type="button"
          >
            <Plus size={16} />新建脚本
          </button>
        </div>
      </header>

      {/* 工具栏 */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-3 shadow-soft">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => updateQuery("search", e.target.value)}
            placeholder="搜索脚本标题、摘要或台词…"
            className="w-full rounded-lg border border-line bg-canvas/40 py-2 pl-9 pr-3 text-sm text-text placeholder:text-muted transition focus:border-blue focus:bg-surface focus:ring-2 focus:ring-blue/10"
          />
        </div>
        <select
          value={projectFilter}
          onChange={(e) => updateQuery("project", e.target.value)}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-text transition focus:border-blue"
        >
          <option value="">全部项目</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
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

      {/* 状态 tab */}
      <div className="mb-5 flex flex-wrap gap-1.5">
        {statusTabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => updateQuery("status", tab.value)}
            className={`rounded-full px-3.5 py-1.5 text-sm transition ${
              statusFilter === tab.value
                ? "bg-blue text-white"
                : "bg-surface text-muted border border-line hover:text-text"
            }`}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 脚本列表 */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 size={24} className="animate-spin text-muted" /></div>
      ) : loadError ? (
        <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">脚本列表加载失败</p>
          <p className="mt-1 text-xs text-muted">{loadError instanceof Error ? loadError.message : "请检查后端服务"}</p>
          <button
            type="button"
            onClick={() => {
              void projectsQuery.refetch();
              void scriptsQuery.refetch();
            }}
            className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white"
          >
            重试
          </button>
        </div>
      ) : scripts.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line py-20 text-center">
          <Clapperboard size={32} className="mx-auto text-line" />
          <p className="mt-3 text-sm text-muted">还没有脚本，点击右上角创建</p>
        </div>
      ) : view === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {scripts.map((script) => {
            const project = projects.find((p) => p.id === script.projectId);
            return (
              <article
                key={script.id}
                onClick={() => openScript(script)}
                onKeyDown={(event) => event.key === "Enter" && openScript(script)}
                className="group overflow-hidden rounded-2xl border border-line bg-surface text-left shadow-soft transition hover:-translate-y-0.5 hover:border-blue/40"
                role="button"
                tabIndex={0}
              >
                <div className="relative">
                  <VideoThumb variant={script.variant} rounded="rounded-none" />
                  <span className="absolute left-3 top-3 rounded-full bg-ink/70 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-sm">
                    {script.format}
                  </span>
                  <span className={`absolute right-3 top-3 rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeClass[script.status]}`}>
                    {script.status}
                  </span>
                  {project?.currentUserRole !== "viewer" && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteScriptId(script.id);
                      }}
                      className="absolute bottom-3 right-3 rounded-lg bg-ink/65 p-2 text-white/80 opacity-0 backdrop-blur-sm transition hover:bg-red hover:text-white group-hover:opacity-100"
                      aria-label={`删除脚本 ${script.title}`}
                    ><Trash2 size={14} /></button>
                  )}
                </div>
                <div className="p-4">
                  <strong className="block text-sm font-semibold text-text">{script.title}</strong>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">{script.summary}</p>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-muted">{project?.name ?? "—"}</span>
                    <span className="flex items-center gap-1 text-xs text-muted">
                      <Clock3 size={12} />{script.duration}
                    </span>
                  </div>
                  <div className="mt-2.5">
                    <div className="flex items-center justify-between text-[11px] text-muted">
                      <span>{script.matchedCount}/{script.unitCount} 单元匹配</span>
                      <span>{script.progress}%</span>
                    </div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-canvas">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-blue to-teal"
                        style={{ width: `${script.progress}%` }}
                      />
                    </div>
                  </div>
                  <small className="mt-2.5 block text-[11px] text-muted">更新于 {script.updatedAt}</small>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-canvas/40 text-left text-xs text-muted">
                <th className="px-4 py-3 font-medium">脚本标题</th>
                <th className="px-4 py-3 font-medium">所属项目</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">格式</th>
                <th className="px-4 py-3 font-medium">进度</th>
                <th className="px-4 py-3 font-medium">更新时间</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {scripts.map((script) => {
                const project = projects.find((p) => p.id === script.projectId);
                return (
                  <tr
                    key={script.id}
                    onClick={() => openScript(script)}
                    className="cursor-pointer border-b border-line/60 transition hover:bg-canvas/40"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-soft text-blue">
                          <Sparkles size={14} />
                        </span>
                        <div className="min-w-0">
                          <span className="block font-medium text-text">{script.title}</span>
                          {script.summary && <span className="mt-0.5 block max-w-md truncate text-xs text-muted">{script.summary}</span>}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted">{project?.name ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${statusBadgeClass[script.status]}`}>
                        {script.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted">{script.format}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1 w-16 overflow-hidden rounded-full bg-canvas">
                          <div className="h-full rounded-full bg-blue" style={{ width: `${script.progress}%` }} />
                        </div>
                        <span className="text-xs text-muted">{script.progress}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted">{script.updatedAt}</td>
                    <td className="px-4 py-3">
                      {project?.currentUserRole !== "viewer" && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setDeleteScriptId(script.id);
                          }}
                          className="rounded-lg p-1.5 text-muted hover:bg-red/10 hover:text-red"
                          aria-label={`删除脚本 ${script.title}`}
                        ><Trash2 size={14} /></button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <DeleteConfirmModal
        open={Boolean(deleteScriptId)}
        entityLabel="脚本"
        loadImpact={() => scriptApi.getDeleteImpact(deleteScriptId!)}
        onDelete={() => scriptApi.remove(deleteScriptId!)}
        onClose={() => setDeleteScriptId(null)}
        onDeleted={() => {
          void queryClient.invalidateQueries({ queryKey: ["scripts"] });
          void queryClient.invalidateQueries({ queryKey: ["projects"] });
          notify("脚本已删除");
        }}
      />
    </div>
  );
}

export default ScriptCenterView;
