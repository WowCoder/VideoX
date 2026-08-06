import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.flat.recommended.rules,
      // 本项目的弹窗和服务端数据水合广泛采用“输入变化后重置本地表单”的模式。
      // 这条 React Compiler 建议会把这些有意的同步状态重置全部判为错误；
      // 依赖完整性、不可变性和 Hooks 调用顺序等正确性规则仍保持启用。
      "react-hooks/set-state-in-effect": "off",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    files: ["src/router.tsx", "src/components/ui/Toast.tsx"],
    rules: {
      // 路由模块和 Toast 模块有意同时导出组件与配套 hooks。
      "react-refresh/only-export-components": "off",
    },
  },
);
