// ──────────────────────────────────────────────
// OpenVMA - AI 生成脚本弹窗
// 三步：brief(需求设置) → generating(后端生成中) → preview(结果预览)
// ──────────────────────────────────────────────

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  Clock,
  Loader2,
  MessageSquareQuote,
  Sparkles,
  WandSparkles,
  X,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useScriptStore } from "@/stores/scriptStore";
import { useProjectStore } from "@/stores/projectStore";
import { generateScript } from "@/api/generate";
import * as projectApi from "@/api/projects";
import type { ScriptUnit } from "@/types/models";

type Step = "brief" | "generating" | "preview";
type Tone = "专业克制" | "科技感" | "故事化";
type Duration = 30 | 60 | 90;

const tones: Tone[] = ["专业克制", "科技感", "故事化"];
const durations: Duration[] = [30, 60, 90];

const briefSamples = [
  "为智能机器人发布会生成 60 秒精华版脚本，突出机器人亮相、核心能力与人机协作愿景。",
  "围绕年度客户故事，生成 90 秒品牌版脚本，体现客户挑战、使用过程与业务成果。",
  "智能工厂参观日 45 秒快剪，按参观动线串联产线、机械臂和嘉宾互动。",
];

export function AIScriptModal() {
  const queryClient = useQueryClient();
  const { aiScriptOpen, aiScriptInitialTitle, closeAIScript, notify } = useUIStore();
  const createScript = useScriptStore((s) => s.createScript);
  const storedProjects = useProjectStore((state) => state.projects);
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectApi.list(),
    enabled: aiScriptOpen,
    retry: false,
  });
  const projects = projectsQuery.data?.items ?? storedProjects;

  const [step, setStep] = useState<Step>("brief");
  const [projectId, setProjectId] = useState("");
  const [brief, setBrief] = useState("");
  const [duration, setDuration] = useState<Duration>(60);
  const [tone, setTone] = useState<Tone>("科技感");
  const [referenceDialogue, setReferenceDialogue] = useState(true);
  const [result, setResult] = useState<{
    title: string;
    summary: string;
    units: ScriptUnit[];
  } | null>(null);

  // 打开时重置
  useEffect(() => {
    if (aiScriptOpen) {
      setStep("brief");
      setProjectId("");
      setBrief(aiScriptInitialTitle ? `围绕"${aiScriptInitialTitle}"生成一版可编辑脚本。` : "");
      setResult(null);
    }
  }, [aiScriptOpen, aiScriptInitialTitle]);

  useEffect(() => {
    if (!aiScriptOpen || projectId || projects.length === 0) return;
    const preferredId = currentProjectId && projects.some((project) => project.id === currentProjectId)
      ? currentProjectId
      : projects[0].id;
    setProjectId(preferredId);
  }, [aiScriptOpen, currentProjectId, projectId, projects]);

  if (!aiScriptOpen) return null;

  async function generate() {
    if (!brief.trim()) {
      notify("请先描述你的创作需求", "error");
      return;
    }
    if (!projectId) {
      notify("请先选择一个所属项目", "error");
      return;
    }
    setStep("generating");
    try {
      const res = await generateScript({
        brief,
        duration,
        tone,
        referenceDialogue,
        projectId,
      });
      // 将后端返回的原始单元映射为前端 ScriptUnit 类型
      const units: ScriptUnit[] = (res.units || []).map((u, idx) => ({
        id: `ai-unit-${idx + 1}`,
        index: idx + 1,
        outline: u.outline || "",
        text: u.text || "",
        intent: u.intent || "",
        duration: u.duration || 0,
        status: "待编辑",
        selectedClipId: null,
        notes: "",
        candidates: [],
        shots: [],
      }));
      setResult({
        title: res.title || aiScriptInitialTitle || "AI 生成脚本",
        summary: res.summary || "",
        units,
      });
      setStep("preview");
    } catch (err) {
      const message = err instanceof Error ? err.message : "AI 生成失败，请稍后重试";
      notify(message, "error");
      setStep("brief");
    }
  }

  async function handleApply() {
    if (!result) return;
    const targetProjectId = projectId;
    if (!targetProjectId) {
      notify("没有可用的项目，请先创建一个项目", "error");
      return;
    }
    try {
      await createScript({
        projectId: targetProjectId,
        title: result.title,
        sourceType: "ai",
        units: result.units,
        summary: result.summary,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scripts"] }),
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
      ]);
      notify("AI 脚本已生成并进入在线编辑器");
      closeAIScript();
    } catch (error) {
      notify(error instanceof Error ? error.message : "脚本保存失败", "error");
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        className="absolute inset-0 cursor-default bg-ink/60 backdrop-blur-sm"
        onClick={closeAIScript}
        aria-label="关闭"
        type="button"
      />

      <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-2xl bg-surface shadow-soft">
        {/* 头部 */}
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal text-white">
              <WandSparkles size={17} />
            </span>
            <div>
              <h2 className="text-base font-semibold text-text">AI 生成脚本</h2>
              <p className="text-xs text-muted">根据创作目标自动生成可编辑的分镜脚本</p>
            </div>
          </div>
          <button
            onClick={closeAIScript}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        {/* 步骤条 */}
        <div className="flex items-center gap-1 border-b border-line bg-canvas/40 px-6 py-2.5">
          {[
            { id: "brief", label: "需求设置" },
            { id: "generating", label: "生成中" },
            { id: "preview", label: "结果预览" },
          ].map((s, idx) => {
            const active =
              (s.id === step) ||
              (step === "generating" && s.id === "generating") ||
              (step === "preview" && (s.id === "brief" || s.id === "preview"));
            return (
              <div key={s.id} className="flex items-center">
                <span
                  className={`flex items-center gap-1.5 text-xs font-medium ${
                    active ? "text-blue" : "text-muted"
                  }`}
                >
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                      active ? "bg-blue text-white" : "bg-line text-muted"
                    }`}
                  >
                    {idx + 1}
                  </span>
                  {s.label}
                </span>
                {idx < 2 && <span className="mx-2 text-line">—</span>}
              </div>
            );
          })}
        </div>

        <div className="max-h-[70vh] overflow-y-auto p-6">
          {step === "brief" && (
            <div className="space-y-5">
              {/* 所属项目 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text">所属项目</label>
                <select
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                  disabled={projectsQuery.isLoading && projects.length === 0}
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                >
                  {projects.length === 0 && (
                    <option value="">
                      {projectsQuery.isLoading ? "正在加载项目…" : "暂无可用项目"}
                    </option>
                  )}
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>{project.name}</option>
                  ))}
                </select>
                {projectsQuery.isError && projects.length === 0 && (
                  <div className="mt-2 flex items-center justify-between gap-3 rounded-lg bg-red/5 px-3 py-2 text-xs text-red">
                    <span>{projectsQuery.error instanceof Error ? projectsQuery.error.message : "项目列表加载失败"}</span>
                    <button
                      type="button"
                      onClick={() => void projectsQuery.refetch()}
                      className="shrink-0 font-medium underline"
                    >
                      重试
                    </button>
                  </div>
                )}
              </div>

              {/* 需求描述 */}
              <div>
                <label className="mb-2 block text-sm font-medium text-text">创作需求</label>
                <textarea
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  placeholder="描述你想生成的视频脚本：主题、目标受众、核心信息、节奏风格…"
                  rows={4}
                  className="w-full resize-none rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {briefSamples.map((sample, idx) => (
                    <button
                      key={idx}
                      onClick={() => setBrief(sample)}
                      className="rounded-full border border-line bg-canvas/50 px-3 py-1 text-xs text-muted transition hover:border-blue/50 hover:text-blue"
                      type="button"
                    >
                      示例 {idx + 1}
                    </button>
                  ))}
                </div>
              </div>

              {/* 目标时长 */}
              <div>
                <label className="mb-2 block text-sm font-medium text-text">目标时长</label>
                <div className="flex gap-2">
                  {durations.map((d) => (
                    <button
                      key={d}
                      onClick={() => setDuration(d)}
                      className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-2.5 text-sm font-medium transition ${
                        duration === d
                          ? "border-blue bg-blue-soft text-blue"
                          : "border-line text-muted hover:border-blue/40 hover:text-text"
                      }`}
                      type="button"
                    >
                      <Clock size={14} />{d} 秒
                    </button>
                  ))}
                </div>
              </div>

              {/* 表达语气 */}
              <div>
                <label className="mb-2 block text-sm font-medium text-text">表达语气</label>
                <div className="flex gap-2">
                  {tones.map((t) => (
                    <button
                      key={t}
                      onClick={() => setTone(t)}
                      className={`flex-1 rounded-lg border py-2.5 text-sm font-medium transition ${
                        tone === t
                          ? "border-blue bg-blue-soft text-blue"
                          : "border-line text-muted hover:border-blue/40 hover:text-text"
                      }`}
                      type="button"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              {/* 参考素材对白 */}
              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-surface px-3.5 py-3">
                <span className="flex items-center gap-2.5">
                  <MessageSquareQuote size={16} className="text-muted" />
                  <span>
                    <strong className="block text-sm text-text">参考素材对白</strong>
                    <small className="text-xs text-muted">读取所选项目已处理素材中的真实对白、OCR 与场景摘要</small>
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => setReferenceDialogue((v) => !v)}
                  className={`relative h-6 w-11 rounded-full transition ${
                    referenceDialogue ? "bg-blue" : "bg-line"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
                      referenceDialogue ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
              </label>
            </div>
          )}

          {step === "generating" && (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="relative">
                <div className="absolute inset-0 animate-ping rounded-full bg-blue/20" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue to-teal">
                  <Sparkles size={28} className="text-white" />
                </div>
              </div>
              <p className="mt-6 text-sm font-medium text-text">AI 正在生成脚本…</p>
              <p className="mt-1 text-xs text-muted">理解需求 · 生成结构 · 撰写分镜 · 校对时长</p>
              <div className="mt-4 flex items-center gap-1.5 text-xs text-muted">
                <Loader2 size={12} className="animate-spin" />
                约 {duration} 秒视频 · {tone}语气
              </div>
            </div>
          )}

          {step === "preview" && result && (
            <div>
              {/* 摘要 */}
              <div className="mb-4 rounded-xl border border-blue/20 bg-blue-soft/40 p-4">
                <div className="flex items-center gap-2">
                  <Sparkles size={15} className="text-blue" />
                  <strong className="text-sm text-text">{result.title}</strong>
                  <span className="ml-auto rounded-full bg-teal/10 px-2 py-0.5 text-xs text-teal">
                    {result.units.length} 个单元 · 约 {duration} 秒
                  </span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted">{result.summary}</p>
              </div>

              {/* 单元预览 */}
              <ol className="space-y-2.5">
                {result.units.map((unit) => (
                  <li
                    key={unit.id}
                    className="flex items-start gap-3 rounded-lg border border-line bg-surface px-3.5 py-3"
                  >
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue to-teal text-xs font-semibold text-white">
                      {String(unit.index).padStart(2, "0")}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm leading-relaxed text-text">{unit.text}</p>
                      <div className="mt-1.5 flex items-center gap-2">
                        <span className="rounded bg-canvas px-1.5 py-0.5 text-[11px] text-muted">
                          {unit.outline}
                        </span>
                        <span className="text-[11px] text-muted">· {unit.duration}s</span>
                      </div>
                    </div>
                    <Check size={15} className="mt-1 shrink-0 text-teal" />
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* 底部操作 */}
        <footer className="flex items-center justify-between border-t border-line px-6 py-4">
          {step === "brief" && (
            <>
              <button
                onClick={closeAIScript}
                className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:bg-canvas"
                type="button"
              >
                取消
              </button>
              <button
                onClick={generate}
                disabled={!brief.trim() || !projectId || projectsQuery.isLoading}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue to-teal px-5 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
              >
                <WandSparkles size={15} />开始生成
              </button>
            </>
          )}
          {step === "generating" && (
            <span className="ml-auto text-xs text-muted">请稍候，正在生成…</span>
          )}
          {step === "preview" && result && (
            <>
              <button
                onClick={() => setStep("brief")}
                className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:bg-canvas"
                type="button"
              >
                重新生成
              </button>
              <button
                onClick={handleApply}
                className="flex items-center gap-1.5 rounded-lg bg-blue px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-2"
                type="button"
              >
                <Check size={15} />应用到脚本编辑器<ArrowRight size={14} />
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}

export default AIScriptModal;
