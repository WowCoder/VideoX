import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useNavigate, useSearchParams } from "@/router";
import { useAuthStore } from "@/stores/authStore";
import { decodeWechatNavigationState } from "@/lib/publicNavigation";

export default function WechatCallbackView() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const loginWithWechat = useAuthStore((state) => state.loginWithWechat);
  const started = useRef(false);
  const code = searchParams.get("code");
  const postAuthAction = decodeWechatNavigationState(searchParams.get("state"));
  const [error, setError] = useState<string | null>(
    code ? null : "微信授权未返回有效 code",
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!code) return;
    void loginWithWechat(code)
      .then(() => navigate("/workspace", {
        replace: true,
        state: postAuthAction ? { postAuthAction } : undefined,
      }))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "微信登录失败"));
  }, [code, loginWithWechat, navigate, postAuthAction]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-soft">
        {error ? (
          <>
            <h1 className="text-lg font-semibold text-text">微信登录失败</h1>
            <p className="mt-2 text-sm text-muted">{error}</p>
            <button type="button" onClick={() => navigate("/", { replace: true })} className="mt-5 rounded-lg bg-blue px-4 py-2 text-sm text-white">
              返回首页
            </button>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-blue" />
            <h1 className="mt-4 text-lg font-semibold text-text">正在完成微信登录</h1>
            <p className="mt-2 text-sm text-muted">正在验证授权信息，请稍候…</p>
          </>
        )}
      </div>
    </main>
  );
}
