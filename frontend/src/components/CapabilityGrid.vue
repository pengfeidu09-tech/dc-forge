<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps({
  components: { type: Array, default: () => [] },
})

const expandedId = ref('')

const capabilityIcons = {
  'anomaly-classification': 'spark',
  'ticket-routing': 'flow',
  'human-approval': 'user',
  'process-monitoring': 'target',
  'feishu-notification': 'arrow',
  'audit-log': 'shield',
  'quality-dashboard': 'grid',
  'enterprise-rag': 'database',
  'feedback-loop': 'flow',
}
</script>

<template>
  <div class="capability-grid">
    <article
      v-for="(item, index) in components"
      :key="item.component_id"
      class="capability-card"
      :class="{ 'capability-card--expanded': expandedId === item.component_id }"
      @click="expandedId = expandedId === item.component_id ? '' : item.component_id"
    >
      <div class="capability-card__head">
        <span class="capability-card__icon" :style="{ '--delay': `${index * 40}ms` }">
          <AppIcon :name="capabilityIcons[item.component_id] || 'layers'" />
        </span>
        <span class="capability-card__index">{{ String(index + 1).padStart(2, '0') }}</span>
      </div>
      <strong>{{ item.name }}</strong>
      <small>{{ item.component_id }}</small>
      <p>{{ item.reason }}</p>
      <div class="capability-card__data">
        <span>需要数据</span>
        <div>
          <em v-for="data in item.required_data" :key="data">{{ data }}</em>
        </div>
      </div>
    </article>
  </div>
</template>
