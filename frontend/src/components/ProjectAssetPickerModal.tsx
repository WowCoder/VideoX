import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, FileAudio, Film, Image as ImageIcon, Loader2, Search, X } from "lucide-react";
import * as assetApi from "@/api/assets";
import * as projectApi from "@/api/projects";
import { VideoThumb } from "@/components/VideoThumb";

interface Props {
  open: boolean;
  projectId: string;
  linkedAssetIds: string[];
  onClose: () => void;
  onAdded: () => Promise<void> | void;
}

const mediaLabels = { video: "视频", image: "图片", audio: "音频" } as const;

export function ProjectAssetPickerModal({ open, projectId, linkedAssetIds, onClose, onAdded }: Props) {
  const [search, setSearch] = useState("");
  const [mediaType, setMediaType] = useState<assetApi.MediaType | "">("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  useEffect(() => {
    if (!open) return;
    setSearch("");
    setMediaType("");
    setSelectedIds([]);
  }, [open]);

  const assetsQuery = useQuery({
    queryKey: ["assets", "project-picker", search, mediaType],
    queryFn: () => assetApi.listPage({ limit: 100, search: search.trim() || undefined, mediaType: mediaType || undefined, status: "ready" }),
    enabled: open && projectId !== "__preview__",
    retry: false,
  });
  const linked = useMemo(() => new Set(linkedAssetIds), [linkedAssetIds]);
  const assets = (assetsQuery.data?.items ?? []).filter((asset) => !linked.has(asset.id));
  const addMutation = useMutation({
    mutationFn: async () => {
      await Promise.all(selectedIds.map((assetId) => projectApi.linkAsset(projectId, assetId)));
    },
    onSuccess: async () => {
      await onAdded();
      onClose();
    },
  });

  if (!open) return null;
  return <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="project-asset-picker-title">
    <section className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-line px-5 py-4"><div><h2 id="project-asset-picker-title" className="text-sm font-semibold text-text">从素材库添加</h2><p className="mt-1 text-[11px] text-muted">选择已有素材关联到当前项目；添加后不会自动替换任何镜头。</p></div><button type="button" aria-label="关闭素材选择器" onClick={onClose} disabled={addMutation.isPending} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={15} /></button></header>
      <div className="flex flex-wrap gap-2 border-b border-line p-4"><label className="flex min-w-[240px] flex-1 items-center gap-2 rounded-lg border border-line px-3 py-2 text-muted"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索素材库" className="min-w-0 flex-1 bg-transparent text-xs text-text outline-none" /></label><div className="flex rounded-lg bg-canvas p-1">{[["", "全部"], ["video", "视频"], ["image", "图片"], ["audio", "音频"]].map(([value, label]) => <button key={value || "all"} type="button" onClick={() => setMediaType(value as assetApi.MediaType | "")} className={`rounded-md px-3 py-1.5 text-[11px] ${mediaType === value ? "bg-white font-semibold text-blue shadow-sm" : "text-muted"}`}>{label}</button>)}</div></div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">{assetsQuery.isLoading ? <div className="grid min-h-64 place-items-center text-xs text-muted"><span><Loader2 size={18} className="mx-auto mb-2 animate-spin" />正在加载素材库…</span></div> : assetsQuery.isError ? <div className="grid min-h-64 place-items-center text-xs text-red">素材库加载失败，请稍后重试</div> : assets.length ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{assets.map((asset) => { const selected = selectedIds.includes(asset.id); const TypeIcon = asset.mediaType === "audio" ? FileAudio : asset.mediaType === "image" ? ImageIcon : Film; return <button key={asset.id} type="button" aria-pressed={selected} onClick={() => setSelectedIds((ids) => selected ? ids.filter((id) => id !== asset.id) : [...ids, asset.id])} className={`overflow-hidden rounded-xl border text-left transition ${selected ? "border-blue ring-2 ring-blue/15" : "border-line hover:border-blue/35"}`}><div className="relative aspect-video bg-[#17191f]"><VideoThumb fill imageUrl={asset.thumbnailUrl ?? (asset.mediaType === "image" ? asset.mediaUrl : undefined)} videoUrl={asset.mediaType === "video" ? asset.mediaUrl : undefined} showPlay={false} /><span className="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/65 px-1.5 py-1 text-[9px] text-white"><TypeIcon size={10} />{mediaLabels[asset.mediaType]}</span>{selected && <span className="absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full bg-blue text-white"><Check size={11} /></span>}</div><div className="p-2.5"><strong className="block truncate text-xs text-text">{asset.name}</strong><span className="mt-1 block text-[9px] text-muted">{asset.sourceCategory === "ai" ? "AI 素材" : "上传素材"}{asset.durationMs ? ` · ${(asset.durationMs / 1000).toFixed(1)} 秒` : ""}</span></div></button>; })}</div> : <div className="grid min-h-64 place-items-center text-center text-xs text-muted"><div><Film size={22} className="mx-auto mb-2 opacity-40" /><strong className="block text-text">没有可添加的素材</strong><span className="mt-1 block">可能已全部关联到当前项目，或没有符合筛选条件的素材。</span></div></div>}</div>
      {(addMutation.error) && <div className="mx-5 mb-3 rounded-lg bg-red/5 px-3 py-2 text-xs text-red">{addMutation.error instanceof Error ? addMutation.error.message : "添加素材失败"}</div>}
      <footer className="flex items-center justify-between border-t border-line bg-canvas/60 px-5 py-4"><span className="text-[11px] text-muted">已选 {selectedIds.length} 项</span><div className="flex gap-2"><button type="button" onClick={onClose} disabled={addMutation.isPending} className="rounded-lg border border-line bg-white px-4 py-2 text-xs text-text">取消</button><button type="button" onClick={() => addMutation.mutate()} disabled={!selectedIds.length || addMutation.isPending} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-45">{addMutation.isPending && <Loader2 size={13} className="animate-spin" />}添加到项目</button></div></footer>
    </section>
  </div>;
}
