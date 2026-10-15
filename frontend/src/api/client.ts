// ──────────────────────────────────────────────
// VideoX - HTTP 客户端封装
// 功能：JWT 自动注入 Bearer token、401 自动刷新、统一错误处理
// 基础路径：/api（Vite proxy 转发到后端 8000）
// ──────────────────────────────────────────────

import type { ApiError } from "@/types/models";

const BASE_URL = "/api";

/* ── Token 管理（内存 + localStorage 持久化）── */

const ACCESS_TOKEN_KEY = "videox_access_token";
const REFRESH_TOKEN_KEY = "videox_refresh_token";

let accessToken: string | null = localStorage.getItem(ACCESS_TOKEN_KEY);
let refreshToken: string | null = localStorage.getItem(REFRESH_TOKEN_KEY);

export function setTokens(access: string | null, refresh: string | null): void {
  accessToken = access;
  refreshToken = refresh;
  if (access) {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
  } else {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
  if (refresh) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  return refreshToken;
}

export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/* ── 刷新锁：避免并发 401 时重复刷新 ── */

interface RefreshResult {
  token: string | null;
  credentialRejected: boolean;
}

let refreshPromise: Promise<RefreshResult> | null = null;

/**
 * 尝试用 refresh token 换取新的 access token。
 * 同一时间只允许一个刷新请求，其余并发调用复用同一 Promise。
 */
async function doRefresh(): Promise<RefreshResult> {
  if (refreshPromise) {
    return refreshPromise;
  }

  const currentRefresh = getRefreshToken();
  if (!currentRefresh) {
    return { token: null, credentialRejected: true };
  }

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: currentRefresh }),
      });

      if (!res.ok) {
        // 只有凭证本身明确无效时才清理登录态。服务端故障或限流不应把用户登出。
        const credentialRejected = res.status === 400 || res.status === 401 || res.status === 403;
        if (credentialRejected) {
          clearTokens();
        }
        return { token: null, credentialRejected };
      }

      const data = await res.json();
      const newAccess: string = data.access_token;
      const newRefresh: string | undefined = data.refresh_token;
      setTokens(newAccess, newRefresh ?? currentRefresh);
      return { token: newAccess, credentialRejected: false };
    } catch {
      // 断网、超时等暂时性异常保留现有 Token，稍后可继续重试。
      return { token: null, credentialRejected: false };
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

function accessTokenExpiresWithin(token: string, seconds: number): boolean {
  try {
    const payload = token.split(".")[1];
    if (!payload) return false;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = JSON.parse(atob(padded)) as { exp?: number };
    if (typeof decoded.exp !== "number") return false;
    return decoded.exp * 1000 <= Date.now() + seconds * 1000;
  } catch {
    // 非标准 JWT 交给服务端校验；若返回 401，调用方仍可强制刷新后重试。
    return false;
  }
}

/**
 * 强制刷新 access token，供 XMLHttpRequest 等无法复用 request() 的调用方使用。
 */
export async function refreshAccessToken(): Promise<string> {
  const result = await doRefresh();
  if (result.token) return result.token;
  if (result.credentialRejected) {
    throw new HttpClientError(401, "登录已过期，请重新登录", "AUTH_EXPIRED");
  }
  throw new HttpClientError(
    503,
    "登录状态暂时无法刷新，请检查网络后重试",
    "AUTH_REFRESH_UNAVAILABLE",
  );
}

/**
 * 返回仍有足够有效期的 access token；临近过期时复用全局刷新锁提前刷新。
 */
export async function getValidAccessToken(minValiditySeconds = 120): Promise<string> {
  const current = getAccessToken();
  if (current && !accessTokenExpiresWithin(current, minValiditySeconds)) {
    return current;
  }
  return refreshAccessToken();
}

/* ── 自定义错误类 ── */

export class HttpClientError extends Error {
  status: number;
  detail: string;
  code?: string;

  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.name = "HttpClientError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

/* ── 请求选项 ── */

export interface RequestOptions extends Omit<RequestInit, "body" | "headers"> {
  body?: unknown;
  /** 自定义请求头 */
  headers?: Record<string, string>;
  /** 跳过自动附加 Authorization 头（用于 login/register/refresh） */
  skipAuth?: boolean;
  /** 跳过 401 自动刷新逻辑 */
  skipRefresh?: boolean;
  /** 以 FormData 形式发送（自动移除 Content-Type 让浏览器设置 boundary） */
  isFormData?: boolean;
}

/**
 * 核心 fetch 封装。
 * - 自动拼接 /api 前缀
 * - 自动注入 Authorization: Bearer <token>
 * - 401 时自动刷新 token 并重试一次
 * - 统一 JSON 解析与错误抛出
 */
async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    body,
    skipAuth = false,
    skipRefresh = false,
    isFormData = false,
    headers: customHeaders = {},
    ...rest
  } = options;

  const headers: Record<string, string> = {
    ...customHeaders,
  };

  // 注入 JWT
  if (!skipAuth && accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  // 序列化 body
  let rawBody: BodyInit | undefined;
  if (body !== undefined && body !== null) {
    if (isFormData) {
      rawBody = body as FormData;
    } else {
      headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
      rawBody = JSON.stringify(body);
    }
  }

  const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;

  const doFetch = (token: string | null): Promise<Response> => {
    const finalHeaders = { ...headers };
    if (!skipAuth && token) {
      finalHeaders["Authorization"] = `Bearer ${token}`;
    }
    return fetch(url, {
      ...rest,
      headers: finalHeaders,
      body: rawBody,
    });
  };

  let response = await doFetch(accessToken);

  // 401 → 尝试刷新并重试
  if (response.status === 401 && !skipAuth && !skipRefresh) {
    const refreshResult = await doRefresh();
    if (refreshResult.token) {
      response = await doFetch(refreshResult.token);
    } else if (!refreshResult.credentialRejected) {
      throw new HttpClientError(
        503,
        "登录状态暂时无法刷新，请检查网络后重试",
        "AUTH_REFRESH_UNAVAILABLE",
      );
    }
  }

  // 处理错误响应
  if (!response.ok) {
    let errorDetail = `请求失败 (${response.status})`;
    let errorCode: string | undefined;

    try {
      const errorData: ApiError = await response.json();
      if (typeof errorData.detail === "string") errorDetail = errorData.detail;
      else if (errorData.detail && typeof errorData.detail === "object") {
        const message = (errorData.detail as { message?: unknown }).message;
        errorDetail = typeof message === "string" ? message : JSON.stringify(errorData.detail);
      }
      errorCode = errorData.code;
    } catch {
      // 响应非 JSON，使用状态文本
      errorDetail = response.statusText || errorDetail;
    }

    // 401 且刷新失败 → 清除 token
    if (response.status === 401) {
      clearTokens();
    }

    throw new HttpClientError(response.status, errorDetail, errorCode);
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  // 尝试解析 JSON
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }

  return (await response.text()) as unknown as T;
}

/* ── 便捷方法 ── */

export const http = {
  get: <T>(path: string, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "POST", body }),

  put: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "PUT", body }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "PATCH", body }),

  delete: <T>(path: string, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "DELETE" }),

  upload: <T>(path: string, formData: FormData, options?: RequestOptions): Promise<T> =>
    request<T>(path, { ...options, method: "POST", body: formData, isFormData: true }),

  download: async (path: string): Promise<{ blob: Blob; filename?: string }> => {
    const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;
    const fetchFile = (token: string | null) =>
      fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    let response = await fetchFile(accessToken);
    if (response.status === 401) {
      const refreshResult = await doRefresh();
      if (refreshResult.token) {
        response = await fetchFile(refreshResult.token);
      } else if (!refreshResult.credentialRejected) {
        throw new HttpClientError(
          503,
          "登录状态暂时无法刷新，请检查网络后重试",
          "AUTH_REFRESH_UNAVAILABLE",
        );
      }
    }
    if (!response.ok) {
      let detail = `下载失败 (${response.status})`;
      try {
        const payload = (await response.json()) as ApiError;
        if (typeof payload.detail === "string") detail = payload.detail;
      } catch {
        // 非 JSON 错误响应保留状态信息。
      }
      throw new HttpClientError(response.status, detail);
    }
    const disposition = response.headers.get("content-disposition") ?? "";
    const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    return {
      blob: await response.blob(),
      filename: encodedName ? decodeURIComponent(encodedName) : undefined,
    };
  },
};

/* ── WebSocket 连接工厂（用于任务实时推送）── */

export function createWebSocket(path: string): WebSocket {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const token = getAccessToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return new WebSocket(`${protocol}//${window.location.host}${path}${query}`);
}
