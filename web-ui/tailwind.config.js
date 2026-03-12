/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bismuth: {
          bg:       '#0a0e1a',
          surface:  '#111827',
          border:   '#1f2937',
          muted:    '#374151',
          text:     '#e5e7eb',
          dim:      '#9ca3af',
          accent:   '#3b82f6',
          green:    '#10b981',
          yellow:   '#f59e0b',
          red:      '#ef4444',
          blue:     '#3b82f6',
          grey:     '#6b7280',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['IBM Plex Sans', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
