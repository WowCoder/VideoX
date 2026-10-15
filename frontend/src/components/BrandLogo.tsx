const BRAND_BASE = `${import.meta.env.BASE_URL}branding/`;
const WORDMARK_DARK = `${BRAND_BASE}videox-wordmark-minimal-dark.svg`;
const WORDMARK_LIGHT = `${BRAND_BASE}videox-wordmark-minimal-light.svg`;
const MARK_DARK = `${BRAND_BASE}videox-mark-minimal-dark.svg`;
const MARK_LIGHT = `${BRAND_BASE}videox-mark-minimal-light.svg`;

const BRAND_ASSETS = {
  wordmark: { dark: WORDMARK_DARK, light: WORDMARK_LIGHT },
  mark: { dark: MARK_DARK, light: MARK_LIGHT },
} as const;

interface BrandLogoProps {
  variant?: "wordmark" | "mark";
  tone?: "dark" | "light";
  height?: number;
  size?: number;
  className?: string;
  decorative?: boolean;
}

export function BrandLogo({
  variant = "wordmark",
  tone = "dark",
  height = 16,
  size = 28,
  className = "",
  decorative = false,
}: BrandLogoProps) {
  const isWordmark = variant === "wordmark";
  return (
    <span
      className={`videox-brand videox-brand--${variant} ${className}`.trim()}
      aria-hidden={decorative || undefined}
    >
      <img
        className={isWordmark ? "videox-brand-wordmark" : "videox-brand-mark"}
        src={BRAND_ASSETS[variant][tone]}
        width={isWordmark ? 448 : 100}
        height={100}
        style={isWordmark ? { height, width: "auto" } : { width: size, height: size }}
        alt={decorative ? "" : "VideoX"}
        draggable="false"
      />
    </span>
  );
}

export default BrandLogo;
