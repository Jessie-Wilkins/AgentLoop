import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "test-results/**", "playwright-report/**", "node_modules/**"]
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        document: "readonly",
        HTMLCanvasElement: "readonly",
        MouseEvent: "readonly",
        process: "readonly",
        requestAnimationFrame: "readonly",
        window: "readonly"
      }
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off"
    }
  }
);
