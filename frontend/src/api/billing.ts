// ──────────────────────────────────────────────
// OpenVMA - 会员与账单 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";

/* ── 后端原始类型（snake_case）── */

interface RawMembership {
  id: string;
  name: string;
  rank: number;
  billing_cycle: string;
  processing_minutes: number;
  ai_image_quota: number;
  ai_video_quota: number;
  storage_gb: number;
  export_quota: number;
  price: number;
}

interface RawUsage {
  processing_seconds_used: number;
  processing_minutes_used: number;
  ai_image_used: number;
  ai_video_used: number;
  storage_used_mb: number;
  export_used: number;
  billing_cycle_start: string;
  billing_cycle_end: string;
}

interface RawSubscription {
  id: string;
  membership_id: string;
  status: "active" | "internal" | "past_due" | "cancelled" | "expired";
  billing_cycle: "monthly" | "yearly" | "permanent";
  current_period_start: string;
  current_period_end: string | null;
  auto_renew: boolean;
  cancel_at_period_end: boolean;
  provider: string;
}

interface RawUpgradeResponse {
  order_id: string;
  message: string;
  pay_url: string;
}

interface RawOrder {
  order_id: string;
  membership_id: string;
  membership_name: string;
  billing_cycle: string;
  amount: number;
  status: "pending" | "paid" | "cancelled";
  pay_url: string;
  created_at: string;
}

interface RawInvoice {
  id: string;
  order_id: string;
  company_name: string;
  tax_number: string;
  email: string;
  status: "requested" | "issued" | "rejected";
  reject_reason: string;
  requested_at: string;
  issued_at: string | null;
  order_amount: number;
  membership_name: string;
  document_type: "application";
  document_notice: string;
}

/* ── 前端类型（camelCase）── */

export interface MembershipPlan {
  id: string;
  name: string;
  rank: number;
  billingCycle: string;
  processingMinutes: number;
  aiImageQuota: number;
  aiVideoQuota: number;
  storageGb: number;
  exportQuota: number;
  price: number;
}

export interface UsageData {
  processingSecondsUsed: number;
  processingMinutesUsed: number;
  aiImageUsed: number;
  aiVideoUsed: number;
  storageUsedMb: number;
  exportUsed: number;
  billingCycleStart: string;
  billingCycleEnd: string;
}

export interface SubscriptionData {
  id: string;
  membershipId: string;
  status: RawSubscription["status"];
  billingCycle: RawSubscription["billing_cycle"];
  currentPeriodStart: string;
  currentPeriodEnd?: string;
  autoRenew: boolean;
  cancelAtPeriodEnd: boolean;
  provider: string;
}

export interface UpgradeResult {
  orderId: string;
  message: string;
  payUrl: string;
}

export interface BillingOrder {
  orderId: string;
  membershipId: string;
  membershipName: string;
  billingCycle: string;
  amount: number;
  status: "pending" | "paid" | "cancelled";
  payUrl: string;
  createdAt: string;
}

export interface BillingInvoice {
  id: string;
  orderId: string;
  companyName: string;
  taxNumber: string;
  email: string;
  status: "requested" | "issued" | "rejected";
  rejectReason: string;
  requestedAt: string;
  issuedAt?: string;
  orderAmount: number;
  membershipName: string;
  documentNotice: string;
}

/* ── 映射函数 ── */

function mapMembership(raw: RawMembership): MembershipPlan {
  return {
    id: raw.id,
    name: raw.name,
    rank: raw.rank,
    billingCycle: raw.billing_cycle,
    processingMinutes: raw.processing_minutes,
    aiImageQuota: raw.ai_image_quota,
    aiVideoQuota: raw.ai_video_quota,
    storageGb: raw.storage_gb,
    exportQuota: raw.export_quota,
    price: raw.price,
  };
}

function mapUsage(raw: RawUsage): UsageData {
  return {
    processingSecondsUsed: raw.processing_seconds_used,
    processingMinutesUsed: raw.processing_seconds_used / 60,
    aiImageUsed: raw.ai_image_used,
    aiVideoUsed: raw.ai_video_used,
    storageUsedMb: raw.storage_used_mb,
    exportUsed: raw.export_used,
    billingCycleStart: raw.billing_cycle_start,
    billingCycleEnd: raw.billing_cycle_end,
  };
}

/* ── API 方法 ── */

/**
 * 获取会员方案列表
 * GET /api/billing/plans
 */
export async function listMemberships(): Promise<MembershipPlan[]> {
  const res = await http.get<RawMembership[]>("/billing/plans");
  return res.map(mapMembership);
}

/**
 * 获取当前用量
 * GET /api/billing/usage
 */
export async function getUsage(): Promise<UsageData> {
  const res = await http.get<RawUsage>("/billing/usage");
  return mapUsage(res);
}

export async function getSubscription(): Promise<SubscriptionData> {
  const raw = await http.get<RawSubscription>("/billing/subscription");
  return {
    id: raw.id,
    membershipId: raw.membership_id,
    status: raw.status,
    billingCycle: raw.billing_cycle,
    currentPeriodStart: raw.current_period_start,
    currentPeriodEnd: raw.current_period_end ?? undefined,
    autoRenew: raw.auto_renew,
    cancelAtPeriodEnd: raw.cancel_at_period_end,
    provider: raw.provider,
  };
}

export async function listOrders(): Promise<BillingOrder[]> {
  const orders = await http.get<RawOrder[]>("/billing/orders");
  return orders.map((order) => ({
    orderId: order.order_id,
    membershipId: order.membership_id,
    membershipName: order.membership_name,
    billingCycle: order.billing_cycle,
    amount: order.amount,
    status: order.status,
    payUrl: order.pay_url,
    createdAt: order.created_at,
  }));
}

/**
 * 创建会员升级订单
 * POST /api/billing/upgrade
 */
export async function upgradeMembership(
  membershipId: string,
  billingCycle: string = "monthly",
): Promise<UpgradeResult> {
  const res = await http.post<RawUpgradeResponse>("/billing/upgrade", {
    membership_id: membershipId,
    billing_cycle: billingCycle,
  });
  return {
    orderId: res.order_id,
    message: res.message,
    payUrl: res.pay_url,
  };
}

function mapInvoice(raw: RawInvoice): BillingInvoice {
  return {
    id: raw.id,
    orderId: raw.order_id,
    companyName: raw.company_name,
    taxNumber: raw.tax_number,
    email: raw.email,
    status: raw.status,
    rejectReason: raw.reject_reason,
    requestedAt: raw.requested_at,
    issuedAt: raw.issued_at ?? undefined,
    orderAmount: raw.order_amount,
    membershipName: raw.membership_name,
    documentNotice: raw.document_notice,
  };
}

export async function listInvoices(): Promise<BillingInvoice[]> {
  return (await http.get<RawInvoice[]>("/billing/invoices")).map(mapInvoice);
}

export async function createInvoiceApplication(data: {
  orderId: string;
  companyName: string;
  taxNumber: string;
  email: string;
}): Promise<BillingInvoice> {
  return mapInvoice(await http.post<RawInvoice>("/billing/invoices", {
    order_id: data.orderId,
    company_name: data.companyName,
    tax_number: data.taxNumber,
    email: data.email,
  }));
}

export async function downloadInvoiceApplication(invoiceId: string): Promise<void> {
  const { blob, filename } = await http.download(`/billing/invoices/${invoiceId}/application.pdf`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename ?? `OpenVMA-开票申请单-${invoiceId}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
