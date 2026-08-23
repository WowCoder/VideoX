import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  CloudUpload,
  Download,
  FileText,
  ImagePlus,
  Library,
  Loader2,
  MoreHorizontal,
  RotateCcw,
  Sparkles,
  WandSparkles,
  X,
} from "lucide-react";
import { useLocation, useNavigate, useNavigationBlocker, useParams } from "@/router";
import { executeProjectOperation, type OperationScope, type ProjectOperation } from "@/api/generate";
import * as jobApi from "@/api/jobs";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { MvpScriptComposer } from "./MvpScriptComposer";
import { AIScriptGeneratorModal, type AIScriptRequest } from "@/components/AIScriptGeneratorModal";
import { QuickAIGenerateModal, type GenerationKind } from "@/components/QuickAIGenerateModal";
import { AIVoiceoverModal } from "@/components/AIVoiceoverModal";
import { applyVoiceoverMaster } from "@/api/voiceover";
import { ProjectAssetPickerModal } from "@/components/ProjectAssetPickerModal";
import { ProjectTaskButton, ProjectTaskPanel } from "@/components/ProjectTaskPanel";
import { ProjectOverview } from "./ProjectOverview";
import type { Job } from "@/types/models";

const saveLabels = {
  idle: "尚未加载",
  dirty: "有未保存改动",
  saving: "保存中…",
  saved: "已保存",
  error: "保存失败",
  conflict: "版本冲突",
} as const;

const operationLabels: Record<ProjectOperation, string> = {
  match_assets: "匹配素材",
  complete_shots: "完善镜头",
  generate_image: "生成图片",
  generate_video: "生成视频",
  generate_effect: "生成特效",
  generate_script: "生成项目脚本",
  generate_voiceover: "生成 AI 旁白",
  compose: "编排主成片",
  export: "导出主成片",
};

export default function ProjectWorkspaceView() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const notify = useUIStore((state) => state.notify);
  const openUploadDrawer = useUIStore((state) => state.openUploadDrawer);
  const openProjectEdit = useUIStore((state) => state.openProjectEdit);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const store = useWorkspaceStore();
  const [operationError, setOperationError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportAspectRatio, setExportAspectRatio] = useState("16:9");
  const [exportResolution, setExportResolution] = useState("1080p");
  const [aiScriptOpen, setAiScriptOpen] = useState(false);
  const [quickAIOpen, setQuickAIOpen] = useState(false);
  const [quickAIKind, setQuickAIKind] = useState<GenerationKind>("image");
  const [quickAIScope, setQuickAIScope] = useState<"project" | "scene" | "shot">("shot");
  const [taskPanelOpen, setTaskPanelOpen] = useState(false);
  const [voiceoverOpen, setVoiceoverOpen] = useState(false);
  const [addAssetMenuOpen, setAddAssetMenuOpen] = useState(false);
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [submittedJobs, setSubmittedJobs] = useState<Job[]>([]);
  const mountedRef = useRef(true);
  const addAssetMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!addAssetMenuOpen) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!addAssetMenuRef.current?.contains(event.target as Node)) setAddAssetMenuOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, [addAssetMenuOpen]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  async function refreshWhenScriptJobFinishes(jobId: string) {
    for (let attempt = 0; attempt < 200 && mountedRef.current; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      if (!mountedRef.current) return;
      try {
        const job = await jobApi.get(jobId);
        if (job.status === "SUCCEEDED") {
          await useWorkspaceStore.getState().reloadServer();
          if (mountedRef.current) notify(job.detail || "AI 脚本已写入项目");
          return;
        }
        if (["FAILED", "CANCELLED"].includes(job.status)) {
          if (mountedRef.current) notify(job.resultDetail || job.detail || "AI 脚本生成失败", "error");
          return;
        }
      } catch {
        // 临时网络错误不终止后台任务跟踪，下一轮继续查询。
      }
    }
  }

  useNavigationBlocker(
    store.saveState === "dirty" || store.saveState === "saving",
    "项目仍有未保存改动，确定离开吗？",
  );

  useEffect(() => {
    if (!projectId) return;
    if (import.meta.env.DEV && projectId === "__preview__") {
      void import("@/dev/workspacePreview").then(({ workspacePreviewFixture }) => {
        useWorkspaceStore.getState().hydrate(workspacePreviewFixture());
      });
      return;
    }
    setCurrentProject(projectId);
    void useWorkspaceStore.getState().load(projectId);
  }, [projectId, setCurrentProject]);

  const workspace = store.workspace;
  const selectedScene = workspace?.document.storyboard.scenes.find((scene) => scene.id === store.selectedSceneId)
    ?? workspace?.document.storyboard.scenes[0];
  const selectedShot = selectedScene?.shots.find((shot) => shot.id === store.selectedShotId)
    ?? selectedScene?.shots[0];
  const startMethod = new URLSearchParams(location.search).get("start");
  const startGuide = startMethod === "write-script"
    ? { title: "项目已创建，从脚本开始", copy: "先建立叙事结构，再让素材和 AI 围绕同一组镜头工作。" }
    : startMethod === "upload-assets"
      ? { title: "项目已创建，从素材开始", copy: "先上传项目素材，然后把素材拖入或选择到对应镜头。" }
      : startMethod === "ai-script"
        ? { title: "项目已创建，使用 AI 辅助脚本", copy: "明确场景或镜头范围后，让 AI 完善内容和画面。" }
        : startMethod === "blank"
          ? { title: "空白项目已创建", copy: "从左侧建立场景，或先导入素材开始创作。" }
          : null;

  const operationMutation = useMutation({
    mutationFn: async ({ operation, parameters = {}, scope }: { operation: ProjectOperation; parameters?: Record<string, unknown>; scope?: OperationScope }) => {
      if (!workspace) throw new Error("项目尚未加载");
      await store.save("before_ai_operation");
      const currentState = useWorkspaceStore.getState();
      const current = currentState.workspace;
      if (!current) throw new Error("项目尚未加载");
      const currentScene = current.document.storyboard.scenes.find((scene) => scene.id === currentState.selectedSceneId)
        ?? current.document.storyboard.scenes[0];
      const currentShot = currentScene?.shots.find((shot) => shot.id === currentState.selectedShotId)
        ?? currentScene?.shots[0];
      const operationScope: OperationScope = scope
        ?? (["compose", "export", "match_assets", "generate_script"].includes(operation)
          ? { type: "project" }
          : currentShot?.id
            ? { type: "shot", shotIds: [currentShot.id] }
            : currentScene?.id
              ? { type: "scene", sceneIds: [currentScene.id] }
              : { type: "project" });
      return executeProjectOperation(current.project.id, {
        scope: operationScope,
        operation,
        parameters,
        expectedRevision: current.document.revision,
      });
    },
    onSuccess: async (jobs, variables) => {
      setOperationError(null);
      if (variables.operation === "export") setExportOpen(false);
      if (variables.operation === "generate_script") setAiScriptOpen(false);
      if (variables.operation === "generate_voiceover") setVoiceoverOpen(false);
      if (["generate_image", "generate_video", "generate_effect"].includes(variables.operation)) setQuickAIOpen(false);
      setSubmittedJobs(jobs);
      setTaskPanelOpen(true);
      notify(`${operationLabels[variables.operation]}已创建 ${jobs.length} 个任务，可在任务面板持续查看`);
      if (variables.operation === "generate_script" && jobs[0]) {
        void refreshWhenScriptJobFinishes(jobs[0].id);
      }
      await store.reloadServer();
      if (variables.operation === "generate_voiceover") {
        void queryClient.invalidateQueries({ queryKey: ["voiceover", projectId] });
      }
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "操作失败";
      setOperationError(message);
      notify(message, "error");
    },
  });

  const refreshAfterTaskUpdate = useCallback(() => {
    void useWorkspaceStore.getState().reloadServer();
    void queryClient.invalidateQueries({ queryKey: ["voiceover", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
  }, [projectId, queryClient]);

  const focusedJobId = new URLSearchParams(location.search).get("job") ?? undefined;
  useEffect(() => {
    if (focusedJobId) setTaskPanelOpen(true);
  }, [focusedJobId]);

  if (store.loading) {
    return <div className="flex min-h-[60vh] items-center justify-center text-sm text-muted"><Loader2 size={20} className="mr-2 animate-spin" />正在加载项目工作台…</div>;
  }
  if (!workspace) {
    return (
      <div className="mx-auto max-w-xl px-6 py-24 text-center">
        <AlertTriangle size={32} className="mx-auto text-red" />
        <h1 className="mt-4 text-lg font-semibold text-text">项目工作台加载失败</h1>
        <p className="mt-2 text-sm text-muted">{store.saveError ?? "项目不存在或暂时无法访问"}</p>
        <div className="mt-5 flex justify-center gap-2"><button type="button" onClick={() => navigate("/workspace")} className="rounded-lg border border-line px-4 py-2 text-sm text-text">返回工作台</button><button type="button" onClick={() => void useWorkspaceStore.getState().load(projectId)} className="rounded-lg bg-blue px-4 py-2 text-sm font-semibold text-white">重新加载</button></div>
      </div>
    );
  }

  const saveTone = store.saveState === "error" || store.saveState === "conflict"
    ? "text-red"
    : store.saveState === "dirty" || store.saveState === "saving" ? "text-amber" : "text-teal";
  const hasMeaningfulScript = workspace.document.storyboard.scenes.some((scene) => (
    Boolean(scene.narrationText.trim() || scene.intent.trim())
    || scene.shots.some((shot) => Boolean(shot.description.trim() || shot.assetId || shot.mediaVersions.length))
  ));

  function openExportDialog() {
    setExportAspectRatio(useWorkspaceStore.getState().workspace?.document.settings.aspectRatio || "16:9");
    setExportOpen(true);
  }

  async function deleteScene() {
    if (!selectedScene?.id || !window.confirm(`确认删除场景“${selectedScene.outline || "未命名场景"}”及其全部镜头？删除后可在短时间内撤销。`)) return;
    try {
      await store.deleteScene(selectedScene.id);
      notify("场景已删除，可通过页面提示撤销");
    } catch (error) {
      notify(error instanceof Error ? error.message : "场景删除失败", "error");
    }
  }

  async function deleteShot() {
    if (!selectedShot?.id || !window.confirm(`确认删除镜头 ${selectedShot.index + 1}？删除后可在短时间内撤销。`)) return;
    try {
      await store.deleteShot(selectedShot.id);
      notify("镜头已删除，可通过页面提示撤销");
    } catch (error) {
      notify(error instanceof Error ? error.message : "镜头删除失败", "error");
    }
  }

  // 项目的主任务是继续创作，因此默认进入编辑器；概览只作为显式的辅助视图。
  const editorMode = new URLSearchParams(location.search).get("view") !== "overview";

  function openQuickAI(scope: "project" | "scene" | "shot" = "shot", kind: GenerationKind = "image") {
    setOperationError(null);
    setQuickAIKind(kind);
    setQuickAIScope(scope);
    setQuickAIOpen(true);
  }

  async function applyGeneratedVoiceoverMaster(assetId: string) {
    try {
      await store.save("before_ai_operation");
      const current = useWorkspaceStore.getState().workspace;
      if (!current) throw new Error("项目尚未加载");
      await applyVoiceoverMaster(current.project.id, assetId, current.document.revision);
      await store.reloadServer();
      notify("AI 旁白母带已应用到项目");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "AI 旁白母带应用失败";
      notify(message, "error");
      throw reason;
    }
  }

  const taskPanel = (
    <ProjectTaskPanel
      projectId={workspace.project.id}
      projectName={workspace.project.name}
      scenes={workspace.document.storyboard.scenes}
      open={taskPanelOpen}
      submittedJobs={submittedJobs}
      focusJobId={focusedJobId}
      onClose={() => setTaskPanelOpen(false)}
      onTerminalUpdate={refreshAfterTaskUpdate}
    />
  );

  if (!editorMode) {
    return (
      <div className="h-full min-h-0 bg-canvas">
        <ProjectOverview
          workspace={workspace}
          onBack={() => navigate("/workspace")}
          onEnterEditor={() => navigate(`/workspace/projects/${workspace.project.id}`)}
          onEditProject={() => openProjectEdit(workspace.project)}
          onUpload={() => openUploadDrawer(workspace.project.id)}
          onOpenQuickAI={() => openQuickAI("project")}
          onOpenTasks={() => setTaskPanelOpen(true)}
        />
        <QuickAIGenerateModal
          open={quickAIOpen}
          projectName={workspace.project.name}
          scenes={workspace.document.storyboard.scenes}
          selectedScene={selectedScene}
          selectedShot={selectedShot}
          initialKind={quickAIKind}
          initialScope={quickAIScope}
          pending={operationMutation.isPending}
          error={operationError}
          onClose={() => !operationMutation.isPending && setQuickAIOpen(false)}
          onGenerate={(operation, scope, parameters) => operationMutation.mutate({ operation, scope, parameters })}
        />
        {taskPanel}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-canvas">
      <header className="relative z-20 shrink-0 border-b border-line bg-surface/95 px-4 py-2.5 backdrop-blur-xl">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="flex min-w-0 items-center gap-3"><button type="button" onClick={() => navigate("/workspace")} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted hover:bg-canvas hover:text-text" aria-label="返回工作台"><ArrowLeft size={17} /></button><button type="button" onClick={() => navigate(`/workspace/projects/${workspace.project.id}?view=overview`)} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink text-xs font-bold text-white" aria-label="打开项目概览" title="项目概览">{workspace.project.initial}</button><strong title={workspace.project.name} className="max-w-[420px] truncate text-sm font-semibold text-text">{workspace.project.name}</strong></div>
          <div className="flex items-center gap-2 rounded-full bg-canvas px-3 py-1.5 text-xs text-muted"><FileText size={13} /><span>脚本编排</span><i className="h-1 w-1 rounded-full bg-line" /><strong className="flex items-center gap-1 font-medium text-teal"><span className="h-1.5 w-1.5 rounded-full bg-teal" />实时预览</strong></div>
          <div className="flex items-center justify-end gap-2">{hasMeaningfulScript ? <details className="relative"><summary aria-label="更多项目操作" className="grid h-9 w-9 cursor-pointer list-none place-items-center rounded-lg border border-line bg-white text-muted hover:border-blue/40 hover:text-blue"><MoreHorizontal size={15} /></summary><div className="absolute right-0 top-11 z-40 w-48 rounded-xl border border-line bg-white p-1.5 shadow-xl"><button type="button" disabled={operationMutation.isPending} onClick={(event) => { (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); setOperationError(null); setAiScriptOpen(true); }} className="flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-xs text-amber hover:bg-amber/5 disabled:opacity-45"><WandSparkles size={14} className="mt-0.5 shrink-0" /><span><strong className="block font-medium">AI 重写全片…</strong><small className="mt-0.5 block text-[9px] leading-4 text-muted">将生成新结构并替换现有场景</small></span></button></div></details> : <button type="button" disabled={operationMutation.isPending} onClick={() => { setOperationError(null); setAiScriptOpen(true); }} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-xs font-medium text-text hover:border-blue/40 hover:text-blue disabled:opacity-45"><WandSparkles size={14} />AI 写脚本</button>}<div ref={addAssetMenuRef} className="relative"><button type="button" aria-expanded={addAssetMenuOpen} onClick={() => setAddAssetMenuOpen((open) => !open)} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-xs font-medium text-text hover:border-blue/40 hover:text-blue"><ImagePlus size={14} />添加素材<ChevronDown size={12} /></button>{addAssetMenuOpen && <div className="absolute right-0 top-11 z-40 w-44 overflow-hidden rounded-xl border border-line bg-white p-1.5 shadow-xl"><button type="button" onClick={() => { setAddAssetMenuOpen(false); setAssetPickerOpen(true); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-text hover:bg-canvas"><Library size={14} className="text-muted" />从素材库添加</button><button type="button" onClick={() => { setAddAssetMenuOpen(false); openUploadDrawer(workspace.project.id); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-text hover:bg-canvas"><CloudUpload size={14} className="text-muted" />上传新素材</button></div>}</div><span className={`ml-1 flex items-center gap-1.5 text-xs ${saveTone}`}>{store.saveState === "saving" ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}{saveLabels[store.saveState]}</span><ProjectTaskButton projectId={workspace.project.id} submittedJobs={submittedJobs} open={taskPanelOpen} onOpen={() => setTaskPanelOpen(true)} /><button type="button" onClick={openExportDialog} disabled={operationMutation.isPending} className="flex items-center gap-1.5 rounded-lg bg-blue px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"><Download size={14} />导出</button></div>
        </div>
        {(store.saveError || operationError) && <div className="mt-2 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{store.saveError ?? operationError}{store.saveState === "conflict" && <button type="button" onClick={() => void store.reloadServer()} className="ml-auto font-semibold underline">重新加载服务器版本</button>}</div>}
      </header>

      {startGuide && <div className="flex shrink-0 items-center gap-3 border-b border-blue/15 bg-blue-soft px-5 py-2.5"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white text-blue"><Sparkles size={15} /></span><div className="min-w-0 flex-1"><strong className="block text-xs text-text">{startGuide.title}</strong><p className="mt-0.5 text-[11px] text-muted">{startGuide.copy}</p></div>{startMethod === "upload-assets" && <button type="button" onClick={() => openUploadDrawer(workspace.project.id)} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white"><CloudUpload size={13} />上传项目素材</button>}<button type="button" onClick={() => navigate(`/workspace/projects/${workspace.project.id}`, { replace: true })} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-white" aria-label="关闭创建提示"><X size={14} /></button></div>}
      {store.undo && <div className="flex shrink-0 items-center gap-3 border-b border-blue/15 bg-blue-soft px-5 py-2 text-xs text-text">已删除{store.undo.label}，可在 {new Date(store.undo.expiresAt).toLocaleTimeString()} 前撤销。<button type="button" onClick={() => void store.undoDelete()} className="ml-auto flex items-center gap-1 font-semibold text-blue"><RotateCcw size={13} />撤销</button></div>}

      <MvpScriptComposer
        workspace={workspace}
        selectedScene={selectedScene}
        selectedShot={selectedShot}
        operationPending={operationMutation.isPending}
        onSelectScene={store.selectScene}
        onSelectShot={store.selectShot}
        onUpdateDocumentSettings={store.updateDocumentSettings}
        onApplyGlobalColorGrade={store.applyGlobalColorGrade}
        onUpdateProject={store.updateProject}
        onUpdateScene={store.updateScene}
        onMoveScene={store.moveScene}
        onUpdateShot={store.updateShot}
        onSplitShot={store.splitShot}
        onRemoveShotAsset={store.removeShotAsset}
        onDuplicateShot={store.duplicateShot}
        onRestoreSubtitle={store.restoreDerivedSubtitle}
        onAddScene={store.addScene}
        onAddShot={store.addShot}
        onDeleteScene={() => void deleteScene()}
        onDeleteShot={() => void deleteShot()}
        onRunOperation={(operation, parameters, scope) => operationMutation.mutate({ operation, parameters, scope })}
        onOpenQuickAI={(scope, kind) => openQuickAI(scope, kind)}
        onOpenVoiceover={() => { setOperationError(null); setVoiceoverOpen(true); }}
        onApplyVoiceoverMaster={applyGeneratedVoiceoverMaster}
      />
      {taskPanel}
      {exportOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="export-dialog-title"><section className="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-white shadow-2xl"><header className="flex items-start justify-between border-b border-line px-5 py-4"><div className="flex gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><Download size={17} /></span><div><h2 id="export-dialog-title" className="text-sm font-semibold text-text">导出主成片</h2><p className="mt-1 text-[11px] leading-5 text-muted">一个项目对应一支主成片，导出时可以适配其他画幅。</p></div></div><button type="button" aria-label="关闭导出设置" onClick={() => setExportOpen(false)} disabled={operationMutation.isPending} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={15} /></button></header><div className="space-y-5 px-5 py-5"><fieldset><legend className="text-xs font-semibold text-text">导出画幅</legend><div className="mt-2 grid grid-cols-2 gap-2">{["16:9", "9:16", "1:1", "4:3"].map((aspectRatio) => <button key={aspectRatio} type="button" onClick={() => setExportAspectRatio(aspectRatio)} className={`rounded-lg border px-3 py-2 text-xs font-medium ${exportAspectRatio === aspectRatio ? "border-blue bg-blue-soft text-blue" : "border-line text-muted hover:border-blue/40"}`}>{aspectRatio}</button>)}</div></fieldset><fieldset><legend className="text-xs font-semibold text-text">清晰度</legend><div className="mt-2 grid grid-cols-2 gap-2">{[["1080p", "1080P"], ["4k", "4K"]].map(([value, label]) => <button key={value} type="button" onClick={() => setExportResolution(value)} className={`rounded-lg border px-3 py-2 text-xs font-medium ${exportResolution === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted hover:border-blue/40"}`}>{label}</button>)}</div></fieldset><div className="rounded-xl bg-canvas px-4 py-3"><strong className="block truncate text-xs text-text">{workspace.project.name}</strong><span className="mt-1 block text-[11px] text-muted">{Math.round(workspace.document.timeline.durationMs / 1000)} 秒 · MP4 · {exportAspectRatio} · {exportResolution === "4k" ? "4K" : "1080P"} · 自动适配字幕安全区</span></div></div><footer className="flex justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-4"><button type="button" onClick={() => setExportOpen(false)} disabled={operationMutation.isPending} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="button" onClick={() => operationMutation.mutate({ operation: "export", parameters: { format: "mp4", resolution: exportResolution, aspect_ratio: exportAspectRatio } })} disabled={operationMutation.isPending || workspace.project.id === "__preview__"} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{operationMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}{workspace.project.id === "__preview__" ? "预览模式" : operationMutation.isPending ? "正在创建任务…" : "开始导出"}</button></footer></section></div>}
      <AIScriptGeneratorModal open={aiScriptOpen} projectName={workspace.project.name} existingSceneCount={hasMeaningfulScript ? workspace.document.storyboard.scenes.length : 0} pending={operationMutation.isPending} error={operationError} onClose={() => !operationMutation.isPending && setAiScriptOpen(false)} onGenerate={(request: AIScriptRequest) => operationMutation.mutate({ operation: "generate_script", parameters: request })} />
      <QuickAIGenerateModal open={quickAIOpen} projectName={workspace.project.name} scenes={workspace.document.storyboard.scenes} selectedScene={selectedScene} selectedShot={selectedShot} initialKind={quickAIKind} initialScope={quickAIScope} pending={operationMutation.isPending} error={operationError} onClose={() => !operationMutation.isPending && setQuickAIOpen(false)} onGenerate={(operation, scope, parameters) => operationMutation.mutate({ operation, scope, parameters })} />
      <AIVoiceoverModal open={voiceoverOpen} projectId={workspace.project.id} scenes={workspace.document.storyboard.scenes} selectedScene={selectedScene} selectedShot={selectedShot} pending={operationMutation.isPending} error={operationError} onClose={() => !operationMutation.isPending && setVoiceoverOpen(false)} onGenerate={(scope, parameters) => operationMutation.mutate({ operation: "generate_voiceover", scope, parameters })} />
      <ProjectAssetPickerModal open={assetPickerOpen} projectId={workspace.project.id} linkedAssetIds={workspace.linkedAssets.map((asset) => asset.id)} onClose={() => setAssetPickerOpen(false)} onAdded={async () => { await store.reloadServer(); notify("素材已添加到项目"); }} />
    </div>
  );
}
