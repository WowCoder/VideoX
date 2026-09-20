const TOKEN_KEY = "openvma_admin_access";

export type AdminProfile = {
  id: string;
  email: string;
  name: string;
  role: "super_admin" | "operator" | "finance";
  status: string;
  permissions: string[];
  last_login_at?: string | null;
};

type ApiOptions = RequestInit & { retryAuth?: boolean };

let accessToken = sessionStorage.getItem(TOKEN_KEY) || "";
let refreshPromise: Promise<boolean> | null = null;

function detailFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => JSON.stringify(item)).join("；");
  }
  return fallback;
}

export function setAdminToken(token: string): void {
  accessToken = token;
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

async function refreshToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const response = await fetch("/api/admin/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        setAdminToken("");
        return false;
      }
      const payload = (await response.json()) as { access_token: string };
      setAdminToken(payload.access_token);
      return true;
    } catch {
      setAdminToken("");
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(path, { ...options, headers, credentials: "include" });
  if (response.status === 401 && options.retryAuth !== false && !path.endsWith("/login")) {
    if (await refreshToken()) return api<T>(path, { ...options, retryAuth: false });
  }
  if (!response.ok) {
    let payload: unknown = null;
    try { payload = await response.json(); } catch { /* empty response */ }
    throw new Error(detailFrom(payload, `请求失败（${response.status}）`));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function loginAdmin(email: string, password: string, otp: string) {
  const result = await api<{ admin: AdminProfile; access_token: string }>("/api/admin/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, otp }),
    retryAuth: false,
  });
  setAdminToken(result.access_token);
  return result.admin;
}

export async function restoreAdmin(): Promise<AdminProfile | null> {
  try {
    if (!accessToken && !(await refreshToken())) return null;
    return await api<AdminProfile>("/api/admin/auth/me");
  } catch {
    setAdminToken("");
    return null;
  }
}

export async function logoutAdmin(): Promise<void> {
  try { await api("/api/admin/auth/logout", { method: "POST" }); } finally { setAdminToken(""); }
}

export function mutationOptions(body: object): RequestInit {
  return {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body),
  };
}

export function patchOptions(body: object): RequestInit {
  return {
    method: "PATCH",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body),
  };
}
