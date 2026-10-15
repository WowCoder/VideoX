import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BadgeDollarSign,
  BriefcaseBusiness,
  CalendarDays,
  ChevronRight,
  CircleAlert,
  Cpu,
  FileText,
  Gauge,
  HardDrive,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import { api, AdminProfile, loginAdmin, logoutAdmin, mutationOptions, restoreAdmin } from "./api/client";
import {
  ActionDialog,
  AdminToastProvider,
  Button,
  ChangeSummary,
  FormField,
  Pagination,
  Panel,
  useAdminToast,
} from "./ui";

type Data = Record<string, unknown>;
type ListResponse = { items: Data[]; total: number; page: number; page_size: number; sort?: string };
type View = "dashboard" | "users" | "jobs" | "transactions" | "pricing" | "audit" | "security";

const NAV: { id: View; label: string; icon: typeof Gauge }[] = [
  { id: "dashboard", label: "工作台", icon: Gauge },
  { id: "users", label: "用户", icon: UsersRound },
  { id: "jobs", label: "任务", icon: BriefcaseBusiness },
  { id: "transactions", label: "交易", icon: BadgeDollarSign },
  { id: "pricing", label: "商业配置", icon: SlidersHorizontal },
  { id: "audit", label: "审计", icon: ShieldCheck },
  { id: "security", label: "会话安全", icon: LockKeyhole },
];

const ROLE_NAMES: Record<string, string> = { super_admin: "超级管理员", operator: "运营", finance: "财务" };
const STATUS_NAMES: Record<string, string> = {
  active: "生效中", internal: "内部授权", paid: "已支付", pending: "待支付", cancelled: "已取消",
  QUEUED: "排队中", RUNNING: "运行中", FAILED: "失败", SUCCEEDED: "成功", CANCELLED: "已取消",
  requested: "待处理", processing: "处理中", issued: "已开具", rejected: "已驳回",
  succeeded: "成功", failed: "失败", started: "执行中", stale: "数据过期",
  ready: "正常", ok: "正常", unavailable: "不可用", warning: "警告", critical: "严重",
};

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function number(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function dateTime(value: unknown): string {
  if (!value) return "—";
  const valueDate = new Date(String(value));
  return Number.isNaN(valueDate.getTime()) ? String(value) : valueDate.toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(value: unknown): string {
  const bytes = number(value);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(index > 2 ? 1 : 0)} ${units[index]}`;
}

function formatDuration(value: unknown): string {
  let seconds = Math.max(0, Math.floor(number(value)));
  const days = Math.floor(seconds / 86400); seconds %= 86400;
  const hours = Math.floor(seconds / 3600);
  return days ? `${days} 天 ${hours} 小时` : `${hours} 小时`;
}

function statusTone(status: unknown): string {
  const value = String(status || "").toLowerCase();
  if (["active", "paid", "succeeded", "issued", "ready", "ok"].includes(value)) return "good";
  if (["failed", "rejected", "cancelled", "unavailable", "critical"].includes(value)) return "bad";
  if (["running", "processing", "queued", "requested", "started", "pending", "internal", "stale", "warning"].includes(value)) return "warn";
  return "neutral";
}

function Status({ value }: { value: unknown }) {
  return <span className={`admin-status ${statusTone(value)}`}>{STATUS_NAMES[String(value)] || text(value)}</span>;
}

function Empty({ children = "暂无数据" }: { children?: ReactNode }) {
  return <div className="admin-empty">{children}</div>;
}

function Loading() {
  return <div className="admin-loading"><LoaderCircle size={20} className="spin"/>正在加载</div>;
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

function readHashParams(): URLSearchParams {
  return new URLSearchParams(location.hash.split("?")[1] || "");
}

function writeHashParams(view: View, values: Record<string, string | number>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (String(value) && String(value) !== "1" && !(key === "page_size" && Number(value) === 20)) params.set(key, String(value));
  });
  const suffix = params.toString() ? `?${params.toString()}` : "";
  history.replaceState(null, "", `${location.pathname}${location.search}#/${view}${suffix}`);
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
  return <main className="admin-login"><div className="admin-login-card">
    <div className="admin-login-brand"><img src="/favicon.svg" alt=""/><span>VideoX</span></div>
    <div className="admin-login-heading"><p className="eyebrow">SECURE ADMIN</p><h1>登录运营后台</h1><p>使用独立管理员账号、密码和动态验证码继续。</p></div>
    <form onSubmit={submit}>
      <label>管理员邮箱<input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required/></label>
      <label>密码<input type="password" minLength={10} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required/></label>
      <label>6 位动态验证码<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} required/></label>
      {error && <div className="admin-error"><CircleAlert size={16}/>{error}</div>}
      <button type="submit" className="admin-login-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18}/> : <ShieldCheck size={18}/>} {busy ? "正在验证" : "继续"}</button>
    </form>
    <small>此系统仅供授权人员使用，敏感查看与所有写操作均会记录审计日志。</small>
  </div></main>;
}

function ResourceBar({ label, used, total, percent }: { label: string; used: unknown; total: unknown; percent: unknown }) {
  const value = Math.min(100, Math.max(0, number(percent)));
  const tone = value >= 90 ? "critical" : value >= 80 ? "warning" : "ok";
  return <div className="resource-row"><div><span>{label}</span><b>{formatBytes(used)} / {formatBytes(total)}</b></div><Status value={tone}/><div className="resource-track"><span className={tone} style={{ width: `${value}%` }}/></div><small>{value.toFixed(1)}%</small></div>;
}

function Dashboard() {
  const [refresh, setRefresh] = useState(0);
  const [refreshingMetrics, setRefreshingMetrics] = useState(false);
  const { notify } = useAdminToast();
  const summary = useRemote<Data>("/api/admin/dashboard/summary", refresh);
  const alerts = useRemote<{ items: Data[] }>("/api/admin/dashboard/alerts", refresh);
  const health = useRemote<Data>("/api/admin/dashboard/health", refresh);
  const system = useRemote<Data>("/api/admin/dashboard/system-metrics", refresh);
  const refreshSystemMetrics = async () => {
    setRefreshingMetrics(true);
    try {
      const result = await api<Data>("/api/admin/dashboard/system-metrics/refresh", { method: "POST" });
      if (result.collection_status === "failed") throw new Error(text(result.error_message, "服务器指标采集失败"));
      notify("服务器资源指标已更新"); setRefresh((value) => value + 1);
    } catch (error) { notify(error instanceof Error ? error.message : "服务器指标刷新失败", "error"); }
    finally { setRefreshingMetrics(false); }
  };
  if (summary.loading) return <Loading/>;
  const userMetrics = [
    ["总用户数", summary.data?.total_users, UsersRound],
    ["今日新增用户", summary.data?.new_users, UserRound],
    ["当天活跃用户", summary.data?.daily_active_users, Activity],
    ["本月活跃用户", summary.data?.monthly_active_users, CalendarDays],
  ] as const;
  const businessMetrics = [
    ["今日支付金额", `¥${number(summary.data?.paid_amount).toFixed(2)}`, BadgeDollarSign],
    ["今日失败任务", summary.data?.failed_jobs, CircleAlert],
    ["待处理发票", summary.data?.requested_invoices, FileText],
  ] as const;
  const latest = system.data?.latest as Data | null | undefined;
  const attempt = system.data?.latest_attempt as Data | null | undefined;
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">TODAY</p><h1>工作台</h1><p>核心业务指标、待办、服务健康和低频服务器资源状态。</p></div></div>
    <section className="dashboard-section"><header><h2>用户概览</h2><span>活跃数据自 {dateTime(summary.data?.activity_collection_started_at)} 起采集</span></header><div className="metric-grid">{userMetrics.map(([label, value, Icon]) => <div className="metric-card" key={label}><Icon size={20}/><span>{label}</span><strong>{text(value, "0")}</strong></div>)}</div></section>
    <section className="dashboard-section"><header><h2>业务概览</h2><span>北京时间自然日</span></header><div className="metric-grid metric-grid-three">{businessMetrics.map(([label, value, Icon]) => <div className="metric-card" key={label}><Icon size={20}/><span>{label}</span><strong>{text(value, "0")}</strong></div>)}</div></section>
    <div className="admin-grid-2">
      <Panel title="需要处理"><div className="alert-list">{alerts.data?.items.map((item) => <div className="alert-row" key={text(item.code)}><div><strong>{text(item.label)}</strong><span>{text(item.severity) === "critical" ? "建议优先处理" : "待跟进"}</span></div><b className={number(item.count) > 0 ? "has-alert" : ""}>{text(item.count, "0")}</b></div>) || <Loading/>}</div></Panel>
      <Panel title="服务健康"><div className="health-list">{health.data && Object.entries((health.data.checks || {}) as Data).map(([name, value]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><Status value={value}/></div>)}</div>{health.error && <div className="admin-error">{health.error}</div>}</Panel>
    </div>
    <Panel title="服务器资源" action={<div className="panel-actions"><Status value={system.data?.status}/><Button busy={refreshingMetrics} onClick={refreshSystemMetrics}><RefreshCw size={14}/>手动刷新</Button></div>}>
      {system.loading ? <Loading/> : !latest ? <div className="system-metrics-empty"><HardDrive size={24}/><strong>还没有成功的服务器资源快照</strong><span>{text(attempt?.error_message, "Celery Beat 将每小时自动采集，也可以立即手动刷新。")}</span></div> : <div className="system-metrics">
        <div className="system-metrics-meta"><span>节点 <b>{text(latest.node_name)}</b></span><span>范围 <b>{latest.metric_scope === "host" ? "宿主机" : "容器"}</b></span><span>最后更新 <b>{dateTime(latest.collected_at)}</b></span><span>运行时间 <b>{formatDuration(latest.uptime_seconds)}</b></span></div>
        {attempt?.collection_status === "failed" && attempt?.id !== latest.id && <div className="admin-action-warning"><CircleAlert size={17}/><span>最近一次采集失败，正在显示上次成功数据：{text(attempt.error_message)}</span></div>}
        <div className="load-grid"><div><Cpu/><span>1 分钟负载</span><b>{text(latest.load_1m, "0")}</b></div><div><Cpu/><span>5 分钟负载</span><b>{text(latest.load_5m, "0")}</b></div><div><Cpu/><span>15 分钟负载</span><b>{text(latest.load_15m, "0")}</b></div><div><Gauge/><span>CPU / 标准化负载</span><b>{text(latest.cpu_count, "0")} 核 / {number(latest.normalized_load_percent).toFixed(1)}%</b></div></div>
        <div className="resource-list"><ResourceBar label="内存" used={latest.memory_used_bytes} total={latest.memory_total_bytes} percent={latest.memory_percent}/><ResourceBar label="磁盘" used={latest.disk_used_bytes} total={latest.disk_total_bytes} percent={latest.disk_percent}/></div>
      </div>}
    </Panel>
  </div>;
}

type UserAction = "reveal" | "quota" | "credits" | "subscription" | null;

function Users({ selectedFromSearch }: { selectedFromSearch?: string }) {
  const initial = useMemo(() => readHashParams(), []);
  const [q, setQ] = useState(initial.get("q") || "");
  const [submitted, setSubmitted] = useState(initial.get("q") || "");
  const [sort, setSort] = useState(initial.get("sort") || "created_desc");
  const [page, setPage] = useState(Number(initial.get("page") || 1));
  const [pageSize, setPageSize] = useState(Number(initial.get("page_size") || 20));
  const [selected, setSelected] = useState(selectedFromSearch || "");
  const [refresh, setRefresh] = useState(0);
  const [action, setAction] = useState<UserAction>(null);
  const [revealed, setRevealed] = useState<Data | null>(null);
  const { notify } = useAdminToast();
  useEffect(() => { if (selectedFromSearch) setSelected(selectedFromSearch); }, [selectedFromSearch]);
  useEffect(() => writeHashParams("users", { q: submitted, sort, page, page_size: pageSize }), [submitted, sort, page, pageSize]);
  const list = useRemote<ListResponse>(`/api/admin/users?q=${encodeURIComponent(submitted)}&sort=${sort}&page=${page}&page_size=${pageSize}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/users/${selected}` : null, refresh);
  const submitAction = async (values: Record<string, string>) => {
    if (action === "reveal") {
      setRevealed(await api<Data>(`/api/admin/users/${selected}/reveal-identities`, { method: "POST", body: JSON.stringify({ reason: values.reason }) }));
      notify("完整身份信息已受控展示，读取行为已审计"); return;
    }
    if (action === "quota") {
      const amount = Number(values.amount);
      if (!Number.isInteger(amount) || amount <= 0) throw new Error("补偿数量必须为正整数");
      await api(`/api/admin/users/${selected}/quota-adjustments`, mutationOptions({ quota_type: values.quota_type, amount, reason: values.reason }));
      notify("额度补偿已发放");
    }
    if (action === "credits") {
      const amount = Number(values.amount);
      if (!Number.isInteger(amount) || amount <= 0) throw new Error("积分数量必须为正整数");
      await api(`/api/admin/users/${selected}/credits`, mutationOptions({ amount, reason: values.reason }));
      notify("V-Credits 补偿已发放");
    }
    if (action === "subscription") {
      const days = Number(values.days);
      if (!Number.isInteger(days) || days < 1 || days > 90) throw new Error("授权天数必须在 1–90 天之间");
      await api(`/api/admin/users/${selected}/internal-subscription`, mutationOptions({ membership_id: values.membership_id.trim(), ends_at: new Date(Date.now() + days * 86400000).toISOString(), reason: values.reason }));
      notify("内部会员授权已生效");
    }
    setRefresh((value) => value + 1);
  };
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">CUSTOMERS</p><h1>用户</h1><p>查询身份、会员、用量和最近业务上下文。</p></div></div>
    <form className="admin-toolbar" onSubmit={(event) => { event.preventDefault(); setSubmitted(q.trim()); setPage(1); }}><Search size={18}/><input placeholder="用户 ID、姓名、邮箱或手机号" value={q} onChange={(event) => setQ(event.target.value)}/><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="created_desc">注册时间：新到旧</option><option value="created_asc">注册时间：旧到新</option></select><Button type="submit" tone="primary">查询</Button></form>
    <Panel title={`用户列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : list.error ? <div className="admin-error">{list.error}</div> : <>{!list.data?.items.length ? <Empty/> : <div className="admin-table-wrap"><table><thead><tr><th>用户</th><th>会员</th><th>订阅</th><th>项目 / 素材</th><th>近 30 天失败</th><th/></tr></thead><tbody>{list.data.items.map((user) => <tr key={text(user.id)}><td><strong>{text(user.name)}</strong><small>{text(user.email)} · {text(user.id)}</small></td><td>{text(user.membership)}</td><td><Status value={user.subscription_status}/></td><td>{text(user.projects, "0")} / {text(user.assets, "0")}</td><td>{text(user.failed_jobs_30d, "0")}</td><td><button className="row-link" onClick={() => setSelected(text(user.id))}>查看 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}<Pagination page={page} pageSize={pageSize} total={list.data?.total || 0} onPageChange={setPage} onPageSizeChange={(value) => { setPageSize(value); setPage(1); }}/></>}</Panel>
    {selected && <Drawer title="用户详情" onClose={() => { setSelected(""); setRevealed(null); }}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><DetailGrid data={{ 用户: detail.data.name, 用户ID: detail.data.id, 邮箱: detail.data.email, 注册时间: dateTime(detail.data.created_at) }}/><div className="action-row"><Button onClick={() => setAction("reveal")}>查看完整身份</Button><Button onClick={() => setAction("quota")}>发放旧额度补偿</Button><Button onClick={() => setAction("credits")}>发放 V-Credits</Button><Button tone="primary" onClick={() => setAction("subscription")}>内部会员授权</Button></div>{revealed && <JsonBlock title="本次受控身份读取" value={revealed}/>}<JsonBlock title="会员与订阅" value={{ membership: detail.data.membership, subscription: detail.data.subscription, usage: detail.data.usage, wallet: detail.data.wallet, reserved: detail.data.reserved, quota_adjustments: detail.data.quota_adjustments }}/><JsonBlock title="最近任务" value={detail.data.recent_jobs}/><JsonBlock title="最近订单" value={detail.data.recent_orders}/></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
    {action && <ActionDialog title={action === "reveal" ? "查看完整身份信息" : action === "quota" ? "发放旧额度补偿" : action === "credits" ? "发放 V-Credits" : "内部会员授权"} description={action === "reveal" ? "完整邮箱、手机号等身份数据属于敏感信息，只能用于明确的业务处理。" : action === "quota" ? "补偿额度会增加用户可用资源，不会篡改历史使用量。" : action === "credits" ? "积分会立即进入用户 V-Credits 钱包，并记录有效期与审计流水。" : "内部授权会改变用户当前会员与订阅状态。"} target={selected} warning={action === "subscription" ? "该操作会覆盖当前有效会员状态，请确认用户和方案无误。" : undefined} confirmPhrase={action === "reveal" || action === "subscription" ? selected : undefined} confirmText={action === "reveal" ? "受控查看" : action === "quota" ? "确认发放" : action === "credits" ? "确认发放" : "确认授权"} onClose={() => setAction(null)} onSubmit={submitAction}>
      {action === "quota" && <><FormField label="额度类型"><select name="quota_type" defaultValue="ai_image" required><option value="processing_seconds">处理秒数</option><option value="ai_image">AI 图片</option><option value="ai_video">AI 视频</option><option value="export">导出次数</option></select></FormField><FormField label="增加数量"><input name="amount" type="number" min={1} max={1000000} defaultValue={1} required/></FormField></>}
      {action === "credits" && <FormField label="积分数量"><input name="amount" type="number" min={1} max={10000000} defaultValue={1000} required/></FormField>}
      {action === "subscription" && <><FormField label="会员方案 ID"><input name="membership_id" placeholder="membership-pro" required/></FormField><FormField label="授权天数"><input name="days" type="number" min={1} max={90} defaultValue={30} required/></FormField></>}
    </ActionDialog>}
  </div>;
}

type JobAction = "payload" | "retry" | "cancel" | null;

function Jobs({ selectedFromSearch }: { selectedFromSearch?: string }) {
  const initial = useMemo(() => readHashParams(), []);
  const [q, setQ] = useState(initial.get("q") || "");
  const [submitted, setSubmitted] = useState(initial.get("q") || "");
  const [status, setStatus] = useState(initial.get("status") || "");
  const [sort, setSort] = useState(initial.get("sort") || "created_desc");
  const [page, setPage] = useState(Number(initial.get("page") || 1));
  const [pageSize, setPageSize] = useState(Number(initial.get("page_size") || 20));
  const [selected, setSelected] = useState(selectedFromSearch || "");
  const [refresh, setRefresh] = useState(0);
  const [action, setAction] = useState<JobAction>(null);
  const [payload, setPayload] = useState<Data | null>(null);
  const { notify } = useAdminToast();
  useEffect(() => { if (selectedFromSearch) setSelected(selectedFromSearch); }, [selectedFromSearch]);
  useEffect(() => writeHashParams("jobs", { q: submitted, status, sort, page, page_size: pageSize }), [submitted, status, sort, page, pageSize]);
  const list = useRemote<ListResponse>(`/api/admin/jobs?q=${encodeURIComponent(submitted)}&status=${encodeURIComponent(status)}&sort=${sort}&page=${page}&page_size=${pageSize}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/jobs/${selected}` : null, refresh);
  const submitAction = async (values: Record<string, string>) => {
    const endpoint = action === "payload" ? "reveal-payload" : action;
    const options = action === "payload" ? { method: "POST", body: JSON.stringify({ reason: values.reason }) } : mutationOptions({ reason: values.reason });
    const result = await api<Data>(`/api/admin/jobs/${selected}/${endpoint}`, options);
    if (action === "payload") { setPayload(result); notify("脱敏 Payload 已展示，读取行为已审计"); }
    else { notify(action === "retry" ? "失败任务已重新派发" : "任务取消指令已提交"); setRefresh((value) => value + 1); }
  };
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">JOBS</p><h1>任务</h1><p>全局排查任务状态，并执行受控重试或取消。</p></div></div>
    <form className="admin-toolbar" onSubmit={(event) => { event.preventDefault(); setSubmitted(q.trim()); setPage(1); }}><Search size={18}/><input placeholder="任务、Celery、项目或用户 ID" value={q} onChange={(event) => setQ(event.target.value)}/><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option><option>QUEUED</option><option>RUNNING</option><option>FAILED</option><option>SUCCEEDED</option><option>CANCELLED</option></select><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="created_desc">创建：新到旧</option><option value="created_asc">创建：旧到新</option><option value="updated_desc">更新：新到旧</option><option value="updated_asc">更新：旧到新</option></select><Button type="submit" tone="primary">查询</Button></form>
    <Panel title={`任务列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : list.error ? <div className="admin-error">{list.error}</div> : <>{!list.data?.items.length ? <Empty/> : <div className="admin-table-wrap"><table><thead><tr><th>任务</th><th>用户</th><th>状态</th><th>阶段</th><th>进度</th><th>更新时间</th><th/></tr></thead><tbody>{list.data.items.map((job) => <tr key={text(job.id)}><td><strong>{text(job.name)}</strong><small>{text(job.type)} · {text(job.id)}</small></td><td>{text((job.owner as Data)?.name)}<small>{text((job.owner as Data)?.email)}</small></td><td><Status value={job.status}/></td><td>{text(job.stage)}</td><td>{text(job.progress, "0")}%</td><td>{dateTime(job.updated_at)}</td><td><button className="row-link" onClick={() => setSelected(text(job.id))}>查看 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}<Pagination page={page} pageSize={pageSize} total={list.data?.total || 0} onPageChange={setPage} onPageSizeChange={(value) => { setPageSize(value); setPage(1); }}/></>}</Panel>
    {selected && <Drawer title="任务详情" onClose={() => { setSelected(""); setPayload(null); }}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><DetailGrid data={{ 任务: detail.data.name, 类型: detail.data.type, 状态: <Status value={detail.data.status}/>, 阶段: detail.data.stage, 进度: `${text(detail.data.progress, "0")}%`, 尝试次数: `${text(detail.data.attempts, "0")} / ${text(detail.data.max_attempts)}`, 错误码: detail.data.error_code, 供应商: detail.data.provider }}/><div className="action-row"><Button onClick={() => setAction("payload")}>查看脱敏 Payload</Button>{detail.data.status === "FAILED" && <Button tone="primary" onClick={() => setAction("retry")}>安全重试</Button>}{["QUEUED", "RUNNING"].includes(text(detail.data.status)) && <Button tone="danger" onClick={() => setAction("cancel")}>取消任务</Button>}</div>{payload && <JsonBlock title="本次受控 Payload 读取" value={payload}/>}<JsonBlock title="日志" value={detail.data.logs}/><JsonBlock title="结果" value={{ result: detail.data.result, detail: detail.data.result_detail, inspiration_run: detail.data.inspiration_run }}/></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
    {action && <ActionDialog title={action === "payload" ? "查看脱敏 Payload" : action === "retry" ? "安全重试任务" : "取消任务"} description={action === "payload" ? "仅展示完成排查所需的脱敏字段。" : action === "retry" ? "系统会创建新的任务尝试并重新派发到 Worker。" : "排队任务将直接取消，运行中的任务会提交终止指令。"} target={selected} warning={action === "cancel" ? "取消运行中任务可能中断正在执行的外部生成或媒体处理。" : undefined} confirmPhrase={action === "payload" ? undefined : selected} confirmText={action === "payload" ? "受控查看" : action === "retry" ? "确认重试" : "确认取消"} tone={action === "cancel" ? "danger" : "primary"} onClose={() => setAction(null)} onSubmit={submitAction}/>}
  </div>;
}

type TransactionAction = "reconcile" | "accept" | "reject" | "issue" | null;

function Transactions({ selectedType, selectedId }: { selectedType?: string; selectedId?: string }) {
  const initial = useMemo(() => readHashParams(), []);
  const [tab, setTab] = useState<"orders" | "invoices">(selectedType === "invoice" || initial.get("tab") === "invoices" ? "invoices" : "orders");
  const [status, setStatus] = useState(initial.get("status") || "");
  const [sort, setSort] = useState(initial.get("sort") || "created_desc");
  const [page, setPage] = useState(Number(initial.get("page") || 1));
  const [pageSize, setPageSize] = useState(Number(initial.get("page_size") || 20));
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState(selectedId || "");
  const [action, setAction] = useState<TransactionAction>(null);
  const { notify } = useAdminToast();
  useEffect(() => { if (selectedId) { setSelected(selectedId); setTab(selectedType === "invoice" ? "invoices" : "orders"); } }, [selectedId, selectedType]);
  useEffect(() => writeHashParams("transactions", { tab, status, sort, page, page_size: pageSize }), [tab, status, sort, page, pageSize]);
  const list = useRemote<ListResponse>(`/api/admin/${tab}?status=${encodeURIComponent(status)}&sort=${sort}&page=${page}&page_size=${pageSize}`, refresh);
  const detail = useRemote<Data>(selected ? `/api/admin/${tab}/${selected}` : null, refresh);
  const submitAction = async (values: Record<string, string>) => {
    const path = action === "reconcile" ? `/api/admin/orders/${selected}/reconcile-subscription` : `/api/admin/invoices/${selected}/${action}`;
    const body: Data = { reason: values.reason };
    if (action === "issue") body.invoice_number = values.invoice_number.trim();
    await api(path, mutationOptions(body));
    notify(action === "reconcile" ? "订单与订阅状态已同步" : action === "accept" ? "发票申请已受理" : action === "reject" ? "发票申请已驳回" : "发票已标记为开具");
    setRefresh((value) => value + 1);
  };
  const switchTab = (next: "orders" | "invoices") => { setTab(next); setSelected(""); setStatus(""); setPage(1); };
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">BILLING</p><h1>交易</h1><p>处理支付订阅一致性与发票状态流转。</p></div></div>
    <div className="admin-filter-row"><div className="admin-tabs"><button className={tab === "orders" ? "active" : ""} onClick={() => switchTab("orders")}>订单</button><button className={tab === "invoices" ? "active" : ""} onClick={() => switchTab("invoices")}>发票</button></div><div className="inline-filters"><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option>{tab === "orders" ? <><option value="pending">待支付</option><option value="paid">已支付</option><option value="cancelled">已取消</option></> : <><option value="requested">待处理</option><option value="processing">处理中</option><option value="issued">已开具</option><option value="rejected">已驳回</option></>}</select><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="created_desc">时间：新到旧</option><option value="created_asc">时间：旧到新</option></select></div></div>
    <Panel title={`${tab === "orders" ? "订单" : "发票"}列表${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : list.error ? <div className="admin-error">{list.error}</div> : <>{!list.data?.items.length ? <Empty/> : <div className="admin-table-wrap"><table><thead><tr>{tab === "orders" ? <><th>订单</th><th>用户</th><th>金额</th><th>状态</th><th>订阅一致性</th><th/></> : <><th>申请</th><th>用户</th><th>企业</th><th>金额</th><th>状态</th><th/></>}</tr></thead><tbody>{list.data.items.map((item) => tab === "orders" ? <tr key={text(item.id)}><td><strong>{text(item.membership_name)}</strong><small>{text(item.id)}</small></td><td>{text((item.user as Data)?.name)}<small>{text((item.user as Data)?.email)}</small></td><td>¥{number(item.amount).toFixed(2)}</td><td><Status value={item.status}/></td><td>{item.requires_reconciliation ? <span className="danger-text">需要同步</span> : "正常"}</td><td><button className="row-link" onClick={() => setSelected(text(item.id))}>查看 <ChevronRight size={15}/></button></td></tr> : <tr key={text(item.id)}><td><strong>{text(item.id)}</strong><small>{dateTime(item.requested_at)}</small></td><td>{text((item.user as Data)?.name)}</td><td>{text(item.company_name)}</td><td>¥{number(item.amount).toFixed(2)}</td><td><Status value={item.status}/></td><td><button className="row-link" onClick={() => setSelected(text(item.id))}>处理 <ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>}<Pagination page={page} pageSize={pageSize} total={list.data?.total || 0} onPageChange={setPage} onPageSizeChange={(value) => { setPageSize(value); setPage(1); }}/></>}</Panel>
    {selected && <Drawer title={tab === "orders" ? "订单详情" : "发票详情"} onClose={() => setSelected("")}>{detail.loading ? <Loading/> : detail.data ? <div className="detail-stack"><JsonBlock title="业务信息" value={detail.data}/><div className="action-row">{tab === "orders" && detail.data.product_type !== "credit_package" && detail.data.status === "paid" && detail.data.subscription_consistent === false && <Button tone="primary" onClick={() => setAction("reconcile")}>同步订阅</Button>}{tab === "invoices" && detail.data.status === "requested" && <Button tone="primary" onClick={() => setAction("accept")}>受理</Button>}{tab === "invoices" && ["requested", "processing"].includes(text(detail.data.status)) && <Button tone="danger" onClick={() => setAction("reject")}>驳回</Button>}{tab === "invoices" && detail.data.status === "processing" && <Button tone="primary" onClick={() => setAction("issue")}>标记已开具</Button>}</div></div> : <div className="admin-error">{detail.error}</div>}</Drawer>}
    {action && <ActionDialog title={action === "reconcile" ? "同步订单与订阅" : action === "accept" ? "受理发票申请" : action === "reject" ? "驳回发票申请" : "标记发票已开具"} description={action === "reconcile" ? "使用该用户最新的已支付订单修复当前订阅状态。" : action === "accept" ? "发票申请将进入处理中状态。" : action === "reject" ? "用户将看到驳回状态和本次操作原因。" : "保存正式发票号码并完成状态流转。"} target={selected} warning={action === "reconcile" || action === "reject" ? "该操作会改变用户可见的业务状态。" : undefined} confirmPhrase={action === "accept" ? undefined : selected} confirmText={action === "reconcile" ? "确认同步" : action === "accept" ? "确认受理" : action === "reject" ? "确认驳回" : "确认开具"} tone={action === "reject" ? "danger" : "primary"} onClose={() => setAction(null)} onSubmit={submitAction}>{action === "issue" && <FormField label="正式发票号码"><input name="invoice_number" minLength={3} maxLength={100} required/></FormField>}</ActionDialog>}
  </div>;
}

function Pricing({ admin }: { admin: AdminProfile }) {
  const canRead = admin.permissions.includes("pricing.read");
  const canWrite = admin.permissions.includes("pricing.write");
  const canPublish = admin.permissions.includes("pricing.publish");
  const [refresh, setRefresh] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Data>>({});
  const [publishOpen, setPublishOpen] = useState(false);
  const { notify } = useAdminToast();
  const catalogs = useRemote<{ items: Data[] }>(canRead ? "/api/admin/billing/catalogs" : null, refresh);
  useEffect(() => {
    if (!selectedId && catalogs.data?.items.length) {
      const preferred = catalogs.data.items.find((item) => item.status === "draft")
        || catalogs.data.items.find((item) => item.status === "published")
        || catalogs.data.items[0];
      setSelectedId(text(preferred?.id));
    }
  }, [catalogs.data, selectedId]);
  const detail = useRemote<Data>(selectedId ? `/api/admin/billing/catalogs/${selectedId}` : null, refresh);
  useEffect(() => {
    if (!detail.data) return;
    const next: Record<string, Data> = {};
    (detail.data.plans as Data[] || []).forEach((item) => { next[`plan:${text(item.plan_code)}`] = { ...item }; });
    (detail.data.credit_packages as Data[] || []).forEach((item) => { next[`package:${text(item.package_code)}`] = { ...item }; });
    (detail.data.skus as Data[] || []).forEach((item) => {
      next[`sku:${text(item.sku)}`] = {
        ...(item.rate as Data || {}),
        sku: item.sku,
        active: item.active,
      };
    });
    setDrafts(next);
  }, [detail.data]);
  if (!canRead) return <div className="admin-error">当前角色没有 pricing.read 权限。</div>;
  const setDraftValue = (key: string, field: string, value: unknown) => setDrafts((items) => ({ ...items, [key]: { ...(items[key] || {}), [field]: value } }));
  const save = async (path: string, body: Data, label: string) => {
    await api(path, { method: "PATCH", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });
    notify(`${label}已保存`); setRefresh((value) => value + 1);
  };
  const createDraft = async () => {
    const source = catalogs.data?.items.find((item) => item.status === "published")?.id;
    const key = `videox-${new Date().toISOString().replaceAll("-", "").replaceAll(":", "").replaceAll("T", "").replaceAll("Z", "").replaceAll(".", "").slice(0, 14)}`;
    const created = await api<Data>("/api/admin/billing/catalogs", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ version_key: key, source_catalog_id: source || null, notes: "从运营后台创建的定价草稿" }),
    });
    setSelectedId(text(created.id)); setRefresh((value) => value + 1); notify("新的商业目录草稿已创建");
  };
  const publish = async (values: Record<string, string>) => {
    await api(`/api/admin/billing/catalogs/${selectedId}/publish`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ reason: values.reason }) });
    notify("商业目录已发布"); setPublishOpen(false); setRefresh((value) => value + 1);
  };
  const isDraft = detail.data?.status === "draft";
  const plans = (detail.data?.plans as Data[] || []);
  const packages = (detail.data?.credit_packages as Data[] || []);
  const skus = (detail.data?.skus as Data[] || []);
  const planCodes = plans.map((plan) => text(plan.plan_code));
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">PRICING CONTROL</p><h1>商业配置</h1><p>版本化调整套餐、充值包和模型点数；只有发布后才会影响新报价。</p></div><div className="action-row">{canWrite && <Button onClick={createDraft}><RefreshCw size={14}/>复制当前目录</Button>}{canPublish && isDraft && <Button tone="primary" onClick={() => setPublishOpen(true)}>发布草稿</Button>}</div></div>
    <div className="admin-filter-row"><div className="inline-filters"><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">选择目录</option>{catalogs.data?.items.map((item) => <option key={text(item.id)} value={text(item.id)}>{text(item.version_key)} · {text(item.status)}</option>)}</select><Status value={detail.data?.status}/></div><span className="admin-muted">目录 ID：{text(detail.data?.id)}</span></div>
    {catalogs.loading || detail.loading ? <Loading/> : catalogs.error || detail.error ? <div className="admin-error">{catalogs.error || detail.error}</div> : !detail.data ? <Empty>还没有商业目录</Empty> : <>
      <Panel title="套餐价格与积分">
        <div className="admin-table-wrap"><table><thead><tr><th>方案</th><th>月付（元）</th><th>年付（元）</th><th>月积分</th><th>注册赠送</th><th>滚存周期</th><th>充值加成</th><th/></tr></thead><tbody>{plans.map((plan) => {
          const key = `plan:${text(plan.plan_code)}`;
          const row = drafts[key] || plan;
          return <tr key={key}>
            <td><strong>{text(plan.display_name)}</strong><small>{text(plan.plan_code)}</small></td>
            <td><input aria-label={`${text(plan.display_name)}月付价格`} className="admin-inline-input" type="number" min="0" step="0.01" disabled={!canWrite || !isDraft} value={(number(row.monthly_price_fen) / 100).toFixed(2)} onChange={(event) => setDraftValue(key, "monthly_price_fen", Math.round(Number(event.target.value) * 100))}/></td>
            <td><input aria-label={`${text(plan.display_name)}年付价格`} className="admin-inline-input" type="number" min="0" step="0.01" disabled={!canWrite || !isDraft} value={(number(row.annual_price_fen) / 100).toFixed(2)} onChange={(event) => setDraftValue(key, "annual_price_fen", Math.round(Number(event.target.value) * 100))}/></td>
            <td><input aria-label={`${text(plan.display_name)}月积分`} className="admin-inline-input" type="number" min="0" step="1" disabled={!canWrite || !isDraft} value={number(row.monthly_credits)} onChange={(event) => setDraftValue(key, "monthly_credits", Number(event.target.value))}/></td>
            <td><input aria-label={`${text(plan.display_name)}注册赠送`} className="admin-inline-input" type="number" min="0" step="1" disabled={!canWrite || !isDraft} value={number(row.signup_credits)} onChange={(event) => setDraftValue(key, "signup_credits", Number(event.target.value))}/></td>
            <td><input aria-label={`${text(plan.display_name)}滚存周期`} className="admin-inline-input" type="number" min="0" max="120" step="1" disabled={!canWrite || !isDraft} value={number(row.rollover_cycles)} onChange={(event) => setDraftValue(key, "rollover_cycles", Number(event.target.value))}/></td>
            <td><span className="admin-input-suffix"><input aria-label={`${text(plan.display_name)}充值加成`} className="admin-inline-input" type="number" min="0" max="100" step="0.01" disabled={!canWrite || !isDraft} value={(number(row.recharge_bonus_bps) / 100).toFixed(2)} onChange={(event) => setDraftValue(key, "recharge_bonus_bps", Math.round(Number(event.target.value) * 100))}/><span>%</span></span></td>
            <td>{canWrite && isDraft && <Button onClick={() => save(`/api/admin/billing/catalogs/${selectedId}/plans/${encodeURIComponent(text(plan.plan_code))}`, { monthly_price_fen: row.monthly_price_fen, annual_price_fen: row.annual_price_fen, monthly_credits: row.monthly_credits, signup_credits: row.signup_credits, rollover_cycles: row.rollover_cycles, recharge_bonus_bps: row.recharge_bonus_bps }, `${text(plan.display_name)} 价格与积分`)}>保存</Button>}</td>
          </tr>;
        })}</tbody></table></div>
      </Panel>
      <Panel title="套餐权益与限制">
        <div className="admin-table-wrap"><table><thead><tr><th>方案</th><th>并发</th><th>存储（GB）</th><th>席位</th><th>队列优先级</th><th>模型权限</th><th>分辨率上限</th><th>授权</th><th/></tr></thead><tbody>{plans.map((plan) => {
          const key = `plan:${text(plan.plan_code)}`;
          const row = drafts[key] || plan;
          return <tr key={`${key}:entitlements`}>
            <td><strong>{text(plan.display_name)}</strong><small>{text(plan.plan_code)}</small></td>
            <td><input aria-label={`${text(plan.display_name)}并发数`} className="admin-inline-input" type="number" min="1" step="1" disabled={!canWrite || !isDraft} value={number(row.generation_concurrency)} onChange={(event) => setDraftValue(key, "generation_concurrency", Number(event.target.value))}/></td>
            <td><input aria-label={`${text(plan.display_name)}存储空间`} className="admin-inline-input" type="number" min="0" step="1" disabled={!canWrite || !isDraft} value={Math.round(number(row.storage_bytes) / 1024 ** 3)} onChange={(event) => setDraftValue(key, "storage_bytes", Math.round(Number(event.target.value) * 1024 ** 3))}/></td>
            <td><input aria-label={`${text(plan.display_name)}席位数`} className="admin-inline-input" type="number" min="1" step="1" disabled={!canWrite || !isDraft} value={number(row.seat_limit)} onChange={(event) => setDraftValue(key, "seat_limit", Number(event.target.value))}/></td>
            <td><input aria-label={`${text(plan.display_name)}队列优先级`} className="admin-inline-input" type="number" min="0" max="100" step="1" disabled={!canWrite || !isDraft} value={number(row.queue_priority)} onChange={(event) => setDraftValue(key, "queue_priority", Number(event.target.value))}/></td>
            <td><select aria-label={`${text(plan.display_name)}模型权限`} disabled={!canWrite || !isDraft} value={text(row.model_access_level, "basic")} onChange={(event) => setDraftValue(key, "model_access_level", event.target.value)}><option value="basic">Basic</option><option value="standard">Standard</option><option value="advanced">Advanced</option></select></td>
            <td><div className="admin-compact-stack"><input aria-label={`${text(plan.display_name)}视频分辨率上限`} className="admin-inline-input" disabled={!canWrite || !isDraft} value={text(row.max_video_resolution, "720p")} onChange={(event) => setDraftValue(key, "max_video_resolution", event.target.value)}/><input aria-label={`${text(plan.display_name)}图片分辨率上限`} className="admin-inline-input" disabled={!canWrite || !isDraft} value={text(row.max_image_resolution, "1k")} onChange={(event) => setDraftValue(key, "max_image_resolution", event.target.value)}/></div></td>
            <td><div className="admin-checkbox-stack"><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.watermark_required)} onChange={(event) => setDraftValue(key, "watermark_required", event.target.checked)}/>水印</label><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.commercial_use)} onChange={(event) => setDraftValue(key, "commercial_use", event.target.checked)}/>商用</label><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.api_access)} onChange={(event) => setDraftValue(key, "api_access", event.target.checked)}/>API</label><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.batch_access)} onChange={(event) => setDraftValue(key, "batch_access", event.target.checked)}/>批量</label></div></td>
            <td>{canWrite && isDraft && <Button onClick={() => save(`/api/admin/billing/catalogs/${selectedId}/plans/${encodeURIComponent(text(plan.plan_code))}`, { generation_concurrency: row.generation_concurrency, storage_bytes: row.storage_bytes, seat_limit: row.seat_limit, queue_priority: row.queue_priority, model_access_level: row.model_access_level, max_video_resolution: row.max_video_resolution, max_image_resolution: row.max_image_resolution, watermark_required: row.watermark_required, commercial_use: row.commercial_use, api_access: row.api_access, batch_access: row.batch_access }, `${text(plan.display_name)} 权益`)}>保存</Button>}</td>
          </tr>;
        })}</tbody></table></div>
      </Panel>
      <Panel title="充值包"><div className="admin-table-wrap"><table><thead><tr><th>充值包</th><th>价格（元）</th><th>基础积分</th><th>包赠送</th><th>排序</th><th>启用</th><th/></tr></thead><tbody>{packages.map((item) => {
        const key = `package:${text(item.package_code)}`;
        const row = drafts[key] || item;
        return <tr key={key}>
          <td><strong>{text(item.display_name)}</strong><small>{text(item.package_code)}</small></td>
          <td><input aria-label={`${text(item.display_name)}价格`} className="admin-inline-input" type="number" min="0.01" step="0.01" disabled={!canWrite || !isDraft} value={(number(row.price_fen) / 100).toFixed(2)} onChange={(event) => setDraftValue(key, "price_fen", Math.round(Number(event.target.value) * 100))}/></td>
          <td><input aria-label={`${text(item.display_name)}基础积分`} className="admin-inline-input" type="number" min="1" step="1" disabled={!canWrite || !isDraft} value={number(row.base_credits)} onChange={(event) => setDraftValue(key, "base_credits", Number(event.target.value))}/></td>
          <td><span className="admin-input-suffix"><input aria-label={`${text(item.display_name)}赠送比例`} className="admin-inline-input" type="number" min="0" max="100" step="0.01" disabled={!canWrite || !isDraft} value={(number(row.package_bonus_bps) / 100).toFixed(2)} onChange={(event) => setDraftValue(key, "package_bonus_bps", Math.round(Number(event.target.value) * 100))}/><span>%</span></span></td>
          <td><input aria-label={`${text(item.display_name)}排序`} className="admin-inline-input" type="number" min="0" step="1" disabled={!canWrite || !isDraft} value={number(row.sort_order)} onChange={(event) => setDraftValue(key, "sort_order", Number(event.target.value))}/></td>
          <td><label className="admin-inline-check"><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.active)} onChange={(event) => setDraftValue(key, "active", event.target.checked)}/><span>{row.active ? "启用" : "停用"}</span></label></td>
          <td>{canWrite && isDraft && <Button onClick={() => save(`/api/admin/billing/catalogs/${selectedId}/packages/${encodeURIComponent(text(item.package_code))}`, { price_fen: row.price_fen, base_credits: row.base_credits, package_bonus_bps: row.package_bonus_bps, sort_order: row.sort_order, active: row.active }, `${text(item.display_name)} 充值包`)}>保存</Button>}</td>
        </tr>;
      })}</tbody></table></div></Panel>
      <Panel title="模型 / 功能点数"><div className="admin-table-wrap"><table><thead><tr><th>SKU</th><th>单位</th><th>费率（积分）</th><th>最低积分</th><th>可用方案</th><th>状态</th><th/></tr></thead><tbody>{skus.map((item) => {
        const key = `sku:${text(item.sku)}`;
        const row = drafts[key] || (item.rate as Data) || {};
        return <tr key={key}>
          <td><strong>{text(item.display_name)}</strong><small>{text(item.sku)}</small></td>
          <td>{text(item.unit)}</td>
          <td><input aria-label={`${text(item.display_name)}费率`} className="admin-inline-input" type="number" min="1" step="1" disabled={!canWrite || !isDraft} value={number(row.credits_per_unit)} onChange={(event) => setDraftValue(key, "credits_per_unit", Number(event.target.value))}/></td>
          <td><input aria-label={`${text(item.display_name)}最低积分`} className="admin-inline-input" type="number" min="0" step="1" disabled={!canWrite || !isDraft} value={number(row.minimum_credits)} onChange={(event) => setDraftValue(key, "minimum_credits", Number(event.target.value))}/></td>
          <td><select aria-label={`${text(item.display_name)}可用方案`} className="admin-plan-select" multiple disabled={!canWrite || !isDraft} value={(row.allowed_plan_codes as string[]) || []} onChange={(event) => setDraftValue(key, "allowed_plan_codes", Array.from(event.target.selectedOptions, (option) => option.value))}>{planCodes.map((code) => <option key={code} value={code}>{code}</option>)}</select></td>
          <td><div className="admin-checkbox-stack"><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.active)} onChange={(event) => setDraftValue(key, "active", event.target.checked)}/>启用</label><label><input type="checkbox" disabled={!canWrite || !isDraft} checked={Boolean(row.included_in_pass)} onChange={(event) => setDraftValue(key, "included_in_pass", event.target.checked)}/>畅享卡</label></div></td>
          <td>{canWrite && isDraft && <Button onClick={() => save(`/api/admin/billing/catalogs/${selectedId}/skus/${encodeURIComponent(text(item.sku))}`, { credits_per_unit: row.credits_per_unit, minimum_credits: row.minimum_credits, allowed_plan_codes: row.allowed_plan_codes, included_in_pass: row.included_in_pass, active: row.active }, `${text(item.display_name)} 费率`)}>保存</Button>}</td>
        </tr>;
      })}</tbody></table></div></Panel>
    </>}
    {publishOpen && <ActionDialog title="发布商业目录" description="发布后，新注册、订阅、充值和任务报价都会读取该目录；历史订单与任务保留原有快照。" target={selectedId} warning="发布会自动退休当前已发布目录，请确认所有价格和费率已复核。" confirmPhrase={selectedId} confirmText="确认发布" onClose={() => setPublishOpen(false)} onSubmit={publish}/>}
  </div>;
}

function Audit() {
  const initial = useMemo(() => readHashParams(), []);
  const [actionInput, setActionInput] = useState(initial.get("action") || "");
  const [action, setAction] = useState(initial.get("action") || "");
  const [status, setStatus] = useState(initial.get("status") || "");
  const [sort, setSort] = useState(initial.get("sort") || "created_desc");
  const [page, setPage] = useState(Number(initial.get("page") || 1));
  const [pageSize, setPageSize] = useState(Number(initial.get("page_size") || 20));
  const [selected, setSelected] = useState<Data | null>(null);
  useEffect(() => writeHashParams("audit", { action, status, sort, page, page_size: pageSize }), [action, status, sort, page, pageSize]);
  const list = useRemote<ListResponse>(`/api/admin/audit-logs?action=${encodeURIComponent(action)}&status=${encodeURIComponent(status)}&sort=${sort}&page=${page}&page_size=${pageSize}`);
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">AUDIT TRAIL</p><h1>审计</h1><p>查看管理员敏感读取、业务变更及失败记录。</p></div></div>
    <form className="admin-toolbar" onSubmit={(event) => { event.preventDefault(); setAction(actionInput.trim()); setPage(1); }}><Search size={18}/><input placeholder="精确操作类型，例如 JOB_RETRY" value={actionInput} onChange={(event) => setActionInput(event.target.value)}/><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option><option value="succeeded">成功</option><option value="failed">失败</option><option value="started">执行中</option></select><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="created_desc">时间：新到旧</option><option value="created_asc">时间：旧到新</option></select><Button type="submit" tone="primary">查询</Button></form>
    <Panel title={`审计记录${list.data ? ` · ${list.data.total}` : ""}`}>{list.loading ? <Loading/> : list.error ? <div className="admin-error">{list.error}</div> : <>{!list.data?.items.length ? <Empty/> : <div className="admin-table-wrap"><table><thead><tr><th>时间</th><th>管理员</th><th>操作</th><th>目标</th><th>状态</th><th>原因</th><th/></tr></thead><tbody>{list.data.items.map((item) => <tr key={text(item.id)}><td>{dateTime(item.created_at)}</td><td>{text((item.admin as Data)?.name)}<small>{text((item.admin as Data)?.role)}</small></td><td><code>{text(item.action)}</code></td><td>{text(item.target_type)}<small>{text(item.target_id)}</small></td><td><Status value={item.status}/></td><td className="reason-cell">{text(item.reason)}</td><td><button className="row-link" onClick={() => setSelected(item)}>查看</button></td></tr>)}</tbody></table></div>}<Pagination page={page} pageSize={pageSize} total={list.data?.total || 0} onPageChange={setPage} onPageSizeChange={(value) => { setPageSize(value); setPage(1); }}/></>}</Panel>
    {selected && <Drawer title="审计详情" onClose={() => setSelected(null)}><div className="detail-stack"><DetailGrid data={{ 操作: selected.action, 状态: <Status value={selected.status}/>, 目标类型: selected.target_type, 目标ID: selected.target_id, 管理员: (selected.admin as Data)?.name, 时间: dateTime(selected.created_at), 请求ID: selected.request_id }}/><section className="audit-reason"><span>操作原因</span><p>{text(selected.reason)}</p>{Boolean(selected.error_message) && <div className="admin-error">{text(selected.error_message)}</div>}</section><ChangeSummary before={(selected.before_data || {}) as Data} after={(selected.after_data || {}) as Data}/><JsonBlock title="完整原始记录" value={selected}/></div></Drawer>}
  </div>;
}

function Security() {
  const [refresh, setRefresh] = useState(0);
  const [action, setAction] = useState<"others" | string | null>(null);
  const sessions = useRemote<{ items: Data[] }>("/api/admin/auth/sessions", refresh);
  const { notify } = useAdminToast();
  const submitAction = async (values: Record<string, string>) => {
    const path = action === "others" ? "/api/admin/auth/sessions/revoke-others" : `/api/admin/auth/sessions/${action}/revoke`;
    await api(path, { method: "POST", body: JSON.stringify({ reason: values.reason }) });
    notify(action === "others" ? "其他管理员会话已全部撤销" : "指定管理员会话已撤销");
    setRefresh((value) => value + 1);
  };
  const otherCount = sessions.data?.items.filter((session) => !session.current).length || 0;
  return <div className="admin-stack">
    <div className="admin-page-title"><div><p className="eyebrow">SESSION SECURITY</p><h1>会话安全</h1><p>查看当前管理员的登录设备，并撤销不再使用的会话。</p></div><Button tone="danger" disabled={!otherCount} onClick={() => setAction("others")}>退出其他设备</Button></div>
    <Panel title={`有效会话 · ${sessions.data?.items.length || 0}`}>{sessions.loading ? <Loading/> : sessions.error ? <div className="admin-error">{sessions.error}</div> : !sessions.data?.items.length ? <Empty/> : <div className="session-list">{sessions.data.items.map((session) => <article key={text(session.id)}><div className="session-icon"><LockKeyhole size={18}/></div><div><div className="session-title"><strong>{session.current ? "当前会话" : "其他设备"}</strong>{Boolean(session.current) && <Status value="active"/>}</div><p>{text(session.user_agent, "未知浏览器")}</p><small>IP {text(session.ip_address)} · 最近活动 {dateTime(session.last_seen_at)} · 到期 {dateTime(session.expires_at)}</small></div><Button tone="danger" disabled={Boolean(session.current)} onClick={() => setAction(text(session.id))}>{session.current ? "当前设备" : "撤销"}</Button></article>)}</div>}</Panel>
    {action && <ActionDialog title={action === "others" ? "退出其他设备" : "撤销管理员会话"} description={action === "others" ? `将撤销除当前设备外的 ${otherCount} 个有效会话。` : "该设备下一次请求或刷新令牌时将立即失去后台访问权限。"} target={action === "others" ? "当前管理员的其他会话" : action} confirmPhrase={action === "others" ? "退出其他设备" : action} confirmText="确认撤销" tone="danger" onClose={() => setAction(null)} onSubmit={submitAction}/>}
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
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [result, setResult] = useState<Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler);
  }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (q.trim().length < 2) return;
    setLoading(true); setError("");
    try { setResult(await api<Data>(`/api/admin/search?q=${encodeURIComponent(q.trim())}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "搜索失败"); }
    finally { setLoading(false); }
  };
  return <><button type="button" className="global-search-trigger" onClick={() => setOpen(true)}><Search size={17}/><span>搜索后台</span><kbd>⌘ K</kbd></button>{open && <div className="search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}><div className="search-dialog"><form onSubmit={submit}><Search/><input autoFocus placeholder="搜索用户、任务、项目、订单或发票" value={q} onChange={(event) => setQ(event.target.value)}/><button type="button" aria-label="关闭搜索" onClick={() => setOpen(false)}><X/></button></form><div className="search-results">{loading ? <Loading/> : error ? <div className="admin-error">{error}</div> : result ? Object.entries(result).flatMap(([group, values]) => (values as Data[]).map((item) => <button type="button" key={`${group}-${text(item.id)}`} onClick={() => { onOpen(text(item.type), text(item.id)); setOpen(false); }}><span><b>{text(item.name, text(item.id))}</b><small>{group} · {text(item.id)}</small></span><ChevronRight/></button>)) : <Empty>输入至少两个字符开始搜索</Empty>}</div></div></div>}</>;
}

function AdminRoot() {
  const [admin, setAdmin] = useState<AdminProfile | null>(null);
  const [booting, setBooting] = useState(true);
  const route = location.hash.slice(2).split("?")[0];
  const hashView = (route.split("/")[0] || "dashboard") as View;
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
    if (view === "pricing") return <Pricing admin={admin as AdminProfile}/>;
    if (view === "audit") return <Audit/>;
    if (view === "security") return <Security/>;
    return <Dashboard/>;
  }, [admin, view, selected]);
  if (booting) return <div className="admin-boot"><LoaderCircle className="spin"/><span>正在恢复安全会话</span></div>;
  if (!admin) return <Login onLogin={setAdmin}/>;
  return <div className="admin-layout"><aside className="admin-sidebar"><div className="sidebar-brand"><img className="admin-brand-mark small" src="/favicon.svg" alt=""/><div><strong>VideoX</strong><span>运营后台</span></div></div><span className="sidebar-section-label">管理</span><nav aria-label="运营后台导航">{NAV.map((item) => { const Icon = item.icon; return <button type="button" className={view === item.id ? "active" : ""} key={item.id} onClick={() => navigate(item.id)}><Icon size={18}/>{item.label}</button>; })}</nav><div className="sidebar-footer"><div><span className="admin-avatar">{admin.name.slice(0, 1)}</span><span><strong>{admin.name}</strong><small>{ROLE_NAMES[admin.role] || admin.role}</small></span></div><button type="button" aria-label="退出运营后台" title="退出" onClick={async () => { await logoutAdmin(); setAdmin(null); }}><LogOut size={18}/></button></div></aside><main className="admin-main"><header className="admin-topbar"><div className="topbar-context"><span>运营控制台</span><div className="environment-banner"><Activity size={13}/>{location.hostname.includes("localhost") ? "开发环境" : "生产环境"}</div></div><GlobalSearch onOpen={openSearchResult}/></header><div className="admin-content">{content}</div></main></div>;
}

export default function AdminApp() {
  return <AdminToastProvider><AdminRoot/></AdminToastProvider>;
}
