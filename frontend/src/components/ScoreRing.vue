<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, default: 0 },
  size: { type: Number, default: 84 },
  label: { type: String, default: '综合评分' },
})

const normalized = computed(() => Math.max(0, Math.min(100, props.score || 0)))
const ringStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  '--score': `${normalized.value * 3.6}deg`,
}))
</script>

<template>
  <div class="score-ring" :style="ringStyle" :aria-label="`${label} ${normalized.toFixed(1)} 分`">
    <div class="score-ring__inner">
      <strong>{{ normalized.toFixed(1) }}</strong>
      <small>{{ label }}</small>
    </div>
  </div>
</template>
