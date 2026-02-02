/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'cp-dark': 'var(--cp-bg-dark)',
        'cp-card': 'var(--cp-bg-card)',
        'cp-neon-green': 'var(--cp-neon-green)',
        'cp-neon-purple': 'var(--cp-neon-purple)',
        'cp-neon-blue': 'var(--cp-neon-blue)',
        'cp-text': 'var(--cp-text-main)',
        'cp-text-muted': 'var(--cp-text-muted)',
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.8s ease-out forwards',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(30%)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
