import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // OpenAI 风格的中性黑白设计令牌。保留既有语义类名，避免业务组件
        // 为了换肤重复维护两套颜色体系。
        ink: { DEFAULT: "#171717", 2: "#242424" },
        blue: {
          DEFAULT: "#171717",
          2: "#000000",
          soft: "#f0f0f1",
        },
        teal: "#357a58",
        amber: "#9a681f",
        red: "#b94747",
        text: "#171717",
        muted: "#73757b",
        line: "#e5e5e7",
        surface: "#ffffff",
        canvas: "#f7f7f8",
      },
      fontFamily: {
        sans: ['Inter', '"PingFang SC"', '"Microsoft YaHei"', "system-ui", "sans-serif"],
      },
      borderRadius: {
        pill: "9999px",
      },
      boxShadow: {
        soft: "0 16px 40px rgba(0,0,0,.08)",
      },
      transitionDuration: {
        fast: "160ms",
      },
    },
  },
  plugins: [],
};

export default config;
