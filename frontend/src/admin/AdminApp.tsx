import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, BadgeDollarSign, BriefcaseBusiness, ChevronRight, CircleAlert,
  FileText, Gauge, LoaderCircle, LogOut, Search, ShieldCheck, UserRound,
  UsersRound, X,
} from "lucide-react";
import { api, AdminProfile, loginAdmin, logoutAdmin, mutationOptions, restoreAdmin } from "./api/client";

type Data = Record<string, unknown>;
type ListResponse = { items: Data[]; total: number; page: number; page_size: number };
type View = "dashboard" | "users" | "jobs" | "transactions" | "audit";

const NAV: { id: View; label: string; icon: typeof Gauge }[] = [
  { id: "dashboard", label: "工作台", icon: Gauge },
  { id: "users", label: "用户", icon: UsersRound },
  { id: "jobs", label: "任务", icon: BriefcaseBusiness },
  { id: "transactions", label: "交易", icon: BadgeDollarSign },
  { id: "audit", label: "审计", icon: ShieldCheck },
];

const ROLE_NAMES: Record<string, string> = { super_admin: "超级管理员", operator: "运营", finance: "财务" };
const STATUS_NAMES: Record<string, string> = {
  active: "生效中", internal: "内部授权", paid: "已支付", pending: "待支付", cancelled: "已取消",
  QUEUED: "排队中", RUNNING: "运行中", FAILED: "失败", SUCCEEDED: "成功", CANCELLED: "已取消",
  requested: "待处理", processing: "处理中", issued: "已开具", rejected: "已驳回",
  succeeded: "成功", failed: "失败", started: "执行中",
};

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function dateTime(value: unknown): string {
  if (!value) return "—";
  const valueDate = new Date(String(value));
  return Number.isNaN(valueDate.getTime()) ? String(value) : valueDate.toLocaleString("zh-CN", { hour12: false });
}

function statusTone(status: unknown): string {
  const value = String(status || "").toLowerCase();
  if (["active", "paid", "succeeded", "issued", "ready", "ok"].includes(value)) return "good";
  if (["failed", "rejected", "cancelled", "unavailable"].includes(value)) return "bad";
  if (["running", "processing", "queued", "requested", "started", "pending", "internal"].includes(value)) return "warn";
  return "neutral";
}

function Status({ value }: { value: unknown }) {
  return <span className={`admin-status ${statusTone(value)}`}>{STATUS_NAMES[String(value)] || text(value)}</span>;
}

function Button({ children, tone = "secondary", disabled, onClick }: {
  children: ReactNode; tone?: "primary" | "secondary" | "danger"; disabled?: boolean; onClick?: () => void;
}) {
  return <button className={`admin-button ${tone}`} disabled={disabled} onClick={onClick}>{children}</button>;
}

function Empty({ children = "暂无数据" }: { children?: ReactNode }) {
  return <div className="admin-empty">{children}</div>;
}

function Loading() {
  return <div className="admin-loading"><LoaderCircle size={20} className="spin" /> 正在加载</div>;
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <section className="admin-panel"><header><h2>{title}</h2>{action}</header>{children}</section>;
}

function useRemote<T>(path: string | null, refreshKey = 0) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (!path) { setData(null); setLoading(false); return; }
    setLoading(true); setError("");
    api<T>(path).then((value) => { if (active) setData(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, refreshKey]);
  return { data, loading, error };
}

function Login({ onLogin }: { onLogin: (admin: AdminProfile) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try { onLogin(await loginAdmin(email, password, otp)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); }
    finally { setBusy(false); }
  };
  return <main className="admin-login">
    <div className="admin-login-card">
      <div className="admin-login-brand"><img src="/favicon.svg" alt=""/><span>OpenVMA</span></div>
      <div className="admin-login-heading"><p className="eyebrow">SECURE ADMIN</p><h1>登录运营后台</h1><p>使用独立管理员账号、密码和动态验证码继续。</p></div>
      <form onSubmit={submit}>
        <label>管理员邮箱<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>密码<input type="password" minLength={10} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        <label>6 位动态验证码<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} required /></label>
        {error && <div className="admin-error"><CircleAlert size={16} />{error}</div>}
        <button type="submit" className="admin-login-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <ShieldCheck size={18} />}{busy ? "正在验证" : "继续"}</button>
      </form>
      <small>此系统仅供授权人员使用，敏感查看与所有写操作均会记录审计日志。</small>
    </div>
  </main>;
}

function Dashboard() {
  const summary = useRemote<Data>("/api/admin/dashboard/summary");
  const alerts = useRemote<{ items: Data[] }>("/api/admin/dashboard/alerts");
  const health = useRemote<Data>("/api/admin/dashboard/health");
  if (summary.loading) return <Loading />;
  const metrics = [
    ["今日新增用户", summary.data?.new_users, UserRound], ["今日支付金额", `¥${Number(summary.data?.paid_amount || 0).toFixed(2)}`, BadgeDollarSign],
    ["今日失败任务", summary.data?.failed_jobs, CircleAlert], ["待处理发票", summary.data?.requested_invoices, FileText],
  ] as const;
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">TODAY</p><h1>工作台</h1><p>核心业务指标、待办和系统健康状态。</p></div></div>
    <div className="metric-grid">{metrics.map(([label, value, Icon]) => <div className="metric-card" key={label}><Icon size={20}/><span>{label}</span><strong>{text(value, "0")}</strong></div>)}</div>
    <div className="admin-grid-2">
      <Panel title="需要处理"><div className="alert-list">{alerts.data?.items.map((item) => <div className="alert-row" key={text(item.code)}><div><strong>{text(item.label)}</strong><span>{text(item.severity) === "critical" ? "建议优先处理" : "待跟进"}</span></div><b className={Number(item.count) > 0 ? "has-alert" : ""}>{text(item.count, "0")}</b></div>) || <Loading />}</div></Panel>
      <Panel title="系统健康"><div className="health-list">{health.data && Object.entries((health.data.checks || {}) as Data).map(([name, value]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><Status value={value}/></div>)}</div>{health.error && <div className="admin-error">{health.error}</div>}</Panel>
    </div>
  </div>;
}

function Users({ selectedFromSearch }: { selectedFromSearch?: string }) {
  const [q, setQ] = useState(""); const [submitted, setSubmitted] = useState("");
  const [selected, setSelected] = useState(selectedFromSearch || ""); const [refresh, setRefresh] = useState(0);
  useEffect(() => { if (selectedFromSearch) setSelected(selectedFromSearch); }, [selectedFromSearch]);
  const list = useRemote<ListResponse>(`/api/admin/users?q=${encodeURIComponent(submitted)}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/users/${selected}` : null, refresh);
  const act = async (kind: "reveal" | "quota" | "subscription") => {
    const reason = window.prompt("请输入操作原因（至少 3 个字符，将写入审计日志）")?.trim(); if (!reason || reason.length < 3) return;
    try {
      if (kind === "reveal") {
        const result = await api<Data>(`/api/admin/users/${selected}/reveal-identities`, { method: "POST", body: JSON.stringify({ reason }) });
        window.alert(JSON.stringify(result, null, 2));
      } else if (kind === "quota") {
        const quota_type = window.prompt("额度类型：processing_seconds / ai_image / ai_video / export", "ai_image")?.trim();
        const amount = Number(window.prompt("增加数量（必须为正整数）", "1"));
        if (!quota_type || !Number.isInteger(amount) || amount <= 0) return;
        await api(`/api/admin/users/${selected}/quota-adjustments`, mutationOptions({ quota_type, amount, reason }));
      } else {
        const membership_id = window.prompt("付费会员方案 ID")?.trim();
        const days = Number(window.prompt("授权天数（1-90）", "30"));
        if (!membership_id || !Number.isInteger(days) || days < 1 || days > 90) return;
        await api(`/api/admin/users/${selected}/internal-subscription`, mutationOptions({ membership_id, ends_at: new Date(Date.now() + days * 86400000).toISOString(), reason }));
      }
      setRefresh((value) => value + 1);
    } catch (error) { window.alert(error instanceof Error ? error.message : "操作失败"); }
  };
  return <div className="admin-stack"><div className="admin-page-title"><div><p className="eyebrow">CUSTOMERS</p><h1>用户</h1><p>查询身份、会员、用量和最近业务上下文。</p></div></div>
    <form className="admin-toolbar" onSubmit={(event) => { event.preventDefault(); setSubmitted(q); }}><Search size={18}/><input placeholder="用户 ID、姓名、邮箱或手机号" value={q} onChange={(event) => setQ(event.target.value)}/><Button tone="primary">查询</Button></form>
    <Panel title={`用户列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : list.error ? <div className="admin-error">{list.error}</div> : <div className="admin-table-wrap"><table><thead><tr><th>用户</th><th>会员</th><th>订阅</th><th>项目 / 素材</th><th>近 30 天失败</th><th/></tr></thead><tbody>{list.data?.items.map((user) => <tr key={text(user.id)}><td><strong>{text(user.name)}</strong><small>{text(user.email)} · {text(user.id)}</small></td><td>{text(user.membership)}</td><td><Status value={user.subscription_status}/></td><td>{text(user.projects, "0")} / {text(user.assets, "0")}</td><td>{text(user.failed_jobs_30d, "0")}</td><td><button className="row-link" onClick={() => setSelected(text(user.id))}>查看 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}</Panel>
    {selected && <Drawer title="用户详情" onClose={() => setSelected("")}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><DetailGrid data={{ 用户: detail.data.name, 用户ID: detail.data.id, 邮箱: detail.data.email, 注册时间: dateTime(detail.data.created_at) }}/><div className="action-row"><Button onClick={() => act("reveal")}>查看完整身份</Button><Button onClick={() => act("quota")}>发放额度补偿</Button><Button tone="primary" onClick={() => act("subscription")}>内部会员授权</Button></div><JsonBlock title="会员与订阅" value={{ membership: detail.data.membership, subscription: detail.data.subscription, usage: detail.data.usage, reserved: detail.data.reserved, quota_adjustments: detail.data.quota_adjustments }}/><JsonBlock title="最近任务" value={detail.data.recent_jobs}/><JsonBlock title="最近订单" value={detail.data.recent_orders}/></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
  </div>;
}

function Jobs({ selectedFromSearch }: { selectedFromSearch?: string }) {
  const [q, setQ] = useState(""); const [submitted, setSubmitted] = useState(""); const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(selectedFromSearch || ""); const [refresh, setRefresh] = useState(0);
  useEffect(() => { if (selectedFromSearch) setSelected(selectedFromSearch); }, [selectedFromSearch]);
  const list = useRemote<ListResponse>(`/api/admin/jobs?q=${encodeURIComponent(submitted)}&status=${encodeURIComponent(status)}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/jobs/${selected}` : null, refresh);
  const act = async (kind: "payload" | "retry" | "cancel") => {
    const reason = window.prompt("请输入操作原因（至少 3 个字符，将写入审计日志）")?.trim(); if (!reason || reason.length < 3) return;
    if (kind !== "payload" && !window.confirm(kind === "retry" ? "确认重新派发此失败任务？" : "确认撤销此任务？运行中的 Worker 子进程将被终止。")) return;
    try {
      const options = kind === "payload" ? { method: "POST", body: JSON.stringify({ reason }) } : mutationOptions({ reason });
      const result = await api<Data>(`/api/admin/jobs/${selected}/${kind === "payload" ? "reveal-payload" : kind}`, options);
      if (kind === "payload") window.alert(JSON.stringify(result, null, 2));
      setRefresh((value) => value + 1);
    } catch (error) { window.alert(error instanceof Error ? error.message : "操作失败"); }
  };
  return <div className="admin-stack"><div className="admin-page-title"><div><p className="eyebrow">JOBS</p><h1>任务</h1><p>全局排查任务状态，并执行受控重试或取消。</p></div></div>
    <form className="admin-toolbar" onSubmit={(event) => { event.preventDefault(); setSubmitted(q); }}><Search size={18}/><input placeholder="任务、Celery、项目或用户 ID" value={q} onChange={(event) => setQ(event.target.value)}/><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option><option>QUEUED</option><option>RUNNING</option><option>FAILED</option><option>SUCCEEDED</option><option>CANCELLED</option></select><Button tone="primary">查询</Button></form>
    <Panel title={`任务列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : <div className="admin-table-wrap"><table><thead><tr><th>任务</th><th>用户</th><th>状态</th><th>阶段</th><th>进度</th><th>更新时间</th><th/></tr></thead><tbody>{list.data?.items.map((job) => <tr key={text(job.id)}><td><strong>{text(job.name)}</strong><small>{text(job.type)} · {text(job.id)}</small></td><td>{text((job.owner as Data)?.name)}<small>{text((job.owner as Data)?.email)}</small></td><td><Status value={job.status}/></td><td>{text(job.stage)}</td><td>{text(job.progress, "0")}%</td><td>{dateTime(job.updated_at)}</td><td><button className="row-link" onClick={() => setSelected(text(job.id))}>查看 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}</Panel>
    {selected && <Drawer title="任务详情" onClose={() => setSelected("")}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><DetailGrid data={{ 任务: detail.data.name, 类型: detail.data.type, 状态: <Status value={detail.data.status}/>, 阶段: detail.data.stage, 进度: `${text(detail.data.progress, "0")}%`, 尝试次数: `${text(detail.data.attempts, "0")} / ${text(detail.data.max_attempts)}`, 错误码: detail.data.error_code, 供应商: detail.data.provider }}/><div className="action-row"><Button onClick={() => act("payload")}>查看脱敏 Payload</Button>{detail.data.status === "FAILED" && <Button tone="primary" onClick={() => act("retry")}>安全重试</Button>}{["QUEUED", "RUNNING"].includes(text(detail.data.status)) && <Button tone="danger" onClick={() => act("cancel")}>取消任务</Button>}</div><JsonBlock title="日志" value={detail.data.logs}/><JsonBlock title="结果" value={{ result: detail.data.result, detail: detail.data.result_detail, inspiration_run: detail.data.inspiration_run }}/></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
  </div>;
}

function Transactions({ selectedType, selectedId }: { selectedType?: string; selectedId?: string }) {
  const [tab, setTab] = useState<"orders" | "invoices">(selectedType === "invoice" ? "invoices" : "orders");
  const [refresh, setRefresh] = useState(0); const [selected, setSelected] = useState(selectedId || "");
  useEffect(() => { if (selectedId) { setSelected(selectedId); setTab(selectedType === "invoice" ? "invoices" : "orders"); } }, [selectedId, selectedType]);
  const list = useRemote<ListResponse>(`/api/admin/${tab}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/${tab}/${selected}` : null, refresh);
  const act = async (kind: "reconcile" | "accept" | "reject" | "issue") => {
    const reason = window.prompt("请输入操作原因（至少 3 个字符，将写入审计日志）")?.trim(); if (!reason || reason.length < 3) return;
    let body: Data = { reason };
    if (kind === "issue") { const invoice_number = window.prompt("请输入正式发票号码")?.trim(); if (!invoice_number) return; body = { ...body, invoice_number }; }
    const path = kind === "reconcile" ? `/api/admin/orders/${selected}/reconcile-subscription` : `/api/admin/invoices/${selected}/${kind}`;
    try { await api(path, mutationOptions(body)); setRefresh((value) => value + 1); }
    catch (error) { window.alert(error instanceof Error ? error.message : "操作失败"); }
  };
  return <div className="admin-stack"><div className="admin-page-title"><div><p className="eyebrow">BILLING</p><h1>交易</h1><p>处理支付订阅一致性与发票状态流转。</p></div></div>
    <div className="admin-tabs"><button className={tab === "orders" ? "active" : ""} onClick={() => { setTab("orders"); setSelected(""); }}>订单</button><button className={tab === "invoices" ? "active" : ""} onClick={() => { setTab("invoices"); setSelected(""); }}>发票</button></div>
    <Panel title={`${tab === "orders" ? "订单" : "发票"}列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : <div className="admin-table-wrap"><table><thead><tr>{tab === "orders" ? <><th>订单</th><th>用户</th><th>金额</th><th>状态</th><th>订阅一致性</th><th/></> : <><th>申请</th><th>用户</th><th>企业</th><th>金额</th><th>状态</th><th/></>}</tr></thead><tbody>{list.data?.items.map((item) => tab === "orders" ? <tr key={text(item.id)}><td><strong>{text(item.membership_name)}</strong><small>{text(item.id)}</small></td><td>{text((item.user as Data)?.name)}<small>{text((item.user as Data)?.email)}</small></td><td>¥{Number(item.amount || 0).toFixed(2)}</td><td><Status value={item.status}/></td><td>{item.requires_reconciliation ? <span className="danger-text">需要同步</span> : "正常"}</td><td><button className="row-link" onClick={() => setSelected(text(item.id))}>查看 <ChevronRight size={15}/></button></td></tr> : <tr key={text(item.id)}><td><strong>{text(item.id)}</strong><small>{dateTime(item.requested_at)}</small></td><td>{text((item.user as Data)?.name)}</td><td>{text(item.company_name)}</td><td>¥{Number(item.amount || 0).toFixed(2)}</td><td><Status value={item.status}/></td><td><button className="row-link" onClick={() => setSelected(text(item.id))}>处理 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}</Panel>
    {selected && <Drawer title={tab === "orders" ? "订单详情" : "发票详情"} onClose={() => setSelected("")}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><JsonBlock title="业务信息" value={detail.data}/><div className="action-row">{tab === "orders" && detail.data.status === "paid" && detail.data.subscription_consistent === false && <Button tone="primary" onClick={() => act("reconcile")}>同步订阅</Button>}{tab === "invoices" && detail.data.status === "requested" && <Button tone="primary" onClick={() => act("accept")}>受理</Button>}{tab === "invoices" && ["requested", "processing"].includes(text(detail.data.status)) && <Button tone="danger" onClick={() => act("reject")}>驳回</Button>}{tab === "invoices" && detail.data.status === "processing" && <Button tone="primary" onClick={() => act("issue")}>标记已开具</Button>}</div></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
  </div>;
}

function Audit() {
  const [action, setAction] = useState(""); const [status, setStatus] = useState("");
  const list = useRemote<ListResponse>(`/api/admin/audit-logs?action=${encodeURIComponent(action)}&status=${encodeURIComponent(status)}`);
  const [selected, setSelected] = useState<Data | null>(null);
  return <div className="admin-stack"><div className="admin-page-title"><div><p className="eyebrow">AUDIT TRAIL</p><h1>审计</h1><p>查看管理员敏感读取、业务变更及失败记录。</p></div></div>
    <div className="admin-toolbar"><Search size={18}/><input placeholder="精确操作类型，例如 JOB_RETRY" value={action} onChange={(event) => setAction(event.target.value)}/><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option><option value="succeeded">成功</option><option value="failed">失败</option><option value="started">执行中</option></select></div>
    <Panel title={`审计记录${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : <div className="admin-table-wrap"><table><thead><tr><th>时间</th><th>管理员</th><th>操作</th><th>目标</th><th>状态</th><th>原因</th><th/></tr></thead><tbody>{list.data?.items.map((item) => <tr key={text(item.id)}><td>{dateTime(item.created_at)}</td><td>{text((item.admin as Data)?.name)}<small>{text((item.admin as Data)?.role)}</small></td><td><code>{text(item.action)}</code></td><td>{text(item.target_type)}<small>{text(item.target_id)}</small></td><td><Status value={item.status}/></td><td className="reason-cell">{text(item.reason)}</td><td><button className="row-link" onClick={() => setSelected(item)}>查看</button></td></tr>)}</tbody></table></div>}</Panel>
    {selected && <Drawer title="审计详情" onClose={() => setSelected(null)}><JsonBlock title="完整记录" value={selected}/></Drawer>}
  </div>;
}

function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return <div className="drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><aside className="admin-drawer"><header><div><p className="eyebrow">DETAIL</p><h2>{title}</h2></div><button aria-label="关闭" onClick={onClose}><X/></button></header><div className="drawer-body">{children}</div></aside></div>;
}

function DetailGrid({ data }: { data: Record<string, unknown> }) {
  return <div className="detail-grid">{Object.entries(data).map(([label, value]) => <div key={label}><span>{label}</span><strong>{typeof value === "object" && value !== null ? value as ReactNode : text(value)}</strong></div>)}</div>;
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return <div className="json-block"><h3>{title}</h3><pre>{JSON.stringify(value, null, 2)}</pre></div>;
}

function GlobalSearch({ onOpen }: { onOpen: (type: string, id: string) => void }) {
  const [open, setOpen] = useState(false); const [q, setQ] = useState(""); const [result, setResult] = useState<Data | null>(null); const [loading, setLoading] = useState(false);
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); } if (event.key === "Escape") setOpen(false); }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); }, []);
  const submit = async (event: FormEvent) => { event.preventDefault(); if (q.trim().length < 2) return; setLoading(true); try { setResult(await api<Data>(`/api/admin/search?q=${encodeURIComponent(q.trim())}`)); } finally { setLoading(false); } };
  return <><button type="button" className="global-search-trigger" onClick={() => setOpen(true)}><Search size={17}/><span>搜索后台</span><kbd>⌘ K</kbd></button>{open && <div className="search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}><div className="search-dialog"><form onSubmit={submit}><Search/><input autoFocus placeholder="搜索用户、任务、项目、订单或发票" value={q} onChange={(event) => setQ(event.target.value)}/><button type="button" aria-label="关闭搜索" onClick={() => setOpen(false)}><X/></button></form><div className="search-results">{loading ? <Loading/> : result ? Object.entries(result).flatMap(([group, values]) => (values as Data[]).map((item) => <button type="button" key={`${group}-${text(item.id)}`} onClick={() => { onOpen(text(item.type), text(item.id)); setOpen(false); }}><span><b>{text(item.name, text(item.id))}</b><small>{group} · {text(item.id)}</small></span><ChevronRight/></button>)) : <Empty>输入至少两个字符开始搜索</Empty>}</div></div></div>}</>;
}

export default function AdminApp() {
  const [admin, setAdmin] = useState<AdminProfile | null>(null); const [booting, setBooting] = useState(true);
  const hashView = (location.hash.slice(2).split("/")[0] || "dashboard") as View;
  const [view, setView] = useState<View>(NAV.some((item) => item.id === hashView) ? hashView : "dashboard");
  const [selected, setSelected] = useState<{ type: string; id: string } | null>(null);
  useEffect(() => { restoreAdmin().then(setAdmin).finally(() => setBooting(false)); }, []);
  const navigate = useCallback((next: View) => { setView(next); setSelected(null); location.hash = `/${next}`; }, []);
  const openSearchResult = (type: string, id: string) => {
    const next: View = type === "user" ? "users" : type === "job" ? "jobs" : ["order", "invoice"].includes(type) ? "transactions" : "dashboard";
    setView(next); setSelected({ type, id }); location.hash = `/${next}`;
  };
  const content = useMemo(() => {
    if (view === "users") return <Users selectedFromSearch={selected?.type === "user" ? selected.id : undefined}/>;
    if (view === "jobs") return <Jobs selectedFromSearch={selected?.type === "job" ? selected.id : undefined}/>;
    if (view === "transactions") return <Transactions selectedType={selected?.type} selectedId={selected?.id}/>;
    if (view === "audit") return <Audit/>;
    return <Dashboard/>;
  }, [view, selected]);
  if (booting) return <div className="admin-boot"><LoaderCircle className="spin"/><span>正在恢复安全会话</span></div>;
  if (!admin) return <Login onLogin={setAdmin}/>;
  return <div className="admin-layout"><aside className="admin-sidebar"><div className="sidebar-brand"><img className="admin-brand-mark small" src="/favicon.svg" alt=""/><div><strong>OpenVMA</strong><span>运营后台</span></div></div><span className="sidebar-section-label">管理</span><nav aria-label="运营后台导航">{NAV.map((item) => { const Icon = item.icon; return <button type="button" className={view === item.id ? "active" : ""} key={item.id} onClick={() => navigate(item.id)}><Icon size={18}/>{item.label}</button>; })}</nav><div className="sidebar-footer"><div><span className="admin-avatar">{admin.name.slice(0, 1)}</span><span><strong>{admin.name}</strong><small>{ROLE_NAMES[admin.role] || admin.role}</small></span></div><button type="button" aria-label="退出运营后台" title="退出" onClick={async () => { await logoutAdmin(); setAdmin(null); }}><LogOut size={18}/></button></div></aside><main className="admin-main"><header className="admin-topbar"><div className="topbar-context"><span>运营控制台</span><div className="environment-banner"><Activity size={13}/>{location.hostname.includes("localhost") ? "开发环境" : "生产环境"}</div></div><GlobalSearch onOpen={openSearchResult}/></header><div className="admin-content">{content}</div></main></div>;
}
