/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./shop.html",
    "./chaos.html",
    "./phone.html",
    "./src/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        airlock: {
          canvas: '#0B0E14',
          deep: '#080A10',
          panel: '#0C1017',
          base: '#1A1C23',
          card: '#252830',
          border: '#3A3F4C',
          text: '#D1D5DB',
          muted: '#94A3B8',
          faint: '#64748B',
          excellent: '#10B981',
          good: '#06B6D4',
          fair: '#F59E0B',
          poor: '#EF4444',
          offline: '#64748B',
          privacy: '#A855F7',
          local: '#A3E635',
          accent: '#38BDF8',
          high: '#F97316',
        }
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'Menlo', 'monospace'],
      }
    },
  },
  plugins: [],
}
