import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2, Mail, Shield, Trash2, UserPlus, Users, X } from "lucide-react";

import * as projectApi from "@/api/projects";
import { useUIStore } from "@/stores/uiStore";

interface Props {
  projectId: string;
  open: boolean;
  onClose: () => void;
}

const roleLabels = { owner: "所有者", editor: "编辑者", viewer: "查看者" } as const;
const invitationStatusLabels: Record<string, string> = {
  pending: "待接受", accepted: "已接受", revoked: "已撤销", expired: "已过期",
};

export function ProjectCollaborationModal({ projectId, open, onClose }: Props) {
  const queryClient = useQueryClient();
  const notify = useUIStore((state) => state.notify);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"editor" | "viewer">("editor");
  const [createdLink, setCreatedLink] = useState("");

  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, open]);

  const collaborationQuery = useQuery({
    queryKey: ["project-collaboration", projectId],
    queryFn: () => projectApi.getCollaboration(projectId),
    enabled: open,
    retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["project-collaboration", projectId] });

  const inviteMutation = useMutation({
    mutationFn: () => projectApi.inviteMember(projectId, { email: email.trim(), role }),
    onSuccess: (invitation) => {
      setEmail("");
      setCreatedLink(invitation.invitationUrl ?? "");
      void refresh();
      notify("邀请已创建；邮件服务未配置，请复制链接发送给成员", "info");
    },
    onError: (error) => notify(error instanceof Error ? error.message : "邀请创建失败", "error"),
  });
  const roleMutation = useMutation({
    mutationFn: ({ memberId, nextRole }: { memberId: string; nextRole: "editor" | "viewer" }) =>
      projectApi.updateMemberRole(projectId, memberId, nextRole),
    onSuccess: () => { void refresh(); notify("成员角色已更新"); },
    onError: (error) => notify(error instanceof Error ? error.message : "角色更新失败", "error"),
  });
  const removeMutation = useMutation({
    mutationFn: (memberId: string) => projectApi.removeMember(projectId, memberId),
    onSuccess: () => { void refresh(); notify("成员已移除"); },
    onError: (error) => notify(error instanceof Error ? error.message : "移除成员失败", "error"),
  });
  const revokeMutation = useMutation({
    mutationFn: (invitationId: string) => projectApi.revokeInvitation(projectId, invitationId),
    onSuccess: () => { void refresh(); notify("邀请已撤销"); },
    onError: (error) => notify(error instanceof Error ? error.message : "撤销邀请失败", "error"),
  });

  async function copyLink() {
    if (!createdLink) return;
    try {
      await navigator.clipboard.writeText(createdLink);
      notify("邀请链接已复制");
    } catch {
      notify("浏览器未允许复制，请手动选择链接", "error");
    }
  }

  if (!open) return null;
  const collaboration = collaborationQuery.data;
  const isOwner = collaboration?.currentUserRole === "owner";
  const canManageMembers = collaboration?.canManageMembers === true;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭成员管理" className="absolute inset-0 bg-ink/60 backdrop-blur-sm" onClick={onClose} />
      <section className="relative z-10 flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-surface shadow-soft">
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-text"><Users size={19} className="text-blue" />项目成员</h2>
            <p className="mt-1 text-xs text-muted">查看者只能读取项目，编辑者可以修改业务内容，只有所有者能管理成员和删除项目。</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 text-muted transition hover:bg-canvas hover:text-text" aria-label="关闭"><X size={18} /></button>
        </header>

        <div className="overflow-y-auto p-6">
          {collaborationQuery.isLoading ? (
            <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-muted" /></div>
          ) : collaborationQuery.error ? (
            <div className="rounded-xl border border-red/20 bg-red/5 p-5 text-center">
              <p className="text-sm text-red">{collaborationQuery.error instanceof Error ? collaborationQuery.error.message : "成员数据加载失败"}</p>
              <button type="button" className="mt-3 rounded-lg bg-blue px-3 py-2 text-sm text-white" onClick={() => void collaborationQuery.refetch()}>重试</button>
            </div>
          ) : collaboration ? (
            <div className="space-y-6">
              {isOwner && (
                <section className="rounded-xl border border-line bg-canvas/50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-text"><UserPlus size={16} />邀请成员</h3>
                    <span className="rounded-full bg-surface px-2.5 py-1 text-xs text-muted">席位 {collaboration.seatsUsed}/{collaboration.seatQuota}</span>
                  </div>
                  <form className="mt-3 grid gap-2 sm:grid-cols-[1fr_110px_auto]" onSubmit={(event) => {
                    event.preventDefault();
                    if (!canManageMembers) return notify("邀请成员需要 Team 会员", "error");
                    if (!email.trim()) return notify("请输入成员邮箱", "error");
                    inviteMutation.mutate();
                  }}>
                    <label className="relative">
                      <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                      <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="member@example.com" className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm text-text outline-none transition focus:border-blue" />
                    </label>
                    <select value={role} onChange={(event) => setRole(event.target.value as "editor" | "viewer")} className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-text outline-none focus:border-blue">
                      <option value="editor">编辑者</option><option value="viewer">查看者</option>
                    </select>
                    <button type="submit" disabled={!canManageMembers || inviteMutation.isPending} className="flex h-10 items-center justify-center gap-1.5 rounded-lg bg-blue px-4 text-sm font-medium text-white transition hover:bg-blue/90 disabled:opacity-50">
                      {inviteMutation.isPending && <Loader2 size={14} className="animate-spin" />}创建邀请
                    </button>
                  </form>
                  <p className="mt-2 text-xs text-muted">{collaboration.managementMessage}。当前未接入邮件发送服务，邀请链接 7 天有效。</p>
                  {createdLink && <div className="mt-3 flex gap-2 rounded-lg border border-blue/20 bg-blue-soft/40 p-2">
                    <input readOnly value={createdLink} className="min-w-0 flex-1 bg-transparent px-1 text-xs text-text outline-none" />
                    <button type="button" onClick={() => void copyLink()} className="flex shrink-0 items-center gap-1 rounded-md bg-surface px-2.5 py-1.5 text-xs text-blue shadow-sm"><Copy size={13} />复制</button>
                  </div>}
                </section>
              )}

              <section>
                <h3 className="mb-3 text-sm font-semibold text-text">已加入成员（{collaboration.members.length}）</h3>
                <ul className="divide-y divide-line rounded-xl border border-line">
                  {collaboration.members.map((member) => <li key={member.id} className="flex items-center gap-3 p-3.5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal text-sm font-medium text-white">{member.avatarInitial}</span>
                    <div className="min-w-0 flex-1"><strong className="block truncate text-sm text-text">{member.name}</strong><span className="block truncate text-xs text-muted">{member.email}</span></div>
                    {canManageMembers && member.role !== "owner" ? <select value={member.role} disabled={roleMutation.isPending} onChange={(event) => roleMutation.mutate({ memberId: member.id, nextRole: event.target.value as "editor" | "viewer" })} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs text-text">
                      <option value="editor">编辑者</option><option value="viewer">查看者</option>
                    </select> : <span className="flex items-center gap-1 rounded-full bg-canvas px-2.5 py-1 text-xs text-muted"><Shield size={12} />{roleLabels[member.role]}</span>}
                    {canManageMembers && member.role !== "owner" && <button type="button" aria-label={`移除 ${member.name}`} disabled={removeMutation.isPending} onClick={() => {
                      if (window.confirm(`确定将 ${member.name} 移出项目吗？`)) removeMutation.mutate(member.id);
                    }} className="rounded-lg p-2 text-muted transition hover:bg-red/10 hover:text-red"><Trash2 size={15} /></button>}
                  </li>)}
                </ul>
              </section>

              {isOwner && collaboration.invitations.length > 0 && <section>
                <h3 className="mb-3 text-sm font-semibold text-text">邀请记录</h3>
                <ul className="divide-y divide-line rounded-xl border border-line">
                  {collaboration.invitations.map((invitation) => <li key={invitation.id} className="flex items-center gap-3 p-3.5">
                    <Mail size={16} className="shrink-0 text-muted" />
                    <div className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium text-text">{invitation.email}</strong><span className="text-xs text-muted">{roleLabels[invitation.role]} · {invitationStatusLabels[invitation.status] ?? invitation.status}</span></div>
                    {canManageMembers && invitation.status === "pending" && <button type="button" disabled={revokeMutation.isPending} onClick={() => revokeMutation.mutate(invitation.id)} className="rounded-lg border border-line px-2.5 py-1.5 text-xs text-muted transition hover:border-red/30 hover:text-red">撤销</button>}
                  </li>)}
                </ul>
              </section>}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default ProjectCollaborationModal;
