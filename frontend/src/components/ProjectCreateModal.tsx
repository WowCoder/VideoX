// ──────────────────────────────────────────────
// OpenVMA - 新建项目弹窗
// 名称、描述、项目类型选择(下拉)
// ──────────────────────────────────────────────

import { useEffect, useState } from "react";
import { useNavigate } from "@/router";
import { ArrowRight, FolderKanban, Loader2, X } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import type { ThumbnailVariant } from "@/types/models";

interface Template {
  id: string;
  label: string;
  description: string;
  variant: ThumbnailVariant;
}

const templates: Template[] = [
  { id: "tech-launch", label: "AI 科技 / 产品讲解", description: "适合发布会、产品演示与科技品牌内容", variant: "robot" },
  { id: "brand-interview", label: "品牌访谈", description: "客户故事、人物访谈与品牌叙事", variant: "interview" },
  { id: "enterprise-event", label: "企业活动", description: "工厂参观、年会与线下活动记录", variant: "hall" },
  { id: "social-short", label: "社媒短视频", description: "竖屏快剪、预告片与传播向内容", variant: "lights" },
  { id: "blank", label: "空白项目", description: "从零开始组织素材、脚本与初剪", variant: "stage" },
];

export function ProjectCreateModal() {
  const { projectCreateOpen, closeProjectCreate, notify } = useUIStore();
  const createProject = useProjectStore((s) => s.createProject);
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState(templates[0].id);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (projectCreateOpen) {
      setName("");
      setDescription("");
      setTemplateId(templates[0].id);
      setSubmitting(false);
    }
  }, [projectCreateOpen]);

  if (!projectCreateOpen) return null;

  const selectedTemplate = templates.find((t) => t.id === templateId) ?? templates[0];

  async function handleCreate() {
    if (!name.trim()) {
      notify("请输入项目名称", "error");
      return;
    }
    setSubmitting(true);
    try {
      const project = await createProject({
        name: name.trim(),
        type: selectedTemplate.label,
        description: description.trim() || selectedTemplate.description,
        variant: selectedTemplate.variant,
      });
      notify(`项目"${project.name}"已创建`);
      closeProjectCreate();
      navigate(`/workspace/projects/${project.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建项目失败，请稍后重试";
      notify(message, "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        className="absolute inset-0 cursor-default bg-ink/60 backdrop-blur-sm"
        onClick={closeProjectCreate}
        aria-label="关闭"
        type="button"
      />

      <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-2xl bg-surface shadow-soft">
        {/* 头部 */}
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-soft text-blue">
              <FolderKanban size={17} />
            </span>
            <h2 className="text-base font-semibold text-text">新建项目</h2>
          </div>
          <button
            onClick={closeProjectCreate}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        <div className="space-y-5 p-6">
          {/* 名称 */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-text">项目名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：智能机器人发布会"
              className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-text">项目描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简单描述这个项目的目标与内容（选填）"
              rows={3}
              className="w-full resize-none rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
            />
          </div>

          {/* 项目类型 */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-text">项目类型</label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="mt-2 rounded-lg bg-canvas/60 px-3 py-2 text-xs leading-relaxed text-muted">
              {selectedTemplate.description}。项目类型仅用于分类、默认描述与预览样式，不会自动生成脚本或素材。
            </p>
          </div>
        </div>

        {/* 底部操作 */}
        <footer className="flex items-center justify-end gap-2 border-t border-line px-6 py-4">
          <button
            onClick={closeProjectCreate}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:bg-canvas"
            type="button"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={submitting}
            className="flex items-center gap-1.5 rounded-lg bg-blue px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-2 disabled:opacity-60"
            type="button"
          >
            {submitting ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <>
                创建项目<ArrowRight size={15} />
              </>
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}

export default ProjectCreateModal;
