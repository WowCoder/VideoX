import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Sparkles, WandSparkles, X } from "lucide-react";

export interface AIScriptRequest extends Record<string, unknown> {
  prompt: string;
  tone: string;
  duration_seconds: number;
  include_asset_context: boolean;
}

interface Props {
  open: boolean;
  projectName: string;
  existingSceneCount: number;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onGenerate: (request: AIScriptRequest) => void;
}

const tones = ["专业清晰", "科技未来", "温暖叙事", "轻快有力"];
const durations = [30, 60, 90, 120];

export function AIScriptGeneratorModal({
  open,
  projectName,
  existingSceneCount,
  pending,
  error,
  onClose,
  onGenerate,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [tone, setTone] = useState(tones[0]);
  const [duration, setDuration] = useState(60);
  const [includeAssetContext, setIncludeAssetContext] = useState(true);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPrompt("");
    setTone(tones[0]);
    setDuration(60);
    setIncludeAssetContext(true);
    setSubmitted(false);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !pending) onClose();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open, pending]);

  if (!open) return null;
  const valid = prompt.trim().length >= 10;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!valid || pending) return;
    onGenerate({
      prompt: prompt.trim(),
      tone,
      duration_seconds: duration,
      include_asset_context: includeAssetContext,
    });
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭 AI 脚本生成" onClick={() => !pending && onClose()} className="absolute inset-0 bg-ink/55 backdrop-blur-sm" />
      <form onSubmit={submit} className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-2xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl" aria-labelledby="ai-script-title">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><WandSparkles size={19} /></span>
          <div className="min-w-0 flex-1"><h2 id="ai-script-title" className="text-base font-semibold text-text">AI 生成项目脚本</h2><p className="mt-1 truncate text-xs text-muted">{projectName} · 从目标生成可直接编辑的场景和镜头</p></div>
          <button type="button" aria-label="关闭" disabled={pending} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>

        <div className="space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
          <label className="block text-sm font-medium text-text">描述你想制作的视频<textarea autoFocus rows={5} maxLength={2000} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：制作一支 60 秒新品发布短片，先建立使用场景，再突出三个核心能力，最后以品牌愿景收束。" className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 outline-none focus:ring-2 focus:ring-blue/10 ${submitted && !valid ? "border-red" : "border-line focus:border-blue/50"}`} /></label>
          <div className="-mt-4 flex justify-between text-[11px]"><span className={submitted && !valid ? "text-red" : "text-muted"}>{submitted && !valid ? "至少输入 10 个字符" : "AI 会将目标拆成场景、旁白和镜头描述"}</span><span className="text-muted">{prompt.length}/2000</span></div>

          <fieldset><legend className="text-xs font-semibold text-text">目标时长</legend><div className="mt-2 grid grid-cols-4 gap-2">{durations.map((value) => <button key={value} type="button" onClick={() => setDuration(value)} className={`flex items-center justify-center gap-1 rounded-lg border py-2 text-xs ${duration === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value} 秒{duration === value && <Check size={12} />}</button>)}</div></fieldset>
          <fieldset><legend className="text-xs font-semibold text-text">表达语气</legend><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{tones.map((value) => <button key={value} type="button" onClick={() => setTone(value)} className={`rounded-lg border px-2 py-2 text-xs ${tone === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value}</button>)}</div></fieldset>

          <label className="flex items-start gap-3 rounded-xl border border-line bg-canvas/60 p-4"><input type="checkbox" checked={includeAssetContext} onChange={(event) => setIncludeAssetContext(event.target.checked)} className="mt-0.5 accent-blue" /><span><strong className="block text-xs text-text">参考项目素材分析结果</strong><small className="mt-1 block text-[11px] leading-5 text-muted">使用已完成的对白、OCR 和标签摘要，让生成内容更容易匹配当前素材。</small></span></label>
          {existingSceneCount > 0 && <div className="flex gap-2 rounded-xl border border-amber/20 bg-amber/5 p-3 text-[11px] leading-5 text-amber"><AlertTriangle size={15} className="mt-0.5 shrink-0" /><span>应用新脚本会替换当前 {existingSceneCount} 个场景；现有结构已保存在不可变项目版本中，素材本身不会删除。</span></div>}
          {error && <div className="rounded-xl bg-red/5 p-3 text-xs text-red">{error}</div>}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-line bg-canvas/50 px-5 py-4 sm:px-6"><p className="hidden text-[11px] text-muted sm:block"><Sparkles size={13} className="mr-1 inline" />任务将在后台真实调用文本模型</p><div className="ml-auto flex gap-2"><button type="button" disabled={pending} onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="submit" disabled={pending} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{pending ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}{pending ? "正在创建任务…" : "生成并应用"}</button></div></footer>
      </form>
    </div>
  );
}
