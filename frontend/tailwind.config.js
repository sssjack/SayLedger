/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f6f7f9',
          100: '#eceef2',
          200: '#d5d9e2',
          300: '#b0b7c6',
          400: '#848ea4',
          500: '#667089',
          600: '#515a70',
          700: '#42495b',
          800: '#393e4d',
          900: '#1c1f27',
          950: '#101218',
        },
        accent: {
          DEFAULT: '#4f46e5',
          soft: '#eef2ff',
          ring: '#c7d2fe',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'sans-serif'],
        num: ['ui-rounded', '-apple-system', 'SF Pro Rounded', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,18,24,.04), 0 8px 24px -12px rgba(16,18,24,.18)',
        float: '0 8px 40px -8px rgba(16,18,24,.22)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%,100%': { opacity: '.35' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        rise: 'rise .28s cubic-bezier(.22,1,.36,1) both',
        pulseSoft: 'pulseSoft 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
