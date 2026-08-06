// ──────────────────────────────────────────────
// OpenVMA - 认证 Hook
// 包装 authStore，提供便捷的 login/register/logout
// ──────────────────────────────────────────────

import { useCallback } from "react";
import { useAuthStore } from "@/stores/authStore";
import type { LoginRequest, RegisterRequest, User } from "@/types/models";

interface UseAuthReturn {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;

  login: (data: LoginRequest) => Promise<User>;
  register: (data: RegisterRequest) => Promise<User>;
  logout: () => void;
  loadFromStorage: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

/**
 * 认证 hook：包装 authStore，提供便捷的认证操作
 *
 * @example
 * const { user, login, logout, isAuthenticated } = useAuth();
 * await login({ email: "user@example.com", password: "pass" });
 */
export function useAuth(): UseAuthReturn {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const loading = useAuthStore((s) => s.loading);
  const error = useAuthStore((s) => s.error);

  const storeLogin = useAuthStore((s) => s.login);
  const storeRegister = useAuthStore((s) => s.register);
  const storeLogout = useAuthStore((s) => s.logout);
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const refreshUser = useAuthStore((s) => s.refreshUser);
  const clearError = useAuthStore((s) => s.clearError);

  const login = useCallback(
    (data: LoginRequest) => storeLogin(data),
    [storeLogin],
  );

  const register = useCallback(
    (data: RegisterRequest) => storeRegister(data),
    [storeRegister],
  );

  const logout = useCallback(() => storeLogout(), [storeLogout]);

  return {
    user,
    token,
    isAuthenticated,
    loading,
    error,
    login,
    register,
    logout,
    loadFromStorage,
    refreshUser,
    clearError,
  };
}
