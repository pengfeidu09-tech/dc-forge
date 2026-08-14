import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // 使用相对资源路径，兼容 GitHub Pages 的 /dc-forge/ 仓库子路径。
  base: './',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/enterprise': 'http://127.0.0.1:8000',
      '/mcp': 'http://127.0.0.1:8000',
    },
  },
})
