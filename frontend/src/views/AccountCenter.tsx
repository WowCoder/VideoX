// ──────────────────────────────────────────────
// OpenVMA - 个人中心
// 页签：账户概览 / 会员方案 / 用量中心 / 账单与发票 / 账户设置
// ──────────────────────────────────────────────

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  CircleUserRound,
  CreditCard,
  Crown,
  Gauge,
  Loader2,
  ReceiptText,
  Settings,
  Download,
  FileCheck2,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import {
  listMemberships,
  getUsage,
  listOrders,
  listInvoices,
  createInvoiceApplication,
  downloadInvoiceApplication,
  upgradeMembership,
  type BillingInvoice,
  type BillingOrder,
  type MembershipPlan,
  type UsageData,
} from "@/api/billing";

type Section = "overview" | "membership" | "usage" | "billing" | "settings";

const sections: { id: Section; label: string; icon: typeof CircleUserRound; copy: string }[] = [
  { id: "overview", label: "账户概览", icon: CircleUserRound, copy: "账户信息与会员概览" },
  { id: "membership", label: "会员方案", icon: Crown, copy: "升级方案或管理续费" },
  { id: "usage", label: "用量中心", icon: Gauge, copy: "处理时长与 AI 额度" },
  { id: "billing", label: "账单与发票", icon: ReceiptText, copy: "付款记录与电子票据" },
  { id: "settings", label: "账户设置", icon: Settings, copy: "资料、通知与安全" },
];

export function AccountCenter() {
  const { notify } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const updateSettings = useAuthStore((s) => s.updateSettings);
  const [section, setSection] = useState<Section>("overview");

  // 获取会员方案列表
  const membershipsQuery = useQuery({
    queryKey: ["memberships"],
    queryFn: listMemberships,
    retry: false,
  });

  // 获取当前用量
  const usageQuery = useQuery({
    queryKey: ["usage"],
    queryFn: getUsage,
    retry: false,
  });
  const ordersQuery = useQuery({
    queryKey: ["billing-orders"],
    queryFn: listOrders,
    retry: false,
  });
  const invoicesQuery = useQuery({
    queryKey: ["billing-invoices"],
    queryFn: listInvoices,
    retry: false,
  });

  const memberships = membershipsQuery.data;
  const usage = usageQuery.data;
  const orders = ordersQuery.data ?? [];
  const invoices = invoicesQuery.data ?? [];
  const loadingMemberships = membershipsQuery.isLoading;
  const dataError = membershipsQuery.error ?? usageQuery.error ?? ordersQuery.error ?? invoicesQuery.error;

  // 当前用户的会员方案
  const currentMembership =
    memberships?.find((m) => m.id === user?.membership?.id) ?? memberships?.[0];

  // 升级会员
  const handleUpgrade = async (membershipId: string, billingCycle: string = "monthly") => {
    try {
      const result = await upgradeMembership(membershipId, billingCycle);
      if (result.payUrl) {
        window.open(result.payUrl, "_blank");
      }
      notify(result.message || "订单已创建");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "升级失败，请稍后重试";
      notify(msg, "error");
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-text">个人中心</h1>
        <p className="mt-1.5 text-sm text-muted">管理账户信息、会员、用量与设置</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        {/* 左侧页签 */}
        <nav className="space-y-1">
          {sections.map((s) => {
            const Icon = s.icon;
            const active = section === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-left text-sm transition ${
                  active
                    ? "bg-blue text-white shadow-soft"
                    : "text-muted hover:bg-canvas hover:text-text"
                }`}
                type="button"
              >
                <Icon size={17} />
                <span>{s.label}</span>
              </button>
            );
          })}
        </nav>

        {/* 右侧内容 */}
        <div className="rounded-2xl border border-line bg-surface p-6 shadow-soft">
          {dataError ? (
            <div className="rounded-xl border border-red/20 bg-red/5 py-12 text-center">
              <p className="text-sm font-medium text-red">账户数据加载失败</p>
              <p className="mt-1 text-xs text-muted">{dataError instanceof Error ? dataError.message : "请检查后端服务"}</p>
              <button
                type="button"
                onClick={() => {
                  void membershipsQuery.refetch();
                  void usageQuery.refetch();
                  void ordersQuery.refetch();
                  void invoicesQuery.refetch();
                }}
                className="mt-4 rounded-lg bg-blue px-3 py-2 text-sm text-white"
              >
                重试
              </button>
            </div>
          ) : section === "overview" ? (
            <OverviewSection user={user} usage={usage} membership={currentMembership} orderCount={orders.length} />
          ) : section === "membership" ? (
            <MembershipSection
              memberships={memberships ?? []}
              loading={loadingMemberships}
              currentId={currentMembership?.id}
              onUpgrade={handleUpgrade}
            />
          ) : section === "usage" ? <UsageSection usage={usage} membership={currentMembership} />
          : section === "billing" ? (
            <BillingSection
              orders={orders}
              invoices={invoices}
              defaultEmail={user?.email ?? ""}
              onChanged={() => void invoicesQuery.refetch()}
              notify={notify}
            />
          )
          : (
            <SettingsSection
              user={user}
              onSave={async (data) => {
                try {
                  await updateSettings(data);
                  notify("账户设置已保存");
                } catch (error) {
                  notify(error instanceof Error ? error.message : "账户设置保存失败", "error");
                }
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ── 账户概览 ── */
function OverviewSection({
  user,
  usage,
  membership,
  orderCount,
}: {
  user: ReturnType<typeof useAuthStore.getState>["user"];
  usage?: UsageData;
  membership?: MembershipPlan;
  orderCount: number;
}) {
  const name = user?.name || "用户";
  const email = user?.email || "";
  const initial = user?.initial || "U";
  const memName = membership?.name || "Free";
  const usedMinutes = usage?.processingMinutesUsed ?? 0;
  const totalMinutes = membership?.processingMinutes ?? 600;

  return (
    <div>
      <div className="flex items-center gap-4 border-b border-line pb-5">
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-xl font-semibold text-white">
          {initial}
        </span>
        <div>
          <h2 className="text-lg font-bold text-text">{name}</h2>
          <p className="text-sm text-muted">{email}</p>
          <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-blue-soft px-2.5 py-0.5 text-xs font-medium text-blue">
            <Crown size={12} />{memName} 会员
          </span>
        </div>
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-line bg-canvas/40 p-4">
          <Gauge size={18} className="text-blue" />
          <strong className="mt-2 block text-lg font-semibold text-text">
            {usedMinutes} / {totalMinutes}
          </strong>
          <small className="text-xs text-muted">处理时长（分钟）</small>
        </div>
        <div className="rounded-xl border border-line bg-canvas/40 p-4">
          <CreditCard size={18} className="text-teal" />
          <strong className="mt-2 block text-lg font-semibold text-text">{memName}</strong>
          <small className="text-xs text-muted">当前会员方案</small>
        </div>
        <div className="rounded-xl border border-line bg-canvas/40 p-4">
          <ReceiptText size={18} className="text-amber" />
          <strong className="mt-2 block text-lg font-semibold text-text">{orderCount}</strong>
          <small className="text-xs text-muted">历史账单数</small>
        </div>
      </div>
      {(membership?.id === "free" || !membership?.price) && (
        <div className="mt-5 rounded-xl border border-blue/20 bg-blue-soft/30 p-4">
          <div className="flex items-center gap-2">
            <Crown size={16} className="text-amber" />
            <strong className="text-sm text-text">升级到 Pro 会员</strong>
          </div>
          <p className="mt-1.5 text-xs text-muted">
            升级后按所选方案解锁更高处理时长、AI 额度、存储空间与导出次数。
          </p>
        </div>
      )}
    </div>
  );
}

/* ── 会员方案 ── */
function MembershipSection({
  memberships,
  loading,
  currentId,
  onUpgrade,
}: {
  memberships: MembershipPlan[];
  loading: boolean;
  currentId?: string;
  onUpgrade: (id: string, cycle?: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 size={24} className="animate-spin text-muted" />
      </div>
    );
  }

  if (memberships.length === 0) {
    return (
      <div>
        <h2 className="mb-4 text-lg font-bold text-text">会员方案</h2>
        <div className="rounded-xl border border-dashed border-line py-12 text-center">
          <Crown size={28} className="mx-auto text-line" />
          <p className="mt-3 text-sm text-muted">暂无可用的会员方案</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-bold text-text">会员方案</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        {memberships.map((plan) => {
          const isCurrent = plan.id === currentId;
          const isRecommended = plan.rank === 1;
          return (
            <div
              key={plan.id}
              className={`relative rounded-2xl border p-5 ${
                isRecommended ? "border-blue shadow-soft" : "border-line"
              }`}
            >
              {isRecommended && (
                <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-blue px-3 py-0.5 text-[11px] font-medium text-white">
                  最受欢迎
                </span>
              )}
              <strong className="block text-base text-text">{plan.name}</strong>
              <div className="mt-2">
                <span className="text-2xl font-bold text-text">¥{plan.price}</span>
                <span className="text-sm text-muted">/ 月</span>
              </div>
              <ul className="mt-4 space-y-2 text-xs text-muted">
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-teal" />
                  {plan.processingMinutes} 分钟处理时长
                </li>
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-teal" />
                  {plan.aiImageQuota} 张 AI 生图额度
                </li>
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-teal" />
                  {plan.aiVideoQuota} 段 AI 生视频额度
                </li>
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-teal" />
                  {plan.exportQuota} 次导出
                </li>
                {plan.rank > 0 && (
                  <li className="flex items-center gap-1.5">
                    <Check size={13} className="text-teal" />
                    无水印导出
                  </li>
                )}
              </ul>
              <button
                onClick={() => !isCurrent && onUpgrade(plan.id)}
                disabled={isCurrent}
                className={`mt-5 w-full rounded-lg py-2 text-sm font-semibold transition ${
                  isCurrent
                    ? "border border-line text-muted cursor-default"
                    : isRecommended
                      ? "bg-blue text-white hover:bg-blue-2"
                      : "border border-line text-text hover:bg-canvas"
                }`}
                type="button"
              >
                {isCurrent ? "当前方案" : plan.price > 0 ? "前往支付升级" : "切换到此方案"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── 用量中心 ── */
function UsageSection({
  usage,
  membership,
}: {
  usage?: UsageData;
  membership?: MembershipPlan;
}) {
  const usages = [
    {
      label: "处理时长",
      used: usage?.processingMinutesUsed ?? 0,
      total: membership?.processingMinutes ?? 600,
      unit: "分钟",
    },
    {
      label: "AI 生图",
      used: usage?.aiImageUsed ?? 0,
      total: membership?.aiImageQuota ?? 100,
      unit: "张",
    },
    {
      label: "AI 生视频",
      used: usage?.aiVideoUsed ?? 0,
      total: membership?.aiVideoQuota ?? 20,
      unit: "段",
    },
    {
      label: "导出次数",
      used: usage?.exportUsed ?? 0,
      total: membership?.exportQuota ?? 10,
      unit: "次",
    },
  ];

  return (
    <div>
      <h2 className="mb-4 text-lg font-bold text-text">用量中心</h2>
      <div className="space-y-4">
        {usages.map((u) => {
          const percent = u.total > 0 ? Math.round((u.used / u.total) * 100) : 0;
          return (
            <div key={u.label} className="rounded-xl border border-line bg-canvas/40 p-4">
              <div className="flex items-center justify-between">
                <strong className="text-sm text-text">{u.label}</strong>
                <span className="text-sm text-muted">
                  <strong className="text-text">{u.used}</strong> / {u.total} {u.unit}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface">
                <div
                  className={`h-full rounded-full transition-all ${
                    percent > 80
                      ? "bg-red"
                      : percent > 50
                        ? "bg-amber"
                        : "bg-gradient-to-r from-blue to-teal"
                  }`}
                  style={{ width: `${percent}%` }}
                />
              </div>
              <small className="mt-1.5 block text-xs text-muted">已使用 {percent}%</small>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── 账单与发票 ── */
function BillingSection({
  orders,
  invoices,
  defaultEmail,
  onChanged,
  notify,
}: {
  orders: BillingOrder[];
  invoices: BillingInvoice[];
  defaultEmail: string;
  onChanged: () => void;
  notify: (text: string, tone?: "success" | "info" | "error") => void;
}) {
  const [selectedOrderId, setSelectedOrderId] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [taxNumber, setTaxNumber] = useState("");
  const [email, setEmail] = useState(defaultEmail);
  const [submitting, setSubmitting] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const invoiceByOrder = new Map(invoices.map((invoice) => [invoice.orderId, invoice]));
  const eligibleOrders = orders.filter(
    (order) => order.status === "paid" && !invoiceByOrder.has(order.orderId),
  );

  async function submitInvoice() {
    if (!selectedOrderId || !companyName.trim() || !taxNumber.trim() || !email.trim()) {
      notify("请完整填写开票申请信息", "error");
      return;
    }
    setSubmitting(true);
    try {
      await createInvoiceApplication({
        orderId: selectedOrderId,
        companyName: companyName.trim(),
        taxNumber: taxNumber.trim(),
        email: email.trim(),
      });
      setSelectedOrderId("");
      setCompanyName("");
      setTaxNumber("");
      onChanged();
      notify("开票申请已提交；当前生成的是申请单，不是电子发票");
    } catch (error) {
      notify(error instanceof Error ? error.message : "开票申请提交失败", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function downloadApplication(invoiceId: string) {
    setDownloadingId(invoiceId);
    try {
      await downloadInvoiceApplication(invoiceId);
      notify("开票申请单已下载");
    } catch (error) {
      notify(error instanceof Error ? error.message : "申请单下载失败", "error");
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div>
      <h2 className="text-lg font-bold text-text">账单与发票</h2>
      <div className="mt-3 rounded-xl border border-amber/20 bg-amber/5 p-3 text-xs leading-relaxed text-muted">
        当前尚未接入税务开票服务。这里提交并下载的是<strong className="text-amber">开票申请单</strong>，不是增值税电子发票，不具备报销或抵扣效力。
      </div>

      {eligibleOrders.length > 0 && (
        <section className="mt-5 rounded-xl border border-line bg-canvas/40 p-4">
          <h3 className="text-sm font-semibold text-text">提交开票申请</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span className="mb-1 block text-xs text-muted">已支付订单</span>
              <select value={selectedOrderId} onChange={(event) => setSelectedOrderId(event.target.value)} className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-text">
                <option value="">请选择订单</option>
                {eligibleOrders.map((order) => <option key={order.orderId} value={order.orderId}>{order.membershipName} · ¥{order.amount.toFixed(2)} · {new Date(order.createdAt).toLocaleDateString("zh-CN")}</option>)}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted">企业名称</span>
              <input value={companyName} onChange={(event) => setCompanyName(event.target.value)} className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-text" placeholder="与营业执照一致" />
            </label>
            <label>
              <span className="mb-1 block text-xs text-muted">纳税人识别号</span>
              <input value={taxNumber} onChange={(event) => setTaxNumber(event.target.value.toUpperCase())} className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-text" placeholder="数字或大写字母" />
            </label>
            <label className="sm:col-span-2">
              <span className="mb-1 block text-xs text-muted">接收邮箱</span>
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-text" />
            </label>
          </div>
          <div className="mt-3 flex justify-end">
            <button type="button" disabled={submitting} onClick={() => void submitInvoice()} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {submitting && <Loader2 size={14} className="animate-spin" />}提交申请
            </button>
          </div>
        </section>
      )}

      <h3 className="mb-3 mt-6 text-sm font-semibold text-text">付款记录</h3>
      {orders.length === 0 ? <div className="rounded-xl border border-dashed border-line py-12 text-center">
        <ReceiptText size={28} className="mx-auto text-line" />
        <p className="mt-3 text-sm text-muted">暂无账单记录</p>
        <p className="text-xs text-muted">升级会员后将在此查看付款记录与发票</p>
      </div> : (
        <div className="overflow-hidden rounded-xl border border-line">
          {orders.map((order) => (
            <div key={order.orderId} className="flex items-center justify-between border-b border-line px-4 py-3 last:border-b-0">
              <div>
                <p className="text-sm font-medium text-text">{order.membershipName} · {order.billingCycle === "yearly" ? "年付" : "月付"}</p>
                <p className="mt-0.5 text-xs text-muted">{new Date(order.createdAt).toLocaleString("zh-CN")}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-text">¥{order.amount.toFixed(2)}</p>
                <p className="text-xs text-muted">{order.status === "paid" ? "已支付" : order.status === "pending" ? "待支付" : "已取消"}</p>
                {invoiceByOrder.has(order.orderId) && <p className="mt-0.5 text-[11px] text-blue">已提交开票申请</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      <h3 className="mb-3 mt-6 text-sm font-semibold text-text">开票申请记录</h3>
      {invoices.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-muted">暂无开票申请</div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-line">
          {invoices.map((invoice) => (
            <div key={invoice.id} className="flex flex-col gap-3 border-b border-line px-4 py-3 last:border-b-0 sm:flex-row sm:items-center">
              <FileCheck2 size={18} className="shrink-0 text-blue" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">{invoice.companyName} · {invoice.membershipName}</p>
                <p className="mt-0.5 text-xs text-muted">{invoice.taxNumber} · ¥{invoice.orderAmount.toFixed(2)} · {new Date(invoice.requestedAt).toLocaleString("zh-CN")}</p>
                {invoice.status === "rejected" && invoice.rejectReason && <p className="mt-1 text-xs text-red">驳回原因：{invoice.rejectReason}</p>}
              </div>
              <span className="rounded-full bg-canvas px-2.5 py-1 text-xs text-muted">
                {invoice.status === "requested" ? "待处理" : invoice.status === "issued" ? "已开具" : "已驳回"}
              </span>
              <button type="button" disabled={downloadingId === invoice.id} onClick={() => void downloadApplication(invoice.id)} className="flex items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-blue transition hover:bg-blue-soft disabled:opacity-50">
                {downloadingId === invoice.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}下载申请单
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 账户设置 ── */
function SettingsSection({
  user,
  onSave,
}: {
  user: ReturnType<typeof useAuthStore.getState>["user"];
  onSave: (data: {
    name: string;
    email: string;
    notifyAssetProcessing: boolean;
    notifyScriptGeneration: boolean;
    notifyMarketing: boolean;
  }) => Promise<void>;
}) {
  const [name, setName] = useState(user?.name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [notifyUpload, setNotifyUpload] = useState(user?.notifyAssetProcessing ?? true);
  const [notifyScript, setNotifyScript] = useState(user?.notifyScriptGeneration ?? true);
  const [notifyMarketing, setNotifyMarketing] = useState(user?.notifyMarketing ?? false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        email: email.trim(),
        notifyAssetProcessing: notifyUpload,
        notifyScriptGeneration: notifyScript,
        notifyMarketing,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h2 className="mb-4 text-lg font-bold text-text">账户设置</h2>
      <div className="space-y-5">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text">昵称</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-text">邮箱</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
          />
        </div>
        <div>
          <strong className="mb-2 block text-sm font-medium text-text">通知偏好</strong>
          <div className="space-y-2">
            {[
              { label: "素材处理完成通知", value: notifyUpload, set: setNotifyUpload },
              { label: "脚本与初剪生成通知", value: notifyScript, set: setNotifyScript },
              { label: "产品与营销邮件", value: notifyMarketing, set: setNotifyMarketing },
            ].map((item) => (
              <label
                key={item.label}
                className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-surface px-3.5 py-2.5"
              >
                <span className="text-sm text-text">{item.label}</span>
                <button
                  type="button"
                  onClick={() => item.set(!item.value)}
                  className={`relative h-6 w-11 rounded-full transition ${item.value ? "bg-blue" : "bg-line"}`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${item.value ? "left-[22px]" : "left-0.5"}`}
                  />
                </button>
              </label>
            ))}
          </div>
        </div>
        <div className="flex justify-end">
          <button
            onClick={() => void save()}
            disabled={saving || !name.trim() || !email.trim()}
            className="rounded-lg bg-blue px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-2"
            type="button"
          >
            {saving ? "保存中…" : "保存设置"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default AccountCenter;
