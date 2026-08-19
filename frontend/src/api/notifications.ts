import { http } from "./client";

interface RawNotification {
  id: string;
  project_id: string | null;
  job_id: string | null;
  type: string;
  title: string;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
  source?: "notification" | "job";
  status?: string | null;
  progress?: number | null;
  action_label?: string | null;
}

interface RawNotificationList {
  items: RawNotification[];
  total: number;
  unread_count: number;
}

export interface NotificationItem {
  id: string;
  projectId?: string;
  jobId?: string;
  type: string;
  title: string;
  message: string;
  link?: string;
  isRead: boolean;
  createdAt: string;
  source: "notification" | "job";
  status?: string;
  progress?: number;
  actionLabel?: string;
}

export interface NotificationList {
  items: NotificationItem[];
  total: number;
  unreadCount: number;
}

function mapNotification(raw: RawNotification): NotificationItem {
  return {
    id: raw.id,
    projectId: raw.project_id ?? undefined,
    jobId: raw.job_id ?? undefined,
    type: raw.type,
    title: raw.title,
    message: raw.message,
    link: raw.link ?? undefined,
    isRead: raw.is_read,
    createdAt: raw.created_at,
    source: raw.source ?? "notification",
    status: raw.status ?? undefined,
    progress: raw.progress ?? undefined,
    actionLabel: raw.action_label ?? undefined,
  };
}

export async function list(params?: {
  page?: number;
  pageSize?: number;
  type?: string;
  readStatus?: "all" | "read" | "unread";
}): Promise<NotificationList> {
  const query = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 50),
    read_status: params?.readStatus ?? "all",
  });
  if (params?.type) query.set("type", params.type);
  const raw = await http.get<RawNotificationList>(`/notifications/feed?${query.toString()}`);
  return {
    items: raw.items.map(mapNotification),
    total: raw.total,
    unreadCount: raw.unread_count,
  };
}

export async function markRead(id: string): Promise<NotificationItem> {
  return mapNotification(await http.post<RawNotification>(`/notifications/${id}/read`));
}

export function markAllRead(): Promise<{ updated: number }> {
  return http.post<{ updated: number }>("/notifications/read-all");
}
