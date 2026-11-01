import type { Config } from "tailwindcss";

// CivicConnect design tokens: a restrained, government-style palette. Navy is the only
// brand colour; status colours are reserved for meaning (success, warning, danger).
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 50: "#eef2f8", 100: "#d6dfec", 200: "#adbfd9", 500: "#34558c", 600: "#1f3a6b", 700: "#172e57", 800: "#112342", 900: "#0b1830" },
        teal: { 50: "#edf6f5", 100: "#cfe7e4", 500: "#1b7f75", 600: "#156a62", 700: "#10554f" },
      },
      fontFamily: {
        sans: ["'Noto Sans'", "'Noto Sans Telugu'", "'Noto Sans Devanagari'", "'Noto Sans Kannada'", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", { lineHeight: "1rem" }] },
    },
  },
  plugins: [],
} satisfies Config;
