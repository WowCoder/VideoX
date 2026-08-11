// ──────────────────────────────────────────────
// OpenVMA - 应用壳：Sidebar + Topbar
// 侧栏深色 (#0c1730) 宽 220px 可折叠；顶栏白色 sticky 毛玻璃
// ──────────────────────────────────────────────

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useLocation } from "@/router";
import {
  Bell,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Clapperboard,
  CircleUserRound,
  CreditCard,
  Crown,
  FolderKanban,
  Gauge,
  HelpCircle,
  Home,
  Library,
  LogOut,
  Menu,
  ReceiptText,
  Search,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import * as notificationApi from "@/api/notifications";
import * as searchApi from "@/api/search";
import { navItems } from "@/data/uiConfig";
import { formatRelativeTime } from "@/lib/utils";

const navIcons = {
  home: Home,
  library: Library,
  script: Clapperboard,
  projects: FolderKanban,
} as const;

/* ── 品牌标识 ── */
function BrandMark() {
  return (
    <span className="brand-mark inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal">
      <Sparkles size={16} className="text-white" />
    </span>
  );
}

/* ── 消息中心下拉 ── */
function MessageCenterMenu({
  data,
  loading,
  error,
  onRetry,
}: {
  data?: notificationApi.NotificationList;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  const { messageCenterOpen, setMessageCenterOpen, notify } = useUIStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const unreadCount = data?.unreadCount ?? 0;

  const markAllMutation = useMutation({
    mutationFn: notificationApi.markAllRead,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (mutationError) =>
      notify(mutationError instanceof Error ? mutationError.message : "通知更新失败", "error"),
  });
  const markReadMutation = useMutation({
    mutationFn: notificationApi.markRead,
    onSuccess: (notification) => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      setMessageCenterOpen(false);
      if (notification.link) navigate(notification.link);
    },
    onError: (mutationError) =>
      notify(mutationError instanceof Error ? mutationError.message : "通知更新失败", "error"),
  });

  if (!messageCenterOpen) return null;

  return (
    <>
      <button
        className="fixed inset-0 z-40 cursor-default"
        onClick={() => setMessageCenterOpen(false)}
        aria-label="关闭消息中心"
        type="button"
      />
      <section className="absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-xl border border-line bg-surface shadow-soft">
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <div>
            <strong className="text-sm text-text">消息中心</strong>
            <small className="ml-2 text-xs text-muted">
              {unreadCount ? `${unreadCount} 条未读` : "全部已读"}
            </small>
          </div>
          <button
            onClick={() => markAllMutation.mutate()}
            disabled={!unreadCount || markAllMutation.isPending}
            className="flex items-center gap-1 text-xs text-blue disabled:text-muted"
            type="button"
          >
            <CheckCheck size={14} />全部已读
          </button>
        </header>
        <div className="max-h-80 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-10">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-blue" />
            </div>
          ) : error ? (
            <div className="px-5 py-8 text-center">
              <p className="text-sm font-medium text-text">消息加载失败</p>
              <p className="mt-1 text-xs text-muted">{error.message}</p>
              <button onClick={onRetry} className="mt-3 text-xs font-medium text-blue" type="button">
                重试
              </button>
            </div>
          ) : !data?.items.length ? (
            <div className="px-5 py-10 text-center">
              <Bell size={24} className="mx-auto text-line" />
              <p className="mt-2 text-sm font-medium text-text">暂无消息</p>
              <p className="mt-1 text-xs text-muted">真实任务完成或失败后会显示在这里</p>
            </div>
          ) : data.items.map((message) => (
            <button
              key={message.id}
              onClick={() => markReadMutation.mutate(message.id)}
              className="flex w-full items-start gap-3 border-b border-line/60 px-4 py-3 text-left transition hover:bg-canvas"
              type="button"
            >
              <span className={!message.isRead ? "text-blue" : "text-muted"}>
                <Bell size={15} />
              </span>
              <div className="flex-1">
                <strong className="text-sm text-text">{message.title}</strong>
                <p className="mt-0.5 text-xs leading-relaxed text-muted">{message.message}</p>
                <small className="text-[11px] text-muted">{formatRelativeTime(message.createdAt)}</small>
              </div>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => {
            setMessageCenterOpen(false);
            navigate("/workspace/notifications");
          }}
          className="w-full border-t border-line px-4 py-2.5 text-center text-xs font-medium text-blue hover:bg-canvas"
        >
          查看全部通知
        </button>
      </section>
    </>
  );
}

/* ── 账户菜单下拉 ── */
function AccountMenu({ placement }: { placement: "sidebar" | "topbar" }) {
  const { accountMenuOrigin, closeAccountMenu, notify } = useUIStore();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const open = accountMenuOrigin === placement;

  const membershipName = user?.membership?.name || "Free";
  const membershipRank = user?.membership?.rank ?? 0;
  const membershipAction = membershipRank === 0
    ? {
        title: "升级 OpenVMA 会员",
        copy: "查看更高存储空间与更多 AI 额度",
      }
    : membershipRank === 1
      ? {
          title: "管理 Pro 会员",
          copy: "查看当前权益或升级到 Team",
        }
      : {
          title: "管理 Team 会员",
          copy: "查看当前方案权益与用量",
        };

  if (!open) return null;

  const menuItems = [
    { id: "overview", label: "个人中心", copy: "账户信息与会员概览", icon: CircleUserRound },
    { id: "membership", label: "会员方案", copy: "查看当前方案与可用额度", icon: CreditCard },
    { id: "usage", label: "用量中心", copy: "处理时长与 AI 额度", icon: Gauge },
    { id: "billing", label: "账单与发票", copy: "付款记录与电子票据", icon: ReceiptText },
    { id: "settings", label: "账户设置", copy: "资料、通知与安全", icon: Settings },
  ];

  function openSection(section: string) {
    closeAccountMenu();
    const sectionMap: Record<string, string> = {
      overview: "/workspace/account?section=overview",
      membership: "/workspace/account?section=membership",
      usage: "/workspace/account?section=usage",
      billing: "/workspace/account?section=billing",
      settings: "/workspace/account?section=settings",
    };
    navigate(sectionMap[section] ?? "/workspace/account");
  }

  return (
    <>
      <button
        className="fixed inset-0 z-40 cursor-default"
        onClick={closeAccountMenu}
        aria-label="关闭账号菜单"
        type="button"
      />
      <section
        className={`absolute z-50 w-72 overflow-hidden rounded-xl border border-line bg-surface shadow-soft ${
          placement === "sidebar" ? "bottom-16 left-3" : "right-0 top-12"
        }`}
        aria-label="个人中心菜单"
      >
        <header className="flex items-center gap-3 border-b border-line bg-canvas/60 px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-sm font-semibold text-white">
            {user?.initial || "U"}
          </span>
          <div className="flex-1">
            <strong className="text-sm text-text">{user?.name || "用户"}</strong>
            <small className="block text-xs text-muted">{user?.email || ""}</small>
          </div>
          <span className="rounded-pill bg-blue-soft px-2 py-0.5 text-[11px] font-medium text-blue">
            {membershipName}
          </span>
        </header>
        <button
          className="flex w-full items-center gap-3 border-b border-line px-4 py-3 text-left transition hover:bg-canvas"
          onClick={() => openSection("membership")}
          type="button"
        >
          <span className="text-amber"><Crown size={17} /></span>
          <div className="flex-1">
            <strong className="text-sm text-text">
              {membershipAction.title}
            </strong>
            <small className="block text-xs text-muted">
              {membershipAction.copy}
            </small>
          </div>
          <ChevronDown size={14} className="text-muted" />
        </button>
        <nav className="py-1">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => openSection(item.id)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-canvas"
                type="button"
              >
                <span className="text-muted"><Icon size={16} /></span>
                <div className="flex-1">
                  <strong className="text-sm text-text">{item.label}</strong>
                  <small className="block text-xs text-muted">{item.copy}</small>
                </div>
              </button>
            );
          })}
        </nav>
        <footer className="border-t border-line py-1">
          <button
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-muted transition hover:bg-canvas"
            onClick={() => {
              closeAccountMenu();
              navigate("/workspace/help");
            }}
            type="button"
          >
            <HelpCircle size={16} />帮助与反馈
          </button>
          <button
            className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-red transition hover:bg-canvas"
            onClick={() => {
              closeAccountMenu();
              logout();
              notify("已退出登录，返回 OpenVMA 官网");
              navigate("/");
            }}
            type="button"
          >
            <LogOut size={16} />退出登录
          </button>
        </footer>
      </section>
    </>
  );
}

/* ── 侧栏 ── */
export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    sidebarCollapsed,
    mobileNavOpen,
    setMobileNavOpen,
    accountMenuOrigin,
    toggleAccountMenu,
    closeAccountMenu,
  } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const membershipName = user?.membership?.name || "Free";
  const membershipRank = user?.membership?.rank ?? 0;
  const sidebarMembershipAction = membershipRank === 0
    ? {
        title: "查看会员方案",
        copy: "获得更高存储与 AI 额度",
      }
    : membershipRank === 1
      ? {
          title: "升级到 Team",
          copy: "获得 200GB 存储与更高额度",
        }
      : null;

  function isActive(path: string) {
    if (path === "/workspace") {
      return location.pathname === "/workspace" || location.pathname === "/workspace/tasks";
    }
    return location.pathname.startsWith(path);
  }

  function handleNavigate(path: string) {
    navigate(path);
    setMobileNavOpen(false);
    closeAccountMenu();
  }

  return (
    <>
      {/* 移动端遮罩 */}
      <div
        className={`fixed inset-0 z-40 bg-ink/50 backdrop-blur-sm transition-opacity lg:hidden ${
          mobileNavOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setMobileNavOpen(false)}
      />
      <aside
        className={`fixed left-0 top-0 z-50 flex h-screen flex-col bg-ink text-white transition-all duration-300 lg:static lg:z-auto ${
          sidebarCollapsed ? "w-[68px]" : "w-[220px]"
        } ${mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        {/* 品牌区 */}
        <div className="flex h-16 items-center justify-between px-4">
          <button
            className="flex items-center gap-2.5"
            onClick={() => navigate("/")}
            aria-label="返回 OpenVMA 官网"
            type="button"
          >
            <BrandMark />
            {!sidebarCollapsed && (
              <span className="text-[15px] font-semibold tracking-wide">OpenVMA</span>
            )}
          </button>
          <button
            className="text-white/60 hover:text-white lg:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-label="关闭导航"
            type="button"
          >
            <X size={18} />
          </button>
        </div>

        {/* 主导航 */}
        <nav className="flex-1 overflow-y-auto px-3 py-2" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = navIcons[item.id as keyof typeof navIcons];
            const active = isActive(item.path);
            return (
              <button
                key={item.id}
                className={`group mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                  active
                    ? "bg-blue text-white shadow-soft"
                    : "text-white/70 hover:bg-white/5 hover:text-white"
                } ${sidebarCollapsed ? "justify-center" : ""}`}
                onClick={() => handleNavigate(item.path)}
                title={sidebarCollapsed ? item.label : undefined}
                type="button"
              >
                <Icon size={18} className="shrink-0" />
                {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* 底部：用量条 + 用户区 */}
        <div className="border-t border-white/10 p-3">
          {!sidebarCollapsed && sidebarMembershipAction && (
            <button
              className="mb-3 flex w-full items-center gap-3 rounded-lg bg-gradient-to-r from-blue-2/40 to-teal/20 p-3 text-left transition hover:from-blue-2/60"
              onClick={() => handleNavigate("/workspace/account?section=membership")}
              type="button"
            >
              <span className="text-amber"><Crown size={16} /></span>
              <div className="flex-1">
                <strong className="block text-xs text-white">{sidebarMembershipAction.title}</strong>
                <small className="text-[11px] text-white/60">{sidebarMembershipAction.copy}</small>
              </div>
              <ChevronRight size={14} className="text-white/40" />
            </button>
          )}
          <button
            className={`flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition hover:bg-white/5 ${
              accountMenuOrigin === "sidebar" ? "bg-white/5" : ""
            } ${sidebarCollapsed ? "justify-center" : ""}`}
            onClick={() => toggleAccountMenu("sidebar")}
            aria-expanded={accountMenuOrigin === "sidebar"}
            type="button"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-xs font-semibold text-white">
              {user?.initial || "U"}
            </span>
            {!sidebarCollapsed && (
              <>
                <span className="flex-1">
                  <strong className="block text-xs text-white">{user?.name || "用户"}</strong>
                  <small className="text-[11px] text-white/50">{membershipName} 会员</small>
                </span>
                <ChevronDown
                  size={14}
                  className={`text-white/40 transition-transform ${
                    accountMenuOrigin === "sidebar" ? "rotate-180" : ""
                  }`}
                />
              </>
            )}
          </button>
          <AccountMenu placement="sidebar" />
        </div>
      </aside>
    </>
  );
}

/* ── 顶栏 ── */
export function Topbar() {
  const navigate = useNavigate();
  const { toggleSidebar, toggleMessageCenter, messageCenterOpen } = useUIStore();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchValue, setSearchValue] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const shortcutLabel = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
    ? "⌘K"
    : "Ctrl K";
  useEffect(() => {
    function handleGlobalSearchShortcut(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") return;
      event.preventDefault();
      setSearchOpen(true);
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    }
    window.addEventListener("keydown", handleGlobalSearchShortcut);
    return () => window.removeEventListener("keydown", handleGlobalSearchShortcut);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchValue.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchValue]);
  const searchQuery = useQuery({
    queryKey: ["global-search", debouncedSearch],
    queryFn: () => searchApi.globalSearch(debouncedSearch),
    enabled: debouncedSearch.length > 0,
    retry: false,
  });
  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationApi.list(),
    retry: false,
    refetchInterval: 10_000,
  });
  const unreadCount = notificationsQuery.data?.unreadCount ?? 0;

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-surface/80 px-4 backdrop-blur-xl lg:px-6">
      <button
        className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-canvas hover:text-text"
        onClick={toggleSidebar}
        aria-label="收起或展开导航"
        type="button"
      >
        <Menu size={20} />
      </button>

      {/* 全局搜索 */}
      <div className="relative z-40 w-full max-w-md min-w-0">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          ref={searchInputRef}
          value={searchValue}
          onChange={(e) => {
            setSearchValue(e.target.value);
            setSearchOpen(true);
          }}
          onFocus={() => setSearchOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setSearchOpen(false);
            if (e.key === "Enter" && searchQuery.data?.length === 1) {
              navigate(searchQuery.data[0].url);
              setSearchOpen(false);
              setSearchValue("");
            }
          }}
          placeholder="搜索脚本、素材、项目…"
          className="w-full rounded-lg border border-line bg-canvas/60 py-2 pl-9 pr-16 text-sm text-text placeholder:text-muted transition focus:border-blue focus:bg-surface focus:ring-2 focus:ring-blue/10"
        />
        <kbd className="absolute right-2.5 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-muted sm:flex">
          {shortcutLabel}
        </kbd>
        {searchOpen && debouncedSearch && (
          <section className="absolute left-0 right-0 top-full mt-2 overflow-hidden rounded-xl border border-line bg-surface shadow-soft">
            {searchQuery.isLoading ? (
              <div className="px-4 py-6 text-center text-sm text-muted">搜索中…</div>
            ) : searchQuery.error ? (
              <div className="px-4 py-5 text-center">
                <p className="text-sm text-red">搜索失败</p>
                <button
                  type="button"
                  onClick={() => void searchQuery.refetch()}
                  className="mt-2 text-xs font-medium text-blue"
                >
                  重试
                </button>
              </div>
            ) : !searchQuery.data?.length ? (
              <div className="px-4 py-6 text-center text-sm text-muted">没有找到匹配的真实数据</div>
            ) : (
              <div className="max-h-96 overflow-y-auto py-1">
                {searchQuery.data.map((item) => (
                  <button
                    key={`${item.type}-${item.id}`}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => {
                      navigate(item.url);
                      setSearchOpen(false);
                      setSearchValue("");
                    }}
                    className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-canvas"
                  >
                    <span className="mt-0.5 rounded-md bg-blue-soft px-2 py-0.5 text-[11px] font-medium text-blue">
                      {{ project: "项目", script: "脚本", asset: "素材", clip: "片段" }[item.type]}
                    </span>
                    <span className="min-w-0 flex-1">
                      <strong className="block truncate text-sm text-text">{item.title}</strong>
                      <small className="mt-0.5 block truncate text-xs text-muted">{item.subtitle}</small>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <button
          className={`relative flex h-9 w-9 items-center justify-center rounded-lg transition hover:bg-canvas ${
            messageCenterOpen ? "bg-blue-soft text-blue" : "text-muted hover:text-text"
          }`}
          onClick={toggleMessageCenter}
          aria-label="消息中心"
          type="button"
        >
          <Bell size={18} />
          {unreadCount > 0 && (
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red" />
          )}
        </button>
        {messageCenterOpen && (
          <MessageCenterMenu
            data={notificationsQuery.data}
            loading={notificationsQuery.isLoading}
            error={notificationsQuery.error}
            onRetry={() => void notificationsQuery.refetch()}
          />
        )}

        <button
          className="hidden items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-canvas hover:text-text md:flex"
          onClick={() => navigate("/workspace/help")}
          type="button"
        >
          <HelpCircle size={16} />帮助中心
        </button>

      </div>
    </header>
  );
}

/* ── Toast 容器（全局） ── */
export function ToastContainer() {
  const { toasts, dismissToast } = useUIStore();
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-6 left-1/2 z-[100] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="flex items-center gap-2.5 rounded-xl bg-ink px-4 py-3 text-sm text-white shadow-soft"
          role="status"
        >
          <Sparkles size={16} className={toast.tone === "error" ? "text-red" : "text-teal"} />
          <span>{toast.text}</span>
          <button
            onClick={() => dismissToast(toast.id)}
            aria-label="关闭提示"
            className="ml-2 text-white/60 hover:text-white"
            type="button"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ── 应用壳布局：Sidebar + Topbar + Outlet 内容区 ── */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto" data-scroll-restoration="workspace-main">{children}</main>
      </div>
      <ToastContainer />
    </div>
  );
}
