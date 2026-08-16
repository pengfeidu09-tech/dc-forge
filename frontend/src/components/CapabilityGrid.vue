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
  <a-row class="capability-grid" :gutter="[14, 14]">
    <a-col
      v-for="(item, index) in components"
      :key="item.component_id"
      :xs="24"
      :md="12"
      :xl="8"
    >
      <a-card
        class="capability-card"
        hoverable
        :class="{ 'capability-card--expanded': expandedId === item.component_id }"
        @click="expandedId = expandedId === item.component_id ? '' : item.component_id"
      >
        <template #title>
          <a-space>
          <AppIcon :name="capabilityIcons[item.component_id] || 'layers'" />
            <span>{{ String(index + 1).padStart(2, '0') }} · {{ item.name }}</span>
          </a-space>
        </template>
        <template #extra><a-tag>{{ item.component_id }}</a-tag></template>
        <a-typography-paragraph>{{ item.reason }}</a-typography-paragraph>
        <a-divider orientation="left" plain>需要数据</a-divider>
        <a-space wrap>
          <a-tag v-for="data in item.required_data" :key="data" color="blue">{{ data }}</a-tag>
        </a-space>
      </a-card>
    </a-col>
  </a-row>
</template>
