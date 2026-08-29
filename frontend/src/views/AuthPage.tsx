import { useEffect, useState, type FormEvent } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Film,
  Loader2,
  MessageCircle,
  ShieldCheck,
  Smartphone,
  Sparkles,
} from "lucide-react";
import { getWechatQrcode, sendSmsCode } from "@/api/auth";
import { BrandLogo } from "@/components/BrandLogo";
import { useLocation, useNavigate } from "@/router";
import {
  encodeWechatNavigationState,
  getPostAuthStartAction,
  type PostAuthStartAction,
} from "@/lib/publicNavigation";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import "./AuthPanel.css";
import "./AuthPage.css";

type AuthMode = "login" | "register";
type AuthChannel = "phone" | "wechat";

const AUTH_VALUE_POINTS = [
  [FileText, "从一份文字开始", "粘贴文章、口播稿或课程文档即可。"],
  [Sparkles, "AI 完成制作规划", "自动生成策划、脚本、分镜与素材建议。"],
  [Film, "像改文档一样做影片", "在同一个项目里预览、调整并完成成片。"],
] as const;

const AUTH_BENEFITS = [
  "保存单支视频项目、分镜和主时间线",
  "同步 AI 任务结果与处理额度",
  "登录后可从工作台继续视频项目",
];

interface Feedback {
  type: "success" | "error";
  message: string;
}

function isFinderCell(row: number, column: number, top: number, left: number): boolean {
  const localRow = row - top;
  const localColumn = column - left;
  if (localRow < 0 || localRow > 6 || localColumn < 0 || localColumn > 6) return false;
  return localRow === 0
    || localRow === 6
    || localColumn === 0
    || localColumn === 6
    || (localRow >= 2 && localRow <= 4 && localColumn >= 2 && localColumn <= 4);
}

function isFinderArea(row: number, column: number, top: number, left: number): boolean {
  return row >= top - 1 && row <= top + 7 && column >= left - 1 && column <= left + 7;
}

const QR_CELLS = Array.from({ length: 21 * 21 }, (_, index) => {
  const row = Math.floor(index / 21);
  const column = index % 21;
  const finder = isFinderCell(row, column, 0, 0)
    || isFinderCell(row, column, 0, 14)
    || isFinderCell(row, column, 14, 0);
  const reserved = isFinderArea(row, column, 0, 0)
    || isFinderArea(row, column, 0, 14)
    || isFinderArea(row, column, 14, 0);
  const dataCell = !reserved && (
    (row * 3 + column * 5 + row * column) % 11 < 4
    || (row + column * 2) % 7 === 0
    || (row * 5 + column) % 13 === 1
  );
  return finder || dataCell;
});

function WechatQrCode() {
  return (
    <div className="auth-wechat-qr" aria-label="微信登录二维码">
      <div className="auth-qr-grid" aria-hidden="true">
        {QR_CELLS.map((dark, index) => <i className={dark ? "is-dark" : ""} key={index} />)}
      </div>
      <span><MessageCircle size={21} fill="currentColor" /></span>
    </div>
  );
}

function normalizePhone(value: string): string {
  return value.replace(/\D/g, "").slice(0, 11);
}

function AuthPanel({
  mode,
  postAuthAction,
  onSwitchMode,
}: {
  mode: AuthMode;
  postAuthAction: PostAuthStartAction | null;
  onSwitchMode: (mode: AuthMode) => void;
}) {
  const isRegister = mode === "register";
  const [channel, setChannel] = useState<AuthChannel>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [wechatUrl, setWechatUrl] = useState<string | null>(null);
  const [wechatLoading, setWechatLoading] = useState(false);
  const { loginWithPhone, loading } = useAuthStore();
  const notify = useUIStore((state) => state.notify);
  const navigate = useNavigate();

  useEffect(() => {
    setFeedback(null);
  }, [mode, channel]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  useEffect(() => {
    if (channel !== "wechat") return;
    let cancelled = false;
    setWechatLoading(true);
    setFeedback(null);
    setWechatUrl(null);
    void getWechatQrcode(encodeWechatNavigationState(postAuthAction))
      .then(({ url }) => {
        if (!cancelled) setWechatUrl(url);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setFeedback({
            type: "error",
            message: error instanceof Error ? error.message : "微信登录暂不可用",
          });
        }
      })
      .finally(() => {
        if (!cancelled) setWechatLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [channel, postAuthAction]);

  async function requestCode() {
    if (!/^1\d{10}$/.test(phone)) {
      setFeedback({ type: "error", message: "请输入正确的 11 位手机号" });
      return;
    }
    try {
      const result = await sendSmsCode(phone);
      setCountdown(60);
      setFeedback({ type: "success", message: result.message || "验证码已发送" });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error instanceof Error ? error.message : "验证码发送失败，请稍后重试",
      });
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback(null);
    try {
      if (!/^1\d{10}$/.test(phone)) throw new Error("请输入正确的 11 位手机号");
      if (!/^\d{4,8}$/.test(code)) throw new Error("请输入手机验证码");
      const user = await loginWithPhone(phone, code);
      notify(isRegister ? "注册成功，欢迎使用 OpenVMA" : `登录成功，欢迎回来 ${user.name}`);
      navigate("/workspace", {
        replace: true,
        state: postAuthAction ? { postAuthAction } : undefined,
      });
    } catch (error) {
      setFeedback({ type: "error", message: error instanceof Error ? error.message : "认证失败，请稍后重试" });
    }
  }

  const title = channel === "wechat"
    ? `微信扫码${isRegister ? "注册" : "登录"} OpenVMA`
    : isRegister ? "使用手机号创建 OpenVMA 工作区" : "使用手机号登录 OpenVMA";
  const description = channel === "wechat"
    ? isRegister ? "使用微信扫一扫，确认后即可创建工作区。" : "使用微信扫一扫，在手机上确认登录。"
    : isRegister ? "无需填写姓名，验证手机号后即可开始创作。" : "输入手机号和验证码，继续处理你的项目。";

  return (
    <section className="auth-modal is-standalone" role="region" aria-labelledby="auth-modal-title">
      <header>
        <span className={`auth-modal-icon ${channel === "wechat" ? "is-wechat" : ""}`}>
          {channel === "wechat" ? <MessageCircle size={19} fill="currentColor" /> : <Sparkles size={19} />}
        </span>
        <div>
          <p>OpenVMA 账号</p>
          <h2 id="auth-modal-title">{title}</h2>
          <span>{description}</span>
        </div>
      </header>

      <div className="auth-mode-tabs" role="tablist" aria-label="登录注册切换">
        <button className={!isRegister ? "is-active" : ""} onClick={() => onSwitchMode("login")} type="button" role="tab" aria-selected={!isRegister}>登录</button>
        <button className={isRegister ? "is-active" : ""} onClick={() => onSwitchMode("register")} type="button" role="tab" aria-selected={isRegister}>注册</button>
      </div>

      <div className="auth-channel-tabs" role="tablist" aria-label="认证方式">
        <button className={channel === "phone" ? "is-active" : ""} onClick={() => setChannel("phone")} type="button" role="tab" aria-selected={channel === "phone"}><Smartphone size={14} />手机验证码</button>
        <button className={`is-wechat ${channel === "wechat" ? "is-active" : ""}`} onClick={() => setChannel("wechat")} type="button" role="tab" aria-selected={channel === "wechat"}><MessageCircle size={14} fill="currentColor" />微信扫码</button>
      </div>

      {channel === "wechat" ? (
        <section className="auth-wechat-panel" aria-label="微信扫码认证">
          {wechatLoading ? <div className="auth-wechat-provider"><Loader2 className="is-spinning" size={34} /><span>正在连接微信开放平台…</span></div> : feedback?.type === "error" ? <div className="auth-wechat-provider is-error"><AlertCircle size={34} /><span>{feedback.message}</span></div> : <WechatQrCode />}
          <div className="auth-wechat-copy">
            <strong>打开微信完成授权</strong>
            <p>{isRegister ? "确认后会自动创建 OpenVMA 账号。" : "请在微信中确认登录，本次授权链接短时间内有效。"}</p>
          </div>
          <button className="auth-wechat-submit" disabled={!wechatUrl || wechatLoading} onClick={() => wechatUrl && window.location.assign(wechatUrl)} type="button">
            {wechatLoading ? <Loader2 className="is-spinning" size={16} /> : <MessageCircle size={16} fill="currentColor" />}
            微信扫码{isRegister ? "注册" : "登录"}
          </button>
        </section>
      ) : (
        <form className="auth-form" onSubmit={submit}>
          <label>
            <span>手机号</span>
            <div className="auth-phone-input"><Smartphone size={16} /><b>+86</b><i aria-hidden="true" /><input type="tel" inputMode="numeric" value={phone} onChange={(event) => setPhone(normalizePhone(event.target.value))} autoComplete="tel" aria-label="手机号" placeholder="请输入手机号" /></div>
          </label>
          <label>
            <span>手机验证码</span>
            <div className="auth-code-row">
              <div className="auth-code-input"><ShieldCheck size={16} /><input type="text" inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 8))} autoComplete="one-time-code" placeholder="输入 6 位验证码" aria-label="手机验证码" /></div>
              <button onClick={() => void requestCode()} disabled={countdown > 0} type="button">{countdown ? `${countdown}s 后重发` : "获取验证码"}</button>
            </div>
          </label>

          {feedback ? <p className={`auth-feedback is-${feedback.type}`} role={feedback.type === "error" ? "alert" : "status"}>{feedback.type === "success" ? <Check size={14} /> : <AlertCircle size={14} />}{feedback.message}</p> : null}
          <button className="auth-submit" disabled={loading} type="submit">
            {loading ? <Loader2 className="is-spinning" size={16} /> : null}
            {isRegister ? "验证并免费注册" : "验证并登录"}<ArrowRight size={16} />
          </button>
        </form>
      )}

      <p className="auth-terms">登录或注册即代表你已阅读并同意《服务条款》和《隐私政策》</p>
      <div className="auth-benefits" aria-label="账号权益">
        {AUTH_BENEFITS.map((benefit) => <span key={benefit}><ShieldCheck size={14} />{benefit}</span>)}
      </div>
      <footer><span>{isRegister ? "已有账号？" : "还没有账号？"}</span><button onClick={() => onSwitchMode(isRegister ? "login" : "register")} type="button">{isRegister ? "去登录" : "免费注册"}</button></footer>
    </section>
  );
}

export function AuthPage({ mode }: { mode: AuthMode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isRegister = mode === "register";
  const postAuthAction = getPostAuthStartAction(location.state);

  return (
    <main className="auth-page">
      <header className="auth-page-header">
        <button className="auth-page-brand" onClick={() => navigate("/")} aria-label="返回 OpenVMA 官网" type="button"><BrandLogo variant="wordmark" tone="dark" height={16} decorative /></button>
        <button className="auth-page-back" onClick={() => navigate("/")} type="button"><ArrowLeft size={15} />返回官网</button>
      </header>

      <section className="auth-page-layout">
        <div className="auth-page-intro">
          <span className="auth-page-kicker">OPENVMA ACCOUNT</span>
          <h1>{isRegister ? "从第一段文字，\n开始第一支影片。" : "欢迎回来，\n继续完成你的影片。"}</h1>
          <p>{isRegister ? "不需要先学会策划、分镜或剪辑。创建工作区后，把想表达的内容交给 OpenVMA。" : "你的项目、脚本、素材和生成记录都保留在同一个工作区中。"}</p>
          <div className="auth-page-points" aria-label="OpenVMA 工作区能力">
            {AUTH_VALUE_POINTS.map(([Icon, title, description]) => <article key={title}><span><Icon size={17} /></span><div><strong>{title}</strong><small>{description}</small></div></article>)}
          </div>
          <small className="auth-page-note"><Check size={13} />项目自动保存，可随时回来继续。</small>
        </div>

        <div className="auth-page-panel">
          {isAuthenticated ? (
            <div className="auth-page-session" role="status"><span><Check size={13} /></span><p><strong>当前设备已登录</strong><small>你可以直接返回工作台，或验证其他账号。</small></p><button onClick={() => navigate("/workspace")} type="button">进入工作台</button></div>
          ) : null}
          <AuthPanel
            mode={mode}
            postAuthAction={postAuthAction}
            onSwitchMode={(nextMode) => navigate(`/${nextMode}`, { state: location.state })}
          />
        </div>
      </section>

      <footer className="auth-page-footer"><span>© 2026 OpenVMA</span><nav aria-label="账号页底部链接"><a href="#terms">服务条款</a><a href="#privacy">隐私政策</a></nav></footer>
    </main>
  );
}

export default AuthPage;
