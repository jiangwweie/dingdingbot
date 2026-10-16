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
          tertiary: "var(--color-surface-tertiary)",
          subtle: "var(--color-surface-subtle)",
          divider: "var(--color-divider)",
          "divider-subtle": "var(--color-divider-subtle)",
          text: "var(--color-text-primary)",
          muted: "var(--color-text-secondary)",
          tertiaryText: "var(--color-text-tertiary)",
          emphasis: "var(--color-emphasis)",
          "emphasis-hover": "var(--color-emphasis-hover)",
          "emphasis-subtle": "var(--color-emphasis-subtle)",
          success: "var(--color-success)",
          "success-hover": "var(--color-success-hover)",
          "success-subtle": "var(--color-success-subtle)",
          danger: "var(--color-danger)",
          "danger-hover": "var(--color-danger-hover)",
          "danger-subtle": "var(--color-danger-subtle)",
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
      boxShadow: {
        panel: "var(--shadow-decorative)",
        dropdown: "var(--shadow-dropdown)",
      },
      borderRadius: {
        control: "var(--radius-control)",
        panel: "var(--radius-panel)",
      },
    },
  },
  plugins: [],
} satisfies Config;
