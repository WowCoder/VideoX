import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CloudUpload,
  Download,
  FileText,
  ImagePlus,
  Loader2,
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
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const store = useWorkspaceStore();
  const [scopeType] = useState<OperationScope["type"]>("shot");
  const [operationError, setOperationError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportAspectRatio, setExportAspectRatio] = useState("16:9");
  const [exportResolution, setExportResolution] = useState("1080p");
  const [aiScriptOpen, setAiScriptOpen] = useState(
    () => new URLSearchParams(location.search).get("start") === "ai-script",
  );
  const mountedRef = useRef(true);

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
    mutationFn: async ({ operation, parameters = {} }: { operation: ProjectOperation; parameters?: Record<string, unknown> }) => {
      if (!workspace) throw new Error("项目尚未加载");
      await store.save("before_ai_operation");
      const currentState = useWorkspaceStore.getState();
      const current = currentState.workspace;
      if (!current) throw new Error("项目尚未加载");
      const currentScene = current.document.storyboard.scenes.find((scene) => scene.id === currentState.selectedSceneId)
        ?? current.document.storyboard.scenes[0];
      const currentShot = currentScene?.shots.find((shot) => shot.id === currentState.selectedShotId)
        ?? currentScene?.shots[0];
      const operationScope: OperationScope = ["compose", "export", "match_assets", "generate_script"].includes(operation)
        ? { type: "project" }
        : scopeType === "scene" && currentScene?.id
          ? { type: "scene", sceneIds: [currentScene.id] }
          : scopeType === "shot" && currentShot?.id
            ? { type: "shot", shotIds: [currentShot.id] }
            : { type: "project" };
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
      notify(`${operationLabels[variables.operation]}已创建 ${jobs.length} 个任务`);
      if (variables.operation === "generate_script" && jobs[0]) {
        void refreshWhenScriptJobFinishes(jobs[0].id);
      }
      await store.reloadServer();
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "操作失败";
      setOperationError(message);
      notify(message, "error");
    },
  });

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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-canvas">
      <header className="relative z-20 shrink-0 border-b border-line bg-surface/95 px-4 py-2.5 backdrop-blur-xl">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="flex min-w-0 items-center gap-3"><button type="button" onClick={() => navigate("/workspace")} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted hover:bg-canvas hover:text-text" aria-label="返回工作台"><ArrowLeft size={17} /></button><button type="button" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink text-xs font-bold text-white" aria-label="当前项目">{workspace.project.initial}</button><label className="min-w-0"><span className="sr-only">影片名称</span><input value={workspace.project.name} onChange={(event) => store.updateProject({ name: event.target.value })} className="w-full min-w-[180px] bg-transparent text-sm font-semibold text-text outline-none" aria-label="影片名称" /></label></div>
          <div className="flex items-center gap-2 rounded-full bg-canvas px-3 py-1.5 text-xs text-muted"><FileText size={13} /><span>脚本编排</span><i className="h-1 w-1 rounded-full bg-line" /><strong className="flex items-center gap-1 font-medium text-teal"><span className="h-1.5 w-1.5 rounded-full bg-teal" />实时预览</strong></div>
          <div className="flex items-center justify-end gap-3"><span className={`flex items-center gap-1.5 text-xs ${saveTone}`}>{store.saveState === "saving" ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}{saveLabels[store.saveState]}</span><button type="button" onClick={openExportDialog} disabled={operationMutation.isPending} className="flex items-center gap-1.5 rounded-lg bg-blue px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"><Download size={14} />导出</button></div>
        </div>
        {(store.saveError || operationError) && <div className="mt-2 flex items-center gap-2 rounded-lg bg-red/5 px-3 py-2 text-xs text-red"><AlertTriangle size={14} />{store.saveError ?? operationError}{store.saveState === "conflict" && <button type="button" onClick={() => void store.reloadServer()} className="ml-auto font-semibold underline">重新加载服务器版本</button>}</div>}
      </header>

      {startGuide && <div className="flex shrink-0 items-center gap-3 border-b border-blue/15 bg-blue-soft px-5 py-2.5"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white text-blue"><Sparkles size={15} /></span><div className="min-w-0 flex-1"><strong className="block text-xs text-text">{startGuide.title}</strong><p className="mt-0.5 text-[11px] text-muted">{startGuide.copy}</p></div>{startMethod === "upload-assets" && <button type="button" onClick={() => openUploadDrawer(workspace.project.id)} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white"><CloudUpload size={13} />上传项目素材</button>}<button type="button" onClick={() => navigate(`/workspace/projects/${workspace.project.id}`, { replace: true })} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-white" aria-label="关闭创建提示"><X size={14} /></button></div>}
      {store.undo && <div className="flex shrink-0 items-center gap-3 border-b border-blue/15 bg-blue-soft px-5 py-2 text-xs text-text">已删除{store.undo.label}，可在 {new Date(store.undo.expiresAt).toLocaleTimeString()} 前撤销。<button type="button" onClick={() => void store.undoDelete()} className="ml-auto flex items-center gap-1 font-semibold text-blue"><RotateCcw size={13} />撤销</button></div>}
      <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-line bg-white px-4 py-2"><span className="mr-auto hidden whitespace-nowrap text-[11px] text-muted md:block">脚本、镜头、素材与声音共同驱动实时成片</span><button type="button" disabled={operationMutation.isPending} onClick={() => { setOperationError(null); setAiScriptOpen(true); }} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-blue px-3 py-2 text-xs font-semibold text-white disabled:opacity-45"><WandSparkles size={14} />AI 写脚本</button><button type="button" onClick={() => openUploadDrawer(workspace.project.id)} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-medium text-text"><ImagePlus size={14} />导入素材分析</button></div>

      <MvpScriptComposer
        workspace={workspace}
        selectedScene={selectedScene}
        selectedShot={selectedShot}
        operationPending={operationMutation.isPending}
        onSelectScene={store.selectScene}
        onSelectShot={store.selectShot}
        onUpdateDocumentSettings={store.updateDocumentSettings}
        onUpdateGlobalScope={store.updateGlobalScope}
        onUpdateScene={store.updateScene}
        onMoveScene={store.moveScene}
        onUpdateShot={store.updateShot}
        onMoveShot={store.moveShot}
        onSplitShot={store.splitShot}
        onRemoveShotAsset={store.removeShotAsset}
        onDuplicateShot={store.duplicateShot}
        onRestoreSubtitle={store.restoreDerivedSubtitle}
        onAddScene={store.addScene}
        onAddShot={store.addShot}
        onDeleteScene={() => void deleteScene()}
        onDeleteShot={() => void deleteShot()}
        onUpload={() => openUploadDrawer(workspace.project.id)}
        onRunOperation={(operation) => operationMutation.mutate({ operation })}
      />
      {exportOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="export-dialog-title"><section className="w-full max-w-md overflow-hidden rounded-2xl border border-line bg-white shadow-2xl"><header className="flex items-start justify-between border-b border-line px-5 py-4"><div className="flex gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><Download size={17} /></span><div><h2 id="export-dialog-title" className="text-sm font-semibold text-text">导出主成片</h2><p className="mt-1 text-[11px] leading-5 text-muted">一个项目对应一支主成片，导出时可以适配其他画幅。</p></div></div><button type="button" aria-label="关闭导出设置" onClick={() => setExportOpen(false)} disabled={operationMutation.isPending} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={15} /></button></header><div className="space-y-5 px-5 py-5"><fieldset><legend className="text-xs font-semibold text-text">导出画幅</legend><div className="mt-2 grid grid-cols-3 gap-2">{["16:9", "9:16", "1:1"].map((aspectRatio) => <button key={aspectRatio} type="button" onClick={() => setExportAspectRatio(aspectRatio)} className={`rounded-lg border px-3 py-2 text-xs font-medium ${exportAspectRatio === aspectRatio ? "border-blue bg-blue-soft text-blue" : "border-line text-muted hover:border-blue/40"}`}>{aspectRatio}</button>)}</div></fieldset><fieldset><legend className="text-xs font-semibold text-text">清晰度</legend><div className="mt-2 grid grid-cols-2 gap-2">{[["1080p", "1080P"], ["4k", "4K"]].map(([value, label]) => <button key={value} type="button" onClick={() => setExportResolution(value)} className={`rounded-lg border px-3 py-2 text-xs font-medium ${exportResolution === value ? "border-blue bg-blue-soft text-blue" : "border-line text-muted hover:border-blue/40"}`}>{label}</button>)}</div></fieldset><div className="rounded-xl bg-canvas px-4 py-3"><strong className="block truncate text-xs text-text">{workspace.project.name}</strong><span className="mt-1 block text-[11px] text-muted">{Math.round(workspace.document.timeline.durationMs / 1000)} 秒 · MP4 · {exportAspectRatio} · {exportResolution === "4k" ? "4K" : "1080P"} · 自动适配字幕安全区</span></div></div><footer className="flex justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-4"><button type="button" onClick={() => setExportOpen(false)} disabled={operationMutation.isPending} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="button" onClick={() => operationMutation.mutate({ operation: "export", parameters: { format: "mp4", resolution: exportResolution, aspect_ratio: exportAspectRatio } })} disabled={operationMutation.isPending || workspace.project.id === "__preview__"} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{operationMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}{workspace.project.id === "__preview__" ? "预览模式" : operationMutation.isPending ? "正在创建任务…" : "开始导出"}</button></footer></section></div>}
      <AIScriptGeneratorModal open={aiScriptOpen} projectName={workspace.project.name} existingSceneCount={workspace.document.storyboard.scenes.length} pending={operationMutation.isPending} error={operationError} onClose={() => !operationMutation.isPending && setAiScriptOpen(false)} onGenerate={(request: AIScriptRequest) => operationMutation.mutate({ operation: "generate_script", parameters: request })} />
    </div>
  );
}
