import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock3,
  FileAudio,
  Film,
  Grid2X2,
  Image as ImageIcon,
  Link2,
  List,
  Loader2,
  Search,
  SlidersHorizontal,
  Trash2,
  Unlink,
  Upload,
  X,
} from "lucide-react";
import * as assetApi from "@/api/assets";
import * as projectApi from "@/api/projects";
import type { Project } from "@/api/projects";
import { VideoThumb } from "@/components/VideoThumb";
import { useUIStore } from "@/stores/uiStore";

type SourceFilter = "all" | assetApi.AssetSourceCategory;
type ContentFilter = "all" | assetApi.AssetContentType;
type ViewMode = "grid" | "list";

const sourceFilters: Array<{ id: SourceFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "ai", label: "AI 素材" },
  { id: "non-ai", label: "非 AI 素材" },
];
const formatFilters: Array<{ id: assetApi.MediaType | ""; label: string }> = [
  { id: "", label: "全部" },
  { id: "audio", label: "音频" },
  { id: "image", label: "图片" },
  { id: "video", label: "视频" },
];
const contentFilters: Array<{ id: ContentFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "scene", label: "场景" },
  { id: "role", label: "角色" },
  { id: "object", label: "物品" },
  { id: "event", label: "事件" },
];
const mediaLabels: Record<assetApi.MediaType, string> = { image: "图片", video: "视频", audio: "音频" };
const contentLabels: Record<assetApi.AssetContentType, string> = { scene: "场景", role: "角色", object: "物品", event: "事件" };

function formatDuration(ms: number) {
  if (!ms) return "静态图片";
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function FilterGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ id: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex min-w-0 items-center gap-3">
      <legend className="sr-only">{label}</legend>
      <span className="w-9 shrink-0 text-xs font-medium text-muted">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.id || "all"}
            type="button"
            aria-pressed={value === option.id}
            onClick={() => onChange(option.id)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              value === option.id ? "bg-ink text-white" : "text-muted hover:bg-canvas hover:text-text"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function AssetTaxonomy({ asset }: { asset: assetApi.Asset }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="rounded-full bg-canvas px-2 py-1 text-[10px] font-medium text-text">
        {asset.sourceCategory === "ai" ? "AI 素材" : "非 AI 素材"}
      </span>
      <span className="rounded-full bg-canvas px-2 py-1 text-[10px] font-medium text-text">{mediaLabels[asset.mediaType]}</span>
      {asset.contentTypes.length ? asset.contentTypes.map((type) => (
        <span key={type} className="rounded-full border border-line px-2 py-1 text-[10px] text-muted">{contentLabels[type]}</span>
      )) : <span className="rounded-full border border-dashed border-line px-2 py-1 text-[10px] text-muted">内容待识别</span>}
    </div>
  );
}

export default function LibraryView({
  previewAssets,
  previewProjects,
}: {
  previewAssets?: assetApi.Asset[];
  previewProjects?: Project[];
} = {}) {
  const previewMode = Boolean(previewAssets);
  const queryClient = useQueryClient();
  const openUploadDrawer = useUIStore((state) => state.openUploadDrawer);
  const notify = useUIStore((state) => state.notify);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [mediaType, setMediaType] = useState<assetApi.MediaType | "">("");
  const [contentFilter, setContentFilter] = useState<ContentFilter>("all");
  const [projectId, setProjectId] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects", "asset-filter"],
    queryFn: () => projectApi.list({ pageSize: 100 }),
    retry: false,
    enabled: !previewMode,
  });
  const assetsQuery = useInfiniteQuery({
    queryKey: ["assets", { search, sourceFilter, mediaType, projectId }],
    queryFn: ({ pageParam }) => assetApi.listPage({
      cursor: pageParam,
      limit: 48,
      search: search || undefined,
      sourceCategory: sourceFilter === "all" ? undefined : sourceFilter,
      mediaType: mediaType || undefined,
      projectId: projectId || undefined,
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.hasMore ? page.nextCursor : undefined,
    retry: false,
    enabled: !previewMode,
  });
  const assets = useMemo(
    () => previewAssets ?? assetsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [assetsQuery.data, previewAssets],
  );
  const visibleAssets = useMemo(
    () => assets
      .filter((asset) => sourceFilter === "all" || asset.sourceCategory === sourceFilter)
      .filter((asset) => !mediaType || asset.mediaType === mediaType)
      .filter((asset) => !projectId || asset.projectIds.includes(projectId))
      .filter((asset) => contentFilter === "all" || asset.contentTypes.includes(contentFilter)),
    [assets, contentFilter, mediaType, projectId, sourceFilter],
  );
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = assetsQuery;
  const selectedListAsset = assets.find((asset) => asset.id === selectedId);
  const detailQuery = useQuery({
    queryKey: ["asset", selectedId],
    queryFn: () => assetApi.get(selectedId!),
    enabled: Boolean(selectedId) && !previewMode,
    retry: false,
  });
  const segmentsQuery = useQuery({
    queryKey: ["asset-segments", selectedId],
    queryFn: () => assetApi.listSegments(selectedId!, { limit: 100 }),
    enabled: Boolean(selectedId) && !previewMode,
    retry: false,
  });
  const selected = detailQuery.data ?? selectedListAsset;
  const projects = previewProjects ?? projectsQuery.data?.items ?? [];
  const selectedSegments = previewMode ? selected?.segments ?? [] : segmentsQuery.data ?? [];

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver((entries) => {
      if (!previewMode && entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) void fetchNextPage();
    }, { rootMargin: "400px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, previewMode]);

  const linkMutation = useMutation({
    mutationFn: async ({ targetProjectId, unlink }: { targetProjectId: string; unlink: boolean }) => {
      if (unlink) await projectApi.unlinkAsset(targetProjectId, selectedId!);
      else await projectApi.linkAsset(targetProjectId, selectedId!);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assets"] });
      void queryClient.invalidateQueries({ queryKey: ["asset", selectedId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      notify("项目素材关联已更新");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "关联更新失败", "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const impact = await assetApi.getDeleteImpact(id);
      if (!impact.canDelete) throw new Error(impact.blockers.join("；"));
      if (!window.confirm("确认将该全局素材移入回收站？已关联或被镜头使用的素材不能删除。")) return false;
      await assetApi.remove(id);
      return true;
    },
    onSuccess: (deleted) => {
      if (!deleted) return;
      setSelectedId(null);
      void queryClient.invalidateQueries({ queryKey: ["assets"] });
      notify("素材已移入回收站，仍会占用存储空间");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "素材删除失败", "error"),
  });

  return (
    <div className="workspace-page max-w-[1500px]">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold tracking-[0.12em] text-muted">GLOBAL ASSET LIBRARY</p>
          <h1 className="workspace-page-title">素材库</h1>
          <p className="workspace-page-copy">统一管理素材、识别内容与处理状态，并按需关联到项目。</p>
        </div>
        <button type="button" onClick={() => openUploadDrawer(null)} className="workspace-primary-button"><Upload size={16} />上传素材</button>
      </header>

      <section className="mb-5 overflow-hidden rounded-2xl border border-line bg-surface">
        <form
          onSubmit={(event) => { event.preventDefault(); setSearch(searchDraft.trim()); setSelectedId(null); }}
          className="flex flex-wrap items-center gap-3 border-b border-line p-3"
        >
          <div className="relative min-w-[260px] flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="搜索名称、标签、转写、OCR 和片段…" className="w-full rounded-lg border border-line bg-canvas/30 py-2.5 pl-9 pr-3 text-sm text-text" />
          </div>
          <button type="submit" className="workspace-secondary-button min-h-10 px-4">搜索</button>
          <label className="flex min-h-10 items-center gap-2 rounded-lg border border-line px-3 text-sm text-muted">
            <SlidersHorizontal size={14} />
            <select value={projectId} onChange={(event) => { setProjectId(event.target.value); setSelectedId(null); }} className="bg-transparent text-sm text-text">
              <option value="">全部项目</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <div className="flex rounded-lg border border-line p-1" aria-label="素材视图">
            <button type="button" aria-label="网格视图" onClick={() => setViewMode("grid")} className={`rounded-md p-2 ${viewMode === "grid" ? "bg-ink text-white" : "text-muted"}`}><Grid2X2 size={15} /></button>
            <button type="button" aria-label="列表视图" onClick={() => setViewMode("list")} className={`rounded-md p-2 ${viewMode === "list" ? "bg-ink text-white" : "text-muted"}`}><List size={15} /></button>
          </div>
        </form>
        <div className="space-y-2.5 px-4 py-3">
          <FilterGroup label="类型" value={sourceFilter} options={sourceFilters} onChange={(value) => { setSourceFilter(value); setSelectedId(null); }} />
          <FilterGroup label="格式" value={mediaType} options={formatFilters} onChange={(value) => { setMediaType(value); setSelectedId(null); }} />
          <FilterGroup label="内容" value={contentFilter} options={contentFilters} onChange={(value) => { setContentFilter(value); setSelectedId(null); }} />
        </div>
      </section>

      {!previewMode && assetsQuery.isLoading ? <div className="flex justify-center py-24"><Loader2 className="animate-spin text-muted" /></div>
        : !previewMode && assetsQuery.isError ? <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center text-sm text-red">{assetsQuery.error instanceof Error ? assetsQuery.error.message : "素材加载失败"}</div>
        : !visibleAssets.length ? <div className="rounded-2xl border border-dashed border-line py-24 text-center"><Search className="mx-auto mb-3 text-muted" size={23} /><strong className="text-sm text-text">没有符合条件的素材</strong><p className="mt-1 text-xs text-muted">调整项目、搜索词或“类型 × 格式 × 内容”分类后重试。</p></div>
        : viewMode === "grid" ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {visibleAssets.map((asset) => {
              const TypeIcon = asset.mediaType === "image" ? ImageIcon : asset.mediaType === "audio" ? FileAudio : Film;
              return (
                <button key={asset.id} type="button" onClick={() => setSelectedId(asset.id)} className="group overflow-hidden rounded-2xl border border-line bg-surface text-left transition hover:-translate-y-0.5 hover:border-[#c3c3c6] hover:shadow-[0_14px_34px_rgba(0,0,0,.08)]">
                  <div className="relative">
                    <VideoThumb imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={asset.mediaType === "video"} />
                    <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-ink/75 px-2 py-1 text-[10px] text-white"><TypeIcon size={11} />{mediaLabels[asset.mediaType]}</span>
                    <span className="absolute right-2 top-2 rounded-full bg-white/90 px-2 py-1 text-[10px] font-medium text-text">{asset.processingStatus}</span>
                  </div>
                  <div className="p-3">
                    <strong className="block truncate text-sm text-text">{asset.name}</strong>
                    <p className="mb-2 mt-1 flex items-center gap-1 text-xs text-muted"><Clock3 size={12} />{formatDuration(asset.durationMs)} · {asset.fileSizeMb.toFixed(1)} MB</p>
                    <AssetTaxonomy asset={asset} />
                    <div className="mt-3 flex justify-between border-t border-line pt-2 text-[11px] text-muted"><span>{asset.createdAtRelative}</span><span>{asset.projectIds.length} 个项目</span></div>
                    {asset.matchExcerpt && <p className="mt-2 line-clamp-2 rounded-lg bg-canvas p-2 text-[11px] text-text">{asset.matchExcerpt}</p>}
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            {visibleAssets.map((asset) => {
              const TypeIcon = asset.mediaType === "image" ? ImageIcon : asset.mediaType === "audio" ? FileAudio : Film;
              return (
                <button key={asset.id} type="button" onClick={() => setSelectedId(asset.id)} className="group grid w-full grid-cols-[112px_minmax(0,1fr)] gap-4 border-b border-line p-3 text-left last:border-b-0 hover:bg-canvas/70 md:grid-cols-[128px_minmax(180px,1.4fr)_minmax(220px,1fr)_120px] md:items-center">
                  <div className="relative"><VideoThumb imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={asset.mediaType === "video"} /><span className="absolute left-1.5 top-1.5 rounded-full bg-ink/75 p-1 text-white"><TypeIcon size={11} /></span></div>
                  <div className="min-w-0"><strong className="block truncate text-sm text-text">{asset.name}</strong><p className="mt-1 text-xs text-muted">{formatDuration(asset.durationMs)} · {asset.fileSizeMb.toFixed(1)} MB · {asset.createdAtRelative}</p><p className="mt-1 text-[11px] text-muted">{asset.projectIds.length ? `已关联 ${asset.projectIds.length} 个项目` : "尚未关联项目"}</p></div>
                  <div className="col-span-2 md:col-span-1"><AssetTaxonomy asset={asset} /></div>
                  <span className="hidden justify-self-end rounded-full bg-canvas px-2.5 py-1 text-xs text-muted md:inline-flex">{asset.processingStatus}</span>
                </button>
              );
            })}
          </div>
        )}

      <div ref={sentinelRef} className="flex h-20 items-center justify-center text-xs text-muted">
        {!previewMode && assetsQuery.isFetchingNextPage ? <><Loader2 size={14} className="mr-2 animate-spin" />加载更多…</> : !previewMode && assetsQuery.hasNextPage ? "继续滚动加载更多素材" : assets.length ? `已加载当前筛选下的全部 ${assets.length} 项` : ""}
      </div>

      {selected && (
        <div className="fixed inset-0 z-[70] flex justify-end bg-ink/40 backdrop-blur-sm" onClick={() => setSelectedId(null)}>
          <aside className="h-full w-full max-w-xl overflow-y-auto bg-surface p-6 shadow-soft" onClick={(event) => event.stopPropagation()}>
            <header className="flex items-start gap-3"><div className="min-w-0 flex-1"><p className="mb-1 text-[10px] font-semibold tracking-[0.12em] text-muted">素材详情</p><h2 className="truncate text-lg font-semibold text-text">{selected.name}</h2><p className="text-xs text-muted">{mediaLabels[selected.mediaType]} · {selected.sourceCategory === "ai" ? "AI 素材" : "非 AI 素材"} · {selected.processingStatus}</p></div><button type="button" aria-label="关闭素材详情" onClick={() => setSelectedId(null)} className="p-2 text-muted"><X size={18} /></button></header>
            <div className="mt-5"><VideoThumb imageUrl={selected.thumbnailUrl ?? (selected.mediaType === "image" ? selected.mediaUrl : undefined)} videoUrl={selected.mediaType === "video" ? selected.mediaUrl : undefined} showPlay={selected.mediaType === "video"} /></div>
            <div className="mt-4"><AssetTaxonomy asset={selected} /></div>
            <div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs">{[["尺寸", selected.width && selected.height ? `${selected.width}×${selected.height}` : "—"], ["时长", formatDuration(selected.durationMs)], ["大小", `${selected.fileSizeMb.toFixed(1)} MB`]].map(([label, value]) => <div key={label} className="rounded-lg bg-canvas p-3"><strong className="block text-text">{value}</strong><span className="text-muted">{label}</span></div>)}</div>
            <section className="mt-5"><h3 className="text-sm font-semibold text-text">项目关联</h3><div className="mt-2 space-y-2">{projects.map((project) => { const linked = selected.projectIds.includes(project.id); return <div key={project.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2"><span className="min-w-0 flex-1 truncate text-xs text-text">{project.name}</span><button type="button" disabled={previewMode} onClick={() => linkMutation.mutate({ targetProjectId: project.id, unlink: linked })} className={`flex items-center gap-1 text-xs font-medium disabled:opacity-45 ${linked ? "text-red" : "text-blue"}`}>{linked ? <><Unlink size={12} />解除</> : <><Link2 size={12} />关联</>}</button></div>; })}</div></section>
            <section className="mt-5"><h3 className="text-sm font-semibold text-text">识别片段</h3><div className="mt-2 max-h-64 space-y-2 overflow-y-auto">{selectedSegments.map((segment) => <div key={segment.id} className="rounded-lg bg-canvas p-3"><div className="flex justify-between text-xs"><strong className="text-text">{segment.title || "未命名片段"}</strong><span className="text-muted">{(segment.startMs / 1000).toFixed(1)}–{(segment.endMs / 1000).toFixed(1)}s</span></div><p className="mt-1 line-clamp-3 text-xs text-muted">{segment.transcript || segment.ocrText || "无文本识别"}</p></div>)}{!previewMode && segmentsQuery.isLoading && <p className="py-6 text-center text-xs text-muted">加载片段…</p>}{!segmentsQuery.isLoading && !selectedSegments.length && <p className="py-6 text-center text-xs text-muted">暂无片段</p>}</div></section>
            <button type="button" disabled={previewMode || deleteMutation.isPending} onClick={() => deleteMutation.mutate(selected.id)} className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-red/20 py-2.5 text-sm font-medium text-red disabled:opacity-50"><Trash2 size={15} />移入回收站</button>
          </aside>
        </div>
      )}
    </div>
  );
}
