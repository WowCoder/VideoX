// ──────────────────────────────────────────────
// OpenVMA - 登录 / 注册弹窗
// 两种模式：login / register
// 两种方式：手机验证码 / 微信扫码
// ──────────────────────────────────────────────

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "@/router";
import {
  AlertCircle,
  ArrowRight,
  Lock,
  Loader2,
  Mail,
  MessageSquare,
  Phone,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { sendSmsCode, getWechatQrcode } from "@/api/auth";

type Mode = "login" | "register";
type Channel = "email" | "phone" | "wechat";

const benefits = [
  "AI 自动理解脚本与素材语义",
  "几分钟完成镜头匹配与初剪装配",
  "缺失画面由 AI 一致性生成补齐",
  "多格式导出，继续精剪或交付成片",
];

export function AuthModal() {
  const { authModalMode, closeAuth, openAuth, notify } = useUIStore();
  const { login, register, loginWithPhone, loading: isLoading } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const [channel, setChannel] = useState<Channel>("email");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [countdown, setCountdown] = useState(0);

  // 微信二维码状态
  const [wechatQrcode, setWechatQrcode] = useState<string | null>(null);
  const [wechatError, setWechatError] = useState<string | null>(null);
  const [wechatLoading, setWechatLoading] = useState(false);

  const mode: Mode = authModalMode === "register" ? "register" : "login";

  // 倒计时
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  // ESC 关闭
  useEffect(() => {
    if (!authModalMode) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeAuth();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [authModalMode, closeAuth]);

  // 切换到微信渠道时获取二维码
  useEffect(() => {
    if (channel !== "wechat") return;
    let cancelled = false;
    setWechatLoading(true);
    setWechatError(null);
    setWechatQrcode(null);
    getWechatQrcode()
      .then((res) => {
        if (!cancelled) {
          setWechatQrcode(res.url);
          setWechatLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setWechatError(err instanceof Error ? err.message : "微信登录未配置");
          setWechatLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [channel]);

  if (!authModalMode) return null;

  async function sendCode() {
    if (!phone.trim()) {
      notify("请输入手机号", "error");
      return;
    }
    try {
      const res = await sendSmsCode(phone);
      setCountdown(60);
      notify(res.message || "验证码已发送");
    } catch (err) {
      const message = err instanceof Error ? err.message : "验证码发送失败";
      notify(message, "error");
    }
  }

  async function handleSubmit() {
    if (channel === "email") {
      if (!email.trim() || !password) {
        notify("请输入邮箱和密码", "error");
        return;
      }
      if (mode === "register" && !name.trim()) {
        notify("请输入昵称", "error");
        return;
      }
      try {
        const user = mode === "register"
          ? await register({ email: email.trim(), password, name: name.trim() })
          : await login({ email: email.trim(), password });
        notify(mode === "register" ? "注册成功，欢迎使用 OpenVMA" : `登录成功，欢迎回来 ${user.name}`);
        closeAuth();
        if (!location.pathname.startsWith("/invite/")) navigate("/workspace");
      } catch (err) {
        notify(err instanceof Error ? err.message : "登录失败，请稍后重试", "error");
      }
    } else if (channel === "phone") {
      if (!phone.trim()) {
        notify("请输入手机号", "error");
        return;
      }
      if (!code.trim()) {
        notify("请输入验证码", "error");
        return;
      }
      try {
        const user = await loginWithPhone(
          phone,
          code,
          mode === "register" ? name : undefined,
        );
        notify(
          mode === "register"
            ? "注册成功，欢迎使用 OpenVMA"
            : `登录成功，欢迎回来 ${user.name}`,
        );
        closeAuth();
        if (!location.pathname.startsWith("/invite/")) navigate("/workspace");
      } catch (err) {
        const message = err instanceof Error ? err.message : "登录失败，请稍后重试";
        notify(message, "error");
      }
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      {/* 遮罩 */}
      <button
        className="absolute inset-0 cursor-default bg-ink/60 backdrop-blur-sm"
        onClick={closeAuth}
        aria-label="关闭"
        type="button"
      />

      {/* 弹窗 */}
      <div className="relative z-10 grid w-full max-w-4xl overflow-hidden rounded-2xl bg-surface shadow-soft lg:grid-cols-[1fr_1.1fr]">
        {/* 左侧品牌区 */}
        <div className="relative hidden flex-col justify-between bg-gradient-to-br from-ink to-ink-2 p-8 text-white lg:flex">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal">
                <Sparkles size={18} />
              </span>
              <span className="text-lg font-semibold tracking-wide">OpenVMA</span>
            </div>
            <h2 className="mt-10 text-2xl font-bold leading-snug">
              把脚本和素材交给 AI，<br />几分钟得到一版可改的初剪。
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-white/60">
              从素材理解、镜头匹配到 AI 画面生成与初剪装配，创作者只需处理真正需要判断的部分。
            </p>
          </div>
          <ul className="space-y-2.5">
            {benefits.map((b) => (
              <li key={b} className="flex items-start gap-2 text-sm text-white/80">
                <ShieldCheck size={16} className="mt-0.5 shrink-0 text-teal" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
          <div className="absolute -bottom-12 -right-12 h-40 w-40 rounded-full bg-blue/20 blur-3xl" />
          <div className="absolute -top-8 -left-8 h-32 w-32 rounded-full bg-teal/10 blur-3xl" />
        </div>

        {/* 右侧表单区 */}
        <div className="flex flex-col p-6 lg:p-8">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-xl font-bold text-text">
              {mode === "register" ? "免费注册" : "欢迎回来"}
            </h3>
            <button
              onClick={closeAuth}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
              aria-label="关闭"
              type="button"
            >
              <X size={18} />
            </button>
          </div>

          {/* 方式切换 */}
          <div className="mb-6 flex gap-1 rounded-lg bg-canvas p-1">
            <button
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition ${
                channel === "email" ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
              }`}
              onClick={() => setChannel("email")}
              type="button"
            >
              <Mail size={15} />邮箱
            </button>
            <button
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition ${
                channel === "phone" ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
              }`}
              onClick={() => setChannel("phone")}
              type="button"
            >
              <Phone size={15} />手机验证码
            </button>
            <button
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition ${
                channel === "wechat" ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
              }`}
              onClick={() => setChannel("wechat")}
              type="button"
            >
              <MessageSquare size={15} />微信扫码
            </button>
          </div>

          {channel === "email" ? (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                void handleSubmit();
              }}
            >
              {mode === "register" && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">昵称</label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="请输入昵称"
                    className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">邮箱</label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    type="email"
                    className="w-full rounded-lg border border-line bg-surface py-2.5 pl-9 pr-3.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">密码</label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="至少 6 位密码"
                    type="password"
                    className="w-full rounded-lg border border-line bg-surface py-2.5 pl-9 pr-3.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2 disabled:opacity-60"
              >
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : mode === "register" ? "注册并开始使用" : "登录"}
              </button>
            </form>
          ) : channel === "phone" ? (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                handleSubmit();
              }}
            >
              {mode === "register" && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">昵称</label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="请输入昵称"
                    className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">手机号</label>
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="请输入手机号"
                  type="tel"
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">验证码</label>
                <div className="flex gap-2">
                  <input
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="6 位验证码"
                    maxLength={6}
                    className="flex-1 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                  <button
                    type="button"
                    onClick={sendCode}
                    disabled={countdown > 0}
                    className="shrink-0 rounded-lg border border-blue px-4 text-sm font-medium text-blue transition hover:bg-blue-soft disabled:border-line disabled:text-muted"
                  >
                    {countdown > 0 ? `${countdown}s` : "获取验证码"}
                  </button>
                </div>
              </div>
              {mode === "register" && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">邮箱（选填，用于接收发票）</label>
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    type="email"
                    className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2 disabled:opacity-60"
              >
                {isLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    {mode === "register" ? "注册并开始使用" : "登录"}
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
          ) : (
            <div className="flex flex-col items-center justify-center py-8">
              {wechatLoading ? (
                <div className="flex h-48 w-48 flex-col items-center justify-center rounded-xl border-2 border-dashed border-line bg-canvas/50">
                  <Loader2 size={32} className="animate-spin text-muted" />
                  <span className="mt-3 text-xs text-muted">正在获取二维码…</span>
                </div>
              ) : wechatError ? (
                <div className="flex h-48 w-48 flex-col items-center justify-center rounded-xl border-2 border-dashed border-amber/30 bg-amber/5 px-4 text-center">
                  <AlertCircle size={32} className="text-amber" />
                  <span className="mt-3 text-xs text-amber">{wechatError}</span>
                  <span className="mt-1 text-xs text-muted">请使用手机验证码登录</span>
                </div>
              ) : wechatQrcode ? (
                <div className="flex flex-col items-center">
                  <ShieldCheck className="h-16 w-16 text-teal" />
                  <p className="mt-4 text-sm text-muted">
                    点击下方按钮进入微信开放平台完成扫码授权
                  </p>
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  if (wechatQrcode) window.location.assign(wechatQrcode);
                }}
                disabled={!wechatQrcode || wechatLoading}
                className="mt-6 flex items-center gap-2 rounded-lg bg-blue px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2 disabled:opacity-60"
              >
                {wechatLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <>
                    微信扫码{mode === "register" ? "注册" : "登录"}
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          )}

          {/* 切换模式 */}
          <p className="mt-6 text-center text-sm text-muted">
            {mode === "register" ? "已有账号？" : "还没有账号？"}
            <button
              type="button"
              className="ml-1 font-medium text-blue hover:underline"
              onClick={() => openAuth(mode === "register" ? "login" : "register")}
            >
              {mode === "register" ? "立即登录" : "免费注册"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default AuthModal;
