import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Sparkles, WandSparkles, X } from "lucide-react";
import { estimateProjectOperation, type OperationEstimate } from "@/api/generate";

export interface AIScriptRequest extends Record<string, unknown> {
  prompt: string;
  tone: string;
  duration_seconds: number;
  include_asset_context: boolean;
}

interface Props {
  open: boolean;
  projectName: string;
  projectId: string;
  expectedRevision: number;
  existingSceneCount: number;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onGenerate: (request: AIScriptRequest, pricingCatalogId?: string) => void;
}

const tones = ["专业清晰", "科技未来", "温暖叙事", "轻快有力"];
const durations = [30, 60, 90, 120];

export function AIScriptGeneratorModal({
  open,
  projectName,
  projectId,
  expectedRevision,
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
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [estimate, setEstimate] = useState<OperationEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPrompt("");
    setTone(tones[0]);
    setDuration(60);
    setIncludeAssetContext(true);
    setReplaceConfirmed(false);
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

  useEffect(() => {
    if (!open || prompt.trim().length < 10 || projectId === "__preview__") {
      setEstimate(null);
      setEstimateLoading(false);
      return;
    }
    let cancelled = false;
    setEstimateLoading(true);
    const timer = window.setTimeout(() => {
      void estimateProjectOperation(projectId, {
        operation: "generate_script", scope: { type: "project" }, expectedRevision,
        parameters: { prompt: prompt.trim(), tone, duration_seconds: duration, include_asset_context: includeAssetContext },
      }).then((value) => { if (!cancelled) setEstimate(value); }).catch(() => { if (!cancelled) setEstimate(null); }).finally(() => { if (!cancelled) setEstimateLoading(false); });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [duration, expectedRevision, includeAssetContext, open, projectId, prompt, tone]);

  if (!open) return null;
  const replacing = existingSceneCount > 0;
  const promptValid = prompt.trim().length >= 10;
  const valid = promptValid && (!replacing || replaceConfirmed);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!valid || pending || !estimate?.sufficient) return;
    onGenerate({
      prompt: prompt.trim(),
      tone,
      duration_seconds: duration,
      include_asset_context: includeAssetContext,
    }, estimate.catalogVersionId);
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <button type="button" aria-label="关闭 AI 脚本生成" onClick={() => !pending && onClose()} className="absolute inset-0 bg-ink/55 backdrop-blur-sm" />
      <form onSubmit={submit} className="relative z-10 grid max-h-[calc(100vh-32px)] w-full max-w-2xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden rounded-2xl border border-line bg-white shadow-2xl" aria-labelledby="ai-script-title">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-soft text-blue"><WandSparkles size={19} /></span>
          <div className="min-w-0 flex-1"><h2 id="ai-script-title" className="text-base font-semibold text-text">{replacing ? "AI 重写全片" : "AI 生成项目脚本"}</h2><p className="mt-1 truncate text-xs text-muted">{projectName} · {replacing ? "生成新结构并替换现有场景与镜头" : "从目标生成可直接编辑的场景和镜头"}</p></div>
          <button type="button" aria-label="关闭" disabled={pending} onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas disabled:opacity-40"><X size={18} /></button>
        </header>

        <div className="space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
          <label className="block text-sm font-medium text-text">描述你想制作的视频<textarea autoFocus rows={5} maxLength={2000} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：制作一支 60 秒新品发布短片，先建立使用场景，再突出三个核心能力，最后以品牌愿景收束。" className={`mt-2 w-full resize-y rounded-xl border p-3 text-sm leading-6 outline-none focus:ring-2 focus:ring-blue/10 ${submitted && !promptValid ? "border-red" : "border-line focus:border-blue/50"}`} /></label>
          <div className="-mt-4 flex justify-between text-[11px]"><span className={submitted && !promptValid ? "text-red" : "text-muted"}>{submitted && !promptValid ? "至少输入 10 个字符" : "AI 会将目标拆成场景、旁白和镜头描述"}</span><span className="text-muted">{prompt.length}/2000</span></div>

          <fieldset><legend className="text-xs font-semibold text-text">目标时长</legend><div className="mt-2 grid grid-cols-4 gap-2">{durations.map((value) => <button key={value} type="button" onClick={() => setDuration(value)} className={`flex items-center justify-center gap-1 rounded-lg border py-2 text-xs ${duration === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value} 秒{duration === value && <Check size={12} />}</button>)}</div></fieldset>
          <fieldset><legend className="text-xs font-semibold text-text">表达语气</legend><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{tones.map((value) => <button key={value} type="button" onClick={() => setTone(value)} className={`rounded-lg border px-2 py-2 text-xs ${tone === value ? "border-blue bg-blue-soft font-semibold text-blue" : "border-line text-muted"}`}>{value}</button>)}</div></fieldset>

          <label className="flex items-start gap-3 rounded-xl border border-line bg-canvas/60 p-4"><input type="checkbox" checked={includeAssetContext} onChange={(event) => setIncludeAssetContext(event.target.checked)} className="mt-0.5 accent-blue" /><span><strong className="block text-xs text-text">参考项目素材分析结果</strong><small className="mt-1 block text-[11px] leading-5 text-muted">使用已完成的对白、OCR 和标签摘要，让生成内容更容易匹配当前素材。</small></span></label>
          {replacing && <label className={`flex gap-3 rounded-xl border p-3 text-[11px] leading-5 ${submitted && !replaceConfirmed ? "border-red/30 bg-red/5 text-red" : "border-amber/20 bg-amber/5 text-amber"}`}><input type="checkbox" checked={replaceConfirmed} onChange={(event) => setReplaceConfirmed(event.target.checked)} className="mt-1 accent-amber" /><span><strong className="flex items-center gap-1.5"><AlertTriangle size={14} />我确认重写当前全片</strong><small className="mt-1 block text-[10px] leading-5 text-muted">新脚本将替换当前 {existingSceneCount} 个场景、现有镜头、场景级图层和当前成片时间线；项目素材本身不会删除。</small></span></label>}
          {submitted && replacing && !replaceConfirmed && <p className="text-xs text-red">请先确认会替换现有全片结构。</p>}
          <div className={`rounded-xl border p-3 ${estimate && !estimate.sufficient ? "border-red/25 bg-red/5" : "border-line bg-canvas/50"}`}><div className="flex items-center justify-between"><span className="text-xs font-semibold text-text">V-Credits 费用预估</span><strong className="text-sm text-text">{estimateLoading ? "计算中…" : estimate ? `${estimate.estimatedCredits.toLocaleString("zh-CN")} V-Credits` : "—"}</strong></div>{estimate && <p className="mt-1 text-[11px] text-muted">当前可用 {estimate.availableCredits.toLocaleString("zh-CN")} · 完成后预计剩余 {estimate.remainingAfter.toLocaleString("zh-CN")}</p>}{estimate && !estimate.sufficient && <p className="mt-1 text-xs font-medium text-red">余额不足，请先充值。</p>}</div>
          {error && <div className="rounded-xl bg-red/5 p-3 text-xs text-red">{error}</div>}
        </div>

          <footer className="flex items-center justify-between gap-3 border-t border-line bg-canvas/50 px-5 py-4 sm:px-6"><p className="hidden text-[11px] text-muted sm:block"><Sparkles size={13} className="mr-1 inline" />失败任务会自动释放 V-Credits</p><div className="ml-auto flex gap-2"><button type="button" disabled={pending} onClick={onClose} className="rounded-lg border border-line bg-white px-4 py-2 text-xs font-medium text-text disabled:opacity-40">取消</button><button type="submit" disabled={pending || estimateLoading || !estimate?.sufficient} className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold text-white disabled:opacity-50 ${replacing ? "bg-amber" : "bg-blue"}`}>{pending ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}{pending ? "正在创建任务…" : replacing ? "确认重写并替换" : "生成并应用"}</button></div></footer>
      </form>
    </div>
  );
}
