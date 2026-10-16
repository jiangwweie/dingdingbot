/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#080A0D',
        surface: {
          1: '#0F1318',
          2: '#151B22',
          3: '#1C242E',
        },
        border: {
          base: '#222933',
          strong: '#2D3745',
          subtle: 'rgba(255, 255, 255, 0.07)',
        },
        brand: {
          DEFAULT: '#F59E0B',
          hover: '#D97706',
          subtle: 'rgba(245, 158, 11, 0.12)',
        },
        status: {
          green: '#10B981',
          'green-bg': 'rgba(16, 185, 129, 0.12)',
          amber: '#F59E0B',
          'amber-bg': 'rgba(245, 158, 11, 0.12)',
          red: '#EF4444',
          'red-bg': 'rgba(239, 68, 68, 0.14)',
          blue: '#3B82F6',
          'blue-bg': 'rgba(59, 130, 246, 0.12)',
        }
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
