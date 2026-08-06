// ──────────────────────────────────────────────
// OpenVMA - 上传素材抽屉
// 从右侧滑出，支持拖拽上传，显示进度，完成后提示跳转素材库
// ──────────────────────────────────────────────

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { useNavigate } from "@/router";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CloudUpload,
  FileVideo,
  Loader2,
  Music,
  X,
} from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { useProjectStore } from "@/stores/projectStore";
import { getAccessToken } from "@/api/client";
import * as jobApi from "@/api/jobs";
import { variantGradient } from "@/data/uiConfig";

interface UploadItem {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: "uploading" | "processing" | "done" | "error";
  jobId?: string;
  error?: string;
}

const acceptedTypes = ".mp4,.mov,.m4v,.avi,.mkv,.webm,.mp3,.wav,.m4a,.aac,.flac,.ogg,.oga,.opus";
const maxUploadBytes = 5 * 1024 * 1024 * 1024;
const acceptedExtensions = new Set([
  "mp4", "mov", "m4v", "avi", "mkv", "webm",
  "mp3", "wav", "m4a", "aac", "flac", "ogg", "oga", "opus",
]);
const audioExtensions = new Set(["mp3", "wav", "m4a", "aac", "flac", "ogg", "oga", "opus"]);

function isAudioFilename(filename: string): boolean {
  return audioExtensions.has(filename.split(".").pop()?.toLowerCase() ?? "");
}

function validateFile(file: File): string | undefined {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!acceptedExtensions.has(extension)) return "不支持该文件扩展名";
  if (file.size <= 0) return "不能上传空文件";
  if (file.size > maxUploadBytes) return "单个文件不能超过 5GB";
  return undefined;
}

function parseUploadError(responseText: string, fallback: string): string {
  try {
    const parsed = JSON.parse(responseText) as { detail?: string };
    return parsed.detail || fallback;
  } catch {
    return responseText || fallback;
  }
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * 使用 XMLHttpRequest 上传文件，支持真实上传进度回调。
 */
function uploadFile(
  file: File,
  projectId: string,
  onProgress: (pct: number) => void,
): Promise<{ assetId: string; name: string; status: string; jobId: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const raw = JSON.parse(xhr.responseText);
          resolve({
            assetId: raw.asset_id,
            name: raw.name,
            status: raw.status,
            jobId: raw.job_id,
          });
        } catch {
          reject(new Error("响应解析失败"));
        }
      } else {
        reject(new Error(parseUploadError(xhr.responseText, "上传失败")));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("网络错误")));
    xhr.addEventListener("abort", () => reject(new Error("上传已取消")));

    xhr.open("POST", `/api/assets/upload?project_id=${encodeURIComponent(projectId)}`);
    const token = getAccessToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(formData);
  });
}

export function UploadDrawer() {
  const { uploadDrawerOpen, closeUploadDrawer, notify } = useUIStore();
  const { currentProjectId } = useProjectStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [noProject, setNoProject] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimersRef = useRef<Record<string, number>>({});
  const pollFailuresRef = useRef<Record<string, number>>({});

  useEffect(() => () => {
    Object.values(pollTimersRef.current).forEach((timer) => window.clearTimeout(timer));
  }, []);

  const refreshBusinessData = useCallback(() => {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["assets"] }),
      queryClient.invalidateQueries({ queryKey: ["projects"] }),
      queryClient.invalidateQueries({ queryKey: ["jobs"] }),
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    ]);
  }, [queryClient]);

  const pollJob = useCallback(async function poll(itemId: string, jobId: string): Promise<void> {
    try {
      const job = await jobApi.get(jobId);
      pollFailuresRef.current[itemId] = 0;
      if (job.status === "SUCCEEDED") {
        setItems((prev) =>
          prev.map((item) =>
            item.id === itemId ? { ...item, progress: 100, status: "done", error: undefined } : item,
          ),
        );
        refreshBusinessData();
        return;
      }
      if (job.status === "FAILED") {
        setItems((prev) =>
          prev.map((item) =>
            item.id === itemId
              ? {
                  ...item,
                  progress: job.progress,
                  status: "error",
                  error: job.resultDetail || job.detail || "素材处理失败",
                }
              : item,
          ),
        );
        refreshBusinessData();
        return;
      }
      setItems((prev) =>
        prev.map((item) =>
          item.id === itemId
            ? { ...item, progress: job.progress, status: "processing" }
            : item,
        ),
      );
    } catch (error) {
      const failures = (pollFailuresRef.current[itemId] ?? 0) + 1;
      pollFailuresRef.current[itemId] = failures;
      if (failures >= 3) {
        setItems((prev) =>
          prev.map((item) =>
            item.id === itemId
              ? {
                  ...item,
                  status: "error",
                  error: error instanceof Error ? `任务状态查询失败：${error.message}` : "任务状态查询失败",
                }
              : item,
          ),
        );
        return;
      }
    }
    pollTimersRef.current[itemId] = window.setTimeout(() => void poll(itemId, jobId), 2_000);
  }, [refreshBusinessData]);

  // ESC 关闭
  useEffect(() => {
    if (!uploadDrawerOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeUploadDrawer();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [uploadDrawerOpen, closeUploadDrawer]);

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (!fileArray.length) return;

      // 检查是否已选择项目
      if (!currentProjectId) {
        setNoProject(true);
        notify("请先选择一个项目再上传素材", "error");
        return;
      }
      setNoProject(false);

      const newItems: UploadItem[] = fileArray.map((file, index) => {
        const validationError = validateFile(file);
        return {
          id: `upload-${Date.now()}-${index}`,
          name: file.name || `素材_${index + 1}.mp4`,
          size: file.size || 0,
          progress: 0,
          status: validationError ? "error" : "uploading",
          error: validationError,
        };
      });

      setItems((prev) => [...newItems, ...prev]);

      // 逐个上传（真实上传进度）
      newItems.forEach((item, index) => {
        if (item.status === "error") return;
        const file = fileArray[index];
        uploadFile(file, currentProjectId, (pct) => {
          setItems((prev) =>
            prev.map((it) =>
              it.id === item.id
                ? { ...it, progress: pct, status: pct >= 100 ? "processing" : "uploading" }
                : it,
            ),
          );
        })
          .then((response) => {
            // 上传完成，进入处理中
            setItems((prev) =>
              prev.map((it) =>
                it.id === item.id
                  ? { ...it, progress: 0, status: "processing", jobId: response.jobId }
                  : it,
              ),
            );
            void pollJob(item.id, response.jobId);
          })
          .catch((err) => {
            setItems((prev) =>
              prev.map((it) =>
                it.id === item.id
                  ? { ...it, status: "error", error: err instanceof Error ? err.message : "上传失败" }
                  : it,
              ),
            );
          });
      });
    },
    [currentProjectId, notify, pollJob],
  );

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) {
      addFiles(e.dataTransfer.files);
    }
  }

  function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) {
      addFiles(e.target.files);
      e.target.value = "";
    }
  }

  const allDone = items.length > 0 && items.every((i) => i.status === "done" || i.status === "error");
  const uploadingCount = items.filter((i) => i.status === "uploading" || i.status === "processing").length;

  function handleDone() {
    closeUploadDrawer();
    const successCount = items.filter((i) => i.status === "done").length;
    const failureCount = items.filter((i) => i.status === "error").length;
    notify(
      failureCount
        ? `素材处理完成 ${successCount} 个，失败 ${failureCount} 个`
        : `已完成 ${successCount} 个素材的上传与处理`,
      failureCount ? "error" : "success",
    );
    navigate("/workspace/library");
    Object.values(pollTimersRef.current).forEach((timer) => window.clearTimeout(timer));
    pollTimersRef.current = {};
    pollFailuresRef.current = {};
    // 清空列表
    setItems([]);
  }

  return (
    <>
      {/* 遮罩 */}
      <div
        className={`fixed inset-0 z-[70] bg-ink/40 backdrop-blur-sm transition-opacity ${
          uploadDrawerOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={closeUploadDrawer}
      />

      {/* 抽屉 */}
      <aside
        className={`fixed right-0 top-0 z-[71] flex h-screen w-full max-w-md flex-col bg-surface shadow-soft transition-transform duration-300 ${
          uploadDrawerOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* 头部 */}
        <header className="flex h-16 items-center justify-between border-b border-line px-5">
          <div>
            <h2 className="text-base font-semibold text-text">上传素材</h2>
            <p className="text-xs text-muted">支持常见视频及 MP3 / WAV / M4A / AAC / FLAC / OGG 音频</p>
          </div>
          <button
            onClick={closeUploadDrawer}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-canvas"
            aria-label="关闭"
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        {/* 未选择项目提示 */}
        {noProject && (
          <div className="mx-5 mt-4 flex items-center gap-2 rounded-lg border border-amber/30 bg-amber/10 px-3.5 py-2.5 text-sm text-amber">
            <AlertCircle size={16} className="shrink-0" />
            <span>请先在项目中心选择一个项目，再上传素材。</span>
          </div>
        )}

        {/* 拖拽区 */}
        <div className="p-5">
          <div
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
              dragOver
                ? "border-blue bg-blue-soft"
                : "border-line bg-canvas/40 hover:border-blue/60 hover:bg-canvas/70"
            }`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-soft text-blue">
              <CloudUpload size={26} />
            </span>
            <p className="mt-4 text-sm font-medium text-text">
              拖拽视频或音频文件到这里，或<span className="text-blue">点击选择</span>
            </p>
            <p className="mt-1 text-xs text-muted">单个文件最大 5GB，可同时选择多个文件</p>
            <input
              ref={fileInputRef}
              type="file"
              accept={acceptedTypes}
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />
          </div>
        </div>

        {/* 上传列表 */}
        <div className="flex-1 overflow-y-auto px-5 pb-5">
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <FileVideo size={32} className="text-line" />
              <p className="mt-3 text-sm text-muted">还没有上传的素材</p>
              <p className="text-xs text-muted">视频会进行理解与切片，音频会生成兼容试听文件</p>
            </div>
          ) : (
            <>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium text-text">
                  上传列表 ({items.length})
                </span>
                {uploadingCount > 0 && (
                  <span className="flex items-center gap-1 text-xs text-muted">
                    <Loader2 size={12} className="animate-spin" />
                    {uploadingCount} 个处理中
                  </span>
                )}
              </div>
              <ul className="space-y-2.5">
                {items.map((item) => {
                  const variantKeys = Object.keys(variantGradient);
                  const gradient =
                    variantGradient[variantKeys[item.id.length % variantKeys.length]];
                  return (
                    <li
                      key={item.id}
                      className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3"
                    >
                      <span
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${gradient}`}
                      >
                        {isAudioFilename(item.name)
                          ? <Music size={18} className="text-white" />
                          : <FileVideo size={18} className="text-white" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-medium text-text">
                            {item.name}
                          </span>
                          <span className="shrink-0 text-xs text-muted">
                            {formatSize(item.size)}
                          </span>
                        </div>
                        <div className="mt-1.5 flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-canvas">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                item.status === "done"
                                  ? "bg-teal"
                                  : item.status === "error"
                                    ? "bg-rose"
                                    : "bg-gradient-to-r from-blue to-teal"
                              }`}
                              style={{ width: `${item.status === "error" ? 100 : item.progress}%` }}
                            />
                          </div>
                          <span className="shrink-0 text-xs text-muted">
                            {item.status === "done"
                              ? "已完成"
                              : item.status === "error"
                                ? "失败"
                                : item.status === "processing"
                                  ? "处理中"
                                  : `${Math.round(item.progress)}%`}
                          </span>
                        </div>
                        {item.status === "error" && item.error && (
                          <p className="mt-1 truncate text-xs text-rose">{item.error}</p>
                        )}
                      </div>
                      {item.status === "done" && (
                        <CheckCircle2 size={18} className="shrink-0 text-teal" />
                      )}
                      {item.status === "error" && (
                        <AlertCircle size={18} className="shrink-0 text-rose" />
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        {/* 底部操作 */}
        {items.length > 0 && (
          <footer className="border-t border-line p-5">
            {allDone ? (
              <button
                onClick={handleDone}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue py-2.5 text-sm font-semibold text-white transition hover:bg-blue-2"
                type="button"
              >
                <CheckCircle2 size={16} />
                查看处理结果
              </button>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 size={16} className="animate-spin text-blue" />
                正在上传与处理，请稍候…
              </div>
            )}
          </footer>
        )}
      </aside>
    </>
  );
}

export default UploadDrawer;
