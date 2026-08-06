import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── 设计令牌映射（来自 MVP2 styles.css）──
        ink: { DEFAULT: "#0c1730", 2: "#132143" },
        blue: {
          DEFAULT: "#2865ed",
          2: "#1e53d5",
          soft: "#eaf1ff",
        },
        teal: "#17a890",
        amber: "#d98a14",
        red: "#d75151",
        text: "#172036",
        muted: "#68738a",
        line: "#e2e7f0",
        surface: "#ffffff",
        canvas: "#f3f6fb",
      },
      fontFamily: {
        sans: ['Inter', '"PingFang SC"', '"Microsoft YaHei"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        pill: "9999px",
      },
      boxShadow: {
        soft: "0 8px 24px rgba(23,35,63,.07)",
      },
      transitionDuration: {
        fast: "160ms",
      },
    },
  },
  plugins: [],
};

export default config;
