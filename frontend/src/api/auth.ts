// ──────────────────────────────────────────────
// VideoX - 认证 API
// 后端返回 { user, access_token, refresh_token }
// 前端转换为 { user, tokens: { accessToken, refreshToken } }
// ──────────────────────────────────────────────

import { http } from "./client";
import { setTokens } from "./client";
import type { User, UserMembership, LoginRequest, RegisterRequest } from "@/types/models";

/** 后端原始响应格式 */
interface BackendAuthResponse {
  user: {
    id: string;
    email: string;
    name: string;
    avatar_initial: string;
    notify_asset_processing: boolean;
    notify_script_generation: boolean;
    notify_marketing: boolean;
    created_at: string | null;
    membership?: {
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
    };
    subscription?: {
      id: string;
      membership_id: string;
      status: "active" | "internal" | "past_due" | "cancelled" | "expired";
      billing_cycle: "monthly" | "yearly" | "permanent";
      current_period_start: string;
      current_period_end: string | null;
      auto_renew: boolean;
      cancel_at_period_end: boolean;
      provider: string;
    };
    usage?: Record<string, unknown>;
  };
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** 将后端用户对象转换为前端 User 类型 */
function mapUser(raw: BackendAuthResponse["user"]): User {
  let membership: UserMembership | undefined;
  if (raw.membership) {
    membership = {
      id: raw.membership.id,
      name: raw.membership.name,
      rank: raw.membership.rank,
    };
  }
  return {
    id: raw.id,
    email: raw.email,
    name: raw.name,
    initial: raw.avatar_initial,
    avatar: undefined,
    createdAt: raw.created_at ?? "",
    notifyAssetProcessing: raw.notify_asset_processing,
    notifyScriptGeneration: raw.notify_script_generation,
    notifyMarketing: raw.notify_marketing,
    membership,
    subscription: raw.subscription ? {
      id: raw.subscription.id,
      membershipId: raw.subscription.membership_id,
      status: raw.subscription.status,
      billingCycle: raw.subscription.billing_cycle,
      currentPeriodStart: raw.subscription.current_period_start,
      currentPeriodEnd: raw.subscription.current_period_end ?? undefined,
      autoRenew: raw.subscription.auto_renew,
      cancelAtPeriodEnd: raw.subscription.cancel_at_period_end,
      provider: raw.subscription.provider,
    } : undefined,
  };
}

/**
 * 用户注册
 * POST /api/auth/register
 */
export async function register(data: RegisterRequest): Promise<{
  user: User;
  tokens: { accessToken: string; refreshToken: string };
}> {
  const res = await http.post<BackendAuthResponse>("/auth/register", data, { skipAuth: true });
  setTokens(res.access_token, res.refresh_token);
  return {
    user: mapUser(res.user),
    tokens: { accessToken: res.access_token, refreshToken: res.refresh_token },
  };
}

/**
 * 用户登录
 * POST /api/auth/login
 */
export async function login(data: LoginRequest): Promise<{
  user: User;
  tokens: { accessToken: string; refreshToken: string };
}> {
  const res = await http.post<BackendAuthResponse>("/auth/login", data, { skipAuth: true });
  setTokens(res.access_token, res.refresh_token);
  return {
    user: mapUser(res.user),
    tokens: { accessToken: res.access_token, refreshToken: res.refresh_token },
  };
}

/**
 * 刷新 token
 * POST /api/auth/refresh
 */
export function refresh(refreshToken: string): Promise<{
  access_token: string;
  refresh_token?: string;
}> {
  return http.post(
    "/auth/refresh",
    { refresh_token: refreshToken },
    { skipAuth: true, skipRefresh: true },
  );
}

/**
 * 获取当前用户信息
 * GET /api/auth/me
 */
export async function getMe(): Promise<User> {
  const raw = await http.get<BackendAuthResponse["user"]>("/auth/me");
  return mapUser(raw);
}

export async function updateMe(data: {
  name: string;
  email: string;
  notifyAssetProcessing: boolean;
  notifyScriptGeneration: boolean;
  notifyMarketing: boolean;
}): Promise<User> {
  const raw = await http.patch<BackendAuthResponse["user"]>("/auth/me", {
    name: data.name,
    email: data.email,
    notify_asset_processing: data.notifyAssetProcessing,
    notify_script_generation: data.notifyScriptGeneration,
    notify_marketing: data.notifyMarketing,
  });
  return mapUser(raw);
}

/* ── 手机验证码登录 ── */

/**
 * 发送手机验证码
 * POST /api/auth/send-code  (body: { phone })
 * 未配置短信凭证时后端返回 503，请改用邮箱登录。
 */
export function sendSmsCode(phone: string): Promise<{ message: string }> {
  return http.post<{ message: string }>("/auth/send-code", { phone }, { skipAuth: true });
}

/**
 * 手机验证码登录
 * POST /api/auth/login-phone  (body: { phone, code, name })
 */
export async function loginWithPhone(phone: string, code: string, name?: string): Promise<{
  user: User;
  tokens: { accessToken: string; refreshToken: string };
}> {
  const res = await http.post<BackendAuthResponse>(
    "/auth/login-phone",
    { phone, code, name },
    { skipAuth: true },
  );
  return {
    user: mapUser(res.user),
    tokens: { accessToken: res.access_token, refreshToken: res.refresh_token },
  };
}

/* ── 微信扫码登录 ── */

/**
 * 获取微信扫码登录二维码 URL
 * GET /api/auth/wechat/qrcode
 * 未配置微信凭证时返回 503。
 */
export function getWechatQrcode(state?: string): Promise<{ url: string }> {
  const query = state ? `?state=${encodeURIComponent(state)}` : "";
  return http.get<{ url: string }>(`/auth/wechat/qrcode${query}`, { skipAuth: true });
}

/**
 * 微信扫码回调（用 code 换 token 并登录/注册）
 * POST /api/auth/wechat/callback  (body: { code })
 * 未配置微信凭证时返回 503。
 */
export async function wechatCallback(code: string): Promise<{
  user: User;
  tokens: { accessToken: string; refreshToken: string };
}> {
  const res = await http.post<BackendAuthResponse>(
    "/auth/wechat/callback",
    { code },
    { skipAuth: true },
  );
  return {
    user: mapUser(res.user),
    tokens: { accessToken: res.access_token, refreshToken: res.refresh_token },
  };
}
