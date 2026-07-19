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

async function readFile(type, event) {
  const file = event.target.files?.[0]
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
  } finally {
    event.target.value = ''
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
        <section class="import-modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
          <button class="modal-close" aria-label="关闭" @click="emit('close')">
            <AppIcon name="close" />
          </button>
          <div class="modal-kicker"><AppIcon name="database" :size="16" /> DATA CONNECTOR</div>
          <h2 id="import-title">替换可视化数据</h2>
          <p>导入与示例结构一致的 JSONL 文件，数据只在当前浏览器内解析，不会上传服务器。</p>

          <div class="upload-grid">
            <label class="upload-card">
              <input type="file" accept=".jsonl,.json" @change="readFile('input', $event)" />
              <span class="upload-card__icon"><AppIcon name="upload" /></span>
              <strong>输入方案</strong>
              <small>{{ inputName || 'input_solutions.jsonl' }}</small>
              <em>选择文件</em>
            </label>
            <label class="upload-card">
              <input type="file" accept=".jsonl,.json" @change="readFile('output', $event)" />
              <span class="upload-card__icon upload-card__icon--cyan"><AppIcon name="download" /></span>
              <strong>输出方案包</strong>
              <small>{{ outputName || 'solution_bundles.jsonl' }}</small>
              <em>选择文件</em>
            </label>
          </div>
          <p v-if="status && !error" class="upload-message upload-message--success">
            <AppIcon name="check" :size="16" /> {{ status }}
          </p>
          <p v-if="error" class="upload-message upload-message--error">
            <AppIcon name="warning" :size="16" /> {{ error }}
          </p>
          <div class="format-note">
            <AppIcon name="code" :size="18" />
            <span>
              <strong>格式说明</strong>
              每行一个 JSON 对象；输出对象需要包含 <code>project_id</code> 和 <code>plans</code>。
            </span>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
