import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useNavigate } from "@/router";

import * as notificationApi from "@/api/notifications";
import { formatRelativeTime } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";

const PAGE_SIZE = 20;

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
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications-page"] });
  };
  const markRead = useMutation({
    mutationFn: notificationApi.markRead,
    onSuccess: (item) => {
      refresh();
      if (item.link) navigate(item.link);
    },
    onError: (error) => notify(error instanceof Error ? error.message : "通知更新失败", "error"),
  });
  const markAll = useMutation({
    mutationFn: notificationApi.markAllRead,
    onSuccess: refresh,
    onError: (error) => notify(error instanceof Error ? error.message : "通知更新失败", "error"),
  });

  const total = notifications.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text">消息中心</h1>
          <p className="mt-1.5 text-sm text-muted">查看真实任务成功、失败和业务通知</p>
        </div>
        <button
          type="button"
          onClick={() => markAll.mutate()}
          disabled={!notifications.data?.unreadCount || markAll.isPending}
          className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-sm text-blue disabled:text-muted"
        >
          <CheckCheck size={16} />全部已读
        </button>
      </header>

      <div className="mb-4 flex flex-wrap gap-2">
        {(["all", "unread", "read"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => { setReadStatus(value); setPage(1); }}
            className={`rounded-lg px-3 py-1.5 text-sm ${readStatus === value ? "bg-blue text-white" : "border border-line bg-surface text-muted"}`}
          >
            {{ all: "全部", unread: "未读", read: "已读" }[value]}
          </button>
        ))}
        <select
          value={type}
          onChange={(event) => { setType(event.target.value); setPage(1); }}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-text"
        >
          <option value="">全部类型</option>
          <option value="success">成功</option>
          <option value="error">失败</option>
          <option value="info">信息</option>
        </select>
      </div>

      <section className="overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        {notifications.isLoading ? (
          <div className="flex justify-center py-20"><Loader2 className="animate-spin text-blue" /></div>
        ) : notifications.error ? (
          <div className="py-16 text-center">
            <p className="text-sm text-red">{notifications.error.message}</p>
            <button type="button" onClick={() => void notifications.refetch()} className="mt-3 text-sm text-blue">重试</button>
          </div>
        ) : !notifications.data?.items.length ? (
          <div className="py-20 text-center">
            <Bell className="mx-auto text-line" />
            <p className="mt-3 text-sm font-medium text-text">当前筛选下暂无通知</p>
          </div>
        ) : notifications.data.items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => markRead.mutate(item.id)}
            className="flex w-full items-start gap-3 border-b border-line/70 px-5 py-4 text-left transition hover:bg-canvas"
          >
            <span className={`mt-1 h-2.5 w-2.5 rounded-full ${item.isRead ? "bg-line" : item.type === "error" ? "bg-red" : "bg-blue"}`} />
            <span className="min-w-0 flex-1">
              <strong className="text-sm text-text">{item.title}</strong>
              <p className="mt-1 text-sm leading-relaxed text-muted">{item.message}</p>
              <small className="mt-1 block text-xs text-muted">{formatRelativeTime(item.createdAt)}</small>
            </span>
          </button>
        ))}
      </section>

      <footer className="mt-4 flex items-center justify-between text-sm text-muted">
        <span>共 {total} 条</span>
        <div className="flex items-center gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="rounded-lg border border-line p-2 disabled:opacity-40"><ChevronLeft size={16} /></button>
          <span>{page} / {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-line p-2 disabled:opacity-40"><ChevronRight size={16} /></button>
        </div>
      </footer>
    </div>
  );
}
