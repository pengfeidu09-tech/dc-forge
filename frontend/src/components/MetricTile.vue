<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  icon: { type: String, default: 'layers' },
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  hint: { type: String, default: '' },
  tone: { type: String, default: 'violet' },
})
</script>

<template>
  <a-card class="metric-tile" size="small" :bordered="false">
    <a-statistic :title="label" :value="value">
      <template #prefix><AppIcon :name="icon" /></template>
      <template v-if="hint" #suffix><a-tooltip :title="hint">?</a-tooltip></template>
    </a-statistic>
  </a-card>
</template>
