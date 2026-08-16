import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // 使用相对资源路径，兼容 GitHub Pages 的 /dc-forge/ 仓库子路径。
  base: './',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/enterprise': 'http://127.0.0.1:8000',
      '/mcp': 'http://127.0.0.1:8000',
      '/internal-console': 'http://127.0.0.1:8000',
      '^/presales/projects': 'http://127.0.0.1:8000',
    },
  },
  build: {
    rollupOptions: {
      input: {
        portal: new URL('./index.html', import.meta.url).pathname,
        presalesWorkbench: new URL('./presales/workbench/index.html', import.meta.url).pathname,
        customerEngagement: new URL('./customer/engagement/index.html', import.meta.url).pathname,
      },
    },
  },
})
