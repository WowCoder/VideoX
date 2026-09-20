import { useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  Bell,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleUserRound,
  CreditCard,
  Crown,
  FolderKanban,
  Gauge,
  HelpCircle,
  LayoutDashboard,
  Library,
  Lightbulb,
  LogOut,
  Menu,
  Plus,
  ReceiptText,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "@/router";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { useProjectStore } from "@/stores/projectStore";
import * as notificationApi from "@/api/notifications";
import * as projectApi from "@/api/projects";
import { navItems } from "@/data/uiConfig";
import { formatRelativeTime } from "@/lib/utils";

const navIcons = {
  home: LayoutDashboard,
  inspiration: Lightbulb,
  library: Library,
} as const;

function BrandMark() {
  return <img src="/favicon.svg" alt="" className="h-8 w-8 rounded-[10px]" />;
}

function messageTarget(item: notificationApi.NotificationItem): string | undefined {
  if (item.link) return item.link;
  if (item.projectId) return `/workspace/projects/${item.projectId}`;
  return undefined;
}

function messageActionLabel(item: notificationApi.NotificationItem): string {
  if (item.actionLabel) return item.actionLabel;
  if (item.projectId) return "打开项目";
  return "查看详情";
}

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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
    },
    onError: (mutationError) =>
      notify(mutationError instanceof Error ? mutationError.message : "消息更新失败", "error"),
  });
  const openMutation = useMutation({
    mutationFn: async (item: notificationApi.NotificationItem) =>
      item.source === "notification" && !item.isRead
        ? notificationApi.markRead(item.id)
        : item,
    onSuccess: (item) => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
      setMessageCenterOpen(false);
      const target = messageTarget(item);
      if (target) navigate(target);
    },
    onError: (mutationError) =>
      notify(mutationError instanceof Error ? mutationError.message : "消息更新失败", "error"),
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
      <section className="absolute right-5 top-[58px] z-50 w-[380px] max-w-[calc(100vw-24px)] overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <strong className="block text-sm font-semibold text-text">消息中心</strong>
            <small className="mt-0.5 block text-xs text-muted">
              {unreadCount ? `${unreadCount} 条未读消息` : "任务动态与业务通知均已同步"}
            </small>
          </div>
          <button
            onClick={() => markAllMutation.mutate()}
            disabled={!unreadCount || markAllMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-text transition hover:bg-canvas disabled:text-muted disabled:opacity-50"
            type="button"
          >
            <CheckCheck size={14} />全部已读
          </button>
        </header>
        <div className="max-h-[430px] overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-12">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-ink" />
            </div>
          ) : error ? (
            <div className="px-5 py-10 text-center">
              <p className="text-sm font-medium text-text">消息加载失败</p>
              <p className="mt-1 text-xs text-muted">{error.message}</p>
              <button onClick={onRetry} className="mt-3 text-xs font-semibold text-text underline" type="button">重试</button>
            </div>
          ) : !data?.items.length ? (
            <div className="px-5 py-12 text-center">
              <Bell size={24} className="mx-auto text-[#b7b7bb]" />
              <p className="mt-3 text-sm font-medium text-text">暂无消息</p>
              <p className="mt-1 text-xs text-muted">处理、生成和导出动态会统一出现在这里</p>
            </div>
          ) : data.items.map((message) => {
            const target = messageTarget(message);
            const running = message.source === "job" && ["QUEUED", "RUNNING", "PAUSED"].includes(message.status ?? "");
            return (
              <button
                key={`${message.source}-${message.id}`}
                onClick={() => openMutation.mutate(message)}
                className="group flex w-full items-start gap-3 border-b border-line/70 px-5 py-4 text-left transition last:border-b-0 hover:bg-canvas"
                type="button"
              >
                <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${message.type === "error" ? "bg-red/10 text-red" : message.isRead ? "bg-canvas text-muted" : "bg-ink text-white"}`}>
                  {message.source === "job" ? <Sparkles size={14} /> : <Bell size={14} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-start justify-between gap-3">
                    <strong className="truncate text-sm font-medium text-text">{message.title}</strong>
                    <small className="shrink-0 text-[10px] text-muted">{formatRelativeTime(message.createdAt)}</small>
                  </span>
                  <span className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{message.message}</span>
                  {running && (
                    <span className="mt-2 block h-1 overflow-hidden rounded-full bg-[#e8e8ea]">
                      <span className="block h-full rounded-full bg-ink" style={{ width: `${message.progress ?? 0}%` }} />
                    </span>
                  )}
                  <span className="mt-2 flex items-center justify-between text-[11px]">
                    <span className="text-muted">{message.source === "job" ? message.status : message.isRead ? "已读" : "未读"}</span>
                    {target && <span className="flex items-center gap-1 font-semibold text-text">{messageActionLabel(message)}<ChevronRight size={12} /></span>}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => {
            setMessageCenterOpen(false);
            navigate("/workspace/notifications");
          }}
          className="flex w-full items-center justify-center gap-1 border-t border-line px-4 py-3.5 text-xs font-semibold text-text transition hover:bg-canvas"
        >
          打开消息中心<ChevronRight size={13} />
        </button>
      </section>
    </>
  );
}

function AccountMenu({ placement }: { placement: "sidebar" | "topbar" }) {
  const { accountMenuOrigin, closeAccountMenu, notify } = useUIStore();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);
  const navigate = useNavigate();
  const open = accountMenuOrigin === placement;
  if (!open) return null;

  const membershipName = user?.membership?.name || "Free";
  const menuItems = [
    { id: "overview", label: "个人中心", copy: "账户信息与会员概览", icon: CircleUserRound },
    { id: "membership", label: "会员方案", copy: "查看积分与套餐权益", icon: CreditCard },
    { id: "credits", label: "V-Credits", copy: "余额、充值与积分明细", icon: Gauge },
    { id: "billing", label: "账单与发票", copy: "付款记录与电子票据", icon: ReceiptText },
    { id: "settings", label: "账户设置", copy: "资料、通知与安全", icon: Settings },
  ];

  function openSection(section: string) {
    closeAccountMenu();
    navigate(`/workspace/account?section=${section}`);
  }

  return createPortal(
    <>
      <button className="fixed inset-0 z-40 cursor-default" onClick={closeAccountMenu} aria-label="关闭账号菜单" type="button" />
      <section
        className={`fixed z-50 w-[310px] max-w-[calc(100vw-24px)] overflow-hidden rounded-2xl border border-line bg-surface shadow-soft ${placement === "sidebar" ? "bottom-[66px] left-3" : "right-4 top-[58px]"}`}
        aria-label="个人中心菜单"
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink text-sm font-semibold text-white">{user?.initial || "U"}</span>
          <div className="min-w-0 flex-1">
            <strong className="block truncate text-sm font-semibold text-text">{user?.name || "用户"}</strong>
            <small className="block truncate text-xs text-muted">{user?.email || ""}</small>
          </div>
          <span className="rounded-full bg-canvas px-2.5 py-1 text-[11px] font-medium text-text">{membershipName}</span>
        </header>
        <button className="flex w-full items-center gap-3 border-b border-line px-4 py-3 text-left transition hover:bg-canvas" onClick={() => openSection("membership")} type="button">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#f0edfb] text-[#7657d9]"><Crown size={16} /></span>
          <span className="min-w-0 flex-1"><strong className="block text-sm text-text">管理会员方案</strong><small className="block text-xs text-muted">查看积分、续费周期和账单</small></span>
          <ChevronRight size={14} className="text-muted" />
        </button>
        <nav className="py-1.5">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} onClick={() => openSection(item.id)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-canvas" type="button">
                <span className="text-muted"><Icon size={16} /></span>
                <span className="min-w-0 flex-1"><strong className="block text-sm font-medium text-text">{item.label}</strong><small className="block text-xs text-muted">{item.copy}</small></span>
              </button>
            );
          })}
        </nav>
        <footer className="border-t border-line py-1.5">
          <button className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-muted transition hover:bg-canvas hover:text-text" onClick={() => { closeAccountMenu(); navigate("/workspace/help"); }} type="button"><HelpCircle size={16} />帮助与反馈</button>
          <button className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-red transition hover:bg-red/5" onClick={() => { closeAccountMenu(); logout(); notify("已退出登录"); navigate("/"); }} type="button"><LogOut size={16} />退出登录</button>
        </footer>
      </section>
    </>,
    document.body,
  );
}

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const {
    sidebarCollapsed,
    mobileNavOpen,
    setMobileNavOpen,
    accountMenuOrigin,
    toggleAccountMenu,
    closeAccountMenu,
    openProjectCreate,
  } = useUIStore();
  const user = useAuthStore((state) => state.user);
  const [projectCenterOpen, setProjectCenterOpen] = useState(true);
  const projectsQuery = useQuery({
    queryKey: ["projects", "sidebar"],
    queryFn: () => projectApi.list({ pageSize: 4 }),
    retry: false,
  });
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: projectApi.getDashboardSummary,
    retry: false,
  });

  function isActive(path: string) {
    if (path === "/workspace") return location.pathname === "/workspace" || location.pathname.startsWith("/workspace/projects/");
    return location.pathname.startsWith(path);
  }

  function handleNavigate(path: string) {
    navigate(path);
    setMobileNavOpen(false);
    closeAccountMenu();
  }

  function openProject(projectId: string) {
    setCurrentProject(projectId);
    handleNavigate(`/workspace/projects/${projectId}`);
  }

  const recentProjects = projectsQuery.data?.items ?? [];
  return (
    <>
      <button
        className={`fixed inset-0 z-40 bg-black/25 backdrop-blur-sm transition-opacity lg:hidden ${mobileNavOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setMobileNavOpen(false)}
        aria-label="关闭导航"
        type="button"
      />
      <aside className={`fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-line bg-[#f7f7f8] text-text transition-all duration-200 lg:static lg:z-auto ${sidebarCollapsed ? "w-[72px]" : "w-[248px]"} ${mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="flex h-[68px] items-center justify-between px-4">
          <button className={`flex items-center gap-2.5 ${sidebarCollapsed ? "mx-auto" : ""}`} onClick={() => navigate("/")} aria-label="返回 OpenVMA 官网" type="button">
            <BrandMark />
            {!sidebarCollapsed && <span className="text-[16px] font-semibold tracking-[-0.03em]">OpenVMA</span>}
          </button>
          <button className="text-muted hover:text-text lg:hidden" onClick={() => setMobileNavOpen(false)} aria-label="关闭导航" type="button"><X size={18} /></button>
        </div>

        <nav className="px-3 pt-3" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = navIcons[item.id];
            const active = isActive(item.path);
            return (
              <button key={item.id} className={`mb-1 flex h-11 w-full items-center gap-3 rounded-[10px] px-3 text-sm transition ${active ? "bg-[#e8e8ea] font-semibold text-text" : "text-[#55565b] hover:bg-[#ececee] hover:text-text"} ${sidebarCollapsed ? "justify-center px-0" : ""}`} onClick={() => handleNavigate(item.path)} title={sidebarCollapsed ? item.label : undefined} type="button">
                <Icon size={18} className="shrink-0" />
                {!sidebarCollapsed && <span>{item.label}</span>}
                {!sidebarCollapsed && item.id === "library" && (summaryQuery.data?.assetCount ?? 0) > 0 && (
                  <span className="ml-auto grid min-w-5 place-items-center rounded-full bg-ink px-1.5 py-0.5 text-[9px] font-semibold text-white">{summaryQuery.data?.assetCount}</span>
                )}
              </button>
            );
          })}
        </nav>

        <section className="mx-3 mt-4 border-t border-line pt-3">
          <div className={`grid items-center gap-1 ${sidebarCollapsed ? "grid-cols-1" : "grid-cols-[1fr_32px]"}`}>
            <button className={`flex h-9 min-w-0 items-center gap-2 rounded-lg text-xs font-semibold text-[#55565b] transition hover:bg-[#ececee] hover:text-text ${sidebarCollapsed ? "justify-center px-0" : "px-2.5"}`} onClick={() => setProjectCenterOpen((open) => !open)} title={sidebarCollapsed ? "项目中心" : undefined} type="button">
              <FolderKanban size={16} />
              {!sidebarCollapsed && <><span>项目中心</span><ChevronDown size={13} className={`ml-auto transition ${projectCenterOpen ? "" : "-rotate-90"}`} /></>}
            </button>
            {!sidebarCollapsed && <button className="grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-[#e5e5e7] hover:text-text" onClick={() => openProjectCreate("blank")} aria-label="新建项目" title="新建项目" type="button"><Plus size={15} /></button>}
          </div>
          {projectCenterOpen && !sidebarCollapsed && (
            <div className="mt-1 space-y-0.5">
              <span className="block px-3 py-1 text-[10px] font-medium text-[#929399]">最近创建</span>
              {recentProjects.map((project) => {
                const active = location.pathname === `/workspace/projects/${project.id}`;
                return (
                  <button key={project.id} type="button" onClick={() => openProject(project.id)} className={`grid min-h-9 w-full grid-cols-[24px_minmax(0,1fr)] items-center gap-2 rounded-lg px-2 text-left transition ${active ? "bg-[#e5e5e8] font-semibold text-text" : "text-[#65666b] hover:bg-[#ececee] hover:text-text"}`}>
                    <span className="grid h-6 w-6 place-items-center rounded-[7px] border border-[#dcdce0] bg-white text-[10px] font-semibold">{project.name.slice(0, 1)}</span>
                    <span className="truncate text-xs">{project.name}</span>
                  </button>
                );
              })}
              {!projectsQuery.isLoading && !recentProjects.length && <p className="px-3 py-2 text-[10px] leading-4 text-muted">还没有项目，点击右上角加号创建</p>}
            </div>
          )}
        </section>

        <div className="mt-auto p-3">
          {!sidebarCollapsed && (
            <button className="mb-2 grid min-h-[68px] w-full grid-cols-[34px_minmax(0,1fr)_14px] items-center gap-2.5 rounded-xl border border-[#dedee0] bg-white p-3 text-left transition hover:border-[#c8c8cb] hover:bg-[#f5f5f6]" onClick={() => handleNavigate("/workspace/account?section=membership")} type="button">
              <span className="grid h-[34px] w-[34px] place-items-center rounded-lg bg-[#f0edfb] text-[#7657d9]"><Crown size={15} /></span>
              <span className="min-w-0"><strong className="block text-[11px] font-semibold text-text">{(user?.membership?.rank ?? 0) <= 0 ? "升级到 Pro 会员" : "管理会员方案"}</strong><small className="block truncate text-[9px] text-muted">{(user?.membership?.rank ?? 0) <= 0 ? "解锁更长时长与更多 AI 能力" : "查看真实额度、续费与账单"}</small></span>
              <ChevronRight size={13} className="text-muted" />
            </button>
          )}
          <div className="relative border-t border-line pt-2">
            <button className={`flex min-h-11 w-full items-center gap-2.5 rounded-[10px] p-2 text-left transition hover:bg-[#ececee] ${accountMenuOrigin === "sidebar" ? "bg-[#ececee]" : ""} ${sidebarCollapsed ? "justify-center" : ""}`} onClick={() => toggleAccountMenu("sidebar")} aria-expanded={accountMenuOrigin === "sidebar"} type="button">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-white">{user?.initial || "U"}</span>
              {!sidebarCollapsed && <><span className="min-w-0 flex-1"><strong className="block truncate text-xs font-semibold text-text">{user?.name || "用户"}</strong><small className="block truncate text-[10px] text-muted">{user?.membership?.name || "Free"} 会员 · 个人空间</small></span><ChevronDown size={13} className={`text-muted transition ${accountMenuOrigin === "sidebar" ? "rotate-180" : ""}`} /></>}
            </button>
            <AccountMenu placement="sidebar" />
          </div>
        </div>
      </aside>
    </>
  );
}

export function Topbar() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const { toggleSidebar, setMobileNavOpen, toggleMessageCenter, messageCenterOpen, toggleAccountMenu, accountMenuOrigin } = useUIStore();
  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationApi.list({ pageSize: 12 }),
    retry: false,
    refetchInterval: 10_000,
  });
  const unreadCount = notificationsQuery.data?.unreadCount ?? 0;

  return (
    <header className="sticky top-0 z-30 flex h-[66px] items-center border-b border-line bg-white/95 px-4 backdrop-blur-xl lg:px-7">
      <button className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-canvas hover:text-text" onClick={() => { if (window.innerWidth < 1024) setMobileNavOpen(true); else toggleSidebar(); }} aria-label="收起或展开导航" type="button"><Menu size={19} /></button>
      <div className="ml-auto flex items-center gap-1.5">
        <div className="relative lg:hidden">
          <button className={`relative grid h-9 w-9 place-items-center rounded-lg transition hover:bg-canvas ${messageCenterOpen ? "bg-canvas text-text" : "text-muted hover:text-text"}`} onClick={toggleMessageCenter} aria-label={`消息中心，${unreadCount} 条未读`} type="button">
            <Bell size={18} />
            {unreadCount > 0 && <span className="absolute right-[7px] top-[7px] h-1.5 w-1.5 rounded-full bg-red ring-1 ring-white" />}
          </button>
          {messageCenterOpen && <MessageCenterMenu data={notificationsQuery.data} loading={notificationsQuery.isLoading} error={notificationsQuery.error} onRetry={() => void notificationsQuery.refetch()} />}
        </div>
        <button className="hidden h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-muted transition hover:bg-canvas hover:text-text sm:flex" onClick={() => navigate("/workspace/help")} type="button"><HelpCircle size={16} />帮助中心</button>
        <div className="relative lg:hidden">
          <button className={`ml-1 grid h-9 w-9 place-items-center rounded-full bg-ink text-xs font-semibold text-white ring-offset-2 transition hover:ring-2 hover:ring-[#d8d8da] ${accountMenuOrigin === "topbar" ? "ring-2 ring-[#c8c8cb]" : ""}`} onClick={() => toggleAccountMenu("topbar")} aria-label={`打开 ${user?.name || "用户"} 的个人中心`} type="button">{user?.initial || "U"}</button>
          <AccountMenu placement="topbar" />
        </div>
      </div>
    </header>
  );
}

export function ToastContainer() {
  const { toasts, dismissToast } = useUIStore();
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-6 left-1/2 z-[100] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((toast) => (
        <div key={toast.id} className="flex items-center gap-2.5 rounded-xl bg-ink px-4 py-3 text-sm text-white shadow-soft" role="status">
          <Sparkles size={15} className={toast.tone === "error" ? "text-[#ff9a9a]" : "text-white/80"} />
          <span>{toast.text}</span>
          <button onClick={() => dismissToast(toast.id)} aria-label="关闭提示" className="ml-2 text-white/60 hover:text-white" type="button"><X size={14} /></button>
        </div>
      ))}
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-white">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-white">
        <Topbar />
        <main className="flex-1 overflow-y-auto bg-white" data-scroll-restoration="workspace-main">{children}</main>
      </div>
      <ToastContainer />
    </div>
  );
}
