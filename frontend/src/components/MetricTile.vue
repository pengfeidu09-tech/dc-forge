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
  <article class="metric-tile">
    <div class="metric-tile__icon" :class="`tone--${tone}`"><AppIcon :name="icon" /></div>
    <div>
      <span>{{ label }}</span>
      <strong>{{ value }}</strong>
      <small v-if="hint">{{ hint }}</small>
    </div>
  </article>
</template>
