import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Mic2, RefreshCw, X } from "lucide-react";
import { getVoiceoverWorkspace, type VoiceLine, type VoiceoverWorkspace } from "@/api/voiceover";
import { estimateProjectOperation, type OperationEstimate } from "@/api/generate";
import type { Scene, Shot } from "@/api/projects";
import { Select } from "@/components/ui/Select";

interface Props {
  open: boolean;
  projectId: string;
  expectedRevision: number;
  scenes: Scene[];
  selectedScene?: Scene;
  selectedShot?: Shot;
  pending: boolean;
  error?: string | null;
  onClose: () => void;
  onGenerate: (
    scope: { type: "project" | "scene"; sceneIds?: string[] },
    parameters: Record<string, unknown>,
    pricingCatalogId?: string,
  ) => void;
}

type Range = "project" | "scene" | "shot";

function time(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 100)) / 10;
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function staleCopy(line: VoiceLine) {
  if (!line.staleReasons?.length) return "字幕或时间已变更";
  const labels = line.staleReasons.map((reason) => ({
    cue_removed: "原台词已删除",
    text_changed: "字幕文字已修改",
    start_changed: "开始时间已调整",
    end_changed: "结束时间已调整",
    source_key_changed: "字幕来源已重建",
  })[reason]);
  return labels.filter(Boolean).join("、");
}

function userFacingVoiceoverError(message: string) {
  if (/dashscope|qwen|provider|model|api[_ -]?key|ai_tts_provider/i.test(message)) {
    return "AI 配音服务暂不可用，请稍后重试；如持续失败，请联系管理员。";
  }
  return message;
}

function selectedShotRange(scenes: Scene[], selectedShot?: Shot) {
  if (!selectedShot?.id) return null;
  let cursor = 0;
  for (const scene of scenes) {
    for (const shot of scene.shots) {
      const startMs = cursor;
      const endMs = startMs + Math.max(100, shot.durationMs || 0);
      if (shot.id === selectedShot.id) return { startMs, endMs, sceneId: scene.id };
      cursor = endMs;
    }
  }
  return null;
}

export function AIVoiceoverModal({
  open, projectId, expectedRevision, scenes, selectedScene, selectedShot, pending, error, onClose, onGenerate,
}: Props) {
  const [data, setData] = useState<VoiceoverWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [range, setRange] = useState<Range>("project");
  const [model, setModel] = useState("qwen-audio-3.0-tts-flash");
  const [voice, setVoice] = useState("longanfengyue");
  const [instruction, setInstruction] = useState("自然、清晰，语速适中，保持前后声线一致");
  const [emotion, setEmotion] = useState("");
  const [force, setForce] = useState(false);
  const [estimate, setEstimate] = useState<OperationEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);

  useEffect(() => {
    if (!open || !projectId || projectId === "__preview__") return;
    let active = true;
    setLoading(true);
    setLoadError(null);
    void getVoiceoverWorkspace(projectId)
      .then((workspace) => {
        if (!active) return;
        setData(workspace);
        setModel(workspace.defaultModel);
        setVoice(workspace.defaultVoice);
      })
      .catch((reason) => active && setLoadError(userFacingVoiceoverError(reason instanceof Error ? reason.message : "配音状态加载失败")))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [open, projectId]);

  const shotRange = useMemo(() => selectedShotRange(scenes, selectedShot), [scenes, selectedShot]);
  const selectedModel = data?.models.find((item) => item.id === model);
  useEffect(() => {
    if (selectedModel?.voices.length && !selectedModel.voices.some((item) => item.id === voice)) {
      setVoice(selectedModel.voices[0].id);
    }
  }, [selectedModel, voice]);

  const visibleLines = useMemo(() => data?.lines.filter((line) => {
    if (!line.captionEnabled && !line.voiceEnabled) return false;
    if (range === "project") return true;
    if (range === "scene") return line.sceneId === selectedScene?.id;
    return Boolean(shotRange && line.startMs < shotRange.endMs && line.endMs > shotRange.startMs);
  }) ?? [], [data?.lines, range, selectedScene?.id, shotRange]);

  const statusCounts = visibleLines.reduce(
    (counts, line) => ({ ...counts, [line.status]: (counts[line.status] ?? 0) + 1 }),
    {} as Record<string, number>,
  );
  const sceneNames = new Map(scenes.map((scene) => [scene.id, `场景 ${scene.index + 1} · ${scene.outline || "未命名场景"}`]));
  const groupedLines = visibleLines.reduce<Array<{ sceneId: string; lines: VoiceLine[] }>>((groups, line) => {
    const group = groups.find((item) => item.sceneId === line.sceneId);
    if (group) group.lines.push(line);
    else groups.push({ sceneId: line.sceneId, lines: [line] });
    return groups;
  }, []);
  const operationScope = useMemo(() => range === "project"
    ? { type: "project" as const }
    : { type: "scene" as const, sceneIds: [range === "scene" ? selectedScene?.id : shotRange?.sceneId].filter(Boolean) as string[] }, [range, selectedScene?.id, shotRange?.sceneId]);
  const operationParameters = useMemo(() => ({
    source: "effective_subtitles", model, voice, instruction, emotion,
    ...(range === "shot" ? { voice_line_ids: visibleLines.map((line) => line.id) } : {}),
    generate_mode: force ? "force_regenerate" : "missing_and_stale",
    apply_after_success: true,
  }), [emotion, force, instruction, model, range, visibleLines, voice]);

  useEffect(() => {
    if (!open || !visibleLines.length || projectId === "__preview__") {
      setEstimate(null);
      setEstimateLoading(false);
      return;
    }
    let cancelled = false;
    setEstimateLoading(true);
    const timer = window.setTimeout(() => {
      void estimateProjectOperation(projectId, { operation: "generate_voiceover", scope: operationScope, parameters: operationParameters, expectedRevision })
        .then((value) => { if (!cancelled) setEstimate(value); })
        .catch(() => { if (!cancelled) setEstimate(null); })
        .finally(() => { if (!cancelled) setEstimateLoading(false); });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [expectedRevision, open, operationParameters, operationScope, projectId, visibleLines.length]);

  if (!open) return null;

  function generateVisible() {
    if (!estimate?.sufficient) return;
    onGenerate(operationScope, operationParameters, estimate.catalogVersionId);
  }

  async function generateSingleLine(line: VoiceLine) {
    const scope = { type: "scene" as const, sceneIds: [line.sceneId] };
    const parameters = { source: "effective_subtitles", model, voice, instruction, emotion, voice_line_ids: [line.id], generate_mode: "force_regenerate", apply_after_success: true };
    try {
      const lineEstimate = await estimateProjectOperation(projectId, { operation: "generate_voiceover", scope, parameters, expectedRevision });
      if (!lineEstimate.sufficient) { setLoadError("V-Credits 余额不足，请先充值后再生成。"); return; }
      if (window.confirm(`本句预计最多消耗 ${lineEstimate.estimatedCredits.toLocaleString("zh-CN")} V-Credits，确认生成？`)) {
        onGenerate(scope, parameters, lineEstimate.catalogVersionId);
      }
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "暂时无法计算本句费用");
    }
  }

  return <div className="fixed inset-0 z-50 grid place-items-center bg-ink/45 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="voiceover-title">
    <section className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-line px-5 py-4">
        <div className="flex gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-soft text-blue"><Mic2 size={18} /></span><div><h2 id="voiceover-title" className="text-sm font-semibold text-text">AI 旁白生成</h2><p className="mt-1 text-[11px] text-muted">按照字幕逐段生成并合成旁白；字幕变化后会标记为需要更新，不会自动重新生成。</p></div></div>
        <button type="button" aria-label="关闭旁白生成" onClick={onClose} disabled={pending} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-canvas"><X size={15} /></button>
      </header>
      <div className="grid min-h-0 flex-1 md:grid-cols-[310px_1fr]">
        <div className="space-y-4 overflow-y-auto border-r border-line p-5">
          {(loadError || error) && <div className="flex gap-2 rounded-lg bg-red/5 p-3 text-xs text-red"><AlertTriangle size={14} className="shrink-0" />{userFacingVoiceoverError(loadError || error || "配音服务暂不可用")}</div>}
          {loading ? <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={14} className="animate-spin" />加载配音配置…</div> : data && !data.enabled ? <div className="rounded-lg bg-amber/10 p-3 text-xs leading-5 text-amber">AI 配音服务暂不可用，请稍后重试或联系管理员。</div> : null}
          <fieldset><legend className="text-xs font-semibold text-text">生成范围</legend><div className="mt-2 grid grid-cols-3 gap-2">
            <button type="button" onClick={() => setRange("project")} className={`rounded-lg border py-2 text-xs ${range === "project" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>全片</button>
            <button type="button" disabled={!selectedScene} onClick={() => setRange("scene")} className={`rounded-lg border py-2 text-xs disabled:opacity-40 ${range === "scene" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>当前场景</button>
            <button type="button" disabled={!shotRange} onClick={() => setRange("shot")} className={`rounded-lg border py-2 text-xs disabled:opacity-40 ${range === "shot" ? "border-blue bg-blue-soft text-blue" : "border-line text-muted"}`}>当前镜头</button>
          </div></fieldset>
          <div className="rounded-xl border border-blue/15 bg-blue-soft/50 p-3 text-[11px] leading-5 text-muted"><strong className="block text-xs text-text">状态依据清晰可查</strong>文字、开始时间或结束时间变化时，旧版本会保留并标出具体原因；仍可试听，但更新后才会进入新母带。</div>
          <label className="block text-xs font-medium text-muted">表达模式<Select value={model} onChange={(event) => setModel(event.target.value)} wrapperClassName="mt-1.5">{data?.models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select><span className="mt-1 block text-[10px] leading-4">{selectedModel?.description}</span></label>
          <label className="block text-xs font-medium text-muted">音色<Select value={voice} onChange={(event) => setVoice(event.target.value)} wrapperClassName="mt-1.5">{selectedModel?.voices.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.description}</option>)}</Select></label>
          <label className="block text-xs font-medium text-muted">导演指令<textarea rows={3} value={instruction} onChange={(event) => setInstruction(event.target.value)} className="mt-1.5 w-full resize-y rounded-lg border border-line p-2.5 text-xs leading-5 text-text" /></label>
          {model.startsWith("qwen-audio-") && <label className="block text-xs font-medium text-muted">情绪标签<Select value={emotion} onChange={(event) => setEmotion(event.target.value)} wrapperClassName="mt-1.5"><option value="">自动 / 无标签</option><option value="serious">严肃</option><option value="excited">兴奋</option><option value="empathetic">共情</option><option value="whispers">耳语</option><option value="curious">好奇</option><option value="sad">悲伤</option></Select></label>}
          <label className="flex items-start gap-2 rounded-lg border border-line p-3 text-[11px] leading-5 text-muted"><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} className="mt-1" /><span><strong className="block text-text">全部重新生成</strong>关闭时只生成缺失或需要更新的台词；开启后已有台词也会重新生成，并重新消耗 V-Credits。</span></label>
          <div className={`rounded-xl border p-3 text-[11px] leading-5 ${estimate && !estimate.sufficient ? "border-red/25 bg-red/5 text-red" : "border-line bg-canvas text-muted"}`}><div className="flex justify-between gap-3"><strong className="text-xs text-text">本次将处理 {visibleLines.length} 条台词</strong><strong className="text-xs text-text">{estimateLoading ? "计算中…" : estimate ? `${estimate.estimatedCredits.toLocaleString("zh-CN")} V-Credits` : "—"}</strong></div>{estimate && <span className="block">可用 {estimate.availableCredits.toLocaleString("zh-CN")} · 完成后预计剩余 {estimate.remainingAfter.toLocaleString("zh-CN")}</span>}{estimate && !estimate.sufficient && <span className="block font-medium">余额不足，请先充值。</span>}</div>
        </div>
        <div className="min-h-0 overflow-y-auto p-5">
          <div className="flex items-center justify-between"><div><strong className="text-xs text-text">全部台词与历史版本</strong><p className="mt-1 text-[10px] text-muted">最新 {statusCounts.ready ?? 0} · 过期 {statusCounts.stale ?? 0} · 生成中 {statusCounts.generating ?? 0}</p></div><span className="rounded-full bg-canvas px-2.5 py-1 text-[10px] text-muted">{visibleLines.length} 条</span></div>
          <div className="mt-3 space-y-4">{groupedLines.length ? groupedLines.map((group) => <section key={group.sceneId}><h3 className="mb-2 text-[10px] font-semibold text-muted">{sceneNames.get(group.sceneId) ?? "未知场景"}</h3><div className="space-y-2">{group.lines.map((line) => {
            const selected = line.takes.find((take) => take.id === line.selectedTakeId) ?? line.takes.find((take) => take.isSelected) ?? line.takes[0];
            const conflict = line.timingStatus === "conflict";
            return <article key={line.id} className={`rounded-xl border p-3 ${conflict ? "border-red/30 bg-red/5" : "border-line"}`}>
              <div className="flex items-center justify-between gap-3"><span className="text-[10px] text-muted">{time(line.startMs)}–{time(line.endMs)} · 朗读预算 {(line.speechBudgetMs / 1000).toFixed(1)}s</span><span title={line.status === "stale" ? staleCopy(line) : undefined} className={`rounded px-1.5 py-0.5 text-[9px] ${conflict ? "bg-red/10 text-red" : line.status === "stale" ? "bg-amber/10 text-amber" : line.status === "ready" ? "bg-teal/10 text-teal" : "bg-canvas text-muted"}`}>{conflict ? `超时 ${(line.overflowMs / 1000).toFixed(1)}s` : line.status === "stale" ? staleCopy(line) : line.status === "ready" ? "已生成" : line.status === "draft" ? "待生成" : line.status}</span></div>
              <p className="mt-2 text-xs leading-5 text-text">{line.text}</p>
              {selected?.audioUrl && <audio controls preload="none" src={selected.audioUrl} className="mt-2 h-7 w-full" />}
              <div className="mt-2 flex items-center justify-between"><span className="text-[9px] text-muted">当前版本{selected ? ` · ${(selected.durationMs / 1000).toFixed(1)}s` : "尚未生成"}</span><button type="button" disabled={pending || !data?.enabled} onClick={() => void generateSingleLine(line)} className="rounded-md bg-blue-soft px-2 py-1 text-[10px] font-semibold text-blue disabled:opacity-40">重生成本句</button></div>
              {line.takes.length > 1 && <details className="mt-2 rounded-lg bg-canvas px-2.5 py-2"><summary className="cursor-pointer text-[10px] font-medium text-muted">查看全部 {line.takes.length} 个语音版本</summary><div className="mt-2 space-y-2">{line.takes.map((take, index) => <div key={take.id} className="rounded-lg border border-line bg-white p-2"><div className="flex items-center justify-between text-[9px] text-muted"><span>版本 {line.takes.length - index}{take.id === selected?.id ? " · 当前使用" : ""}</span><span>{(take.durationMs / 1000).toFixed(1)}s</span></div>{take.audioUrl && <audio controls preload="none" src={take.audioUrl} className="mt-1.5 h-7 w-full" />}</div>)}</div></details>}
            </article>;
          })}</div></section>) : <div className="rounded-xl border border-dashed border-line p-8 text-center text-xs text-muted">当前范围没有旁白台词。字幕台词将在保存后显示，可逐条生成和试听。</div>}</div>
        </div>
      </div>
      <footer className="flex items-center justify-between border-t border-line bg-canvas/60 px-5 py-4"><span className="text-[10px] text-muted">只对成功生成的任务实际扣除 V-Credits</span><div className="flex gap-2"><button type="button" onClick={onClose} disabled={pending} className="rounded-lg border border-line bg-white px-4 py-2 text-xs text-text">取消</button><button type="button" disabled={pending || estimateLoading || !data?.enabled || !visibleLines.length || !estimate?.sufficient} onClick={generateVisible} className="flex items-center gap-1.5 rounded-lg bg-blue px-4 py-2 text-xs font-semibold text-white disabled:opacity-45">{pending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}{pending ? "正在创建任务…" : force ? "全部重新生成" : "生成缺失/需更新配音"}</button></div></footer>
    </section>
  </div>;
}
