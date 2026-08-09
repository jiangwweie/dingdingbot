import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        owner: {
          background: "var(--color-background)",
          surface: "var(--color-surface)",
          elevated: "var(--color-surface-secondary)",
          divider: "var(--color-divider)",
          text: "var(--color-text-primary)",
          muted: "var(--color-text-secondary)",
          emphasis: "var(--color-emphasis)",
          success: "var(--color-success)",
          danger: "var(--color-danger)",
        },
      },
      maxWidth: {
        owner: "var(--layout-max-width)",
      },
      height: {
        nav: "var(--height-navigation)",
      },
      fontFamily: {
        sans: ["Inter", "IBM Plex Sans", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
