/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Direct Semantic Tokens
        background: 'var(--color-background)',
        surface: {
          DEFAULT: 'var(--color-surface)',
          1: 'var(--color-surface)',
          2: 'var(--color-surface-subtle)',
          3: 'var(--color-surface-elevated)',
          elevated: 'var(--color-surface-elevated)',
          subtle: 'var(--color-surface-subtle)',
        },
        canvas: 'var(--color-background)',
        border: {
          DEFAULT: 'var(--color-border)',
          base: 'var(--color-border)',
          strong: 'var(--color-border-strong)',
          subtle: 'var(--color-border)',
        },
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-muted': 'var(--color-text-muted)',
        'text-disabled': 'var(--color-text-disabled)',
        accent: {
          DEFAULT: 'var(--color-accent)',
          hover: 'var(--color-accent-hover)',
          subtle: 'var(--color-accent-subtle)',
        },
        brand: {
          DEFAULT: 'var(--color-accent)',
          hover: 'var(--color-accent-hover)',
          subtle: 'var(--color-accent-subtle)',
        },
        status: {
          green: 'var(--color-success)',
          'green-bg': 'var(--color-success-bg)',
          amber: 'var(--color-warning)',
          'amber-bg': 'var(--color-warning-bg)',
          red: 'var(--color-danger)',
          'red-bg': 'var(--color-danger-bg)',
          'red-border': 'var(--color-danger-border)',
          blue: 'var(--color-info)',
          'blue-bg': 'var(--color-info-bg)',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
