<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, default: 0 },
  size: { type: Number, default: 84 },
  label: { type: String, default: '综合评分' },
})

const normalized = computed(() => Math.max(0, Math.min(100, props.score || 0)))
</script>

<template>
  <a-progress
    class="score-ring"
    type="circle"
    :percent="normalized"
    :size="size"
    :stroke-width="8"
    stroke-color="#1677ff"
    :aria-label="`${label} ${normalized.toFixed(1)} 分`"
  >
    <template #format>
      <div class="score-ring__inner">
      <strong>{{ normalized.toFixed(1) }}</strong>
      <small>{{ label }}</small>
      </div>
    </template>
  </a-progress>
</template>
