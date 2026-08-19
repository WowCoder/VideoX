import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  FileText,
  FolderKanban,
  FolderPlus,
  Images,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { useNavigate } from "@/router";
import { useUIStore, type ProjectStartMethod } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import * as projectApi from "@/api/projects";
import type { AspectRatio } from "@/api/projects";
import { temporaryId } from "@/stores/workspaceTransforms";

interface StartMethod {
  id: ProjectStartMethod;
  label: string;
  description: string;
  result: string;
  projectType: string;
  variant: string;
  icon: typeof FileText;
}

const startMethods: StartMethod[] = [
  {
    id: "write-script",
    label: "从脚本开始",
    description: "先在项目中整理脚本、场景与镜头，再匹配或生成画面",
    result: "进入后先编写场景与旁白",
    projectType: "脚本创作",
    variant: "stage",
    icon: FileText,
  },
  {
    id: "upload-assets",
    label: "从素材开始",
    description: "创建后立即上传并关联图片、音频或视频素材",
    result: "进入后自动打开素材上传",
    projectType: "素材编排",
    variant: "hall",
    icon: Images,
  },
  {
    id: "ai-script",
    label: "AI 辅助脚本",
    description: "进入项目后从脚本结构开始，按需使用 AI 完善镜头",
    result: "进入脚本编排与 AI 操作区",
    projectType: "AI 辅助脚本",
    variant: "robot",
    icon: Sparkles,
  },
  {
    id: "blank",
    label: "空白项目",
    description: "只创建项目空间，稍后再补充脚本和素材",
    result: "不预设脚本或素材",
    projectType: "空白项目",
    variant: "stage",
    icon: FolderPlus,
  },
];

const aspectRatios: AspectRatio[] = ["16:9", "9:16", "1:1", "4:3"];

export function ProjectCreateModal() {
  const {
    projectCreateOpen,
    projectCreateIntent,
    projectEditing,
    closeProjectCreate,
    openUploadDrawer,
    notify,
  } = useUIStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const editing = Boolean(projectEditing);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startMethod, setStartMethod] = useState<ProjectStartMethod>("blank");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [targetDuration, setTargetDuration] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState("");

  useEffect(() => {
    if (!projectCreateOpen) return;
    setName(projectEditing?.name ?? "");
    setDescription(projectEditing?.description ?? "");
    setStartMethod(projectCreateIntent);
    setAspectRatio("16:9");
    setTargetDuration("");
    setSubmitting(false);
    setSubmitted(false);
    setIdempotencyKey(temporaryId("project-request"));
  }, [projectCreateIntent, projectCreateOpen, projectEditing]);

  if (!projectCreateOpen) return null;

  const selectedMethod = startMethods.find((method) => method.id === startMethod) ?? startMethods[0];
  const hasName = Boolean(name.trim());
  const resolvedTargetDuration = targetDuration.trim() ? Number(targetDuration) : 0;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (!hasName || submitting) return;

    setSubmitting(true);
    try {
      if (projectEditing) {
        await projectApi.update(projectEditing.id, {
          name: name.trim(),
          description: description.trim(),
        });
        await queryClient.invalidateQueries({ queryKey: ["projects"] });
        notify(`项目“${name.trim()}”已更新`);
        closeProjectCreate();
        return;
      }

      const workspace = await projectApi.create({
        name: name.trim(),
        type: selectedMethod.projectType,
        description: "",
        variant: selectedMethod.variant,
        scriptTitle: name.trim(),
        aspectRatio,
        targetDurationSeconds: Number.isFinite(resolvedTargetDuration) ? resolvedTargetDuration : 0,
        idempotencyKey,
      });
      useWorkspaceStore.getState().hydrate(workspace);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
      ]);
      notify(`项目“${workspace.project.name}”已创建`);
      closeProjectCreate();
      navigate(`/workspace/projects/${workspace.project.id}?start=${startMethod}`);
      if (startMethod === "upload-assets") openUploadDrawer(workspace.project.id);
    } catch (error) {
      notify(error instanceof Error ? error.message : editing ? "项目信息保存失败" : "创建项目失败，请稍后重试", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        className="absolute inset-0 cursor-default bg-ink/55 backdrop-blur-sm"
        onClick={() => !submitting && closeProjectCreate()}
        aria-label={editing ? "关闭编辑项目" : "关闭新建项目"}
        type="button"
      />

      <form
        className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-2xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_28px_80px_rgba(0,0,0,.22)]"
        onSubmit={handleSubmit}
        aria-labelledby="project-create-title"
      >
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-blue-soft text-blue">
            <FolderKanban size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="project-create-title" className="text-base font-semibold text-text">
              {editing ? "编辑项目信息" : "新建项目"}
            </h2>
            <p className="mt-1 text-xs leading-5 text-muted">
              {editing ? "更新影片名称和项目说明。" : "选择你已有的内容，并设置这支视频的基本输出目标。"}
            </p>
          </div>
          <button
            onClick={closeProjectCreate}
            disabled={submitting}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-canvas hover:text-text disabled:opacity-40"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        <div className="overflow-y-auto px-5 py-5 sm:px-6">
          <label className="block text-sm font-medium text-text">
            项目名称
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：2026 秋季新品发布"
              maxLength={200}
              autoFocus
              aria-invalid={submitted && !hasName}
              className={`mt-2 w-full rounded-[10px] border bg-surface px-3.5 py-2.5 text-sm text-text transition placeholder:text-[#999a9f] focus:ring-2 focus:ring-black/5 ${submitted && !hasName ? "border-red" : "border-line focus:border-[#a9a9ad]"}`}
            />
            {submitted && !hasName && <span className="mt-1.5 block text-xs font-normal text-red">请输入项目名称</span>}
          </label>

          {!editing && (
            <fieldset className="mt-5">
              <legend className="text-sm font-medium text-text">创作起点</legend>
              <p className="mt-1 text-xs text-muted">已根据你点击的入口预选，创建前仍可修改。</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {startMethods.map((method) => {
                  const Icon = method.icon;
                  const selected = method.id === startMethod;
                  return (
                    <button
                      key={method.id}
                      type="button"
                      onClick={() => setStartMethod(method.id)}
                      aria-pressed={selected}
                      className={`grid min-h-[92px] grid-cols-[38px_minmax(0,1fr)_20px] items-start gap-3 rounded-xl border p-3 text-left transition ${selected ? "border-ink bg-[#f5f5f6] shadow-[inset_0_0_0_1px_#171717]" : "border-line bg-white hover:border-[#bfc0c4] hover:bg-[#fafafa]"}`}
                    >
                      <span className={`grid h-[38px] w-[38px] place-items-center rounded-[10px] ${selected ? "bg-ink text-white" : "bg-canvas text-muted"}`}><Icon size={18} /></span>
                      <span className="min-w-0"><strong className="block text-sm font-semibold text-text">{method.label}</strong><small className="mt-1 block text-xs leading-5 text-muted">{method.description}</small><em className="mt-1.5 block text-[11px] not-italic text-blue">{method.result}</em></span>
                      <span className={`mt-1 grid h-5 w-5 place-items-center rounded-full border ${selected ? "border-ink bg-ink text-white" : "border-[#d6d6d9]"}`}>{selected && <Check size={12} />}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          )}

          {editing ? (
            <label className="block text-sm font-medium text-text">
              项目说明 <span className="font-normal text-muted">可选</span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="说明内容目标、素材范围或制作要求"
                rows={4}
                maxLength={5000}
                className="mt-2 w-full resize-none rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-sm leading-6 text-text transition placeholder:text-[#999a9f] focus:border-[#a9a9ad] focus:ring-2 focus:ring-black/5"
              />
            </label>
          ) : (
            <fieldset className="mt-5">
              <legend className="text-sm font-medium text-text">输出目标</legend>
              <p className="mt-1 text-xs text-muted">这些设置会直接写入项目主成片和脚本，不是展示标签。</p>
              <div className="mt-3 grid gap-4 rounded-xl border border-line bg-[#fafafb] p-4 sm:grid-cols-[minmax(0,1fr)_180px]">
                <div>
                  <span className="text-xs font-medium text-muted">主画幅</span>
                  <div className="mt-2 grid grid-cols-4 gap-2">
                    {aspectRatios.map((ratio) => (
                      <button
                        key={ratio}
                        type="button"
                        onClick={() => setAspectRatio(ratio)}
                        aria-pressed={aspectRatio === ratio}
                        className={`min-h-10 rounded-lg border text-xs font-semibold transition ${aspectRatio === ratio ? "border-ink bg-ink text-white" : "border-line bg-white text-text hover:border-[#bfc0c4]"}`}
                      >
                        {ratio}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="text-xs font-medium text-muted">
                  目标时长 <span className="font-normal">可选</span>
                  <div className="mt-2 flex min-h-10 items-center rounded-lg border border-line bg-white px-3 focus-within:border-[#a9a9ad] focus-within:ring-2 focus-within:ring-black/5">
                    <input
                      type="number"
                      min={5}
                      max={86400}
                      inputMode="numeric"
                      value={targetDuration}
                      onChange={(event) => setTargetDuration(event.target.value)}
                      placeholder="自动推算"
                      className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none"
                      aria-label="目标时长（秒，可选）"
                    />
                    <span className="text-xs text-muted">秒</span>
                  </div>
                </label>
              </div>
            </fieldset>
          )}
        </div>

        <footer className="flex flex-col gap-3 border-t border-line bg-[#fbfbfc] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="text-xs leading-5 text-muted">
            {editing ? "修改后会同步更新工作台和项目页。" : startMethod === "upload-assets" ? "创建成功后将进入项目，并立即打开素材上传。" : "创建成功后将进入对应的创作起点。"}
          </p>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={closeProjectCreate}
              disabled={submitting}
              className="min-h-10 rounded-[9px] border border-line bg-white px-4 text-sm font-medium text-text transition hover:bg-canvas disabled:opacity-50"
              type="button"
            >
              取消
            </button>
            <button
              disabled={submitting || !hasName}
              className="flex min-h-10 items-center gap-1.5 rounded-[9px] bg-ink px-5 text-sm font-semibold text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-45"
              type="submit"
            >
              {submitting ? <><Loader2 size={15} className="animate-spin" />正在保存</> : editing ? "保存修改" : <>创建并进入项目<ArrowRight size={15} /></>}
            </button>
          </div>
        </footer>
      </form>
    </div>
  );
}

export default ProjectCreateModal;
