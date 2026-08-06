import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CheckCircle2, Loader2, ShieldCheck, Users } from "lucide-react";
import { useNavigate, useParams } from "@/router";

import * as projectApi from "@/api/projects";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";

export function InvitationView() {
  const { token = "" } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const openAuth = useUIStore((state) => state.openAuth);
  const notify = useUIStore((state) => state.notify);

  const previewQuery = useQuery({
    queryKey: ["project-invitation", token],
    queryFn: () => projectApi.previewInvitation(token),
    enabled: !!token,
    retry: false,
  });
  const acceptMutation = useMutation({
    mutationFn: () => projectApi.acceptInvitation(token),
    onSuccess: (result) => {
      notify(`已加入「${result.projectName}」`);
      navigate(`/workspace/projects/${result.projectId}`, { replace: true });
    },
    onError: (error) => notify(error instanceof Error ? error.message : "接受邀请失败", "error"),
  });

  const preview = previewQuery.data;
  const canAccept = preview?.status === "pending";
  const roleLabel = preview?.role === "editor" ? "编辑者" : "查看者";

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-5 py-12">
      <section className="w-full max-w-lg overflow-hidden rounded-2xl border border-line bg-surface shadow-soft">
        <div className="bg-gradient-to-br from-ink to-ink-2 px-8 py-7 text-white">
          <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={18} className="text-teal" />OpenVMA 项目邀请</div>
          <h1 className="mt-5 text-2xl font-bold">加入协作项目</h1>
          <p className="mt-2 text-sm text-white/60">邀请信息来自真实项目数据，接受后权限立即生效。</p>
        </div>
        <div className="p-8">
          {previewQuery.isLoading ? (
            <div className="flex justify-center py-12"><Loader2 size={26} className="animate-spin text-muted" /></div>
          ) : previewQuery.error ? (
            <div className="py-8 text-center">
              <AlertCircle size={32} className="mx-auto text-red" />
              <h2 className="mt-3 font-semibold text-text">邀请链接不可用</h2>
              <p className="mt-1 text-sm text-muted">{previewQuery.error instanceof Error ? previewQuery.error.message : "请联系项目所有者重新邀请"}</p>
              <button type="button" onClick={() => void previewQuery.refetch()} className="mt-5 rounded-lg bg-blue px-4 py-2 text-sm text-white">重试</button>
            </div>
          ) : preview ? (
            <div>
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-soft text-blue"><Users size={25} /></div>
              <h2 className="mt-5 text-xl font-bold text-text">{preview.projectName}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{preview.inviterName} 邀请 <strong className="text-text">{preview.recipient}</strong> 以“{roleLabel}”身份加入该项目。</p>
              <div className="mt-5 rounded-xl border border-line bg-canvas/60 p-4 text-sm">
                <div className="flex justify-between"><span className="text-muted">项目角色</span><strong className="text-text">{roleLabel}</strong></div>
                <div className="mt-2 flex justify-between"><span className="text-muted">邀请状态</span><strong className={canAccept ? "text-teal" : "text-red"}>{canAccept ? "待接受" : preview.status === "expired" ? "已过期" : "已失效"}</strong></div>
                <div className="mt-2 flex justify-between"><span className="text-muted">有效期至</span><span className="text-text">{new Date(preview.expiresAt).toLocaleString("zh-CN")}</span></div>
              </div>

              {!canAccept ? (
                <div className="mt-6 flex items-center gap-2 rounded-lg bg-red/5 p-3 text-sm text-red"><AlertCircle size={16} />该邀请无法继续使用，请联系项目所有者。</div>
              ) : !isAuthenticated ? (
                <button type="button" onClick={() => openAuth("login")} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-blue py-3 text-sm font-semibold text-white">登录后接受邀请<ArrowRight size={16} /></button>
              ) : (
                <>
                  <p className="mt-5 text-xs text-muted">当前账户：{user?.email}。只有与邀请邮箱一致的账户可以接受。</p>
                  <button type="button" disabled={acceptMutation.isPending} onClick={() => acceptMutation.mutate()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-blue py-3 text-sm font-semibold text-white disabled:opacity-50">
                    {acceptMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}接受并加入项目
                  </button>
                </>
              )}
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}

export default InvitationView;
