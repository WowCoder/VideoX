// ──────────────────────────────────────────────
// OpenVMA - 剪辑工作区（三栏 + 多轨时间线）
// 左栏：素材箱(bin)  中栏：预览器  右栏：检查器(inspector)
// 底部：多轨时间线（video / audio / subtitle），支持选中、拖拽、裁剪、播放头
// 数据：react-query 拉取项目/素材/脚本/时间线；编辑结果自动保存到后端
// ──────────────────────────────────────────────

import type * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useNavigationBlocker, useParams } from "@/router";
import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  Download,
  Upload,
  Search,
  Film,
  FileText,
  Sparkles,
  Loader2,
  AlertTriangle,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Scissors,
  Trash2,
  Undo2,
  Redo2,
  RefreshCw,
  ZoomIn,
  ZoomOut,
  Music,
  Type,
  SlidersHorizontal,
  Volume2,
  Mic,
  Plus,
  GripVertical,
} from "lucide-react";

import { useProjectStore } from "@/stores/projectStore";
import { useUIStore } from "@/stores/uiStore";
import * as projectApi from "@/api/projects";
import * as assetApi from "@/api/assets";
import * as scriptApi from "@/api/scripts";
import * as generateApi from "@/api/generate";
import * as jobApi from "@/api/jobs";
import { HttpClientError } from "@/api/client";
import type { Asset, Clip, Script, ScriptUnit, Shot, ThumbnailVariant } from "@/types/models";
import { Thumbnail } from "@/components/Thumbnail";
import { BackButton } from "@/components/BackButton";
import { Modal } from "@/components/ui/Modal";

/* ── 工具 ── */

const uid = () => Math.random().toString(36).slice(2, 10);

const pad = (n: number) => String(Math.floor(n)).padStart(2, "0");
/** 秒 → MM:SS.cs 时间码 */
function fmtTimecode(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const cs = Math.floor((sec % 1) * 100);
  return `${pad(m)}:${pad(s)}.${pad(cs)}`;
}

/* ── 时间线片段类型 ── */

type TrackKind = "video" | "audio" | "subtitle";
type TLClip = projectApi.ProjectTimelineClip;

const DEFAULT_TRANSFORM = {
  scale: 100,
  x: 0,
  y: 0,
  rotation: 0,
  opacity: 100,
  crop: { l: 0, t: 0, r: 0, b: 0 },
};
const DEFAULT_ADJUST = { brightness: 100, contrast: 100, saturation: 100 };
const DEFAULT_AUDIO = {
  volume: 100,
  muted: false,
  denoise: false,
  fadeIn: 0,
  fadeOut: 0,
};
const DEFAULT_TRANSITION = { type: "none" as const, duration: 0.5 };

const ASPECT_OPTIONS = ["16:9", "9:16", "1:1", "4:3"];
const TRACK_META: { kind: TrackKind; label: string; color: string; Icon: typeof Film }[] = [
  { kind: "video", label: "视频", color: "bg-blue", Icon: Film },
  { kind: "audio", label: "音频", color: "bg-teal", Icon: Music },
  { kind: "subtitle", label: "字幕", color: "bg-amber", Icon: Type },
];

const MIN_TIMELINE_DURATION = 10;
const MIN_CLIP_DURATION = 0.5;

const roundTime = (value: number) => Math.round(value * 100) / 100;

function getAssetDuration(asset?: Asset): number {
  if (!asset) return 0;
  const duration = Number.parseFloat(asset.duration);
  return Number.isFinite(duration) ? duration : 0;
}

function getTimelineIssues(clips: TLClip[], assets: Asset[]): string[] {
  const issues: string[] = [];
  const assetMap = new Map(assets.map((asset) => [asset.id, asset]));

  for (const clip of clips) {
    if (clip.track === "video" && !clip.assetId) {
      if (clip.origin === "script_placeholder") {
        issues.push(`分镜「${clip.name}」仍是待补素材占位片段`);
      } else if (
        !["script_generated", "manual_generated"].includes(clip.origin ?? "")
        || !clip.generatedMediaPath
        || !clip.generatedMediaType
      ) {
        issues.push(`视频片段「${clip.name}」没有关联可用素材`);
      }
      continue;
    }
    if (!clip.assetId) continue;
    const asset = assetMap.get(clip.assetId);
    if (!asset) {
      issues.push(`片段「${clip.name}」引用的素材当前不可用`);
      continue;
    }
    if (clip.track === "video" && asset.mediaType !== "video") {
      issues.push(`视频片段「${clip.name}」引用的是音频素材`);
    }
    if (clip.track === "audio" && !asset.hasAudio) {
      issues.push(`音频片段「${clip.name}」引用的素材没有可用音轨`);
    }
    const sourceDuration = getAssetDuration(asset);
    if (sourceDuration > 0 && clip.sourceStart + clip.duration > sourceDuration + 0.05) {
      issues.push(`片段「${clip.name}」超出源素材时长`);
    }
    if (clip.sourceClipId) {
      const sourceClip = asset.clips.find((candidate) => candidate.id === clip.sourceClipId);
      if (
        !sourceClip ||
        clip.sourceStart < sourceClip.startTime - 0.05 ||
        clip.sourceStart + clip.duration > sourceClip.endTime + 0.05
      ) {
        issues.push(`片段「${clip.name}」超出所选识别片段范围`);
      }
    }
  }

  const videos = clips
    .filter((clip) => clip.track === "video")
    .sort((a, b) => a.start - b.start);
  let cursor = 0;
  for (const clip of videos) {
    if (clip.start < cursor - 0.01) issues.push(`视频片段「${clip.name}」与前一个片段重叠`);
    cursor = Math.max(cursor, clip.start + clip.duration);
  }
  return issues;
}

function nearestAvailableVideoStart(
  candidate: number,
  duration: number,
  clipId: string,
  clips: TLClip[],
): number {
  const occupied = clips
    .filter((clip) => clip.track === "video" && clip.id !== clipId)
    .sort((a, b) => a.start - b.start);
  const gaps: Array<{ min: number; max: number }> = [];
  let cursor = 0;
  for (const clip of occupied) {
    if (clip.start - cursor >= duration) gaps.push({ min: cursor, max: clip.start - duration });
    cursor = Math.max(cursor, clip.start + clip.duration);
  }
  gaps.push({ min: cursor, max: Number.POSITIVE_INFINITY });

  let best = Math.max(0, candidate);
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const gap of gaps) {
    const start = Math.max(gap.min, Math.min(gap.max, Math.max(0, candidate)));
    const distance = Math.abs(start - candidate);
    if (distance < bestDistance) {
      best = start;
      bestDistance = distance;
    }
  }
  return roundTime(best);
}

function makeClip(
  track: TrackKind,
  start: number,
  duration: number,
  name: string,
  variant: ThumbnailVariant = "stage",
  text?: string,
  assetId?: string,
  sourceStart = 0,
  sourceClipId?: string,
): TLClip {
  return {
    id: uid(),
    track,
    start,
    duration,
    name,
    variant,
    text,
    assetId,
    sourceClipId,
    sourceStart,
    origin: assetId ? "manual_asset" : "manual_generated",
    syncStatus: "detached",
    transform: { ...DEFAULT_TRANSFORM, crop: { ...DEFAULT_TRANSFORM.crop } },
    adjust: { ...DEFAULT_ADJUST },
    audio: { ...DEFAULT_AUDIO },
    transition: { ...DEFAULT_TRANSITION },
  };
}

/* ──────────────────────────────────────────────
   主组件
   ────────────────────────────────────────────── */

export default function ProjectEditorView() {
  const navigate = useNavigate();
  const { projectId: routeProjectId } = useParams<{ projectId: string }>();
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);
  const openUploadDrawer = useUIStore((s) => s.openUploadDrawer);
  const projectId = routeProjectId ?? currentProjectId;

  /* ── 拉取项目 / 素材 / 脚本 ── */
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectApi.get(projectId!),
    enabled: !!projectId,
  });
  const sourceScriptQuery = useQuery({
    queryKey: ["source-script", projectQuery.data?.sourceScriptId],
    queryFn: () => scriptApi.get(projectQuery.data!.sourceScriptId!),
    enabled: !!projectQuery.data?.sourceScriptId,
  });
  const sourceAssetProjectId = sourceScriptQuery.data?.projectId;
  const assetsQuery = useQuery({
    queryKey: ["assets", projectId],
    queryFn: () => assetApi.list({ projectId: projectId! }),
    enabled: !!projectId,
  });
  const sourceAssetsQuery = useQuery({
    queryKey: ["assets", sourceAssetProjectId],
    queryFn: () => assetApi.list({ projectId: sourceAssetProjectId! }),
    enabled: !!sourceAssetProjectId && sourceAssetProjectId !== projectId,
  });
  const scriptsQuery = useQuery({
    queryKey: ["scripts", projectId],
    queryFn: () => scriptApi.list({ projectId: projectId! }),
    enabled: !!projectId,
  });
  const snapshotScriptQuery = useQuery({
    queryKey: ["snapshot-script", projectId],
    queryFn: () => scriptApi.getSnapshot(projectId!),
    enabled: !!projectId && !!projectQuery.data?.sourceScriptId,
  });
  const timelineQuery = useQuery({
    queryKey: ["project-timeline", projectId],
    queryFn: () => projectApi.getTimeline(projectId!),
    enabled: !!projectId,
  });
  const projectMediaQuery = useQuery({
    queryKey: ["project-media", projectId],
    queryFn: () => projectApi.listMedia(projectId!),
    enabled: !!projectId,
  });
  const readOnly = projectQuery.data?.currentUserRole === "viewer";

  /* ── 本地状态 ── */
  const [clips, setClips] = useState<TLClip[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pxPerSec, setPxPerSec] = useState(40);
  const [aspect, setAspect] = useState("16:9");
  const [timelineVersion, setTimelineVersion] = useState(0);
  const [past, setPast] = useState<TLClip[][]>([]);
  const [future, setFuture] = useState<TLClip[][]>([]);
  const [autoSaveStatus, setAutoSaveStatus] = useState<"saved" | "saving" | "error">("saved");
  const [saveAttempt, setSaveAttempt] = useState(0);
  const [saveConflict, setSaveConflict] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [lastSavedSignature, setLastSavedSignature] = useState("");
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<"mp4" | "mov" | "prores">("mp4");
  const [exportResolution, setExportResolution] = useState<"480p" | "720p" | "1080p" | "4k">("1080p");
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportDownloading, setExportDownloading] = useState(false);

  const clipsRef = useRef(clips);
  const hydratedProjectRef = useRef<string | null>(null);
  const blockedSaveSignatureRef = useRef<string | null>(null);
  const currentSignature = useMemo(() => JSON.stringify({ clips, aspect }), [clips, aspect]);
  const currentSignatureRef = useRef(currentSignature);
  const inspectorSnapshotRef = useRef<TLClip[] | null>(null);
  const inspectorHistoryTimerRef = useRef<number | null>(null);
  const autoDownloadedJobRef = useRef<string | null>(null);
  useEffect(() => {
    clipsRef.current = clips;
    currentSignatureRef.current = currentSignature;
  }, [clips, currentSignature]);

  useEffect(
    () => () => {
      if (inspectorHistoryTimerRef.current) window.clearTimeout(inspectorHistoryTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    if (projectId) setCurrentProject(projectId);
  }, [projectId, setCurrentProject]);

  useEffect(() => {
    if (!projectId || !timelineQuery.data || hydratedProjectRef.current === projectId) return;
    const nextClips = timelineQuery.data.clips;
    const nextAspect = timelineQuery.data.aspectRatio || "16:9";
    const signature = JSON.stringify({ clips: nextClips, aspect: nextAspect });
    hydratedProjectRef.current = projectId;
    setLastSavedSignature(signature);
    blockedSaveSignatureRef.current = null;
    currentSignatureRef.current = signature;
    setClips(nextClips);
    setSelectedId(nextClips.find((clip) => clip.track === "video")?.id ?? nextClips[0]?.id ?? null);
    setAspect(nextAspect);
    setTimelineVersion(timelineQuery.data.version);
    setPast([]);
    setFuture([]);
    setAutoSaveStatus("saved");
  }, [projectId, timelineQuery.data]);

  const timelineDirty = Boolean(lastSavedSignature) && currentSignature !== lastSavedSignature;
  useNavigationBlocker(
    !readOnly && timelineDirty,
    autoSaveStatus === "error"
      ? "时间线保存失败，确定放弃当前修改并离开吗？"
      : "时间线仍有修改正在保存，确定现在离开吗？",
  );

  useEffect(() => {
    const warnBeforeLeave = (event: BeforeUnloadEvent) => {
      if (readOnly || !timelineDirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeLeave);
    return () => window.removeEventListener("beforeunload", warnBeforeLeave);
  }, [readOnly, timelineDirty]);

  const {
    mutate: saveTimeline,
    isPending: saveTimelinePending,
  } = useMutation({
    mutationFn: (input: projectApi.ProjectTimelineSaveInput & { signature: string }) =>
      projectApi.saveTimeline(projectId!, {
        version: input.version,
        aspectRatio: input.aspectRatio,
        clips: input.clips,
      }),
    onSuccess: (saved, variables) => {
      setTimelineVersion(saved.version);
      setLastSavedSignature(variables.signature);
      blockedSaveSignatureRef.current = null;
      setSaveConflict(false);
      setEditorError(null);
      setAutoSaveStatus(
        currentSignatureRef.current === variables.signature ? "saved" : "saving",
      );
    },
    onError: (error, variables) => {
      blockedSaveSignatureRef.current = variables.signature;
      setAutoSaveStatus("error");
      if (error instanceof HttpClientError && error.status === 409) {
        setSaveConflict(true);
        setEditorError("时间线已在其他页面更新。请点击顶部冲突提示重新加载最新版本。");
      } else {
        setSaveConflict(false);
        setEditorError(error instanceof Error ? `自动保存失败：${error.message}` : "自动保存失败，请重试");
      }
    },
  });

  useEffect(() => {
    if (
      !projectId ||
      readOnly ||
      hydratedProjectRef.current !== projectId ||
      currentSignature === lastSavedSignature ||
      blockedSaveSignatureRef.current === currentSignature ||
      saveTimelinePending
    ) {
      return;
    }

    setAutoSaveStatus("saving");
    const timer = window.setTimeout(() => {
      saveTimeline({
        version: timelineVersion,
        aspectRatio: aspect,
        clips,
        signature: currentSignature,
      });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [
    aspect,
    clips,
    currentSignature,
    lastSavedSignature,
    projectId,
    saveAttempt,
    saveTimeline,
    saveTimelinePending,
    timelineVersion,
    readOnly,
  ]);

  const retrySave = () => {
    if (saveConflict) {
      hydratedProjectRef.current = null;
      blockedSaveSignatureRef.current = null;
      setSaveConflict(false);
      setAutoSaveStatus("saving");
      void timelineQuery.refetch();
      setEditorError(null);
      setToast("正在重新加载最新时间线");
      return;
    }
    blockedSaveSignatureRef.current = null;
    setAutoSaveStatus("saving");
    setSaveAttempt((value) => value + 1);
  };

  const exportMutation = useMutation({
    mutationFn: () => generateApi.exportProject({
      projectId: projectId!,
      format: exportFormat,
      resolution: exportResolution,
    }),
    onSuccess: (result) => {
      setEditorError(null);
      setExportJobId(result.jobId);
      autoDownloadedJobRef.current = null;
      setToast(`${result.message}，可在弹窗中查看进度`);
    },
    onError: (error) =>
      setEditorError(error instanceof Error ? `导出失败：${error.message}` : "导出任务创建失败"),
  });

  const exportJobQuery = useQuery({
    queryKey: ["job", exportJobId],
    queryFn: () => jobApi.get(exportJobId!),
    enabled: !!exportJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["QUEUED", "RUNNING", "PAUSED"].includes(status) ? 2_000 : false;
    },
  });

  const exportJobActionMutation = useMutation({
    mutationFn: ({ action, id }: { action: "cancel" | "retry"; id: string }) =>
      action === "cancel" ? jobApi.cancel(id) : jobApi.retry(id),
    onSuccess: (job) => {
      setExportJobId(job.id);
      void exportJobQuery.refetch();
    },
    onError: (error) => setEditorError(error instanceof Error ? error.message : "导出任务操作失败"),
  });

  const downloadExport = useCallback(async (jobId: string) => {
    setExportDownloading(true);
    try {
      await jobApi.downloadResult(jobId);
      setToast("成片下载已开始");
    } catch (error) {
      setEditorError(error instanceof Error ? `下载失败：${error.message}` : "成片下载失败");
    } finally {
      setExportDownloading(false);
    }
  }, []);

  useEffect(() => {
    const job = exportJobQuery.data;
    if (!job || job.status !== "SUCCEEDED" || autoDownloadedJobRef.current === job.id) return;
    autoDownloadedJobRef.current = job.id;
    void downloadExport(job.id);
  }, [downloadExport, exportJobQuery.data]);

  const syncMediaMutation = useMutation({
    mutationFn: () => projectApi.syncMedia(projectId!),
    onSuccess: () => {
      setToast("已同步来源脚本素材和 AI 生成媒体");
      void projectMediaQuery.refetch();
    },
    onError: (error) => setEditorError(error instanceof Error ? error.message : "项目媒体同步失败"),
  });

  const assembleTimelineMutation = useMutation({
    mutationFn: () => projectApi.assembleTimelineFromScript(projectId!),
    onSuccess: () => {
      hydratedProjectRef.current = null;
      setEditorError(null);
      setToast("已按脚本装配完整时间线");
      void timelineQuery.refetch();
    },
    onError: (error) =>
      setEditorError(error instanceof Error ? `时间线装配失败：${error.message}` : "无法按脚本装配时间线"),
  });

  const startExport = () => {
    if (readOnly) {
      setToast("当前为查看者权限，不能导出或修改项目");
      return;
    }
    if (assetsQuery.isLoading || sourceAssetsQuery.isLoading) {
      setEditorError("素材信息仍在加载，请稍后再导出");
      return;
    }
    const availableAssets = [
      ...(assetsQuery.data?.items ?? []),
      ...(sourceAssetsQuery.data?.items ?? []),
    ];
    const issues = getTimelineIssues(clips, availableAssets);
    if (issues.length) {
      setEditorError(`无法导出：${issues[0]}${issues.length > 1 ? `（另有 ${issues.length - 1} 个问题）` : ""}`);
      return;
    }
    if (autoSaveStatus !== "saved" || currentSignature !== lastSavedSignature) {
      setEditorError(autoSaveStatus === "error" ? "请先重试保存时间线" : "时间线正在保存，请稍后导出");
      return;
    }
    setExportDialogOpen(true);
  };

  const timelineEnd = useMemo(
    () => Math.max(MIN_TIMELINE_DURATION, ...clips.map((c) => c.start + c.duration + 2), 0),
    [clips],
  );
  const playbackEnd = useMemo(
    () => Math.max(...clips.filter((clip) => clip.track === "video").map((clip) => clip.start + clip.duration), 0),
    [clips],
  );

  const selectedClip = useMemo(
    () => clips.find((c) => c.id === selectedId) ?? null,
    [clips, selectedId],
  );

  const linkedScript = sourceScriptQuery.data;
  const snapshotScript = snapshotScriptQuery.data;

  const findTimelineClipForShot = useCallback((unit: ScriptUnit, shot: Shot) => {
    return clips.find((clip) =>
      clip.sourceShotId === shot.id
      || clip.snapshotShotId === shot.id
      || Boolean(shot.selectedClipId && clip.sourceClipId === shot.selectedClipId),
    ) ?? clips.find((clip) =>
      clip.sourceUnitId === unit.id || clip.snapshotUnitId === unit.id,
    );
  }, [clips]);

  const locateScriptShot = useCallback((unit: ScriptUnit, shot: Shot) => {
    const timelineClip = findTimelineClipForShot(unit, shot);
    if (!timelineClip) {
      setToast(`「${shot.description || unit.outline || "该分镜"}」尚未剪入当前时间线`);
      return;
    }
    setSelectedId(timelineClip.id);
    setPlayhead(timelineClip.start);
    setPlaying(false);
  }, [findTimelineClipForShot]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2400);
    return () => clearTimeout(t);
  }, [toast]);

  /* ── 播放循环 ── */
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setPlayhead((p) => {
        const np = p + dt;
        if (np >= playbackEnd) {
          setPlaying(false);
          return playbackEnd;
        }
        return np;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, playbackEnd]);

  /* ── 历史 ── */
  const applyChange = useCallback((next: TLClip[]) => {
    if (readOnly) return;
    if (inspectorHistoryTimerRef.current) window.clearTimeout(inspectorHistoryTimerRef.current);
    inspectorHistoryTimerRef.current = null;
    inspectorSnapshotRef.current = null;
    setPast((p) => [...p, clipsRef.current]);
    setFuture([]);
    setClips(next);
  }, [readOnly]);

  /** 拖拽结束后提交历史：clips 已被实时修改，只需把拖拽前快照入栈 */
  const commitDrag = useCallback((snapshot: TLClip[]) => {
    if (readOnly) return;
    setPast((p) => [...p, snapshot]);
    setFuture([]);
  }, [readOnly]);

  const undo = useCallback(() => {
    if (readOnly) return;
    if (inspectorHistoryTimerRef.current) window.clearTimeout(inspectorHistoryTimerRef.current);
    if (inspectorSnapshotRef.current) {
      const snapshot = inspectorSnapshotRef.current;
      inspectorHistoryTimerRef.current = null;
      inspectorSnapshotRef.current = null;
      setFuture((futureClips) => [clipsRef.current, ...futureClips]);
      setClips(snapshot);
      return;
    }
    setPast((p) => {
      if (!p.length) return p;
      const prev = p[p.length - 1];
      setFuture((f) => [clipsRef.current, ...f]);
      setClips(prev);
      return p.slice(0, -1);
    });
  }, [readOnly]);

  const redo = useCallback(() => {
    if (readOnly) return;
    setFuture((f) => {
      if (!f.length) return f;
      const next = f[0];
      setPast((p) => [...p, clipsRef.current]);
      setClips(next);
      return f.slice(1);
    });
  }, [readOnly]);

  /* ── 检查器连续输入按一次操作写入历史，避免滑杆产生大量撤销节点 ── */
  const updateClip = useCallback((id: string, patch: Partial<TLClip>) => {
    if (readOnly) return;
    if (!inspectorSnapshotRef.current) inspectorSnapshotRef.current = clipsRef.current;
    setClips((prev) => prev.map((c) => (c.id === id
      ? {
          ...c,
          ...patch,
          syncStatus: c.sourceUnitId || c.snapshotUnitId ? "timeline_changed" : c.syncStatus,
        }
      : c)));
    if (inspectorHistoryTimerRef.current) window.clearTimeout(inspectorHistoryTimerRef.current);
    inspectorHistoryTimerRef.current = window.setTimeout(() => {
      const snapshot = inspectorSnapshotRef.current;
      inspectorSnapshotRef.current = null;
      inspectorHistoryTimerRef.current = null;
      if (snapshot) {
        setPast((history) => [...history, snapshot]);
        setFuture([]);
      }
    }, 400);
  }, [readOnly]);

  /* ── 添加素材到时间线 ── */
  const addAssetAudioToTimeline = useCallback(
    (asset: Asset, sourceClip?: Clip) => {
      if (readOnly) return;
      if (!asset.hasAudio) {
        setToast(`「${asset.name}」没有可用音轨`);
        return;
      }
      const assetDuration = getAssetDuration(asset);
      const sourceStart = sourceClip?.startTime ?? 0;
      const dur = sourceClip
        ? Math.max(sourceClip.duration, sourceClip.endTime - sourceClip.startTime)
        : assetDuration || 8;
      const start = Math.max(0, roundTime(playhead));
      const clip = makeClip(
        "audio",
        start,
        dur,
        asset.mediaType === "video" ? `${sourceClip?.title || asset.name}（音频）` : sourceClip?.title || asset.name,
        sourceClip?.variant || asset.variant,
        undefined,
        asset.id,
        sourceStart,
        sourceClip?.id,
      );
      applyChange([...clips, clip]);
      setSelectedId(clip.id);
      setPlayhead(start);
      setEditorError(null);
      setToast(`已添加「${clip.name}」到音频轨`);
    },
    [applyChange, clips, playhead, readOnly],
  );

  const addToTimeline = useCallback(
    (asset: Asset, sourceClip?: Clip) => {
      if (asset.mediaType === "audio") {
        addAssetAudioToTimeline(asset, sourceClip);
        return;
      }
      if (readOnly) return;
      const assetDuration = getAssetDuration(asset);
      const sourceStart = sourceClip?.startTime ?? 0;
      const dur = sourceClip
        ? Math.max(sourceClip.duration, sourceClip.endTime - sourceClip.startTime)
        : assetDuration || 8;
      const trackClips = clips.filter((c) => c.track === "video");
      const start = trackClips.length
        ? Math.max(...trackClips.map((c) => c.start + c.duration))
        : 0;
      const clip = makeClip(
        "video",
        start,
        dur,
        sourceClip?.title || asset.name,
        sourceClip?.variant || asset.variant,
        undefined,
        asset.id,
        sourceStart,
        sourceClip?.id,
      );
      applyChange([...clips, clip]);
      setSelectedId(clip.id);
      setPlayhead(start);
      setEditorError(null);
      setToast(`已添加「${clip.name}」到时间线`);
    },
    [addAssetAudioToTimeline, clips, applyChange, readOnly],
  );

  const detachSelectedAudio = useCallback(() => {
    if (readOnly || !selectedClip || selectedClip.track !== "video" || !selectedClip.assetId) return;
    const asset = [
      ...(assetsQuery.data?.items ?? []),
      ...(sourceAssetsQuery.data?.items ?? []),
      ...(projectMediaQuery.data?.items.flatMap((item) => item.asset ? [item.asset] : []) ?? []),
    ].find((candidate) => candidate.id === selectedClip.assetId);
    if (!asset?.hasAudio) {
      setToast("当前视频片段没有可分离的音轨");
      return;
    }
    const audioClip: TLClip = {
      ...makeClip(
        "audio",
        selectedClip.start,
        selectedClip.duration,
        `${selectedClip.name}（分离音频）`,
        selectedClip.variant,
        undefined,
        selectedClip.assetId,
        selectedClip.sourceStart,
        selectedClip.sourceClipId,
      ),
      audio: { ...selectedClip.audio, muted: false },
    };
    const next = clips.map((clip) => clip.id === selectedClip.id
      ? { ...clip, audio: { ...clip.audio, muted: true } }
      : clip);
    applyChange([...next, audioClip]);
    setSelectedId(audioClip.id);
    setToast("已将视频音轨分离到独立音频轨，并静音原视频片段");
  }, [
    applyChange,
    assetsQuery.data?.items,
    clips,
    projectMediaQuery.data?.items,
    readOnly,
    selectedClip,
    sourceAssetsQuery.data?.items,
  ]);

  const addGeneratedMediaToTimeline = useCallback(
    (item: projectApi.ProjectMediaItem) => {
      if (readOnly || !item.storagePath || !item.mediaUrl) return;
      if (item.mediaType === "audio") return;
      const videoClips = clips.filter((clip) => clip.track === "video");
      const start = videoClips.length
        ? Math.max(...videoClips.map((clip) => clip.start + clip.duration))
        : 0;
      const duration = item.duration > 0 ? item.duration : 5;
      const clip: TLClip = {
        ...makeClip("video", start, duration, item.name, "robot"),
        generatedMediaPath: item.storagePath,
        generatedMediaUrl: item.mediaUrl,
        generatedMediaType: item.mediaType,
        origin: "manual_generated",
      };
      applyChange([...clips, clip]);
      setSelectedId(clip.id);
      setPlayhead(start);
      setEditorError(null);
      setToast(`已添加「${item.name}」到时间线`);
    },
    [applyChange, clips, readOnly],
  );

  /* ── 分割 ── */
  const splitAtPlayhead = useCallback(() => {
    if (readOnly) return;
    if (!selectedClip) return;
    const { id, start, duration } = selectedClip;
    if (playhead <= start || playhead >= start + duration) {
      setToast("请将播放头移到片段内部再分割");
      return;
    }
    const leftDur = playhead - start;
    const rightDur = duration - leftDur;
    const right = {
      ...selectedClip,
      id: uid(),
      start: playhead,
      duration: rightDur,
      sourceStart: selectedClip.sourceStart + leftDur,
      transform: { ...selectedClip.transform, crop: { ...selectedClip.transform.crop } },
      adjust: { ...selectedClip.adjust },
      audio: { ...selectedClip.audio },
      syncStatus: selectedClip.sourceUnitId || selectedClip.snapshotUnitId
        ? "timeline_changed" as const
        : selectedClip.syncStatus,
    };
    applyChange(
      clips.map((c) => (c.id === id ? {
        ...c,
        duration: leftDur,
        syncStatus: c.sourceUnitId || c.snapshotUnitId ? "timeline_changed" : c.syncStatus,
      } : c)).concat(right),
    );
    setToast("已分割片段");
  }, [selectedClip, playhead, clips, applyChange, readOnly]);

  /* ── 删除 ── */
  const deleteSelected = useCallback(() => {
    if (readOnly) return;
    if (!selectedClip) return;
    applyChange(clips.filter((c) => c.id !== selectedClip.id));
    setSelectedId(null);
  }, [selectedClip, clips, applyChange, readOnly]);

  /* ── 缩放 ── */
  const zoomIn = () => setPxPerSec((p) => Math.min(120, Math.round(p * 1.25)));
  const zoomOut = () => setPxPerSec((p) => Math.max(12, Math.round(p * 0.8)));

  /* ── 加载 / 空状态 ── */
  if (!projectId) {
    return (
      <EmptyState
        title="未选择项目"
        desc="请从项目中心打开一个项目进入剪辑工作区。"
        actionLabel="前往项目中心"
        onAction={() => navigate("/workspace/projects")}
      />
    );
  }
  if (projectQuery.isLoading || timelineQuery.isLoading || sourceScriptQuery.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <Loader2 className="h-8 w-8 animate-spin text-blue" />
      </div>
    );
  }
  if (projectQuery.isError || timelineQuery.isError || sourceScriptQuery.isError) {
    const loadError = projectQuery.error ?? timelineQuery.error ?? sourceScriptQuery.error;
    return (
      <EmptyState
        title="加载失败"
        desc={loadError instanceof Error ? loadError.message : "无法加载项目剪辑数据"}
        actionLabel="前往项目中心"
        onAction={() => navigate("/workspace/projects")}
      />
    );
  }

  const project = projectQuery.data;
  const projectMedia = projectMediaQuery.data?.items ?? [];
  const referencedAssetIds = new Set(clips.map((clip) => clip.assetId).filter(Boolean));
  const assets = (() => {
    const byId = new Map<string, Asset>();
    for (const asset of [
      ...(assetsQuery.data?.items ?? []),
      ...projectMedia.flatMap((item) => item.asset ? [item.asset] : []),
      ...(sourceAssetsQuery.data?.items ?? []).filter((asset) => referencedAssetIds.has(asset.id)),
    ]) {
      byId.set(asset.id, asset);
    }
    return [...byId.values()];
  })();
  const scripts = scriptsQuery.data?.items ?? [];
  const assetsError = assetsQuery.error ?? projectMediaQuery.error ?? sourceAssetsQuery.error;
  const assetsLoading = assetsQuery.isLoading || projectMediaQuery.isLoading || sourceAssetsQuery.isLoading;
  const retryAssets = () => {
    void assetsQuery.refetch();
    void projectMediaQuery.refetch();
    if (sourceAssetProjectId && sourceAssetProjectId !== projectId) void sourceAssetsQuery.refetch();
  };

  const syncClipTextFromScript = (clip: TLClip, unit: ScriptUnit) => {
    if (readOnly) return;
    applyChange(clips.map((item) => item.id === clip.id
      ? { ...item, text: unit.text, syncStatus: "synced" }
      : item));
    setSelectedId(clip.id);
    setToast(`已将第 ${unit.index + 1} 句脚本文本更新到字幕`);
  };

  const applyScriptShotSelection = (clip: TLClip, shot: Shot) => {
    if (readOnly) return;
    if (!shot.selectedClipId) {
      setToast("该分镜当前没有选中的素材片段");
      return;
    }
    const asset = assets.find((candidate) =>
      candidate.clips.some((sourceClip) => sourceClip.id === shot.selectedClipId),
    );
    const sourceClip = asset?.clips.find((candidate) => candidate.id === shot.selectedClipId);
    if (!asset || !sourceClip) {
      setEditorError("脚本当前选中的素材不在可访问素材库中，请先检查素材权限或重新匹配");
      return;
    }
    const rangedDuration = sourceClip.endTime - sourceClip.startTime;
    const sourceDuration = rangedDuration > 0 ? rangedDuration : sourceClip.duration;
    if (sourceDuration < MIN_CLIP_DURATION) {
      setEditorError("脚本选中的素材片段过短，无法替换当前时间线片段");
      return;
    }
    const nextDuration = Math.min(clip.duration, sourceDuration);
    applyChange(clips.map((item) => item.id === clip.id
      ? {
          ...item,
          assetId: asset.id,
          sourceClipId: sourceClip.id,
          sourceStart: sourceClip.startTime,
          generatedMediaPath: undefined,
          generatedMediaUrl: undefined,
          generatedMediaType: undefined,
          duration: nextDuration,
          name: sourceClip.title || asset.name,
          variant: sourceClip.variant || asset.variant,
          origin: "script_match",
          syncStatus: "synced",
        }
      : item));
    setSelectedId(clip.id);
    setPlayhead(clip.start);
    setEditorError(null);
    setToast(`已使用脚本当前素材替换「${clip.name}」`);
  };

  return (
    <div className="flex h-screen flex-col bg-canvas">
      {/* 顶部 */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4">
        <BackButton
          fallback={`/workspace/projects/${projectId}`}
          fallbackLabel="项目主页"
          className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-muted transition hover:bg-canvas hover:text-text"
        />
        <div className="h-5 w-px bg-line" />
        <h1 className="flex-1 truncate text-base font-semibold text-ink">
          {project?.name ?? "剪辑工作区"}
        </h1>

        {readOnly && (
          <span className="rounded-full bg-amber/10 px-2.5 py-1 text-xs font-medium text-amber">
            只读查看
          </span>
        )}

        <button
          type="button"
          onClick={!readOnly && autoSaveStatus === "error" ? retrySave : undefined}
          className={clsx(
            "flex items-center gap-1.5 text-xs",
            autoSaveStatus === "error" ? "cursor-pointer text-red-600" : "cursor-default text-muted",
          )}
        >
          {autoSaveStatus === "saving" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue" />
          ) : autoSaveStatus === "error" ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : (
            <span className="h-2 w-2 rounded-full bg-teal" />
          )}
          {readOnly
            ? "查看者权限"
            : autoSaveStatus === "saving"
            ? "自动保存中…"
            : autoSaveStatus === "error"
              ? saveConflict ? "时间线冲突，点击重新加载" : "保存失败，点击重试"
              : "已自动保存"}
        </button>

        <button
          onClick={startExport}
          disabled={readOnly || exportMutation.isPending || assetsQuery.isLoading || sourceAssetsQuery.isLoading}
          className="flex items-center gap-1.5 rounded-lg bg-blue px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {exportMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          {exportMutation.isPending ? "创建任务…" : "导出"}
        </button>
      </header>

      {editorError && (
        <div className="flex shrink-0 items-center gap-3 border-b border-red/20 bg-red/10 px-4 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1">{editorError}</span>
          {autoSaveStatus === "error" && !readOnly && (
            <button
              type="button"
              onClick={retrySave}
              className="shrink-0 rounded-md bg-red/10 px-2.5 py-1 text-xs font-medium hover:bg-red/20"
            >
              {saveConflict ? "重新加载" : "重试保存"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setEditorError(null)}
            className="shrink-0 rounded px-2 py-1 text-xs hover:bg-red/10"
          >
            关闭
          </button>
        </div>
      )}

      {timelineQuery.data?.clips.length === 0 && linkedScript && (
        <div className="flex shrink-0 items-center gap-3 border-b border-blue/20 bg-blue-soft/40 px-4 py-2.5 text-sm text-text">
          <Film className="h-4 w-4 shrink-0 text-blue" />
          <div className="min-w-0 flex-1">
            <div className="font-medium">这个旧剪辑版本还没有装配时间线</div>
            <div className="mt-0.5 text-xs text-muted">
              可以按初剪脚本快照生成完整镜头、AI 画面、待补素材位置和字幕；不会覆盖已有剪辑内容。
            </div>
          </div>
          <button
            type="button"
            onClick={() => assembleTimelineMutation.mutate()}
            disabled={readOnly || assembleTimelineMutation.isPending || timelineQuery.isFetching}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-blue px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {assembleTimelineMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {assembleTimelineMutation.isPending ? "正在装配…" : "按脚本生成时间线"}
          </button>
        </div>
      )}

      {/* 三栏主体 */}
      <div className="flex min-h-0 flex-1">
        {/* 左栏 素材箱 */}
        <BinPanel
          assets={assets}
          assetsLoading={assetsLoading}
          assetsError={assetsError}
          onRetryAssets={retryAssets}
          scripts={scripts}
          linkedScript={linkedScript}
          snapshotScript={snapshotScript}
          snapshotLoading={snapshotScriptQuery.isLoading}
          snapshotError={snapshotScriptQuery.error}
          onRetrySnapshot={() => void snapshotScriptQuery.refetch()}
          timelineClips={clips}
          selectedClip={selectedClip}
          scriptsLoading={scriptsQuery.isLoading}
          scriptsError={scriptsQuery.error}
          onRetryScripts={() => void scriptsQuery.refetch()}
          onAddAsset={addToTimeline}
          onAddAssetAudio={addAssetAudioToTimeline}
          mediaItems={projectMedia}
          mediaLoading={projectMediaQuery.isLoading}
          mediaError={projectMediaQuery.error}
          onRetryMedia={() => void projectMediaQuery.refetch()}
          onSyncMedia={() => syncMediaMutation.mutate()}
          mediaSyncing={syncMediaMutation.isPending}
          onAddGeneratedMedia={addGeneratedMediaToTimeline}
          onUpload={() => readOnly ? setToast("当前为查看者权限，不能上传素材") : openUploadDrawer()}
          onOpenScript={(script) => navigate(`/workspace/scripts/${script.id}/editor`)}
          onLocateShot={locateScriptShot}
          readOnly={readOnly}
        />

        {/* 中栏 预览器 */}
        <PreviewPanel
          clips={clips}
          assets={assets}
          playhead={playhead}
          playing={playing}
          setPlaying={setPlaying}
          setPlayhead={setPlayhead}
          timelineEnd={timelineEnd}
          playbackEnd={playbackEnd}
          aspect={aspect}
          setAspect={readOnly ? () => undefined : setAspect}
          selectedClip={selectedClip}
          onRetryAssets={retryAssets}
        />

        {/* 右栏 检查器 */}
        <InspectorPanel
          clip={selectedClip}
          updateClip={updateClip}
          linkedScript={linkedScript}
          snapshotScript={snapshotScript}
          onOpenSourceScript={() => linkedScript && navigate(`/workspace/scripts/${linkedScript.id}/editor`)}
          onSyncScriptText={syncClipTextFromScript}
          onApplyScriptShot={applyScriptShotSelection}
          readOnly={readOnly}
        />
      </div>

      {/* 底部时间线 */}
      <Timeline
        clips={clips}
        assets={assets}
        pxPerSec={pxPerSec}
        timelineEnd={timelineEnd}
        playhead={playhead}
        setPlayhead={setPlayhead}
        selectedId={selectedId}
        setSelectedId={setSelectedId}
        setClips={readOnly ? () => undefined : setClips}
        commitDrag={commitDrag}
        clipsRef={clipsRef}
        onUndo={undo}
        onRedo={redo}
        canUndo={!readOnly && past.length > 0}
        canRedo={!readOnly && future.length > 0}
        onSplit={splitAtPlayhead}
        onDetachAudio={detachSelectedAudio}
        canDetachAudio={Boolean(
          !readOnly
          && selectedClip?.track === "video"
          && selectedClip.assetId
          && assets.find((asset) => asset.id === selectedClip.assetId)?.hasAudio
        )}
        onDelete={deleteSelected}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
      />

      <Modal
        open={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        title="导出成片"
        maskClosable={!exportMutation.isPending}
        footer={(
          <>
            <button
              type="button"
              onClick={() => setExportDialogOpen(false)}
              className="rounded-lg border border-line px-3 py-2 text-sm text-muted hover:bg-canvas hover:text-text"
            >
              关闭
            </button>
            {!exportJobId && (
              <button
                type="button"
                onClick={() => exportMutation.mutate()}
                disabled={exportMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {exportMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                {exportMutation.isPending ? "正在创建任务…" : "开始导出"}
              </button>
            )}
            {exportJobQuery.data?.status === "SUCCEEDED" && (
              <button
                type="button"
                onClick={() => void downloadExport(exportJobQuery.data!.id)}
                disabled={exportDownloading}
                className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {exportDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {exportDownloading ? "准备下载…" : "再次下载"}
              </button>
            )}
          </>
        )}
      >
        {!exportJobId ? (
          <div className="space-y-5">
            <p className="text-sm text-muted">导出会使用当前已保存的完整时间线。任务可在工作台继续查看和下载。</p>
            <label className="block text-sm font-medium text-text">
              格式
              <select
                value={exportFormat}
                onChange={(event) => setExportFormat(event.target.value as typeof exportFormat)}
                className="mt-2 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm"
              >
                <option value="mp4">MP4（推荐）</option>
                <option value="mov">MOV</option>
                <option value="prores">ProRes MOV</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-text">
              分辨率
              <select
                value={exportResolution}
                onChange={(event) => setExportResolution(event.target.value as typeof exportResolution)}
                className="mt-2 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm"
              >
                <option value="480p">480p</option>
                <option value="720p">720p</option>
                <option value="1080p">1080p（推荐）</option>
                <option value="4k">4K</option>
              </select>
            </label>
          </div>
        ) : exportJobQuery.isLoading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-blue" /></div>
        ) : exportJobQuery.data ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-text">{exportJobQuery.data.stage || "等待执行"}</span>
              <span className="font-mono text-blue">{exportJobQuery.data.progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-canvas">
              <div className="h-full rounded-full bg-gradient-to-r from-blue to-teal transition-all" style={{ width: `${exportJobQuery.data.progress}%` }} />
            </div>
            <p className={clsx("text-sm", exportJobQuery.data.status === "FAILED" ? "text-red" : "text-muted")}>
              {exportJobQuery.data.status === "FAILED"
                ? exportJobQuery.data.resultDetail || exportJobQuery.data.detail
                : exportJobQuery.data.detail}
            </p>
            <div className="flex gap-2">
              {["QUEUED", "RUNNING"].includes(exportJobQuery.data.status) && (
                <button
                  type="button"
                  onClick={() => exportJobActionMutation.mutate({ action: "cancel", id: exportJobQuery.data!.id })}
                  disabled={exportJobActionMutation.isPending}
                  className="rounded-lg border border-red/30 px-3 py-1.5 text-xs font-medium text-red hover:bg-red/10"
                >取消导出</button>
              )}
              {exportJobQuery.data.status === "FAILED" && (
                <button
                  type="button"
                  onClick={() => exportJobActionMutation.mutate({ action: "retry", id: exportJobQuery.data!.id })}
                  disabled={exportJobActionMutation.isPending}
                  className="rounded-lg border border-blue/30 px-3 py-1.5 text-xs font-medium text-blue hover:bg-blue-soft"
                >重试导出</button>
              )}
              {["FAILED", "CANCELLED"].includes(exportJobQuery.data.status) && (
                <button
                  type="button"
                  onClick={() => setExportJobId(null)}
                  className="rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:bg-canvas"
                >修改导出设置</button>
              )}
            </div>
          </div>
        ) : (
          <PanelLoadError message={exportJobQuery.error instanceof Error ? exportJobQuery.error.message : "任务状态加载失败"} onRetry={() => void exportJobQuery.refetch()} />
        )}
      </Modal>

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-ink px-4 py-2 text-sm text-white shadow-soft">
          {toast}
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────
   左栏：素材箱
   ────────────────────────────────────────────── */

type BinTab = "assets" | "scripts" | "ai";

type DetailedScript = Script & { units: ScriptUnit[] };

function findSnapshotUnit(snapshotScript: DetailedScript | undefined, unit: ScriptUnit) {
  if (!snapshotScript) return undefined;
  return snapshotScript.units.find((candidate) => candidate.sourceUnitId === unit.id)
    ?? snapshotScript.units.find((candidate) => !candidate.sourceUnitId && candidate.index === unit.index);
}

function findSnapshotShot(snapshotUnit: ScriptUnit | undefined, shot: Shot) {
  if (!snapshotUnit) return undefined;
  return snapshotUnit.shots.find((candidate) => candidate.sourceShotId === shot.id)
    ?? snapshotUnit.shots.find((candidate) => !candidate.sourceShotId && candidate.index === shot.index);
}

function findCurrentUnitForSnapshot(script: DetailedScript, snapshotUnit: ScriptUnit) {
  return snapshotUnit.sourceUnitId
    ? script.units.find((candidate) => candidate.id === snapshotUnit.sourceUnitId)
    : script.units.find((candidate) => candidate.index === snapshotUnit.index);
}

function findCurrentShotForSnapshot(unit: ScriptUnit, snapshotShot: Shot) {
  return snapshotShot.sourceShotId
    ? unit.shots.find((candidate) => candidate.id === snapshotShot.sourceShotId)
    : unit.shots.find((candidate) => candidate.index === snapshotShot.index);
}

const sameText = (left?: string | null, right?: string | null) =>
  (left ?? "") === (right ?? "");

const sameDuration = (left?: number | null, right?: number | null) =>
  Math.abs((left ?? 0) - (right ?? 0)) < 0.01;

function getScriptChangeSummary(script: DetailedScript, snapshotScript?: DetailedScript) {
  if (!snapshotScript) return { changeCount: 0, deletedUnitCount: 0, deletedShotCount: 0 };

  let changeCount = 0;
  let deletedUnitCount = 0;
  let deletedShotCount = 0;

  for (const unit of script.units) {
    const snapshotUnit = findSnapshotUnit(snapshotScript, unit);
    if (!snapshotUnit) {
      changeCount += 1;
      continue;
    }
    if (!sameText(unit.text, snapshotUnit.text)) changeCount += 1;
    for (const shot of unit.shots) {
      const snapshotShot = findSnapshotShot(snapshotUnit, shot);
      if (!snapshotShot) {
        changeCount += 1;
        continue;
      }
      if (!sameText(shot.description, snapshotShot.description)) changeCount += 1;
      if (!sameDuration(shot.duration, snapshotShot.duration)) changeCount += 1;
      if ((shot.selectedClipId ?? null) !== (snapshotShot.selectedClipId ?? null)) changeCount += 1;
    }
  }

  for (const snapshotUnit of snapshotScript.units) {
    const currentUnit = findCurrentUnitForSnapshot(script, snapshotUnit);
    if (!currentUnit) {
      deletedUnitCount += 1;
      changeCount += 1;
      continue;
    }
    for (const snapshotShot of snapshotUnit.shots) {
      if (!findCurrentShotForSnapshot(currentUnit, snapshotShot)) {
        deletedShotCount += 1;
        changeCount += 1;
      }
    }
  }

  return { changeCount, deletedUnitCount, deletedShotCount };
}

function BinPanel({
  assets,
  assetsLoading,
  assetsError,
  onRetryAssets,
  scripts,
  linkedScript,
  snapshotScript,
  snapshotLoading,
  snapshotError,
  onRetrySnapshot,
  timelineClips,
  selectedClip,
  scriptsLoading,
  scriptsError,
  onRetryScripts,
  onAddAsset,
  onAddAssetAudio,
  mediaItems,
  mediaLoading,
  mediaError,
  onRetryMedia,
  onSyncMedia,
  mediaSyncing,
  onAddGeneratedMedia,
  onUpload,
  onOpenScript,
  onLocateShot,
  readOnly,
}: {
  assets: Asset[];
  assetsLoading: boolean;
  assetsError: Error | null;
  onRetryAssets: () => void;
  scripts: Script[];
  linkedScript?: DetailedScript;
  snapshotScript?: DetailedScript;
  snapshotLoading: boolean;
  snapshotError: Error | null;
  onRetrySnapshot: () => void;
  timelineClips: TLClip[];
  selectedClip: TLClip | null;
  scriptsLoading: boolean;
  scriptsError: Error | null;
  onRetryScripts: () => void;
  onAddAsset: (asset: Asset, sourceClip?: Clip) => void;
  onAddAssetAudio: (asset: Asset, sourceClip?: Clip) => void;
  mediaItems: projectApi.ProjectMediaItem[];
  mediaLoading: boolean;
  mediaError: Error | null;
  onRetryMedia: () => void;
  onSyncMedia: () => void;
  mediaSyncing: boolean;
  onAddGeneratedMedia: (item: projectApi.ProjectMediaItem) => void;
  onUpload: () => void;
  onOpenScript: (script: Script) => void;
  onLocateShot: (unit: ScriptUnit, shot: Shot) => void;
  readOnly: boolean;
}) {
  const [tab, setTab] = useState<BinTab>("assets");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("全部");
  const [mediaType, setMediaType] = useState<"全部" | "video" | "audio">("全部");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const sourceOptions = useMemo(
    () => ["全部", ...Array.from(new Set(assets.map((asset) => asset.source).filter(Boolean)))],
    [assets],
  );

  const filteredAssets = useMemo(() => {
    return assets.filter(
      (a) =>
        (type === "全部" || a.source === type) &&
        (mediaType === "全部" || a.mediaType === mediaType) &&
        a.name.toLowerCase().includes(query.toLowerCase()),
    );
  }, [assets, mediaType, type, query]);
  const generatedMedia = useMemo(
    () => mediaItems.filter((item) => item.kind.startsWith("ai_")),
    [mediaItems],
  );

  return (
    <section className="flex w-64 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex shrink-0 border-b border-line">
        {([
          { key: "assets", label: "素材" },
          { key: "scripts", label: "脚本" },
          { key: "ai", label: "AI生成" },
        ] as { key: BinTab; label: string }[]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              "flex-1 py-2.5 text-xs font-medium transition",
              tab === t.key ? "border-b-2 border-blue text-blue" : "text-muted hover:text-text",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "assets" && (
        <div className="flex shrink-0 flex-col gap-2 border-b border-line p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索素材"
              className="w-full rounded-lg border border-line bg-canvas py-1.5 pl-8 pr-2 text-xs text-text focus:border-blue focus:bg-surface"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={mediaType}
              onChange={(e) => setMediaType(e.target.value as typeof mediaType)}
              className="min-w-0 rounded-lg border border-line bg-canvas px-2 py-1.5 text-xs text-text"
            >
              <option value="全部">全部类型</option>
              <option value="video">视频</option>
              <option value="audio">音频</option>
            </select>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="min-w-0 rounded-lg border border-line bg-canvas px-2 py-1.5 text-xs text-text"
            >
              {sourceOptions.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <button
            onClick={onUpload}
            disabled={readOnly}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-blue/50 bg-blue-soft/40 py-2 text-xs font-medium text-blue transition hover:bg-blue-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Upload className="h-3.5 w-3.5" />
            上传素材
          </button>
        </div>
      )}

      {tab === "ai" && (
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line p-3">
          <div>
            <div className="text-xs font-medium text-text">项目 AI 媒体</div>
            <div className="text-[10px] text-muted">{generatedMedia.length} 项 · 不复制源文件</div>
          </div>
          <button
            type="button"
            onClick={onSyncMedia}
            disabled={readOnly || mediaSyncing}
            className="flex items-center gap-1 rounded-lg border border-line px-2 py-1.5 text-[11px] text-muted hover:bg-canvas hover:text-blue disabled:opacity-40"
          >
            {mediaSyncing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            同步
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "assets" &&
          (assetsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-blue" />
            </div>
          ) : assetsError ? (
            <PanelLoadError
              message={assetsError.message || "素材加载失败"}
              onRetry={onRetryAssets}
            />
          ) : filteredAssets.length === 0 ? (
            <EmptyHint icon={Film} text="暂无素材，上传后可从列表添加到时间线" />
          ) : (
            <div className="space-y-1.5">
              {filteredAssets.map((asset) => {
                const expanded = selectedAssetId === asset.id;
                return (
                  <div
                    key={asset.id}
                    className={clsx(
                      "overflow-hidden rounded-lg border transition",
                      expanded ? "border-blue/40 bg-blue-soft/20" : "border-transparent hover:border-line hover:bg-canvas",
                    )}
                  >
                    <div className="group flex items-center">
                      <button
                        type="button"
                        onClick={() => setSelectedAssetId(expanded ? null : asset.id)}
                        onDoubleClick={() => !readOnly && onAddAsset(asset)}
                        className="flex min-w-0 flex-1 items-center gap-2 p-1.5 text-left"
                        title="单击展开识别片段，双击添加完整素材"
                      >
                        {asset.mediaType === "audio" ? (
                          <span className="flex h-11 w-16 shrink-0 items-center justify-center rounded bg-teal/10 text-teal">
                            <Music className="h-5 w-5" />
                          </span>
                        ) : (
                          <Thumbnail
                            variant={asset.variant}
                            imageUrl={asset.thumbnailUrl}
                            className="h-11 w-16 shrink-0 rounded"
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-xs font-medium text-text">{asset.name}</div>
                          <div className="text-[11px] text-muted">
                            {fmtTimecode(getAssetDuration(asset))} · {asset.mediaType === "audio" ? "音频素材" : `${asset.clips.length} 个识别片段`}
                          </div>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => onAddAsset(asset)}
                        disabled={readOnly}
                        aria-label={`添加完整素材 ${asset.name} 到时间线`}
                        title={asset.mediaType === "audio" ? "添加到音频轨" : "添加到视频轨"}
                        className="mr-1.5 rounded-md p-1.5 text-muted transition hover:bg-blue-soft hover:text-blue disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                      {asset.mediaType === "video" && asset.hasAudio && (
                        <button
                          type="button"
                          onClick={() => onAddAssetAudio(asset)}
                          disabled={readOnly}
                          aria-label={`仅添加 ${asset.name} 的音频到时间线`}
                          title="仅添加音频"
                          className="mr-1.5 rounded-md p-1.5 text-muted transition hover:bg-teal/10 hover:text-teal disabled:cursor-not-allowed disabled:opacity-30"
                        >
                          <Music className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>

                    {expanded && asset.mediaType === "audio" && asset.mediaUrl && (
                      <div className="border-t border-blue/10 p-2">
                        <audio src={asset.mediaUrl} controls preload="metadata" className="h-8 w-full" />
                      </div>
                    )}

                    {expanded && asset.mediaType === "video" && asset.clips.length > 0 && (
                      <div className="space-y-1 border-t border-blue/10 p-1.5">
                        {asset.clips.map((sourceClip, index) => (
                          <div key={sourceClip.id} className="flex items-center gap-2 rounded-md bg-surface px-2 py-1.5">
                            <button
                              type="button"
                              onDoubleClick={() => !readOnly && onAddAsset(asset, sourceClip)}
                              className="min-w-0 flex-1 text-left"
                              title="双击添加该识别片段"
                            >
                              <div className="truncate text-[11px] font-medium text-text">
                                {sourceClip.title || `片段 ${String(index + 1).padStart(2, "0")}`}
                              </div>
                              <div className="font-mono text-[10px] text-muted">
                                {fmtTimecode(sourceClip.startTime)}–{fmtTimecode(sourceClip.endTime)}
                              </div>
                            </button>
                            {asset.hasAudio && (
                              <button
                                type="button"
                                onClick={() => onAddAssetAudio(asset, sourceClip)}
                                disabled={readOnly}
                                aria-label={`仅添加识别片段 ${sourceClip.title || index + 1} 的音频`}
                                title="仅添加音频"
                                className="rounded p-1 text-muted hover:bg-teal/10 hover:text-teal disabled:opacity-30"
                              >
                                <Music className="h-3 w-3" />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => onAddAsset(asset, sourceClip)}
                              disabled={readOnly}
                              aria-label={`添加识别片段 ${sourceClip.title || index + 1}`}
                              className="rounded p-1 text-muted hover:bg-blue-soft hover:text-blue disabled:opacity-30"
                            >
                              <Plus className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}

        {tab === "scripts" && linkedScript && (
          <LinkedScriptOutline
            script={linkedScript}
            snapshotScript={snapshotScript}
            snapshotLoading={snapshotLoading}
            snapshotError={snapshotError}
            onRetrySnapshot={onRetrySnapshot}
            timelineClips={timelineClips}
            selectedClip={selectedClip}
            onLocateShot={onLocateShot}
            onOpenScript={() => onOpenScript(linkedScript)}
          />
        )}

        {tab === "scripts" && !linkedScript &&
          (scriptsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-blue" />
            </div>
          ) : scriptsError ? (
            <PanelLoadError
              message={scriptsError.message || "脚本加载失败"}
              onRetry={onRetryScripts}
            />
          ) : scripts.length === 0 ? (
            <EmptyHint icon={FileText} text="暂无脚本" />
          ) : (
            <div className="space-y-1.5">
              {scripts.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onOpenScript(s)}
                  className="flex w-full items-center gap-2 rounded-lg border border-transparent p-1.5 text-left transition hover:border-line hover:bg-canvas"
                >
                  <div className="flex h-11 w-16 shrink-0 items-center justify-center rounded bg-blue-soft">
                    <FileText className="h-5 w-5 text-blue" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-text">{s.title}</div>
                    <div className="text-[11px] text-muted">
                      {s.unitCount} 单元 · {s.status}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ))}

        {tab === "ai" && (
          mediaLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-blue" /></div>
          ) : mediaError ? (
            <PanelLoadError message={mediaError.message || "AI 媒体加载失败"} onRetry={onRetryMedia} />
          ) : generatedMedia.length ? (
            <div className="space-y-1.5">
              {generatedMedia.map((item) => (
                  <div key={item.id} className="flex items-center gap-2 rounded-lg border border-line p-1.5">
                    {item.mediaType === "image" ? (
                      <Thumbnail variant="robot" imageUrl={item.thumbnailUrl || item.mediaUrl} className="h-11 w-16 shrink-0 rounded" />
                    ) : item.mediaUrl ? (
                      <video src={item.mediaUrl} preload="metadata" muted className="h-11 w-16 shrink-0 rounded bg-ink object-cover" />
                    ) : (
                      <div className="flex h-11 w-16 shrink-0 items-center justify-center rounded bg-blue-soft"><Film className="h-4 w-4 text-blue" /></div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-text">{item.name}</div>
                      <div className="text-[11px] text-muted">
                        {item.kind === "ai_image" ? "AI 图片" : item.kind === "ai_effect_video" ? "特效视频" : "AI 视频"}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onAddGeneratedMedia(item)}
                      disabled={readOnly || !item.mediaUrl || !item.storagePath}
                      aria-label={`添加 ${item.name} 到时间线`}
                      className="rounded-md p-1.5 text-muted hover:bg-blue-soft hover:text-blue disabled:opacity-30"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
            </div>
          ) : (
            <EmptyHint icon={Sparkles} text="暂无 AI 生成媒体，可从来源脚本同步" />
          )
        )}
      </div>
    </section>
  );
}

function LinkedScriptOutline({
  script,
  snapshotScript,
  snapshotLoading,
  snapshotError,
  onRetrySnapshot,
  timelineClips,
  selectedClip,
  onLocateShot,
  onOpenScript,
}: {
  script: DetailedScript;
  snapshotScript?: DetailedScript;
  snapshotLoading: boolean;
  snapshotError: Error | null;
  onRetrySnapshot: () => void;
  timelineClips: TLClip[];
  selectedClip: TLClip | null;
  onLocateShot: (unit: ScriptUnit, shot: Shot) => void;
  onOpenScript: () => void;
}) {
  const isClipLinkedToShot = (clip: TLClip, unit: ScriptUnit, shot: Shot) =>
    clip.sourceShotId === shot.id
    || clip.snapshotShotId === shot.id
    || Boolean(shot.selectedClipId && clip.sourceClipId === shot.selectedClipId)
    || (
      !clip.sourceShotId
      && !clip.snapshotShotId
      && (clip.sourceUnitId === unit.id || clip.snapshotUnitId === unit.id)
    );

  const linkedShotCount = script.units.reduce(
    (count, unit) => count + unit.shots.filter(
      (shot) => timelineClips.some((clip) => isClipLinkedToShot(clip, unit, shot)),
    ).length,
    0,
  );
  const shotCount = script.units.reduce((count, unit) => count + unit.shots.length, 0);
  const changeSummary = getScriptChangeSummary(script, snapshotScript);

  return (
    <div className="space-y-2">
      <div className="rounded-lg border border-blue/20 bg-blue-soft/30 p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-text">{script.title}</div>
            <div className="mt-1 text-[11px] text-muted">{linkedShotCount}/{shotCount} 个分镜已剪入当前版本</div>
            {snapshotScript && changeSummary.changeCount > 0 && (
              <div className="mt-1.5 inline-flex rounded-full bg-amber/10 px-2 py-0.5 text-[10px] font-medium text-amber">
                脚本有 {changeSummary.changeCount} 处更新
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onOpenScript}
            className="shrink-0 rounded-md border border-blue/20 bg-surface px-2 py-1 text-[10px] font-medium text-blue hover:bg-blue-soft"
          >
            查看脚本
          </button>
        </div>
        {(changeSummary.deletedUnitCount > 0 || changeSummary.deletedShotCount > 0) && (
          <div className="mt-2 rounded-md border border-amber/20 bg-amber/10 px-2 py-1.5 text-[10px] leading-relaxed text-amber">
            初剪后脚本删除了
            {changeSummary.deletedUnitCount > 0 ? ` ${changeSummary.deletedUnitCount} 个脚本句` : ""}
            {changeSummary.deletedUnitCount > 0 && changeSummary.deletedShotCount > 0 ? "、" : ""}
            {changeSummary.deletedShotCount > 0 ? ` ${changeSummary.deletedShotCount} 个分镜` : ""}
            ，对应时间线内容不会自动删除，请人工检查。
          </div>
        )}
        {snapshotLoading && (
          <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted">
            <Loader2 className="h-3 w-3 animate-spin" />
            正在读取初剪脚本基线…
          </div>
        )}
        {snapshotError && (
          <div className="mt-2 rounded-md border border-red/20 bg-red/10 px-2 py-1.5 text-[10px] leading-relaxed text-red-700">
            <div>无法读取初剪脚本基线，暂时不能检测脚本变化。</div>
            <button
              type="button"
              onClick={onRetrySnapshot}
              className="mt-1 font-medium underline underline-offset-2"
            >
              重试
            </button>
          </div>
        )}
      </div>

      {script.units.map((unit) => {
        const snapshotUnit = findSnapshotUnit(snapshotScript, unit);
        const unitChanges = !snapshotScript
          ? []
          : !snapshotUnit
            ? ["新增脚本句"]
            : !sameText(unit.text, snapshotUnit.text)
              ? ["台词已修改"]
              : [];
        const unitClips = timelineClips.filter((clip) =>
          clip.sourceUnitId === unit.id
          || clip.snapshotUnitId === unit.id
          || unit.shots.some((shot) => isClipLinkedToShot(clip, unit, shot)),
        );
        return (
          <section key={unit.id} className="overflow-hidden rounded-lg border border-line bg-surface">
            <header className="border-b border-line bg-canvas/60 px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <strong className="min-w-0 truncate text-[11px] text-text">
                  {String(unit.index + 1).padStart(2, "0")} · {unit.outline || unit.text || "未命名脚本句"}
                </strong>
                <span className={clsx(
                  "shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-medium",
                  unitClips.length ? "bg-teal/10 text-teal" : "bg-amber/10 text-amber",
                )}>
                  {unitClips.length ? "已进入时间线" : "尚未剪入"}
                </span>
              </div>
              {unit.text && <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted">{unit.text}</p>}
              {unitChanges.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {unitChanges.map((change) => (
                    <span key={change} className="rounded-full bg-amber/10 px-1.5 py-0.5 text-[9px] font-medium text-amber">
                      {change}
                    </span>
                  ))}
                </div>
              )}
            </header>
            <div className="space-y-1 p-1.5">
              {unit.shots.map((shot, shotIndex) => {
                const snapshotShot = findSnapshotShot(snapshotUnit, shot);
                const shotChanges = !snapshotScript || !snapshotUnit
                  ? []
                  : !snapshotShot
                    ? ["新增分镜"]
                    : [
                        !sameText(shot.description, snapshotShot.description) ? "描述已修改" : null,
                        !sameDuration(shot.duration, snapshotShot.duration) ? "时长已修改" : null,
                        (shot.selectedClipId ?? null) !== (snapshotShot.selectedClipId ?? null)
                          ? "脚本素材已变更"
                          : null,
                      ].filter((change): change is string => Boolean(change));
                const shotClips = timelineClips.filter((clip) => isClipLinkedToShot(clip, unit, shot));
                const active = Boolean(selectedClip && shotClips.some((clip) => clip.id === selectedClip.id));
                return (
                  <button
                    key={shot.id}
                    type="button"
                    onClick={() => onLocateShot(unit, shot)}
                    className={clsx(
                      "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition",
                      active ? "bg-blue-soft text-blue" : "hover:bg-canvas",
                    )}
                  >
                    <span className={clsx(
                      "mt-1 h-2 w-2 shrink-0 rounded-full",
                      shotClips.length ? "bg-teal" : "bg-amber",
                    )} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11px] font-medium">
                        Shot {shotIndex + 1} · {shot.description || "未填写画面描述"}
                      </span>
                      <span className="mt-0.5 block text-[9px] text-muted">
                        {shotClips.length ? `${shotClips.length} 个时间线片段` : "尚未剪入"} · {shot.duration}s
                      </span>
                      {shotChanges.length > 0 && (
                        <span className="mt-1 flex flex-wrap gap-1">
                          {shotChanges.map((change) => (
                            <span key={change} className="rounded-full bg-amber/10 px-1.5 py-0.5 text-[9px] font-medium text-amber">
                              {change}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/* ──────────────────────────────────────────────
   中栏：预览器
   ────────────────────────────────────────────── */

function PreviewPanel({
  clips,
  assets,
  playhead,
  playing,
  setPlaying,
  setPlayhead,
  timelineEnd,
  playbackEnd,
  aspect,
  setAspect,
  selectedClip,
  onRetryAssets,
}: {
  clips: TLClip[];
  assets: Asset[];
  playhead: number;
  playing: boolean;
  setPlaying: (v: boolean) => void;
  setPlayhead: (v: number) => void;
  timelineEnd: number;
  playbackEnd: number;
  aspect: string;
  setAspect: (v: string) => void;
  selectedClip: TLClip | null;
  onRetryAssets: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRefs = useRef<Map<string, HTMLAudioElement>>(new Map());
  const stageHostRef = useRef<HTMLDivElement>(null);
  const [failedVideoSource, setFailedVideoSource] = useState<string | null>(null);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });

  // 当前播放头所在视频片段
  const activeVideo = useMemo(
    () =>
      clips.find(
        (c) => c.track === "video" && playhead >= c.start && playhead < c.start + c.duration,
      ) ?? null,
    [clips, playhead],
  );

  const aspectValue = useMemo(() => {
    switch (aspect) {
      case "9:16":
        return 9 / 16;
      case "1:1":
        return 1;
      case "4:3":
        return 4 / 3;
      default:
        return 16 / 9;
    }
  }, [aspect]);

  useEffect(() => {
    const host = stageHostRef.current;
    if (!host) return;
    const updateSize = () => {
      const styles = window.getComputedStyle(host);
      const availableWidth = host.clientWidth
        - Number.parseFloat(styles.paddingLeft)
        - Number.parseFloat(styles.paddingRight);
      const availableHeight = host.clientHeight
        - Number.parseFloat(styles.paddingTop)
        - Number.parseFloat(styles.paddingBottom);
      if (!availableWidth || !availableHeight) return;
      const width = Math.max(1, Math.min(availableWidth, availableHeight * aspectValue));
      setStageSize({ width, height: width / aspectValue });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(host);
    return () => observer.disconnect();
  }, [aspectValue]);

  const selectedVideo = selectedClip?.track === "video" ? selectedClip : null;
  const previewClip = activeVideo ?? (!playing ? selectedVideo : null);
  const previewAsset = assets.find((asset) => asset.id === previewClip?.assetId);
  const generatedVideoSource = previewClip?.generatedMediaType === "video"
    ? previewClip.generatedMediaUrl
    : undefined;
  const generatedImageSource = previewClip?.generatedMediaType === "image"
    ? previewClip.generatedMediaUrl
    : undefined;
  const videoSource = previewClip?.track === "video"
    ? previewAsset?.mediaUrl ?? generatedVideoSource
    : undefined;
  const mediaError = Boolean(videoSource && failedVideoSource === videoSource);
  const expectedMediaTime = previewClip
    ? Math.max(0, previewClip.sourceStart + Math.max(0, playhead - previewClip.start))
    : 0;
  const hasPlayableVideo = clips.some((clip) => clip.track === "video");
  const activeSubtitle = clips.find(
    (clip) => clip.track === "subtitle" && playhead >= clip.start && playhead < clip.start + clip.duration,
  );
  const previewText = activeSubtitle?.text ?? activeVideo?.text;
  const firstVideoStart = useMemo(
    () => {
      const starts = clips.filter((clip) => clip.track === "video").map((clip) => clip.start);
      return starts.length ? Math.min(...starts) : 0;
    },
    [clips],
  );
  const independentAudio = useMemo(
    () => clips
      .filter((clip) => clip.track === "audio" && clip.assetId)
      .map((clip) => ({
        clip,
        source: assets.find((asset) => asset.id === clip.assetId)?.mediaUrl,
      }))
      .filter((item): item is { clip: TLClip; source: string } => Boolean(item.source)),
    [assets, clips],
  );

  const clipGainAtPlayhead = useCallback((clip: TLClip) => {
    if (clip.audio.muted) return 0;
    const localTime = Math.max(0, playhead - clip.start);
    const fadeInGain = clip.audio.fadeIn > 0 ? Math.min(1, localTime / clip.audio.fadeIn) : 1;
    const remaining = Math.max(0, clip.duration - localTime);
    const fadeOutGain = clip.audio.fadeOut > 0 ? Math.min(1, remaining / clip.audio.fadeOut) : 1;
    return Math.max(0, Math.min(1, (clip.audio.volume / 100) * fadeInGain * fadeOutGain));
  }, [playhead]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !videoSource || !previewClip) return;
    video.volume = clipGainAtPlayhead(previewClip);
    video.muted = previewClip.audio.muted;
    if (Number.isFinite(video.duration) && expectedMediaTime <= video.duration) {
      if (Math.abs(video.currentTime - expectedMediaTime) > (playing ? 0.3 : 0.05)) {
        video.currentTime = expectedMediaTime;
      }
    }
  }, [clipGainAtPlayhead, expectedMediaTime, playing, previewClip, videoSource]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing && activeVideo && videoSource && !mediaError) {
      void video.play().catch(() => setPlaying(false));
    } else {
      video.pause();
    }
  }, [activeVideo, mediaError, playing, setPlaying, videoSource]);

  useEffect(() => {
    for (const { clip, source } of independentAudio) {
      const audio = audioRefs.current.get(clip.id);
      if (!audio || audio.src !== source && !audio.currentSrc) continue;
      const active = playhead >= clip.start && playhead < clip.start + clip.duration;
      const expectedTime = Math.max(0, clip.sourceStart + playhead - clip.start);
      audio.volume = clipGainAtPlayhead(clip);
      audio.muted = clip.audio.muted;

      if (!active) {
        audio.pause();
        continue;
      }
      if (Number.isFinite(audio.duration) && expectedTime <= audio.duration) {
        if (Math.abs(audio.currentTime - expectedTime) > (playing ? 0.3 : 0.05)) {
          audio.currentTime = expectedTime;
        }
      }
      if (playing) {
        void audio.play().catch(() => undefined);
      } else {
        audio.pause();
      }
    }
  }, [clipGainAtPlayhead, independentAudio, playhead, playing]);

  useEffect(() => () => {
    for (const audio of audioRefs.current.values()) audio.pause();
    audioRefs.current.clear();
  }, []);

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-ink/95">
      <div className="hidden" aria-hidden="true">
        {independentAudio.map(({ clip, source }) => (
          <audio
            key={`${clip.id}:${source}`}
            ref={(element) => {
              if (element) audioRefs.current.set(clip.id, element);
              else audioRefs.current.delete(clip.id);
            }}
            src={source}
            preload="auto"
            onLoadedMetadata={(event) => {
              const expectedTime = Math.max(0, clip.sourceStart + playhead - clip.start);
              event.currentTarget.currentTime = Math.min(
                expectedTime,
                event.currentTarget.duration || expectedTime,
              );
            }}
          />
        ))}
      </div>
      {/* 画幅选择 */}
      <div className="flex shrink-0 items-center gap-2 bg-ink px-4 py-2">
        <span className="text-xs text-white/60">画幅</span>
        <div className="flex gap-1">
          {ASPECT_OPTIONS.map((a) => (
            <button
              key={a}
              onClick={() => setAspect(a)}
              className={clsx(
                "rounded px-2 py-0.5 text-[11px] font-medium transition",
                aspect === a ? "bg-white text-ink" : "text-white/60 hover:text-white",
              )}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* 预览画面 */}
      <div ref={stageHostRef} className="flex min-h-0 flex-1 items-center justify-center p-4">
        <div
          data-testid="preview-stage"
          className="relative shrink-0 overflow-hidden rounded-lg bg-black shadow-soft"
          style={{
            width: stageSize.width || "100%",
            height: stageSize.height || undefined,
            aspectRatio: String(aspectValue),
          }}
        >
          {previewClip ? (
            <div
              className="absolute inset-0 flex items-center justify-center"
              style={{
                transform: `translate(${previewClip.transform.x}%, ${previewClip.transform.y}%) scale(${
                  previewClip.transform.scale / 100
                }) rotate(${previewClip.transform.rotation}deg)`,
                opacity: previewClip.transform.opacity / 100,
                filter: `brightness(${previewClip.adjust.brightness}%) contrast(${previewClip.adjust.contrast}%) saturate(${previewClip.adjust.saturation}%)`,
                clipPath: `inset(${previewClip.transform.crop.t}% ${previewClip.transform.crop.r}% ${previewClip.transform.crop.b}% ${previewClip.transform.crop.l}%)`,
              }}
            >
              {videoSource && !mediaError ? (
                <video
                  ref={videoRef}
                  key={`${previewClip.id}:${videoSource}`}
                  src={videoSource}
                  poster={previewAsset?.thumbnailUrl}
                  playsInline
                  preload="auto"
                  onLoadedMetadata={(event) => {
                    event.currentTarget.currentTime = Math.min(expectedMediaTime, event.currentTarget.duration || expectedMediaTime);
                    if (playing && activeVideo) void event.currentTarget.play().catch(() => setPlaying(false));
                  }}
                  onError={() => {
                    setFailedVideoSource(videoSource ?? null);
                    setPlaying(false);
                  }}
                  onEnded={() => {
                    setPlayhead(Math.min(timelineEnd, previewClip.start + previewClip.duration));
                  }}
                  className="h-full w-full object-cover"
                />
              ) : generatedImageSource ? (
                <img
                  src={generatedImageSource}
                  alt={previewClip.name}
                  className="h-full w-full object-cover"
                />
              ) : previewClip.origin === "script_placeholder" ? (
                <div className="flex h-full w-full flex-col items-center justify-center bg-ink px-8 text-center text-white/70">
                  <AlertTriangle className="h-10 w-10 text-amber" />
                  <div className="mt-3 text-sm font-medium text-white">待补素材</div>
                  <div className="mt-1 line-clamp-3 text-xs leading-relaxed text-white/55">
                    {previewClip.name}
                  </div>
                  <div className="mt-2 rounded-full bg-white/10 px-2 py-0.5 text-[10px]">
                    已保留 {previewClip.duration.toFixed(1)} 秒脚本时间
                  </div>
                </div>
              ) : (
                <Thumbnail
                  variant={previewClip.variant}
                  imageUrl={previewAsset?.thumbnailUrl}
                  className="h-full w-full"
                  label
                />
              )}
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-white/40">
              <Film className="h-12 w-12" />
              <p className="mt-2 text-sm">选择片段进行预览</p>
            </div>
          )}
          {previewText && (
            <div className="absolute bottom-4 left-1/2 max-w-[85%] -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-center text-sm text-white">
              {previewText}
            </div>
          )}
          {mediaError && (
            <div className="absolute inset-x-4 top-4 flex items-center justify-between gap-3 rounded-lg bg-red/90 px-3 py-2 text-xs text-white">
              <span>视频加载失败，媒体地址可能已过期</span>
              <button
                type="button"
                onClick={() => {
                  setFailedVideoSource(null);
                  onRetryAssets();
                }}
                className="shrink-0 rounded bg-white/15 px-2 py-1 hover:bg-white/25"
              >
                刷新
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 播放控制 */}
      <div className="flex shrink-0 items-center justify-between bg-ink px-4 py-2.5">
        <div className="font-mono text-sm tabular-nums text-white/90">
          {fmtTimecode(playhead)}{" "}
          <span className="text-white/40">/ {fmtTimecode(playbackEnd)}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              setPlaying(false);
              setPlayhead(firstVideoStart);
            }}
            aria-label="跳到时间线开头"
            className="rounded-md p-1.5 text-white/70 transition hover:bg-white/10 hover:text-white"
          >
            <SkipBack className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              if (playing) {
                setPlaying(false);
                return;
              }
              if (playhead < firstVideoStart || playhead >= playbackEnd) setPlayhead(firstVideoStart);
              setPlaying(true);
            }}
            disabled={!hasPlayableVideo}
            aria-label={playing ? "暂停" : "播放"}
            className="rounded-md bg-white p-2 text-ink transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>
          <button
            onClick={() => {
              setPlaying(false);
              setPlayhead(playbackEnd);
            }}
            aria-label="跳到时间线结尾"
            className="rounded-md p-1.5 text-white/70 transition hover:bg-white/10 hover:text-white"
          >
            <SkipForward className="h-4 w-4" />
          </button>
        </div>
        <div className="w-24" />
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────
   右栏：检查器
   ────────────────────────────────────────────── */

type InspTab = "visual" | "audio" | "subtitle" | "ai";

function InspectorPanel({
  clip,
  updateClip,
  linkedScript,
  snapshotScript,
  onOpenSourceScript,
  onSyncScriptText,
  onApplyScriptShot,
  readOnly,
}: {
  clip: TLClip | null;
  updateClip: (id: string, patch: Partial<TLClip>) => void;
  linkedScript?: DetailedScript;
  snapshotScript?: DetailedScript;
  onOpenSourceScript: () => void;
  onSyncScriptText: (clip: TLClip, unit: ScriptUnit) => void;
  onApplyScriptShot: (clip: TLClip, shot: Shot) => void;
  readOnly: boolean;
}) {
  const [tab, setTab] = useState<InspTab>("visual");

  const linkedSource = (() => {
    if (!clip || !linkedScript) return null;
    for (const unit of linkedScript.units) {
      const shot = unit.shots.find((candidate) =>
        clip.sourceShotId === candidate.id
        || clip.snapshotShotId === candidate.id
        || Boolean(candidate.selectedClipId && clip.sourceClipId === candidate.selectedClipId),
      );
      if (shot) return { unit, shot };
      if (clip.sourceUnitId === unit.id || clip.snapshotUnitId === unit.id) return { unit, shot: null };
    }
    return null;
  })();

  const snapshotSource = (() => {
    if (!linkedSource) return null;
    const unit = findSnapshotUnit(snapshotScript, linkedSource.unit);
    const shot = linkedSource.shot ? findSnapshotShot(unit, linkedSource.shot) : undefined;
    return { unit, shot };
  })();

  const textNeedsSync = Boolean(
    clip
    && linkedSource
    && clip.track === "subtitle"
    && !sameText(clip.text, linkedSource.unit.text),
  );
  const selectedAssetNeedsSync = Boolean(
    clip
    && linkedSource?.shot?.selectedClipId
    && clip.sourceClipId !== linkedSource.shot.selectedClipId,
  );
  const shotMetadataChanged = Boolean(
    linkedSource?.shot
    && snapshotSource?.shot
    && (
      !sameText(linkedSource.shot.description, snapshotSource.shot.description)
      || !sameDuration(linkedSource.shot.duration, snapshotSource.shot.duration)
    ),
  );
  const hasPendingScriptUpdate = textNeedsSync || selectedAssetNeedsSync;
  const relationshipStatus = hasPendingScriptUpdate
    ? "待应用脚本更新"
    : shotMetadataChanged
      ? "脚本变更待检查"
      : clip?.syncStatus === "timeline_changed"
        ? "时间线已独立调整"
        : "已关联当前脚本";
  const relationshipSynced = !hasPendingScriptUpdate
    && !shotMetadataChanged
    && clip?.syncStatus !== "timeline_changed";

  const tabs: { key: InspTab; label: string; Icon: typeof SlidersHorizontal }[] = [
    { key: "visual", label: "画面", Icon: SlidersHorizontal },
    { key: "audio", label: "音频", Icon: Volume2 },
    { key: "subtitle", label: "字幕", Icon: Type },
    { key: "ai", label: "AI", Icon: Sparkles },
  ];

  return (
    <section className="flex w-72 shrink-0 flex-col border-l border-line bg-surface">
      <div className="flex shrink-0 border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            disabled={!clip}
            className={clsx(
              "flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium transition disabled:opacity-40",
              tab === t.key ? "border-b-2 border-blue text-blue" : "text-muted hover:text-text",
            )}
          >
            <t.Icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {!clip ? (
          <EmptyHint icon={SlidersHorizontal} text="选择时间线片段以编辑属性" />
        ) : (
          <div className="space-y-3">
            {linkedSource && (
              <div className="rounded-lg border border-blue/20 bg-blue-soft/30 p-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[10px] font-medium text-blue">来源脚本</div>
                    <div className="mt-1 truncate text-xs font-semibold text-text">
                      第 {linkedSource.unit.index + 1} 句 · {linkedSource.unit.outline || "未命名脚本句"}
                    </div>
                    {linkedSource.shot && (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted">
                        Shot {(linkedSource.shot.index ?? 0) + 1} · {linkedSource.shot.description || "未填写画面描述"}
                      </p>
                    )}
                    <span className={clsx(
                      "mt-2 inline-flex rounded-full px-2 py-0.5 text-[9px] font-medium",
                      relationshipSynced ? "bg-teal/10 text-teal" : "bg-amber/10 text-amber",
                    )}>
                      {relationshipStatus}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={onOpenSourceScript}
                    className="shrink-0 rounded border border-blue/20 bg-surface px-2 py-1 text-[10px] font-medium text-blue hover:bg-blue-soft"
                  >
                    查看
                  </button>
                </div>

                {textNeedsSync && (
                  <div className="mt-2 rounded-md border border-amber/20 bg-surface p-2">
                    <div className="text-[10px] font-medium text-amber">脚本文本已更新</div>
                    <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted">
                      {linkedSource.unit.text || "当前脚本句为空"}
                    </p>
                    <button
                      type="button"
                      onClick={() => onSyncScriptText(clip, linkedSource.unit)}
                      disabled={readOnly}
                      className="mt-2 w-full rounded-md bg-blue px-2 py-1.5 text-[10px] font-medium text-white transition hover:bg-blue/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      更新当前字幕
                    </button>
                  </div>
                )}

                {selectedAssetNeedsSync && linkedSource.shot && (
                  <div className="mt-2 rounded-md border border-amber/20 bg-surface p-2">
                    <div className="text-[10px] font-medium text-amber">脚本当前选中的素材已变化</div>
                    <p className="mt-1 text-[10px] leading-relaxed text-muted">
                      应用后仅替换当前镜头的源素材，并保留时间线位置和已有脚本关联。
                    </p>
                    <button
                      type="button"
                      onClick={() => onApplyScriptShot(clip, linkedSource.shot!)}
                      disabled={readOnly}
                      className="mt-2 w-full rounded-md bg-blue px-2 py-1.5 text-[10px] font-medium text-white transition hover:bg-blue/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      使用脚本当前素材
                    </button>
                  </div>
                )}

                {shotMetadataChanged && (
                  <div className="mt-2 rounded-md border border-line bg-canvas/60 px-2 py-1.5 text-[10px] leading-relaxed text-muted">
                    脚本分镜描述或目标时长已更新，不会自动覆盖当前剪辑，请按实际画面人工调整。
                  </div>
                )}

                {clip.origin === "script_placeholder" && (
                  <div className="mt-2 rounded-md border border-amber/20 bg-amber/10 px-2 py-1.5 text-[10px] leading-relaxed text-amber">
                    这是生成初剪时保留的待补素材位置。请在脚本中为该分镜选择素材，再回到这里应用；占位片段不会被允许直接导出。
                  </div>
                )}
              </div>
            )}

            {tab === "visual" ? (
              <VisualInspector clip={clip} updateClip={updateClip} />
            ) : tab === "audio" ? (
              <AudioInspector clip={clip} updateClip={updateClip} />
            ) : tab === "subtitle" ? (
              <SubtitleInspector clip={clip} updateClip={updateClip} />
            ) : (
              <AIInspector clip={clip} />
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function VisualInspector({
  clip,
  updateClip,
}: {
  clip: TLClip;
  updateClip: (id: string, patch: Partial<TLClip>) => void;
}) {
  const t = clip.transform;
  const a = clip.adjust;
  const setTransform = (patch: Partial<TLClip["transform"]>) =>
    updateClip(clip.id, { transform: { ...t, ...patch } });
  const setAdjust = (patch: Partial<TLClip["adjust"]>) =>
    updateClip(clip.id, { adjust: { ...a, ...patch } });
  const setCrop = (patch: Partial<TLClip["transform"]["crop"]>) =>
    updateClip(clip.id, { transform: { ...t, crop: { ...t.crop, ...patch } } });

  return (
    <div className="space-y-4">
      <SliderRow label="缩放" value={t.scale} min={10} max={300} unit="%" onChange={(v) => setTransform({ scale: v })} />
      <SliderRow label="水平位置" value={t.x} min={-100} max={100} unit="%" onChange={(v) => setTransform({ x: v })} />
      <SliderRow label="垂直位置" value={t.y} min={-100} max={100} unit="%" onChange={(v) => setTransform({ y: v })} />
      <SliderRow label="旋转" value={t.rotation} min={-180} max={180} unit="°" onChange={(v) => setTransform({ rotation: v })} />
      <SliderRow label="不透明度" value={t.opacity} min={0} max={100} unit="%" onChange={(v) => setTransform({ opacity: v })} />

      <div>
        <div className="mb-1.5 text-xs font-medium text-muted">裁剪</div>
        <div className="grid grid-cols-2 gap-2">
          <SliderRow label="左" value={t.crop.l} min={0} max={50} unit="%" onChange={(v) => setCrop({ l: v })} compact />
          <SliderRow label="右" value={t.crop.r} min={0} max={50} unit="%" onChange={(v) => setCrop({ r: v })} compact />
          <SliderRow label="上" value={t.crop.t} min={0} max={50} unit="%" onChange={(v) => setCrop({ t: v })} compact />
          <SliderRow label="下" value={t.crop.b} min={0} max={50} unit="%" onChange={(v) => setCrop({ b: v })} compact />
        </div>
      </div>

      {clip.track === "video" && (
        <div className="space-y-2 border-t border-line pt-3">
          <label className="block text-xs font-medium text-muted">片段转场</label>
          <select
            value={clip.transition.type}
            onChange={(event) =>
              updateClip(clip.id, {
                transition: {
                  ...clip.transition,
                  type: event.target.value as TLClip["transition"]["type"],
                },
              })
            }
            className="w-full rounded-lg border border-line bg-canvas px-2.5 py-2 text-sm text-text"
          >
            <option value="none">无转场</option>
            <option value="fade_black">黑场淡入淡出</option>
            <option value="fade_white">白场淡入淡出</option>
          </select>
          {clip.transition.type !== "none" && (
            <SliderRow
              label="转场时长"
              value={clip.transition.duration}
              min={0.1}
              max={Math.min(3, Math.max(0.1, clip.duration / 2))}
              step={0.1}
              unit="s"
              onChange={(duration) =>
                updateClip(clip.id, { transition: { ...clip.transition, duration } })
              }
            />
          )}
          <p className="text-[11px] leading-relaxed text-muted">转场会真实写入导出视频的片段头尾。</p>
        </div>
      )}

      <div>
        <div className="mb-1.5 text-xs font-medium text-muted">画面调节</div>
        <div className="space-y-2">
          <SliderRow label="亮度" value={a.brightness} min={0} max={200} unit="%" onChange={(v) => setAdjust({ brightness: v })} />
          <SliderRow label="对比度" value={a.contrast} min={0} max={200} unit="%" onChange={(v) => setAdjust({ contrast: v })} />
          <SliderRow label="饱和度" value={a.saturation} min={0} max={200} unit="%" onChange={(v) => setAdjust({ saturation: v })} />
        </div>
      </div>
    </div>
  );
}

function AudioInspector({
  clip,
  updateClip,
}: {
  clip: TLClip;
  updateClip: (id: string, patch: Partial<TLClip>) => void;
}) {
  const fadeMax = Math.min(30, Math.max(0, clip.duration / 2));
  return (
    <div className="space-y-4">
      <SliderRow
        label="音量"
        value={clip.audio.volume}
        min={0}
        max={200}
        unit="%"
        onChange={(v) => updateClip(clip.id, { audio: { ...clip.audio, volume: v } })}
      />
      <label className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
        <span className="flex items-center gap-1.5 text-sm text-text">
          <Volume2 className="h-4 w-4 text-muted" />
          静音
        </span>
        <button
          type="button"
          aria-label="切换静音"
          onClick={() => updateClip(clip.id, { audio: { ...clip.audio, muted: !clip.audio.muted } })}
          className={clsx(
            "relative h-5 w-9 rounded-full transition",
            clip.audio.muted ? "bg-red" : "bg-line",
          )}
        >
          <span
            className={clsx(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all",
              clip.audio.muted ? "left-4.5" : "left-0.5",
            )}
          />
        </button>
      </label>
      <label className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
        <span className="flex items-center gap-1.5 text-sm text-text">
          <Volume2 className="h-4 w-4 text-muted" />
          降噪
        </span>
        <button
          type="button"
          aria-label="切换降噪"
          onClick={() => updateClip(clip.id, { audio: { ...clip.audio, denoise: !clip.audio.denoise } })}
          className={clsx(
            "relative h-5 w-9 rounded-full transition",
            clip.audio.denoise ? "bg-teal" : "bg-line",
          )}
        >
          <span
            className={clsx(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all",
              clip.audio.denoise ? "left-4.5" : "left-0.5",
            )}
          />
        </button>
      </label>
      <SliderRow
        label="淡入"
        value={Math.min(clip.audio.fadeIn, fadeMax)}
        min={0}
        max={fadeMax}
        step={0.1}
        unit="s"
        onChange={(fadeIn) => updateClip(clip.id, { audio: { ...clip.audio, fadeIn } })}
      />
      <SliderRow
        label="淡出"
        value={Math.min(clip.audio.fadeOut, fadeMax)}
        min={0}
        max={fadeMax}
        step={0.1}
        unit="s"
        onChange={(fadeOut) => updateClip(clip.id, { audio: { ...clip.audio, fadeOut } })}
      />
      <p className="rounded-lg bg-canvas px-3 py-2 text-[11px] text-muted">
        音量、静音和淡入淡出会同步用于预览与导出；降噪在导出时由 FFmpeg 应用。
      </p>
    </div>
  );
}

function SubtitleInspector({
  clip,
  updateClip,
}: {
  clip: TLClip;
  updateClip: (id: string, patch: Partial<TLClip>) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted">字幕文本</label>
        <textarea
          value={clip.text ?? ""}
          onChange={(e) => updateClip(clip.id, { text: e.target.value })}
          rows={5}
          placeholder="输入字幕内容…"
          className="w-full resize-none rounded-lg border border-line bg-canvas px-2.5 py-2 text-sm text-text focus:border-blue focus:bg-surface"
        />
      </div>
      <p className="rounded-lg bg-canvas px-3 py-2 text-[11px] text-muted">
        字幕将显示在对应时间段内，可在时间线字幕轨拖动调整位置。
      </p>
    </div>
  );
}

function AIInspector({ clip }: { clip: TLClip }) {
  const [copy, setCopy] = useState(clip.text ?? "");

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-blue-soft bg-blue-soft/40 p-2.5">
        <div className="flex items-center gap-1.5 text-xs font-medium text-blue">
          <Sparkles className="h-3.5 w-3.5" />
          AI 辅助
        </div>
        <p className="mt-1 text-[11px] text-muted">以下生成能力尚未配置，启用前不会产生占位结果或消耗额度</p>
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted">文案润色</label>
        <textarea
          value={copy}
          onChange={(e) => setCopy(e.target.value)}
          rows={3}
          className="w-full resize-none rounded-lg border border-line bg-canvas px-2.5 py-2 text-xs text-text focus:border-blue focus:bg-surface"
        />
        <button
          disabled
          title="文案润色后端尚未接入"
          className="mt-2 flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-1.5 text-xs font-medium text-white opacity-40"
        >
          <Sparkles className="h-3.5 w-3.5" />
          文案润色
        </button>
      </div>

      <button
        disabled
        title="配音生成后端尚未接入"
        className="flex w-full cursor-not-allowed items-center gap-2 rounded-lg border border-line px-3 py-2 text-left text-xs text-text opacity-50"
      >
        <Mic className="h-4 w-4 text-teal" />
        <div className="flex-1">
          <div className="font-medium">配音生成</div>
          <div className="text-[11px] text-muted">将文案转为语音</div>
        </div>
      </button>

      <button
        disabled
        title="背景音乐推荐后端尚未接入"
        className="flex w-full cursor-not-allowed items-center gap-2 rounded-lg border border-line px-3 py-2 text-left text-xs text-text opacity-50"
      >
        <Music className="h-4 w-4 text-amber" />
        <div className="flex-1">
          <div className="font-medium">背景音乐推荐</div>
          <div className="text-[11px] text-muted">智能匹配 BGM</div>
        </div>
      </button>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  unit,
  onChange,
  step = 1,
  compact = false,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (v: number) => void;
  step?: number;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "" : ""}>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-muted">{label}</span>
        <span className="font-mono text-[11px] text-text">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-blue"
      />
    </div>
  );
}

/* ──────────────────────────────────────────────
   底部：多轨时间线
   ────────────────────────────────────────────── */

interface TimelineProps {
  clips: TLClip[];
  assets: Asset[];
  pxPerSec: number;
  timelineEnd: number;
  playhead: number;
  setPlayhead: (v: number) => void;
  selectedId: string | null;
  setSelectedId: (v: string | null) => void;
  setClips: React.Dispatch<React.SetStateAction<TLClip[]>>;
  commitDrag: (snapshot: TLClip[]) => void;
  clipsRef: React.MutableRefObject<TLClip[]>;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onSplit: () => void;
  onDetachAudio: () => void;
  canDetachAudio: boolean;
  onDelete: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
}

type DragMode = "move" | "trimL" | "trimR" | "playhead";
interface DragState {
  mode: DragMode;
  clipId?: string;
  startX: number;
  origStart: number;
  origDuration: number;
  origSourceStart: number;
  snapshot: TLClip[];
  moved: boolean;
}

function Timeline(props: TimelineProps) {
  const {
    clips,
    assets,
    pxPerSec,
    timelineEnd,
    playhead,
    setPlayhead,
    selectedId,
    setSelectedId,
    setClips,
    commitDrag,
    clipsRef,
    onUndo,
    onRedo,
    canUndo,
    canRedo,
    onSplit,
    onDetachAudio,
    canDetachAudio,
    onDelete,
    onZoomIn,
    onZoomOut,
  } = props;

  const dragRef = useRef<DragState | null>(null);
  const rulerRef = useRef<HTMLDivElement>(null);

  const totalWidth = timelineEnd * pxPerSec;

  /* ── 拖拽：移动 / 裁剪 ── */
  const beginClipDrag = (e: React.PointerEvent, clip: TLClip, mode: DragMode) => {
    e.preventDefault();
    e.stopPropagation();
    setSelectedId(clip.id);
    dragRef.current = {
      mode,
      clipId: clip.id,
      startX: e.clientX,
      origStart: clip.start,
      origDuration: clip.duration,
      origSourceStart: clip.sourceStart,
      snapshot: clipsRef.current,
      moved: false,
    };
  };

  /* ── 播放头拖拽 ── */
  const beginPlayheadDrag = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = rulerRef.current!.getBoundingClientRect();
    const sec = (e.clientX - rect.left) / pxPerSec;
    setPlayhead(Math.max(0, Math.min(timelineEnd, sec)));
    dragRef.current = {
      mode: "playhead",
      startX: e.clientX,
      origStart: 0,
      origDuration: 0,
      origSourceStart: 0,
      snapshot: [],
      moved: true,
    };
  };

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const deltaSec = (e.clientX - d.startX) / pxPerSec;
      if (Math.abs(e.clientX - d.startX) > 2) d.moved = true;

      if (d.mode === "playhead") {
        const rect = rulerRef.current!.getBoundingClientRect();
        const sec = (e.clientX - rect.left) / pxPerSec;
        setPlayhead(Math.max(0, Math.min(timelineEnd, sec)));
        return;
      }
      if (!d.clipId) return;
      setClips((prev) =>
        prev.map((c) => {
          if (c.id !== d.clipId) return c;
          if (d.mode === "move") {
            const candidate = Math.max(0, d.origStart + deltaSec);
            const start = c.track === "video"
              ? nearestAvailableVideoStart(candidate, c.duration, c.id, prev)
              : roundTime(candidate);
            return {
              ...c,
              start,
              syncStatus: c.sourceUnitId || c.snapshotUnitId ? "timeline_changed" : c.syncStatus,
            };
          }
          if (d.mode === "trimL") {
            const asset = assets.find((candidate) => candidate.id === c.assetId);
            const sourceClip = asset?.clips.find((candidate) => candidate.id === c.sourceClipId);
            const sourceMin = sourceClip?.startTime ?? 0;
            const previousEnd = c.track === "video"
              ? Math.max(
                  0,
                  ...prev
                    .filter((item) => item.track === "video" && item.id !== c.id && item.start + item.duration <= d.origStart + 0.01)
                    .map((item) => item.start + item.duration),
                )
              : 0;
            const maxShift = d.origDuration - MIN_CLIP_DURATION;
            const minShift = Math.max(
              -d.origStart,
              sourceMin - d.origSourceStart,
              previousEnd - d.origStart,
            );
            const shift = Math.max(minShift, Math.min(maxShift, deltaSec));
            return {
              ...c,
              start: roundTime(d.origStart + shift),
              duration: roundTime(d.origDuration - shift),
              sourceStart: roundTime(d.origSourceStart + shift),
              syncStatus: c.sourceUnitId || c.snapshotUnitId ? "timeline_changed" : c.syncStatus,
            };
          }
          // trimR
          const asset = assets.find((candidate) => candidate.id === c.assetId);
          const sourceClip = asset?.clips.find((candidate) => candidate.id === c.sourceClipId);
          const assetEnd = getAssetDuration(asset) || Number.POSITIVE_INFINITY;
          const sourceEnd = sourceClip?.endTime ?? assetEnd;
          const sourceAvailable = Math.max(MIN_CLIP_DURATION, sourceEnd - c.sourceStart);
          const nextStart = c.track === "video"
            ? Math.min(
                Number.POSITIVE_INFINITY,
                ...prev
                  .filter((item) => item.track === "video" && item.id !== c.id && item.start >= d.origStart + d.origDuration - 0.01)
                  .map((item) => item.start),
              )
            : Number.POSITIVE_INFINITY;
          const timelineAvailable = nextStart - c.start;
          const dur = Math.max(
            MIN_CLIP_DURATION,
            Math.min(sourceAvailable, timelineAvailable, d.origDuration + deltaSec),
          );
          return {
            ...c,
            duration: roundTime(dur),
            syncStatus: c.sourceUnitId || c.snapshotUnitId ? "timeline_changed" : c.syncStatus,
          };
        }),
      );
    };

    const onUp = () => {
      const d = dragRef.current;
      // 拖拽 / 裁剪产生位移时，把拖拽前快照推入历史栈（clips 已被实时修改）
      if (d && d.mode !== "playhead" && d.moved && d.snapshot) {
        commitDrag(d.snapshot);
      }
      dragRef.current = null;
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [assets, commitDrag, pxPerSec, setClips, setPlayhead, timelineEnd]);

  return (
    <section className="flex h-64 shrink-0 flex-col border-t border-line bg-surface">
      {/* 工具栏 */}
      <div className="flex shrink-0 items-center gap-1 border-b border-line px-3 py-1.5">
        <ToolBtn icon={Undo2} title="撤销" onClick={onUndo} disabled={!canUndo} />
        <ToolBtn icon={Redo2} title="重做" onClick={onRedo} disabled={!canRedo} />
        <div className="mx-1 h-5 w-px bg-line" />
        <ToolBtn icon={Scissors} title="分割（在播放头处）" onClick={onSplit} />
        <ToolBtn
          icon={Music}
          title="分离视频音频到独立音频轨"
          onClick={onDetachAudio}
          disabled={!canDetachAudio}
        />
        <ToolBtn icon={Trash2} title="删除选中" onClick={onDelete} danger />
        <div className="mx-1 h-5 w-px bg-line" />
        <ToolBtn icon={ZoomOut} title="缩小" onClick={onZoomOut} />
        <ToolBtn icon={ZoomIn} title="放大" onClick={onZoomIn} />
        <div className="ml-auto flex items-center gap-2 text-[11px] text-muted">
          <span>{pxPerSec}px/s</span>
        </div>
      </div>

      {/* 时间线主体 */}
      <div className="flex min-h-0 flex-1">
        {/* 轨道标签列 */}
        <div className="w-20 shrink-0 border-r border-line bg-canvas/50">
          <div className="h-7 border-b border-line" />
          {TRACK_META.map((m) => (
            <div
              key={m.kind}
              className="flex h-12 items-center gap-1.5 border-b border-line px-2 text-xs font-medium text-muted"
            >
              <span className={clsx("h-2 w-2 rounded-full", m.color)} />
              <m.Icon className="h-3.5 w-3.5" />
              {m.label}
            </div>
          ))}
        </div>

        {/* 轨道滚动区 */}
        <div className="relative min-w-0 flex-1 overflow-x-auto overflow-y-hidden">
          <div style={{ width: totalWidth, minWidth: "100%" }} className="relative">
            {/* 刻度尺 */}
            <div
              ref={rulerRef}
              onPointerDown={beginPlayheadDrag}
              className="relative h-7 cursor-ew-resize select-none border-b border-line bg-canvas/30"
            >
              {Array.from({ length: Math.ceil(timelineEnd) + 1 }).map((_, i) =>
                i % 5 === 0 ? (
                  <div key={i} className="absolute top-0 h-full" style={{ left: i * pxPerSec }}>
                    <div className="absolute top-0 h-3 w-px bg-muted/50" />
                    <span className="absolute top-3 left-1 text-[10px] text-muted">{i}s</span>
                  </div>
                ) : (
                  <div
                    key={i}
                    className="absolute top-0 h-1.5 w-px bg-line"
                    style={{ left: i * pxPerSec }}
                  />
                ),
              )}
            </div>

            {/* 三条轨道 */}
            {TRACK_META.map((m) => (
              <div
                key={m.kind}
                className="relative h-12 border-b border-line bg-[repeating-linear-gradient(90deg,transparent,transparent_39px,rgba(226,231,240,0.5)_39px,rgba(226,231,240,0.5)_40px)]"
              >
                {clips
                  .filter((c) => c.track === m.kind)
                  .map((clip) => (
                    <ClipBlock
                      key={clip.id}
                      clip={clip}
                      thumbnailUrl={assets.find((asset) => asset.id === clip.assetId)?.thumbnailUrl}
                      pxPerSec={pxPerSec}
                      selected={clip.id === selectedId}
                      onPointerDownBody={(e) => beginClipDrag(e, clip, "move")}
                      onPointerDownL={(e) => beginClipDrag(e, clip, "trimL")}
                      onPointerDownR={(e) => beginClipDrag(e, clip, "trimR")}
                      onClick={() => setSelectedId(clip.id)}
                    />
                  ))}
              </div>
            ))}

            {clips.length === 0 && (
              <div className="pointer-events-none absolute left-0 right-0 top-7 flex h-36 items-center justify-center">
                <div className="rounded-xl border border-dashed border-line bg-surface/90 px-5 py-3 text-center shadow-sm">
                  <Film className="mx-auto h-5 w-5 text-muted" />
                  <p className="mt-1 text-xs font-medium text-text">时间线还是空的</p>
                  <p className="mt-0.5 text-[11px] text-muted">从左侧添加已上传的真实视频素材</p>
                </div>
              </div>
            )}

            {/* 播放头 */}
            <div
              className="pointer-events-none absolute top-0 bottom-0 z-20"
              style={{ left: playhead * pxPerSec }}
            >
              <div className="absolute -left-1.5 top-0 h-3 w-3 rounded-b-sm bg-red" />
              <div className="h-full w-px bg-red" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ToolBtn({
  icon: Icon,
  title,
  onClick,
  disabled,
  danger,
}: {
  icon: typeof Undo2;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(
        "rounded-md p-1.5 transition disabled:opacity-30",
        danger ? "text-muted hover:bg-red/10 hover:text-red" : "text-muted hover:bg-canvas hover:text-text",
      )}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

function ClipBlock({
  clip,
  thumbnailUrl,
  pxPerSec,
  selected,
  onPointerDownBody,
  onPointerDownL,
  onPointerDownR,
  onClick,
}: {
  clip: TLClip;
  thumbnailUrl?: string;
  pxPerSec: number;
  selected: boolean;
  onPointerDownBody: (e: React.PointerEvent) => void;
  onPointerDownL: (e: React.PointerEvent) => void;
  onPointerDownR: (e: React.PointerEvent) => void;
  onClick: () => void;
}) {
  const left = clip.start * pxPerSec;
  const width = Math.max(8, clip.duration * pxPerSec);
  const accent =
    clip.track === "video" ? "border-blue" : clip.track === "audio" ? "border-teal" : "border-amber";

  return (
    <div
      onPointerDown={onPointerDownBody}
      onClick={onClick}
      className={clsx(
        "absolute top-1 bottom-1 flex cursor-grab items-center overflow-hidden rounded-md border bg-surface shadow-soft active:cursor-grabbing",
        selected ? clsx(accent, "ring-2 ring-blue/40") : "border-line",
      )}
      style={{ left, width }}
    >
      {/* 入点裁剪手柄 */}
      <div
        onPointerDown={onPointerDownL}
        className="absolute left-0 top-0 z-10 flex h-full w-1.5 cursor-ew-resize items-center justify-center bg-current opacity-0 transition hover:opacity-100"
        style={{ color: clip.track === "video" ? "#2865ed" : clip.track === "audio" ? "#17a890" : "#d98a14" }}
      >
        <GripVertical className="h-3 w-3 text-white" />
      </div>

      {clip.track === "video" ? (
        <div className="flex h-full w-full items-center gap-1 px-1">
          <Thumbnail
            variant={clip.variant}
            imageUrl={thumbnailUrl}
            className="h-7 w-10 shrink-0 rounded-sm"
          />
          <span className="truncate text-[11px] font-medium text-text">{clip.name}</span>
        </div>
      ) : clip.track === "audio" ? (
        <div className="flex h-full w-full items-center gap-1 px-1.5">
          <Music className="h-3 w-3 shrink-0 text-teal" />
          <div className="flex flex-1 items-center gap-px overflow-hidden">
            {Array.from({ length: Math.max(4, Math.floor(width / 4)) }).map((_, i) => (
              <span
                key={i}
                className="w-0.5 shrink-0 rounded-full bg-teal/60"
                style={{ height: `${30 + Math.abs(Math.sin(i * 1.3)) * 60}%` }}
              />
            ))}
          </div>
          <span className="shrink-0 text-[11px] font-medium text-text">{clip.name}</span>
        </div>
      ) : (
        <div className="flex h-full w-full items-center gap-1 px-1.5">
          <Type className="h-3 w-3 shrink-0 text-amber" />
          <span className="truncate text-[11px] text-text">{clip.text || clip.name}</span>
        </div>
      )}

      {/* 出点裁剪手柄 */}
      <div
        onPointerDown={onPointerDownR}
        className="absolute right-0 top-0 z-10 flex h-full w-1.5 cursor-ew-resize items-center justify-center opacity-0 transition hover:opacity-100"
        style={{ color: clip.track === "video" ? "#2865ed" : clip.track === "audio" ? "#17a890" : "#d98a14" }}
      >
        <GripVertical className="h-3 w-3 text-white" />
      </div>
    </div>
  );
}

/* ── 通用空状态提示 ── */

function EmptyHint({ icon: Icon, text }: { icon: typeof Film; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <Icon className="h-8 w-8 text-line" />
      <p className="mt-2 text-xs text-muted">{text}</p>
    </div>
  );
}

function PanelLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-3 py-8 text-center">
      <AlertTriangle className="h-7 w-7 text-red" />
      <p className="mt-2 text-xs font-medium text-text">加载失败</p>
      <p className="mt-1 line-clamp-3 text-[11px] text-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-text transition hover:border-blue hover:text-blue"
      >
        重试
      </button>
    </div>
  );
}

function EmptyState({
  title,
  desc,
  actionLabel,
  onAction,
}: {
  title: string;
  desc: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="flex h-screen flex-col items-center justify-center bg-canvas px-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-soft">
        <AlertTriangle className="h-8 w-8 text-blue" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-text">{title}</h2>
      <p className="mt-1 max-w-sm text-sm text-muted">{desc}</p>
      <button
        onClick={onAction}
        className="mt-4 flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-2"
      >
        <ArrowLeft className="h-4 w-4" />
        {actionLabel}
      </button>
    </div>
  );
}
