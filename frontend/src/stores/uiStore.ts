// ──────────────────────────────────────────────
// OpenVMA - 全局 UI 状态管理（Zustand）
// 管理：侧栏折叠、移动端导航、各种弹窗/抽屉开关、Toast、通知中心
// ──────────────────────────────────────────────

import { create } from "zustand";

export type ToastTone = "success" | "info" | "error";

export interface ToastMessage {
  id: number;
  text: string;
  tone: ToastTone;
}

interface UIState {
  /** 侧栏是否折叠（桌面端） */
  sidebarCollapsed: boolean;
  /** 移动端导航抽屉是否打开 */
  mobileNavOpen: boolean;
  /** 账户菜单展开来源：sidebar | topbar | null */
  accountMenuOrigin: "sidebar" | "topbar" | null;
  /** 消息中心是否打开 */
  messageCenterOpen: boolean;

  /** 各类弹窗 / 抽屉 */
  authModalMode: "login" | "register" | null;
  uploadDrawerOpen: boolean;
  scriptCreateOpen: boolean;
  aiScriptOpen: boolean;
  aiScriptInitialTitle: string;
  projectCreateOpen: boolean;

  /** Toast 队列 */
  toasts: ToastMessage[];

  toggleSidebar: () => void;
  setMobileNavOpen: (open: boolean) => void;
  toggleAccountMenu: (origin: "sidebar" | "topbar") => void;
  closeAccountMenu: () => void;
  toggleMessageCenter: () => void;
  setMessageCenterOpen: (open: boolean) => void;

  openAuth: (mode: "login" | "register") => void;
  closeAuth: () => void;
  openUploadDrawer: () => void;
  closeUploadDrawer: () => void;
  openScriptCreate: () => void;
  closeScriptCreate: () => void;
  openAIScript: (initialTitle?: string) => void;
  closeAIScript: () => void;
  openProjectCreate: () => void;
  closeProjectCreate: () => void;

  notify: (text: string, tone?: ToastTone) => void;
  dismissToast: (id: number) => void;
}

let toastIdCounter = 0;

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  mobileNavOpen: false,
  accountMenuOrigin: null,
  messageCenterOpen: false,

  authModalMode: null,
  uploadDrawerOpen: false,
  scriptCreateOpen: false,
  aiScriptOpen: false,
  aiScriptInitialTitle: "",
  projectCreateOpen: false,

  toasts: [],

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setMobileNavOpen: (open) => set({ mobileNavOpen: open }),
  toggleAccountMenu: (origin) =>
    set((s) => ({
      accountMenuOrigin: s.accountMenuOrigin === origin ? null : origin,
      messageCenterOpen: false,
    })),
  closeAccountMenu: () => set({ accountMenuOrigin: null }),
  toggleMessageCenter: () =>
    set((s) => ({
      messageCenterOpen: !s.messageCenterOpen,
      accountMenuOrigin: null,
    })),
  setMessageCenterOpen: (open) => set({ messageCenterOpen: open }),

  openAuth: (mode) =>
    set({ authModalMode: mode, accountMenuOrigin: null, mobileNavOpen: false }),
  closeAuth: () => set({ authModalMode: null }),
  openUploadDrawer: () => set({ uploadDrawerOpen: true }),
  closeUploadDrawer: () => set({ uploadDrawerOpen: false }),
  openScriptCreate: () => set({ scriptCreateOpen: true }),
  closeScriptCreate: () => set({ scriptCreateOpen: false }),
  openAIScript: (initialTitle = "") =>
    set({ aiScriptOpen: true, aiScriptInitialTitle: initialTitle }),
  closeAIScript: () => set({ aiScriptOpen: false, aiScriptInitialTitle: "" }),
  openProjectCreate: () => set({ projectCreateOpen: true }),
  closeProjectCreate: () => set({ projectCreateOpen: false }),

  notify: (text, tone = "success") => {
    toastIdCounter += 1;
    const id = toastIdCounter;
    set((s) => ({ toasts: [...s.toasts, { id, text, tone }] }));
    // 自动消失
    window.setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 3200);
  },
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
