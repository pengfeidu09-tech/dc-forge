<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'import'])
const inputName = ref('')
const outputName = ref('')
const status = ref('')
const error = ref('')

async function readFile(type, file) {
  if (!file) return

  error.value = ''
  try {
    const raw = await file.text()
    emit('import', { type, raw })
    if (type === 'input') inputName.value = file.name
    else outputName.value = file.name
    status.value = `${file.name} 已载入`
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '文件解析失败'
  }
  return false
}
</script>

<template>
  <a-modal :open="open" title="替换可视化数据" :footer="null" width="720px" @cancel="emit('close')">
    <a-alert type="info" show-icon message="文件只在当前浏览器内解析，不会上传服务器。" />
    <a-row :gutter="16" class="upload-grid">
      <a-col :span="12">
        <a-upload-dragger accept=".jsonl,.json" :show-upload-list="false" :before-upload="(file) => readFile('input', file)">
          <AppIcon name="upload" /><p class="ant-upload-text">输入方案</p><p class="ant-upload-hint">{{ inputName || 'input_solutions.jsonl' }}</p>
        </a-upload-dragger>
      </a-col>
      <a-col :span="12">
        <a-upload-dragger accept=".jsonl,.json" :show-upload-list="false" :before-upload="(file) => readFile('output', file)">
          <AppIcon name="download" /><p class="ant-upload-text">输出方案包</p><p class="ant-upload-hint">{{ outputName || 'solution_bundles.jsonl' }}</p>
        </a-upload-dragger>
      </a-col>
    </a-row>
    <a-alert v-if="status && !error" type="success" show-icon :message="status" />
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <a-typography-paragraph type="secondary">每行一个 JSON 对象；输出对象需要包含 <code>project_id</code> 和 <code>plans</code>。</a-typography-paragraph>
  </a-modal>
</template>
