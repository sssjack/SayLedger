import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base 由命令行决定：
//   npm run build                          -> 部署在域名根路径
//   npm run build -- --base=/jizhang/      -> 部署在子路径
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5288,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8791',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
          react: ['react', 'react-dom'],
        },
      },
    },
  },
})
