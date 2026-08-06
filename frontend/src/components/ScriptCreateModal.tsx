// ──────────────────────────────────────────────
// OpenVMA - 新建脚本弹窗
// 两种模式：paste(粘贴文本) / upload(表格上传)
// paste: 输入标题 + 粘贴文本，支持"填入示例"
// upload: 支持 XLSX/CSV/TSV 文件选择 → 解析预览 → 创建
// ──────────────────────────────────────────────

import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import readXlsxFile from "read-excel-file";
import {
  ArrowRight,
  Check,
  FileSpreadsheet,
  FileType2,
  Loader2,
  Plus,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { useScriptStore } from "@/stores/scriptStore";
import * as projectApi from "@/api/projects";
import type { ScriptUnit } from "@/types/models";

type Mode = "paste" | "upload";
type Step = "input" | "parsing" | "preview";

const sampleText = `01 展馆灯光依次亮起，一场关于未来协作的发布正式开始。
02 机器人穿过人群，第一次走到所有人面前。
03 它不只是被展示的产品，更是即将加入团队的新成员。
04 从重复工作到复杂协作，人的创造力因此被重新释放。
05 未来已经入场，而我们正在一起定义它。`;

interface ParsedUnit {
  index: number;
  text: string;
  outline: string;
  intent: string;
  duration: number;
}

function parseTextToUnits(text: string): ParsedUnit[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  return lines.map((line, idx) => {
    const match = line.match(/^(\d+)[\s.、:：]+(.+)$/);
    const index = match ? parseInt(match[1], 10) : idx + 1;
    const content = match ? match[2] : line;
    return {
      index,
      text: content,
      outline: content.length > 24 ? content.slice(0, 22) + "…" : content,
      intent: "",
      duration: 8,
    };
  });
}

export function ScriptCreateModal() {
  const queryClient = useQueryClient();
  const { scriptCreateOpen, closeScriptCreate, openAIScript, notify } = useUIStore();
  const storedProjects = useProjectStore((state) => state.projects);
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const createScript = useScriptStore((s) => s.createScript);

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectApi.list(),
    enabled: scriptCreateOpen,
    retry: false,
  });
  const projects = projectsQuery.data?.items ?? storedProjects;

  const [mode, setMode] = useState<Mode>("paste");
  const [step, setStep] = useState<Step>("input");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [parsedUnits, setParsedUnits] = useState<ParsedUnit[]>([]);

  // 打开时重置
  useEffect(() => {
    if (scriptCreateOpen) {
      setMode("paste");
      setStep("input");
      setTitle("");
      setText("");
      setFileName("");
      setParsedUnits([]);
      setProjectId("");
    }
  }, [scriptCreateOpen]);

  useEffect(() => {
    if (!scriptCreateOpen || projectId || projects.length === 0) return;
    const preferredId = currentProjectId && projects.some((project) => project.id === currentProjectId)
      ? currentProjectId
      : projects[0].id;
    setProjectId(preferredId);
  }, [currentProjectId, projectId, projects, scriptCreateOpen]);

  if (!scriptCreateOpen) return null;

  function fillSample() {
    setTitle("发布会 60 秒精华版");
    setText(sampleText);
    notify("已填入示例脚本");
  }

  async function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setStep("parsing");
    try {
      let rows: Array<Array<string | number | null>>;
      if (/\.xlsx$/i.test(file.name)) {
        rows = (await readXlsxFile(file)) as Array<Array<string | number | null>>;
      } else {
        const delimiter = /\.tsv$/i.test(file.name) ? "\t" : ",";
        rows = (await file.text())
          .split(/\r?\n/)
          .filter(Boolean)
          .map((line) => line.split(delimiter).map((cell) => cell.trim()));
      }
      if (rows.length === 0) throw new Error("表格中没有可识别的内容");

      const headers = rows[0].map((cell) => String(cell ?? "").trim().toLowerCase());
      const textIndex = headers.findIndex((header) => ["台词", "文案", "旁白", "text", "content"].includes(header));
      const indexIndex = headers.findIndex((header) => ["序号", "编号", "index", "no"].includes(header));
      const intentIndex = headers.findIndex((header) => ["分镜意图", "画面意图", "镜头意图", "intent", "visual_intent"].includes(header));
      const durationIndex = headers.findIndex((header) => ["时长", "建议时长", "duration", "seconds"].includes(header));
      const dataRows = textIndex >= 0 ? rows.slice(1) : rows;
      const units = dataRows
        .map((row, rowIndex) => {
          const rawText = row[textIndex >= 0 ? textIndex : Math.min(1, row.length - 1)] ?? row[0];
          const content = String(rawText ?? "").trim();
          const rawIndex = indexIndex >= 0 ? Number(row[indexIndex]) : rowIndex + 1;
          const intent = intentIndex >= 0 ? String(row[intentIndex] ?? "").trim() : "";
          const rawDuration = durationIndex >= 0
            ? Number(String(row[durationIndex] ?? "").replace(/[^\d.]/g, ""))
            : 8;
          return {
            index: Number.isFinite(rawIndex) && rawIndex > 0 ? rawIndex : rowIndex + 1,
            text: content,
            outline: intent || (content.length > 24 ? `${content.slice(0, 22)}…` : content),
            intent,
            duration: Number.isFinite(rawDuration) && rawDuration > 0 && rawDuration <= 600
              ? rawDuration
              : 8,
          };
        })
        .filter((unit) => unit.text);
      if (units.length === 0) throw new Error("未找到“台词/文案”内容")
      setParsedUnits(units);
      setTitle((current) => current || file.name.replace(/\.(xlsx|csv|tsv)$/i, "") || "新脚本");
      setStep("preview");
    } catch (error) {
      notify(error instanceof Error ? error.message : "表格解析失败", "error");
      setStep("input");
    }
    e.target.value = "";
  }

  function startParsing(sourceName: string) {
    setStep("parsing");
    const units = parseTextToUnits(text);
    setParsedUnits(units);
    if (!title) {
      setTitle(sourceName.replace(/\.(xlsx|csv|tsv)$/i, "") || "新脚本");
    }
    setStep("preview");
  }

  function handleParse() {
    if (mode === "paste" && !text.trim()) {
      notify("请先粘贴脚本内容", "error");
      return;
    }
    if (mode === "upload" && !fileName && !text.trim()) {
      notify("请先选择表格文件", "error");
      return;
    }
    startParsing(mode === "upload" ? fileName || "表格文件" : "粘贴文本");
  }

  async function handleCreate() {
    const targetProjectId = projectId || projects[0]?.id;
    if (!targetProjectId) {
      notify("请先创建并选择一个项目", "error");
      return;
    }
    const units: ScriptUnit[] = parsedUnits.map((u) => ({
      id: `unit-${Date.now()}-${u.index}`,
      index: u.index,
      outline: u.outline,
      text: u.text,
      intent: u.intent,
      status: "待编辑",
      selectedClipId: null,
      duration: u.duration,
      notes: "",
      candidates: [],
      shots: [],
    }));

    try {
      await createScript({
        projectId: targetProjectId,
        title: title.trim() || "新脚本",
        sourceType: mode === "paste" ? "paste" : "spreadsheet",
        units,
        summary:
          mode === "paste"
            ? `从粘贴内容识别生成 ${units.length} 句在线脚本，可继续编辑台词和分镜。`
            : `从 ${fileName} 识别生成 ${units.length} 句在线脚本。`,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["scripts"] }),
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
      ]);
      notify(`脚本"${title || "新脚本"}"已创建`);
      closeScriptCreate();
    } catch (error) {
      notify(error instanceof Error ? error.message : "脚本创建失败", "error");
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <button
        className="absolute inset-0 cursor-default bg-ink/60 backdrop-blur-sm"
        onClick={closeScriptCreate}
        aria-label="关闭"
        type="button"
      />

      <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-2xl bg-surface shadow-soft">
        {/* 头部 */}
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-soft text-blue">
              <Plus size={17} />
            </span>
            <h2 className="text-base font-semibold text-text">新建脚本</h2>
          </div>
          <button
            onClick={closeScriptCreate}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        {/* 步骤指示 */}
        {step !== "input" && (
          <div className="flex items-center gap-2 border-b border-line bg-canvas/40 px-6 py-2.5 text-xs">
            <span className={step === "parsing" ? "font-medium text-blue" : "text-teal"}>
              {step === "parsing" ? "解析中…" : "解析完成"}
            </span>
            <span className="text-muted">·</span>
            <span className="text-muted">
              {mode === "paste" ? "粘贴文本" : fileName || "表格文件"}
            </span>
          </div>
        )}

        <div className="max-h-[70vh] overflow-y-auto p-6">
          {step === "input" && (
            <>
              {/* 模式切换 */}
              <div className="mb-5 flex gap-1 rounded-lg bg-canvas p-1">
                <button
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition ${
                    mode === "paste" ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
                  }`}
                  onClick={() => setMode("paste")}
                  type="button"
                >
                  <FileType2 size={15} />粘贴文本
                </button>
                <button
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-medium transition ${
                    mode === "upload" ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
                  }`}
                  onClick={() => setMode("upload")}
                  type="button"
                >
                  <FileSpreadsheet size={15} />上传表格
                </button>
              </div>

              {/* 项目选择 */}
              <div className="mb-4">
                <label className="mb-1.5 block text-sm font-medium text-text">所属项目</label>
                <select
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  disabled={projectsQuery.isLoading && projects.length === 0}
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                >
                  {projects.length === 0 && (
                    <option value="">
                      {projectsQuery.isLoading ? "正在加载项目…" : "暂无可用项目"}
                    </option>
                  )}
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                {projectsQuery.isError && projects.length === 0 && (
                  <div className="mt-2 flex items-center justify-between gap-3 rounded-lg bg-red/5 px-3 py-2 text-xs text-red">
                    <span>
                      {projectsQuery.error instanceof Error
                        ? projectsQuery.error.message
                        : "项目列表加载失败"}
                    </span>
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

              {/* 标题 */}
              <div className="mb-4">
                <label className="mb-1.5 block text-sm font-medium text-text">脚本标题</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="给这版脚本起个名字"
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                />
              </div>

              {mode === "paste" ? (
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label className="text-sm font-medium text-text">脚本内容</label>
                    <button
                      onClick={fillSample}
                      className="flex items-center gap-1 text-xs text-blue hover:underline"
                      type="button"
                    >
                      <Sparkles size={12} />填入示例
                    </button>
                  </div>
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={"每行一句台词，可使用「序号 + 内容」格式：\n01 展馆灯光依次亮起…\n02 机器人穿过人群…"}
                    rows={8}
                    className="w-full resize-none rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-text placeholder:text-muted transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                  />
                  <p className="mt-1.5 text-xs text-muted">
                    每行将识别为一个脚本单元，支持「序号 + 内容」或纯文本
                  </p>
                </div>
              ) : (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-text">上传表格文件</label>
                  <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line bg-canvas/40 px-6 py-10 text-center transition hover:border-blue/60 hover:bg-canvas/70">
                    <span className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-soft text-blue">
                      <Upload size={22} />
                    </span>
                    <p className="mt-3 text-sm font-medium text-text">
                      {fileName || "选择 XLSX / CSV / TSV 文件"}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      支持「序号」「台词」「分镜意图」「时长」列
                    </p>
                    <input
                      type="file"
                      accept=".xlsx,.csv,.tsv"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                  </label>
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-blue-soft/50 px-3 py-2 text-xs text-blue">
                    <FileSpreadsheet size={14} />
                    <span>未准备好表格？</span>
                    <button
                      onClick={fillSample}
                      className="font-medium underline"
                      type="button"
                    >
                      使用示例内容预览解析效果
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {step === "parsing" && (
            <div className="flex flex-col items-center justify-center py-16">
              <Loader2 size={36} className="animate-spin text-blue" />
              <p className="mt-4 text-sm font-medium text-text">正在解析脚本结构…</p>
              <p className="mt-1 text-xs text-muted">解析序号、台词、分镜意图与建议时长</p>
            </div>
          )}

          {step === "preview" && (
            <>
              <div className="mb-4">
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="text-sm font-medium text-text">脚本标题</label>
                  <span className="text-xs text-teal">
                    <Check size={12} className="inline" /> 解析到 {parsedUnits.length} 个单元
                  </span>
                </div>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm text-text transition focus:border-blue focus:ring-2 focus:ring-blue/10"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-text">解析预览</label>
                <ol className="space-y-2">
                  {parsedUnits.map((unit) => (
                    <li
                      key={unit.index}
                      className="flex items-start gap-3 rounded-lg border border-line bg-surface px-3.5 py-2.5"
                    >
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-blue-soft text-xs font-semibold text-blue">
                        {String(unit.index).padStart(2, "0")}
                      </span>
                      <div className="flex-1">
                        <p className="text-sm text-text">{unit.text}</p>
                        <p className="mt-0.5 text-xs text-muted">
                          {unit.intent || "未提供分镜意图"} · 建议 {unit.duration} 秒
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </>
          )}
        </div>

        {/* 底部操作 */}
        <footer className="flex items-center justify-between border-t border-line px-6 py-4">
          <button
            onClick={() => {
              closeScriptCreate();
              openAIScript(title);
            }}
            className="flex items-center gap-1.5 text-sm text-blue transition hover:underline"
            type="button"
          >
            <Sparkles size={15} />改用 AI 生成脚本
          </button>
          <div className="flex items-center gap-2">
            {step === "preview" && (
              <button
                onClick={() => setStep("input")}
                className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:bg-canvas"
                type="button"
              >
                返回修改
              </button>
            )}
            {step === "input" && (
              <button
                onClick={closeScriptCreate}
                className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:bg-canvas"
                type="button"
              >
                取消
              </button>
            )}
            {step === "input" && (
              <button
                onClick={handleParse}
                disabled={mode === "upload" && !fileName && !text.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-blue px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-2 disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
              >
                解析并预览<ArrowRight size={15} />
              </button>
            )}
            {step === "preview" && (
              <button
                onClick={handleCreate}
                className="flex items-center gap-1.5 rounded-lg bg-blue px-5 py-2 text-sm font-semibold text-white transition hover:bg-blue-2"
                type="button"
              >
                <Check size={15} />创建脚本
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

export default ScriptCreateModal;
