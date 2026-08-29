const WORDMARK_DARK = "/branding/openvma-wordmark-minimal-dark.svg";
const WORDMARK_LIGHT = "/branding/openvma-wordmark-minimal-light.svg";
const MARK_DARK = "/branding/openvma-mark-minimal-dark.svg";
const MARK_LIGHT = "/branding/openvma-mark-minimal-light.svg";

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
      className={`openvma-brand openvma-brand--${variant} ${className}`.trim()}
      aria-hidden={decorative || undefined}
    >
      <img
        className={isWordmark ? "openvma-brand-wordmark" : "openvma-brand-mark"}
        src={BRAND_ASSETS[variant][tone]}
        width={isWordmark ? 508 : 100}
        height={100}
        style={isWordmark ? { height, width: "auto" } : { width: size, height: size }}
        alt={decorative ? "" : "OpenVMA"}
        draggable="false"
      />
    </span>
  );
}

export default BrandLogo;
