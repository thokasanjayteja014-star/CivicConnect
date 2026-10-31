import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 50: "#eef2f9", 100: "#d5deef", 600: "#1f3a6b", 700: "#172e57", 800: "#112342", 900: "#0b1830" },
        teal: { 50: "#ecfaf8", 100: "#cdf1ec", 500: "#14a394", 600: "#0f8579", 700: "#0d6b62" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
