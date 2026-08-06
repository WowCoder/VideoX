import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";

import type { DeleteImpact } from "@/api/deletion";
import { Modal } from "@/components/ui/Modal";

interface Props {
  open: boolean;
  entityLabel: "项目" | "素材" | "脚本";
  requireName?: boolean;
  loadImpact: () => Promise<DeleteImpact>;
  onDelete: () => Promise<void>;
  onClose: () => void;
  onDeleted: () => void;
}

const COUNT_LABELS: Record<string, string> = {
  assets: "素材",
  scripts: "脚本",
  jobs: "历史任务",
  clips: "识别片段",
  units: "脚本单元",
  project_media_items: "项目媒体项",
  linked_projects: "关联剪辑项目",
  timeline_references: "时间线引用",
  script_unit_references: "脚本单元引用",
  shot_references: "分镜引用",
  candidate_references: "候选镜头引用",
  project_media_references: "素材箱引用",
  active_jobs: "进行中任务",
  snapshots: "初剪快照",
  external_asset_references: "外部素材引用",
};

export function DeleteConfirmModal({
  open,
  entityLabel,
  requireName = false,
  loadImpact,
  onDelete,
  onClose,
  onDeleted,
}: Props) {
  const [impact, setImpact] = useState<DeleteImpact | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadImpactRef = useRef(loadImpact);

  useEffect(() => {
    loadImpactRef.current = loadImpact;
  }, [loadImpact]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setImpact(null);
    setConfirmation("");
    setError(null);
    setLoading(true);
    void loadImpactRef.current()
      .then((result) => {
        if (!cancelled) setImpact(result);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "删除影响检查失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const confirmed = Boolean(
    impact?.canDelete && (!requireName || confirmation.trim() === impact.name),
  );

  const performDelete = async () => {
    if (!confirmed) return;
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
      onDeleted();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `删除${entityLabel}失败`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`删除${entityLabel}`}
      maskClosable={!deleting}
      footer={(
        <>
          <button type="button" onClick={onClose} disabled={deleting} className="rounded-lg border border-line px-3 py-2 text-sm text-muted hover:bg-canvas">
            取消
          </button>
          <button
            type="button"
            onClick={() => void performDelete()}
            disabled={!confirmed || deleting}
            className="flex items-center gap-1.5 rounded-lg bg-red px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            {deleting ? "正在删除…" : `确认删除${entityLabel}`}
          </button>
        </>
      )}
    >
      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-blue" /></div>
      ) : error ? (
        <div className="rounded-lg border border-red/20 bg-red/5 p-3 text-sm text-red">{error}</div>
      ) : impact ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-red/20 bg-red/5 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red" />
              <div>
                <div className="font-medium text-text">{impact.name}</div>
                <p className="mt-1 text-sm text-muted">
                  {impact.canDelete
                    ? `删除后该${entityLabel}及其独占文件无法恢复。`
                    : `当前${entityLabel}仍有依赖，不能删除。`}
                </p>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(impact.counts)
              .filter(([, value]) => value > 0)
              .map(([key, value]) => (
                <div key={key} className="rounded-lg bg-canvas px-3 py-2 text-sm">
                  <span className="text-muted">{COUNT_LABELS[key] ?? key}</span>
                  <strong className="float-right text-text">{value}</strong>
                </div>
              ))}
          </div>
          {impact.blockers.length > 0 && (
            <ul className="space-y-1 rounded-lg border border-amber/20 bg-amber/5 p-3 text-sm text-amber">
              {impact.blockers.map((blocker) => <li key={blocker}>• {blocker}</li>)}
            </ul>
          )}
          {requireName && impact.canDelete && (
            <label className="block text-sm text-text">
              请输入 <strong>{impact.name}</strong> 确认删除
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                className="mt-2 w-full rounded-lg border border-line bg-canvas px-3 py-2"
                autoComplete="off"
              />
            </label>
          )}
        </div>
      ) : null}
    </Modal>
  );
}

export default DeleteConfirmModal;
