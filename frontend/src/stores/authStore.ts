// ──────────────────────────────────────────────
// VideoX - 认证状态管理（Zustand）
// token 持久化到 localStorage
// ──────────────────────────────────────────────

import { create } from "zustand";
import * as authApi from "@/api/auth";
import { HttpClientError, setTokens, clearTokens, getAccessToken } from "@/api/client";
import type { User, LoginRequest, RegisterRequest } from "@/types/models";

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  initialized: boolean;
  loading: boolean;
  error: string | null;

  login: (data: LoginRequest) => Promise<User>;
  register: (data: RegisterRequest) => Promise<User>;
  loginWithPhone: (phone: string, code: string, name?: string) => Promise<User>;
  loginWithWechat: (code: string) => Promise<User>;
  logout: () => void;
  /** 从 localStorage 恢复登录态（应用启动时调用） */
  loadFromStorage: () => Promise<void>;
  /** 刷新当前用户信息 */
  refreshUser: () => Promise<void>;
  updateSettings: (data: {
    name: string;
    email: string;
    notifyAssetProcessing: boolean;
    notifyScriptGeneration: boolean;
    notifyMarketing: boolean;
  }) => Promise<User>;
  clearError: () => void;
}

let authRestorePromise: Promise<void> | null = null;

function isAuthenticationFailure(error: unknown): boolean {
  return error instanceof HttpClientError && [400, 401, 403].includes(error.status);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: getAccessToken(),
  isAuthenticated: !!getAccessToken(),
  initialized: false,
  loading: false,
  error: null,

  login: async (data: LoginRequest) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.login(data);
      setTokens(res.tokens.accessToken, res.tokens.refreshToken);
      set({
        user: res.user,
        token: res.tokens.accessToken,
        isAuthenticated: true,
        initialized: true,
        loading: false,
      });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : "登录失败";
      set({ loading: false, error: message, isAuthenticated: false, initialized: true });
      throw err;
    }
  },

  register: async (data: RegisterRequest) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.register(data);
      setTokens(res.tokens.accessToken, res.tokens.refreshToken);
      set({
        user: res.user,
        token: res.tokens.accessToken,
        isAuthenticated: true,
        initialized: true,
        loading: false,
      });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : "注册失败";
      set({ loading: false, error: message, initialized: true });
      throw err;
    }
  },

  loginWithPhone: async (phone: string, code: string, name?: string) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.loginWithPhone(phone, code, name);
      setTokens(res.tokens.accessToken, res.tokens.refreshToken);
      set({
        user: res.user,
        token: res.tokens.accessToken,
        isAuthenticated: true,
        initialized: true,
        loading: false,
      });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : "手机验证码登录失败";
      set({ loading: false, error: message, isAuthenticated: false, initialized: true });
      throw err;
    }
  },

  loginWithWechat: async (code: string) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.wechatCallback(code);
      setTokens(res.tokens.accessToken, res.tokens.refreshToken);
      set({
        user: res.user,
        token: res.tokens.accessToken,
        isAuthenticated: true,
        initialized: true,
        loading: false,
      });
      return res.user;
    } catch (err) {
      const message = err instanceof Error ? err.message : "微信登录失败";
      set({ loading: false, error: message, isAuthenticated: false, initialized: true });
      throw err;
    }
  },

  logout: () => {
    clearTokens();
    set({ user: null, token: null, isAuthenticated: false, initialized: true, error: null });
  },

  loadFromStorage: () => {
    if (get().initialized) return Promise.resolve();
    if (authRestorePromise) return authRestorePromise;

    authRestorePromise = (async () => {
      const token = getAccessToken();
      if (!token) {
        set({ user: null, isAuthenticated: false, token: null, initialized: true, loading: false });
        return;
      }

      set({ token, loading: true, error: null });
      try {
        const user = await authApi.getMe();
        set({ user, isAuthenticated: true, initialized: true, loading: false });
      } catch (error) {
        if (isAuthenticationFailure(error)) {
          clearTokens();
          set({
            user: null,
            token: null,
            isAuthenticated: false,
            initialized: true,
            loading: false,
            error: null,
          });
          return;
        }
        set({
          token,
          isAuthenticated: true,
          initialized: true,
          loading: false,
          error: "暂时无法验证登录状态，请检查网络后重试",
        });
      }
    })().finally(() => {
      authRestorePromise = null;
    });

    return authRestorePromise;
  },

  refreshUser: async () => {
    if (!getAccessToken()) return;
    set({ loading: true });
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, loading: false });
    } catch (error) {
      if (isAuthenticationFailure(error)) {
        clearTokens();
        set({ user: null, token: null, isAuthenticated: false, loading: false, error: null });
        return;
      }
      set({ loading: false, error: "用户信息刷新失败，请稍后重试" });
    }
  },

  updateSettings: async (data) => {
    set({ loading: true, error: null });
    try {
      const user = await authApi.updateMe(data);
      set({ user, loading: false, error: null });
      return user;
    } catch (err) {
      const message = err instanceof Error ? err.message : "账户设置保存失败";
      set({ loading: false, error: message });
      throw err;
    }
  },

  clearError: () => set({ error: null }),
}));
