// ──────────────────────────────────────────────
// OpenVMA - 脚本分镜编辑器（产品最核心页面）
// 全宽表格：一句脚本共享大纲与台词，每个分镜独立编辑画面与时长
// 按需制作抽屉：素材推荐 / AI分镜 / 图生视频 / 示意特效
// 数据：zustand scriptStore 管理草稿；@tanstack/react-query 调用 API
// 保存：PATCH /api/scripts/:id/units
// ──────────────────────────────────────────────

import type * as React from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useNavigationBlocker, useParams, useSearchParams } from "@/router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  Save,
  Download,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Wand2,
  Plus,
  Trash2,
  Lock,
  Unlock,
  Check,
  Search,
  RefreshCw,
  Image as ImageIcon,
  Video,
  PenTool,
  Clapperboard,
  Cpu,
  Film,
  Camera,
  Layers,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Link2,
  Eraser,
  FileText,
  X,
  Clock3,
} from "lucide-react";

import { useScriptStore } from "@/stores/scriptStore";
import * as scriptApi from "@/api/scripts";
import * as assetApi from "@/api/assets";
import * as projectApi from "@/api/projects";
import * as generateApi from "@/api/generate";
import * as jobApi from "@/api/jobs";
import { DeleteConfirmModal } from "@/components/DeleteConfirmModal";
import type {
  Script,
  ScriptUnit,
  Shot,
  VisualConfig,
  Reference,
  StylePreset,
  AspectRatio,
  Palette,
  CameraRhythm,
  VisualMode,
  Candidate,
  Asset,
  Clip,
} from "@/types/models";
import { Thumbnail } from "@/components/Thumbnail";
import { BackButton } from "@/components/BackButton";
import "@/styles/script-editor.css";

/* ── 工具函数 ── */

const uid = () => Math.random().toString(36).slice(2, 10);

const EMPTY_UNITS: ScriptUnit[] = [];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

const DEFAULT_VISUAL_CONFIG: VisualConfig = {
  stylePreset: "brand-tech",
  aspectRatio: "16:9",
  palette: "冷灰蓝",
  cameraRhythm: "稳定推进",
  consistencyEnabled: true,
  generationPolicy:
    "优先复用统一素材库中的角色与场景，缺失时按整体风格补齐镜头，保持跨分镜光线、色调与构图一致性。",
  references: { characters: [], objects: [], spaces: [] },
};

function newShot(desc = "", duration = 4): Shot {
  return {
    id: uid(),
    description: desc,
    status: "待编辑",
    selectedClipId: null,
    visualMode: null,
    duration,
    notes: "",
    candidates: [],
  };
}

function newUnit(index: number, outline = ""): ScriptUnit {
  return {
    id: uid(),
    index,
    outline,
    text: "",
    intent: "",
    status: "待编辑",
    selectedClipId: null,
    duration: 0,
    notes: "",
    candidates: [],
    shots: [newShot()],
  };
}

/* ── 常量配置 ── */

const STYLE_PRESETS: {
  value: StylePreset;
  label: string;
  tag: string;
  Icon: typeof Cpu;
}[] = [
  { value: "brand-tech", label: "品牌科技", tag: "brand-tech", Icon: Cpu },
  { value: "cinematic", label: "写实电影", tag: "cinematic", Icon: Film },
  { value: "documentary", label: "纪录质感", tag: "documentary", Icon: Camera },
  { value: "illustration", label: "二维插画", tag: "illustration", Icon: PenTool },
];

const ASPECT_RATIOS: AspectRatio[] = ["16:9", "9:16", "1:1", "4:3"];
const PALETTES: Palette[] = ["冷灰蓝", "自然中性", "暖金色", "高饱和撞色"];
const RHYTHMS: CameraRhythm[] = ["稳定推进", "舒缓留白", "快速切换", "手持纪实"];

const SOURCE_OPTIONS: { value: Exclude<VisualMode, null>; label: string }[] = [
  { value: "recommend", label: "素材推荐" },
  { value: "image", label: "AI分镜" },
  { value: "video", label: "图生视频" },
  { value: "sketch", label: "示意特效" },
];

const REF_TABS: { key: keyof VisualConfig["references"]; label: string }[] = [
  { key: "characters", label: "人物" },
  { key: "objects", label: "物品" },
  { key: "spaces", label: "空间" },
];

const GEN_STAGES: Record<"image" | "video" | "effect", string[]> = {
  image: ["排队中", "解析分镜描述", "生成构图", "渲染关键帧", "完成"],
  video: ["排队中", "加载关键帧", "推算运镜轨迹", "合成视频帧", "完成"],
  effect: ["排队中", "解析手绘草图", "生成动效", "渲染特效视频", "完成"],
};

const SKETCH_COLORS = ["#0c1730", "#2865ed", "#17a890", "#d98a14", "#d75151"];

type SaveStatus = "saved" | "unsaved" | "saving" | "error";
type GenKind = "image" | "video" | "effect";
interface GenState {
  status: "idle" | "running" | "done" | "error";
  progress: number;
  kind?: GenKind;
  jobId?: string;
  resultUrl?: string;
  error?: string;
}
type ShotGenStates = Partial<Record<GenKind, GenState>>;

/* ──────────────────────────────────────────────
   主组件
   ────────────────────────────────────────────── */

export default function ScriptDetailView() {
  const navigate = useNavigate();
  const { scriptId: routeScriptId } = useParams<{ scriptId: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const selectedScriptId = useScriptStore((s) => s.currentScriptId);
  const selectScript = useScriptStore((s) => s.setCurrentScriptId);
  const updateCurrentUnits = useScriptStore((s) => s.updateCurrentUnits);
  const setCurrentScript = useScriptStore((s) => s.setCurrentScript);

  const scriptId = routeScriptId ?? searchParams.get("script") ?? selectedScriptId;

  /* ── 拉取脚本详情（react-query）── */
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["script", scriptId],
    queryFn: () => scriptApi.get(scriptId!),
    enabled: !!scriptId,
  });

  /* ── 本地 UI 状态 ── */
  const [scriptMeta, setScriptMeta] = useState<Script | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [visualConfig, setVisualConfig] = useState<VisualConfig>(DEFAULT_VISUAL_CONFIG);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<VisualMode>("recommend");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [productionOpen, setProductionOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(true);
  const [refTab, setRefTab] = useState<keyof VisualConfig["references"]>("characters");
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteScriptOpen, setDeleteScriptOpen] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [lastSavedAt, setLastSavedAt] = useState("刚刚");
  const [activeScriptJob, setActiveScriptJob] = useState<{
    id: string;
    kind: "match" | "complete";
    progress: number;
    stage: string;
  } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [genStates, setGenStates] = useState<Record<string, ShotGenStates>>({});
  const [referencePicker, setReferencePicker] = useState<keyof VisualConfig["references"] | null>(null);
  const initializedScriptId = useRef<string | null>(null);
  const editVersionRef = useRef(0);

  const referenceAssetsQuery = useQuery({
    queryKey: ["reference-assets", data?.projectId],
    queryFn: () => assetApi.list({ projectId: data!.projectId }),
    enabled: Boolean(data?.projectId),
    retry: false,
  });
  const projectAccessQuery = useQuery({
    queryKey: ["project", data?.projectId],
    queryFn: () => projectApi.get(data!.projectId),
    enabled: Boolean(data?.projectId),
  });

  const linkedCutsQuery = useQuery({
    queryKey: ["linked-cuts", scriptId],
    queryFn: () => scriptApi.listLinkedCuts(scriptId!),
    enabled: Boolean(scriptId && !data?.isSnapshot),
  });

  const capabilitiesQuery = useQuery({
    queryKey: ["generation-capabilities"],
    queryFn: generateApi.getCapabilities,
    staleTime: 60_000,
    retry: false,
  });

  /* ── 草稿从 store 读取（store 管理数据）── */
  const draftUnitsRaw = useScriptStore((s) =>
    s.currentScript?.id === scriptId ? s.currentScript?.units : undefined,
  );
  const draftUnits = draftUnitsRaw ?? EMPTY_UNITS;

  /* ── 数据到达后初始化 ── */
  useEffect(() => {
    if (data) {
      setScriptMeta(data);
      selectScript(data.id);
      const current = useScriptStore.getState().currentScript;
      const localUnits = current?.id === data.id ? current.units : undefined;
      if (initializedScriptId.current !== data.id) {
        initializedScriptId.current = data.id;
        setDraftTitle(data.title);
        setVisualConfig(data.visualConfig ?? DEFAULT_VISUAL_CONFIG);
        setSaveStatus("saved");
        setLastSavedAt(data.updatedAt || "刚刚");
      }
      if (!localUnits) {
        setCurrentScript({ ...data, units: data.units ?? [] });
      } else {
        const remoteShots = new Map(
          (data.units ?? []).flatMap((unit) => unit.shots).map((shot) => [shot.id, shot]),
        );
        const mergedUnits = localUnits.map((unit) => ({
          ...unit,
          shots: unit.shots.map((shot) => {
            const remote = remoteShots.get(shot.id);
            return remote
              ? {
                  ...shot,
                  status: remote.status,
                  generatedImagePath: remote.generatedImagePath,
                  generatedVideoPath: remote.generatedVideoPath,
                  generatedEffectVideoPath: remote.generatedEffectVideoPath,
                }
              : shot;
          }),
        }));
        setCurrentScript({ ...data, units: mergedUnits });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  /* ── 派生数据 ── */
  const allShots = useMemo(() => draftUnits.flatMap((u) => u.shots), [draftUnits]);
  const matchedCount = allShots.filter((s) =>
    Boolean(
      s.selectedClipId
      || s.generatedImagePath
      || s.generatedVideoPath
      || s.generatedEffectVideoPath,
    )
  ).length;
  const dialogueChars = draftUnits.reduce((sum, unit) => sum + unit.text.length, 0);
  const descriptionChars = allShots.reduce((sum, shot) => sum + shot.description.length, 0);
  const totalDuration = allShots.reduce((sum, shot) => sum + (Number(shot.duration) || 0), 0);
  const selectedShotIds = useMemo(
    () => draftUnits
      .filter((unit) => checked.has(unit.id))
      .flatMap((unit) => unit.shots.map((shot) => shot.id)),
    [checked, draftUnits],
  );

  const selected = (() => {
    for (const u of draftUnits) {
      for (const s of u.shots) {
        if (s.id === selectedShotId) return { unit: u, shot: s };
      }
    }
    return null;
  })();

  /* ── 自动选中首个分镜 ── */
  useEffect(() => {
    if (!selectedShotId && allShots.length > 0) {
      setSelectedShotId(allShots[0].id);
    }
  }, [allShots, selectedShotId]);

  useEffect(() => {
    const validIds = new Set(draftUnits.map((unit) => unit.id));
    setChecked((previous) => {
      const next = new Set([...previous].filter((id) => validIds.has(id)));
      return next.size === previous.size ? previous : next;
    });
  }, [draftUnits]);

  /* ── 选中分镜切换时同步右侧 tab ── */
  useEffect(() => {
    if (selected) setActiveTab(selected.shot.visualMode ?? "recommend");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShotId]);

  /* ── 从后端任务读取真实生成进度与结果 ── */
  const runningJobKey = useMemo(
    () => Object.entries(genStates)
      .flatMap(([shotId, states]) =>
        (Object.entries(states) as [GenKind, GenState][])
          .filter(([, state]) => state.status === "running" && state.jobId)
          .map(([kind, state]) => `${shotId}:${kind}:${state.jobId}`),
      )
      .sort()
      .join("|"),
    [genStates],
  );
  useEffect(() => {
    if (!runningJobKey) return;
    const jobs = runningJobKey.split("|").map((entry) => {
      const [shotId, kind, jobId] = entry.split(":");
      return { shotId, kind: kind as GenKind, jobId };
    });
    let cancelled = false;
    const poll = async () => {
      const results = await Promise.allSettled(
        jobs.map(async ({ shotId, kind, jobId }) => ({ shotId, kind, job: await jobApi.get(jobId) })),
      );
      if (cancelled) return;
      const completed = results.some(
        (result) => result.status === "fulfilled" && result.value.job.status === "SUCCEEDED",
      );
      setGenStates((previous) => {
        const next = { ...previous };
        for (const result of results) {
          if (result.status !== "fulfilled") continue;
          const { shotId, kind, job } = result.value;
          const current = next[shotId]?.[kind];
          if (!current || current.jobId !== job.id) continue;
          const shotStates = { ...next[shotId] };
          if (job.status === "SUCCEEDED") {
            shotStates[kind] = job.resultUrl
              ? { ...current, status: "done", progress: 100, resultUrl: job.resultUrl }
              : { ...current, status: "error", progress: job.progress, error: "任务完成但未返回媒体地址" };
          } else if (job.status === "FAILED") {
            shotStates[kind] = { ...current, status: "error", progress: job.progress, error: job.resultDetail || job.detail || "生成失败" };
          } else {
            shotStates[kind] = { ...current, progress: job.progress };
          }
          next[shotId] = shotStates;
        }
        return next;
      });
      if (completed) {
        void queryClient.refetchQueries({ queryKey: ["script", scriptId], type: "active" });
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [queryClient, runningJobKey, scriptId]);

  /* ── toast 自动消失 ── */
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  /* ── 草稿编辑方法 ── */
  const markDirty = useCallback(() => {
    editVersionRef.current += 1;
    setSaveStatus("unsaved");
  }, []);

  const commitUnits = useCallback(
    (next: ScriptUnit[]) => {
      if (!scriptId) return;
      updateCurrentUnits(next);
      markDirty();
    },
    [markDirty, scriptId, updateCurrentUnits],
  );

  const updateShot = useCallback(
    (shotId: string, patch: (s: Shot) => Shot) => {
      const next = draftUnits.map((u) => ({
        ...u,
        shots: u.shots.map((s) => (s.id === shotId ? patch(s) : s)),
      }));
      commitUnits(next);
    },
    [draftUnits, commitUnits],
  );

  const updateUnit = useCallback(
    (unitId: string, patch: Partial<ScriptUnit>) => {
      commitUnits(draftUnits.map((unit) => {
        if (unit.id !== unitId) return unit;
        const semanticChanged =
          (patch.outline !== undefined && patch.outline !== unit.outline)
          || (patch.text !== undefined && patch.text !== unit.text)
          || (patch.intent !== undefined && patch.intent !== unit.intent);
        return semanticChanged
          ? {
              ...unit,
              ...patch,
              status: "待编辑",
              selectedClipId: null,
              candidates: [],
              shots: unit.shots.map((shot) => ({
                ...shot,
                status: "待编辑",
                selectedClipId: null,
                candidates: [],
              })),
            }
          : { ...unit, ...patch };
      }));
    },
    [draftUnits, commitUnits],
  );

  const addShotToUnit = useCallback(
    (unitId: string) => {
      commitUnits(
        draftUnits.map((u) =>
          u.id === unitId ? { ...u, shots: [...u.shots, newShot()] } : u,
        ),
      );
    },
    [draftUnits, commitUnits],
  );

  const addScene = useCallback(() => {
    const nextIndex = draftUnits.length ? draftUnits[draftUnits.length - 1].index + 1 : 0;
    const unit = newUnit(nextIndex);
    commitUnits([...draftUnits, unit]);
    setSelectedShotId(unit.shots[0].id);
  }, [draftUnits, commitUnits]);

  const addThreeRows = useCallback(() => {
    const firstIndex = draftUnits.length ? draftUnits[draftUnits.length - 1].index + 1 : 0;
    const additions = [0, 1, 2].map((offset) => newUnit(firstIndex + offset));
    commitUnits([...draftUnits, ...additions]);
    setSelectedShotId(additions[0].shots[0].id);
  }, [draftUnits, commitUnits]);

  const deleteShot = useCallback(
    (shotId: string) => {
      const owner = draftUnits.find((unit) => unit.shots.some((shot) => shot.id === shotId));
      if (!owner || owner.shots.length <= 1) {
        setToast("每句脚本至少保留一个分镜；如需删除，请删除整句脚本");
        return;
      }
      const next = draftUnits.map((unit) =>
        unit.id === owner.id
          ? { ...unit, shots: unit.shots.filter((shot) => shot.id !== shotId) }
          : unit,
      );
      commitUnits(next);
      if (selectedShotId === shotId) {
        setSelectedShotId(next.find((unit) => unit.id === owner.id)?.shots[0]?.id ?? next[0]?.shots[0]?.id ?? null);
      }
    },
    [draftUnits, commitUnits, selectedShotId],
  );

  const deleteScene = useCallback((unitId: string) => {
    const unit = draftUnits.find((item) => item.id === unitId);
    if (!unit) return;
    const confirmed = window.confirm(`确定删除“${unit.outline || `第 ${unit.index + 1} 句脚本`}”及其所有分镜吗？`);
    if (!confirmed) return;
    const next = draftUnits
      .filter((item) => item.id !== unitId)
      .map((item, index) => ({ ...item, index }));
    commitUnits(next);
    setChecked((previous) => {
      const selectedUnits = new Set(previous);
      selectedUnits.delete(unitId);
      return selectedUnits;
    });
    if (unit.shots.some((shot) => shot.id === selectedShotId)) {
      setSelectedShotId(next[0]?.shots[0]?.id ?? null);
      setProductionOpen(false);
    }
  }, [commitUnits, draftUnits, selectedShotId]);

  const deleteSelectedScenes = useCallback(() => {
    if (!checked.size) return;
    const confirmed = window.confirm(`确定删除所选的 ${checked.size} 句脚本及其所有分镜吗？`);
    if (!confirmed) return;
    const next = draftUnits
      .filter((unit) => !checked.has(unit.id))
      .map((unit, index) => ({ ...unit, index }));
    commitUnits(next);
    setChecked(new Set());
    if (!next.some((unit) => unit.shots.some((shot) => shot.id === selectedShotId))) {
      setSelectedShotId(next[0]?.shots[0]?.id ?? null);
      setProductionOpen(false);
    }
  }, [checked, commitUnits, draftUnits, selectedShotId]);

  const toggleCheck = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleCheckAll = () => {
    if (checked.size === draftUnits.length) setChecked(new Set());
    else setChecked(new Set(draftUnits.map((unit) => unit.id)));
  };

  const setTab = (tab: VisualMode) => {
    setActiveTab(tab);
  };

  const openProduction = (shotId: string, mode?: VisualMode) => {
    const shot = allShots.find((item) => item.id === shotId);
    setSelectedShotId(shotId);
    setActiveTab(mode ?? shot?.visualMode ?? "recommend");
    setProductionOpen(true);
  };

  /* ── 视觉配置编辑 ── */
  const patchConfig = (patch: Partial<VisualConfig>) => {
    setVisualConfig((prev) => ({ ...prev, ...patch }));
    markDirty();
  };

  const patchReference = (
    key: keyof VisualConfig["references"],
    refId: string,
    patch: Partial<Reference>,
  ) => {
    setVisualConfig((prev) => ({
      ...prev,
      references: {
        ...prev.references,
        [key]: prev.references[key].map((r) => (r.id === refId ? { ...r, ...patch } : r)),
      },
    }));
    markDirty();
  };

  const addReference = (key: keyof VisualConfig["references"]) => {
    setReferencePicker(key);
  };

  const confirmReferences = (
    key: keyof VisualConfig["references"],
    selectedReferences: Reference[],
  ) => {
    setVisualConfig((prev) => ({
      ...prev,
      references: {
        ...prev.references,
        [key]: [
          ...prev.references[key],
          ...selectedReferences.filter(
            (next) => !prev.references[key].some(
              (existing) => existing.assetId === next.assetId && existing.clipId === next.clipId,
            ),
          ),
        ],
      },
    }));
    markDirty();
    setReferencePicker(null);
  };

  const removeReference = (key: keyof VisualConfig["references"], refId: string) => {
    setVisualConfig((prev) => ({
      ...prev,
      references: {
        ...prev.references,
        [key]: prev.references[key].filter((r) => r.id !== refId),
      },
    }));
    markDirty();
  };

  /* ── Mutations ── */
  const saveMutation = useMutation({
    mutationFn: async (payload: {
      title: string;
      visualConfig: VisualConfig;
      units: ScriptUnit[];
      version: number;
    }) => {
      const [meta, unitResult] = await Promise.all([
        scriptApi.update(scriptId!, {
          title: payload.title,
          visualConfig: payload.visualConfig,
        }),
        scriptApi.batchUpdateUnits(scriptId!, payload.units),
      ]);
      return { meta, units: unitResult.units, version: payload.version };
    },
    onMutate: () => setSaveStatus("saving"),
    onSuccess: (result) => {
      if (result.version !== editVersionRef.current) {
        setSaveStatus("unsaved");
        setToast("已保存上一版，当前还有未保存修改");
        return;
      }
      const savedScript = { ...result.meta, units: result.units };
      setCurrentScript(savedScript);
      setScriptMeta(result.meta);
      setDraftTitle(result.meta.title);
      setVisualConfig(result.meta.visualConfig ?? visualConfig);
      setLastSavedAt("刚刚");
      setSaveStatus("saved");
      queryClient.setQueryData(["script", scriptId], savedScript);
      setToast("脚本、视觉配置和分镜已保存");
    },
    onError: (error) => {
      setSaveStatus("error");
      setToast(`保存失败：${errorMessage(error, "请重试")}`);
    },
  });

  const roughCutMutation = useMutation({
    mutationFn: () => scriptApi.createRoughCut(scriptId!, {
      title: draftTitle.trim(),
      visualConfig,
    }),
    onSuccess: (res) => {
      setToast(`初剪任务已创建（任务 ${res.jobId}）`);
      void queryClient.invalidateQueries({ queryKey: ["linked-cuts", scriptId] });
      navigate(`/workspace/projects/${res.project.id}`);
    },
    onError: (error) => setToast(`初剪生成失败：${errorMessage(error, "请重试")}`),
  });

  const matchMutation = useMutation({
    mutationFn: (options?: { unitId?: string; shotIds?: string[] }) =>
      scriptApi.matchClips(scriptId!, options),
    onSuccess: (result) => {
      setActiveScriptJob({ id: result.jobId, kind: "match", progress: 0, stage: "等待匹配" });
      setToast("镜头匹配任务已创建，完成后会自动刷新候选");
    },
    onError: (error) => setToast(`匹配失败：${errorMessage(error, "请重试")}`),
  });

  const completeMutation = useMutation({
    mutationFn: (shotIds: string[]) => scriptApi.completeShots(scriptId!, shotIds),
    onSuccess: (result) => {
      setActiveScriptJob({ id: result.jobId, kind: "complete", progress: 0, stage: "等待完善" });
      setToast("AI 分镜完善任务已创建，完成后会自动刷新脚本");
    },
    onError: (error) => setToast(`AI 完善失败：${errorMessage(error, "请重试")}`),
  });

  const saveAll = useCallback(() => {
    const title = draftTitle.trim();
    if (!title) {
      setToast("请先填写脚本标题");
      return;
    }
    if (saveMutation.isPending) return;
    saveMutation.mutate({
      title,
      visualConfig,
      units: draftUnits,
      version: editVersionRef.current,
    });
  }, [draftTitle, draftUnits, saveMutation, visualConfig]);

  useEffect(() => {
    const saveWithShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        saveAll();
      }
    };
    window.addEventListener("keydown", saveWithShortcut);
    return () => window.removeEventListener("keydown", saveWithShortcut);
  }, [saveAll]);

  useEffect(() => {
    const warnBeforeLeave = (event: BeforeUnloadEvent) => {
      if (saveStatus === "saved") return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeLeave);
    return () => window.removeEventListener("beforeunload", warnBeforeLeave);
  }, [saveStatus]);

  useNavigationBlocker(
    saveStatus !== "saved",
    "当前有未保存修改，确定离开当前脚本吗？",
  );

  const activeScriptJobId = activeScriptJob?.id;
  useEffect(() => {
    if (!activeScriptJobId || !scriptId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const job = await jobApi.get(activeScriptJobId);
        if (cancelled) return;
        if (job.status === "SUCCEEDED") {
          const refreshed = await scriptApi.get(scriptId);
          if (cancelled) return;
          setCurrentScript({ ...refreshed, units: refreshed.units ?? [] });
          setScriptMeta(refreshed);
          setDraftTitle(refreshed.title);
          setVisualConfig(refreshed.visualConfig ?? DEFAULT_VISUAL_CONFIG);
          setSaveStatus("saved");
          setLastSavedAt("刚刚");
          setChecked(new Set());
          setActiveScriptJob(null);
          queryClient.setQueryData(["script", scriptId], refreshed);
          setToast(job.resultDetail || "任务已完成，脚本内容已刷新");
          return;
        }
        if (job.status === "FAILED" || job.status === "CANCELLED") {
          setActiveScriptJob(null);
          setToast(`任务失败：${job.resultDetail || job.detail || "请重试"}`);
          return;
        }
        setActiveScriptJob((previous) => previous?.id === job.id
          ? { ...previous, progress: job.progress, stage: job.stage }
          : previous);
      } catch (pollError) {
        if (!cancelled) setToast(`任务状态读取失败：${errorMessage(pollError, "请稍后重试")}`);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeScriptJobId, queryClient, scriptId, setCurrentScript]);

  const startMatch = (options?: { unitId?: string; shotIds?: string[] }) => {
    if (saveStatus !== "saved") {
      setToast("请先保存脚本修改，再匹配素材");
      return;
    }
    if (activeScriptJob) {
      setToast("已有脚本任务正在执行，请等待完成");
      return;
    }
    matchMutation.mutate(options);
  };

  const startAiComplete = (shotIds: string[] = selectedShotIds) => {
    if (!shotIds.length) {
      setToast("请先选择要完善的脚本句或分镜");
      return;
    }
    if (saveStatus !== "saved") {
      setToast("请先保存脚本修改，再使用 AI 完善");
      return;
    }
    if (activeScriptJob) {
      setToast("已有脚本任务正在执行，请等待完成");
      return;
    }
    const confirmed = window.confirm(
      `将使用一次线上文本模型调用完善 ${shotIds.length} 个分镜描述，是否继续？`,
    );
    if (confirmed) completeMutation.mutate(shotIds);
  };

  const startBatchMatch = () => {
    const shotIds = selectedShotIds.length ? selectedShotIds : allShots.map((shot) => shot.id);
    if (!shotIds.length) {
      setToast("当前脚本没有可匹配的分镜");
      return;
    }
    startMatch({ shotIds });
  };

  const startRoughCut = () => {
    if (saveStatus !== "saved") {
      setToast("请先保存脚本修改，再创建初剪项目");
      return;
    }
    const confirmed = window.confirm(
      "将基于当前脚本创建一个独立初剪项目。原脚本不会被修改，系统会保存内部任务快照。是否继续？",
    );
    if (confirmed) roughCutMutation.mutate();
  };

  const setShotGenState = (shotId: string, kind: GenKind, state: GenState) => {
    setGenStates((previous) => ({
      ...previous,
      [shotId]: { ...previous[shotId], [kind]: state },
    }));
  };

  const imgGen = useMutation({
    mutationFn: (v: { shotId: string; unitId: string; description: string }) =>
      generateApi.generateImage({
        projectId: scriptMeta!.projectId,
        shotId: v.shotId,
        description: v.description,
      }),
    onMutate: (v) =>
      setShotGenState(v.shotId, "image", { status: "running", progress: 5, kind: "image" }),
    onSuccess: (data, v) => {
      setShotGenState(v.shotId, "image", {
        status: "running",
        progress: 0,
        kind: "image",
        jobId: data.jobId,
      });
      setToast(data.message);
    },
    onError: (error, v) =>
      setShotGenState(v.shotId, "image", {
        status: "error",
        progress: 0,
        kind: "image",
        error: errorMessage(error, "关键帧生成失败，请重试"),
      }),
  });

  const videoGen = useMutation({
    mutationFn: (v: { shotId: string; unitId: string; motion?: string; duration?: number }) =>
      generateApi.generateVideo({
        projectId: scriptMeta!.projectId,
        shotId: v.shotId,
        motionPrompt: v.motion,
      }),
    onMutate: (v) =>
      setShotGenState(v.shotId, "video", { status: "running", progress: 5, kind: "video" }),
    onSuccess: (data, v) => {
      setShotGenState(v.shotId, "video", {
        status: "running",
        progress: 0,
        kind: "video",
        jobId: data.jobId,
      });
      setToast(data.message);
    },
    onError: (error, v) =>
      setShotGenState(v.shotId, "video", {
        status: "error",
        progress: 0,
        kind: "video",
        error: errorMessage(error, "视频生成失败，请重试"),
      }),
  });

  const effectGen = useMutation({
    mutationFn: (v: { shotId: string; unitId: string; sketchData: string; motion?: string }) =>
      generateApi.generateEffect({
        projectId: scriptMeta!.projectId,
        shotId: v.shotId,
        sketchData: v.sketchData,
        motionDescription: v.motion,
      }),
    onMutate: (v) =>
      setShotGenState(v.shotId, "effect", { status: "running", progress: 5, kind: "effect" }),
    onSuccess: (data, v) => {
      setShotGenState(v.shotId, "effect", {
        status: "running",
        progress: 0,
        kind: "effect",
        jobId: data.jobId,
      });
      setToast(data.message);
    },
    onError: (error, v) =>
      setShotGenState(v.shotId, "effect", {
        status: "error",
        progress: 0,
        kind: "effect",
        error: errorMessage(error, "特效生成失败，请重试"),
      }),
  });

  const handleExport = async (format: "pdf" | "xlsx" | "json" | "csv") => {
    setExportOpen(false);
    if (!scriptId) {
      setToast("未选择可导出的脚本");
      return;
    }
    try {
      await scriptApi.exportFile(scriptId, format);
      setToast("脚本文件已从真实数据生成并开始下载");
    } catch (exportError) {
      setToast(errorMessage(exportError, "脚本导出失败"));
    }
  };

  /* ── 加载 / 空状态 ── */
  if (!scriptId) {
    return (
      <EmptyState
        title="未选择脚本"
        desc="请从脚本中心选择一个脚本进入分镜编辑器。"
        actionLabel="前往脚本中心"
        onAction={() => navigate("/workspace/scripts")}
      />
    );
  }
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <Loader2 className="h-8 w-8 animate-spin text-blue" />
      </div>
    );
  }
  if (isError) {
    return (
      <EmptyState
        title="加载失败"
        desc={error instanceof Error ? error.message : "无法加载脚本详情"}
        actionLabel="前往脚本中心"
        onAction={() => navigate("/workspace/scripts")}
      />
    );
  }

  const saveLabel =
    saveStatus === "saving"
      ? "保存中…"
      : saveStatus === "saved"
        ? "已保存"
        : saveStatus === "error"
          ? "保存失败"
          : "未保存";

  /* ──────────────────────────────────────────────
     渲染
     ────────────────────────────────────────────── */
  return (
    <div className="script-editor-v2 flex h-screen flex-col bg-[#f4f4f5]">
      <header className="script-editor-header grid h-[68px] shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[#dedee2] bg-white px-5">
        <BackButton fallback="/workspace/scripts" fallbackLabel="脚本中心" />
        <div className="min-w-0 text-center">
          <h1 className="max-w-[520px] truncate text-[17px] font-semibold text-[#27272b]">
            {draftTitle || "未命名脚本"}
          </h1>
          <p className="mt-1 text-[11px] text-[#8a8a90]">
            表格式分镜脚本 · {saveStatus === "saved" ? `已保存 ${lastSavedAt}` : saveLabel}
          </p>
        </div>
        <div className="flex items-center justify-end gap-2">
          {projectAccessQuery.data?.currentUserRole !== "viewer" && !data?.isSnapshot && (
            <button
              type="button"
              onClick={() => setDeleteScriptOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-red/30 bg-white px-3 py-2 text-sm font-medium text-red transition hover:bg-red/10"
            >
              <Trash2 className="h-4 w-4" />删除脚本
            </button>
          )}
          <div className="relative">
            <button
              onClick={() => setExportOpen((value) => !value)}
              className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-sm font-medium text-text transition hover:bg-canvas"
            >
              <Download className="h-4 w-4" />
              导出
              <ChevronDown className={clsx("h-3.5 w-3.5 transition", exportOpen && "rotate-180")} />
            </button>
            {exportOpen && (
              <>
                <button className="fixed inset-0 z-10 cursor-default" onClick={() => setExportOpen(false)} aria-label="关闭导出菜单" />
                <div className="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-soft">
                  {[
                    { label: "导出分镜表 PDF", format: "pdf" as const },
                    { label: "导出 Excel", format: "xlsx" as const },
                    { label: "导出 CSV", format: "csv" as const },
                    { label: "导出 JSON", format: "json" as const },
                  ].map((item) => (
                    <button
                      key={item.label}
                      onClick={() => void handleExport(item.format)}
                      className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm text-text transition hover:bg-canvas"
                    >
                      <FileText className="h-4 w-4 text-muted" />
                      {item.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          {saveStatus === "saved" ? (
            <span className="flex min-w-[92px] items-center justify-center gap-2 rounded-xl bg-teal/10 px-3 py-2 text-xs font-medium text-teal">
              <Check className="h-4 w-4" />
              <span><strong className="block">已保存</strong><small className="block font-normal">{lastSavedAt}</small></span>
            </span>
          ) : (
            <button
              onClick={saveAll}
              disabled={saveStatus === "saving" || saveMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-sm font-medium text-white transition hover:bg-black disabled:opacity-55"
            >
              {saveStatus === "saving" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {saveStatus === "saving" ? "保存中…" : "保存更改"}
            </button>
          )}
        </div>
      </header>

      <main
        className="script-editor-main flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 pb-3 pt-4"
        data-scroll-restoration="script-editor-main"
      >
        <section className="flex shrink-0 items-end justify-between gap-6">
          <label className="block min-w-0 flex-1">
            <span className="mb-1 block text-[11px] font-medium text-[#8a8a90]">脚本标题</span>
            <input
              value={draftTitle}
              onChange={(event) => {
                setDraftTitle(event.target.value);
                markDirty();
              }}
              placeholder="请输入脚本标题"
              className="w-full max-w-[720px] border-b border-transparent bg-transparent pb-1 text-[28px] font-bold tracking-[-0.035em] text-[#202024] transition placeholder:text-[#c4c5c8] focus:border-[#b9b9be]"
            />
          </label>
          <div className="pb-1 text-right">
            <strong className="block text-sm font-semibold text-[#56565b]">
              {draftUnits.length} 句脚本 · {allShots.length} 个分镜 · 预计 {totalDuration} 秒
            </strong>
            <span className="mt-1 block text-xs text-[#929297]">{matchedCount} / {allShots.length} 个分镜已有画面</span>
          </div>
        </section>

        <section className="flex min-h-[58px] shrink-0 items-center justify-between gap-4 rounded-xl border border-[#dedee2] bg-white px-3 py-2 shadow-[0_5px_18px_rgba(20,20,24,.025)]">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#edf2fb] text-[#4a659c]">
              <Sparkles className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <strong className="block truncate text-sm text-[#343439]">批量完善脚本与分镜</strong>
              <small className="mt-0.5 block truncate text-xs text-[#85858a]">
                {checked.size ? `当前作用于已选择的 ${checked.size} 句脚本` : "选择脚本句后可批量完善；素材匹配默认处理全部分镜"}
              </small>
            </div>
          </div>
          {activeScriptJob ? (
            <div className="w-[300px] max-w-[36vw]">
              <div className="flex items-center justify-between text-xs text-blue">
                <span className="flex min-w-0 items-center gap-1 truncate"><Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />{activeScriptJob.stage}</span>
                <span>{activeScriptJob.progress}%</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-blue-soft">
                <div className="h-full rounded-full bg-blue transition-all" style={{ width: `${activeScriptJob.progress}%` }} />
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => startAiComplete()}
                disabled={!selectedShotIds.length || completeMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-medium text-text transition hover:border-blue hover:text-blue disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Wand2 className="h-4 w-4" />AI 完善分镜
              </button>
              <button
                onClick={startBatchMatch}
                disabled={!allShots.length || matchMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg border border-blue px-3 py-2 text-xs font-medium text-blue transition hover:bg-blue-soft disabled:opacity-40"
              >
                <Search className="h-4 w-4" />自动匹配素材
              </button>
            </div>
          )}
        </section>

        <VisualConfigCard
          open={configOpen}
          onToggle={() => setConfigOpen((value) => !value)}
          config={visualConfig}
          patchConfig={patchConfig}
          refTab={refTab}
          setRefTab={setRefTab}
          patchReference={patchReference}
          addReference={addReference}
          removeReference={removeReference}
          referenceAssets={referenceAssetsQuery.data?.items ?? []}
          onRoughCut={startRoughCut}
          roughCutLoading={roughCutMutation.isPending}
          linkedCuts={linkedCutsQuery.data ?? []}
          linkedCutsLoading={linkedCutsQuery.isLoading}
          linkedCutsError={linkedCutsQuery.error}
          onRetryLinkedCuts={() => void linkedCutsQuery.refetch()}
          onOpenCut={(projectId) => navigate(`/workspace/projects/${projectId}/editor`)}
          shotCount={allShots.length}
          matchedShotCount={matchedCount}
        />

        <section className="grid min-h-[42px] shrink-0 grid-cols-[auto_1fr_auto] items-center gap-4 rounded-lg border border-[#e0e0e3] bg-white px-3">
          <div className="flex items-center gap-2 text-xs text-[#646469]">
            <input
              type="checkbox"
              checked={draftUnits.length > 0 && checked.size === draftUnits.length}
              onChange={toggleCheckAll}
              aria-label="选择全部脚本句"
              className="h-4 w-4 accent-blue"
            />
            <span>已选择 <strong>{checked.size}</strong> 句脚本</span>
          </div>
          <p className="truncate text-center text-xs text-[#8a8a90]">台词作为父级只保留一份；每句脚本可添加多个拥有独立画面、时长和备注的分镜。</p>
          <button
            onClick={deleteSelectedScenes}
            disabled={!checked.size}
            className="flex items-center gap-1 text-xs text-[#985d5d] disabled:opacity-35"
          >
            <Trash2 className="h-3.5 w-3.5" />删除所选
          </button>
        </section>

        <section className="storyboard-table-shell min-h-[260px] shrink-0 overflow-x-auto rounded-xl border border-[#dcdce0] bg-white shadow-[0_8px_28px_rgba(20,20,24,.035)]" aria-label="分镜脚本编辑表">
          <div className="storyboard-table-grid sticky top-0 z-10 border-b border-[#dedee2] bg-[#f7f7f8] text-xs font-semibold text-[#66666c]">
            <div className="storyboard-header-cell text-center">序号</div>
            <div className="storyboard-header-cell">大纲 / 画面意图</div>
            <div className="storyboard-header-cell">分镜描述（可多条）</div>
            <div className="storyboard-header-cell">画面结果</div>
            <div className="storyboard-header-cell">台词文案（共享）</div>
            <div className="storyboard-header-cell">备注 / 时长</div>
          </div>
          {draftUnits.length ? draftUnits.map((unit) => (
            <StoryboardSceneRow
              key={unit.id}
              unit={unit}
              selected={checked.has(unit.id)}
              activeShotId={selectedShotId}
              onToggleSelected={() => toggleCheck(unit.id)}
              onUpdateUnit={(patch) => updateUnit(unit.id, patch)}
              onUpdateShot={(shotId, patch) => updateShot(shotId, (current) =>
                patch.description !== undefined && patch.description !== current.description
                  ? { ...current, ...patch, status: "待编辑", selectedClipId: null, candidates: [] }
                  : { ...current, ...patch }
              )}
              onAddShot={() => addShotToUnit(unit.id)}
              onDeleteShot={deleteShot}
              onDeleteScene={() => deleteScene(unit.id)}
              onOpenProduction={openProduction}
              onAiComplete={(shotId) => startAiComplete([shotId])}
              aiLoading={completeMutation.isPending || activeScriptJob?.kind === "complete"}
            />
          )) : (
            <div className="flex min-h-[240px] flex-col items-center justify-center text-center">
              <Layers className="h-10 w-10 text-line" />
              <p className="mt-2 text-sm text-muted">暂无脚本句，点击下方添加场景开始</p>
            </div>
          )}
        </section>

        <footer className="flex shrink-0 items-center justify-center gap-2 pb-0.5">
          <button onClick={addScene} className="flex min-h-9 items-center gap-1.5 rounded-lg bg-[#171717] px-4 text-xs font-medium text-white">
            <Plus className="h-4 w-4" />添加场景
          </button>
          <button onClick={addThreeRows} className="min-h-9 rounded-lg border border-[#d8d8dc] bg-white px-4 text-xs font-medium text-[#515156]">
            一次添加 3 行
          </button>
          <span className="ml-2 text-[11px] text-[#929297]">
            台词 {dialogueChars} 字 · 分镜描述 {descriptionChars} 字 · {saveStatus === "saved" ? `已保存 ${lastSavedAt}` : saveLabel} · 支持 ⌘/Ctrl + S
          </span>
        </footer>
      </main>

      {productionOpen && selected && (
        <div className="fixed inset-0 z-40">
          <button className="absolute inset-0 cursor-default bg-black/20" onClick={() => setProductionOpen(false)} aria-label="关闭画面制作台" />
          <aside className="storyboard-production-drawer absolute bottom-0 right-0 top-0 flex w-[min(460px,calc(100vw-24px))] flex-col border-l border-[#dadade] bg-white shadow-[-24px_0_60px_rgba(0,0,0,.14)]">
            <button
              onClick={() => setProductionOpen(false)}
              className="absolute right-3 top-3 z-10 grid h-8 w-8 place-items-center rounded-lg bg-canvas text-muted hover:text-text"
              aria-label="关闭画面制作台"
            >
              <X className="h-4 w-4" />
            </button>
            <ProductionPanel
              selected={selected}
              activeTab={activeTab}
              setTab={setTab}
              genStates={genStates[selected.shot.id]}
              capabilities={capabilitiesQuery.data}
              visualConfig={visualConfig}
              onMatch={() => startMatch({ shotIds: [selected.shot.id] })}
              matchLoading={matchMutation.isPending || activeScriptJob?.kind === "match"}
              onGenerateImage={(description) => {
                if (saveStatus !== "saved") {
                  setToast("请先保存脚本修改，再生成关键帧");
                  return;
                }
                imgGen.mutate({ shotId: selected.shot.id, unitId: selected.unit.id, description });
              }}
              onGenerateVideo={(motion) => {
                if (saveStatus !== "saved") {
                  setToast("请先保存脚本修改，再生成视频");
                  return;
                }
                videoGen.mutate({ shotId: selected.shot.id, unitId: selected.unit.id, motion, duration: selected.shot.duration });
              }}
              onGenerateEffect={(sketchData, motion) => {
                if (saveStatus !== "saved") {
                  setToast("请先保存脚本修改，再生成示意特效");
                  return;
                }
                effectGen.mutate({ shotId: selected.shot.id, unitId: selected.unit.id, sketchData, motion });
              }}
              onRelate={(candidateId) => updateShot(selected.shot.id, (shot) => ({
                ...shot,
                selectedClipId: candidateId,
                visualMode: "recommend",
                status: "已选择",
              }))}
              imgLoading={imgGen.isPending}
              videoLoading={videoGen.isPending}
              effectLoading={effectGen.isPending}
              onRefreshMedia={() => void queryClient.refetchQueries({ queryKey: ["script", scriptId], type: "active" })}
            />
          </aside>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-ink px-4 py-2 text-sm text-white shadow-soft">
          {toast}
        </div>
      )}
      {referencePicker && scriptMeta?.projectId && (
        <ReferencePickerModal
          category={referencePicker}
          assets={referenceAssetsQuery.data?.items ?? []}
          loading={referenceAssetsQuery.isLoading}
          error={referenceAssetsQuery.error}
          onRetry={() => void referenceAssetsQuery.refetch()}
          onClose={() => setReferencePicker(null)}
          onConfirm={(references) => confirmReferences(referencePicker, references)}
        />
      )}
      {scriptId && (
        <DeleteConfirmModal
          open={deleteScriptOpen}
          entityLabel="脚本"
          loadImpact={() => scriptApi.getDeleteImpact(scriptId)}
          onDelete={() => scriptApi.remove(scriptId)}
          onClose={() => setDeleteScriptOpen(false)}
          onDeleted={() => {
            selectScript(null);
            setCurrentScript(null);
            void queryClient.invalidateQueries({ queryKey: ["scripts"] });
            void queryClient.invalidateQueries({ queryKey: ["projects"] });
            navigate("/workspace/scripts", { replace: true });
          }}
        />
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────
   子组件：视觉一致性配置卡
   ────────────────────────────────────────────── */

interface VisualConfigCardProps {
  open: boolean;
  onToggle: () => void;
  config: VisualConfig;
  patchConfig: (patch: Partial<VisualConfig>) => void;
  refTab: keyof VisualConfig["references"];
  setRefTab: (k: keyof VisualConfig["references"]) => void;
  patchReference: (
    key: keyof VisualConfig["references"],
    refId: string,
    patch: Partial<Reference>,
  ) => void;
  addReference: (key: keyof VisualConfig["references"]) => void;
  removeReference: (key: keyof VisualConfig["references"], refId: string) => void;
  referenceAssets: Asset[];
  onRoughCut: () => void;
  roughCutLoading: boolean;
  linkedCuts: scriptApi.LinkedCut[];
  linkedCutsLoading: boolean;
  linkedCutsError: Error | null;
  onRetryLinkedCuts: () => void;
  onOpenCut: (projectId: string) => void;
  shotCount: number;
  matchedShotCount: number;
}

function VisualConfigCard(props: VisualConfigCardProps) {
  const {
    open,
    onToggle,
    config,
    patchConfig,
    refTab,
    setRefTab,
    patchReference,
    addReference,
    removeReference,
    referenceAssets,
    onRoughCut,
    roughCutLoading,
    linkedCuts,
    linkedCutsLoading,
    linkedCutsError,
    onRetryLinkedCuts,
    onOpenCut,
    shotCount,
    matchedShotCount,
  } = props;
  const refs = config.references[refTab];

  return (
    <div className="shrink-0 overflow-hidden rounded-xl border border-[#dedee2] bg-white shadow-[0_8px_24px_rgba(20,20,24,.025)]">
      <header className="flex min-h-[58px] items-center justify-between gap-4 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-blue-soft text-blue">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <strong className="block truncate text-sm text-[#343439]">整体分镜风格与统一素材</strong>
            <p className="mt-0.5 truncate text-xs text-[#85858a]">统一人物、物品和空间设定，让素材匹配与 AI 生成画面保持连续。</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={clsx(
            "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium",
            config.consistencyEnabled ? "bg-teal/10 text-teal" : "bg-canvas text-muted",
          )}>
            {config.consistencyEnabled ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
            {config.consistencyEnabled ? "跨分镜一致性已启用" : "跨分镜一致性已关闭"}
          </span>
          <button onClick={onToggle} className="flex items-center gap-1 rounded-lg border border-line px-3 py-2 text-xs text-muted hover:bg-canvas">
            {open ? "收起配置" : "展开配置"}
            {open ? <ChevronDown className="h-3.5 w-3.5 rotate-180" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
          {linkedCuts[0] && (
            <button
              type="button"
              onClick={() => onOpenCut(linkedCuts[0].projectId)}
              className="flex items-center gap-1.5 rounded-lg border border-blue/30 bg-blue-soft px-3 py-2 text-xs font-medium text-blue hover:bg-blue-soft/70"
            >
              <Film className="h-3.5 w-3.5" />
              继续剪辑
            </button>
          )}
          <button
            onClick={onRoughCut}
            disabled={roughCutLoading}
            className="flex items-center gap-1.5 rounded-lg bg-[#171717] px-3.5 py-2 text-xs font-medium text-white disabled:opacity-55"
          >
            {roughCutLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />}
            {linkedCuts.length ? "新建剪辑版本" : "创建初剪项目"}
          </button>
        </div>
      </header>

      {(linkedCutsLoading || linkedCutsError || linkedCuts.length > 0) && (
        <div className="border-t border-[#e6e6e9] bg-[#fafbfc] px-3 py-2">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <span className="text-[11px] font-medium text-[#646469]">关联剪辑版本</span>
            <span className="text-[10px] text-muted">由当前脚本创建</span>
          </div>
          {linkedCutsLoading ? (
            <div className="flex items-center gap-1.5 py-1 text-[11px] text-muted">
              <Loader2 className="h-3 w-3 animate-spin" />正在读取剪辑版本…
            </div>
          ) : linkedCutsError ? (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-red/20 bg-red/5 px-2.5 py-2 text-[11px] text-red-600">
              <span className="min-w-0 truncate">剪辑版本读取失败：{errorMessage(linkedCutsError, "请重试")}</span>
              <button type="button" onClick={onRetryLinkedCuts} className="shrink-0 rounded border border-red/20 px-2 py-1 hover:bg-red/10">
                重试
              </button>
            </div>
          ) : (
            <div className="flex gap-2 overflow-x-auto pb-0.5">
              {linkedCuts.map((cut, index) => (
                <button
                  key={cut.projectId}
                  type="button"
                  onClick={() => onOpenCut(cut.projectId)}
                  className="flex min-w-[210px] items-center gap-2 rounded-lg border border-line bg-white px-2.5 py-2 text-left hover:border-blue/30 hover:bg-blue-soft/20"
                >
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-blue-soft text-blue">
                    <Clapperboard className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <strong className="block truncate text-[11px] text-text">
                      {cut.name || `剪辑版本 ${index + 1}`}
                    </strong>
                    <small className="mt-0.5 block truncate text-[10px] text-muted">
                      {cut.aspectRatio || "16:9"} · {cut.status} · {cut.updatedAt}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {open && (
        <div className="grid gap-3 border-t border-[#e6e6e9] bg-[#fbfbfc] p-3 xl:grid-cols-[minmax(0,1.05fr)_minmax(420px,.95fr)]">
          <section className="min-w-0 rounded-xl border border-[#e3e3e7] bg-white p-3">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div><strong className="block text-xs text-[#45454a]">整体分镜风格</strong><p className="mt-0.5 text-[11px] text-muted">应用到所有分镜匹配、AI 生图和图生视频任务。</p></div>
              <span className="rounded-full bg-blue-soft px-2.5 py-1 text-[11px] font-medium text-blue">{matchedShotCount}/{shotCount} 个分镜已有画面</span>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {STYLE_PRESETS.map((p) => {
                const active = config.stylePreset === p.value;
                return (
                  <button
                    key={p.value}
                    onClick={() => patchConfig({ stylePreset: p.value })}
                    className={clsx(
                      "relative flex min-h-[66px] flex-col items-start justify-center gap-1 rounded-lg border px-3 py-2 text-left text-xs transition",
                      active
                        ? "border-blue bg-blue-soft text-blue"
                        : "border-line text-muted hover:border-blue/40 hover:text-text",
                    )}
                  >
                    {active && <Check className="absolute right-2 top-2 h-3.5 w-3.5" />}
                    <span className="font-medium">{p.label}</span>
                    <span className="text-[10px] opacity-70">{p.tag}</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2">
              <CompactSelect label="默认画幅" value={config.aspectRatio} options={ASPECT_RATIOS} onChange={(value) => patchConfig({ aspectRatio: value as AspectRatio })} />
              <CompactSelect label="色彩基调" value={config.palette} options={PALETTES} onChange={(value) => patchConfig({ palette: value as Palette })} />
              <CompactSelect label="镜头节奏" value={config.cameraRhythm} options={RHYTHMS} onChange={(value) => patchConfig({ cameraRhythm: value as CameraRhythm })} />
              <button
                onClick={() => patchConfig({ consistencyEnabled: !config.consistencyEnabled })}
                className={clsx(
                  "flex min-h-[58px] items-center justify-between rounded-lg border px-3 text-left text-xs font-medium transition",
                  config.consistencyEnabled
                    ? "border-teal bg-teal/10 text-teal"
                    : "border-line text-muted",
                )}
              >
                <span><strong className="block">跨分镜一致性</strong><small className="mt-0.5 block font-normal">{config.consistencyEnabled ? "生成时引用统一特征" : "允许分镜自由变化"}</small></span>
                <span
                  className={clsx(
                    "relative h-4 w-7 rounded-full transition",
                    config.consistencyEnabled ? "bg-teal" : "bg-line",
                  )}
                >
                  <span
                    className={clsx(
                      "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all",
                      config.consistencyEnabled ? "left-3.5" : "left-0.5",
                    )}
                  />
                </span>
              </button>
            </div>
            <label className="mt-3 flex items-center gap-2 rounded-lg bg-blue-soft/60 px-3 py-2">
              <Sparkles className="h-4 w-4 shrink-0 text-blue" />
              <span className="shrink-0 text-[11px] font-medium text-blue">镜头补齐策略</span>
              <input value={config.generationPolicy} onChange={(event) => patchConfig({ generationPolicy: event.target.value })} className="min-w-0 flex-1 bg-transparent text-xs text-[#5f6c85]" />
              <em className="rounded-full bg-white px-2 py-0.5 text-[10px] not-italic text-blue">自动</em>
            </label>
          </section>

          <section className="min-w-0 rounded-xl border border-[#e3e3e7] bg-white p-3">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div><strong className="block text-xs text-[#45454a]">统一素材库</strong><p className="mt-0.5 text-[11px] text-muted">锁定角色、关键物品和场景空间，供所有分镜共同引用。</p></div>
              <button
                onClick={() => addReference(refTab)}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-text hover:border-blue hover:text-blue"
              >
                <Plus className="h-3 w-3" />
                添加{REF_TABS.find((tab) => tab.key === refTab)?.label}
              </button>
            </div>
            <div className="mb-2 flex w-fit gap-1 rounded-lg bg-canvas p-1">
              {REF_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setRefTab(t.key)}
                  className={clsx(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition",
                    refTab === t.key ? "bg-surface text-blue shadow-soft" : "text-muted hover:text-text",
                  )}
                >
                  {t.label}<span className="ml-1 rounded-full bg-canvas px-1.5 py-0.5 text-[10px]">{config.references[t.key].length}</span>
                </button>
              ))}
            </div>
            <div className="max-h-[116px] space-y-2 overflow-y-auto pr-1">
              {refs.length === 0 ? (
                <button onClick={() => addReference(refTab)} className="flex min-h-[78px] w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-line text-xs text-muted hover:border-blue hover:text-blue">
                  <Plus className="h-4 w-4" />
                  暂无{REF_TABS.find((t) => t.key === refTab)?.label}引用
                </button>
              ) : (
                refs.map((r) => {
                  const referencedAsset = referenceAssets.find((asset) => asset.id === r.assetId);
                  const referencedClip = referencedAsset?.clips.find((clip) => clip.id === r.clipId);
                  return (
                  <div
                    key={r.id}
                    className="flex items-center gap-2 rounded-lg border border-line p-2"
                  >
                    <Thumbnail
                      variant={r.variant}
                      imageUrl={referencedClip?.thumbnailUrl ?? referencedAsset?.thumbnailUrl}
                      className="h-12 w-16 shrink-0 rounded-md"
                    />
                    <div className="min-w-0 flex-1">
                      <input
                        value={r.name}
                        onChange={(e) => patchReference(refTab, r.id, { name: e.target.value })}
                        className="w-full bg-transparent text-xs font-medium text-text"
                      />
                      <input
                        value={r.detail}
                        onChange={(e) => patchReference(refTab, r.id, { detail: e.target.value })}
                        className="mt-0.5 w-full bg-transparent text-[11px] text-muted"
                      />
                    </div>
                    <button
                      onClick={() => patchReference(refTab, r.id, { locked: !r.locked })}
                      className={clsx(
                        "rounded-md p-1.5 transition",
                        r.locked ? "text-amber" : "text-muted hover:bg-canvas",
                      )}
                      title={r.locked ? "已锁定" : "未锁定"}
                    >
                      {r.locked ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      onClick={() => removeReference(refTab, r.id)}
                      className="rounded-md p-1.5 text-muted transition hover:bg-red/10 hover:text-red"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  );
                })
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function CompactSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-medium text-muted">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="h-9 w-full rounded-lg border border-line bg-white px-2.5 text-xs text-text">
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

interface ReferenceCandidate {
  key: string;
  asset: Asset;
  clip?: Clip;
}

function referenceCandidateName(
  category: keyof VisualConfig["references"],
  asset: Asset,
  clip?: Clip,
): string {
  if (category === "characters" && clip?.persons?.length) return clip.persons.join("、");
  if (category === "objects" && clip?.objects?.length) return clip.objects.join("、");
  if (category === "spaces" && clip?.sceneType) return clip.sceneType;
  return clip?.title || asset.name;
}

function ReferencePickerModal({
  category,
  assets,
  loading,
  error,
  onRetry,
  onClose,
  onConfirm,
}: {
  category: keyof VisualConfig["references"];
  assets: Asset[];
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  onClose: () => void;
  onConfirm: (references: Reference[]) => void;
}) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const label = REF_TABS.find((tab) => tab.key === category)?.label ?? "素材";

  const candidates = useMemo(() => {
    const all: ReferenceCandidate[] = assets.flatMap((asset) =>
      asset.clips.length
        ? asset.clips.map((clip) => ({ key: `${asset.id}:${clip.id}`, asset, clip }))
        : [{ key: `${asset.id}:asset`, asset }],
    );
    const semanticMatches = all.filter(({ clip }) => {
      if (category === "characters") return Boolean(clip?.persons?.length);
      if (category === "objects") return Boolean(clip?.objects?.length);
      return Boolean(clip?.sceneType);
    });
    const source = semanticMatches.length ? semanticMatches : all;
    const keyword = search.trim().toLowerCase();
    if (!keyword) return source;
    return source.filter(({ asset, clip }) =>
      [
        asset.name,
        asset.transcript,
        asset.ocrText,
        clip?.title,
        clip?.transcriptSegment,
        clip?.sceneType,
        ...(clip?.persons ?? []),
        ...(clip?.objects ?? []),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    );
  }, [assets, category, search]);

  function toggle(key: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function confirm() {
    const references = candidates
      .filter((candidate) => selected.has(candidate.key))
      .map(({ asset, clip }) => ({
        id: uid(),
        category,
        assetId: asset.id,
        clipId: clip?.id,
        name: referenceCandidateName(category, asset, clip),
        detail: clip
          ? `${asset.name} · ${clip.range || `${clip.startTime.toFixed(1)}s–${clip.endTime.toFixed(1)}s`}`
          : `${asset.name} · 完整素材`,
        variant: clip?.variant ?? asset.variant,
        locked: false,
      } satisfies Reference));
    onConfirm(references);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/55 p-6 backdrop-blur-sm">
      <button type="button" aria-label="关闭统一素材选择器" className="absolute inset-0" onClick={onClose} />
      <section className="relative z-10 flex max-h-[78vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-text">从真实素材库选择{label}</h2>
            <p className="mt-0.5 text-xs text-muted">只有确认后才会写入脚本视觉配置</p>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭" className="rounded-lg p-2 text-muted hover:bg-canvas">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="border-b border-line p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索素材名称、对白、OCR 或识别标签…"
              className="w-full rounded-lg border border-line bg-canvas py-2 pl-9 pr-3 text-sm text-text focus:border-blue focus:bg-surface"
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-blue" /></div>
          ) : error ? (
            <div className="py-14 text-center">
              <p className="text-sm text-red">素材加载失败：{error.message}</p>
              <button type="button" onClick={onRetry} className="mt-3 rounded-lg bg-blue px-3 py-2 text-xs text-white">重试</button>
            </div>
          ) : candidates.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted">当前项目没有可选择的真实素材片段</div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {candidates.map(({ key, asset, clip }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggle(key)}
                  className={clsx(
                    "flex items-center gap-3 rounded-xl border p-2.5 text-left transition",
                    selected.has(key) ? "border-blue bg-blue-soft/40" : "border-line hover:border-blue/40 hover:bg-canvas",
                  )}
                >
                  <Thumbnail
                    variant={clip?.variant ?? asset.variant}
                    imageUrl={clip?.thumbnailUrl ?? asset.thumbnailUrl}
                    className="h-16 w-24 shrink-0 rounded-lg"
                  />
                  <span className="min-w-0 flex-1">
                    <strong className="block truncate text-sm text-text">{referenceCandidateName(category, asset, clip)}</strong>
                    <small className="mt-1 block truncate text-xs text-muted">{asset.name}</small>
                    <small className="block text-[11px] text-muted">{clip?.range || "完整素材"}</small>
                  </span>
                  <span className={clsx("flex h-5 w-5 shrink-0 items-center justify-center rounded border", selected.has(key) ? "border-blue bg-blue text-white" : "border-line")}>
                    {selected.has(key) && <Check className="h-3.5 w-3.5" />}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <footer className="flex items-center justify-between border-t border-line px-5 py-3">
          <span className="text-xs text-muted">已选择 {selected.size} 项</span>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm text-text hover:bg-canvas">取消</button>
            <button type="button" onClick={confirm} disabled={!selected.size} className="rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white hover:bg-blue-2 disabled:cursor-not-allowed disabled:opacity-40">确认添加</button>
          </div>
        </footer>
      </section>
    </div>
  );
}

/* ──────────────────────────────────────────────
   子组件：一句脚本 + 多个分镜行
   ────────────────────────────────────────────── */

interface StoryboardSceneRowProps {
  unit: ScriptUnit;
  selected: boolean;
  activeShotId: string | null;
  onToggleSelected: () => void;
  onUpdateUnit: (patch: Partial<ScriptUnit>) => void;
  onUpdateShot: (shotId: string, patch: Partial<Shot>) => void;
  onAddShot: () => void;
  onDeleteShot: (shotId: string) => void;
  onDeleteScene: () => void;
  onOpenProduction: (shotId: string, mode?: VisualMode) => void;
  onAiComplete: (shotId: string) => void;
  aiLoading: boolean;
}

function StoryboardSceneRow(props: StoryboardSceneRowProps) {
  const {
    unit,
    selected,
    activeShotId,
    onToggleSelected,
    onUpdateUnit,
    onUpdateShot,
    onAddShot,
    onDeleteShot,
    onDeleteScene,
    onOpenProduction,
    onAiComplete,
    aiLoading,
  } = props;
  const sharedStyle: React.CSSProperties = { gridRow: `1 / span ${unit.shots.length}` };
  const hasActiveShot = unit.shots.some((shot) => shot.id === activeShotId);

  return (
    <article className={clsx("storyboard-scene-grid", selected && "is-selected", hasActiveShot && "is-active")}>
      <div className="storyboard-cell storyboard-number-cell" style={{ ...sharedStyle, gridColumn: 1 }}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelected}
          aria-label={`选择第 ${unit.index + 1} 句脚本`}
          className="h-4 w-4 accent-blue"
        />
        <strong>{String(unit.index + 1).padStart(2, "0")}</strong>
        <span>{unit.shots.length} 个分镜</span>
        <button onClick={onDeleteScene} className="mt-auto rounded-md p-1.5 text-muted hover:bg-red/10 hover:text-red" title="删除整句脚本">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="storyboard-cell flex flex-col gap-3" style={{ ...sharedStyle, gridColumn: 2 }}>
        <label className="block">
          <span className="mb-1.5 block text-[11px] font-medium text-muted">大纲</span>
          <textarea value={unit.outline} onChange={(event) => onUpdateUnit({ outline: event.target.value })} rows={3} placeholder="概括这句脚本的拍摄内容" className="storyboard-textarea min-h-[72px] p-1.5 font-medium" />
        </label>
        <details className="rounded-lg border border-line bg-canvas/55 px-2.5 py-2">
          <summary className="cursor-pointer text-[11px] font-medium text-muted">画面意图（高级）</summary>
          <textarea value={unit.intent} onChange={(event) => onUpdateUnit({ intent: event.target.value })} rows={3} placeholder="补充这句脚本希望表达的画面意图" className="storyboard-textarea mt-2 min-h-[66px] bg-white p-2" />
        </details>
      </div>

      <div className="storyboard-cell flex flex-col" style={{ ...sharedStyle, gridColumn: 5 }}>
        <span className="mb-2 block text-[11px] font-medium text-muted">台词文案 · 同句分镜共享</span>
        <textarea
          value={unit.text}
          onChange={(event) => onUpdateUnit({ text: event.target.value })}
          rows={8}
          placeholder="点击输入台词或旁白"
          className="storyboard-textarea min-h-[154px] flex-1 rounded-lg bg-[#fafafa] p-3"
        />
      </div>

      {unit.shots.map((shot, shotIndex) => {
        const rowStyle: React.CSSProperties = { gridRow: shotIndex + 1 };
        const hasNext = shotIndex < unit.shots.length - 1;
        const active = activeShotId === shot.id;
        const candidate = shot.candidates.find((item) => item.id === shot.selectedClipId || item.clipId === shot.selectedClipId);
        const generatedUrl = shot.generatedVideoPath || shot.generatedEffectVideoPath || shot.generatedImagePath;
        const sourceLabel = shot.generatedVideoPath
          ? "图生视频"
          : shot.generatedEffectVideoPath
            ? "示意特效"
            : shot.generatedImagePath
              ? "AI分镜"
              : candidate
                ? "素材推荐"
                : SOURCE_OPTIONS.find((option) => option.value === shot.visualMode)?.label ?? "未设置";
        const visualTitle = candidate?.title
          || (shot.generatedVideoPath ? "AI 分镜视频" : shot.generatedEffectVideoPath ? "示意特效视频" : shot.generatedImagePath ? "AI 分镜关键帧" : "暂无画面");
        return (
          <Fragment key={shot.id}>
            <div className={clsx("storyboard-cell storyboard-shot-cell flex flex-col", hasNext && "has-next-shot", active && "is-active")} style={{ ...rowStyle, gridColumn: 3 }}>
              <div className="mb-2 flex items-center gap-2">
                <strong className="text-xs text-blue">分镜 {String(shotIndex + 1).padStart(2, "0")}</strong>
                <StatusPill status={shot.status} />
                <button onClick={() => onDeleteShot(shot.id)} disabled={unit.shots.length <= 1} title={unit.shots.length <= 1 ? "每句脚本至少保留一个分镜" : "删除当前分镜"} className="ml-auto rounded-md p-1 text-muted hover:bg-red/10 hover:text-red disabled:cursor-not-allowed disabled:opacity-25">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <textarea value={shot.description} onChange={(event) => onUpdateShot(shot.id, { description: event.target.value })} rows={6} placeholder="描述景别、主体、动作、构图和运镜" className="storyboard-textarea min-h-[112px] flex-1 rounded-lg bg-[#fafafa] p-3" />
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <button onClick={() => onAiComplete(shot.id)} disabled={aiLoading} className="flex items-center gap-1 rounded-md bg-canvas px-2 py-1.5 text-[11px] text-muted hover:text-blue disabled:opacity-45">
                  {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                  AI 补充细节
                </button>
                {shotIndex === unit.shots.length - 1 && (
                  <button onClick={onAddShot} className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] text-blue hover:bg-blue-soft"><Plus className="h-3.5 w-3.5" />同句新增分镜</button>
                )}
              </div>
            </div>

            <div className={clsx("storyboard-cell storyboard-shot-cell flex flex-col", hasNext && "has-next-shot", active && "is-active")} style={{ ...rowStyle, gridColumn: 4 }}>
              {generatedUrl || candidate ? (
                <div className="flex min-h-[104px] gap-3 rounded-xl border border-line bg-white p-2">
                  {shot.generatedVideoPath || shot.generatedEffectVideoPath ? (
                    <video src={shot.generatedVideoPath || shot.generatedEffectVideoPath} muted preload="metadata" className="h-[88px] w-[132px] shrink-0 rounded-lg bg-ink object-cover" />
                  ) : (
                    <Thumbnail variant={candidate?.variant ?? "stage"} imageUrl={shot.generatedImagePath} className="h-[88px] w-[132px] shrink-0 rounded-lg" />
                  )}
                  <div className="min-w-0 flex-1 py-1">
                    <span className="rounded bg-canvas px-1.5 py-0.5 text-[10px] text-muted">{sourceLabel}</span>
                    <strong className="mt-2 block line-clamp-2 text-sm text-text">{visualTitle}</strong>
                    <small className="mt-1 block truncate text-[11px] text-muted">{candidate ? `${candidate.source}${candidate.range ? ` · ${candidate.range}` : ""}` : "已写入当前分镜"}</small>
                  </div>
                </div>
              ) : (
                <button onClick={() => onOpenProduction(shot.id, "recommend")} className="flex min-h-[104px] flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-line text-xs text-muted hover:border-blue hover:bg-blue-soft/40 hover:text-blue">
                  <Plus className="h-5 w-5" />添加或生成画面
                </button>
              )}
              <button onClick={() => onOpenProduction(shot.id, shot.visualMode ?? "recommend")} className="mt-2 flex items-center justify-center gap-1.5 rounded-lg border border-line py-2 text-xs font-medium text-text hover:border-blue hover:text-blue">
                <Clapperboard className="h-4 w-4" />制作画面 <span className="font-normal text-muted">· {sourceLabel}</span>
              </button>
            </div>

            <div className={clsx("storyboard-cell storyboard-shot-cell flex flex-col", hasNext && "has-next-shot", active && "is-active")} style={{ ...rowStyle, gridColumn: 6 }}>
              <span className="mb-1.5 text-[11px] font-medium text-muted">备注 · 分镜 {String(shotIndex + 1).padStart(2, "0")}</span>
              <textarea value={shot.notes} onChange={(event) => onUpdateShot(shot.id, { notes: event.target.value })} rows={5} placeholder="拍摄、特效或审核备注" className="storyboard-textarea min-h-[104px] flex-1 rounded-lg bg-[#fafafa] p-2.5" />
              <label className="mt-2 flex items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-xs text-muted">
                <Clock3 className="h-3.5 w-3.5" />
                <input type="number" min={1} value={shot.duration} onChange={(event) => onUpdateShot(shot.id, { duration: Math.max(1, Number(event.target.value) || 1) })} className="min-w-0 flex-1 bg-transparent text-right font-medium text-text" />
                <span>秒</span>
              </label>
            </div>
          </Fragment>
        );
      })}
    </article>
  );
}

/* ──────────────────────────────────────────────
   子组件：分镜画面制作台（右栏）
   ────────────────────────────────────────────── */

interface ProductionPanelProps {
  selected: { unit: ScriptUnit; shot: Shot } | null;
  activeTab: VisualMode;
  setTab: (t: VisualMode) => void;
  genStates?: ShotGenStates;
  capabilities?: Awaited<ReturnType<typeof generateApi.getCapabilities>>;
  visualConfig: VisualConfig;
  onMatch: () => void;
  matchLoading: boolean;
  onGenerateImage: (description: string) => void;
  onGenerateVideo: (motion: string) => void;
  onGenerateEffect: (sketchData: string, motion: string) => void;
  onRelate: (candidateId: string) => void;
  imgLoading: boolean;
  videoLoading: boolean;
  effectLoading: boolean;
  onRefreshMedia: () => void;
}

function ProductionPanel(props: ProductionPanelProps) {
  const {
    selected,
    activeTab,
    setTab,
    genStates,
    capabilities,
    visualConfig,
    onMatch,
    matchLoading,
    onGenerateImage,
    onGenerateVideo,
    onGenerateEffect,
    onRelate,
    imgLoading,
    videoLoading,
    effectLoading,
    onRefreshMedia,
  } = props;

  const tabs: { value: VisualMode; label: string; Icon: typeof ImageIcon }[] = [
    { value: "recommend", label: "素材推荐", Icon: Search },
    { value: "image", label: "AI分镜", Icon: ImageIcon },
    { value: "video", label: "图生视频", Icon: Video },
    { value: "sketch", label: "示意特效", Icon: PenTool },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* 头部 */}
      <div className="shrink-0 border-b border-line py-3 pl-4 pr-14">
        {selected ? (
          <>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="rounded bg-canvas px-1.5 py-0.5 font-medium">
                场景 {selected.unit.index + 1}
              </span>
              <span className="rounded bg-canvas px-1.5 py-0.5 font-medium">分镜</span>
              <StatusPill status={selected.shot.status} />
            </div>
            <p className="mt-1.5 line-clamp-2 text-sm text-text">
              {selected.unit.intent || selected.unit.outline || selected.shot.description || "（未填写意图描述）"}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted">请从左侧选择一个分镜</p>
        )}
      </div>

      {/* tab 切换 */}
      <div className="flex shrink-0 border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            disabled={!selected}
            className={clsx(
              "flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium transition disabled:opacity-40",
              activeTab === t.value
                ? "border-b-2 border-blue text-blue"
                : "text-muted hover:text-text",
            )}
          >
            <t.Icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* tab 内容 */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!selected ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-muted">
            <Layers className="h-10 w-10 text-line" />
            <p className="mt-2 text-sm">选择分镜后可进行画面制作</p>
          </div>
        ) : activeTab === "recommend" ? (
          <RecommendTab
            shot={selected.shot}
            onMatch={onMatch}
            matchLoading={matchLoading}
            onRelate={onRelate}
          />
        ) : activeTab === "image" ? (
          <ImageTab
            shot={selected.shot}
            genState={genStates?.image}
            visualConfig={visualConfig}
            loading={imgLoading}
            onGenerate={onGenerateImage}
            onRefreshMedia={onRefreshMedia}
          />
        ) : activeTab === "video" ? (
          <VideoTab
            shot={selected.shot}
            imageState={genStates?.image}
            videoState={genStates?.video}
            loading={videoLoading}
            onGenerate={onGenerateVideo}
            capability={capabilities?.imageToVideo}
            onRefreshMedia={onRefreshMedia}
          />
        ) : (
          <SketchTab
            shot={selected.shot}
            genState={genStates?.effect}
            loading={effectLoading}
            onGenerate={onGenerateEffect}
            capability={capabilities?.effectVideo}
          />
        )}
      </div>

      {/* 候选区 */}
      {selected && (
        <div className="shrink-0 border-t border-line bg-canvas/50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-text">候选区</span>
            <span className="text-[11px] text-muted">
              {selected.shot.candidates.length} 个候选
            </span>
          </div>
          <div className="max-h-44 space-y-2 overflow-y-auto">
            {selected.shot.candidates.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted">
                暂无候选，可切换到「AI分镜」生成或点击「重新匹配」
              </p>
            ) : (
              selected.shot.candidates.map((c) => (
                <CandidateCard
                  key={c.id}
                  candidate={c}
                  related={selected.shot.selectedClipId === (c.clipId ?? c.id)}
                  onRelate={() => onRelate(c.clipId ?? c.id)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: Shot["status"] }) {
  const map: Record<Shot["status"], string> = {
    已选择: "bg-teal/10 text-teal",
    待编辑: "bg-canvas text-muted",
    待确认: "bg-amber/10 text-amber",
  };
  return <span className={clsx("rounded px-1.5 py-0.5 text-[11px] font-medium", map[status])}>{status}</span>;
}

/* ── 素材推荐 tab ── */

function RecommendTab({
  shot,
  onMatch,
  matchLoading,
  onRelate,
}: {
  shot: Shot;
  onMatch: () => void;
  matchLoading: boolean;
  onRelate: (id: string) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-blue-soft bg-blue-soft/40 p-3">
        <div className="flex items-start gap-2">
          <Search className="mt-0.5 h-4 w-4 shrink-0 text-blue" />
          <div className="flex-1">
            <div className="text-sm font-medium text-text">素材智能匹配</div>
            <p className="mt-0.5 text-xs text-muted">
              基于分镜描述在素材库中检索候选画面，按匹配度排序，低置信度结果会标记提示。
            </p>
          </div>
        </div>
        <button
          onClick={onMatch}
          disabled={matchLoading}
          className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-2 disabled:opacity-60"
        >
          {matchLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          重新匹配素材
        </button>
      </div>

      {shot.candidates.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line py-8 text-center text-xs text-muted">
          暂无匹配候选，点击「重新匹配素材」
        </div>
      ) : (
        shot.candidates.map((c) => (
          <CandidateCard
            key={c.id}
            candidate={c}
            related={shot.selectedClipId === (c.clipId ?? c.id)}
            onRelate={() => onRelate(c.clipId ?? c.id)}
            expanded
          />
        ))
      )}
    </div>
  );
}

/* ── AI 分镜 tab ── */

function ImageTab({
  shot,
  genState,
  visualConfig,
  loading,
  onGenerate,
  onRefreshMedia,
}: {
  shot: Shot;
  genState?: GenState;
  visualConfig: VisualConfig;
  loading: boolean;
  onGenerate: (description: string) => void;
  onRefreshMedia: () => void;
}) {
  const [prompt, setPrompt] = useState(shot.description);
  useEffect(() => setPrompt(shot.description), [shot.id, shot.description]);
  const running = genState?.status === "running" && genState?.kind === "image";
  const imageUrl = shot.generatedImagePath || genState?.resultUrl;
  const done = Boolean(imageUrl);

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-line p-2.5 text-xs text-muted">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-text">
          <ImageIcon className="h-3.5 w-3.5 text-blue" />
          关键帧生成
        </div>
        风格 {STYLE_PRESETS.find((s) => s.value === visualConfig.stylePreset)?.label} · 画幅{" "}
        {visualConfig.aspectRatio} · {visualConfig.palette}
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-muted">分镜描述（可编辑）</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          className="w-full resize-none rounded-lg border border-line bg-canvas px-2.5 py-2 text-xs text-text focus:border-blue focus:bg-surface"
        />
      </div>

      {running && <GenStageView genState={genState!} />}

      {done && (
        <div className="overflow-hidden rounded-lg border border-line">
          <img
            src={imageUrl}
            alt="AI 关键帧"
            className="aspect-video w-full object-cover"
            onError={onRefreshMedia}
          />
          <div className="flex items-center gap-1.5 bg-teal/10 px-2.5 py-1.5 text-xs text-teal">
            <CheckCircle2 className="h-3.5 w-3.5" />
            关键帧已生成并写入分镜
          </div>
        </div>
      )}

      {genState?.status === "error" && genState?.kind === "image" && (
        <div className="flex items-center gap-1.5 rounded-lg bg-red/10 px-2.5 py-2 text-xs text-red">
          <AlertTriangle className="h-3.5 w-3.5" />
          {genState.error}
        </div>
      )}

      <button
        onClick={() => onGenerate(prompt)}
        disabled={loading || running || !prompt.trim()}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-2 disabled:opacity-60"
      >
        {loading || running ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Sparkles className="h-4 w-4" />
        )}
        {done ? "重新生成关键帧" : "生成关键帧"}
      </button>
    </div>
  );
}

/* ── 图生视频 tab ── */

function VideoTab({
  shot,
  imageState,
  videoState,
  loading,
  onGenerate,
  capability,
  onRefreshMedia,
}: {
  shot: Shot;
  imageState?: GenState;
  videoState?: GenState;
  loading: boolean;
  onGenerate: (motion: string) => void;
  capability?: { available: boolean; reason: string };
  onRefreshMedia: () => void;
}) {
  const [motion, setMotion] = useState("");
  const imageUrl = shot.generatedImagePath || imageState?.resultUrl;
  const videoUrl = shot.generatedVideoPath || videoState?.resultUrl;
  const hasImage = Boolean(imageUrl);
  const running = videoState?.status === "running";
  const done = Boolean(videoUrl);

  return (
    <div className="space-y-3">
      {!hasImage ? (
        <div className="flex flex-col items-center rounded-lg border border-dashed border-line py-8 text-center">
          <ImageIcon className="h-8 w-8 text-line" />
          <p className="mt-2 text-xs text-muted">请先在「AI分镜」生成关键帧</p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-line">
            <img
              src={imageUrl}
              alt="关键帧"
              className="aspect-video w-full object-cover"
              onError={onRefreshMedia}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">运镜描述（可选）</label>
            <input
              value={motion}
              onChange={(e) => setMotion(e.target.value)}
              placeholder="如：缓慢推进、左移跟拍…"
              className="w-full rounded-lg border border-line bg-canvas px-2.5 py-2 text-xs text-text focus:border-blue focus:bg-surface"
            />
          </div>

          {running && <GenStageView genState={videoState!} />}

          {done && (
            <div className="overflow-hidden rounded-lg border border-line">
              <video
                src={videoUrl}
                controls
                className="aspect-video w-full bg-ink"
              />
              <div className="flex items-center gap-1.5 bg-teal/10 px-2.5 py-1.5 text-xs text-teal">
                <CheckCircle2 className="h-3.5 w-3.5" />
                视频已生成并关联到分镜
              </div>
            </div>
          )}

          {videoState?.status === "error" && (
            <div className="flex items-center gap-1.5 rounded-lg bg-red/10 px-2.5 py-2 text-xs text-red">
              <AlertTriangle className="h-3.5 w-3.5" />
              {videoState.error}
            </div>
          )}

          {capability && !capability.available && (
            <div className="flex items-center gap-1.5 rounded-lg bg-amber/10 px-2.5 py-2 text-xs text-amber">
              <AlertTriangle className="h-3.5 w-3.5" />
              {capability.reason}
            </div>
          )}

          <button
            onClick={() => onGenerate(motion)}
            disabled={loading || running || capability?.available === false}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-2 disabled:opacity-60"
          >
            {loading || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />}
            {done ? "重新生成视频" : "生成视频"}
          </button>
        </>
      )}
    </div>
  );
}

/* ── 示意特效 tab（手绘 Canvas）── */

function SketchTab({
  shot,
  genState,
  loading,
  onGenerate,
  capability,
}: {
  shot: Shot;
  genState?: GenState;
  loading: boolean;
  onGenerate: (sketchData: string, motion: string) => void;
  capability?: { available: boolean; reason: string };
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const [color, setColor] = useState(SKETCH_COLORS[1]);
  const [size, setSize] = useState(3);
  const [motion, setMotion] = useState("");

  const getPos = (e: React.PointerEvent) => {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * c.width,
      y: ((e.clientY - rect.top) / rect.height) * c.height,
    };
  };

  const start = (e: React.PointerEvent) => {
    drawing.current = true;
    last.current = getPos(e);
    (e.target as Element).setPointerCapture(e.pointerId);
  };

  const move = (e: React.PointerEvent) => {
    if (!drawing.current) return;
    const ctx = canvasRef.current!.getContext("2d")!;
    const p = getPos(e);
    const l = last.current!;
    ctx.strokeStyle = color;
    ctx.lineWidth = size;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(l.x, l.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last.current = p;
  };

  const end = () => {
    drawing.current = false;
    last.current = null;
  };

  const clear = () => {
    const c = canvasRef.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
  };

  const exportSketch = () => {
    const source = canvasRef.current!;
    const output = document.createElement("canvas");
    output.width = source.width;
    output.height = source.height;
    const context = output.getContext("2d")!;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, output.width, output.height);
    context.drawImage(source, 0, 0);
    return output.toDataURL("image/png");
  };

  const running = genState?.status === "running" && genState?.kind === "effect";
  const effectVideoUrl = shot.generatedEffectVideoPath || genState?.resultUrl;
  const done = Boolean(effectVideoUrl);

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-line p-2.5 text-xs text-muted">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-text">
          <PenTool className="h-3.5 w-3.5 text-blue" />
          手绘示意画布
        </div>
        在 640×360 画布上绘制示意画面，AI 将生成对应的特效视频。
      </div>

      <canvas
        ref={canvasRef}
        width={640}
        height={360}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerLeave={end}
        className="w-full touch-none rounded-lg border border-line bg-white"
        style={{ aspectRatio: "640 / 360" }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          {SKETCH_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => setColor(c)}
              className={clsx(
                "h-5 w-5 rounded-full border-2 transition",
                color === c ? "border-ink" : "border-transparent",
              )}
              style={{ backgroundColor: c }}
            />
          ))}
        </div>
        <div className="flex items-center gap-1 text-xs text-muted">
          粗细
          <input
            type="range"
            min={1}
            max={10}
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
            className="w-20 accent-blue"
          />
        </div>
        <button
          onClick={clear}
          className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-muted transition hover:bg-canvas"
        >
          <Eraser className="h-3 w-3" />
          清空
        </button>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-muted">动效描述（可选）</label>
        <input
          value={motion}
          onChange={(e) => setMotion(e.target.value)}
          placeholder="如：箭头从左向右移动…"
          className="w-full rounded-lg border border-line bg-canvas px-2.5 py-2 text-xs text-text focus:border-blue focus:bg-surface"
        />
      </div>

      {running && <GenStageView genState={genState!} />}

      {done && (
        <div className="overflow-hidden rounded-lg border border-line">
          <video src={effectVideoUrl} controls className="aspect-video w-full bg-ink" />
          <div className="flex items-center gap-1.5 bg-teal/10 px-2.5 py-1.5 text-xs text-teal">
            <CheckCircle2 className="h-3.5 w-3.5" />
            特效视频已生成并关联到分镜
          </div>
        </div>
      )}

      {genState?.status === "error" && genState.kind === "effect" && (
        <div className="flex items-center gap-1.5 rounded-lg bg-red/10 px-2.5 py-2 text-xs text-red">
          <AlertTriangle className="h-3.5 w-3.5" />
          {genState.error}
        </div>
      )}

      {capability && !capability.available && (
        <div className="flex items-center gap-1.5 rounded-lg bg-amber/10 px-2.5 py-2 text-xs text-amber">
          <AlertTriangle className="h-3.5 w-3.5" />
          {capability.reason}
        </div>
      )}

      <button
        onClick={() => onGenerate(exportSketch(), motion)}
        disabled={loading || running || capability?.available === false}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-2 disabled:opacity-60"
      >
        {loading || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
        生成特效视频
      </button>
    </div>
  );
}

/* ── 生成阶段视图 ── */

function GenStageView({ genState }: { genState: GenState }) {
  const stages = GEN_STAGES[genState.kind ?? "image"];
  const stageIdx = Math.min(stages.length - 1, Math.floor((genState.progress / 100) * stages.length));
  return (
    <div className="rounded-lg border border-blue-soft bg-blue-soft/30 p-3">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-medium text-blue">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {stages[stageIdx]}
        </span>
        <span className="font-mono text-blue">{Math.round(genState.progress)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white">
        <div
          className="h-full rounded-full bg-blue transition-all duration-300"
          style={{ width: `${genState.progress}%` }}
        />
      </div>
      <div className="mt-2 space-y-1">
        {stages.map((s, i) => (
          <div key={s} className="flex items-center gap-1.5 text-[11px]">
            {i < stageIdx ? (
              <Check className="h-3 w-3 text-teal" />
            ) : i === stageIdx ? (
              <Loader2 className="h-3 w-3 animate-spin text-blue" />
            ) : (
              <span className="h-3 w-3 rounded-full border border-line" />
            )}
            <span className={i <= stageIdx ? "text-text" : "text-muted"}>{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 候选卡片 ── */

function CandidateCard({
  candidate,
  related,
  onRelate,
  expanded = false,
}: {
  candidate: Candidate;
  related: boolean;
  onRelate: () => void;
  expanded?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex gap-2.5 rounded-lg border p-2.5 transition",
        related ? "border-blue bg-blue-soft/50" : "border-line bg-surface",
      )}
    >
      <Thumbnail variant={candidate.variant} className="h-14 w-20 shrink-0 rounded" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium text-text">{candidate.title}</span>
          {candidate.lowConfidence && (
            <span className="shrink-0 rounded bg-amber/15 px-1.5 py-0.5 text-[10px] font-medium text-amber">
              低置信
            </span>
          )}
        </div>
        <div className="text-[11px] text-muted">
          {candidate.source}
          {candidate.range ? ` · ${candidate.range}` : ""}
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-line">
            <div
              className={clsx(
                "h-full rounded-full",
                candidate.score >= 0.8 ? "bg-teal" : candidate.score >= 0.6 ? "bg-amber" : "bg-red",
              )}
              style={{ width: `${candidate.score * 100}%` }}
            />
          </div>
          <span className="text-[11px] font-medium text-muted">{Math.round(candidate.score * 100)}%</span>
        </div>
        {expanded && (
          <p className="mt-1 line-clamp-2 text-[11px] text-muted">{candidate.reason}</p>
        )}
      </div>
      <button
        onClick={onRelate}
        disabled={related}
        className={clsx(
          "flex shrink-0 items-center gap-1 self-center rounded-md px-2 py-1 text-[11px] font-medium transition",
          related
            ? "bg-blue-soft text-blue"
            : "border border-blue text-blue hover:bg-blue hover:text-white",
        )}
      >
        {related ? <Check className="h-3 w-3" /> : <Link2 className="h-3 w-3" />}
        {related ? "已关联" : "关联"}
      </button>
    </div>
  );
}

/* ── 空状态 ── */

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
