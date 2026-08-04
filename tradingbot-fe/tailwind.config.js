/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      animation: {
        'pulse-subtle': 'pulse-subtle 0.6s ease-out',
      },
      keyframes: {
        'pulse-subtle': {
          '0%': { boxShadow: '0 0 0 0 rgba(6, 182, 212, 0.4)' },
          '50%': { boxShadow: '0 0 0 6px rgba(6, 182, 212, 0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(6, 182, 212, 0)' },
        },
      },
    },
  },
  plugins: [],
}
