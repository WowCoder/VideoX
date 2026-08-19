import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useNavigate } from "@/router";
import * as notificationApi from "@/api/notifications";
import { formatRelativeTime } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";

const PAGE_SIZE = 20;

function targetFor(item: notificationApi.NotificationItem): string | undefined {
  if (item.link) return item.link;
  if (item.projectId) return `/workspace/projects/${item.projectId}`;
  return undefined;
}

function actionLabelFor(item: notificationApi.NotificationItem): string {
  if (item.actionLabel) return item.actionLabel;
  if (item.projectId) return "打开项目";
  return "查看详情";
}

export default function NotificationsView() {
  const navigate = useNavigate();
  const notify = useUIStore((state) => state.notify);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [readStatus, setReadStatus] = useState<"all" | "read" | "unread">("all");
  const [type, setType] = useState("");

  const notifications = useQuery({
    queryKey: ["notifications-page", page, readStatus, type],
    queryFn: () => notificationApi.list({ page, pageSize: PAGE_SIZE, readStatus, type }),
    retry: false,
    refetchInterval: 10_000,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
  };
  const openItem = useMutation({
    mutationFn: async (item: notificationApi.NotificationItem) =>
      item.source === "notification" && !item.isRead
        ? notificationApi.markRead(item.id)
        : item,
    onSuccess: (item) => {
      refresh();
      const target = targetFor(item);
      if (target) navigate(target);
    },
    onError: (error) => notify(error instanceof Error ? error.message : "消息更新失败", "error"),
  });
  const markAll = useMutation({
    mutationFn: notificationApi.markAllRead,
    onSuccess: refresh,
    onError: (error) => notify(error instanceof Error ? error.message : "消息更新失败", "error"),
  });

  const total = notifications.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="workspace-page max-w-[1180px]">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold tracking-[0.12em] text-muted">ACTIVITY FEED</p>
          <h1 className="workspace-page-title">消息中心</h1>
          <p className="workspace-page-copy">处理、生成、导出等真实任务动态与业务通知统一显示在这里。</p>
        </div>
        <button type="button" onClick={() => markAll.mutate()} disabled={!notifications.data?.unreadCount || markAll.isPending} className="workspace-secondary-button disabled:opacity-45"><CheckCheck size={16} />全部已读</button>
      </header>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex gap-1 rounded-[10px] bg-canvas p-1">
          {(["all", "unread", "read"] as const).map((value) => (
            <button key={value} type="button" onClick={() => { setReadStatus(value); setPage(1); }} className={`rounded-lg px-3.5 py-2 text-xs font-medium transition ${readStatus === value ? "bg-white text-text shadow-[0_1px_3px_rgba(0,0,0,.08)]" : "text-muted hover:text-text"}`}>
              {{ all: "全部消息", unread: "未读", read: "已读与任务" }[value]}
            </button>
          ))}
        </div>
        <select value={type} onChange={(event) => { setType(event.target.value); setPage(1); }} className="h-10 rounded-[9px] border border-line bg-white px-3 text-xs text-text">
          <option value="">全部类型</option>
          <option value="task">任务动态</option>
          <option value="success">成功</option>
          <option value="error">失败</option>
          <option value="info">进行中与信息</option>
        </select>
      </div>

      <section className="mt-5 overflow-hidden rounded-2xl border border-line bg-white">
        {notifications.isLoading ? (
          <div className="flex justify-center py-24"><Loader2 className="animate-spin text-muted" /></div>
        ) : notifications.error ? (
          <div className="py-20 text-center">
            <p className="text-sm text-red">{notifications.error.message}</p>
            <button type="button" onClick={() => void notifications.refetch()} className="mt-3 text-sm font-semibold text-text underline">重试</button>
          </div>
        ) : !notifications.data?.items.length ? (
          <div className="py-24 text-center">
            <Bell className="mx-auto text-[#b7b7bb]" />
            <p className="mt-3 text-sm font-medium text-text">当前筛选下暂无消息</p>
            <p className="mt-1 text-xs text-muted">新的任务动态和业务结果会自动出现在这里</p>
          </div>
        ) : notifications.data.items.map((item) => {
          const target = targetFor(item);
          const running = item.source === "job" && ["QUEUED", "RUNNING", "PAUSED"].includes(item.status ?? "");
          const Icon = item.type === "error" ? CircleAlert : item.type === "success" ? CircleCheck : item.source === "job" ? Sparkles : Clock3;
          return (
            <article key={`${item.source}-${item.id}`} className="grid grid-cols-[38px_minmax(0,1fr)_auto] gap-3 border-b border-line/75 px-5 py-5 last:border-b-0 hover:bg-[#fbfbfc]">
              <span className={`grid h-9 w-9 place-items-center rounded-[10px] ${item.type === "error" ? "bg-red/10 text-red" : item.type === "success" ? "bg-teal/10 text-teal" : item.isRead ? "bg-canvas text-muted" : "bg-ink text-white"}`}><Icon size={16} /></span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <strong className="text-sm font-semibold text-text">{item.title}</strong>
                  <span className="rounded-full bg-canvas px-2 py-0.5 text-[10px] font-medium text-muted">{item.source === "job" ? item.status : item.isRead ? "已读" : "未读"}</span>
                </div>
                <p className="mt-1.5 text-sm leading-6 text-muted">{item.message}</p>
                {running && (
                  <div className="mt-3 max-w-md">
                    <div className="h-1.5 overflow-hidden rounded-full bg-[#e8e8ea]"><div className="h-full rounded-full bg-ink" style={{ width: `${item.progress ?? 0}%` }} /></div>
                    <p className="mt-1 text-[10px] text-muted">当前进度 {item.progress ?? 0}%</p>
                  </div>
                )}
                <small className="mt-2 block text-[11px] text-muted">{formatRelativeTime(item.createdAt)}</small>
              </div>
              {target ? (
                <button type="button" onClick={() => openItem.mutate(item)} className="mt-0.5 flex h-9 items-center gap-1 rounded-lg border border-line bg-white px-3 text-xs font-semibold text-text transition hover:border-[#bfc0c4] hover:bg-canvas">{actionLabelFor(item)}<ChevronRight size={13} /></button>
              ) : item.source === "notification" && !item.isRead ? (
                <button type="button" onClick={() => openItem.mutate(item)} className="mt-0.5 h-9 rounded-lg px-3 text-xs font-medium text-muted transition hover:bg-canvas hover:text-text">标为已读</button>
              ) : null}
            </article>
          );
        })}
      </section>

      <footer className="mt-4 flex items-center justify-between text-xs text-muted">
        <span>共 {total} 条消息与任务动态</span>
        <div className="flex items-center gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-white disabled:opacity-35"><ChevronLeft size={15} /></button>
          <span>{page} / {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)} className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-white disabled:opacity-35"><ChevronRight size={15} /></button>
        </div>
      </footer>
    </div>
  );
}
