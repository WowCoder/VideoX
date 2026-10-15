// ──────────────────────────────────────────────
// VideoX - 视频缩略图组件
// 优先展示后端媒体；缺少媒体时展示明确的中性占位。
// ──────────────────────────────────────────────

import { useState } from "react";
import { Film, Play } from "lucide-react";
import type { ThumbnailVariant } from "@/types/models";

interface VideoThumbProps {
  variant?: ThumbnailVariant;
  className?: string;
  /** 圆角 */
  rounded?: string;
  /** 是否显示播放图标 */
  showPlay?: boolean;
  /** 是否显示 16:9 */
  ratio?: "16:9" | "9:16" | "1:1" | "4:3";
  /** 填满外部固定尺寸容器，不再使用自身宽高比撑开布局 */
  fill?: boolean;
  imageUrl?: string;
  videoUrl?: string;
}

const ratioClass: Record<NonNullable<VideoThumbProps["ratio"]>, string> = {
  "16:9": "aspect-video",
  "9:16": "aspect-[9/16]",
  "1:1": "aspect-square",
  "4:3": "aspect-[4/3]",
};

export function VideoThumb({
  className = "",
  rounded = "rounded-xl",
  showPlay = true,
  ratio = "16:9",
  fill = false,
  imageUrl,
  videoUrl,
}: VideoThumbProps) {
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);
  const [failedVideoUrl, setFailedVideoUrl] = useState<string | null>(null);

  const sizeClass = fill ? "absolute inset-0 h-full w-full" : `relative ${ratioClass[ratio]}`;
  const showImage = Boolean(imageUrl) && failedImageUrl !== imageUrl;
  const showVideo = !showImage && Boolean(videoUrl) && failedVideoUrl !== videoUrl;
  const hasPreview = showImage || showVideo;
  return (
    <div
      className={`overflow-hidden ${sizeClass} ${rounded} bg-ink ${className}`}
    >
      {showImage ? (
        <img
          src={imageUrl}
          alt=""
          onError={() => setFailedImageUrl(imageUrl ?? null)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : showVideo ? (
        <video
          src={videoUrl}
          muted
          playsInline
          preload="metadata"
          onError={() => setFailedVideoUrl(videoUrl ?? null)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-canvas text-muted">
          <Film className="h-7 w-7" strokeWidth={1.5} />
          <span className="mt-1 text-[10px]">暂无预览</span>
        </div>
      )}
      {hasPreview && (
        <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/30 to-transparent" />
      )}
      {showPlay && hasPreview && (
        <span className="absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white/20 backdrop-blur-sm transition group-hover:scale-110 group-hover:bg-white/30">
          <Play size={16} className="ml-0.5 fill-white text-white" />
        </span>
      )}
    </div>
  );
}

export default VideoThumb;
