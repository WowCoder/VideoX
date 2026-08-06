// ──────────────────────────────────────────────
// OpenVMA - 素材库
// 页头 + 上传按钮 + 统计卡 + 工具栏(搜索/项目筛选/状态筛选/视图切换)
// 素材网格/列表 + 素材详情面板
// ──────────────────────────────────────────────

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "@/router";
import {
  Clock3,
  FileVideo,
  LayoutGrid,
  List,
  Loader2,
  Music,
  Search,
  ScanText,
  Sparkles,
  Tag,
  Trash2,
  Upload,
  Users,
  X,
} from "lucide-react";
import * as assetApi from "@/api/assets";
import * as projectApi from "@/api/projects";
import { useUIStore } from "@/stores/uiStore";
import { VideoThumb } from "@/components/VideoThumb";
import type { Asset, AssetStatus } from "@/types/models";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";

const statusOptions: { value: string; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "处理完成", label: "处理完成" },
  { value: "AI 处理中", label: "AI 处理中" },
  { value: "处理中", label: "处理中" },
  { value: "处理失败", label: "处理失败" },
];

const statusBadgeClass: Record<AssetStatus, string> = {
  处理完成: "bg-teal/10 text-teal",
  "AI 处理中": "bg-blue-soft text-blue",
  处理中: "bg-amber/10 text-amber",
  处理失败: "bg-red/10 text-red",
  失败: "bg-red/10 text-red",
};

const EMPTY_PROJECTS: Awaited<ReturnType<typeof projectApi.list>>["items"] = [];
const EMPTY_ASSETS: Asset[] = [];

export function LibraryView() {
  const { openUploadDrawer, notify } = useUIStore();
  const queryClient = useQueryClient();
  const [deleteAssetId, setDeleteAssetId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get("search") ?? "";
  const projectFilter = searchParams.get("project") ?? "";
  const statusFilter = searchParams.get("status") ?? "";
  const mediaTypeFilter = searchParams.get("media") === "audio"
    ? "audio"
    : searchParams.get("media") === "video"
      ? "video"
      : "";
  const view = searchParams.get("view") === "list" ? "list" : "grid";
  const selectedAssetId = searchParams.get("asset");

  function updateQuery(key: string, value: string | null) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  }

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectApi.list(),
    retry: false,
  });
  const projects = projectsData?.items ?? EMPTY_PROJECTS;

  const { data: assetsData, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["assets", projectFilter, search, statusFilter, mediaTypeFilter],
    queryFn: () =>
      assetApi.list({
        projectId: projectFilter || undefined,
        mediaType: mediaTypeFilter || undefined,
        search: search || undefined,
        status: statusFilter || undefined,
      }),
    retry: false,
  });
  const assets = assetsData?.items ?? EMPTY_ASSETS;
  const selectedAsset = selectedAssetId
    ? assets.find((asset) => asset.id === selectedAssetId) ?? null
    : null;

  const stats = useMemo(() => {
    const videos = assets.filter((asset) => asset.mediaType === "video").length;
    const audios = assets.filter((asset) => asset.mediaType === "audio").length;
    const clips = assets.reduce((sum, asset) => sum + asset.clips.length, 0);
    const processing = assets.filter(
      (a) => a.status !== "处理完成" && a.status !== "失败" && a.status !== "处理失败",
    ).length;
    return { videos, audios, clips, processing };
  }, [assets]);

  function handleAssetClick(asset: Asset) {
    updateQuery("asset", asset.id);
  }

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      {/* 页头 */}
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">素材库</h1>
          <p className="mt-1.5 text-sm text-muted">管理项目下的视频、音频素材与可搜索片段</p>
        </div>
        <button
          onClick={openUploadDrawer}
          className="flex items-center gap-2 rounded-lg bg-blue px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2"
          type="button"
        >
          <Upload size={16} />上传素材
        </button>
      </header>

      {/* 统计卡片 */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-soft text-blue">
            <FileVideo size={20} />
          </span>
          <div>
            <strong className="text-xl font-semibold text-text">{stats.videos}</strong>
            <small className="block text-xs text-muted">视频素材</small>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal/10 text-teal">
            <Music size={20} />
          </span>
          <div>
            <strong className="text-xl font-semibold text-text">{stats.audios}</strong>
            <small className="block text-xs text-muted">音频素材</small>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal/10 text-teal">
            <Sparkles size={20} />
          </span>
          <div>
            <strong className="text-xl font-semibold text-text">{stats.clips}</strong>
            <small className="block text-xs text-muted">可搜索片段</small>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 shadow-soft">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber/10 text-amber">
            <Clock3 size={20} />
          </span>
          <div>
            <strong className="text-xl font-semibold text-text">{stats.processing}</strong>
            <small className="block text-xs text-muted">处理中</small>
          </div>
        </div>
      </div>

      {/* 工具栏 */}
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-3 shadow-soft">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => updateQuery("search", e.target.value)}
            placeholder="搜索素材名称、标签、对白或画面文字…"
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
        <select
          value={mediaTypeFilter}
          onChange={(e) => updateQuery("media", e.target.value)}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-text transition focus:border-blue"
        >
          <option value="">全部类型</option>
          <option value="video">视频</option>
          <option value="audio">音频</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => updateQuery("status", e.target.value)}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-text transition focus:border-blue"
        >
          {statusOptions.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <div className="flex gap-1 rounded-lg bg-canvas p-1">
          <button
            onClick={() => updateQuery("view", null)}
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

      <div className={selectedAsset ? "grid min-w-0 grid-cols-[minmax(0,1fr)_400px] gap-5" : "min-w-0"}>
        <section className="min-w-0">
      {/* 素材区 */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Loader2 size={24} className="animate-spin text-muted" /></div>
      ) : isError ? (
        <div className="rounded-2xl border border-red/20 bg-red/5 py-16 text-center">
          <p className="text-sm font-medium text-red">素材加载失败</p>
          <p className="mt-1 text-xs text-muted">{error instanceof Error ? error.message : "请检查后端服务"}</p>
          <button type="button" onClick={() => void refetch()} className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white">
            重试
          </button>
        </div>
      ) : assets.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line py-20 text-center">
          {mediaTypeFilter === "audio"
            ? <Music size={32} className="mx-auto text-line" />
            : <FileVideo size={32} className="mx-auto text-line" />}
          <p className="mt-3 text-sm text-muted">还没有素材，点击右上角上传</p>
        </div>
      ) : view === "grid" ? (
        <div className={selectedAsset ? "grid gap-4 md:grid-cols-2 xl:grid-cols-3" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"}>
          {assets.map((asset) => (
            <article
              key={asset.id}
              onClick={() => handleAssetClick(asset)}
              onKeyDown={(event) => event.key === "Enter" && handleAssetClick(asset)}
              className={`group overflow-hidden rounded-2xl border bg-surface text-left shadow-soft transition hover:-translate-y-0.5 hover:border-blue/40 ${selectedAssetId === asset.id ? "border-blue ring-2 ring-blue/10" : "border-line"}`}
              role="button"
              tabIndex={0}
            >
              <div className="relative">
                {asset.mediaType === "audio" ? (
                  <div className="flex aspect-video flex-col items-center justify-center bg-gradient-to-br from-teal/15 via-blue-soft to-canvas px-5">
                    <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface text-teal shadow-soft">
                      <Music size={22} />
                    </span>
                    {asset.mediaUrl && (
                      <audio
                        src={asset.mediaUrl}
                        controls
                        preload="metadata"
                        onClick={(event) => event.stopPropagation()}
                        className="mt-4 h-8 w-full"
                      />
                    )}
                  </div>
                ) : (
                  <VideoThumb
                    variant={asset.variant}
                    imageUrl={asset.thumbnailUrl}
                    videoUrl={asset.mediaUrl}
                    rounded="rounded-none"
                  />
                )}
                {projects.find((project) => project.id === asset.projectId)?.currentUserRole !== "viewer" && (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setDeleteAssetId(asset.id);
                    }}
                    className="absolute bottom-3 right-3 rounded-lg bg-ink/65 p-2 text-white/80 opacity-0 backdrop-blur-sm transition hover:bg-red hover:text-white group-hover:opacity-100"
                    aria-label={`删除素材 ${asset.name}`}
                  ><Trash2 size={14} /></button>
                )}
              </div>
              <div className="p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <strong className="truncate text-sm text-text">{asset.name}</strong>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${statusBadgeClass[asset.status]}`}>
                    {asset.status}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3 text-xs text-muted">
                  <span className="flex items-center gap-1"><Clock3 size={12} />{asset.duration}</span>
                  <span>·</span>
                  <span>{asset.uploadedAt}</span>
                </div>
                <AssetTags asset={asset} />
                {search.trim() && <AssetMatchInfo asset={asset} />}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface shadow-soft">
          <table className="min-w-[760px] w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-canvas/40 text-left text-xs text-muted">
                <th className="px-4 py-3 font-medium">素材名称</th>
                <th className="px-4 py-3 font-medium">所属项目</th>
                <th className="px-4 py-3 font-medium">时长</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">上传时间</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => {
                const project = projects.find((p) => p.id === asset.projectId);
                return (
                  <tr
                    key={asset.id}
                    onClick={() => handleAssetClick(asset)}
                    className={`cursor-pointer border-b border-line/60 transition hover:bg-canvas/40 ${selectedAssetId === asset.id ? "bg-blue-soft/60" : ""}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-8 w-12 items-center justify-center rounded bg-gradient-to-br from-blue to-teal">
                          {asset.mediaType === "audio"
                            ? <Music size={14} className="text-white" />
                            : <FileVideo size={14} className="text-white" />}
                        </span>
                        <div className="min-w-0">
                          <span className="block truncate font-medium text-text">{asset.name}</span>
                          {search.trim() && <AssetMatchInfo asset={asset} compact />}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted">{project?.name ?? "—"}</td>
                    <td className="px-4 py-3 text-muted">{asset.duration}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${statusBadgeClass[asset.status]}`}>
                        {asset.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted">{asset.uploadedAt}</td>
                    <td className="px-4 py-3">
                      {project?.currentUserRole !== "viewer" && (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setDeleteAssetId(asset.id);
                          }}
                          className="rounded-lg p-1.5 text-muted hover:bg-red/10 hover:text-red"
                          aria-label={`删除素材 ${asset.name}`}
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
        </section>

      {/* 素材详情面板 */}
      {selectedAsset && (
        <AssetDetailPanel
          asset={selectedAsset}
          projectName={projects.find((p) => p.id === selectedAsset.projectId)?.name ?? ""}
          onClose={() => updateQuery("asset", null)}
        />
      )}
      <DeleteConfirmModal
        open={Boolean(deleteAssetId)}
        entityLabel="素材"
        loadImpact={() => assetApi.getDeleteImpact(deleteAssetId!)}
        onDelete={() => assetApi.remove(deleteAssetId!)}
        onClose={() => setDeleteAssetId(null)}
        onDeleted={() => {
          if (selectedAssetId === deleteAssetId) updateQuery("asset", null);
          void queryClient.invalidateQueries({ queryKey: ["assets"] });
          void queryClient.invalidateQueries({ queryKey: ["projects"] });
          notify("素材已删除");
        }}
      />
      </div>
    </div>
  );
}

const matchLabels: Record<NonNullable<Asset["matchField"]>, string> = {
  name: "名称命中",
  tag: "标签命中",
  transcript: "对白命中",
  ocr: "画面文字命中",
  clip_title: "片段标题命中",
  clip_transcript: "片段对白命中",
  clip_ocr: "片段画面文字命中",
};

function AssetTags({ asset }: { asset: Asset }) {
  const tags = (asset.tags ?? []).filter(Boolean).slice(0, 3);
  if (!tags.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {tags.map((tag) => (
        <span key={tag} className="rounded bg-canvas px-1.5 py-0.5 text-[10px] text-muted">
          {tag}
        </span>
      ))}
    </div>
  );
}

function AssetMatchInfo({ asset, compact = false }: { asset: Asset; compact?: boolean }) {
  if (!asset.matchField || !asset.matchExcerpt) return null;
  return (
    <div className={`${compact ? "mt-0.5" : "mt-2 rounded-lg bg-blue-soft/50 px-2 py-1.5"} text-[11px] leading-relaxed text-blue`}>
      <span className="font-medium">{matchLabels[asset.matchField]}：</span>
      <span>{asset.matchExcerpt}</span>
    </div>
  );
}

/* ── 素材详情面板（Desktop 主从布局右栏） ── */
function AssetDetailPanel({
  asset,
  projectName,
  onClose,
}: {
  asset: Asset;
  projectName: string;
  onClose: () => void;
}) {
  const { data: latestAsset, refetch } = useQuery({
    queryKey: ["asset-detail", asset.id],
    queryFn: () => assetApi.get(asset.id),
    initialData: asset,
    staleTime: 30_000,
  });
  const [failedMediaUrl, setFailedMediaUrl] = useState<string | null>(null);
  const [refreshingMedia, setRefreshingMedia] = useState(false);
  const mediaError = failedMediaUrl === latestAsset.mediaUrl
    ? `${latestAsset.mediaType === "audio" ? "音频" : "视频"}加载失败，媒体地址可能已过期`
    : null;

  async function refreshMediaUrl() {
    setRefreshingMedia(true);
    try {
      await refetch();
      setFailedMediaUrl(null);
    } finally {
      setRefreshingMedia(false);
    }
  }

  return (
      <aside className="sticky top-4 flex max-h-[calc(100vh-2rem)] min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        <header className="flex h-16 items-center justify-between border-b border-line px-5">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-text">{latestAsset.name}</h2>
            <p className="truncate text-xs text-muted">{projectName || "未归属项目"}</p>
          </div>
          <button
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">
          <div className="flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-black">
            {latestAsset.mediaUrl && !mediaError && latestAsset.mediaType === "audio" ? (
              <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-teal/20 via-ink to-black px-6">
                <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/10 text-teal">
                  <Music size={30} />
                </span>
                <audio
                  key={latestAsset.mediaUrl}
                  src={latestAsset.mediaUrl}
                  controls
                  preload="metadata"
                  onError={() => setFailedMediaUrl(latestAsset.mediaUrl ?? null)}
                  className="mt-5 w-full"
                />
              </div>
            ) : latestAsset.mediaUrl && !mediaError ? (
              <video
                key={latestAsset.mediaUrl}
                src={latestAsset.mediaUrl}
                poster={latestAsset.thumbnailUrl}
                controls
                playsInline
                preload="metadata"
                onError={() => setFailedMediaUrl(latestAsset.mediaUrl ?? null)}
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center px-6 text-center text-white/60">
                {latestAsset.mediaType === "audio" ? <Music size={30} /> : <FileVideo size={30} />}
                <p className="mt-2 text-sm">
                  {mediaError || `该素材暂无可播放的${latestAsset.mediaType === "audio" ? "音频" : "视频"}`}
                </p>
                {latestAsset.mediaUrl && (
                  <button
                    type="button"
                    onClick={() => void refreshMediaUrl()}
                    disabled={refreshingMedia}
                    className="mt-3 rounded-lg bg-white/10 px-3 py-1.5 text-xs text-white transition hover:bg-white/20 disabled:opacity-50"
                  >
                    {refreshingMedia ? "刷新中…" : "刷新媒体地址"}
                  </button>
                )}
              </div>
            )}
          </div>
          <div className="mt-4 flex items-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 text-xs ${statusBadgeClass[latestAsset.status]}`}>
              {latestAsset.status}
            </span>
            <span className="rounded-full bg-blue-soft px-2.5 py-0.5 text-xs text-blue">
              {latestAsset.mediaType === "audio" ? "音频" : "视频"}
            </span>
            <span className="rounded-full bg-canvas px-2.5 py-0.5 text-xs text-muted">{projectName}</span>
          </div>

          {(latestAsset.tags ?? []).length > 0 && (
            <section className="mt-5">
              <div className="flex items-center gap-1.5 text-sm font-medium text-text">
                <Tag size={14} className="text-blue" />标签
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(latestAsset.tags ?? []).map((tag) => (
                  <span key={tag} className="rounded-full bg-blue-soft px-2.5 py-1 text-xs text-blue">{tag}</span>
                ))}
              </div>
            </section>
          )}

          <dl className="mt-5 space-y-3">
            <div className="flex justify-between border-b border-line/60 pb-2.5">
              <dt className="text-sm text-muted">时长</dt>
              <dd className="text-sm font-medium text-text">{latestAsset.duration}</dd>
            </div>
            <div className="flex justify-between border-b border-line/60 pb-2.5">
              <dt className="text-sm text-muted">来源</dt>
              <dd className="text-sm font-medium text-text">{latestAsset.source}</dd>
            </div>
            {latestAsset.mediaType === "audio" && (
              <>
                <div className="flex justify-between border-b border-line/60 pb-2.5">
                  <dt className="text-sm text-muted">音频编码</dt>
                  <dd className="text-sm font-medium uppercase text-text">{latestAsset.audioCodec || "—"}</dd>
                </div>
                <div className="flex justify-between border-b border-line/60 pb-2.5">
                  <dt className="text-sm text-muted">采样率</dt>
                  <dd className="text-sm font-medium text-text">
                    {latestAsset.sampleRate ? `${(latestAsset.sampleRate / 1000).toFixed(1)} kHz` : "—"}
                  </dd>
                </div>
                <div className="flex justify-between border-b border-line/60 pb-2.5">
                  <dt className="text-sm text-muted">声道</dt>
                  <dd className="text-sm font-medium text-text">
                    {latestAsset.channels ? `${latestAsset.channels} 声道` : "—"}
                  </dd>
                </div>
                <div className="flex justify-between border-b border-line/60 pb-2.5">
                  <dt className="text-sm text-muted">码率</dt>
                  <dd className="text-sm font-medium text-text">
                    {latestAsset.bitrate ? `${Math.round(latestAsset.bitrate / 1000)} kbps` : "—"}
                  </dd>
                </div>
              </>
            )}
            <div className="flex justify-between border-b border-line/60 pb-2.5">
              <dt className="text-sm text-muted">上传时间</dt>
              <dd className="text-sm font-medium text-text">{latestAsset.uploadedAt}</dd>
            </div>
            {latestAsset.mediaType === "video" && <div className="flex justify-between border-b border-line/60 pb-2.5">
              <dt className="text-sm text-muted">镜头片段</dt>
              <dd className="text-sm font-medium text-text">
                {latestAsset.status === "处理完成"
                  ? `${latestAsset.clips.length} 个片段`
                  : latestAsset.status === "处理失败" || latestAsset.status === "失败"
                    ? "处理失败"
                    : "处理中"}
              </dd>
            </div>}
          </dl>

          {latestAsset.status === "处理完成" && latestAsset.mediaType === "video" && (
            <div className="mt-5">
              <strong className="text-sm font-medium text-text">完整对白转写</strong>
              <p className="mt-2 rounded-xl bg-canvas/60 p-3 text-xs leading-relaxed text-muted">
                {latestAsset.transcript?.trim() || "未从该素材中提取到可用语音转写。"}
              </p>
              <div className="mt-4 flex items-center gap-1.5 text-sm font-medium text-text">
                <ScanText size={14} className="text-teal" />画面文字 OCR
              </div>
              <p className="mt-2 rounded-xl bg-canvas/60 p-3 text-xs leading-relaxed text-muted">
                {latestAsset.ocrText?.trim() || "未从该素材中识别到可用画面文字。"}
              </p>

              <div className="mt-5 flex items-center justify-between">
                <strong className="text-sm font-medium text-text">可搜索片段</strong>
                <span className="text-xs text-muted">{latestAsset.clips.length} 个</span>
              </div>
              <div className="mt-2 space-y-2.5">
                {latestAsset.clips.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-line py-5 text-center text-xs text-muted">
                    该素材尚未生成可搜索片段
                  </div>
                ) : latestAsset.clips.map((clip) => (
                  <article
                    key={clip.id}
                    className={`rounded-xl border p-3 ${latestAsset.matchedClipId === clip.id ? "border-blue bg-blue-soft/30" : "border-line"}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <strong className="block truncate text-xs text-text">{clip.title || "未命名片段"}</strong>
                        <span className="text-[11px] text-muted">{clip.range}</span>
                      </div>
                      {clip.qualityScore != null && (
                        <span className="shrink-0 rounded bg-teal/10 px-1.5 py-0.5 text-[10px] text-teal">
                          质量 {Math.round(clip.qualityScore)}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-xs leading-relaxed text-text">
                      {clip.transcriptSegment?.trim() || "未识别到片段对白"}
                    </p>
                    {clip.ocrSegment?.trim() && (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-muted">OCR：{clip.ocrSegment}</p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-1">
                      {[clip.sceneType, clip.shotType, clip.cameraMotion].filter(Boolean).map((value) => (
                        <span key={value} className="rounded bg-canvas px-1.5 py-0.5 text-[10px] text-muted">{value}</span>
                      ))}
                    </div>
                    {(clip.persons?.length || clip.objects?.length) ? (
                      <div className="mt-2 space-y-1 text-[11px] text-muted">
                        {!!clip.persons?.length && <p className="flex gap-1"><Users size={12} className="mt-0.5 shrink-0" />人物：{clip.persons.join("、")}</p>}
                        {!!clip.objects?.length && <p>物品：{clip.objects.join("、")}</p>}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>
  );
}

export default LibraryView;
