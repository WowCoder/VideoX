// ──────────────────────────────────────────────
// OpenVMA - 通用缩略图组件
// 根据 ThumbnailVariant 渲染渐变 + 图标，无需真实图片资源
// ──────────────────────────────────────────────

import { useState } from "react";
import type { ThumbnailVariant } from "@/types/models";
import {
  Mic2,
  Bot,
  MessageCircle,
  Users,
  Lightbulb,
  Building2,
  Presentation,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";

interface VariantMeta {
  gradient: string;
  Icon: LucideIcon;
  label: string;
}

const VARIANT_META: Record<ThumbnailVariant, VariantMeta> = {
  stage: { gradient: "from-blue to-blue-2", Icon: Mic2, label: "舞台" },
  robot: { gradient: "from-teal to-blue", Icon: Bot, label: "机器人" },
  interview: { gradient: "from-amber to-red", Icon: MessageCircle, label: "访谈" },
  crowd: { gradient: "from-red to-amber", Icon: Users, label: "人群" },
  lights: { gradient: "from-blue-soft to-blue", Icon: Lightbulb, label: "灯光" },
  hall: { gradient: "from-ink to-ink-2", Icon: Building2, label: "展厅" },
  speaker: { gradient: "from-teal to-ink", Icon: Presentation, label: "演讲" },
};

interface ThumbnailProps {
  variant: ThumbnailVariant;
  className?: string;
  /** 是否在左下角显示中文标签 */
  label?: boolean;
  imageUrl?: string;
}

export function Thumbnail({ variant, className, label = false, imageUrl }: ThumbnailProps) {
  const meta = VARIANT_META[variant] ?? VARIANT_META.stage;
  const { Icon } = meta;
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);
  const showImage = Boolean(imageUrl) && failedImageUrl !== imageUrl;
  return (
    <div
      className={clsx(
        "relative flex items-center justify-center overflow-hidden bg-gradient-to-br",
        meta.gradient,
        className,
      )}
    >
      {showImage ? (
        <img
          src={imageUrl}
          alt=""
          onError={() => setFailedImageUrl(imageUrl ?? null)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <Icon className="h-1/3 w-1/3 text-white/80" strokeWidth={1.5} />
      )}
      {label && (
        <span className="absolute bottom-1 left-1 rounded bg-black/25 px-1.5 py-0.5 text-[10px] font-medium text-white/90">
          {meta.label}
        </span>
      )}
      {!showImage && (
        <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.25),transparent_60%)]" />
      )}
    </div>
  );
}

export default Thumbnail;
