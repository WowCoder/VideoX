// ──────────────────────────────────────────────
// OpenVMA - 会员与账单 API
// 后端返回 snake_case，前端映射为 camelCase
// ──────────────────────────────────────────────

import { http } from "./client";

/* ── 后端原始类型（snake_case）── */

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
  product_type?: string;
  product_code?: string | null;
  credit_amount?: number | null;
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

interface RawCatalogPlan {
  plan_code: string;
  membership_id?: string;
  display_name: string;
  rank: number;
  monthly_price_fen: number;
  annual_price_fen?: number | null;
  monthly_credits: number;
  signup_credits: number;
  rollover_cycles: number;
  recharge_bonus_bps: number;
  generation_concurrency: number;
  storage_bytes: number;
  seat_limit: number;
  queue_priority: number;
  model_access_level: string;
  max_video_resolution: string;
  max_image_resolution: string;
  watermark_required: boolean;
  commercial_use: boolean;
  api_access: boolean;
  batch_access: boolean;
  rollover_policy: string;
  metadata?: Record<string, unknown>;
}
interface RawCatalogPackage {
  package_code: string;
  display_name: string;
  price_fen: number;
  base_credits: number;
  package_bonus_bps: number;
  sort_order: number;
  active: boolean;
}
interface RawCatalogSku {
  sku: string;
  display_name: string;
  category: string;
  unit: string;
  minimum_quantity: number;
  rounding_mode: string;
  access_level: string;
  credits_per_unit: number;
  minimum_credits: number;
  allowed_plan_codes?: string[];
  included_in_pass: boolean;
  metadata?: Record<string, unknown>;
}
interface RawWalletLot {
  id: string;
  source_type: string;
  original_amount: number;
  remaining_amount: number;
  granted_at: string;
  expires_at?: string | null;
}
interface RawWallet {
  account_id: string;
  owner_type: string;
  owner_id: string;
  available_credits: number;
  reserved_credits: number;
  total_credits: number;
  lots?: RawWalletLot[];
}
interface RawCreditLedgerEntry {
  id: string;
  entry_type: string;
  amount: number;
  balance_after: number;
  reason: string;
  order_id?: string | null;
  job_id?: string | null;
  created_at: string;
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
  monthlyCredits?: number;
  annualPrice?: number;
  rechargeBonusBps?: number;
  generationConcurrency?: number;
  modelAccessLevel?: string;
  maxVideoResolution?: string;
  maxImageResolution?: string;
  watermarkRequired?: boolean;
  commercialUse?: boolean;
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
  productType: string;
  productCode?: string;
  creditAmount?: number;
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

export interface BillingCatalogPlan {
  planCode: string;
  membershipId?: string;
  displayName: string;
  rank: number;
  monthlyPriceFen: number;
  annualPriceFen?: number | null;
  monthlyCredits: number;
  signupCredits: number;
  rolloverCycles: number;
  rechargeBonusBps: number;
  generationConcurrency: number;
  storageBytes: number;
  seatLimit: number;
  queuePriority: number;
  modelAccessLevel: string;
  maxVideoResolution: string;
  maxImageResolution: string;
  watermarkRequired: boolean;
  commercialUse: boolean;
  apiAccess: boolean;
  batchAccess: boolean;
  rolloverPolicy: string;
  metadata: Record<string, unknown>;
}

export interface BillingCatalogSku {
  sku: string;
  displayName: string;
  category: string;
  unit: string;
  minimumQuantity: number;
  roundingMode: string;
  accessLevel: string;
  creditsPerUnit: number;
  minimumCredits: number;
  allowedPlanCodes: string[];
  includedInPass: boolean;
  metadata: Record<string, unknown>;
}

export interface BillingCatalog {
  id: string;
  versionKey: string;
  status: string;
  effectiveAt?: string;
  publishedAt?: string;
  plans: BillingCatalogPlan[];
  creditPackages: Array<{
    packageCode: string;
    displayName: string;
    priceFen: number;
    baseCredits: number;
    packageBonusBps: number;
    sortOrder: number;
    active: boolean;
  }>;
  skus: BillingCatalogSku[];
}

export interface BillingWallet {
  accountId: string;
  ownerType: string;
  ownerId: string;
  availableCredits: number;
  reservedCredits: number;
  totalCredits: number;
  lots: Array<{
    id: string;
    sourceType: string;
    originalAmount: number;
    remainingAmount: number;
    grantedAt: string;
    expiresAt?: string;
  }>;
}

export interface CreditLedgerEntry {
  id: string;
  entryType: string;
  amount: number;
  balanceAfter: number;
  reason: string;
  orderId?: string;
  jobId?: string;
  createdAt: string;
}

/* ── 映射函数 ── */

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
  const catalog = await getBillingCatalog();
  return catalog.plans.map((plan) => ({
    id: plan.membershipId || `plan-${plan.planCode}`,
    name: plan.displayName,
    rank: plan.rank,
    billingCycle: "monthly",
    processingMinutes: 0,
    aiImageQuota: 0,
    aiVideoQuota: 0,
    storageGb: Math.round(plan.storageBytes / 1024 ** 3),
    exportQuota: 0,
    price: plan.monthlyPriceFen / 100,
    monthlyCredits: plan.monthlyCredits,
    annualPrice: plan.annualPriceFen == null ? undefined : plan.annualPriceFen / 100,
    rechargeBonusBps: plan.rechargeBonusBps,
    generationConcurrency: plan.generationConcurrency,
    modelAccessLevel: plan.modelAccessLevel,
    maxVideoResolution: plan.maxVideoResolution,
    maxImageResolution: plan.maxImageResolution,
    watermarkRequired: plan.watermarkRequired,
    commercialUse: plan.commercialUse,
  }));
}

export async function getBillingCatalog(): Promise<BillingCatalog> {
  const raw = await http.get<{
    id: string;
    version_key: string;
    status: string;
    effective_at?: string;
    published_at?: string;
    plans: RawCatalogPlan[];
    credit_packages: RawCatalogPackage[];
    skus: RawCatalogSku[];
  }>("/billing/catalog");
  return {
    id: raw.id,
    versionKey: raw.version_key,
    status: raw.status,
    effectiveAt: raw.effective_at,
    publishedAt: raw.published_at,
    plans: raw.plans.map((p) => ({
      planCode: p.plan_code,
      membershipId: p.membership_id,
      displayName: p.display_name,
      rank: p.rank,
      monthlyPriceFen: p.monthly_price_fen,
      annualPriceFen: p.annual_price_fen,
      monthlyCredits: p.monthly_credits,
      signupCredits: p.signup_credits,
      rolloverCycles: p.rollover_cycles,
      rechargeBonusBps: p.recharge_bonus_bps,
      generationConcurrency: p.generation_concurrency,
      storageBytes: p.storage_bytes,
      seatLimit: p.seat_limit,
      queuePriority: p.queue_priority,
      modelAccessLevel: p.model_access_level,
      maxVideoResolution: p.max_video_resolution,
      maxImageResolution: p.max_image_resolution,
      watermarkRequired: p.watermark_required,
      commercialUse: p.commercial_use,
      apiAccess: p.api_access,
      batchAccess: p.batch_access,
      rolloverPolicy: p.rollover_policy,
      metadata: p.metadata ?? {},
    })),
    creditPackages: raw.credit_packages.map((p) => ({
      packageCode: p.package_code,
      displayName: p.display_name,
      priceFen: p.price_fen,
      baseCredits: p.base_credits,
      packageBonusBps: p.package_bonus_bps,
      sortOrder: p.sort_order,
      active: p.active,
    })),
    skus: raw.skus.map((s) => ({
      sku: s.sku,
      displayName: s.display_name,
      category: s.category,
      unit: s.unit,
      minimumQuantity: s.minimum_quantity,
      roundingMode: s.rounding_mode,
      accessLevel: s.access_level,
      creditsPerUnit: s.credits_per_unit,
      minimumCredits: s.minimum_credits,
      allowedPlanCodes: s.allowed_plan_codes ?? [],
      includedInPass: s.included_in_pass,
      metadata: s.metadata ?? {},
    })),
  };
}

export async function getBillingWallet(): Promise<BillingWallet> {
  const raw = await http.get<RawWallet>("/billing/wallet");
  return {
    accountId: raw.account_id,
    ownerType: raw.owner_type,
    ownerId: raw.owner_id,
    availableCredits: raw.available_credits,
    reservedCredits: raw.reserved_credits,
    totalCredits: raw.total_credits,
    lots: (raw.lots ?? []).map((lot) => ({
      id: lot.id,
      sourceType: lot.source_type,
      originalAmount: lot.original_amount,
      remainingAmount: lot.remaining_amount,
      grantedAt: lot.granted_at,
      expiresAt: lot.expires_at ?? undefined,
    })),
  };
}

export async function getCreditLedger(): Promise<CreditLedgerEntry[]> {
  const rows = await http.get<RawCreditLedgerEntry[]>("/billing/ledger?limit=100");
  return rows.map((row) => ({
    id: row.id,
    entryType: row.entry_type,
    amount: row.amount,
    balanceAfter: row.balance_after,
    reason: row.reason,
    orderId: row.order_id ?? undefined,
    jobId: row.job_id ?? undefined,
    createdAt: row.created_at,
  }));
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
    productType: order.product_type ?? "membership",
    productCode: order.product_code ?? undefined,
    creditAmount: order.credit_amount ?? undefined,
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

export async function topupCredits(packageCode: string): Promise<UpgradeResult> {
  const res = await http.post<RawUpgradeResponse>("/billing/topup", { package_code: packageCode });
  return { orderId: res.order_id, message: res.message, payUrl: res.pay_url };
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
