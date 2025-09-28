/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#7c5cff',
          hover: '#6b4cff',
        },
        accent: {
          DEFAULT: '#00d1b2',
          hover: '#00b89f',
        },
        danger: '#ff5c7c',
        warning: '#ffd166',
        muted: '#64748b',
        border: '#e5e7eb',
        panel: '#ffffff',
        'panel-2': '#f8fafc',
        text: '#0f172a',
        bg: '#ffffff',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol'],
      },
      animation: {
        'fade-in': 'fadeIn 0.35s ease',
        'xp-pop': 'xpPop 1.1s ease forwards',
        'marquee': 'marquee 40s linear infinite',
        'party-glow': 'partyGlow 6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0', transform: 'translateY(3px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
        xpPop: {
          '0%': { opacity: '0', transform: 'translate(-50%, 6px) scale(0.9)' },
          '20%': { opacity: '1', transform: 'translate(-50%, 0) scale(1)' },
          '100%': { opacity: '0', transform: 'translate(-50%, -24px) scale(0.9)' },
        },
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        partyGlow: {
          '0%, 100%': { filter: 'hue-rotate(0deg) brightness(1)' },
          '50%': { filter: 'hue-rotate(60deg) brightness(1.15)' },
        },
      },
    },
  },
  plugins: [
    require('daisyui'),
  ],
  daisyui: {
    themes: ['light'],
    darkTheme: 'dark',
    base: true,
    styled: true,
    utils: true,
    prefix: '',
    logs: true,
    themeRoot: ':root',
  },
}