import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Loader2, Sparkles, X } from "lucide-react";
import { useNavigate } from "@/router";
import * as projectApi from "@/api/projects";
import { useUIStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { temporaryId } from "@/stores/workspaceTransforms";

function ModalFrame({ title, description, busy, onClose, children, footer }: {
  title: string;
  description: string;
  busy: boolean;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭弹窗" disabled={busy} onClick={onClose} className="absolute inset-0 cursor-default bg-ink/55 backdrop-blur-sm disabled:cursor-wait" />
      <section role="dialog" aria-modal="true" aria-labelledby="project-modal-title" className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_28px_80px_rgba(0,0,0,.22)]">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><Sparkles size={19} /></span>
          <div className="min-w-0 flex-1"><h2 id="project-modal-title" className="text-base font-semibold text-text">{title}</h2><p className="mt-1 text-xs leading-5 text-muted">{description}</p></div>
          <button type="button" aria-label="关闭" disabled={busy} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>
        <div className="overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-canvas/50 px-5 py-4 sm:px-6">{footer}</footer>
      </section>
    </div>
  );
}

function ProjectNameField({ name, onChange, submitted }: { name: string; onChange: (name: string) => void; submitted: boolean }) {
  return (
    <label className="block text-sm font-medium text-text">项目名称
      <input autoFocus value={name} maxLength={200} onChange={(event) => onChange(event.target.value)} placeholder="例如：2026 秋季新品发布" aria-invalid={submitted && !name.trim()} className={`mt-2 w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm text-text focus:ring-2 focus:ring-blue/10 ${submitted && !name.trim() ? "border-red" : "border-line focus:border-blue/50"}`} />
      {submitted && !name.trim() && <span className="mt-1.5 block text-xs font-normal text-red">请输入项目名称</span>}
    </label>
  );
}

function BlankProjectModal() {
  const { closeProjectCreate, notify } = useUIStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  async function createBlank(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const workspace = await projectApi.create({
        name: name.trim(),
        type: "空白项目",
        description: "",
        variant: "stage",
        scriptTitle: name.trim(),
        idempotencyKey: temporaryId("project-request"),
      });
      useWorkspaceStore.getState().hydrate(workspace);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
      ]);
      closeProjectCreate();
      notify(`空白项目“${workspace.project.name}”已创建`);
      navigate(`/workspace/projects/${workspace.project.id}?start=blank`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "创建项目失败", "error");
    } finally {
      setBusy(false);
    }
  }

  const footer = <><button type="button" disabled={busy} onClick={closeProjectCreate} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text">取消</button><button form="blank-project-form" type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? <Loader2 size={14} className="animate-spin" /> : <FolderPlus size={14} />}{busy ? "正在创建…" : "创建空白项目"}</button></>;
  return <ModalFrame title="创建空白项目" description="仅创建项目空间，不预设脚本、分镜或素材。其他创作方式请从工作台开始。" busy={busy} onClose={closeProjectCreate} footer={footer}><form id="blank-project-form" onSubmit={createBlank}><ProjectNameField name={name} onChange={setName} submitted={submitted} /></form></ModalFrame>;
}

function ProjectEditModal() {
  const { projectEditing, closeProjectCreate, notify } = useUIStore();
  const queryClient = useQueryClient();
  const [name, setName] = useState(projectEditing?.name ?? "");
  const [description, setDescription] = useState(projectEditing?.description ?? "");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setName(projectEditing?.name ?? "");
    setDescription(projectEditing?.description ?? "");
  }, [projectEditing]);

  if (!projectEditing) return null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!name.trim() || busy || !projectEditing) return;
    setBusy(true);
    try {
      await projectApi.update(projectEditing.id, { name: name.trim(), description: description.trim() });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      closeProjectCreate();
      notify(`项目“${name.trim()}”已更新`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "项目信息保存失败", "error");
    } finally {
      setBusy(false);
    }
  }

  const footer = <><button type="button" disabled={busy} onClick={closeProjectCreate} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text">取消</button><button form="project-edit-form" type="submit" disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy && <Loader2 size={14} className="animate-spin" />}{busy ? "正在保存…" : "保存修改"}</button></>;
  return <ModalFrame title="编辑项目信息" description="更新影片名称和项目说明。" busy={busy} onClose={closeProjectCreate} footer={footer}><form id="project-edit-form" onSubmit={save} className="space-y-5"><ProjectNameField name={name} onChange={setName} submitted={submitted} /><label className="block text-sm font-medium text-text">项目说明 <span className="font-normal text-muted">可选</span><textarea rows={5} maxLength={5000} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="说明内容目标、素材范围或制作要求" className="mt-2 w-full resize-y rounded-xl border border-line p-3 text-sm leading-6 text-text focus:border-blue/50 focus:ring-2 focus:ring-blue/10" /></label></form></ModalFrame>;
}

export function ProjectCreateModal() {
  const { projectCreateOpen, projectEditing } = useUIStore();
  if (!projectCreateOpen) return null;
  if (projectEditing) return <ProjectEditModal />;
  return <BlankProjectModal />;
}

export default ProjectCreateModal;
