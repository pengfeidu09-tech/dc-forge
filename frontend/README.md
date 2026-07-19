# DC Forge 前端可视化

基于 Vue 3 + Vite 的输入输出方案可视化工作台。默认读取 `mock` 目录中的两份 JSONL，也支持在页面中临时导入同结构文件。

## 启动

```bash
npm install
npm run dev
```

生产构建：

```bash
npm run build
npm run preview
```

## GitHub Pages

仓库已配置 `.github/workflows/deploy-frontend.yml`。推送到 `main` 分支后，GitHub Actions 会自动构建并发布 `frontend/dist`。

默认站点地址：

```text
https://pengfeidu09-tech.github.io/dc-forge/
```

## 数据约定

- 输入文件：每行包含一个方案对象，并使用 `source_project_id` 关联项目。
- 输出文件：每行包含 `project_id` 与 `plans` 数组。
- 页面导入的数据只在浏览器内存中解析，不会被上传。

## 目录结构

```text
src/
├── components/      # 可复用展示与交互组件
├── composables/     # JSONL 解析、选择状态和数据替换
├── styles/          # 设计变量、全局样式和响应式布局
├── App.vue          # 工作台编排
└── main.js
```
