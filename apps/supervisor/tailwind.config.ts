import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Дизайн-система Solvix Chronometry (светлая тема).
 * Семантические токены (background/foreground/primary/...) заданы в HSL
 * в src/index.css — они совместимы с shadcn/ui, поэтому `npx shadcn add ...`
 * сразу отдаёт компоненты в фирменном стиле.
 *
 * Статусные и брендовые оттенки (fl-*) заданы как готовые hex-переменные —
 * их удобно дергать в графиках и бейджах, где HSL-обёртка ни к чему.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      fontFamily: {
        sans: [
          "Manrope",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Бренд и статусы Solvix — прямые hex-переменные.
        brand: {
          DEFAULT: "var(--fl-brand)",
          hover: "var(--fl-brand-hover)",
          soft: "var(--fl-brand-soft)",
          faint: "var(--fl-brand-faint)",
        },
        ink: "var(--fl-ink)",
        gold: "var(--fl-gold)",
        status: {
          ok: "var(--fl-ok)",
          "ok-soft": "var(--fl-ok-soft)",
          warn: "var(--fl-warn)",
          "warn-soft": "var(--fl-warn-soft)",
          danger: "var(--fl-danger)",
          "danger-soft": "var(--fl-danger-soft)",
          info: "var(--fl-info)",
          "info-soft": "var(--fl-info-soft)",
          idle: "var(--fl-idle)",
          "idle-soft": "var(--fl-idle-soft)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.04)",
        float: "0 12px 30px rgba(16,24,40,0.09)",
      },
      keyframes: {
        "fl-ring": {
          "0%": { transform: "scale(.9)", opacity: "0.5" },
          "80%": { transform: "scale(1.35)", opacity: "0" },
          "100%": { opacity: "0" },
        },
        "fl-fade": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" },
        },
        "fl-pulse": {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "fl-ring": "fl-ring 2.6s ease-out infinite",
        "fl-fade": "fl-fade .28s ease both",
        "fl-pulse": "fl-pulse 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [animate],
};

export default config;
