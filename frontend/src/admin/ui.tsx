/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  FormEvent,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { CheckCircle2, CircleAlert, LoaderCircle, X } from "lucide-react";

export type ToastTone = "success" | "error";

type Toast = { id: number; text: string; tone: ToastTone };
type ToastContextValue = { notify: (text: string, tone?: ToastTone) => void };

const ToastContext = createContext<ToastContextValue | null>(null);

export function AdminToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const value = useMemo<ToastContextValue>(() => ({
    notify: (text, tone = "success") => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((items) => [...items, { id, text, tone }]);
      window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 4200);
    },
  }), []);
  return <ToastContext.Provider value={value}>
    {children}
    <div className="admin-toast-stack" aria-live="polite">
      {toasts.map((toast) => <div className={`admin-toast ${toast.tone}`} key={toast.id} role="status">
        {toast.tone === "success" ? <CheckCircle2 size={17}/> : <CircleAlert size={17}/>}<span>{toast.text}</span>
        <button type="button" aria-label="关闭提示" onClick={() => setToasts((items) => items.filter((item) => item.id !== toast.id))}><X size={15}/></button>
      </div>)}
    </div>
  </ToastContext.Provider>;
}

export function useAdminToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useAdminToast must be used inside AdminToastProvider");
  return value;
}

export function Button({
  children,
  tone = "secondary",
  disabled,
  busy,
  type = "button",
  onClick,
}: {
  children: ReactNode;
  tone?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  onClick?: () => void;
}) {
  return <button type={type} className={`admin-button ${tone}`} disabled={disabled || busy} onClick={onClick}>
    {busy && <LoaderCircle size={14} className="spin"/>}{children}
  </button>;
}

export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <section className="admin-panel"><header><h2>{title}</h2>{action}</header>{children}</section>;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const start = total ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(total, page * pageSize);
  return <div className="admin-pagination">
    <span>{start}–{end} / {total}</span>
    <label>每页
      <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
        <option value={20}>20</option><option value={50}>50</option><option value={100}>100</option>
      </select>
    </label>
    <Button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>上一页</Button>
    <b>{page} / {pages}</b>
    <Button disabled={page >= pages} onClick={() => onPageChange(page + 1)}>下一页</Button>
  </div>;
}

export function FormField({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return <label className="admin-form-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

export function ActionDialog({
  title,
  description,
  target,
  warning,
  confirmText = "确认提交",
  confirmPhrase,
  tone = "primary",
  children,
  onClose,
  onSubmit,
}: {
  title: string;
  description: string;
  target?: string;
  warning?: string;
  confirmText?: string;
  confirmPhrase?: string;
  tone?: "primary" | "danger";
  children?: ReactNode;
  onClose: () => void;
  onSubmit: (values: Record<string, string>) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [busy, onClose]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true); setError("");
    const values = Object.fromEntries(new FormData(event.currentTarget).entries()) as Record<string, string>;
    try { await onSubmit(values); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
    finally { setBusy(false); }
  };
  return <div className="admin-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section className="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-action-title">
      <header><div><p className="eyebrow">SECURE ACTION</p><h2 id="admin-action-title">{title}</h2></div><button type="button" aria-label="关闭" disabled={busy} onClick={onClose}><X/></button></header>
      <form onSubmit={submit}>
        <div className="admin-modal-body">
          <p className="admin-modal-description">{description}</p>
          {target && <div className="admin-action-target"><span>操作对象</span><code>{target}</code></div>}
          {warning && <div className="admin-action-warning"><CircleAlert size={17}/><span>{warning}</span></div>}
          {children}
          <FormField label="操作原因" hint="至少 3 个字符，将完整写入管理员审计日志。">
            <textarea name="reason" minLength={3} maxLength={2000} required placeholder="说明业务背景和执行理由"/>
          </FormField>
          {confirmPhrase && <FormField label="二次确认" hint={<>请输入 <code>{confirmPhrase}</code> 后继续。</>}>
            <input name="confirmation" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required/>
          </FormField>}
          {error && <div className="admin-error"><CircleAlert size={16}/>{error}</div>}
        </div>
        <footer><Button disabled={busy} onClick={onClose}>取消</Button><Button type="submit" tone={tone} busy={busy} disabled={Boolean(confirmPhrase && confirmation !== confirmPhrase)}>{confirmText}</Button></footer>
      </form>
    </section>
  </div>;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ChangeSummary({ before, after }: { before: Record<string, unknown>; after: Record<string, unknown> }) {
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})]));
  if (!keys.length) return <div className="admin-empty compact">该操作没有记录字段差异</div>;
  return <div className="audit-diff">
    {keys.map((key) => {
      const previous = displayValue(before?.[key]);
      const next = displayValue(after?.[key]);
      return <div key={key} className={previous === next ? "unchanged" : "changed"}>
        <span>{key.replaceAll("_", " ")}</span><div><code>{previous}</code><b>→</b><code>{next}</code></div>
      </div>;
    })}
  </div>;
}
